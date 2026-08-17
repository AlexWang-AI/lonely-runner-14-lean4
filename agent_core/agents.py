"""
agents.py — 智能双子星: ProverAgent (推导主攻手) 与 CriticAgent (按需纠偏哨兵)

战略原则【以推理为主, 纠偏为哨兵 (乐观推导机制)】:
  - ProverAgent 是绝对主角, 由 deepseek-v4-pro (深度推理模型) 承担全部推导工作;
  - CriticAgent 是轻量哨兵 (deepseek-v4-flash), 仅在 Lean 编译失败时被动唤醒,
    绝不允许喧宾夺主或制造无意义的交互摩擦;
  - 失败的尝试是宝贵资产: Critic 不仅纠错, 更负责把"走不通的路"提炼为
    【禁手规则】存入错题本 (failure_log), 供 Prover 后续避坑 — 即"测绘雷区"。

两个 Agent 均为异步实现 (openai AsyncOpenAI), 与 main_loop 的 asyncio 状态机对接。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Sequence

from dotenv import load_dotenv
from openai import AsyncOpenAI, BadRequestError

# ---------------------------------------------------------------------------
# 环境配置 (从项目根目录 .env 读取, 带默认值兜底)
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

PROVER_MODEL: Final[str] = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-v4-pro")
CRITIC_MODEL: Final[str] = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-v4-flash")
_BASE_URL: Final[str] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ---- 性能手术: 思维链预算控制 (可通过 .env 覆盖) ----
# 输出 token 上限: 证明代码 4096 token 绰绰有余, 诊断 JSON 1024 token 足够
PROVER_MAX_TOKENS: Final[int] = int(os.getenv("DEEPSEEK_PROVER_MAX_TOKENS", "4096"))
CRITIC_MAX_TOKENS: Final[int] = int(os.getenv("DEEPSEEK_CRITIC_MAX_TOKENS", "1024"))
# 思考预算 (若 API 支持 thinking_budget 参数): 限制推理模型的无节制深度思考。
# 本机实测: 无预算时 v4-pro 对简单命题空转 170.6 秒; 设预算后目标 <60 秒。
THINKING_BUDGET: Final[int | None] = (
    int(os.getenv("DEEPSEEK_THINKING_BUDGET", "1024"))
    if os.getenv("DEEPSEEK_THINKING_BUDGET") else None
)

# 共享异步客户端 (超时 600s: 推理模型的深度思考可能较久)
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """惰性创建共享的 AsyncOpenAI 客户端; 缺少 API Key 时给出明确报错。"""
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY, 请先配置项目根目录的 .env 文件 (参考 .env.example)"
            )
        _client = AsyncOpenAI(api_key=api_key, base_url=_BASE_URL, timeout=600.0)
    return _client


# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------

# 错误性质二分: minor = 轻微语法/类型小错 (可微调); dead_end = 数学思路死胡同 (须掉头)
ErrorClass = Literal["minor", "dead_end"]


@dataclass(frozen=True)
class CriticDiagnosis:
    """CriticAgent 的结构化诊断结果 (机器可读, 供状态机分支)。"""

    error_class: ErrorClass
    fix_instruction: str          # 代码级修正方向 (≤3 句硬核建议)
    forbidden_rule: str | None    # 死胡同时的【禁手总结】, 存入错题本供 Prover 避坑


# ---------------------------------------------------------------------------
# 组件 A: ProverAgent — 数学探索主攻手 (deepseek-v4-pro)
# ---------------------------------------------------------------------------

_PROVER_SYSTEM_PROMPT: Final[str] = (
    "你是一个前沿数学推导引擎。在给出推导时：\n"
    "1. 仔细阅读【禁手与失败记录】，绝对不要重复走不通的老路。\n"
    "2. 给出下一步的数学直觉与逻辑分析（2-4 句即可，不要长篇大论）。\n"
    "3. 将最终的 Lean 4 证明代码包裹在 `<lean_code>` 和 `</lean_code>` 标签中。\n"
    "\n"
    "输出结构必须严格为：\n"
    "1. 简要的数学逻辑步骤阐述。\n"
    "2. 包含在 `<lean_code>` 和 `</lean_code>` 标签内的完整 Lean 4 证明代码。\n"
    "严禁任何客套话和多余闲聊。\n"
    "\n"
    "【策略优先级】（最高指令）：\n"
    "1. 若目标可被 Mathlib 现有 tactic 一键闭合（如 linarith / ring / norm_num / "
    "aesop / omega / positivity / simpa using ... / exact 已知定理），立即输出，"
    "不要生成冗长的底层证明思维链。\n"
    "2. 严禁车轱辘话自我反思：数学分析不超过 2-3 句，直接给出代码。\n"
    "\n"
    "代码规范：\n"
    "- 输出【当前完整证明状态】的代码：包含此前已通过验证的部分，"
    "尚未攻克的子目标处用 `sorry` 占位（分步推进，逐步消灭 sorry）。\n"
    "- 不要输出任何 import 语句，系统会自动注入所需导入；"
    "仅在确实需要特定子模块时（如 `import Mathlib.Data.Real.Basic`）才显式写 import。\n"
    "- 代码必须能独立编译（除 sorry 外不得引用未定义的名字）。"
)


class ProverAgent:
    """推导核心 — 数学探索主攻手。

    输入: 目标定理 + 当前已证明的步骤上下文 + 历史失败尝试与禁手列表 (Failure Memory)。
    输出: 原始 LLM 文本 (含 <lean_code> 标签), 代码提取交给 LeanValidator 完成。
    """

    def __init__(
        self,
        model: str = PROVER_MODEL,
        max_tokens: int = PROVER_MAX_TOKENS,
        thinking_budget: int | None = THINKING_BUDGET,
    ) -> None:
        """初始化 ProverAgent。

        Args:
            model: 推理模型名 (默认 deepseek-v4-pro)。
            max_tokens: 输出 token 上限 (性能手术: 截断无节制长输出)。
            thinking_budget: 思考预算 (若 API 支持 thinking_budget 参数),
                限制推理模型的深度思考时长, 实测可把 170s 空转压到一分钟内。
        """
        self.model: str = model
        self.max_tokens: int = max_tokens
        self.thinking_budget: int | None = thinking_budget
        self.client: AsyncOpenAI = _get_client()

    async def _complete(self, system: str, user: str) -> str:
        """底层补全调用: 携带思维链预算; 空内容/参数拒绝时自动降级重试。

        实测教训 (Erdős 首战): 推理模型思考阶段耗尽预算时会返回空 content,
        必须重试 (去掉 thinking_budget + 加倍 max_tokens) 而非直接崩溃。
        """
        # 实测 (2026-08-17): v4-pro 推理模式下 reasoning_content 会吃光输出,
        # content 恒为空 (8192/32768 预算均无效) → 必须显式关闭推理模式。
        # extra_body 直通服务端; thinking_budget 参数本身不被 SDK 接受 (TypeError)。
        extra_body: dict = {"thinking": {"type": "disabled"}}
        budget_kwargs: dict[str, int] = {"max_tokens": self.max_tokens}
        if self.thinking_budget is not None:
            budget_kwargs["thinking_budget"] = self.thinking_budget
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            resp = await self.client.chat.completions.create(
                model=self.model, messages=messages, extra_body=extra_body,
                **budget_kwargs,
            )
        except (BadRequestError, TypeError):
            # thinking_budget 不被支持时降级: 仅保留 max_tokens 重试。
            # TypeError = SDK 客户端签名校验拒绝 (openai 3.x 实测);
            # BadRequestError = 服务端拒绝 (旧 SDK 路径)。两者同待遇。
            resp = await self.client.chat.completions.create(
                model=self.model, messages=messages, extra_body=extra_body,
                max_tokens=self.max_tokens,
            )
        content = (resp.choices[0].message.content or "").strip()
        if content:
            return content
        # 空内容 (思考耗尽预算): 去掉 thinking_budget 且加倍 max_tokens 重试一次
        resp = await self.client.chat.completions.create(
            model=self.model, messages=messages,
            max_tokens=self.max_tokens * 2,
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError(
                f"ProverAgent 模型连续两次返回空内容 (model={self.model}), "
                f"请检查 thinking_budget 配置或换用更简单的目标"
            )
        return content

    @staticmethod
    def _format_failure_log(failure_log: Sequence[str]) -> str:
        """将错题本格式化为提示词片段; 空时明确告知可以放心探索。"""
        if not failure_log:
            return "（暂无禁手记录 — 放心探索全新路线）"
        return "\n".join(f"  - {rule}" for rule in failure_log)

    async def derive_next(
        self,
        goal: str,
        proven_context: str,
        failure_log: Sequence[str],
        literature_boundary: str | None = None,
    ) -> str:
        """主推导调用: 生成下一步证明代码 (乐观推导的正向路径)。

        Args:
            goal: 目标定理命题 (Lean 4 的 theorem 声明或自然语言描述)。
            proven_context: 当前已通过 Lean 验证的证明代码 (可为空)。
            failure_log: 错题本 (禁手与失败记录), 必须逐条遵守。
            literature_boundary: 文献查新边界 (ScoutAgent 报告摘要, 可为空)。
                前人已证方向禁止重复劳动, 优先从空白处发起进攻。

        Returns:
            LLM 原始输出文本 (含 <lean_code> 标签)。
        """
        parts = [
            "【目标定理】",
            goal,
            "",
            "【当前已通过验证的证明代码】(可能为空)",
            proven_context or "（空 — 请从头开始构造证明）",
            "",
            "【禁手与失败记录 (Failure Memory)】(必须逐条遵守, 绝不重复走不通的老路)",
            self._format_failure_log(failure_log),
        ]
        if literature_boundary:
            parts += [
                "",
                "【文献查新边界 (Scout 哨兵)】(前人成果与未决空白: "
                "已被证明的方向禁止重复劳动, 优先从空白处发起进攻)",
                literature_boundary,
            ]
        parts += [
            "",
            "请输出下一步推导: 完整 Lean 4 代码 (含已验证部分, 未完成处用 sorry 占位), "
            "包裹在 <lean_code> 标签中。",
        ]
        user_prompt = "\n".join(parts)
        return await self._complete(_PROVER_SYSTEM_PROMPT, user_prompt)

    async def repair(
        self,
        goal: str,
        failing_code: str,
        error_log: str,
        fix_instruction: str,
        failure_log: Sequence[str],
    ) -> str:
        """微调修复调用: 按 Critic 的代码级修正指令就地修复 (轻微错误的就地纠偏)。

        Args:
            goal: 目标定理命题。
            failing_code: 编译失败的完整代码。
            error_log: Lean 编译器错误日志 (已截断)。
            fix_instruction: Critic 给出的代码级修正方向。
            failure_log: 错题本 (修复时同样不得触碰禁手)。

        Returns:
            LLM 原始输出文本 (含 <lean_code> 标签的修复后完整代码)。
        """
        user_prompt = (
            "【目标定理】\n"
            f"{goal}\n"
            "\n"
            "【Critic 诊断】(必须按此方向修复, 不要另起炉灶)\n"
            f"{fix_instruction}\n"
            "\n"
            "【Lean 编译器错误日志】\n"
            f"{error_log}\n"
            "\n"
            "【当前失败代码】\n"
            f"{failing_code}\n"
            "\n"
            "【禁手与失败记录】(不得触碰)\n"
            f"{self._format_failure_log(failure_log)}\n"
            "\n"
            "请就地微调修复, 输出修复后的【完整】代码 (含已验证部分), "
            "包裹在 <lean_code> 标签中。"
        )
        return await self._complete(_PROVER_SYSTEM_PROMPT, user_prompt)


# ---------------------------------------------------------------------------
# 组件 B: CriticAgent — 按需纠偏哨兵 (deepseek-v4-flash)
# ---------------------------------------------------------------------------

_CRITIC_SYSTEM_PROMPT: Final[str] = (
    "你是一个无情的 Lean 4 编译报错诊断专家。你的唯一任务是阅读 Lean 编译器的 "
    "Error Log 和 Prover 的代码，精准指出哪一行、哪个类型或哪个 tactic 出错，"
    "并用不超过 3 句话给出具体的修复方向。不要做宏观哲学讨论，只给硬核修改建议。\n"
    "\n"
    "诊断规则：\n"
    "1. 分析报错根因：是简单的语法/类型小错（error_class=minor），"
    "还是底层的数学思路死胡同（error_class=dead_end）？\n"
    "2. 语法小错：fix_instruction 直接给出代码级修正指令（改哪一行、改成什么）。\n"
    "3. 数学思路撞墙：提炼出一条清晰的【禁手总结】（例如：'由于边界发散，"
    "不要再尝试直接对该项求导'），填入 forbidden_rule，存入记忆库供 Prover 避坑。\n"
    "\n"
    "输出格式【严格要求】为 JSON 对象，不要输出 JSON 以外的任何内容：\n"
    '{"error_class": "minor" 或 "dead_end", '
    '"fix_instruction": "代码级修正方向 (≤3 句)", '
    '"forbidden_rule": "禁手总结 (仅 dead_end 时填写, 否则为 null)"}'
)

# 容错解析: 从 LLM 输出中抠出 JSON 对象 (允许模型在 JSON 外多说话)
_JSON_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)


class CriticAgent:
    """按需纠偏 — 轻量级、低延迟的报错分析器 (只在编译失败时被动唤醒)。

    不仅纠错, 更负责提炼"负向知识": 把数学死胡同转成【禁手规则】写入错题本,
    使失败的尝试成为"测绘雷区"的宝贵资产。
    """

    def __init__(self, model: str = CRITIC_MODEL, max_tokens: int = CRITIC_MAX_TOKENS) -> None:
        self.model: str = model
        self.max_tokens: int = max_tokens
        self.client: AsyncOpenAI = _get_client()

    def _parse_diagnosis(self, raw: str) -> CriticDiagnosis:
        """解析 Critic 的 JSON 输出; 解析失败时用关键词启发式兜底分类。"""
        match = _JSON_BLOCK_PATTERN.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                error_class: ErrorClass = (
                    "dead_end" if str(data.get("error_class", "")).strip().lower() == "dead_end"
                    else "minor"
                )
                fix = str(data.get("fix_instruction") or "请检查类型并就地修正").strip()
                forbidden = str(data.get("forbidden_rule") or "").strip() or None
                if error_class == "dead_end" and not forbidden:
                    forbidden = fix or "该思路不可行, 请更换证明路线"
                return CriticDiagnosis(
                    error_class=error_class, fix_instruction=fix, forbidden_rule=forbidden
                )
            except json.JSONDecodeError:
                pass  # 落入启发式兜底

        # 启发式兜底: 文本中出现"死胡同/禁手"类词汇则视为 dead_end
        if re.search(r"死胡同|禁手|思路撞墙|dead.end|更换路线", raw, re.IGNORECASE):
            return CriticDiagnosis(
                error_class="dead_end",
                fix_instruction="该路线被判定为数学死胡同, 请更换证明策略",
                forbidden_rule=raw.strip()[:500] or "该证明路线不可行",
            )
        return CriticDiagnosis(
            error_class="minor",
            fix_instruction=raw.strip()[:500] or "请就地修正语法或类型错误",
            forbidden_rule=None,
        )

    async def analyze(self, prover_code: str, error_log: str) -> CriticDiagnosis:
        """诊断一次编译失败: 给出机器可读的 error_class 与修复/禁手指令。

        Args:
            prover_code: Prover 本次提交的完整代码。
            error_log: Lean 编译器的错误日志 (来自 LeanValidator 的 message 字段)。

        Returns:
            CriticDiagnosis: 结构化诊断 (minor → 就地微调; dead_end → 掉头 + 禁手入库)。
        """
        user_prompt = (
            "【Prover 提交的代码】\n"
            f"{prover_code}\n"
            "\n"
            "【Lean 编译器错误日志】\n"
            f"{error_log}\n"
            "\n"
            "请按规则输出 JSON 诊断。"
        )
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.max_tokens,
        )
        content = resp.choices[0].message.content
        if not content:
            raise RuntimeError(f"CriticAgent 模型返回空内容 (model={self.model})")
        return self._parse_diagnosis(content.strip())

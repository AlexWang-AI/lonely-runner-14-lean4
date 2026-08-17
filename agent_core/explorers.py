"""
explorers.py — V3 正交分布异步树探索引擎 · 独立并行推进槽

三个 Explorer 同时在线并发运算, 无任何相互通信接口 (零闲聊, 100% 高墙推导):
  Explorer A [Algebraic Mode]     多项式因式分解 / ring-linarith 恒等式 / 矩阵迹操作
  Explorer B [Geometric Mode]     反证法极值构图分解 / 边界点特异化 (退化态分析)
  Explorer C [Combinatorial Mode] 鸽巢原理分割 / 无穷降轨发散分析 / 结构分类化

设计契约:
  - 每个 Explorer 持有独立的正交系统提示词与独立的战损日志 (本路错题本);
  - 黑石碑 (FailureAnalyst) 的 Fingerprint 墙作为最高权重负样本先验注入所有支线;
  - 输出通过 Async 捕获机制返回各自独立子模块, 支线之间零共享状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Sequence

from agent_core.agents import PROVER_MODEL, ProverAgent

# ---------------------------------------------------------------------------
# 公共代码规范尾块 (三路共享的 Lean 输出契约; 不属于"通信", 是编译规范)
# ---------------------------------------------------------------------------

_COMMON_TAIL: Final[str] = (
    "【Lean 输出契约】\n"
    "1. 输出【当前完整证明状态】的代码: 包含此前已通过验证的部分, "
    "尚未攻克的子目标处用 `sorry` 占位 (分步推进, 逐步消灭 sorry)。\n"
    "2. 将完整 Lean 4 证明代码包裹在 `<lean_code>` 和 `</lean_code>` 标签中。\n"
    "3. 不要输出任何 import 语句, 系统会自动注入所需导入; "
    "仅在确实需要特定子模块时才显式写 import。\n"
    "4. 代码必须能独立编译 (除 sorry 外不得引用未定义的名字)。\n"
    "5. 若目标可被现有 tactic 一键闭合 (ring / linarith / norm_num / omega / "
    "aesop / positivity), 立即输出, 不要生成冗长底层证明。"
)

# ---------------------------------------------------------------------------
# 三路正交策略系统提示词
# ---------------------------------------------------------------------------

_SYSTEM_ALGEBRAIC: Final[str] = (
    "你是一台纯代数消元推导引擎 (Algebraic Mode)。\n"
    "\n"
    "【战略】极度侧重: 多项式因式分解、ring/linarith/nlinarith 恒等式操作、"
    "矩阵迹 (trace) 与行列式 (det) 展开、特征多项式降维、SOS 平方和表示、"
    "半正定矩阵的 Schur 补与主子式判据。所有论证必须收敛到可被 ring/linarith "
    "闭合的代数恒等式链。\n"
    "\n"
    "【禁令】禁止需要空间想象的几何论证; 禁止连续性/中间值叙事; 禁止构造性闲聊。\n"
    "\n"
    + _COMMON_TAIL
)

_SYSTEM_GEOMETRIC: Final[str] = (
    "你是一台几何/拓扑反证推导引擎 (Geometric Mode)。\n"
    "\n"
    "【战略】极度侧重: 反证法极值构图分解 (取达到极值的构型)、边界点特异化 "
    "(退化状态分析: 重合点/共线/共面/直径情形逐一击破)、连续性/紧性论证、"
    "凸性与分离超平面、距离与包含关系的不变量。将几何直觉翻译为解析表达式后"
    "落地成 Lean 代码。\n"
    "\n"
    "【禁令】禁止纯代数符号推演空转; 禁止与极值构型无关的泛泛不等式堆叠。\n"
    "\n"
    + _COMMON_TAIL
)

_SYSTEM_COMBINATORIAL: Final[str] = (
    "你是一台组合结构分类推导引擎 (Combinatorial Mode)。\n"
    "\n"
    "【战略】极度侧重: 鸽巢原理分割 (按余数/奇偶/大小分箱)、无穷降轨发散分析 "
    "(最小反例法)、结构分类 (case split 全枚举)、贪心构造与计数论证。优先把"
    "连续命题离散化为有限配置的分类讨论, 再用 omega/linarith 收口。\n"
    "\n"
    "【禁令】禁止连续性中间值式论证; 禁止未穷尽分支的分类结论。\n"
    "\n"
    + _COMMON_TAIL
)

# 工厂: 三路正交槽位 (名称 → 策略标签 → 系统提示词)
_EXPLORER_BLUEPRINTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Explorer-A", "algebraic", _SYSTEM_ALGEBRAIC),
    ("Explorer-B", "geometric", _SYSTEM_GEOMETRIC),
    ("Explorer-C", "combinatorial", _SYSTEM_COMBINATORIAL),
)


# ---------------------------------------------------------------------------
# Explorer 类
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExplorerConfig:
    """一路 Explorer 的完整配置 (名称 / 策略标签 / 系统提示词)。"""

    name: str
    strategy_tag: str
    system_prompt: str


def build_default_explorers() -> list["Explorer"]:
    """构建标准三路正交探索槽 (A/B/C), 每路独立实例零共享状态。"""
    return [Explorer(config=ExplorerConfig(name=n, strategy_tag=t, system_prompt=s))
            for n, t, s in _EXPLORER_BLUEPRINTS]


class Explorer(ProverAgent):
    """独立并行推进槽 — 一路正交策略的异步推导执行体。

    继承 ProverAgent 复用其 LLM 调用基座 (思维链预算 / 空内容重试 / 客户端),
    但持有独立的系统提示词与本路战损日志。实例之间无任何通信接口。
    """

    def __init__(
        self,
        config: ExplorerConfig | None = None,
        name: str = "Explorer-X",
        strategy_tag: str = "custom",
        system_prompt: str = _SYSTEM_ALGEBRAIC,
        model: str = PROVER_MODEL,
        max_tokens: int = 4096,
        thinking_budget: int | None = 1024,
    ) -> None:
        """初始化一路 Explorer。

        Args:
            config: ExplorerConfig (名称/策略标签/系统提示词); 提供时覆盖
                name/strategy_tag/system_prompt。
            model/max_tokens/thinking_budget: 透传 ProverAgent 的推理模型参数。
        """
        if config is not None:
            name, strategy_tag, system_prompt = (
                config.name, config.strategy_tag, config.system_prompt
            )
        super().__init__(model=model, max_tokens=max_tokens,
                         thinking_budget=thinking_budget)
        self.name: str = name
        self.strategy_tag: str = strategy_tag
        self.system_prompt: str = system_prompt
        self.failure_log: list[str] = []   # 本路战损日志 (本路错题本)

    @staticmethod
    def _format_own_failures(failures: Sequence[str]) -> str:
        if not failures:
            return "（本路暂无战损记录 — 放心探索）"
        return "\n".join(f"  - {f}" for f in failures[-5:])

    @staticmethod
    def _format_fingerprints(fingerprints: Sequence[str]) -> str:
        if not fingerprints:
            return "（黑石碑暂无 Fingerprint — 无系统级禁忌）"
        return "\n".join(f"  - ⛔ {f}" for f in fingerprints)

    async def derive(
        self,
        goal: str,
        proven_context: str,
        fingerprints: Sequence[str],
    ) -> str:
        """本路异步推导: 目标 + 已验证上下文 + 本路战损 + 黑石碑 Fingerprint 墙。

        Args:
            goal: 目标定理命题 (Root_Target)。
            proven_context: 当前已通过 Lean 验证的证明代码 (可为空)。
            fingerprints: 黑石碑最高权重禁忌图谱规则列表 (负样本先验墙表)。

        Returns:
            LLM 原始输出文本 (含 <lean_code> 标签)。
        """
        user_prompt = (
            "【目标定理 (Root_Target)】\n"
            f"{goal}\n"
            "\n"
            "【当前已通过验证的证明代码】(可能为空)\n"
            f"{proven_context or '（空 — 请从头开始构造证明）'}\n"
            "\n"
            "【本路战损日志 (Failure Log)】(必须逐条遵守, 绝不重复走不通的老路)\n"
            f"{self._format_own_failures(self.failure_log)}\n"
            "\n"
            "【黑石碑 Fingerprint 墙 (系统级禁忌图谱, 最高权重)】(绝对不可穿越)\n"
            f"{self._format_fingerprints(fingerprints)}\n"
            "\n"
            "请按你的正交策略输出下一步推导 (完整 Lean 4 代码, 未完成处用 sorry 占位)。"
        )
        return await self._complete(self.system_prompt, user_prompt)

    def record_failure(self, summary: str) -> None:
        """记录本路战损 (截断报错摘要入本路错题本)。"""
        self.failure_log.append(summary[:300])

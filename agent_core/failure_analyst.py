"""
failure_analyst.py — 「黑石碑」全局全知视野诊断器 (FailureAnalyst)

被动唤醒条件: 3 位并行 Explorers 在同一回合全部战损废弃。
唯一职责: 阅读 3 条被数学客观规律处死的推理链与 Lean4 报错栈,
          提取共性「系统级推导漏洞 / 不可穿越的空间阻碍矩阵属性」,
          产出最高权重 Rule:「Fingerprint (战损拓扑阻碍禁忌图谱)」,
          交回中央刷新下一批探险子程序的负样本先验墙表。
红线: 不允许帮助修正局部代码 — 只诊断系统级阻碍, 不修单行。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final, Sequence

# 复用查新哨兵的 flash 调用基座 (3 次指数退避重试, 空内容自动加倍预算)
from agent_core.scout_agent import LiteratureScoutAgent

_JSON_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_PROMPT: Final[str] = (
    "你是一台没有情感的高维废卷抽查机 (Black Monolith Failure Analyst)。\n"
    "\n"
    "你将收到 3 条被数学客观规律处死的推理链及其 Lean 4 报错栈 — 它们来自三条"
    "正交策略支线 (代数消元 / 几何反证 / 组合分类), 现已全部战损。\n"
    "\n"
    "【你的唯一任务】: 提取这三条死链的【共性系统级推导漏洞】——即那些"
    "「不可穿越的空间阻碍矩阵属性」(如: 某类目标结构在任意代数消元下都会"
    "触发的类型墙、跨支线重复出现的错误归纳、某数学对象在 Lean 中的不可表达"
    "维度等)。\n"
    "\n"
    "【红线】: 不允许帮助修正局部代码! 不允许给出单行修复建议! "
    "只产出系统级禁忌图谱 Rule。\n"
    "\n"
    "输出格式【严格要求】为 JSON 对象, 不要输出 JSON 以外的任何内容:\n"
    '{"fingerprint": "系统级推导漏洞/空间阻碍禁忌图谱 Rule (一条最高权重规则, '
    '陈述『任何支线都不得再尝试的数学/形式化路线』)", '
    '"severity": 1到5的整数 (5=绝对不可穿越), '
    '"affected_strategies": ["algebraic" 和/或 "geometric" 和/或 "combinatorial"]}'
)


@dataclass(frozen=True)
class ExplorerCasualty:
    """一路 Explorer 的战损档案 (供黑石碑会诊)。"""

    explorer: str                 # 名称 (Explorer-A/B/C)
    strategy_tag: str             # algebraic / geometric / combinatorial
    code: str                     # 战损代码 (已截断)
    error_log: str                # Lean 4 报错栈 / 异常摘要 (已截断)


@dataclass(frozen=True)
class Fingerprint:
    """黑石碑产出的最高权重禁忌图谱 Rule。"""

    rule: str
    severity: int                 # 1~5, 5=绝对不可穿越
    affected_strategies: tuple[str, ...]

    def __str__(self) -> str:
        return f"[severity={self.severity}] {self.rule}"


class FailureAnalyst:
    """黑石碑 — 全局全知视野诊断器 (单极分析, 被动唤醒, 不修局部代码)。"""

    def __init__(self, max_tokens: int = 2048) -> None:
        self.max_tokens = max_tokens
        # 复用 flash 调用基座 (指数退避 + 空内容加倍预算)
        self._scout = LiteratureScoutAgent()

    async def analyze(
        self,
        goal: str,
        casualties: Sequence[ExplorerCasualty],
    ) -> Fingerprint:
        """会诊 3 条战损链, 产出 Fingerprint。

        Args:
            goal: 本回合的 Root_Target。
            casualties: 全部战损的 Explorer 档案 (通常 3 条)。

        Returns:
            Fingerprint: 系统级禁忌图谱 Rule (解析失败时兜底为通用禁律)。
        """
        case_blocks = []
        for i, c in enumerate(casualties, 1):
            case_blocks.append(
                f"── 战损链 {i}: {c.explorer} [{c.strategy_tag}] ──\n"
                f"推理代码:\n{c.code[:1200] or '（无代码 — 调用异常）'}\n"
                f"Lean 4 报错栈:\n{c.error_log[:1200]}"
            )
        user_prompt = (
            "【本回合目标 (Root_Target)】\n"
            f"{goal}\n"
            "\n"
            + "\n\n".join(case_blocks)
            + "\n\n请会诊 3 条战损链, 输出 JSON Fingerprint。"
        )
        raw = await self._scout._complete(
            _SYSTEM_PROMPT, user_prompt, self.max_tokens, "黑石碑会诊"
        )
        match = _JSON_BLOCK_PATTERN.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                rule = str(data.get("fingerprint") or "").strip()
                if rule:
                    try:
                        severity = max(1, min(5, int(data.get("severity", 3))))
                    except (TypeError, ValueError):
                        severity = 3
                    affected_raw = data.get("affected_strategies") or []
                    affected = tuple(str(s).strip() for s in affected_raw
                                     if str(s).strip()) or ("all",)
                    return Fingerprint(rule=rule[:500], severity=severity,
                                       affected_strategies=affected)
            except json.JSONDecodeError:
                pass  # 落入兜底
        return Fingerprint(
            rule="禁止重复本回合三支线共同采用的推导路线: "
                 "三条正交策略在同一数学对象上同时触壁, 该对象在当前形式化粒度下"
                 "不可穿越 — 下回合必须更换攻击目标层级 (换对象/换归纳变量/换表达)",
            severity=3,
            affected_strategies=("all",),
        )

"""
ideation_critic.py — 灵感生成评分器 (IdeationCritic)

SymPy 3 秒极速代数验真闸口 (防翻车):
  - 受限解析 SymPy_Formula (白名单函数, 绝不执行任意代码);
  - 随机参数压力测试 (200 样本 × 3 秒预算);
  - 快速证伪剪枝: 平凡反例/代数矛盾 → REJECT (零 Token 烧进 Lean);
  - 100% 成立 → FEASIBLE_INVARIANT 标签, 提交下游执行集群。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Final

import sympy as sp
from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication_application,
                                        parse_expr, standard_transformations)

from agent_core.ideation_mutator import HypothesisPair

# 白名单: 仅符号 + 有限函数集 (解析层沙箱)
_SAFE_FUNCS: Final[dict] = {
    "sqrt": sp.sqrt, "abs": sp.Abs, "sin": sp.sin, "cos": sp.cos,
    "exp": sp.exp, "log": sp.log, "pi": sp.pi, "E": sp.E,
    "floor": sp.floor, "ceiling": sp.ceiling, "min": sp.Min, "max": sp.Max,
    "Rational": sp.Rational,
}

_COMPARE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(.*?)\s*(>=|<=|==|>|<)\s*(.*)$")
_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

VERDICT_FEASIBLE: Final[str] = "FEASIBLE_INVARIANT"
VERDICT_REJECT: Final[str] = "REJECT"


@dataclass(frozen=True)
class IdeationVerdict:
    verdict: str              # FEASIBLE_INVARIANT / REJECT
    reason: str
    samples_tested: int
    elapsed: float
    lhs: str
    rhs: str
    op: str


class IdeationCritic:
    """SymPy 3 秒极速验真闸口 — 快速证伪剪枝 + FEASIBLE_INVARIANT 放行。"""

    def __init__(self, samples: int = 200, time_budget: float = 3.0):
        self.samples = samples
        self.time_budget = time_budget

    def _parse_side(self, text: str) -> sp.Expr:
        """受限解析: 白名单函数 + 隐式乘法; 拒绝任何越权符号。"""
        for sym in _SYMBOL_PATTERN.findall(text):
            if sym not in _SAFE_FUNCS and len(sym) > 1:
                raise ValueError(f"越权符号: {sym}")
        local_dict = dict(_SAFE_FUNCS)
        return parse_expr(
            text.strip(),
            transformations=standard_transformations + (implicit_multiplication_application, convert_xor),
            local_dict=local_dict,
            evaluate=False,
        )

    def gate(self, pair: HypothesisPair) -> IdeationVerdict:
        """3 秒压力测试闸口。"""
        t0 = time.time()
        m = _COMPARE_PATTERN.match(pair.sympy_formula.strip())
        if not m:
            return IdeationVerdict(VERDICT_REJECT, "公式非单一比较式", 0,
                                   time.time() - t0, "", "", "")
        lhs_s, op, rhs_s = m.group(1).strip(), m.group(2), m.group(3).strip()
        try:
            lhs = self._parse_side(lhs_s)
            rhs = self._parse_side(rhs_s)
        except Exception as exc:  # noqa: BLE001 — 解析失败即拒
            return IdeationVerdict(VERDICT_REJECT, f"解析失败: {type(exc).__name__}",
                                   0, time.time() - t0, lhs_s, rhs_s, op)
        diff = sp.simplify(lhs - rhs)
        free = sorted(diff.free_symbols, key=str)
        if not free:
            # 无自由符号: 直接符号判定
            try:
                val = float(diff)
                holds = (op in (">=", ">") and val >= 0) or \
                        (op in ("<=", "<") and val <= 0) or \
                        (op == "==" and abs(val) < 1e-12)
            except Exception:
                holds = False
            return IdeationVerdict(
                VERDICT_FEASIBLE if holds else VERDICT_REJECT,
                f"符号判定: diff={val:.6g}", 1, time.time() - t0, lhs_s, rhs_s, op)
        # 随机压力测试 (时间预算内)
        rng = __import__("random").Random(0)
        tested = 0
        for _ in range(self.samples):
            if time.time() - t0 > self.time_budget:
                break
            subs = {s: rng.uniform(-3, 3) for s in free}
            try:
                val = complex(diff.subs(subs)).real
            except Exception:  # noqa: BLE001
                return IdeationVerdict(VERDICT_REJECT, "数值求值异常",
                                       tested, time.time() - t0, lhs_s, rhs_s, op)
            tested += 1
            if op in (">=", ">") and val < -1e-9:
                return IdeationVerdict(VERDICT_REJECT,
                                       f"反例: {subs} → diff={val:.6g}",
                                       tested, time.time() - t0, lhs_s, rhs_s, op)
            if op in ("<=", "<") and val > 1e-9:
                return IdeationVerdict(VERDICT_REJECT,
                                       f"反例: {subs} → diff={val:.6g}",
                                       tested, time.time() - t0, lhs_s, rhs_s, op)
            if op == "==" and abs(val) > 1e-9:
                return IdeationVerdict(VERDICT_REJECT,
                                       f"反例: {subs} → diff={val:.6g}",
                                       tested, time.time() - t0, lhs_s, rhs_s, op)
        return IdeationVerdict(VERDICT_FEASIBLE,
                               f"{tested} 样本随机压力测试通过",
                               tested, time.time() - t0, lhs_s, rhs_s, op)

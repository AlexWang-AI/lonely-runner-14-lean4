"""
ideation_mutator.py — 跨界灵感突变发生器 (CrossDomainMutator)

自主灵感突变与跨界涌现协议 (AIM-Protocol) 核心组件:
  现有路径战损时, 从 20+ 领域灵感池自由抽取交叉学科工具,
  生成「突变假说对 (Hypothesis Pair)」:
    - Mathematical_Ansatz   跨界核心思想与连续/离散数学映射
    - SymPy_Formula         对应的代数关系式/势能函数/特征值不等式
    - Lean4_Goal_Blueprint  形式化引理声明雏形
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Final

from agent_core.scout_agent import LiteratureScoutAgent

_JSON_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)

# 20+ 领域灵感池 (跨界工具箱)
DOMAIN_POOL: Final[tuple[str, ...]] = (
    "统计物理自旋玻璃模型", "辛几何动力流", "代数拓扑示性类",
    "量子信息纠缠熵", "拟共形映射", "李代数根系", "遍历论相空间测度",
    "离散调和分析自相关极值", "多项式平方和 SOS 松弛", "Farkas 对偶锥",
    "中国剩余定理模塔", "多项式方法零点限制", "加性组合学 Plünnecke",
    "傅里叶限制估计", "随机矩阵理论", "测度集中现象", "渗流临界理论",
    "双曲几何测地流", "编码理论对偶码", "拟阵理论独立集", "热带几何",
)

_SYSTEM_PROMPT: Final[str] = (
    "你是自主灵感突变发生器 (CrossDomain Mutator) — 全学科交叉联想引擎。\n"
    "\n"
    "任务: 面对一个撞墙的数学攻坚目标, 从指定的两个交叉领域提取全新数学工具, "
    "构造一个【桥梁子引理 (Bridging Ansatz)】。\n"
    "\n"
    "输出格式【严格要求】为 JSON 对象, 不要输出 JSON 以外的任何内容:\n"
    '{"mathematical_ansatz": "跨界核心思想与数学映射 (2-3 句)", '
    '"sympy_formula": "单一代数关系式, 形如 \'expr1 >= expr2\' 或 \'expr1 == expr2\', '
    '自由符号用小写字母 (如 a, b, x), 仅允许 + - * / ** sqrt abs sin cos 与整数/有理数", '
    '"lean4_goal_blueprint": "形式化引理声明雏形 (Lean 4 伪代码, 通用量词级, 不含具体数值代入)"}\n'
    "\n"
    "【铁律】: ① 严禁具体速度假设与具体维度代入; ② sympy_formula 必须是单一比较式; "
    "③ 假说必须与目标的结构特征 (周期轨道/覆盖/测度) 相关。"
)


@dataclass(frozen=True)
class HypothesisPair:
    """突变假说对 — 跨界灵感的结构化产物。"""

    mathematical_ansatz: str
    sympy_formula: str
    lean4_goal_blueprint: str
    domains: tuple[str, str]


class CrossDomainMutator:
    """跨界灵感突变发生器 — 领域池随机交叉 + flash 联想 + 结构化假说对。"""

    def __init__(self, seed: int = 0):
        self._scout = LiteratureScoutAgent()   # 复用 flash 重试基座
        self._rng = random.Random(seed)
        self._used_domain_pairs: set[tuple[str, str]] = set()

    def _sample_domains(self) -> tuple[str, str]:
        """随机抽取未用过的领域对 (池耗尽则重置)。"""
        if len(self._used_domain_pairs) >= len(DOMAIN_POOL) * (len(DOMAIN_POOL) - 1) // 2:
            self._used_domain_pairs.clear()
        while True:
            pair = tuple(sorted(self._rng.sample(DOMAIN_POOL, 2)))
            if pair not in self._used_domain_pairs:
                self._used_domain_pairs.add(pair)
                return pair  # type: ignore[return-value]

    async def generate(
        self,
        goal: str,
        fingerprints: list[str],
        failure_summary: str = "",
    ) -> HypothesisPair:
        """生成一个突变假说对 (LLM 失败时确定性兜底)。"""
        d1, d2 = self._sample_domains()
        user_prompt = (
            "【攻坚目标】\n"
            f"{goal[:800]}\n"
            "\n"
            "【黑石碑 Fingerprint 墙 (历史死因, 严禁重复)】\n"
            + "\n".join(f"  - {f}" for f in fingerprints[-8:])
            + "\n"
            f"【本轮失败摘要】{failure_summary or '（无）'}\n"
            "\n"
            f"【指定交叉领域】① {d1} ② {d2}\n"
            "\n"
            "请构造桥梁子引理, 严格输出 JSON。"
        )
        try:
            raw = await self._scout._complete(
                _SYSTEM_PROMPT, user_prompt, 1536, "跨界灵感突变"
            )
        except RuntimeError as exc:
            # API 抖动装甲: 突变失败不得击穿主循环 → 确定性兜底假说
            return HypothesisPair(
                mathematical_ansatz=f"兜底 (API 抖动 {str(exc)[:60]}): 周期函数平凡正性核",
                sympy_formula="(1 - abs(x)) ** 2 >= 0",
                lean4_goal_blueprint="example : ∀ x : ℝ, (1 - |x|) ^ 2 ≥ 0",
                domains=(d1, d2),
            )
        match = _JSON_BLOCK_PATTERN.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                ansatz = str(data.get("mathematical_ansatz") or "").strip()
                formula = str(data.get("sympy_formula") or "").strip()
                blueprint = str(data.get("lean4_goal_blueprint") or "").strip()
                if ansatz and formula:
                    return HypothesisPair(ansatz, formula, blueprint, (d1, d2))
            except json.JSONDecodeError:
                pass
        # 确定性兜底: 初等且必真的桥梁引理 (供流程不中断)
        return HypothesisPair(
            mathematical_ansatz="兜底: 周期函数的平均孤独立度下界 (积分中值平凡界)",
            sympy_formula="(1 - abs(x)) ** 2 >= 0",
            lean4_goal_blueprint="example : ∀ x : ℝ, (1 - |x|) ^ 2 ≥ 0",
            domains=(d1, d2),
        )

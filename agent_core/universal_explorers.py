"""
universal_explorers.py — V5 跨学科四路正交全称量词引擎 (Universal Invariant Engine)

四路通用探索者, 各搭载全新跨界心智模型, 目标一致:
  构造【与具体速度无关的全局不变量】, 攻克 LRC 任意 k 通法证明。
  - Explorer_Harmonic   [调和分析·波赫纳正定核流]: 光滑周期正定核 K_k,
      零频主模式 > 速度差交调高频总和 → 积分均值 > 0 → 孤独时刻存在;
  - Explorer_Entropy    [信息论·KL 亏损流]: 圆周测度流联合分布与密铺测度的
      刚性信息亏损 ≥ δ(k) > 0 → 强制存在测度 ≥ 1/(k+1) 的未覆盖空洞;
  - Explorer_Spectral   [谱图·拉普拉斯切格流]: 速度差矩阵 → 循环图代数连通度
      λ₂, 切格等周 → 高维环面轨迹测地线不可完全截断;
  - Explorer_RealAlgebra[实闭域·SOS 流]: Stengle 弱零点定理构建障碍多项式,
      「不存在孤独时刻」方程组在实闭域无实数解。

铁律 (黑石碑 V5 强制): 任何引理若含【具体速度假设】(如 v 0 = 1, 具体数值元组)
一律视为退化 — 通法证明必须只依赖 k 与 h_inj 的普遍结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from agent_core.agents import PROVER_MODEL, ProverAgent

# 全称目标定理 (与 universal_loop 共享的 Root_Target)
UNIVERSAL_GOAL: Final[str] = (
    "def dist_torus (x : ℝ) : ℝ := |x - round x|"
    "\n\n"
    "theorem lonely_runner_conjecture_universal (k : ℕ) (hk : k ≥ 1) "
    "(v : Fin k → ℕ+) (h_inj : Function.Injective v) : "
    "∃ (t : ℝ), ∀ (i : Fin k), dist_torus ((v i : ℝ) * t) ≥ (1 : ℝ) / ((k : ℝ) + 1)"
)

_COMMON_TAIL: Final[str] = (
    "\n\n【通用性铁律 (V5, 最高权重)】"
    "\n1. 输出【当前完整证明状态】的代码: 尚未攻克的子目标用 `sorry` 占位。"
    "\n2. 完整 Lean 4 代码包裹在 `<lean_code>` 与 `</lean_code>` 标签中。"
    "\n3. 【绝对禁止】引入任何具体速度假设 (如 `v 0 = 1`、具体数值元组、"
    "具体 k 值代入) — 通法引理必须只依赖 k、h_inj 与普遍结构; 违者即退化。"
    "\n4. 不要输出 import 语句, 系统自动注入导入; 仅在确需特定子模块时显式写 import。"
    "\n5. 代码必须独立编译 (除 sorry 外不得引用未定义名字)。"
)

_SYSTEM_HARMONIC: Final[str] = (
    "你是一台调和分析推导引擎 (Harmonic Invariant Mode)。\n"
    "\n"
    "【战略】构造光滑周期正定核函数 K_k : ℝ/ℤ → ℝ (波赫纳定理保证其傅里叶系数"
    "非负), 使零频主模式系数严格大于所有速度差交调高频系数的总和:\n"
    "  K̂_k(0) > Σ_{i≠j} |K̂_k(v_i − v_j)|\n"
    "由此 (1/k)Σᵢ K_k(vᵢ t) 的积分均值严格大于 0, 经积分中值定理导出任意速度谱"
    "下必存在孤独时刻 t*。核心工作是: 显式构造 K_k 并用初等傅里叶系数界证明"
    "不等式链 — 全程不得引入具体速度值。\n"
    + _COMMON_TAIL
)

_SYSTEM_ENTROPY: Final[str] = (
    "你是一台信息论推导引擎 (Entropy Deficit Mode)。\n"
    "\n"
    "【战略】将 k 维连续轨迹在圆周上的投影视为测度流 μ_t; 设联合测度与完全密铺"
    "测度之间的 KL 散度存在刚性下界 D_KL ≥ δ(k) > 0 (由条件熵非负性与互信息"
    "次模性导出)。信息亏损迫使圆周上必然存在测度 ≥ 1/(k+1) 的未覆盖空洞 —"
    "该空洞内任意时刻即孤独时刻。核心: 建立 δ(k) 的显式下界函数并形式化"
    "熵不等式链, 只依赖 k。\n"
    + _COMMON_TAIL
)

_SYSTEM_SPECTRAL: Final[str] = (
    "你是一台谱图理论推导引擎 (Spectral Cheeger Mode)。\n"
    "\n"
    "【战略】将速度差结构映射为循环图 G_k 的邻接/拉普拉斯矩阵; 用代数连通度"
    "λ₂ (Fiedler 值) 与切格等周不等式证明: 高维环面轨迹的测地线流不能被有限"
    "个超平面完全截断 — 截断集测度存在正下界 ⟺ 存在未覆盖区域。核心: 把"
    "连续覆盖问题降维为 λ₂ > 0 的谱判定与等周常数估计, 全程与具体速度无关。\n"
    + _COMMON_TAIL
)

_SYSTEM_REALALGEBRA: Final[str] = (
    "你是一台实代数几何推导引擎 (Positivstellensatz Mode)。\n"
    "\n"
    "【战略】将「不存在孤独时刻」写为紧致实射影空间上的代数方程组/不等式组;"
    "利用 Stengle 弱零点定理 (Positivstellensatz) 构造障碍多项式恒等式:\n"
    "  −1 = σ₀ + Σ σᵢ pᵢ + Σ τⱼ qⱼ\n"
    "(σ 为平方和, pᵢ 为等号约束, qⱼ 为不等式约束)。该恒等式在实闭域上无解"
    "⟹ 原方程组无实数解 ⟹ 孤独时刻必然存在。核心: 构造与 k 相关的障碍多项式"
    "族并证明其系数恒等式, 严禁具体速度代入。\n"
    + _COMMON_TAIL
)


@dataclass(frozen=True)
class UniversalExplorerConfig:
    name: str
    strategy_tag: str
    system_prompt: str


def build_universal_explorers() -> list["UniversalExplorer"]:
    """构建标准四路通用探索槽 (Harmonic/Entropy/Spectral/RealAlgebra)。"""
    return [
        UniversalExplorer(UniversalExplorerConfig("Explorer-Harmonic", "harmonic",
                                                  _SYSTEM_HARMONIC)),
        UniversalExplorer(UniversalExplorerConfig("Explorer-Entropy", "entropy",
                                                  _SYSTEM_ENTROPY)),
        UniversalExplorer(UniversalExplorerConfig("Explorer-Spectral", "spectral",
                                                  _SYSTEM_SPECTRAL)),
        UniversalExplorer(UniversalExplorerConfig("Explorer-RealAlgebra", "realalgebra",
                                                  _SYSTEM_REALALGEBRA)),
    ]


class UniversalExplorer(ProverAgent):
    """V5 通用探索者 — 一路全称不变量策略的异步推导执行体。

    继承 ProverAgent 复用 LLM 调用基座 (thinking-disabled 修复已内建),
    持有独立系统提示词与本路战损日志; 实例间零通信。
    """

    def __init__(
        self,
        config: UniversalExplorerConfig,
        model: str = PROVER_MODEL,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(model=model, max_tokens=max_tokens,
                         thinking_budget=None)
        self.name: str = config.name
        self.strategy_tag: str = config.strategy_tag
        self.system_prompt: str = config.system_prompt
        self.failure_log: list[str] = []

    async def derive(
        self,
        goal: str,
        proven_context: str,
        fingerprints: list[str],
    ) -> str:
        """本路异步推导: 全称目标 + 已验证上下文 + 本路战损 + 黑石碑 Fingerprint 墙。"""
        parts = [
            "【全称目标定理 (Root_Target, 任意 k 通法)】",
            goal,
            "",
            "【当前已通过验证的证明代码】(可能为空)",
            proven_context or "（空 — 请从全局不变量构造开始）",
            "",
            "【本路战损日志】(必须逐条遵守)",
            *([f"  - {f}" for f in self.failure_log[-5:]]
              or ["  （暂无战损记录）"]),
            "",
            "【黑石碑 Fingerprint 墙 (系统级禁忌, 最高权重)】(绝对不可穿越)",
            *([f"  - ⛔ {f}" for f in fingerprints]
              or ["  （暂无 Fingerprint）"]),
            "",
            "请按你的不变量策略输出下一步推导 (完整 Lean 4 代码, 未完成处用 sorry 占位)。",
        ]
        user_prompt = "\n".join(parts)
        return await self._complete(self.system_prompt, user_prompt)

    def record_failure(self, summary: str) -> None:
        self.failure_log.append(summary[:300])

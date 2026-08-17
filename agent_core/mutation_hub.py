"""
mutation_hub.py — 自主假说突变中枢 (V5.5 黑石碑自进化孵化器)

职责:
  1. 死因基因解剖: 从历史指纹中提取代数断点类别;
  2. 跨界工具箱动态注入: 每轮全灭后抽取新领域对, 借 CrossDomainMutator
     捏造【桥梁子引理 (Bridging Ansatz)】;
  3. 生成 research/ansatz_quick_check.py: 对突变引理做独立快速验真脚本
     (确定性模板, 不执行 LLM 代码)。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

# 死因基因字典: 指纹关键词 → 代数断点类别
_DEATH_GENES: Final[dict[str, str]] = {
    "L2": "核函数 L2 范数鸿沟",
    "测度": "测度论连续性转换壁垒",
    "模塔": "复合模数不透明原子墙",
    "退化": "具体速度假设退化",
    "omega": "Presburger 模推理超时",
    "unknown": "mathlib API 缺口",
    "类型": "类型墙/实例缺失",
    "sorry": "骨架未闭合",
}


@dataclass
class HubState:
    """突变中枢状态 (黑石板持久化)。"""

    death_genes: list[str] = field(default_factory=list)
    ansatz_history: list[dict] = field(default_factory=list)
    mutations: int = 0
    last_ansatz: dict | None = None

    def to_dict(self) -> dict:
        return {
            "death_genes": self.death_genes,
            "ansatz_history": self.ansatz_history[-20:],
            "mutations": self.mutations,
            "last_ansatz": self.last_ansatz,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HubState":
        st = cls()
        st.death_genes = d.get("death_genes", [])
        st.ansatz_history = d.get("ansatz_history", [])
        st.mutations = d.get("mutations", 0)
        st.last_ansatz = d.get("last_ansatz")
        return st


class MutationHub:
    """自主假说突变中枢 — 指纹解剖 + 跨界注入 + 快速验真脚本生成。"""

    def __init__(self):
        self._board = _PROJECT_ROOT / "research" / "mutation_hub_state.json"
        self.state = self._load()

    def _load(self) -> HubState:
        if self._board.exists():
            try:
                return HubState.from_dict(
                    json.loads(self._board.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        return HubState()

    def save(self) -> None:
        self._board.parent.mkdir(parents=True, exist_ok=True)
        self._board.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=1),
            encoding="utf-8")

    def ingest_fingerprints(self, fingerprints: list[str]) -> list[str]:
        """死因基因解剖: 指纹关键词 → 断点类别 (新基因才入库)。"""
        new_genes = []
        for fp in fingerprints:
            for key, gene in _DEATH_GENES.items():
                if key in fp and gene not in self.state.death_genes:
                    self.state.death_genes.append(gene)
                    new_genes.append(gene)
        if new_genes:
            self.save()
        return new_genes

    def record_ansatz(self, pair, verdict: str, critic_reason: str) -> dict:
        """记录突变假说及其验真裁决。"""
        entry = {
            "ts": time.time(),
            "domains": list(pair.domains),
            "ansatz": pair.mathematical_ansatz[:200],
            "formula": pair.sympy_formula,
            "blueprint": pair.lean4_goal_blueprint[:200],
            "verdict": verdict,
            "critic_reason": critic_reason[:200],
        }
        self.state.ansatz_history.append(entry)
        self.state.last_ansatz = entry
        self.state.mutations += 1
        self.save()
        return entry

    def generate_quick_check(self, formula: str) -> Path:
        """生成 research/ansatz_quick_check.py (确定性验真模板)。"""
        path = _PROJECT_ROOT / "research" / "ansatz_quick_check.py"
        template = (
            '"""ansatz_quick_check.py — 突变引理极速验真 (自动生成)"""\n'
            "import random, sys\n"
            "from pathlib import Path\n"
            "sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
            "_R = Path(__file__).resolve().parent.parent\n"
            "if str(_R) not in sys.path:\n"
            "    sys.path.insert(0, str(_R))\n"
            "from agent_core.ideation_critic import IdeationCritic\n"
            "from agent_core.ideation_mutator import HypothesisPair\n"
            f"PAIR = HypothesisPair('auto', {formula!r}, 'auto', ('auto', 'auto'))\n"
            "V = IdeationCritic().gate(PAIR)\n"
            "print(V.verdict, '|', V.reason)\n"
            "sys.exit(0 if V.verdict == 'FEASIBLE_INVARIANT' else 1)\n"
        )
        path.write_text(template, encoding="utf-8")
        return path

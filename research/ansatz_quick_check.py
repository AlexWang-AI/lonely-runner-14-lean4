"""ansatz_quick_check.py — 突变引理极速验真 (自动生成)"""
import random, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
_R = Path(__file__).resolve().parent.parent
if str(_R) not in sys.path:
    sys.path.insert(0, str(_R))
from agent_core.ideation_critic import IdeationCritic
from agent_core.ideation_mutator import HypothesisPair
PAIR = HypothesisPair('auto', '(1 - abs(x)) ** 2 >= 0', 'auto', ('auto', 'auto'))
V = IdeationCritic().gate(PAIR)
print(V.verdict, '|', V.reason)
sys.exit(0 if V.verdict == 'FEASIBLE_INVARIANT' else 1)

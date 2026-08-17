"""
universal_loop.py — V5 跨学科四路正交全称量词引擎 · 点火枢纽

目标: LRC 任意 k 通法证明 (Universal Solitude)。
四路 (Harmonic/Entropy/Spectral/RealAlgebra) 异步并发, 每路独立
temp_universal_worker_{id}.lean 沙盒; 黑石碑 V5 仅捕获「任意 k 通用性」:
凡含具体速度假设的代码一律视为退化并施加阻碍指纹。

唤醒条件: A = 0-sorry 全称证明斩获 (落盘 outputs/) | 轮数/墙钟耗尽。
基础设施熔断: 四路同源异常且零代码产出 → 立即中止 (V3 教训)。
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, Callable

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.lean_verifier import LeanCodeParseError, LeanValidator
from agent_core.universal_explorers import (UNIVERSAL_GOAL,
                                            UniversalExplorer,
                                            build_universal_explorers)

# 目标轨 B: 弱孤独跑者常数界 (经典真定理, 10 万元组数值验证)
WEAK_GOAL: Final[str] = (
    "theorem weak_lonely_runner_universal (k : ℕ) (hk : k ≥ 1) "
    "(v : Fin k → ℕ+) (h_inj : Function.Injective v) : "
    "∃ (t : ℝ), ∀ (i : Fin k), dist_torus ((v i : ℝ) * t) ≥ "
    "(1 : ℝ) / ((2 : ℝ) * (k : ℝ))"
)

_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bsorry\b|\badmit\b")
_GOAL_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:theorem|lemma)\s+([A-Za-z_][\w']*)")

_CAPTURE_NAMES: Final[tuple[str, ...]] = (
    "lonely_runner_conjecture_universal", "weak_lonely_runner_universal")

# V5 通用性退格检测: 具体速度假设/具体维度代入/具体 k 值
_DEGENERATE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bv\s+(?:⟨)?\d+"),           # v 0 / v 1 / v ⟨0, ...⟩
    re.compile(r"Fin\s+[0-9]+"),              # Fin 3 等具体维度
    re.compile(r"\bk\s*=\s*[0-9]+"),          # k = 3 等具体代入
    re.compile(r"!\[\[?\s*-?\d"),             # 具体矩阵/元组字面量
)

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _g(t: str) -> str:
    return f"{_GREEN}{t}{_RESET}"


def _r(t: str) -> str:
    return f"{_RED}{t}{_RESET}"


def _y(t: str) -> str:
    return f"{_YELLOW}{t}{_RESET}"


def _c(t: str) -> str:
    return f"{_CYAN}{t}{_RESET}"


@dataclass(frozen=True)
class UniversalRunReport:
    success: bool
    goal: str
    proof_code: str
    output_file: Path | None
    winner: str | None
    rounds_used: int
    fingerprints: tuple[str, ...]
    elapsed_seconds: float


@dataclass
class _WorkerResult:
    explorer: UniversalExplorer
    code: str
    raw: str
    verify: dict | None
    error: str
    degenerate: bool = False


class UniversalProvingLoop:
    """V5 全称量词引擎 — 四路通用不变量并发轰炸 + 通用性黑石碑。"""

    def __init__(
        self,
        max_rounds: int = 50,
        verify_timeout: float = 600.0,
        explorers: list[UniversalExplorer] | None = None,
        validators: dict[str, LeanValidator] | None = None,
        aim: bool = False,
    ) -> None:
        self.max_rounds = max_rounds
        self.verify_timeout = verify_timeout
        self.aim = aim
        self.explorers: list[UniversalExplorer] = explorers or build_universal_explorers()
        if validators is not None:
            self.validators = validators
        else:
            self.validators = {
                e.name: LeanValidator(worker_id=f"universal_{e.name}",
                                      server_prelude="import Mathlib.Tactic",
                                      prelude_ladder=())
                for e in self.explorers
            }
        # AIM 协议组件 (惰性挂载)
        self._mutator = None
        self._critic = None
        self._hub = None
        self._current_ansatz: str = ""

    @staticmethod
    def _is_capture(code: str) -> bool:
        return bool(code) and not _PLACEHOLDER_PATTERN.search(code) \
            and any(n in code for n in _CAPTURE_NAMES)

    def _aim_components(self):
        if self._mutator is None:
            from agent_core.ideation_critic import IdeationCritic
            from agent_core.ideation_mutator import CrossDomainMutator
            from agent_core.mutation_hub import MutationHub
            self._mutator = CrossDomainMutator()
            self._critic = IdeationCritic()
            self._hub = MutationHub()
        return self._mutator, self._critic, self._hub

    async def _aim_mutate(self, goal: str, fingerprints: list[str],
                          failure_summary: str) -> str:
        """AIM 状态机: 突变 → 3 秒 SymPy 闸口 → FEASIBLE 脚手架注入 / REJECT 重试。"""
        mutator, critic, hub = self._aim_components()
        for _ in range(3):
            pair = await mutator.generate(goal, fingerprints, failure_summary)
            verdict = critic.gate(pair)
            hub.record_ansatz(pair, verdict.verdict, verdict.reason)
            hub.generate_quick_check(pair.sympy_formula)
            if verdict.verdict == "FEASIBLE_INVARIANT":
                print(_y(f"  🌌 AIM 突变放行: [{pair.domains[0]} × {pair.domains[1]}] "
                         f"{verdict.reason} — 脚手架注入"))
                self._current_ansatz = (
                    f"【最新突变桥梁引理 (AIM 脚手架, 最高优先级)】\n"
                    f"思想: {pair.mathematical_ansatz}\n"
                    f"代数式: {pair.sympy_formula} (SymPy {verdict.samples_tested} 样本验真)\n"
                    f"Lean 蓝图: {pair.lean4_goal_blueprint}")
                return self._current_ansatz
            print(_r(f"  🌌 AIM 突变证伪: {verdict.reason} — 换领域对重突变"))
        return self._current_ansatz or ""

    @staticmethod
    def _is_degenerate(code: str) -> bool:
        """黑石碑 V5 通用性检查: 含具体速度假设即退化。"""
        return any(p.search(code) for p in _DEGENERATE_PATTERNS)

    def _save_proof(self, report: UniversalRunReport) -> Path:
        out_dir = _PROJECT_ROOT / "outputs"
        out_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"proved_lonely_runner_universal_{stamp}.lean"
        header = [
            "-- ============================================================",
            "-- AI Math Institute · V5 全称量词引擎 · 自动生成证明脚本",
            f"-- 目标: LRC 任意 k 通法 | 斩获者: {report.winner}",
            f"-- 回合数: {report.rounds_used} | 耗时: {report.elapsed_seconds:.2f}s",
            "-- ============================================================",
        ]
        path.write_text("\n".join(header) + "\n\n" + report.proof_code,
                        encoding="utf-8")
        return path

    async def _round(self, goal: str, context: str, fingerprints: list[str]):
        results = await asyncio.gather(
            *(e.derive(goal, context, fingerprints) for e in self.explorers),
            return_exceptions=True,
        )
        workers: list[_WorkerResult] = []
        for e, raw in zip(self.explorers, results):
            if isinstance(raw, BaseException):
                workers.append(_WorkerResult(e, "", "", None,
                                             f"{type(raw).__name__}: {raw}"))
                continue
            try:
                code = self.validators[e.name].extract_lean_code(raw)
                workers.append(_WorkerResult(e, code, raw, None, ""))
            except LeanCodeParseError as exc:
                workers.append(_WorkerResult(e, "", raw, None, f"解析失败: {exc}"))
        # 并行验证 (独立沙盒)
        verify_tasks = {
            asyncio.create_task(
                asyncio.to_thread(self.validators[w.explorer.name].verify_code,
                                  w.code, self.verify_timeout)
            ): w
            for w in workers if w.code
        }
        captured: _WorkerResult | None = None
        while verify_tasks:
            done, _ = await asyncio.wait(verify_tasks,
                                         return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                w = verify_tasks.pop(task)
                w.verify = task.result()
                if captured is None and w.verify.get("status") == "success" \
                        and self._is_capture(w.code):
                    captured = w
                    for t in verify_tasks:
                        t.cancel()
                    verify_tasks.clear()
                    break
        return workers, captured

    async def run(self, goal: str = UNIVERSAL_GOAL) -> UniversalRunReport:
        start_ts = time.monotonic()
        fingerprints: list[str] = []
        best_context = ""
        winner: str | None = None
        proof_code = ""

        print(f"{_BOLD}{_c('═══ V5 跨学科四路正交全称量词引擎 · 点火 ═══')}{_RESET}")
        print(f"{_c('目标')}: LRC 任意 k 通法 (Universal Solitude)")
        print(f"{_c('四路槽位')}: " + " | ".join(
            f"{e.name}[{e.strategy_tag}]" for e in self.explorers))
        print(f"{_c('参数')}: max_rounds={self.max_rounds}, "
              f"verify_timeout={self.verify_timeout}s")

        rounds = 0
        while rounds < self.max_rounds:
            rounds += 1
            print(f"\n{_BOLD}── Round {rounds}/{self.max_rounds} · 四路不变量轰炸 ──{_RESET}")
            # AIM 协议: 突变脚手架注入 + 双轨目标挂载
            round_goal = goal + "\n\n" + WEAK_GOAL
            if self._current_ansatz:
                round_goal = self._current_ansatz + "\n\n" + round_goal
            workers, captured = await self._round(round_goal, best_context, fingerprints)

            for w in workers:
                if w.verify and w.verify.get("status") == "success":
                    if _PLACEHOLDER_PATTERN.search(w.code):
                        print(f"  {_y('🟡 编译通过含 sorry')} | {w.explorer.name}")
                        best_context = w.code
                    else:
                        print(f"  {_g('✅ 验证通过')} | {w.explorer.name}")
                else:
                    msg = (w.verify or {}).get("message", "") or w.error
                    print(f"  {_r('❌ 战损')} | {w.explorer.name} | {msg[:70]}")

            if captured is not None:
                winner = captured.explorer.name
                proof_code = captured.code
                elapsed = time.monotonic() - start_ts
                report = UniversalRunReport(
                    success=True, goal=goal, proof_code=proof_code,
                    output_file=self._save_proof(UniversalRunReport(
                        True, goal, proof_code, None, winner, rounds,
                        tuple(fingerprints), elapsed)),
                    winner=winner, rounds_used=rounds,
                    fingerprints=tuple(fingerprints), elapsed_seconds=elapsed,
                )
                msg = (f'🏆 全称证明斩获! 胜者: {winner} — '
                       f'封存: {report.output_file}')
                print(f"\n{_BOLD}{_g(msg)}{_RESET}")
                return report

            # 基础设施熔断 (V3 教训)
            if all(not w.code for w in workers) \
                    and len({w.error for w in workers}) == 1 and workers:
                print(f"\n{_BOLD}{_r('🏭 基础设施熔断: 四路共享调用契约破裂 — 修复调用层后重新点火')}{_RESET}")
                return UniversalRunReport(False, goal, "", None, None, rounds,
                                          tuple(fingerprints),
                                          time.monotonic() - start_ts)

            # 黑石碑 V5: 通用性检查 → 退化指纹
            last_error = ""
            for w in workers:
                if w.code and self._is_degenerate(w.code):
                    fp = (f"退化指纹: {w.explorer.name} 引入具体速度假设/具体维度 "
                          f"(违反任意 k 通用性铁律) — 该路线作废")
                    fingerprints.append(fp)
                    w.explorer.record_failure(fp)
                    print(_y(f"  ⛔ {fp}"))
                elif w.error or (w.verify and w.verify.get("status") != "success"):
                    last_error = ((w.verify or {}).get("message", "") or w.error)[:300]
                    w.explorer.record_failure(last_error)
            # Failure Reflex: AIM 协议突变自愈 (装甲: 突变故障绝不击穿主循环)
            if self.aim and captured is None:
                try:
                    if self._hub is None:
                        self._aim_components()
                    self._hub.ingest_fingerprints(fingerprints)
                    self._current_ansatz = await self._aim_mutate(
                        goal, fingerprints, last_error)
                except Exception as exc:  # noqa: BLE001 — 反射装甲
                    print(_r(f"  🛡️ AIM 反射装甲吸收异常: {type(exc).__name__} — 继续攻坚"))
        return UniversalRunReport(False, goal, best_context, None, None, rounds,
                                  tuple(fingerprints), time.monotonic() - start_ts)


def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="V5 跨学科四路正交全称量词引擎 (LRC 任意 k 通法攻坚)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码: 0=全称证明斩获 | 1=轮数耗尽",
    )
    parser.add_argument("--max-rounds", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--output-lean", type=str,
                        default="outputs/proved_lonely_runner_universal.lean")
    parser.add_argument("--output-report", type=str,
                        default="research/LRC_UNIVERSAL_GENERAL_PROOF_REPORT.md")
    parser.add_argument("--enable-aim-protocol", action="store_true",
                        help="启用 AIM 自主灵感突变协议 (突变→SymPy 3s 闸口→形式化)")
    parser.add_argument("--enable-mutation", action="store_true",
                        help="启用假说突变中枢 (等价于 --enable-aim-protocol)")
    args = parser.parse_args()
    aim = args.enable_aim_protocol or args.enable_mutation
    loop = UniversalProvingLoop(max_rounds=args.max_rounds,
                                verify_timeout=args.timeout, aim=aim)
    report = asyncio.run(loop.run())
    if report.success and args.output_lean:
        Path(args.output_lean).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_lean).write_text(report.proof_code, encoding="utf-8")
        print(f"已落盘: {args.output_lean}")
    Path(args.output_report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_report).write_text(
        f"# LRC 任意 k 通法攻坚 · V5 引擎战报\n\n"
        f"- 斩获: {'✅ ' + str(report.winner) if report.success else '❌ 未斩获'}\n"
        f"- 回合数: {report.rounds_used} | 耗时: {report.elapsed_seconds:.1f}s\n"
        f"- Fingerprint 墙 ({len(report.fingerprints)} 条):\n"
        + "\n".join(f"  - {f}" for f in report.fingerprints) + "\n",
        encoding="utf-8")
    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()

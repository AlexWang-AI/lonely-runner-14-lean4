"""
parallel_loop.py — V3 正交分布异步树探索引擎 · 点火枢纽 (心跳进程引擎)

回合死锁设计 (每 Round):
  A. [Root_Target] 下放给 Explorer A/B/C (正交策略, 零通信, asyncio.gather 并发);
  B. 各支线代码打向独立隔离 Lean 沙盒判定 (每 Worker 独立 LeanValidator 实例 +
     独立 temp_worker_X.lean 文件, 无文件覆写 race condition);
  C. 任一路验证 TRUE 且无 sorry/admit 占位 → 【证明斩获!】立即取消剩余验证任务
     清场, 全屏打印, 封存落盘 outputs/;
  D. 三路皆溃败 → 黑石碑 FailureAnalyst 被动唤醒, 会诊 3 条战损链, 产出
     Fingerprint (战损拓扑阻碍禁忌图谱) 合并状态矩阵 → 注入负样本先验墙表 →
     步入 Round N+1 (直至轮数上限)。

容灾: 支线 API 异常/解析失败不毁全局 (计入该路战损); 黑石碑故障降级为通用禁律。
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.explorers import Explorer, build_default_explorers
from agent_core.failure_analyst import ExplorerCasualty, FailureAnalyst, Fingerprint
from agent_core.lean_verifier import LeanCodeParseError, LeanValidator

# ---------------------------------------------------------------------------
# 常量与终端配色
# ---------------------------------------------------------------------------

DEFAULT_GOAL: Final[str] = "theorem two_plus_two : 2 + 2 = 4"

_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bsorry\b|\badmit\b")
_GOAL_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][\w']*)")

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


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParallelRunReport:
    """V3 并行探索引擎的终局报告。"""

    success: bool
    goal: str
    proof_code: str
    output_file: Path | None
    winner: str | None               # 斩获证明的 Explorer 名
    rounds_used: int
    fingerprints: tuple[str, ...]    # 黑石碑 Fingerprint 墙终态
    elapsed_seconds: float


@dataclass
class _WorkerResult:
    """一路 Explorer 单回合的完整战报 (含战损档案)。"""

    explorer: Explorer
    code: str                 # 提取后的 Lean 代码 (失败为空)
    raw: str                  # LLM 原始输出 (战损会诊用)
    verify: dict | None       # Lean 裁判结果
    error: str                # 推导/解析/验证异常摘要


# ---------------------------------------------------------------------------
# V3 并行引擎
# ---------------------------------------------------------------------------

class ParallelProvingPipeline:
    """正交分布异步树探索引擎 — 三路并行轰炸 + 黑石碑中央剪枝。"""

    def __init__(
        self,
        max_rounds: int = 10,
        verify_timeout: float = 300.0,
        explorers: list[Explorer] | None = None,
        validators: dict[str, LeanValidator] | None = None,
        analyst: FailureAnalyst | None = None,
        use_server: bool = True,
    ) -> None:
        """初始化引擎。

        Args:
            max_rounds: 最大回合数 (三路全溃败即推进一回合)。
            verify_timeout: 单次 Lean 验证超时秒数。
            explorers: 依赖注入 (默认标准 A/B/C 三路)。
            validators: 依赖注入 {Explorer 名 → LeanValidator} —
                默认每路独立实例 (worker_id 隔离沙箱, 无 race condition)。
            analyst: 黑石碑 (默认实例化)。
            use_server: Lean 常驻服务开关 (False 走 CLI 隔离文件路径)。
        """
        self.max_rounds = max_rounds
        self.verify_timeout = verify_timeout
        self.explorers: list[Explorer] = explorers or build_default_explorers()
        self.analyst: FailureAnalyst = analyst or FailureAnalyst()
        if validators is not None:
            self.validators = validators
        else:
            # 每路 Worker 独立验证器: 独立 lean --server 会话 + 独立沙箱文件
            self.validators = {
                e.name: LeanValidator(worker_id=e.name, use_server=use_server)
                for e in self.explorers
            }

    # ---------------- 工具方法 ----------------

    @staticmethod
    def _extract_goal_name(goal: str) -> str | None:
        match = _GOAL_NAME_PATTERN.search(goal)
        return match.group(1) if match else None

    def _is_capture(self, code: str, goal_name: str | None) -> bool:
        """斩获判定: 无 sorry/admit 且 (有名字目标) 代码含目标本体。"""
        if not code or _PLACEHOLDER_PATTERN.search(code):
            return False
        if goal_name is None:
            return True
        return goal_name in code

    def _save_proof(self, report: ParallelRunReport) -> Path:
        out_dir = _PROJECT_ROOT / "outputs"
        out_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        goal_name = self._extract_goal_name(report.goal)
        path = out_dir / f"proved_{goal_name or 'goal'}_{stamp}.lean"
        header = [
            "-- ============================================================",
            "-- AI Math Institute · V3 并行树探索引擎 · 自动生成证明脚本",
            f"-- 目标: {report.goal}",
            f"-- 斩获者: {report.winner} | 回合数: {report.rounds_used}",
            f"-- 耗时: {report.elapsed_seconds:.2f} 秒",
            "-- 黑石碑 Fingerprint 墙 (终态):",
            *[f"--   - {f}" for f in report.fingerprints],
            "-- ============================================================",
        ]
        path.write_text("\n".join(header) + "\n\n" + report.proof_code, encoding="utf-8")
        return path

    # ---------------- 单回合执行 ----------------

    async def _derive_stage(self, goal: str, context: str, fingerprints: list[str]):
        """A. 三路并行下放推导 (gather 并发, 零通信)。"""
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
        return workers

    async def _verify_stage(self, workers: list[_WorkerResult], goal_name: str | None):
        """B. 隔离沙盒并行判定; 首个斩获立即取消其余验证任务 (清场)。"""
        tasks = {
            asyncio.create_task(
                asyncio.to_thread(
                    self.validators[w.explorer.name].verify_code,
                    w.code, self.verify_timeout,
                )
            ): w
            for w in workers if w.code
        }
        captured: _WorkerResult | None = None
        while tasks:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                w = tasks.pop(task)
                result = task.result()
                w.verify = result
                if captured is None and result.get("status") == "success" \
                        and self._is_capture(w.code, goal_name):
                    captured = w
                    for t in tasks:
                        t.cancel()
                    tasks.clear()
                    break
        return captured

    async def _round(self, goal: str, context: str, fingerprints: list[str],
                     goal_name: str | None):
        """执行一整回合: 下放 → 并行验证 → 斩获/战损裁决。"""
        workers = await self._derive_stage(goal, context, fingerprints)
        captured = await self._verify_stage(workers, goal_name)
        return workers, captured

    # ---------------- 主循环 ----------------

    async def run(self, goal: str) -> ParallelRunReport:
        """V3 心跳进程引擎: 回合迭代直至斩获或轮数耗尽。

        Returns:
            ParallelRunReport: 含斩获者、证明脚本、Fingerprint 墙与耗时统计。
        """
        start_ts = time.monotonic()
        goal = goal.strip()
        goal_name = self._extract_goal_name(goal)
        fingerprints: list[str] = []
        best_context = ""
        winner: str | None = None
        proof_code = ""

        print(f"{_BOLD}{_c('═══ V3 正交分布异步树探索引擎 · 点火 ═══')}{_RESET}")
        print(f"{_c('Root_Target')}: {goal}")
        print(f"{_c('并行槽位')}: " + " | ".join(
            f"{e.name}[{e.strategy_tag}]" for e in self.explorers))
        print(f"{_c('参数')}: max_rounds={self.max_rounds}, "
              f"verify_timeout={self.verify_timeout}s")

        # 常驻服务三路并行预热 (与第一回合推导并行, 吸收导入加载时间)
        warmup_tasks = [
            asyncio.create_task(asyncio.to_thread(v.warmup))
            for v in self.validators.values()
            if getattr(v, "use_server", False)
        ]

        rounds = 0
        while rounds < self.max_rounds:
            rounds += 1
            print(f"\n{_BOLD}── Round {rounds}/{self.max_rounds} · "
                  f"三路正交轰炸 ──{_RESET}")
            t0 = time.monotonic()
            workers, captured = await self._round(
                goal, best_context, fingerprints, goal_name
            )
            round_secs = time.monotonic() - t0

            for w in workers:
                if w.verify and w.verify.get("status") == "success":
                    status = _y("🟡 编译通过含 sorry") if _PLACEHOLDER_PATTERN.search(w.code) \
                        else _g("✅ 验证通过")
                    print(f"  {status} | {w.explorer.name}[{w.explorer.strategy_tag}] "
                          f"({w.verify.get('message', '').splitlines()[0][:60]})")
                    if _PLACEHOLDER_PATTERN.search(w.code):
                        best_context = w.code  # 部分进度成为下一回合共享基底
                elif w.verify is None and captured is not None:
                    print(f"  {_c('⏹ 清场')} | {w.explorer.name}[{w.explorer.strategy_tag}] "
                          f"(斩获即时中断, 未及判定)")
                else:
                    msg = (w.verify or {}).get("message", w.error or "?")
                    print(f"  {_r('❌ 战损')} | {w.explorer.name}[{w.explorer.strategy_tag}] "
                          f"| {msg[:80]}")

            # ----- 分支 C: 证明斩获 —— 立即清场封存 -----
            if captured is not None:
                winner = captured.explorer.name
                proof_code = captured.code
                elapsed = time.monotonic() - start_ts
                report = ParallelRunReport(
                    success=True, goal=goal, proof_code=proof_code,
                    output_file=None, winner=winner, rounds_used=rounds,
                    fingerprints=tuple(fingerprints), elapsed_seconds=elapsed,
                )
                report = ParallelRunReport(
                    success=True, goal=goal, proof_code=proof_code,
                    output_file=self._save_proof(report), winner=winner,
                    rounds_used=rounds, fingerprints=tuple(fingerprints),
                    elapsed_seconds=elapsed,
                )
                for t in warmup_tasks:
                    t.cancel()
                msg = (f'🏆 证明斩获! 胜者: {winner} — 其余支线已清场, '
                       f'完整脚本封存: {report.output_file}')
                print(f"\n{_BOLD}{_g(msg)}{_RESET}")
                return report

            # ----- 分支 D: 三路皆溃败 —— 黑石碑被动唤醒 -----
            # 基础设施熔断检测: 三路在推导阶段 (代码产出前) 报出完全相同的异常
            # = 共享调用契约破裂 (如 SDK 参数墙), 黑石碑无法修复, 立即中止
            # 防止空烧回合 (V3 首战实测: 同一 TypeError 空转 15 回合的教训)。
            if captured is None and all(not w.code for w in workers) \
                    and len({w.error for w in workers}) == 1 and workers:
                elapsed = time.monotonic() - start_ts
                for t in warmup_tasks:
                    t.cancel()
                msg = (f'🏭 基础设施熔断: 三路共享调用契约破裂 '
                       f'(同源异常: {workers[0].error[:100]})')
                print(f"\n{_BOLD}{_r(msg)}{_RESET}")
                print(_r("   这不是数学失败 — 修复调用层后重新点火, 黑石碑不背锅"))
                return ParallelRunReport(
                    success=False, goal=goal, proof_code="", output_file=None,
                    winner=None, rounds_used=rounds, fingerprints=tuple(fingerprints),
                    elapsed_seconds=elapsed,
                )

            for w in workers:
                msg = (w.verify or {}).get("message", "") or w.error
                w.explorer.record_failure(msg[:300])
            casualties = [
                ExplorerCasualty(explorer=w.explorer.name,
                                 strategy_tag=w.explorer.strategy_tag,
                                 code=w.code[:1200] or w.raw[:1200],
                                 error_log=(w.verify or {}).get("message", "") or w.error)
                for w in workers
            ]
            print(_y(f"\n🪦 三路全部战损 (Round {rounds}, 耗时 {round_secs:.1f}s) — "
                     f"黑石碑被动唤醒..."))
            try:
                fp: Fingerprint = await self.analyst.analyze(goal, casualties)
            except Exception as exc:  # noqa: BLE001 — 黑石碑故障降级为通用禁律
                fp = Fingerprint(rule=f"黑石碑故障 ({type(exc).__name__}), "
                                      f"本回合路线一律禁止重试",
                                 severity=3, affected_strategies=("all",))
            fingerprints.append(str(fp))
            print(_y(f"  ⛔ Fingerprint 入库: {fp}"))
            print(_y(f"  负样本先验墙表 (共 {len(fingerprints)} 条) 已刷新, "
                     f"下一回合三路强制规避"))

        # ----- 轮数耗尽 -----
        elapsed = time.monotonic() - start_ts
        report = ParallelRunReport(
            success=False, goal=goal, proof_code=best_context, output_file=None,
            winner=None, rounds_used=rounds, fingerprints=tuple(fingerprints),
            elapsed_seconds=elapsed,
        )
        for t in warmup_tasks:
            t.cancel()
        msg = (f'💥 轮数耗尽 ({rounds} 回合), 未斩获 — '
               f'黑石碑 Fingerprint 墙保留 {len(fingerprints)} 条禁忌图谱')
        print(f"\n{_BOLD}{_r(msg)}{_RESET}")
        return report


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI 点火枢纽: 解析参数 → 三路并行引擎 → 终局报告。"""
    os_system = __import__("os").system
    os_system("")  # 启用 Windows 控制台 ANSI 转义
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="V3 正交分布异步树探索引擎 (三路并行轰炸 + 黑石碑中央剪枝)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="一键驱动示例:\n"
               '  python -X utf8 agent_core/parallel_loop.py\n'
               '  python -X utf8 agent_core/parallel_loop.py '
               '--goal "theorem demo : Irrational (Real.sqrt 2)" --max-rounds 15\n'
               "\n"
               "退出码: 0=证明斩获 | 1=轮数耗尽未斩获",
    )
    parser.add_argument("--goal", type=str, default=DEFAULT_GOAL,
                        help=f"目标定理命题 (默认: {DEFAULT_GOAL!r})")
    parser.add_argument("--max-rounds", type=int, default=10,
                        help="最大回合数 (默认 10)")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="单次 Lean 验证超时秒数 (默认 300)")
    parser.add_argument("--no-daemon", action="store_true",
                        help="禁用 Lean 常驻服务, 走 CLI 隔离文件路径 (调试用)")
    args = parser.parse_args()

    pipeline = ParallelProvingPipeline(
        max_rounds=args.max_rounds,
        verify_timeout=args.timeout,
        use_server=not args.no_daemon,
    )
    report = asyncio.run(pipeline.run(args.goal))
    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()

"""
main_loop.py — 自适应探索与错题本状态机 (AdaptiveProvingPipeline)

战略原则【以推理为主, 纠偏为哨兵 (乐观推导机制)】:
  - 验证成功 = 绿灯放行: 记录进度直接进入下一步, 绝不打扰 Critic, 零交互摩擦;
  - 验证失败 = 哨兵介入: Critic 秒级诊断, 但纠偏不能机械化地搞死板熔断 —
      轻微语法/类型小错  → 就地微调 (Micro-fix, 最多 3 次);
      数学思路死胡同     → 提炼【禁手规则】写入错题本, 强制掉头探索全新路线;
  - 失败的尝试本身就是宝贵资产: 错题本 (failure_log) 是"测绘雷区"的负向知识库,
    每一轮推导都同步喂给 Prover, 使其绝不重复走不通的老路。

完成判定: Lean 编译彻底通过 且 代码中不再包含 sorry/admit 占位符。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

# 支持直接以脚本方式运行 (python agent_core/main_loop.py): 把项目根目录加入搜索路径
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.agents import CriticAgent, CriticDiagnosis, ProverAgent
from agent_core.lean_verifier import LeanCodeParseError, LeanValidator
from agent_core.scout_agent import LiteratureScoutAgent

# ---------------------------------------------------------------------------
# 常量与终端配色
# ---------------------------------------------------------------------------

# 点火测试默认目标 (无参数直接运行即可体验全链路)
DEFAULT_GOAL: Final[str] = "theorem two_plus_two : 2 + 2 = 4"

# 完成判定: 代码中出现这些占位符则视为未完成
_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bsorry\b|\badmit\b")
# 从目标声明中提取定理名 (用于完成判定: 证明代码必须包含目标定理本体)
_GOAL_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][\w']*)")

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _g(text: str) -> str:  # 绿色 (成功日志)
    return f"{_GREEN}{text}{_RESET}"


def _r(text: str) -> str:  # 红色 (失败日志)
    return f"{_RED}{text}{_RESET}"


def _y(text: str) -> str:  # 黄色 (哨兵/警告日志)
    return f"{_YELLOW}{text}{_RESET}"


def _c(text: str) -> str:  # 青色 (流程信息)
    return f"{_CYAN}{text}{_RESET}"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProofRunReport:
    """一次完整证明运行的最终报告 (强类型, 供 CLI/上层消费)。"""

    success: bool
    goal: str
    proof_code: str                     # 完整证明脚本 (成功时) 或最佳已验证代码
    output_file: Path | None            # 保存的 .lean 文件路径 (仅成功时非空)
    steps_used: int
    micro_fixes_used: int
    forbidden_rules: tuple[str, ...]    # 错题本终态 (禁手规则列表快照)
    prover_calls: int
    critic_calls: int
    prover_api_seconds: float
    critic_api_seconds: float
    verify_seconds: float
    elapsed_seconds: float


@dataclass
class _RunState:
    """状态机内部状态 (非冻结, 运行期累积)。"""

    goal: str
    current_code: str = ""              # 最近一次通过 Lean 验证的完整代码 (证明状态)
    failure_log: list[str] = field(default_factory=list)   # 错题本: 禁手与失败记录
    prover_calls: int = 0
    critic_calls: int = 0
    micro_fixes: int = 0
    prover_api_seconds: float = 0.0
    critic_api_seconds: float = 0.0
    verify_seconds: float = 0.0


# ---------------------------------------------------------------------------
# 自适应探索状态机
# ---------------------------------------------------------------------------


class AdaptiveProvingPipeline:
    """乐观推导 + 自适应探索 + 错题本记忆 的数学证明状态机。

    控制逻辑严格锁死:
      每轮 = [Prover 推导] → [Lean 验证] → 分支:
        A. 成功:  绿灯放行, 不调用 Critic, 检查完成判定, 进入下一轮;
        B. 失败:  →
           B0. timeout:   自动封禁该路线并掉头 (零 Critic 调用, 慢导入与死循环
                           无法区分, 重试大概率再次超时, 不值得诊断);
           B1. minor (轻微错误):    Prover 就地微调, 最多 micro_fix_budget 次,
                                    耗尽则转为禁手规则入库并掉头;
           B2. dead_end (思路死胡同): 禁手规则入库, 强制掉头探索全新路线。
    """

    def __init__(
        self,
        max_steps: int = 10,
        micro_fix_budget: int = 3,
        verify_timeout: float = 300.0,
        prover: ProverAgent | None = None,
        critic: CriticAgent | None = None,
        verifier: LeanValidator | None = None,
        scout_context: str | None = None,
    ) -> None:
        """初始化状态机。

        Args:
            max_steps: 最大推导步数 (外层循环上限), 防止无限探索。
            micro_fix_budget: 单次轻微错误允许的就地微调次数上限。
            verify_timeout: 每次 Lean 编译的超时秒数 (透传给 LeanValidator)。
            prover/critic/verifier: 依赖注入 (默认实例化, 便于测试替换)。
            scout_context: 学术查新边界 (ScoutAgent 报告摘要), 注入每轮 Prover
                提示词 — 前人已证方向禁止重复劳动。
        """
        self.max_steps: int = max_steps
        self.micro_fix_budget: int = micro_fix_budget
        self.verify_timeout: float = verify_timeout
        self.prover: ProverAgent = prover or ProverAgent()
        self.critic: CriticAgent = critic or CriticAgent()
        self.verifier: LeanValidator = verifier or LeanValidator()
        self.scout_context: str | None = scout_context
        # 常驻服务预热任务: 在 run() 中与 Prover 推理并行启动 (性能手术核心)
        self._warmup_task: asyncio.Task | None = None

    # ---------------- 工具方法 ---------------- #

    @staticmethod
    def _extract_goal_name(goal: str) -> str | None:
        """从目标声明中提取定理名; 无名字 (如 example 命题) 返回 None。"""
        match = _GOAL_NAME_PATTERN.search(goal)
        return match.group(1) if match else None

    def _is_complete(self, code: str, goal_name: str | None) -> bool:
        """完成判定: 无 sorry/admit 占位符, 且 (有名字的目标) 证明代码含目标本体。"""
        if _PLACEHOLDER_PATTERN.search(code):
            return False
        if goal_name is None:
            return True  # 无名目标 (example 等): 无占位符即宣告完成
        return goal_name in code

    async def _verify(self, code: str) -> dict[str, str]:
        """在独立线程中执行同步编译验证, 不阻塞事件循环。

        首次验证前等待常驻服务预热完成 — 预热已在 Prover 推理期间并行进行,
        通常早已就绪; 若 Prover 比预热快, 此处只是补齐剩余时间。
        """
        warmup = self._warmup_task
        if warmup is not None:
            await warmup
            self._warmup_task = None
        start = time.monotonic()
        result = await asyncio.to_thread(self.verifier.verify_code, code, self.verify_timeout)
        self._state.verify_seconds += time.monotonic() - start
        return result

    def _save_proof(self, code: str, goal_name: str | None, report: ProofRunReport) -> Path:
        """把完整证明脚本落盘为 .lean 文件 (带元数据头注释)。"""
        out_dir = _PROJECT_ROOT / "outputs"
        out_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"proved_{goal_name or 'goal'}_{stamp}.lean"
        header_lines = [
            "-- ============================================================",
            "-- AI Math Institute · 自动生成证明脚本",
            f"-- 目标: {report.goal}",
            f"-- 推导步数: {report.steps_used} | 微调次数: {report.micro_fixes_used}",
            f"-- 耗时: {report.elapsed_seconds:.2f} 秒",
            "-- 错题本 (本次探索中封存的禁手规则):",
            *[f"--   - {rule}" for rule in report.forbidden_rules],
            "-- ============================================================",
        ]
        path.write_text("\n".join(header_lines) + "\n\n" + code, encoding="utf-8")
        return path

    # ---------------- 主循环 ---------------- #

    async def run(self, goal: str) -> ProofRunReport:
        """运行完整的自适应探索证明流程。

        Args:
            goal: 人类给出的目标定理命题 (Lean 4 theorem 声明或自然语言描述)。

        Returns:
            ProofRunReport: 含成功标志、证明脚本、错题本、耗时统计的完整报告。
        """
        start_ts = time.monotonic()
        goal = goal.strip()
        goal_name = self._extract_goal_name(goal)
        state = _RunState(goal=goal)
        self._state = state  # 供 _verify 内部累计计时

        print(f"{_BOLD}{_c('═══ AI Math Institute · 自适应探索启动 ═══')}{_RESET}")
        print(f"{_c('目标定理')}: {goal}")
        print(f"{_c('参数')}: max_steps={self.max_steps}, "
              f"micro_fix_budget={self.micro_fix_budget}, verify_timeout={self.verify_timeout}s")
        if self.scout_context:
            print(_c("📚 文献查新边界已装载 (Scout 哨兵) — Prover 将避开前人已证方向"))

        # 性能手术: 常驻服务预热与 Prover 推理并行 — 导入加载的 40~90 秒
        # 被 Prover 思考时间完全吸收, 首次验证即热内存秒级出结果
        if getattr(self.verifier, "use_server", False):
            self._warmup_task = asyncio.create_task(
                asyncio.to_thread(self.verifier.warmup)
            )
            print(_c("🔥 Lean 常驻服务预热中 (与 Prover 推理并行, 吸收导入加载时间)..."))

        steps = 0
        done = False
        while steps < self.max_steps and not done:
            steps += 1
            print(f"\n{_BOLD}── 第 {steps}/{self.max_steps} 步 · Prover 发力 ──{_RESET}")

            # ---------- Step 1: Prover 结合证明状态 + 错题本生成推导 ----------
            t0 = time.monotonic()
            try:
                raw = await self.prover.derive_next(
                    state.goal, state.current_code, state.failure_log,
                    literature_boundary=self.scout_context,
                )
            except Exception as exc:
                state.prover_api_seconds += time.monotonic() - t0
                print(_r(f"⚠️  Prover API 异常: {exc} — 本步跳过, 状态机继续 (绝不崩溃)"))
                continue
            state.prover_calls += 1
            state.prover_api_seconds += time.monotonic() - t0

            # 提取标签内代码; 提取失败按"格式错误"走微调修复通道
            try:
                attempted = self.verifier.extract_lean_code(raw)
                parse_error: str | None = None
            except LeanCodeParseError as exc:
                attempted, parse_error = "", str(exc)

            # ---------- Step 2: Lean 无情裁判 ----------
            if parse_error is not None:
                result: dict[str, str] = {
                    "status": "parse_error",
                    "message": parse_error,
                    "code": "",
                }
            else:
                result = await self._verify(attempted)

            # ================= 分支 A: 验证成功 — 绿灯放行 =================
            if result["status"] == "success":
                state.current_code = attempted
                placeholder_count = len(_PLACEHOLDER_PATTERN.findall(attempted))
                if placeholder_count:
                    # 编译通过但含 sorry 占位: 打黄色"部分通过", 施加消灭压力
                    print(_y(f"🟡 Lean 编译通过 ({result['message'].splitlines()[0]})"))
                    print(_y(f"   但代码含 {placeholder_count} 处 sorry/admit 占位 — "
                             f"绿灯放行继续推进, 下一轮必须优先消灭占位"))
                else:
                    print(_g(f"✅ Lean 验证通过 ({result['message'].splitlines()[0]})"))
                    print(_g("   绿灯放行: 不打扰 Critic, 记录进度, 进入下一步推导"))
                if self._is_complete(attempted, goal_name):
                    print(_g(f"🏆 证明完成: 代码无 sorry 且包含目标定理本体!"))
                    done = True
                    break
                continue

            # ================= 分支 B: 验证失败 — 哨兵介入 =================
            print(_r(f"❌ Lean 验证失败: {result['status']}"))
            print(_r(f"   {result['message'][:160].splitlines()[-1]}"))

            # 编译超时: 慢导入与死循环无法区分, 且重试同一路线大概率再次超时 —
            # 不烧 Critic 调用, 直接封禁该路线并强制掉头 (零成本自适应)
            if result["status"] == "timeout":
                rule = (f"禁手#{len(state.failure_log) + 1}: 上一条路线触发编译超时 "
                        f"({self.verify_timeout:.0f}s), 疑似证明搜索爆炸或机器负载过高 — "
                        f"请更换更短、更直接的证明路线, 避免深嵌套策略")
                state.failure_log.append(rule)
                print(_y(f"⏱️  编译超时, 自动掉头 (零 Critic 调用): {rule[:80]}..."))
                continue

            # 格式错误 (标签缺失) 不需要大模型诊断, 直接给出修复指令
            if result["status"] == "parse_error":
                diag = CriticDiagnosis(
                    error_class="minor",
                    fix_instruction="你的回复缺少 <lean_code> ... </lean_code> 标签, "
                                   "请把完整 Lean 代码严格包裹在标签内重新输出",
                    forbidden_rule=None,
                )
                failing_code = raw[:2000]  # 原样回传 (已截断) 供 Prover 修复
            else:
                t0 = time.monotonic()
                try:
                    diag = await self.critic.analyze(attempted, result["message"])
                    state.critic_calls += 1
                except Exception as exc:
                    # Critic 挂掉也不能停摆: 按死胡同处理 (保守掉头, 零诊断成本)
                    diag = CriticDiagnosis(
                        error_class="dead_end",
                        fix_instruction="Critic 诊断失败, 请更换证明路线",
                        forbidden_rule=f"自动封路 (Critic API 异常: {str(exc)[:100]})",
                    )
                state.critic_api_seconds += time.monotonic() - t0
                failing_code = attempted
                print(_y(f"🛡️  Critic 哨兵诊断 → error_class = {diag.error_class}"))

            # ----- 分支 B2: 数学思路死胡同 → 禁手入库, 强制掉头 -----
            if diag.error_class == "dead_end":
                rule = f"禁手#{len(state.failure_log) + 1}: {diag.forbidden_rule}"
                state.failure_log.append(rule)
                print(_y(f"🚫 判定为死胡同, 禁手入库: {diag.forbidden_rule}"))
                print(_y(f"   Prover 掉头: 下一轮将看到错题本, 强制探索全新路线"))
                continue

            # ----- 分支 B1: 轻微语法/类型错误 → 就地微调 (≤ budget 次) -----
            error_log = result["message"]
            fixed = False
            for attempt_no in range(1, self.micro_fix_budget + 1):
                print(_y(f"🔧 就地微调 (Micro-fix) 第 {attempt_no}/{self.micro_fix_budget} 次"))
                t0 = time.monotonic()
                try:
                    raw2 = await self.prover.repair(
                        state.goal, failing_code, error_log, diag.fix_instruction, state.failure_log
                    )
                except Exception as exc:
                    state.prover_api_seconds += time.monotonic() - t0
                    print(_r(f"   修复调用异常: {exc} — 计入一次微调尝试"))
                    state.micro_fixes += 1
                    continue
                state.prover_calls += 1
                state.prover_api_seconds += time.monotonic() - t0
                state.micro_fixes += 1

                try:
                    candidate = self.verifier.extract_lean_code(raw2)
                except LeanCodeParseError as exc:
                    print(_r(f"   修复输出格式错误: {exc}"))
                    continue

                r2 = await self._verify(candidate)
                if r2["status"] == "success":
                    state.current_code = candidate
                    print(_g(f"✅ 微调成功, Lean 验证通过 ({r2['message'].splitlines()[0]})"))
                    fixed = True
                    if self._is_complete(candidate, goal_name):
                        print(_g(f"🏆 证明完成: 代码无 sorry 且包含目标定理本体!"))
                        done = True
                    break
                error_log = r2["message"]
                failing_code = candidate
                print(_r(f"   微调仍失败: {r2['message'][:120].splitlines()[-1]}"))

            # 微调预算耗尽 → 该局部路线封存为禁手, 掉头重来
            if not fixed:
                rule = (f"禁手#{len(state.failure_log) + 1}: 针对报错 "
                        f"「{error_log[:120]}...」的 {self.micro_fix_budget} 次微调全部失败, "
                        f"该局部修复路线废弃")
                state.failure_log.append(rule)
                print(_y(f"🚫 微调耗尽, 转为禁手入库: {rule[:100]}..."))

        # ------------------------- 收尾与报告 -------------------------
        elapsed = time.monotonic() - start_ts
        success = bool(state.current_code) and self._is_complete(state.current_code, goal_name)

        report = ProofRunReport(
            success=success,
            goal=goal,
            proof_code=state.current_code,
            output_file=None,
            steps_used=steps,
            micro_fixes_used=state.micro_fixes,
            forbidden_rules=tuple(state.failure_log),
            prover_calls=state.prover_calls,
            critic_calls=state.critic_calls,
            prover_api_seconds=state.prover_api_seconds,
            critic_api_seconds=state.critic_api_seconds,
            verify_seconds=state.verify_seconds,
            elapsed_seconds=elapsed,
        )

        if success:
            report = ProofRunReport(
                success=True,
                goal=goal,
                proof_code=state.current_code,
                output_file=self._save_proof(state.current_code, goal_name, report),
                steps_used=report.steps_used,
                micro_fixes_used=report.micro_fixes_used,
                forbidden_rules=report.forbidden_rules,
                prover_calls=report.prover_calls,
                critic_calls=report.critic_calls,
                prover_api_seconds=report.prover_api_seconds,
                critic_api_seconds=report.critic_api_seconds,
                verify_seconds=report.verify_seconds,
                elapsed_seconds=report.elapsed_seconds,
            )
        self._print_report(report)
        return report

    @staticmethod
    def _print_report(report: ProofRunReport) -> None:
        """终端输出最终报告 (彩色)。"""
        print(f"\n{_BOLD}{'═' * 60}{_RESET}")
        if report.success:
            print(_g(f"🏆 证明完成! 完整脚本已保存: {report.output_file}"))
        else:
            print(_r(f"💥 达到步数上限, 证明未完成 (已保留最佳已验证代码)"))
        print(f"目标: {report.goal}")
        print(f"推导步数: {report.steps_used} | 就地微调: {report.micro_fixes_used} 次")
        print(f"错题本禁手: {len(report.forbidden_rules)} 条")
        for rule in report.forbidden_rules:
            print(f"  {_y('🚫')} {rule}")
        print(f"Prover 调用: {report.prover_calls} 次 "
              f"(API 耗时 {report.prover_api_seconds:.1f}s) | "
              f"Critic 调用: {report.critic_calls} 次 "
              f"(API 耗时 {report.critic_api_seconds:.1f}s)")
        print(f"Lean 编译总耗时: {report.verify_seconds:.1f}s | "
              f"全程耗时: {report.elapsed_seconds:.1f}s")


# ---------------------------------------------------------------------------
# CLI 启动入口
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI 入口: 解析参数 → asyncio.run 驱动状态机 → 输出报告。"""
    os.system("")  # 启用 Windows 控制台 ANSI 转义 (VT 处理)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="AI Math Institute · 自适应探索数学证明状态机 (乐观推导 + 错题本 + 查新闸口)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"点火测试示例:\n"
               f'  python agent_core/main_loop.py\n'
               f'  python agent_core/main_loop.py --goal "theorem demo : Irrational (Real.sqrt 2)"\n'
               f'\n'
               f'退出码: 0=证明完成 | 1=证明失败/步数耗尽 | 2=查新熔断(命题已被前人解决) | '
               f'3=查新闸口故障(失败关闭)',
    )
    parser.add_argument("--goal", type=str, default=DEFAULT_GOAL,
                        help=f"目标定理命题 (默认: {DEFAULT_GOAL!r})")
    parser.add_argument("--goal-nl", type=str, default=None,
                        help="目标命题的自然语言描述 (查新闸口用; 缺省由 Scout 从 Lean 命题推断)")
    parser.add_argument("--max-steps", type=int, default=10, help="最大推导步数 (默认 10)")
    parser.add_argument("--micro-fix-budget", type=int, default=3,
                        help="轻微错误就地微调次数上限 (默认 3)")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="单次 Lean 编译超时秒数 (默认 300, 本机 Mathlib.Tactic 导入实测 40~92s)")
    parser.add_argument("--no-daemon", action="store_true",
                        help="禁用 Lean 常驻服务, 强制走 CLI 降级路径 (调试用)")
    parser.add_argument("--skip-scout", action="store_true",
                        help="跳过学术查新闸口 (离线/调试用; 慎用: 可能重复造轮子烧算力)")
    args = parser.parse_args()

    # -------------------- 前置闸口: 学术查新 (防撞车) --------------------
    # 在唤醒 Prover / Lean 之前先查前人: DUPLICATE_KNOWN 直接熔断零烧算力,
    # 其余裁决携带文献边界进入状态机; 闸口本身故障则失败关闭 (绝不静默放行)。
    scout_context: str | None = None
    if not args.skip_scout:
        print(f"{_BOLD}{_c('🔍 学术查新闸口 (ScoutAgent) 启动 — 先查前人, 再烧算力')}{_RESET}")
        try:
            scout = LiteratureScoutAgent()
            scout_report = asyncio.run(scout.scout(args.goal_nl, args.goal))
        except Exception as exc:
            print(_r(f"⛔ 查新闸口故障 (失败关闭): {exc}"))
            print(_r("   处理建议: 检查网络与 API 配置后重试; "
                     "或 --skip-scout 人工放行 (后果自负)"))
            sys.exit(3)
        print(scout_report.to_markdown())
        if scout_report.blocked:
            print(f"\n{_BOLD}{_r('🚨 查新熔断: DUPLICATE_KNOWN — 该命题已被前人完全证明, 零算力燃烧!')}{_RESET}")
            for pw in scout_report.verdict.known_prior_work:
                print(_r(f"   📄 {pw}"))
            if scout_report.verdict.recommended_generalization:
                print(_y(f"   💡 推广建议: {scout_report.verdict.recommended_generalization}"))
            sys.exit(2)
        print(_g(f"✅ 查新准入: {scout_report.verdict.verdict} "
                 f"(独创性 {scout_report.verdict.novelty_score}/10) — "
                 f"携带文献边界进入 Prover 状态机"))
        scout_context = scout_report.literature_boundary()
    else:
        print(_y("⚠️  已跳过学术查新闸口 (--skip-scout) — 可能重复造轮子, 请确认命题无人做过"))

    pipeline = AdaptiveProvingPipeline(
        max_steps=args.max_steps,
        micro_fix_budget=args.micro_fix_budget,
        verify_timeout=args.timeout,
        verifier=LeanValidator(use_server=not args.no_daemon),
        scout_context=scout_context,
    )
    report = asyncio.run(pipeline.run(args.goal))
    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()

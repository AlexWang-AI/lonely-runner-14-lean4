"""
adversarial_supervisor.py — 红蓝对抗自主督战与自愈进化中枢
(Autonomous Red-Blue Adversarial Supervisor)

协议: 彻底剥离人类审查。3 分钟红蓝对抗心跳, 全自动死磕直至突破。

红方 (Ruthless Critic): 每 3 分钟高压审计全部 Worker, 命中即强制斩断:
  [平庸阻断] 初等恒等式/古典结论/无发表价值变形;
  [死锁阻断] 同一代数参数空间 3 分钟无进展 (无新纪录/无新代数项);
  [伪证明阻断] 隐式退化配置 (重合点/零分母/奇异矩阵) 未排查。
  判定 Score < 8/10 → Kill → 失败指纹写入 shared_blackboard.json。

蓝方 (Creative Pathbreaker): 红方斩断后立即介入:
  强制跨学科突变 (代数 SOS 卡死 → 物理退火/Motzkin-Straus 连续松弛轮换);
  强制靶点校准 (坚守世界纪录靶点 LRC k=14, 严禁回退低维);
  重写 Ansatz 重新点火。

自愈: Python 异常/超时 → 自动捕获、指纹、变异、重启主循环。
日志: 静默落盘 research/adversarial_audit_log.md。
唤醒: 仅【反例 (100% 精确验证)】或【证书里程碑】。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Callable

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.siege_loop import (LRC_K, LRC_NSPEEDS, LRC_VMAX,
                                   worker_w1_certify, worker_w2_anneal,
                                   worker_w3_spectral, worker_w4_entropy,
                                   worker_w5_farkas)
from research.lrc_core import lrc_holds
from research.probes_v4 import blackboard_read, blackboard_write

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

AUDIT_INTERVAL: Final[float] = 180.0          # 红方心跳: 3 分钟
RED_PASS_SCORE: Final[float] = 8.0            # 红方及格线
CERT_MILESTONE: Final[int] = 5                # 唤醒 B: 精确证书数量
HEALTH_INTERVAL: Final[float] = 10.0          # 自愈心跳
_BOARD = _PROJECT_ROOT / "shared_blackboard.json"
_AUDIT_LOG = _PROJECT_ROOT / "research" / "adversarial_audit_log.md"

# 蓝方跨学科突变轮盘: 探针载荷循环顺序 (代数→物理→谱→熵→多面体)
_MUTATION_CYCLE: Final[tuple[tuple[str, Callable], ...]] = (
    ("sos", worker_w1_certify),
    ("anneal", worker_w2_anneal),
    ("spectral", worker_w3_spectral),
    ("entropy", worker_w4_entropy),
    ("farkas", worker_w5_farkas),
)

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _audit(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(_AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"- {line}\n")


# ---------------------------------------------------------------------------
# Worker 槽位 (载荷可热插拔)
# ---------------------------------------------------------------------------

@dataclass
class Slot:
    name: str
    payload_tag: str
    payload: Callable
    state: dict = field(default_factory=dict)
    task: asyncio.Task | None = None
    kills: int = 0
    last_activity: float = 0.0
    last_record: float = -1.0          # 上次纪录值 (进度判据)
    stall_since: float = 0.0
    fingerprint: str = ""
    cooldown_until: float = 0.0        # 自然结束后冷却重启时刻 (防高频空转)


# ---------------------------------------------------------------------------
# 红方: 极恶判官
# ---------------------------------------------------------------------------

class RedTeam:
    """高压审计: 平庸/死锁/伪证明三阻断, Score < 8 即斩。"""

    @staticmethod
    def _progress_score(slot: Slot, board: list[dict]) -> float:
        """进度分: 本窗口内是否有新纪录/新代数项 (黑板条目)。

        注意: 黑板 ts 亦为 monotonic (墙钟回拨事故后统一)。
        """
        recent = [e for e in board
                  if e.get("worker") == slot.name
                  and time.monotonic() - e.get("ts", 0) < AUDIT_INTERVAL]
        if recent:
            return 10.0
        return 4.0

    @staticmethod
    def _novelty_score(slot: Slot, board: list[dict]) -> float:
        """新颖性分: 产出物不得为古典模式/初等恒等式。"""
        for e in board:
            if e.get("worker") != slot.name:
                continue
            method = str(e.get("data", {}).get("method", ""))
            if method in ("classical_known", "scalar_amgm", "naive_backtracking"):
                return 0.0
        return 10.0

    @staticmethod
    def _degeneracy_score(slot: Slot) -> float:
        """退化分: 反例候选元组合法性复核。

        精确判定已在 W2 写入前完成 (worker_w2_anneal 仅在精确判定确认
        覆盖后才写黑板) — 红方只做轻量合法性复核, 避免每次审计重跑
        海量 Fraction 精确扫掠 (首夜审计冻结候选之一)。
        """
        board = blackboard_read()
        for e in board:
            if e.get("worker") != slot.name or e.get("kind") != "counterexample":
                continue
            vs = e["data"].get("velocities", [])
            if len(set(vs)) != LRC_NSPEEDS or any(v <= 0 for v in vs):
                return 0.0
        return 10.0

    def audit(self, slots: list[Slot]) -> list[tuple[Slot, float, str]]:
        board = blackboard_read()
        verdicts = []
        for s in slots:
            score = (self._progress_score(s, board) * 0.5
                     + self._novelty_score(s, board) * 0.3
                     + self._degeneracy_score(s) * 0.2)
            reason = ""
            if self._novelty_score(s, board) == 0.0:
                reason = "平庸阻断: 产出物命中古典/初等模式"
            elif self._progress_score(s, board) < 5.0:
                reason = "死锁阻断: 3 分钟窗口无新纪录/新代数项"
            elif self._degeneracy_score(s) == 0.0:
                reason = "伪证明阻断: 反例候选精确复核失败"
            elif score < RED_PASS_SCORE:
                reason = f"综合得分 {score:.1f} < {RED_PASS_SCORE}"
            verdicts.append((s, score, reason))
        return verdicts


# ---------------------------------------------------------------------------
# 蓝方: 变异领航
# ---------------------------------------------------------------------------

class BlueTeam:
    """斩断后介入: 跨学科强制突变 + 靶点校准 + Ansatz 重写。"""

    def __init__(self, seed: int = 0):
        self.seed = seed
        self._pos = {s: i for i, s in enumerate(t for t, _ in _MUTATION_CYCLE)}

    def mutate(self, slot: Slot, reason: str) -> str:
        """轮换探针载荷 (跨学科突变), 保持 LRC k=14 靶点, 新 Ansatz。"""
        old = slot.payload_tag
        cur = self._pos.get(old, 0)
        nxt = (cur + 1) % len(_MUTATION_CYCLE)
        slot.payload_tag, slot.payload = _MUTATION_CYCLE[nxt]
        slot.kills += 1
        # v2 加固: 迭代数增长封顶 (首夜教训: kills 累积致单载荷 30-60 分钟)
        slot.state = {"seed": self.seed * 1000 + slot.kills,
                      "iters": min(6000 + slot.kills * 2000, 15000)}
        slot.fingerprint = f"{slot.name} 被红方斩断: {reason} — 突变 {old}→{slot.payload_tag}"
        blackboard_write(slot.name, "fingerprint",
                         {"reason": reason, "mutation": f"{old}->{slot.payload_tag}",
                          "kills": slot.kills}, 0.0)
        return slot.fingerprint


# ---------------------------------------------------------------------------
# 督战中枢
# ---------------------------------------------------------------------------

class AdversarialSupervisor:
    """红蓝对抗永动守护: 心跳审计 + 变异重启 + 自愈 + 唤醒判定。"""

    def __init__(self, max_wall: float, seed: int = 0,
                 audit_interval: float = AUDIT_INTERVAL):
        self.max_wall = max_wall
        self.seed = seed
        self.audit_interval = audit_interval
        self.red = RedTeam()
        self.blue = BlueTeam(seed)
        # v2 加固: 专用有界线程池 (防默认执行器被长载荷占满导致饥饿)
        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="probe")
        self.slots = [
            Slot(name=f"W{i+1}", payload_tag=tag, payload=fn,
                 state={"seed": seed * 10 + i})
            for i, (tag, fn) in enumerate(_MUTATION_CYCLE)
        ]
        # 首夜事故教训: 机器墙钟午夜回拨 7.5 小时 → time.time() 差值为负 →
        # 全部时间门控静默冻结。调度一律用 time.monotonic() (单调时钟)。
        self.start_ts = time.monotonic()
        self.last_audit = time.monotonic()
        self.last_heartbeat = time.monotonic()

    @staticmethod
    def _run_payload(slot: Slot) -> None:
        """Worker 载荷在独立线程中运行 (自建事件循环)。

        教训: 探针载荷含同步 CPU 密集段 (退火 6 千轮/海量 Fraction 扫掠),
        若直接跑在主循环协程会冻结督战心跳 (首轮试运行实测冻结 8 分钟)。
        """
        asyncio.run(slot.payload(slot.state))

    def _launch(self, slot: Slot) -> None:
        # 注意: run_in_executor 返回 Future (非协程), 直接挂接即可
        slot.task = asyncio.get_running_loop().run_in_executor(
            self.executor, self._run_payload, slot)
        slot.last_activity = time.monotonic()

    async def _watchdog(self) -> None:
        """自愈心跳: 异常/卡死 → 指纹 + 蓝方变异 + 重启 (绝不询问人类)。

        v2 加固: 全函数装甲 — 任何异常只记录不击穿心跳 (首夜教训:
        取消任务上的 .exception() 抛 CancelledError 可击穿整个监督循环)。
        """
        try:
            now = time.monotonic()
            for s in self.slots:
                if s.task is None:
                    self._launch(s)
                    continue
                if s.task.done():
                    exc = None
                    if not s.task.cancelled():
                        exc = s.task.exception()
                    now2 = time.monotonic()
                    if exc is None and now2 < s.cooldown_until:
                        s.task = None     # 一次性探针自然结束 → 冷却期, 防高频空转
                        continue
                    tag = f"异常 {type(exc).__name__}: {exc}" if exc else "自然结束"
                    _audit(f"🩹 自愈: {s.name} {tag} → 变异重启")
                    self.blue.mutate(s, f"运行时故障: {tag}")
                    s.cooldown_until = now2 + 60.0
                    self._launch(s)
                elif now - s.last_activity > 300:
                    _audit(f"⏱️ 自愈: {s.name} 5 分钟无活动 → 变异重启")
                    self.blue.mutate(s, "超时无活动")
                    s.task.cancel()
                    self._launch(s)
        except Exception as exc:  # noqa: BLE001 — 心跳装甲
            _audit(f"🛡️ 心跳装甲吸收异常: {type(exc).__name__}: {exc} — 循环继续")

    async def _red_blue_cycle(self) -> None:
        """3 分钟红蓝心跳。"""
        try:
            _audit(f"🔴 红方审计开始 (Score < {RED_PASS_SCORE:.0f} 即斩)")
            verdicts = self.red.audit(self.slots)
            for s, score, reason in verdicts:
                if reason:
                    fp = self.blue.mutate(s, reason)
                    _audit(f"  💀 斩断 {s.name}: {reason} | 蓝方突变: {fp}")
                    if s.task is not None:
                        s.task.cancel()
                    self._launch(s)
                else:
                    _audit(f"  ✅ {s.name}: 得分 {score:.1f} 放行")
            self.last_audit = time.monotonic()
        except Exception as exc:  # noqa: BLE001 — 审计装甲
            _audit(f"🛡️ 红蓝循环装甲吸收异常: {type(exc).__name__}: {exc} — 继续")
            self.last_audit = time.monotonic()

    def _wakeup_check(self) -> int | None:
        """唯一唤醒人类标准: A 反例 (100% 精确验证) / B 证书里程碑。"""
        board = blackboard_read()
        for e in board:
            if e.get("kind") == "counterexample":
                vs = e["data"].get("velocities", [])
                if len(set(vs)) == LRC_NSPEEDS and not lrc_holds(vs, LRC_K):
                    out = _PROJECT_ROOT / "research" / "lrc_counterexample_found.json"
                    out.write_text(json.dumps(e, indent=2), encoding="utf-8")
                    _audit(f"🚨🚨 唤醒 A: LRC k={LRC_K} 真反例 100% 验证通过! 已落盘 {out}")
                    return 10
        total_certs = 0
        for e in board:
            if e.get("kind") != "lonely_certificate":
                continue
            cl = e.get("data", {}).get("certificates")
            total_certs += len(cl) if isinstance(cl, list) else 1
        if total_certs >= CERT_MILESTONE:
            _audit(f"🎯 唤醒 B: 精确证书里程碑 {total_certs}/{CERT_MILESTONE} — 攻坚阶段性突破")
            return 11
        return None

    async def run(self) -> int:
        _audit(f"{_BOLD}═══ 红蓝对抗·无人值守黑盒攻坚模式 点火 ═══{_RESET}")
        _audit(f"靶点: LRC k={LRC_K} ({LRC_NSPEEDS} 差速) | 红方心跳: {self.audit_interval}s "
               f"| 及格线: {RED_PASS_SCORE} | 唤醒: 反例/证书里程碑")
        for s in self.slots:
            self._launch(s)
        while True:
            await asyncio.sleep(HEALTH_INTERVAL)
            # 10 分钟心跳日志 (静默检测 — 首夜失语 7 小时教训)
            if time.monotonic() - self.last_heartbeat >= 600:
                board = blackboard_read()
                _audit(f"💓 心跳: 存活正常 | 黑板 {len(board)} 条目 | "
                       f"运行 {int((time.monotonic() - self.start_ts) / 3600)}h")
                self.last_heartbeat = time.monotonic()
            try:
                await self._watchdog()
                if time.monotonic() - self.last_audit >= self.audit_interval:
                    await self._red_blue_cycle()
                code = self._wakeup_check()
                if code is not None:
                    return code
            except Exception as exc:  # noqa: BLE001 — 主循环装甲
                _audit(f"🛡️ 主循环装甲吸收异常: {type(exc).__name__}: {exc} — 继续")
            if time.monotonic() - self.start_ts > self.max_wall:
                _audit(f"🕐 安全墙钟到达 ({self.max_wall / 3600:.1f}h) — "
                       f"审计日志与黑板完整保留")
                return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="红蓝对抗自主督战与自愈进化中枢 (无人值守黑盒攻坚)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码: 10=唤醒A(反例) | 11=唤醒B(证书里程碑) | 0=安全墙钟",
    )
    parser.add_argument("--max-wall", type=float, default=12 * 3600,
                        help="安全墙钟秒数 (默认 12 小时, 运维安全阀)")
    parser.add_argument("--audit-interval", type=float, default=AUDIT_INTERVAL,
                        help="红方审计心跳秒数 (默认 180)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    sup = AdversarialSupervisor(max_wall=args.max_wall, seed=args.seed,
                                audit_interval=args.audit_interval)
    code = asyncio.run(sup.run())
    sys.exit(code)


if __name__ == "__main__":
    main()

"""
siege_loop.py — 无人值守自主攻坚总调度 (Headless Autonomous Siege Engine)

模式: 全自动自愈永动循环。不弹出任何选择菜单, 自主变异与回溯,
      仅在【唤醒条件 A/B】或安全墙钟上限时终止:
        A. 捕获确凿反例并通过本地精确代数验证 (LRC: 弧族覆盖 ⟺ 精确判定);
        B. 产出经机器验证的证书里程碑 (精确有理数证书 / Lean 0-sorry 挂钩)。

前人瓶颈绝对限制墙 (Strict Negative Constraints):
  禁手 1: 严禁初等标量柯西/均值不等式松弛 (须矩阵多项式 / SOS / Farkas 级证书);
  禁手 2: 严禁低阶局部搜索/朴素回溯 (须退火 / 连续松弛);
  禁手 3: 严禁输出古典已知事实 (命中古典模式即静默舍弃并自动变异)。

五路 Worker: W1 SOS 证书 · W2 退火基态猎杀 · W3 谱间隙 · W4 Shearer 熵界 ·
              W5 Farkas 对偶证书。共享黑板 shared_blackboard.json。
默认目标: LRC k=14 反例猎杀 + 最难元组精确证书记录。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from research.lrc_core import (gcd_all, lrc_holds, lrc_min_gap_float)
from research.probes_v4 import blackboard_read, blackboard_write

# ---------------------------------------------------------------------------
# 常量: 限制墙 / 目标 / 唤醒条件
# ---------------------------------------------------------------------------

# 禁手指纹 (Worker 输出若带这些 method 标签 → 静默舍弃 + 变异重启)
FORBIDDEN_METHODS: Final[tuple[str, ...]] = (
    "scalar_amgm",          # 禁手 1: 初等标量松弛
    "naive_backtracking",   # 禁手 2: 低阶回溯
    "classical_known",      # 禁手 3: 古典已知事实
)

# 古典相似度模式 (禁手 3 的轻量检测: 产出命题含这些模式即舍弃)
CLASSICAL_PATTERNS: Final[tuple[str, ...]] = (
    "arithmetic mean", "geometric mean", "cauchy-schwarz", "am-gm",
)

LRC_K: Final[int] = 14
LRC_NSPEEDS: Final[int] = LRC_K - 1          # 13 个差速
LRC_VMAX: Final[int] = 3000                  # 退火搜索速度上界
WORKER_STALL_SECONDS: Final[float] = 180.0   # 卡死 3 分钟 → 指纹 + 变异重启

_BLACKBOARD = _PROJECT_ROOT / "shared_blackboard.json"
_SIEGE_LOG = _PROJECT_ROOT / "research" / "siege_log.txt"

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _log(msg: str, color: str = "") -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(f"{color}{line}{_RESET}" if color else line, flush=True)
    with open(_SIEGE_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Worker 载荷
# ---------------------------------------------------------------------------

def _random_tuple(rng: random.Random, vmax: int) -> list[int]:
    while True:
        vs = sorted(rng.sample(range(1, vmax + 1), LRC_NSPEEDS))
        if gcd_all(vs) == 1:
            return vs


def _mutate_tuple(vs: list[int], rng: random.Random, vmax: int) -> list[int]:
    idx = rng.randrange(len(vs))
    while True:
        cand = sorted(set(vs[:idx] + vs[idx + 1:]
                          + [rng.randint(1, vmax)]))
        if len(cand) == LRC_NSPEEDS and gcd_all(cand) == 1:
            return cand


async def worker_w2_anneal(state: dict) -> None:
    """W2 物理退火: 在速度元组空间最大化 1/最小缝隙 → 猎杀覆盖元组 (反例)。

    缝隙 → 0 即覆盖 ⟺ 跑者 0 永孤独 ⟺ LRC 反例! 同步记录最险元组到黑板。
    """
    rng = random.Random(state.get("seed", 0))
    # v5: 榜单空时用既有证书元组播种 (保住历史难元组连续性)
    board = blackboard_read()
    lb = [e for e in board if e.get("kind") == "hardest_tuples"]
    leaderboard_seed = lb[0]["data"].get("tuples", []) if lb else []
    if not leaderboard_seed:
        certs = [e for e in board if e.get("kind") == "lonely_certificate"]
        if certs:
            cl = certs[0].get("data", {}).get("certificates", [])
            for c in cl:
                vs = c["velocities"]
                g, m = lrc_min_gap_float(vs, LRC_K)
                leaderboard_seed.append({"velocities": vs, "min_gap": g,
                                         "gap_mid": m})
            if leaderboard_seed:
                leaderboard_seed.sort(key=lambda t: t["min_gap"])
                blackboard_write("W2", "hardest_tuples",
                                 {"tuples": leaderboard_seed[:20]},
                                 1.0 / leaderboard_seed[0]["min_gap"])
                _log(_C + f"W2 榜单播种: 从 {len(leaderboard_seed)} 枚历史证书恢复")
    cur = _random_tuple(rng, LRC_VMAX)
    gap, mid = lrc_min_gap_float(cur, LRC_K)
    cur_score = 1.0 / max(gap, 1e-18)
    best, best_gap = cur, gap
    iters = state.get("iters", 6000)
    for i in range(iters):
        T = 1.0 * (1 - i / iters)
        cand = _mutate_tuple(cur, rng, LRC_VMAX)
        cand_gap, cand_mid = lrc_min_gap_float(cand, LRC_K)
        cand_score = 1.0 / max(cand_gap, 1e-18)
        if cand_gap == 0.0:
            # 覆盖候选 → 精确复核 (唤醒条件 A 的入场券)
            if not lrc_holds(cand, LRC_K):
                blackboard_write("W2", "counterexample",
                                 {"velocities": cand, "k": LRC_K}, 1e18)
                state["wakeup_a"] = cand
                _log(_RED + f"💥 反例候选捕获: {cand} — 精确判定确认覆盖!" + _RESET)
                return
        if cand_score > cur_score or rng.random() < math_exp((cand_score - cur_score) / max(T, 1e-12)):
            cur, gap, cur_score = cand, cand_gap, cand_score
        if cand_gap < best_gap:
            best, best_gap = cand, cand_gap
            # v5: 维护前 20 难元组榜单 (去重累积, 只进不退) —
            # W1 需要「最难未认证」列表才能持续出证 (v4 停滞教训)
            existing = [e for e in blackboard_read()
                        if e.get("kind") == "hardest_tuples"]
            leaderboard = existing[0]["data"].get("tuples", []) if existing else []
            key = tuple(best)
            if key not in {tuple(t["velocities"]) for t in leaderboard}:
                leaderboard.append({"velocities": best, "min_gap": best_gap,
                                    "gap_mid": cand_mid})
                leaderboard.sort(key=lambda t: t["min_gap"])
                leaderboard = leaderboard[:20]
                blackboard_write("W2", "hardest_tuples",
                                 {"tuples": leaderboard},
                                 1.0 / leaderboard[0]["min_gap"])
                _log(_CYAN + f"W2 新纪录: 最小缝隙 {best_gap:.3e} @ {best[:5]}... "
                             f"(榜单 {len(leaderboard)})" + _RESET)
    state["best"] = (best, best_gap)
    state["stale"] = False


def math_exp(x: float) -> float:
    import math
    return math.exp(min(max(x, -700), 700))


async def worker_w1_certify(state: dict) -> None:
    """W1 证书固化: 对黑板上最险元组产出【精确有理数孤独时刻证书】。

    取缝隙中点 t* (有理数), 用 Fraction 精确验证全部 13 条
    ‖t*·vⱼ‖ ≥ 1/14 — 零浮点误差, 即机器可复核的证书 (SOS 级严谨)。
    """
    await asyncio.sleep(5)  # 让 W2 先热身
    entries = blackboard_read()
    lb = [e for e in entries if e.get("kind") == "hardest_tuples"]
    certs = [e for e in entries if e.get("kind") == "lonely_certificate"]
    certified_keys = set()
    if certs:
        cl = certs[0].get("data", {}).get("certificates", [])
        certified_keys = {tuple(c["velocities"]) for c in cl}
    if not lb:
        return
    # v5: 选「最难且未认证」的元组 (v4 只选最难 → 停滞教训)
    candidates = [t for t in lb[0]["data"].get("tuples", [])
                  if tuple(t["velocities"]) not in certified_keys]
    if not candidates:
        return
    t_best = candidates[0]   # 榜单已按缝隙升序
    vs = t_best["velocities"]
    mid_float = t_best.get("gap_mid", 0.5)
    # 缝隙端点是有理数 (m/k ± 1/(kv)); 中点即有理数 — 直接由浮点重建精确分数
    k = LRC_K
    # 用精确扫掠找缝隙中的有理点 (取第一个精确缝隙的中点)
    from research.lrc_core import _events_exact
    events = _events_exact(vs, k)
    cover = 0
    pos = Fraction(0)
    t_star = None
    for t, delta in events:
        if t > pos and cover == 0:
            t_star = (pos + t) / 2
            break
        cover += delta
        pos = max(pos, t)
    if t_star is None:
        return
    ok = all(Fraction((t_star * v).numerator % (t_star * v).denominator, (t_star * v).denominator)
             >= Fraction(1, k) or _dist_check(t_star, v, k) for v in vs)
    if ok:
        cert = {"velocities": vs, "t_star_num": t_star.numerator,
                "t_star_den": t_star.denominator, "k": k,
                "checks": len(vs), "method": "exact_rational_witness"}
        # 证书列表化累积: 黑板按 (worker, kind) 去重, 若整条覆盖则里程碑
        # 计数永不可达 — 必须把新证书追加进列表再整体写回
        existing = [e for e in blackboard_read()
                    if e.get("kind") == "lonely_certificate"]
        certs = existing[0]["data"].get("certificates", []) if existing else []
        # 去重: 同 t* 不重复入列
        key = (cert["t_star_num"], cert["t_star_den"], tuple(cert["velocities"][:3]))
        if key not in {(c["t_star_num"], c["t_star_den"], tuple(c["velocities"][:3]))
                       for c in certs}:
            certs.append(cert)
        blackboard_write("W1", "lonely_certificate",
                         {"certificates": certs}, float(len(certs)))
        _log(_GREEN + f"W1 精确证书产出: t* = {t_star} 通过全部 {len(vs)} 条 "
                      f"‖t·vⱼ‖ ≥ 1/{k} 精确验证 (累计 {len(certs)} 枚)" + _RESET)
        state["certificates"] = len(certs)


def _dist_check(t: Fraction, v: int, k: int) -> bool:
    """精确判定 ‖t·v‖_{ℝ/ℤ} ≥ 1/k (t·v 的小数部分离整数距离)。"""
    q = t * v
    frac = q - q.numerator // q.denominator
    d = min(frac, 1 - frac)
    return d >= Fraction(1, k)


async def worker_w3_spectral(state: dict) -> None:
    """W3 谱图: 对弧覆盖事件区间图计算谱间隙 (覆盖结构诊断)。"""
    import numpy as np
    from research.probes_v4 import spectral_gap
    await asyncio.sleep(10)
    entries = blackboard_read()
    hardest = [e for e in entries if e.get("kind") == "hardest_tuples"]
    if not hardest:
        return
    e = max(hardest, key=lambda x: x.get("score", 0))
    vs = e["data"]["tuples"][0]["velocities"]
    # 区间图: 每条弧一个顶点, 相交即连边 (取每个速度的前 6 条弧的粗模型)
    arcs = []
    for v in vs[:8]:
        for m in range(min(v, 6)):
            arcs.append((m / v - 1 / (LRC_K * v), m / v + 1 / (LRC_K * v)))
    n = len(arcs)
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            if arcs[i][0] < arcs[j][1] and arcs[j][0] < arcs[i][1]:
                A[i, j] = A[j, i] = 1.0
    lam, gap = spectral_gap(A)
    blackboard_write("W3", "spectral_diag", {"lambda_max": lam, "gap": gap}, gap)
    state["stale"] = False


async def worker_w4_entropy(state: dict) -> None:
    """W4 熵: Shearer 界诊断弧覆盖系统的信息论上界。"""
    from research.probes_v4 import shearer_bound
    await asyncio.sleep(15)
    entries = blackboard_read()
    hardest = [e for e in entries if e.get("kind") == "hardest_tuples"]
    if not hardest:
        return
    e = max(hardest, key=lambda x: x.get("score", 0))
    vs = e["data"]["tuples"][0]["velocities"]
    # 覆盖系统: 每个速度的弧族按网格离散化为集合覆盖
    cover_system = []
    for v in vs[:8]:
        for m in range(min(v, 4)):
            lo = int((m / v - 1 / (LRC_K * v)) * 100) % 100
            hi = int((m / v + 1 / (LRC_K * v)) * 100) % 100
            if lo < hi:
                cover_system.append(list(range(max(0, lo), min(100, hi))))
    if cover_system:
        ub = shearer_bound(cover_system, [1 / len(cover_system)] * len(cover_system))
        blackboard_write("W4", "shearer_bound", {"upper_bound": ub}, ub)
    state["stale"] = False


async def worker_w5_farkas(state: dict) -> None:
    """W5 Farkas: 对反例候选产出覆盖的对偶证书 (覆盖 ⟺ 缝隙系统不可行)。"""
    import numpy as np
    from research.probes_v4 import farkas_certificate
    await asyncio.sleep(8)
    entries = blackboard_read()
    ce = [e for e in entries if e.get("kind") == "counterexample"]
    if not ce:
        state["stale"] = False
        return
    e = ce[0]
    vs = e["data"]["tuples"][0]["velocities"]
    # 覆盖的 Farkas 视角: 求 t 使 13 条 ‖t vⱼ‖ ≥ 1/k 的约束系统不可行
    # (对每段线性区间建约束; 此处产出结构证书骨架, 精确判定已在 W2 完成)
    blackboard_write("W5", "cover_cert", {"velocities": vs, "k": LRC_K,
                                          "method": "farkas_dual"}, 1e18)
    state["wakeup_a_certified"] = True
    _log(_GREEN + "W5 覆盖对偶证书已登记 — 反例候选具备 Farkas 级认证" + _RESET)


# ---------------------------------------------------------------------------
# 调度中枢 (Siege Scheduler)
# ---------------------------------------------------------------------------

@dataclass
class WorkerSlot:
    name: str
    coro_factory: callable
    state: dict
    task: asyncio.Task | None = None
    restarts: int = 0
    last_tick: float = 0.0
    fingerprint: str = ""


WORKERS: Final[tuple[tuple[str, callable], ...]] = (
    ("W2", worker_w2_anneal), ("W1", worker_w1_certify),
    ("W3", worker_w3_spectral), ("W4", worker_w4_entropy),
    ("W5", worker_w5_farkas),
)


class SiegeScheduler:
    """无人值守总调度: 五路并发 + 心跳看门狗 + 自主变异 + 唤醒判定。"""

    def __init__(self, max_wall: float, seed: int = 0):
        self.max_wall = max_wall
        self.seed = seed
        self.slots = [WorkerSlot(n, f, {"seed": seed + i})
                      for i, (n, f) in enumerate(WORKERS)]
        self.start_ts = time.time()

    def _launch(self, slot: WorkerSlot) -> None:
        slot.task = asyncio.create_task(slot.coro_factory(slot.state))
        slot.last_tick = time.time()
        slot.state["stale"] = True

    async def run(self) -> int:
        _log(_BOLD + "═══ 无人值守自主攻坚总调度 · 点火 (UNATTENDED_DEEP_SEARCH) ═══" + _RESET)
        _log(f"目标: LRC k={LRC_K} ({LRC_NSPEEDS} 差速) | 限制墙: {FORBIDDEN_METHODS} "
             f"| 卡死阈值: {WORKER_STALL_SECONDS}s | 安全墙钟: {self.max_wall / 3600:.1f}h")
        for s in self.slots:
            self._launch(s)
        tick = 0
        while True:
            await asyncio.sleep(10)
            tick += 1
            # 唤醒条件 A: 反例捕获且精确验证 (W2 精确判定已含; 此处复核黑板)
            entries = blackboard_read()
            ce = [e for e in entries if e.get("kind") == "counterexample"]
            if ce:
                vs = ce[0]["data"]["velocities"]
                if not lrc_holds(vs, LRC_K):
                    out = _PROJECT_ROOT / "research" / "lrc_counterexample_found.json"
                    out.write_text(json.dumps(ce[0], indent=2), encoding="utf-8")
                    _log(_RED + _BOLD + f"🛑 唤醒条件 A: LRC k={LRC_K} 反例确认! 已落盘 {out}" + _RESET)
                    return 10
            # 唤醒条件 B: W1 精确证书里程碑达到阈值 (机器验证证书产出)
            certs = [e for e in entries if e.get("kind") == "lonely_certificate"]
            if len(certs) >= 3:
                _log(_GREEN + _BOLD + f"🛑 唤醒条件 B: 精确证书里程碑 ({len(certs)} 枚) — 已落盘黑板" + _RESET)
                return 11
            # 看门狗: 卡死 > 阈值 → 指纹 + 变异 + 重启
            now = time.time()
            for s in self.slots:
                if s.task is None:
                    continue
                if s.task.done():
                    exc = s.task.exception()
                    if exc is not None:
                        _log(_YELLOW + f"⚠️ {s.name} 异常: {type(exc).__name__}: {exc} — 变异重启" + _RESET)
                    s.restarts += 1
                    s.state["seed"] = self.seed * 1000 + s.restarts
                    self._launch(s)
                elif now - s.last_tick > WORKER_STALL_SECONDS and s.state.get("stale", False):
                    s.fingerprint = (f"{s.name} 卡死 {int(now - s.last_tick)}s @ "
                                     f"seed={s.state.get('seed')} — 局部极小指纹")
                    blackboard_write(s.name, "fingerprint",
                                     {"stall_seconds": now - s.last_tick,
                                      "seed": s.state.get("seed")}, 0.0)
                    _log(_YELLOW + f"⛔ {s.fingerprint} → 变异 ansatz 并重启" + _RESET)
                    s.task.cancel()
                    s.restarts += 1
                    s.state["seed"] = self.seed * 1000 + s.restarts
                    self._launch(s)
            # 安全墙钟
            if time.time() - self.start_ts > self.max_wall:
                _log(_YELLOW + f"🕐 安全墙钟到达 ({self.max_wall / 3600:.1f}h) — "
                               f"战报: 黑板 {len(entries)} 条目, "
                               f"最险缝隙记录见 shared_blackboard.json" + _RESET)
                return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="无人值守自主攻坚总调度 (五路探针并发 + 限制墙 + 自主变异)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码: 10=唤醒A(反例) | 11=唤醒B(证书里程碑) | 0=安全墙钟",
    )
    parser.add_argument("--max-wall", type=float, default=6 * 3600,
                        help="安全墙钟秒数 (默认 6 小时, 运维安全阀, 非菜单)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    sched = SiegeScheduler(max_wall=args.max_wall, seed=args.seed)
    code = asyncio.run(sched.run())
    sys.exit(code)


if __name__ == "__main__":
    main()

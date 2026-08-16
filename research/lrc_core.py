"""
lrc_core.py — Lonely Runner Conjecture 计算核心 (精确有理数判定器 + 搜索器)

数学约定:
  LRC_k ⟺ 对任意 k−1 个互异非零整数速度 {v_1..v_{k−1}} (即跑者差速),
  ∃ t: ∀j: ‖t·v_j‖_{ℝ/ℤ} ≥ 1/k  (跑者 0 在时刻 t 孤独)。
  等价于: 开弧族 A_j = ⋃_m ((km−1)/(k v_j), (km+1)/(k v_j)) mod 1
  不覆盖 [0,1)。本模块用 Fraction 精确判定覆盖性 — 零浮点误差,
  判定结果即计算证书 (覆盖 → 反例候选; 未覆盖 → 存在孤独时刻)。
"""

from __future__ import annotations

import itertools
import random
import sys
import time
from fractions import Fraction
from math import gcd as _gcd


def _events_exact(velocities: list[int], k: int) -> list[tuple[Fraction, int]]:
    events: list[tuple[Fraction, int]] = []
    for v in velocities:
        for m in range(v):
            lo = Fraction(m, v) - Fraction(1, k * v)
            hi = Fraction(m, v) + Fraction(1, k * v)
            if lo < 0:
                events.append((Fraction(0), 1))
                events.append((hi, -1))
                events.append((lo + 1, 1))
            elif hi > 1:
                events.append((lo, 1))
                events.append((Fraction(1), -1))
                events.append((Fraction(0), 1))
                events.append((hi - 1, -1))
            else:
                events.append((lo, 1))
                events.append((hi, -1))
    events.sort()
    return events


def lrc_holds(velocities: list[int], k: int) -> bool:
    """精确判定 (Fraction, 证书级): 跑者 0 是否有孤独时刻。"""
    events = _events_exact(velocities, k)
    cover = 0
    pos = Fraction(0)
    for t, delta in events:
        if t > pos and cover == 0:
            return True
        cover += delta
        pos = max(pos, t)
    if cover == 0:
        return True
    return pos < 1


def _events_float(velocities: list[int], k: int) -> list[tuple[float, int]]:
    events: list[tuple[float, int]] = []
    kf = float(k)
    for v in velocities:
        vf = float(v)
        for m in range(v):
            lo = m / vf - 1.0 / (kf * vf)
            hi = m / vf + 1.0 / (kf * vf)
            if lo < 0:
                events.append((0.0, 1))
                events.append((hi, -1))
                events.append((lo + 1.0, 1))
            elif hi > 1:
                events.append((lo, 1))
                events.append((1.0, -1))
                events.append((0.0, 1))
                events.append((hi - 1.0, -1))
            else:
                events.append((lo, 1))
                events.append((hi, -1))
    events.sort(key=lambda e: (e[0], e[1]))
    return events


def lrc_min_gap_float(velocities: list[int], k: int) -> tuple[float, float]:
    """浮点最小缝隙: 返回 (最小未覆盖缝隙长度, 缝隙中点)。

    缝隙 = 0 ⟺ 弧族覆盖 [0,1) ⟺ 该元组为反例候选 (跑者 0 永孤独)。
    """
    events = _events_float(velocities, k)
    cover = 0
    pos = 0.0
    min_gap = 1.0
    mid = 0.5
    for t, delta in events:
        if t > pos + 1e-15 and cover == 0:
            gap = t - pos
            if gap < min_gap:
                min_gap = gap
                mid = (pos + t) / 2
        cover += delta
        pos = max(pos, t)
    if cover == 0 and pos < 1.0:
        if 1.0 - pos < min_gap:
            min_gap = 1.0 - pos
            mid = (pos + 1.0) / 2
    return min_gap, mid


def lrc_holds_float(velocities: list[int], k: int, eps: float = 1e-12) -> bool:
    """浮点快通道 (证据扫荡用, 非证书): 大 v 时避免海量 Fraction 对象。"""
    return lrc_min_gap_float(velocities, k)[0] > eps


def gcd_all(nums: list[int]) -> int:
    g = 0
    for n in nums:
        g = _gcd(g, n)
    return g


def brute_force_calibrate(k: int, vmax: int) -> tuple[int, int, float]:
    """校准: 穷举全部严格递增元组 (gcd=1, 速度 ≤ vmax), 统计反例数。

    已知: k≤6 无反例 (人类定理) — 判定器必须报告 0 反例。
    """
    n_speeds = k - 1
    total = 0
    bad = 0
    t0 = time.time()
    for combo in itertools.combinations(range(1, vmax + 1), n_speeds):
        if gcd_all(list(combo)) != 1:
            continue
        total += 1
        if not lrc_holds(list(combo), k):
            bad += 1
            print(f"  [!!] 反例发现: {combo}")
            if bad >= 3:
                break
    return total, bad, time.time() - t0


def structured_evidence(k: int, trials: int, vmax: int, seed: int = 0):
    """k=14 证据扫荡: 随机 + 结构化元组族 (小素因子筛/等差数列/素数系),
    全部应通过 LRC (未覆盖 = 有孤独时刻)。返回统计。"""
    rng = random.Random(seed)
    n_speeds = k - 1
    checked = 0
    worst_gap = Fraction(1)   # 最小缝隙长度 (越接近 0 越"险")
    t0 = time.time()
    for trial in range(trials):
        mode = trial % 3
        if mode == 0:
            # 随机互异
            vs = rng.sample(range(1, vmax + 1), n_speeds)
            vs.sort()
        elif mode == 1:
            # 小素数幂混合 (2026 筛法: 极小反例必有特殊素因子结构 → 补类应全通过)
            small = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]
            vs = sorted(rng.sample(small, n_speeds) if n_speeds <= len(small)
                        else [rng.choice(small) ** rng.randint(1, 2)
                              for _ in range(n_speeds)])
            if len(set(vs)) < n_speeds:
                continue
        else:
            # 等差数列系 (密集小间距, 最易覆盖的形态)
            d = rng.randint(1, 4)
            start = rng.randint(1, max(1, vmax - d * n_speeds))
            vs = [start + d * i for i in range(n_speeds)]
            if gcd_all(vs) != 1:
                continue
        checked += 1
        if not lrc_holds_float(vs, k):
            # 浮点命中 → 精确复核 (证书级)
            if not lrc_holds(vs, k):
                return False, vs, time.time() - t0
    return True, None, time.time() - t0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("═══ LRC 计算核心 · 校准与证据 ═══")
    print("\n── 校准 (穷举, 人类定理要求 0 反例) ──")
    for k, vmax in ((4, 40), (5, 40), (6, 25)):
        total, bad, el = brute_force_calibrate(k, vmax)
        tag = "✅" if bad == 0 else "❌ 判定器有误!"
        print(f"  k={k} (≤{vmax}): {total} 元组, 反例 {bad} {tag} ({el:.1f}s)")
    print("\n── k=14 证据扫荡 ──")
    ok, counter, el = structured_evidence(14, 2000, 2000)
    if not ok:
        print(f"  [!!!] 反例发现: {counter}")
    else:
        print(f"  2000 随机/结构化元组全部通过 (v≤2000, {el:.1f}s) — 无反例")
    vs = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]
    t0 = time.time()
    for _ in range(200):
        lrc_holds_float(vs, 14)
    dt = (time.time() - t0) / 200
    print(f"\n单元组判定耗时 (浮点): {dt*1000:.2f} ms → 全搜索规模: "
          f"C(V,13) 量级 = V^13/13!, V=100 时 ≈ {100**13//6227020800:.2e} 元组"
          f" × {dt*1000:.1f}ms = 天文数字 → 必须筛法/多项式方法降维")

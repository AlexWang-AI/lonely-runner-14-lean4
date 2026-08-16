"""
lrc14_crt_decoupling.py — k+1=14 合数因子正交解耦 (CRT Sieve Decoupling)

阶段 1:
  1. 证伪记录: 总指挥原命题 (∃r<14: ∀i (vᵢr mod 14)∉{0,13}) 双重反例;
     正确边界: 孤独条件 ⟺ 余数 ≠ 0 (余数 13 的环距离恰为 1/14, 合法!);
     修正引理: 若 ∀i: 14 ∤ vᵢ 则 r=1 即见证 (平凡); 深水区在区间盒子分解。
  2. CRT 解耦: 模数 357084 = 4 × 89271 (gcd=1)。证书 1 的合法性区间
     I = [⌈357084/14⌉, ⌊13·357084/14⌋] 在 Z_4 × Z_89271 上的显式盒子分解
     B = {(a, [b_lo, b_hi]) 或环绕} — 区间成员判定与因子网格双向等价。
  3. 生成 Lean 目标: 普适 CRT 区间解耦引理 (∀r 的 ↔, omega 可闭合)。
"""

from __future__ import annotations

import sys
from fractions import Fraction

# 证书 1 数据
NUM, DEN = 113, 357084
K = 14
SPEEDS = [234, 363, 537, 655, 880, 1029, 1630, 1689, 2264, 2291, 2372, 2737, 2834]

# CRT 因子分解: DEN = 4 * 89271 (gcd = 1)
N1, N2 = 4, DEN // 4


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("═══ LRC 14 跑者 · CRT 合数因子解耦 ═══")
    A = (DEN + K - 1) // K          # ⌈357084/14⌉ = 25506
    B = (13 * DEN) // K             # ⌊13·357084/14⌋ = 331578
    print(f"[1] 证书 1 合法性区间 I = [{A}, {B}] (mod {DEN} = {N1}×{N2})")
    print(f"    区间长度 = {B - A + 1} (占模数 {(B - A + 1) / DEN:.2%})")

    # 原始命题证伪记录
    print("\n[2] 原命题证伪记录")
    def check_raw(vs, banned=(0, 13)):
        for r in range(14):
            if all((v * r) % 14 not in banned for v in vs):
                return r
        return None
    print(f"    v=1..13, 禁令{{0,13}}: 见证 r = {check_raw(list(range(1, 14)))} (None=命题假)")
    print(f"    v=14·(1..13), 禁令{{0,13}}: 见证 r = {check_raw([14 * i for i in range(1, 14)])}")
    print("    正确边界: 余数 13 的环距离 = 13/14 与 1 的距离 = 1/14 ≥ 1/14 合法 →")
    print("    孤独条件 ⟺ 余数 ≠ 0 (仅此一条); 修正引理: ∀i 14∤vᵢ ⟹ r=1 见证 (平凡)")

    # CRT 盒子分解 (AP 窗口形式): 区间占模数 85.7%, 每类 b 覆盖是
    # 等差数列窗口 {w_a + 4t mod N2 : 0 ≤ t < c_a} (非区间! 首版误判为全域)
    print("\n[3] CRT 盒子分解 (Z_4 × Z_89271, AP 窗口)")
    boxes = []   # (a, w, c): x≡a(mod4) 且 x%N2 ∈ {w+4t mod N2 : t<c}
    for a in range(N1):
        lo = A + ((a - A) % N1)
        hi = B - ((B - a) % N1)
        if lo > B or hi < lo:
            continue
        w = lo % N2
        c = (hi - lo) // N1 + 1
        boxes.append((a, w, c))
    for a, w, c in boxes:
        print(f"    a={a}: w={w}, 窗口长 c={c} (覆盖 {c}/{N2} = {c / N2:.1%})")
    # 双向穷举验证 (O(1) AP 成员判定: 4 在 Z_N2 中可逆, inv4 = pow(4,-1,N2))
    inv4 = pow(N1, -1, N2)
    def in_box(x):
        a, b = x % N1, x % N2
        for ba, w, c in boxes:
            if a != ba:
                continue
            t = ((b - w) * inv4) % N2
            if t < c:
                return True
        return False
    fwd = all(in_box(x) for x in range(A, B + 1))
    bwd = all((not in_box(x)) or (A <= x % DEN <= B) for x in range(DEN))
    print(f"    双向验证 (前向 {B - A + 1} 点 + 反向 {DEN} 点): "
          f"{'通过 ✓' if fwd and bwd else '失败 ✗'}")

    # 证书 1 的 13 速在盒子网格中的落点
    print("\n[4] 证书 1 · 13 速的 CRT 网格落点")
    all_in = True
    for v in SPEEDS:
        r = (NUM * v) % DEN
        a, b = r % N1, r % N2
        in_interval = A <= r <= B
        if not (in_interval and in_box(r)):
            all_in = False
        print(f"    v={v:5d}: r={r:6d} → (mod4, mod89271) = ({a}, {b}) "
              f"| 区间{'✓' if in_interval else '✗'} 盒子{'✓' if in_box(r) else '✗'}")
    print(f"    13 速全部通过: {'✓' if all_in else '✗'}")

    # 生成 Lean 普适解耦引理 (AP 窗口 ∃t 形式)
    print("\n[5] Lean 普适 CRT 解耦引理")
    disj = " ∨ ".join(
        f"(r % {N1} = {a} ∧ ∃ t : ℕ, t < {c} ∧ r % {N2} = ({w} + {N1} * t) % {N2})"
        for a, w, c in boxes)
    goal = (f"theorem lrc14_crt_interval_decoupling (r : ℕ) : "
            f"(({A} ≤ r % {DEN} ∧ r % {DEN} ≤ {B}) ↔ ({disj}))")
    open("research/crt_goal.txt", "w", encoding="utf-8").write(goal)
    print(f"    已写入 research/crt_goal.txt ({len(goal)} 字符) — omega 可闭合候选")


if __name__ == "__main__":
    main()

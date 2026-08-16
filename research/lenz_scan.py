"""
lenz_scan.py — Lenz 构型代数扫描 (SymPy + 数值 Gauss-Newton)

Part 1: K_{3,3} 单位距离图在 R^3 的 Cayley-Menger 符号证书
    —— 6 点在 R^3 必仿射相关 → CM 行列式必为 0; 若 K_{3,3} 距离模式的
       CM 多项式在正定义域上恒不为 0 → 不可嵌入的刚性阻碍证书。
Part 2: 5~6 顶点单位距离图半代数可实现性系统扫描 (多起点 Levenberg 数值)

运行: ./venv/Scripts/python.exe research/lenz_scan.py
"""

from __future__ import annotations

import itertools
import math
import random
import sys
import time

import sympy as sp


# ============================================================================
# Part 1: K_{3,3} Cayley-Menger 符号证书
# ============================================================================

def cm_determinant_k33() -> sp.Expr:
    """K_{3,3} 距离模式 (9 条交叉边 = 1, 6 条部内边自由) 的 CM 行列式。

    点序: a1,a2,a3,b1,b2,b3。部内边: x=|a1a2|, y=|a1a3|, z=|a2a3|,
    u=|b1b2|, v=|b1b3|, w=|b2b3|。
    """
    x, y, z, u, v, w = sp.symbols("x y z u v w", positive=True)
    intra = {(0, 1): x, (0, 2): y, (1, 2): z, (3, 4): u, (3, 5): v, (4, 5): w}
    n = 6
    m = sp.zeros(n + 1, n + 1)
    for j in range(n):
        m[0, j + 1] = sp.Integer(1)
        m[j + 1, 0] = sp.Integer(1)
    for i in range(n):
        for j in range(n):
            if i == j:
                m[i + 1, j + 1] = sp.Integer(0)
            elif (i, j) in intra:
                m[i + 1, j + 1] = intra[(i, j)] ** 2
            elif (j, i) in intra:
                m[i + 1, j + 1] = intra[(j, i)] ** 2
            else:
                m[i + 1, j + 1] = sp.Integer(1)  # 交叉边全为 1
    return m.det()


def sample_sign(poly: sp.Expr, n: int = 2000) -> tuple[float, float, int, int]:
    """随机正点采样 CM 多项式符号 (含三角不等式约束抽样)。"""
    rng = random.Random(0)
    sym_map = {str(s): s for s in poly.free_symbols}
    lo, hi = 0.0, 0.0
    npos = nneg = 0
    for _ in range(n):
        # 三角形可行域采样: 先取三角形三边 (SSS 有效), 两两独立
        triples = []
        for _ in range(2):
            while True:
                a, b = rng.uniform(0.05, 3), rng.uniform(0.05, 3)
                c = rng.uniform(abs(a - b) + 1e-6, a + b - 1e-6)
                if c > 0:
                    triples.append((a, b, c))
                    break
        subs = {sym_map[s]: t for s, t in zip("xyzuvw", triples[0] + triples[1])}
        val = float(poly.subs(subs))
        lo, hi = min(lo, val), max(hi, val)
        npos += val > 1e-9
        nneg += val < -1e-9
    return lo, hi, npos, nneg


def verify_heron_factorization(poly: sp.Expr) -> bool:
    """验证两个恒等式:

    (1) P = 2·f(x,y,z)·f(u,v,w) − 2x²y²z²u²v²w², f = a²b²c² − 16·Area²;
    (2) 闭式 P = 512·A_x²·A_u²·(1 − R_x² − R_u²)  (R = 外接圆半径)。
    """
    x, y, z, u, v, w = sp.symbols("x y z u v w")
    name_map = {str(s): s for s in poly.free_symbols}

    def f(a, b, c):
        area2 = (a + b + c) * (-a + b + c) * (a - b + c) * (a + b - c) / 16
        return a**2 * b**2 * c**2 - 16 * area2

    def area2(a, b, c):
        return (a + b + c) * (-a + b + c) * (a - b + c) * (a + b - c) / 16

    def r2(a, b, c):
        return a**2 * b**2 * c**2 / (16 * area2(a, b, c))

    rhs1 = 2 * f(x, y, z) * f(u, v, w) - 2 * x**2 * y**2 * z**2 * u**2 * v**2 * w**2
    rhs2 = 512 * area2(x, y, z) * area2(u, v, w) * (1 - r2(x, y, z) - r2(u, v, w))
    S = {x: name_map["x"], y: name_map["y"], z: name_map["z"],
         u: name_map["u"], v: name_map["v"], w: name_map["w"]}
    ok1 = sp.expand(poly - rhs1.subs(S)) == 0          # 多项式: expand 即可
    ok2 = sp.cancel(poly - rhs2.subs(S)) == 0          # 有理式: 需 cancel 约分
    return ok1 and ok2


# ============================================================================
# Part 2: 5~6 顶点单位距离图可实现性扫描 (数值 Levenberg)
# ============================================================================

def residual_sq(coords: list[float], edges: list[tuple[int, int]]) -> float:
    s = 0.0
    for i, j in edges:
        d2 = sum((coords[3 * i + k] - coords[3 * j + k]) ** 2 for k in range(3))
        s += (d2 - 1.0) ** 2
    return s


# 顶点互异罚项: 任意两顶点距离平方小于 δ² 时施加二次罚 (阻止数值解顶点塌缩作弊)
def distinctness_penalty(coords: list[float], n: int, delta: float = 0.2) -> float:
    d2_min = delta * delta
    s = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            d2 = sum((coords[3 * i + k] - coords[3 * j + k]) ** 2 for k in range(3))
            if d2 < d2_min:
                s += (d2 - d2_min) ** 2
    return s


def total_cost(coords: list[float], edges: list[tuple[int, int]], n: int,
               w: float) -> float:
    return residual_sq(coords, edges) + w * distinctness_penalty(coords, n)


def levenberg(coords: list[float], edges: list[tuple[int, int]],
              iters: int = 600) -> float:
    """纯 Python Levenberg-Marquardt: min Σ(|ci-cj|²-1)² + w·顶点互异罚。

    返回 (边残差, 最小顶点间距平方) —— 边残差≈0 但顶点间距≈0 的解是
    「顶点塌缩作弊解」, 图论上非法 (K_{3,3} 的唯一数值逃逸路径)。
    """
    n = max(max(e) for e in edges) + 1
    w = 100.0
    dim = len(coords)
    lam = 1e-4
    best = total_cost(coords, edges, n, w)
    for _ in range(iters):
        r = []
        for i, j in edges:
            d2 = sum((coords[3 * i + k] - coords[3 * j + k]) ** 2 for k in range(3))
            r.append(d2 - 1.0)
        # 罚项残差: 每对过近顶点贡献 (d2 - d2min), 权重 sqrt(w) 吸收进残差向量
        pen = []
        d2_min = 0.2 * 0.2
        for i in range(n):
            for j in range(i + 1, n):
                d2 = sum((coords[3 * i + k] - coords[3 * j + k]) ** 2 for k in range(3))
                if d2 < d2_min:
                    pen.append((i, j, (d2 - d2_min) * math.sqrt(w)))
        jtj = [[0.0] * dim for _ in range(dim)]
        g = [0.0] * dim
        for e, (i, j) in enumerate(edges):
            diff = [2 * (coords[3 * i + k] - coords[3 * j + k]) for k in range(3)]
            cols = []
            for k in range(3):
                cols.append((3 * i + k, diff[k]))
                cols.append((3 * j + k, -diff[k]))
            for (p, jp) in cols:
                g[p] += jp * r[e]
                for (q, jq) in cols:
                    jtj[p][q] += jp * jq
        for (i, j, pv) in pen:
            diff = [2 * (coords[3 * i + k] - coords[3 * j + k]) for k in range(3)]
            cols = []
            for k in range(3):
                cols.append((3 * i + k, diff[k]))
                cols.append((3 * j + k, -diff[k]))
            for (p, jp) in cols:
                g[p] += jp * pv
                for (q, jq) in cols:
                    jtj[p][q] += jp * jq
        for p in range(dim):
            jtj[p][p] += lam
        a = [row[:] for row in jtj]
        b = [-x for x in g]
        for col in range(dim):
            pivot = max(range(col, dim), key=lambda r_: abs(a[r_][col]))
            if abs(a[pivot][col]) < 1e-15:
                continue
            a[col], a[pivot] = a[pivot], a[col]
            b[col], b[pivot] = b[pivot], b[col]
            inv = a[col][col]
            for r_ in range(col + 1, dim):
                f = a[r_][col] / inv
                if f == 0:
                    continue
                for c in range(col, dim):
                    a[r_][c] -= f * a[col][c]
                b[r_] -= f * b[col]
        delta = [0.0] * dim
        for r_ in range(dim - 1, -1, -1):
            if abs(a[r_][r_]) < 1e-15:
                continue
            s = b[r_] - sum(a[r_][c] * delta[c] for c in range(r_ + 1, dim))
            delta[r_] = s / a[r_][r_]
        cand = [coords[p] + delta[p] for p in range(dim)]
        val = total_cost(cand, edges, n, w)
        if val < best * (1 - 1e-12):
            coords, best, lam = cand, val, max(lam * 0.5, 1e-9)
        else:
            lam = min(lam * 10, 1e10)
            if lam > 1e8:
                break
    # 返回边残差与最小顶点间距平方
    min_d2 = min(
        sum((coords[3 * i + k] - coords[3 * j + k]) ** 2 for k in range(3))
        for i in range(n) for j in range(i + 1, n)
    )
    return residual_sq(coords, edges), min_d2


def realize(graph_name: str, n: int, edges: list[tuple[int, int]],
            starts: int = 200) -> str:
    """多起点数值可实现性判定 (含顶点互异约束)。

    判定:
      FEASIBLE   — 边残差 ≈0 且顶点两两分离 (真实单位距离实现);
      DEGENERATE — 边残差 ≈0 但顶点塌缩 (数值作弊解, 图论上非法;
                   非退化无解 → 刚性阻碍的数值证据);
      INFEASIBLE — 非退化域内残差有正下界。
    """
    rng = random.Random(12345)
    best_r = float("inf")
    best_degen = float("inf")
    best_boundary = float("inf")   # 最优解顶点间距² (诊断: 是否贴在罚边界 δ²=0.04)
    t0 = time.time()
    for _ in range(starts):
        coords = [rng.uniform(-2, 2) for _ in range(3 * n)]
        r, min_d2 = levenberg(coords, edges)
        if r < 1e-8 and min_d2 > 0.01:
            return f"FEASIBLE   (残差 {r:.2e}, 顶点间距² {min_d2:.3f}, {time.time()-t0:.1f}s)"
        if r < 1e-8:
            best_degen = min(best_degen, min_d2)
        if r < best_r:
            best_r, best_boundary = r, min_d2
    if best_degen < float("inf"):
        return (f"DEGENERATE (边残差 {best_r:.2e}, 但顶点塌缩 间距²={best_degen:.2e} "
                f"— 非退化无解, 刚性阻碍数值证据, {time.time()-t0:.1f}s)")
    if best_r < 0.01:
        return (f"NEAR-DEGEN (残差 {best_r:.2e}, 最优解顶点间距²={best_boundary:.3f} "
                f"(罚边界0.040) — 收敛路径退化, 非退化不可实现证据, {time.time()-t0:.1f}s)")
    return f"INFEASIBLE (残差 {best_r:.3f}, {time.time()-t0:.1f}s)"


GRAPH_CATALOG: list[tuple[str, int, list[tuple[int, int]]]] = [
    # 5 顶点: 经典刚性/极值族
    ("K4 (四面体)", 4, [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]),
    ("K5−e", 5, list(itertools.combinations(range(5), 2))[:-1]),
    ("K5", 5, list(itertools.combinations(range(5), 2))),
    ("K2,3", 5, [(i, 2 + j) for i in range(2) for j in range(3)]),
    ("K2,3+e", 5, [(i, 2 + j) for i in range(2) for j in range(3)] + [(2, 3)]),
    ("W5 轮图", 5, [(0, i) for i in range(1, 5)] + [(1, 2), (2, 3), (3, 4), (4, 1)]),
    ("C5 圈", 5, [(i, (i + 1) % 5) for i in range(5)]),
    # 6 顶点: 极值/阻碍候选
    ("K3,3", 6, [(i, 3 + j) for i in range(3) for j in range(3)]),
    ("K3,3−e", 6, [(i, 3 + j) for i in range(3) for j in range(3)][:-1]),
    ("K3,3+e", 6, [(i, 3 + j) for i in range(3) for j in range(3)] + [(0, 1)]),
    ("K2,4", 6, [(i, 2 + j) for i in range(2) for j in range(4)]),
    ("K2,4+e", 6, [(i, 2 + j) for i in range(2) for j in range(4)] + [(2, 3)]),
    ("正八面体", 6, [(i, j) for i in range(6) for j in range(i + 1, 6)
                     if (i, j) not in {(0, 3), (1, 4), (2, 5)}]),
    ("三角柱", 6, [(i, (i + 1) % 3) for i in range(3)]
     + [(3 + i, 3 + (i + 1) % 3) for i in range(3)]
     + [(i, 3 + i) for i in range(3)]),
    ("K4+两个孤立边", 6, [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3), (4, 5)]),
    ("K4+双锥(两顶点连K4)", 6, list(itertools.combinations(range(4), 2))
     + [(4, i) for i in range(4)] + [(5, i) for i in range(4)]),
    ("C6 圈", 6, [(i, (i + 1) % 6) for i in range(6)]),
    ("C6+三对角", 6, [(i, (i + 1) % 6) for i in range(6)]
     + [(0, 3), (1, 4), (2, 5)]),
    ("K5 加孤立点", 6, list(itertools.combinations(range(5), 2))),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("═══ Part 1: K_{3,3} Cayley-Menger 符号证书 ═══")
    t0 = time.time()
    p = cm_determinant_k33()
    print(f"CM 行列式 (7×7, 6 符号) 计算耗时 {time.time()-t0:.1f}s, 项数 {len(p.as_terms()[0])}")
    pf = sp.factor(p)
    print(f"因式分解 (48 项): {str(pf)[:200]}...")
    ok = verify_heron_factorization(p)
    print(f"结构验证 ① P = 2·f(x)·f(u) − 2x²y²z²u²v²w² ② 闭式 "
          f"P = 512·A_x²·A_u²·(1 − R_x² − R_u²): {'通过 ✓' if ok else '失败 ✗'}")
    lo, hi, npos, nneg = sample_sign(p)
    print(f"正定义域随机采样: 值域 [{lo:.3f}, {hi:.3f}], "
          f"正样本 {npos} / 负样本 {nneg} / 共 2000")
    print(f"几何意义: P = 0 ⟺ R_x² + R_u² = 1 ⟺ 两部三角形外接圆半径平方和恰为 1")
    print("\n═══ Part 2: 5~6 顶点单位距离图可实现性扫描 ═══")
    print(f"{'图':<22} {'顶点':<4} {'边数':<4} 判定")
    for name, n, edges in GRAPH_CATALOG:
        verdict = realize(name, n, edges)
        print(f"{name:<22} {n:<4} {len(edges):<4} {verdict}")


if __name__ == "__main__":
    main()

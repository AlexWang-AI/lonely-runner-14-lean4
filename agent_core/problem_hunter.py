"""
problem_hunter.py — 顶刊级命题猎人 (Problem Hunter) · Crouzeix 级捕猎范围

狩猎流水线 (上游于 Prover 状态机):
  1. arXiv 监听雷达: 轮询 arXiv 官方 API — 分类白名单 (含 math.FA/RA/OC 连续谱系)
     + 高阶探测关键词 (Matrix inequality / Operator norm / Sum of Squares /
     Semidefinite), 去重后产出候选论文池;
  2. Filter Agent 初筛 (deepseek-v4-flash): 按「可代数化」放行规则裁决 —
     - 放行: 矩阵/算子范数界限、正定多项式极值、半代数集极值, 且具备通过
       平方和松弛 (SOS) / 迹恒等式 (Trace identities) / 行列式恒等式 /
       特征多项式 降维为有限维代数系统的潜力;
     - 拒绝: 纳维-斯托克斯式纯 PDE 解析解、依赖无限维拓扑且无法代数化的命题、
       无明确数学断言的纯数值实验;
  3. 算力体检 (SymPy dry-run): 验证命题能否写出小规模 (3×3/4×4) 矩阵的行列式 /
     迹 / 特征多项式 / SOS 平方和 符号表达式 (术语数、总度数、耗时统计);
  4. 产出候选清单 (JSON) — attackable 候选可直接交付 main_loop 点火。

安全设计: LLM 只输出【声明式探针规格】(kind/size/structure), 符号矩阵由本模块
自行构建 — 绝不执行 LLM 生成的任意代码。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import sympy as sp

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 复用查新哨兵的 arXiv 抓取 (证书降级 + 重试) 与 LLM 基座 (flash + 指数退避)
from agent_core.scout_agent import LiteratureScoutAgent, ScoutPaper

# ---------------------------------------------------------------------------
# 雷达配置 (升级版: 连续谱系分类 + 高阶关键词)
# ---------------------------------------------------------------------------

# 原有离散谱系 + 新增连续/代数谱系 (Crouzeix 级捕猎范围)
HUNT_CATEGORIES: Final[tuple[str, ...]] = (
    "math.NT", "math.CO", "math.CA", "math.MG",   # 原有: 离散/组合/经典分析/度量几何
    "math.FA", "math.RA", "math.OC",              # 新增: 泛函分析 / 环与代数 / 优化控制
)

# 高阶探测关键词 (矩阵极值 / 多项式代数化通道; 含 Kakeya 型离散化)
HIGH_ORDER_KEYWORDS: Final[tuple[str, ...]] = (
    "matrix inequality",
    "operator norm",
    "sum of squares",
    "semidefinite",
    "eigenvalue inequality",
    "Kakeya",
)

_POLITE_DELAY: Final[float] = 3.0        # arXiv 礼貌间隔
_RADAR_PER_CAT: Final[int] = 3           # 每分类最新预印本数
_RADAR_PER_KEYWORD: Final[int] = 3       # 每关键词命中数
_PROBE_TIME_BUDGET: Final[float] = 20.0  # SymPy 体检单题时间预算 (秒)
_PROBE_TERM_CAP: Final[int] = 20000      # 符号表达式术语数上限 (超过判不可攻)

_JSON_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FilterVerdict:
    """Filter Agent 初筛裁决。"""

    verdict: str                      # PASS / REJECT
    algebraic_route: str              # SOS / trace / det / charpoly / none
    reduction_plan: str
    score: int                        # 可攻性 1~10
    reason: str
    candidate_theorem: str            # 从论文中提炼的明确断言 (供 main_loop 点火)
    probe: dict | None                # 声明式探针规格 (kind/size/structure)


@dataclass(frozen=True)
class ProbeResult:
    """SymPy 算力体检结果。"""

    ok: bool
    kind: str
    size: int
    structure: str
    term_count: int
    total_degree: int | None
    elapsed: float
    sample: str


@dataclass(frozen=True)
class Candidate:
    """狩猎产出: 一篇候选论文 + 完整评估链。"""

    paper: ScoutPaper
    filter: FilterVerdict
    probe: ProbeResult | None
    attackable: bool

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.paper.entry_id,
            "title": self.paper.title,
            "published": self.paper.published,
            "url": self.paper.url,
            "filter": self.filter.__dict__,
            "probe": self.probe.__dict__ if self.probe else None,
            "attackable": self.attackable,
        }


# ---------------------------------------------------------------------------
# Filter Agent 系统提示词 (升级版放行规则)
# ---------------------------------------------------------------------------

_FILTER_SYSTEM_PROMPT: Final[str] = (
    "你是顶级期刊命题猎人 (Problem Hunter) 的初筛 Filter Agent。评估一篇 arXiv 论文"
    "对「AI 数学研究所全自动定理证明流水线 (Lean 4 + 代数消元)」的可攻性。\n"
    "\n"
    "【放行规则】(Crouzeix 级 — 表面泛函分析、实则代数可降维的神级命题):\n"
    "1. 命题属于「矩阵/算子范数界限」「正定多项式极值」「半代数集极值」等范畴;\n"
    "2. 且具备通过 平方和松弛 (SOS relaxation) / 迹恒等式 (Trace identities) / "
    "矩阵行列式恒等式 / 特征多项式 降维为有限维代数系统的潜力;\n"
    "3. 论文含明确可形式化断言 (定理/猜想/不等式) 是加分项。\n"
    "   满足 1+2 即 PASS — 不因命题是连续/分析问题而一刀切拒绝!\n"
    "\n"
    "【拒绝规则】(坚决):\n"
    "1. 纳维-斯托克斯式纯 PDE 流体力学解析解;\n"
    "2. 依赖无限维拓扑/泛函结构且无法代数化的命题 (一般 Banach 空间不动点、"
    "C*-代数同构分类等);\n"
    "3. 纯数值实验、无明确数学断言的论文。\n"
    "\n"
    "输出格式【严格要求】为 JSON 对象, 不要输出 JSON 以外的任何内容:\n"
    '{"verdict": "PASS" 或 "REJECT", '
    '"algebraic_route": "SOS" 或 "trace" 或 "det" 或 "charpoly" 或 "none", '
    '"reduction_plan": "代数降维路线 (2-3 句)", "score": 1到10的整数, '
    '"reason": "裁决理由 (≤3 句)", '
    '"candidate_theorem": "从论文提炼的明确数学断言 (Lean 命题化蓝本, 若 REJECT 填 null)", '
    '"probe": {"kind": "det" 或 "trace" 或 "charpoly" 或 "sos", '
    '"size": 3 或 4, "structure": "symmetric" 或 "generic" 或 "block2x2"}}'
)


# ---------------------------------------------------------------------------
# 组件: Problem Hunter
# ---------------------------------------------------------------------------

class ProblemHunter:
    """顶刊级命题猎人 — arXiv 雷达 → LLM 初筛 → SymPy 算力体检。"""

    # 雷达通道顺序: 新增连续谱系优先 (FA/RA/OC + 高阶关键词), 原有离散谱系殿后
    _CATEGORY_ORDER: Final[tuple[str, ...]] = ("math.FA", "math.RA", "math.OC",
                                                "math.NT", "math.CO", "math.CA", "math.MG")

    def __init__(self, limit: int = 6) -> None:
        self.limit = limit
        # 复用 ScoutAgent 实例: 提供 arXiv 抓取 (证书降级+重试) 与 flash 调用基座
        self._scout = LiteratureScoutAgent(
            categories=HUNT_CATEGORIES,
            max_results_per_query=max(_RADAR_PER_CAT, _RADAR_PER_KEYWORD),
        )

    # ---------------- 1. arXiv 监听雷达 ----------------

    def _radar_sweep(self) -> list[ScoutPaper]:
        """分类白名单 + 高阶关键词双通道扫描, 分层轮转去重 (新增谱系通道优先)。"""
        channels: list[list[ScoutPaper]] = []
        for cat in self._CATEGORY_ORDER:
            channels.append(self._radar_channel(f"分类雷达 cat:{cat}", f"cat:{cat}"))
        for kw in HIGH_ORDER_KEYWORDS:
            q = (f'all:"{kw}" AND '
                 f'(cat:math.FA OR cat:math.RA OR cat:math.OC)')
            channels.append(self._radar_channel(f"关键词雷达 all:{kw!r}", q))

        # 分层轮转: 每通道各取一篇循环, 保证新增谱系进入初筛池
        seen: set[str] = set()
        pool: list[ScoutPaper] = []
        idx = 0
        while True:
            progressed = False
            for ch in channels:
                if idx < len(ch):
                    progressed = True
                    if ch[idx].entry_id not in seen:
                        seen.add(ch[idx].entry_id)
                        pool.append(ch[idx])
            idx += 1
            if not progressed:
                break
        return pool

    def _radar_channel(self, label: str, query: str) -> list[ScoutPaper]:
        """单通道抓取 (失败不毁全局, 礼貌间隔)。"""
        try:
            hits = self._scout._fetch_arxiv(query)
        except Exception as exc:  # noqa: BLE001
            print(f"[RADAR] {label}... 失败: {type(exc).__name__}")
            return []
        hits = sorted(hits, key=lambda p: p.published, reverse=True)[:_RADAR_PER_CAT]
        print(f"[RADAR] {label}... 命中 {len(hits)}")
        time.sleep(_POLITE_DELAY)
        return hits

    # ---------------- 2. Filter Agent 初筛 ----------------

    async def _filter(self, paper: ScoutPaper) -> FilterVerdict:
        user_prompt = (
            "【论文标题】\n"
            f"{paper.title}\n"
            "\n"
            "【摘要】\n"
            f"{paper.summary[:800]}\n"
            "\n"
            f"【主分类】{paper.primary_category} | 【日期】{paper.published}\n"
            "\n"
            "请按放行规则输出 JSON 裁决。"
        )
        raw = await self._scout._complete(
            _FILTER_SYSTEM_PROMPT, user_prompt, 2048, "Problem Hunter 初筛"
        )
        match = _JSON_BLOCK_PATTERN.search(raw)
        if not match:
            return FilterVerdict(
                verdict="REJECT", algebraic_route="none", reduction_plan="",
                score=1, reason=f"Filter 输出非 JSON: {raw[:120]!r}", candidate_theorem="",
                probe=None,
            )
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return FilterVerdict(
                verdict="REJECT", algebraic_route="none", reduction_plan="",
                score=1, reason=f"Filter JSON 解析失败: {exc}", candidate_theorem="",
                probe=None,
            )
        verdict = str(data.get("verdict") or "REJECT").strip().upper()
        if verdict not in ("PASS", "REJECT"):
            verdict = "REJECT"
        try:
            score = max(1, min(10, int(data.get("score", 1))))
        except (TypeError, ValueError):
            score = 1
        probe_raw = data.get("probe")
        probe = probe_raw if isinstance(probe_raw, dict) else None
        return FilterVerdict(
            verdict=verdict,
            algebraic_route=str(data.get("algebraic_route") or "none").strip(),
            reduction_plan=str(data.get("reduction_plan") or "").strip(),
            score=score,
            reason=str(data.get("reason") or "").strip(),
            candidate_theorem=str(data.get("candidate_theorem") or "").strip(),
            probe=probe,
        )

    # ---------------- 3. SymPy 算力体检 (Dry-run Check) ----------------

    @staticmethod
    def _build_symbolic_matrix(size: int, structure: str) -> sp.Matrix:
        """按声明式规格构建小规模符号矩阵 (LLM 规格 → 本模块构建, 绝不 eval)。"""
        n = min(max(size, 2), 4)
        m = sp.zeros(n, n)
        if structure == "generic":
            for i in range(n):
                for j in range(n):
                    m[i, j] = sp.Symbol(f"g{i}{j}")
        elif structure == "block2x2" and n >= 2:
            half = n // 2
            for i in range(n):
                for j in range(n):
                    m[i, j] = sp.Symbol(f"b{i}{j}")
        else:  # symmetric (默认)
            for i in range(n):
                for j in range(i, n):
                    m[i, j] = m[j, i] = sp.Symbol(f"s{i}{j}")
        return m

    @staticmethod
    def _build_sos_form(nvars: int = 2) -> sp.Expr:
        """构造 SOS 演示表达式: 3 个泛二次型的平方和 (4 次多项式, 可展开)。"""
        gens = [sp.Symbol(f"v{i}") for i in range(nvars)]
        total = sp.Integer(0)
        for k in range(3):
            quad = sum(
                sp.Symbol(f"c{k}{i}{j}") * g1 * g2
                for i, g1 in enumerate(gens) for j, g2 in enumerate(gens) if i <= j
            )
            total += quad ** 2
        return sp.expand(total)

    def _sympy_dry_run(self, spec: dict | None) -> ProbeResult:
        """算力体检: 能否写出命题对应的小规模矩阵 det/trace/charpoly/SOS 符号表达式。"""
        kind = str((spec or {}).get("kind") or "charpoly").strip().lower()
        size = min(max(int((spec or {}).get("size") or 3), 2), 4)
        structure = str((spec or {}).get("structure") or "symmetric").strip().lower()
        if kind not in ("det", "trace", "charpoly", "sos"):
            kind = "charpoly"

        def work() -> ProbeResult:
            t0 = time.time()
            display_size, display_structure = size, structure
            try:
                if kind == "sos":
                    # SOS 探针: 3 个泛二次型的平方和 (2 变量四次多项式)
                    expr = self._build_sos_form(2)
                    display_size, display_structure = 2, "sos_quadratic"
                else:
                    m = self._build_symbolic_matrix(size, structure)
                    if kind == "det":
                        expr = m.det()
                    elif kind == "trace":
                        expr = m.trace()
                    else:
                        expr = m.charpoly(sp.Symbol("t")).as_expr()
                term_count = len(expr.as_terms()[0]) if hasattr(expr, "as_terms") else 1
                degree = None
                try:
                    if kind == "sos":
                        # 度数只统计主变量 (v0, v1), 排除系数符号
                        degree = sp.Poly(expr, sp.Symbol("v0"), sp.Symbol("v1")).total_degree()
                    else:
                        degree = sp.Poly(expr).total_degree()
                except Exception:  # noqa: BLE001
                    pass
                elapsed = time.time() - t0
                if term_count > _PROBE_TERM_CAP:
                    return ProbeResult(ok=False, kind=kind, size=display_size,
                                       structure=display_structure,
                                       term_count=term_count, total_degree=degree,
                                       elapsed=round(elapsed, 2),
                                       sample=f"术语爆炸 ({term_count} 项) — 判定不可攻")
                return ProbeResult(ok=True, kind=kind, size=display_size,
                                   structure=display_structure,
                                   term_count=term_count, total_degree=degree,
                                   elapsed=round(elapsed, 2), sample=str(expr)[:80])
            except Exception as exc:  # noqa: BLE001
                return ProbeResult(ok=False, kind=kind, size=display_size,
                                   structure=display_structure,
                                   term_count=0, total_degree=None,
                                   elapsed=round(time.time() - t0, 2),
                                   sample=f"符号构建失败: {type(exc).__name__} {str(exc)[:80]}")

        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                return pool.submit(work).result(timeout=_PROBE_TIME_BUDGET)
            except FutureTimeout:
                return ProbeResult(ok=False, kind=kind, size=size, structure=structure,
                                   term_count=0, total_degree=None,
                                   elapsed=_PROBE_TIME_BUDGET, sample="超时 — 判定不可攻")

    # ---------------- 一站式狩猎入口 ----------------

    async def hunt(self, out: Path | None = None) -> list[Candidate]:
        """雷达扫描 → 初筛 → 体检 → 候选清单 (可选落盘 JSON)。"""
        print("═══ Problem Hunter 狩猎启动 (Crouzeix 级捕猎范围) ═══")
        papers = await asyncio.to_thread(self._radar_sweep)
        print(f"[HUNT] 雷达命中 {len(papers)} 篇, 初筛前 {min(self.limit, len(papers))} 篇")
        candidates: list[Candidate] = []
        for paper in papers[: self.limit]:
            filt = await self._filter(paper)
            probe = None
            if filt.verdict == "PASS":
                # Filter 输出携带声明式探针规格; 缺失时按 algebraic_route 映射默认规格
                probe_spec = filt.probe or {
                    "kind": filt.algebraic_route
                    if filt.algebraic_route in ("det", "trace", "charpoly", "sos")
                    else "charpoly",
                    "size": 4 if filt.algebraic_route == "trace" else 3,
                    "structure": "symmetric",
                }
                probe = await asyncio.to_thread(self._sympy_dry_run, probe_spec)
            attackable = filt.verdict == "PASS" and (probe is not None and probe.ok)
            candidates.append(Candidate(paper=paper, filter=filt, probe=probe,
                                        attackable=attackable))
            tag = "🟢" if attackable else ("🟡" if filt.verdict == "PASS" else "🔴")
            print(f"{tag} {paper.title[:70]} | {filt.verdict} "
                  f"(route={filt.algebraic_route}, score={filt.score})")
            if probe:
                print(f"   🧪 体检: {probe.kind} {probe.size}×{probe.size} "
                      f"{probe.structure} → 术语 {probe.term_count}, "
                      f"度数 {probe.total_degree}, {probe.elapsed}s | {probe.sample[:60]}")
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps([c.to_dict() for c in candidates], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[HUNT] 候选清单已落盘: {out}")
        n_attack = sum(1 for c in candidates if c.attackable)
        print(f"[HUNT] 狩猎完成: {len(candidates)} 篇初审, "
              f"PASS {sum(1 for c in candidates if c.filter.verdict == 'PASS')} 篇, "
              f"可攻 {n_attack} 篇")
        return candidates


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Problem Hunter · arXiv 雷达 → LLM 初筛 → SymPy 算力体检 (Crouzeix 级范围)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit", type=int, default=6, help="初筛论文数 (默认 6)")
    parser.add_argument("--out", type=str, default=None,
                        help="候选清单 JSON 输出路径 (默认不落盘)")
    args = parser.parse_args()
    hunter = ProblemHunter(limit=args.limit)
    out = Path(args.out) if args.out else None
    asyncio.run(hunter.hunt(out=out))


if __name__ == "__main__":
    main()

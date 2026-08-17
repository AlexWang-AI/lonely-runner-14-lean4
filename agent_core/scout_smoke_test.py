"""
scout_smoke_test.py — 微型冒烟测试 (ScoutAgent)

Part 1: 检索源连通性探测 — arXiv 官方 API 与 OpenAlex 降级源逐一实测
        (本机位于中国大陆, arXiv 直连预期不可达 → 查新应自动降级 OpenAlex);
Part 2: 完整查新流程 — 对「√2 无理数」(公元前即知的经典结果) 跑 scout(),
        预期裁决 DUPLICATE_KNOWN 触发查新熔断; 裁决质量属软检查, 只告警不失败。

运行: ./venv/Scripts/python.exe agent_core/scout_smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.scout_agent import LiteratureScoutAgent, ScoutSearchError


def probe_connectivity() -> None:
    """Part 1: 检索源连通性探测 (arXiv 被墙属预期, OpenAlex 必须可达)。"""
    print("═══ Part 1: 检索源连通性探测 ═══")
    scout = LiteratureScoutAgent()
    try:
        papers = scout._fetch_arxiv('all:"irrationality" AND cat:math.NT')
        print(f"[CONN] arXiv 官方 API: OK 可达 ({len(papers)} 篇命中)")
    except ScoutSearchError as exc:
        print(f"[CONN] arXiv 官方 API: 不可达 ({exc})")
        print("       └─ 本机网络受限 (预期内), 查新将自动降级 OpenAlex")
    try:
        papers = scout._fetch_openalex('all:"irrationality of square root of two"')
        print(f"[CONN] OpenAlex 降级源: OK 可达 ({len(papers)} 篇命中)")
    except ScoutSearchError as exc:
        print(f"[CONN] OpenAlex 降级源: 不可达 ({exc}) — 查新闸口将失败关闭!")
        sys.exit(1)


async def run_full_flow() -> None:
    """Part 2: 完整查新流程 (经典已知结果, 预期 DUPLICATE_KNOWN)。"""
    print("\n═══ Part 2: 完整查新流程 (√2 无理数, 预期 DUPLICATE_KNOWN) ═══")
    scout = LiteratureScoutAgent()
    report = await scout.scout(
        "2 的平方根是无理数 (√2 不是有理数, 经典结果)",
        "theorem sqrt2_irrational : Irrational (Real.sqrt 2)",
    )
    print(report.to_markdown())
    verdict = report.verdict.verdict
    print(f"\n[SMOKE] 最终裁决: {verdict} (novelty_score {report.verdict.novelty_score}/10)")
    print(f"[SMOKE] 命中文献: {len(report.papers)} 篇 | 检索源告警: {len(report.warnings)} 条")
    if verdict == "DUPLICATE_KNOWN":
        print("[SMOKE] ✅ 符合预期: 查新闸口正确识别教科书级已知结果 (将触发零烧算力熔断)")
    else:
        print(f"[SMOKE] ⚠️  预期 DUPLICATE_KNOWN, 实际 {verdict} — 裁决质量请人工复核")
    if not report.papers and not report.warnings:
        print("[SMOKE] ⚠️  检索零命中且无降级告警 — 检索链路可疑, 请人工检查")


def main() -> None:
    os.system("")  # 启用 Windows 控制台 ANSI 转义
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    probe_connectivity()
    asyncio.run(run_full_flow())
    print("\n[SMOKE] 冒烟测试结束")


if __name__ == "__main__":
    main()

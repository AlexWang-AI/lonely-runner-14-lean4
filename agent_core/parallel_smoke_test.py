"""
parallel_smoke_test.py — V3 并行引擎闭环冒烟测试 (全伪造注入, 零 API/Lean 消耗)

场景 1 (斩获路径): A 路返回无 sorry 完整证明, B/C 战损 → 引擎应立即斩获、
                  清场其余支线、落盘 outputs/。
场景 2 (全溃败路径): 三路皆战损 → 黑石碑唤醒产出 Fingerprint → 负样本墙
                  刷新 → 回合迭代直至耗尽。
运行: ./venv/Scripts/python.exe -X utf8 agent_core/parallel_smoke_test.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent_core.failure_analyst import Fingerprint
from agent_core.parallel_loop import ParallelProvingPipeline

GOAL = "theorem two_plus_two : 2 + 2 = 4"
WIN_CODE = "theorem two_plus_two : 2 + 2 = 4 := by rfl"
FAIL_CODE = "theorem two_plus_two : 2 + 2 = 4 := by sorry"
_TAG = re.compile(r"<lean_code>(.*)</lean_code>", re.DOTALL)


class FakeExplorer:
    """伪造推进槽: 按 explorer 名与场景回传预设输出。"""

    def __init__(self, name: str, tag: str, win_mode: bool):
        self.name = name
        self.strategy_tag = tag
        self.win_mode = win_mode
        self.failure_log: list[str] = []
        self.derive_calls = 0

    async def derive(self, goal: str, context: str, fingerprints: list[str]) -> str:
        self.derive_calls += 1
        code = WIN_CODE if self.win_mode else FAIL_CODE
        return f"推理过程略\n<lean_code>{code}</lean_code>"

    def record_failure(self, summary: str) -> None:
        self.failure_log.append(summary)


class FakeValidator:
    """伪造裁判: A 路代码判成功, 其余判失败 (与场景解耦由 win_mode 控制)。"""

    def __init__(self, win_mode: bool):
        self.win_mode = win_mode
        self.use_server = False
        self.verify_calls = 0

    def warmup(self) -> None:
        pass

    def extract_lean_code(self, raw: str) -> str:
        m = _TAG.search(raw)
        if not m:
            raise ValueError("no tag")
        return m.group(1).strip()

    def verify_code(self, code: str, timeout: float) -> dict:
        self.verify_calls += 1
        if self.win_mode:
            return {"status": "success", "message": "验证通过 ✅ (伪造裁判)", "code": code}
        return {"status": "error", "message": f"编译失败 ❌ (伪造裁判): 测试报错栈 {code[:20]}"}


class FakeAnalyst:
    """伪造黑石碑: 回传固定 Fingerprint, 并记录会诊次数。"""

    def __init__(self):
        self.calls = 0
        self.last_casualties: list = []

    async def analyze(self, goal: str, casualties) -> Fingerprint:
        self.calls += 1
        self.last_casualties = list(casualties)
        return Fingerprint(rule="测试禁忌: 禁止 sorry 占位路线",
                           severity=5, affected_strategies=("all",))


def _build_pipeline(win_mode: bool, max_rounds: int) -> ParallelProvingPipeline:
    explorers = [
        FakeExplorer("Explorer-A", "algebraic", win_mode=win_mode),
        FakeExplorer("Explorer-B", "geometric", win_mode=False),
        FakeExplorer("Explorer-C", "combinatorial", win_mode=False),
    ]
    validators = {e.name: FakeValidator(win_mode=(e.name == "Explorer-A" and win_mode))
                  for e in explorers}
    return ParallelProvingPipeline(
        max_rounds=max_rounds,
        explorers=explorers,
        validators=validators,
        analyst=FakeAnalyst(),
        use_server=False,
    )


async def scenario1() -> None:
    """斩获路径: A 路一击必杀, 其余支线清场。"""
    print("═══ 场景 1: 斩获路径 (A 路无 sorry 证明) ═══")
    pipeline = _build_pipeline(win_mode=True, max_rounds=3)
    report = await pipeline.run(GOAL)
    assert report.success, "场景 1 应斩获"
    assert report.winner == "Explorer-A", f"胜者应为 A, 实际 {report.winner}"
    assert report.rounds_used == 1
    assert report.output_file is not None and report.output_file.exists()
    assert pipeline.analyst.calls == 0, "斩获路径不得唤醒黑石碑"
    print(f"✅ 场景 1 通过: 胜者 {report.winner}, 1 回合斩获, 已落盘 {report.output_file}")


async def scenario2() -> None:
    """全溃败路径: 黑石碑唤醒 → Fingerprint 墙 → 轮数耗尽。"""
    print("\n═══ 场景 2: 全溃败路径 (三路皆战损) ═══")
    pipeline = _build_pipeline(win_mode=False, max_rounds=2)
    report = await pipeline.run(GOAL)
    assert not report.success, "场景 2 应耗尽"
    assert report.rounds_used == 2
    assert pipeline.analyst.calls == 2, f"黑石碑应唤醒 2 次, 实际 {pipeline.analyst.calls}"
    assert len(report.fingerprints) == 2
    assert pipeline.analyst.last_casualties and len(pipeline.analyst.last_casualties) == 3
    for e in pipeline.explorers:
        assert len(e.failure_log) == 2, f"{e.name} 应有 2 条战损记录"
    print(f"✅ 场景 2 通过: 2 回合耗尽, 黑石碑唤醒 {pipeline.analyst.calls} 次, "
          f"Fingerprint 墙 {len(report.fingerprints)} 条, 三路战损日志各 2 条")


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    await scenario1()
    await scenario2()
    print("\n[SMOKE] V3 并行引擎闭环测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())

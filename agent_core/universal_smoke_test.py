"""universal_smoke_test.py — V5 引擎闭环冒烟测试 (全伪造, 零 API 消耗)"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_core.universal_loop import UniversalProvingLoop
from agent_core.universal_explorers import UNIVERSAL_GOAL

_TAG = re.compile(r"<lean_code>(.*)</lean_code>", re.DOTALL)
CAPTURE_CODE = ("def dist_torus (x : ℝ) : ℝ := |x - round x|\n\n"
                "theorem lonely_runner_conjecture_universal (k : ℕ) (hk : k ≥ 1) "
                "(v : Fin k → ℕ+) (h_inj : Function.Injective v) : "
                "∃ (t : ℝ), ∀ (i : Fin k), dist_torus ((v i : ℝ) * t) ≥ "
                "(1 : ℝ) / ((k : ℝ) + 1) := by trivial")
DEGEN_CODE = ("theorem lonely_runner_conjecture_universal (k : ℕ) (hk : k ≥ 1) "
              "(v : Fin k → ℕ+) (h_inj : Function.Injective v) : "
              "∃ (t : ℝ), ∀ (i : Fin k), dist_torus ((v i : ℝ) * t) ≥ "
              "(1 : ℝ) / ((k : ℝ) + 1) := by\n"
              "  have hsp : v 0 = 1 := by sorry\n  sorry")


class FakeExplorer:
    def __init__(self, name, tag, mode):
        self.name, self.strategy_tag, self.mode = name, tag, mode
        self.failure_log: list[str] = []

    async def derive(self, goal, context, fingerprints):
        code = CAPTURE_CODE if self.mode == "capture" else \
            (DEGEN_CODE if self.mode == "degen" else CAPTURE_CODE.replace(
                "by sorry", "by sorry"))
        return f"推理略\n<lean_code>{code}</lean_code>"

    def record_failure(self, summary):
        self.failure_log.append(summary)


class FakeValidator:
    def __init__(self, accept_names):
        self.accept_names = accept_names
        self.use_server = False

    def warmup(self):
        pass

    def extract_lean_code(self, raw):
        return _TAG.search(raw).group(1)

    def verify_code(self, code, timeout):
        if self.accept_names and "hsp" not in code:
            return {"status": "success", "message": "OK", "code": code}
        return {"status": "error", "message": "test error"}


async def scenario_degenerate() -> None:
    """退化指纹路径: 含 v 0 = 1 的代码必须被黑石碑 V5 打指纹。"""
    print("═══ 冒烟 1: 退化指纹路径 ═══")
    exps = [FakeExplorer("Explorer-Harmonic", "harmonic", "degen"),
            FakeExplorer("Explorer-Entropy", "entropy", "degen"),
            FakeExplorer("Explorer-Spectral", "spectral", "degen"),
            FakeExplorer("Explorer-RealAlgebra", "realalgebra", "degen")]
    vals = {e.name: FakeValidator(False) for e in exps}
    loop = UniversalProvingLoop(max_rounds=2, explorers=exps, validators=vals)
    report = await loop.run()
    assert not report.success
    assert any("退化指纹" in f for f in report.fingerprints), report.fingerprints
    print("✅ 退化指纹路径通过:", report.fingerprints[0][:60], "...")


async def scenario_capture() -> None:
    """斩获路径: 一路 0-sorry 全称证明 → 立即斩获落盘。"""
    print("\n═══ 冒烟 2: 斩获路径 ═══")
    exps = [FakeExplorer("Explorer-Harmonic", "harmonic", "capture"),
            FakeExplorer("Explorer-Entropy", "entropy", "degen"),
            FakeExplorer("Explorer-Spectral", "spectral", "degen"),
            FakeExplorer("Explorer-RealAlgebra", "realalgebra", "degen")]
    vals = {e.name: FakeValidator(True) for e in exps}
    loop = UniversalProvingLoop(max_rounds=2, explorers=exps, validators=vals)
    report = await loop.run()
    assert report.success and report.winner == "Explorer-Harmonic"
    assert report.output_file and report.output_file.exists()
    print(f"✅ 斩获路径通过: 胜者 {report.winner}, 落盘 {report.output_file.name}")


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    await scenario_degenerate()
    await scenario_capture()
    print("\n[SMOKE] V5 全称量词引擎闭环测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())

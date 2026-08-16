"""launch_cert_v3.py — 以全量 prelude 注入三路验证器, 点火 V3 攻坚证书 1。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_core.lean_verifier import LeanValidator
from agent_core.parallel_loop import ParallelProvingPipeline

GOAL = (_ROOT / "research" / "cert1_goal.txt").read_text(encoding="utf-8")


def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    validators = {
        name: LeanValidator(worker_id=name,
                            server_prelude="import Mathlib.Tactic",
                            prelude_ladder=())
        for name in ("Explorer-A", "Explorer-B", "Explorer-C")
    }
    pipeline = ParallelProvingPipeline(max_rounds=8, verify_timeout=600,
                                       validators=validators)
    report = asyncio.run(pipeline.run(GOAL))
    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()

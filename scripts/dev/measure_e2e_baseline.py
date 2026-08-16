#!/usr/bin/env python3
"""CX-6: (re)generate `tests/e2e/perf_baseline.json` from a live measurement
sweep on THIS machine.

Run manually, on purpose, when a real perf change makes the checked-in
baseline stale - `tests/e2e/test_perf_baseline.py`'s own regression guard
only READS this file; nothing in the test suite ever calls this script for
you, matching the plan's own wording: "the guard reads the baseline, never
auto-updates it - updating is a deliberate commit."

Usage:
    python scripts/dev/measure_e2e_baseline.py
"""

from __future__ import annotations

import importlib.util
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E = REPO_ROOT / "tests" / "e2e"

# Loaded by file path, deliberately never `import perf_measure` - a bare
# top-level import here would be a literal `ast.Import` node under
# `scripts/`, and `scripts/godmode_runtime/godmode_bindings.py`'s own SBOM
# scanner reads every such node under `scripts/`/`hooks/` as a claimed
# runtime dependency unless its name is stdlib or a first-party module
# living directly under `scripts/`/`hooks/` - `tests/e2e/perf_measure.py`
# is neither, so a bare import here would trip the zero-dependency budget
# (`godmode sbom --gate`) for a project-internal test helper that ships no
# such dependency at all. `perf_measure.py`'s own `measure_fast_classify`
# already uses this exact technique to load `hooks/godmode_gate_fast.py`
# the same way, for the same reason.
_spec = importlib.util.spec_from_file_location("perf_measure", E2E / "perf_measure.py")
perf_measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(perf_measure)  # type: ignore[union-attr]


def main() -> int:
    report = perf_measure.measure_all()
    report["machine"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["note"] = (
        "Median+p95 wall-clock seconds per stage, measured on the machine "
        "named above. The regression guard (tests/e2e/test_perf_baseline.py) "
        "fails a stage that regresses more than 20% against these numbers; "
        "it never updates this file - re-run this script and commit the "
        "result deliberately when a real perf change makes it stale."
    )
    out = E2E / "perf_baseline.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

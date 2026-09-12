"""Check: which platforms this release is measured on, and where it is not.

The product claims Windows and macOS. A session can only measure the platform
it runs on, so the honest output is a matrix: `measured` where a run was
recorded, `failing` where one was recorded and failed, `unmeasured` everywhere
else. `unmeasured` is not a pass and is not dressed up as one (R8).

**`unmeasured` does not fail the build, on purpose.** A check that goes red
because a developer lacks a second machine gets disabled within a week, and a
disabled check measures nothing. A *recorded failing run* does fail.

Recording is explicit (`--record`), never a side effect of reporting, so the
matrix cannot quietly mark itself green by being looked at.

**A hazard scan was tried here and removed.** It flagged absolute path literals
that can only exist on one operating system. Run against this repository it
produced thirteen findings and all thirteen were correct code: an interpreter
probe list guarded by `if os.name != "nt"` (deliberately cross-platform - the
opposite of the defect), fuzz corpus inputs, code that *detects* a `/tmp` path
rather than writing to one, and a docstring example. A detector with a 100%
false-positive rate on its own codebase is a detector that gets disabled, so it
is not shipped. What remains is the matrix, which reports a fact rather than
guessing at one.

What this check cannot do, stated so the matrix is not over-read: passing on
Windows with macOS `unmeasured` says nothing about macOS. The pure-path tests
in `tests/test_install_manifest.py` and `tests/test_install_remove.py` assert
portability *properties* and run identically anywhere - evidence that
portability was designed for, not evidence that it holds on a host nobody ran.
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS_PATH = ROOT / "quality" / "platform-runs.json"

#: Platforms the product makes a support claim about.
SUPPORTED = ("Windows", "Darwin", "Linux")

#: The test modules whose subject is portability. A recorded run means these.
PORTABILITY_MODULES = (
    "tests.test_install_manifest",
    "tests.test_install_remove",
    "tests.test_platform_parity",
)


def current_platform() -> str:
    return platform.system()


def load_runs(path: Path = RUNS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    runs = data.get("runs")
    return runs if isinstance(runs, dict) else {}


def matrix(runs: dict[str, Any]) -> dict[str, str]:
    """Per-platform verdict. Absent means `unmeasured`, never `clean`."""
    out: dict[str, str] = {}
    for name in SUPPORTED:
        entry = runs.get(name)
        if not isinstance(entry, dict):
            out[name] = "unmeasured"
        elif entry.get("result") == "pass":
            out[name] = "measured"
        else:
            out[name] = "failing"
    return out


def run_portability_suite() -> tuple[bool, int, str]:
    """Run the portability modules here. Returns (passed, count, tail)."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *PORTABILITY_MODULES],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    found = re.search(r"Ran (\d+) test", output)
    return proc.returncode == 0, int(found.group(1)) if found else 0, output.strip()[-400:]


def record_this_platform(path: Path = RUNS_PATH) -> dict[str, Any]:
    """Run the suite and record the outcome for the platform we are on."""
    passed, count, _tail = run_portability_suite()
    runs = load_runs(path)
    runs[current_platform()] = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "release": platform.release(),
        "python": sys.version.split()[0],
        "tests": count,
        "result": "pass" if passed else "fail",
    }
    payload = {
        "schema": "godmode-platform-runs-v1",
        "note": "One entry per platform a portability run was actually performed on. "
                "A platform absent from this file is unmeasured, which is not a pass. "
                "Written only by `platform_parity.py --record`, never as a side effect "
                "of reporting.",
        "modules": list(PORTABILITY_MODULES),
        "runs": runs,
    }
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return runs[current_platform()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] != "--record":
        print(f"unknown option {argv[0]!r}; supported: --record", file=sys.stderr)
        return 2

    if argv == ["--record"]:
        entry = record_this_platform()
        print(f"recorded {current_platform()}: {entry['result']} "
              f"({entry['tests']} tests, python {entry['python']})")

    runs = load_runs()
    verdicts = matrix(runs)
    print(f"running on {current_platform()} (python {sys.version.split()[0]})")
    for name in SUPPORTED:
        entry = runs.get(name) or {}
        detail = (f"  {entry.get('date')}  {entry.get('tests')} tests  python {entry.get('python')}"
                  if entry else "  no run recorded")
        print(f"  {name:9} {verdicts[name]:11}{detail}")

    failing = [n for n, v in verdicts.items() if v == "failing"]
    if failing:
        print(f"FAIL: recorded failing runs: {failing}", file=sys.stderr)
        return 1

    unmeasured = [n for n, v in verdicts.items() if v == "unmeasured"]
    if unmeasured:
        print(f"\nunmeasured: {', '.join(unmeasured)} - no host available to this session. "
              f"Not a pass; run this check with --record on such a host to settle it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

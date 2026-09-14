"""Latency sampler: the fast gate's own read-only vs mutating cost.

D-3: `tests/` proves *whether* a command escalates to the full hook by
asserting state (a marker file the stubbed full hook alone can create -
`tests/e2e/harness.py`'s `stub_full_hook`, `tests/test_gate_fast.py`'s
`UngovernedProject` tests) - never by racing a clock. That state proof
answers "did it happen"; it deliberately says nothing about "how long did
it take", which is a real number worth publishing, just not one a unit
test's pass/fail should depend on (a field gate saw a 2.47s call fail a
2.0s bound that had nothing wrong with it).

This script is that number, on demand:

    python benchmarks/gate_latency.py [--n 21] [--json out.json]

Spawns the real `hooks/godmode_gate_fast.py` as a subprocess, exactly as a
host would, N times for a read-only command (`git status` - fast-allowed,
never reaches the full hook) and N times for a mutating one (`git push
--force` - escalates to the real full hook's classify+archive round trip),
against a throwaway, fully-initialized godmode project so neither this
repository's own archive nor its git remote is ever touched. Prints p50/p95
per command in milliseconds. No assertions, nothing importable by
`unittest` discovery - a percentile is a fact about this machine right
now, not a contract.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

FAST_GATE = ROOT / "hooks" / "godmode_gate_fast.py"

COMMANDS = {
    "read-only (git status, fast-allowed)": "git status",
    "mutating (git push --force, escalates)": "git push --force",
}


def _init_project(project: Path, state: Path) -> dict[str, str]:
    """A real, throwaway git work tree with its own isolated godmode state
    - mirrors `tests/e2e/harness.py`'s `e2e_repo`, so a benchmark run never
    writes a single record into this checkout's own archive."""
    project.mkdir(parents=True, exist_ok=True)
    for command in (["init", "-q"], ["config", "user.email", "bench@example.invalid"],
                    ["config", "user.name", "bench"]):
        subprocess.run(["git", *command], cwd=project, capture_output=True)
    (project / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=project, capture_output=True)

    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    for stale in ("GODMODE_HOST", "GROK_AGENT", "CLAUDE_CODE_ENTRYPOINT"):
        environment.pop(stale, None)

    old_state_home = os.environ.get("GODMODE_STATE_HOME")
    os.environ["GODMODE_STATE_HOME"] = str(state)
    try:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle

        Chronicle(resolve_anchor(project)).initialize()
    finally:
        if old_state_home is None:
            os.environ.pop("GODMODE_STATE_HOME", None)
        else:
            os.environ["GODMODE_STATE_HOME"] = old_state_home
    return environment


def _sample(command: str, project: Path, env: dict[str, str], repeats: int) -> list[float]:
    import time

    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(project),
    }).encode("utf-8")
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        subprocess.run([sys.executable, str(FAST_GATE)], input=payload,
                       capture_output=True, cwd=str(project), timeout=60, env=env)
        samples.append(time.perf_counter() - started)
    return samples


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=21,
                        help="samples per command (default 21)")
    parser.add_argument("--json", help="write the raw per-command stats to this path too")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="godmode-gate-latency-") as raw:
        base = Path(raw)
        project = base / "project"
        state = base / "state"
        env = _init_project(project, state)

        results: dict[str, dict[str, float]] = {}
        for label, command in COMMANDS.items():
            samples = _sample(command, project, env, arguments.n)
            p50 = statistics.median(samples)
            p95 = _p95(samples)
            results[label] = {"p50_ms": p50 * 1000, "p95_ms": p95 * 1000, "n": arguments.n}
            print(f"{label}: p50={p50 * 1000:.1f}ms p95={p95 * 1000:.1f}ms (n={arguments.n})")

    if arguments.json:
        target = Path(arguments.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

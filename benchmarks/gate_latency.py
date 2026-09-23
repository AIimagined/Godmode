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
    python benchmarks/gate_latency.py --write-baseline [--n 21]
    python benchmarks/gate_latency.py --check [--n 21]
    python benchmarks/gate_latency.py --notes-line

Spawns the real `hooks/godmode_gate_fast.py` as a subprocess, exactly as a
host would, N times for a read-only command (`git status` - fast-allowed,
never reaches the full hook) and N times for a mutating one (`git push
--force` - escalates to the real full hook's classify+archive round trip),
against a throwaway, fully-initialized godmode project so neither this
repository's own archive nor its git remote is ever touched. Prints p50/p95
per command in milliseconds.

`--write-baseline` records those numbers, and the sample count `n` they were
taken at, to the committed, machine-specific `benchmarks/gate_latency_baseline.json`.
`--check` re-measures and compares against that baseline (`check()`, below),
defaulting its own sample count to the baseline's recorded `n` when `--n` is
not given, exiting 1 on a regression of 20% or more (or a phase the baseline
has but the new measurement is missing) and 2 when no usable baseline is
committed (absent, unparsable, or written under a different schema).

Below 21 samples, `_p95` degenerates toward the plain sample max (at n=11 the
95th-percentile index is the 11th and last value), so both `--write-baseline`
and `--check` refuse `--n` under 21 outright rather than record or judge a
baseline that isn't really a percentile. `--check` and `--write-baseline` are
mutually exclusive.

`--notes-line` (G-9) prints the one line `godmode release-notes` requires
under a release's `## Benchmarks` section - `Gate latency (p95, n=<n>):
fast_allow <ms> ms, escalate <ms> ms` - read straight from the committed
baseline via `notes_line()`, below; it measures nothing and exits 2 when no
usable baseline is committed, the same as `--check`.

`measure()`, `check()`, `recommended_timeouts()`, and `notes_line()` are the
only importable, assertion-bearing surface here, and
`tests/test_gate_latency_check.py` drives all but `measure()` with fabricated
numbers only - never a live timing - so the *unit* tests never race a clock.
A percentile from `measure()` is still a fact about this machine right now,
not a contract; `--check` is the deliberate, separate place a live number is
allowed to fail a build - and, run once, only an advisory one (see
`benchmarks/README.md`).
"""

from __future__ import annotations

import argparse
import json
import math
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

BASELINE_PATH = Path(__file__).resolve().parent / "gate_latency_baseline.json"
BASELINE_SCHEMA = "godmode-gate-latency-baseline-v1"

# Below this, `_p95`'s index (round(0.95 * (n - 1))) lands on or near the
# last sample, so "p95" is really just "the max" - not a percentile a
# baseline or a regression check should trust.
MIN_SAMPLES = 21

# fast_allow: read-only, never reaches the full hook. escalate: mutating,
# escalates to the real full hook's classify+archive round trip.
PHASES = {"fast_allow": "git status", "escalate": "git push --force"}


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


def measure(n: int = 21) -> dict[str, dict[str, float]]:
    """Sample every phase in `PHASES` against one throwaway, fully-initialized
    godmode project - the same setup `main()` used inline before `--check`
    and `--write-baseline` needed to share it."""
    with tempfile.TemporaryDirectory(prefix="godmode-gate-latency-") as raw:
        base = Path(raw)
        project = base / "project"
        state = base / "state"
        env = _init_project(project, state)

        results: dict[str, dict[str, float]] = {}
        for phase, command in PHASES.items():
            samples = _sample(command, project, env, n)
            p50 = statistics.median(samples)
            p95 = _p95(samples)
            results[phase] = {"p50_ms": p50 * 1000, "p95_ms": p95 * 1000, "n": n}
        return results


def check(baseline: dict, measured: dict, tolerance: float = 0.20) -> dict:
    """Fabricated numbers in, never a live measurement - the unit tests own
    this function; `--check` is the only caller that feeds it real ones.

    A phase the baseline has but `measured` does not is never treated as a
    silent 0ms pass: it lands in `missing` and fails the verdict, the same
    as an actual regression."""
    regressions = []
    missing = []
    for phase, row in (baseline.get("phases") or {}).items():
        measured_row = measured.get(phase)
        if measured_row is None:
            missing.append(phase)
            continue
        base = float(row["p95_ms"])
        now = float(measured_row.get("p95_ms", 0.0))
        if base > 0 and now >= base * (1.0 + tolerance):
            regressions.append({"phase": phase, "baseline_p95_ms": base,
                                "measured_p95_ms": now, "ratio": round(now / base, 3)})
    return {"tolerance": tolerance, "regressions": regressions, "missing": missing,
            "verdict": "regression" if (regressions or missing) else "within-budget"}


def recommended_timeouts(measured: dict) -> dict[str, int]:
    """Hook timeouts sized off measured p95s, clamped to a sane range so a
    slow one-off machine cannot recommend an unusably long or short bound."""
    esc = float(measured.get("escalate", {}).get("p95_ms", 0.0))
    fast = float(measured.get("fast_allow", {}).get("p95_ms", 0.0))
    pre = min(30, max(3, math.ceil(esc * 3 / 1000)))
    return {"pre_tool_use": pre,
            "stop": min(60, max(10, math.ceil(esc * 5 / 1000))),
            "user_prompt": min(60, max(10, math.ceil(fast * 10 / 1000)))}


def notes_line(baseline: dict) -> str | None:
    """G-9: the one-line benchmark summary `godmode release-notes` requires
    under a release's `## Benchmarks` section - built from the committed
    baseline's own recorded numbers, never a fresh measurement (`--check`
    and `--write-baseline` are the only callers allowed to spawn one).

    `None` when `baseline` carries no usable `p95_ms` for both `PHASES`
    keys (`fast_allow`, `escalate`) - a partial or malformed baseline
    prints nothing rather than a line with a fabricated number in it.
    `scripts/godmode_runtime/godmode_release_notes.py` reproduces this
    exact wording (not by importing this module - see its own docstring)
    so a pasted `--notes-line` line and `check_notes`'s expectation are
    always the same string."""
    phases = baseline.get("phases")
    if not isinstance(phases, dict):
        return None
    fast = phases.get("fast_allow")
    escalate = phases.get("escalate")
    if not isinstance(fast, dict) or not isinstance(escalate, dict):
        return None
    if "p95_ms" not in fast or "p95_ms" not in escalate:
        return None
    n = baseline.get("n", MIN_SAMPLES)
    return (f"Gate latency (p95, n={n}): fast_allow {float(fast['p95_ms']):.0f} ms, "
            f"escalate {float(escalate['p95_ms']):.0f} ms")


def _load_baseline() -> dict | None:
    """`None` for "no usable baseline" - absent, unreadable, unparsable, or
    written under a schema this script does not recognize - never a
    traceback; the caller turns that into a plain exit 2."""
    if not BASELINE_PATH.exists():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != BASELINE_SCHEMA:
        return None
    return data


def _resolve_n(requested: int | None, baseline: dict | None) -> int:
    """`--n` if given; otherwise the baseline's recorded sample count for
    `--check` (so a check compares like-for-like order statistics with the
    baseline it is judged against); otherwise `MIN_SAMPLES`."""
    if requested is not None:
        return requested
    if baseline and baseline.get("n"):
        return int(baseline["n"])
    return MIN_SAMPLES


def _n_floor_error(n: int) -> str | None:
    if n < MIN_SAMPLES:
        return (f"--n must be >= {MIN_SAMPLES} (got {n}); below {MIN_SAMPLES} samples "
                f"_p95 degenerates toward the sample max, not a real percentile")
    return None


def _runtime_version() -> str:
    try:
        data = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        return str(data.get("version", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def _write_json(path: str, measured: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(measured, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=None,
                        help="samples per command (default 21; --check defaults to the baseline's n)")
    parser.add_argument("--json", help="write the raw per-command stats to this path too")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="compare against the committed baseline; exit 1 on regression, 2 if no usable baseline")
    mode.add_argument("--write-baseline", action="store_true",
                      help="measure and write benchmarks/gate_latency_baseline.json")
    mode.add_argument("--notes-line", action="store_true",
                      help="print the release-notes G-9 line from the committed baseline; measures nothing")
    arguments = parser.parse_args()

    if arguments.notes_line:
        baseline = _load_baseline()
        if baseline is None:
            print(f"no usable baseline at {BASELINE_PATH} (missing, unparsable, or wrong schema)",
                  file=sys.stderr)
            return 2
        line = notes_line(baseline)
        if line is None:
            print(f"baseline at {BASELINE_PATH} carries no usable phases for fast_allow/escalate",
                  file=sys.stderr)
            return 2
        print(line)
        return 0

    if arguments.check:
        baseline = _load_baseline()
        if baseline is None:
            print(f"no usable baseline at {BASELINE_PATH} (missing, unparsable, or wrong schema)",
                  file=sys.stderr)
            return 2
        n = _resolve_n(arguments.n, baseline)
        floor_error = _n_floor_error(n)
        if floor_error:
            print(floor_error, file=sys.stderr)
            return 2
        measured = measure(n)
        report = check(baseline, measured)
        print(json.dumps(report, indent=2, sort_keys=True))
        if arguments.json:
            _write_json(arguments.json, measured)
        return 1 if report["verdict"] == "regression" else 0

    if arguments.write_baseline:
        n = _resolve_n(arguments.n, None)
        floor_error = _n_floor_error(n)
        if floor_error:
            print(floor_error, file=sys.stderr)
            return 2
        measured = measure(n)
        for phase, command in PHASES.items():
            row = measured[phase]
            print(f"{phase} ({command}): p50={row['p50_ms']:.1f}ms p95={row['p95_ms']:.1f}ms (n={row['n']})")
        BASELINE_PATH.write_text(json.dumps({
            "schema": BASELINE_SCHEMA,
            "n": n,
            "phases": {phase: {"p95_ms": row["p95_ms"]} for phase, row in measured.items()},
            "recommended_timeouts": recommended_timeouts(measured),
            "runtime_version": _runtime_version(),
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote baseline to {BASELINE_PATH}")
        if arguments.json:
            _write_json(arguments.json, measured)
        return 0

    n = arguments.n if arguments.n is not None else MIN_SAMPLES
    measured = measure(n)
    for phase, command in PHASES.items():
        row = measured[phase]
        print(f"{phase} ({command}): p50={row['p50_ms']:.1f}ms p95={row['p95_ms']:.1f}ms (n={row['n']})")

    if arguments.json:
        _write_json(arguments.json, measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

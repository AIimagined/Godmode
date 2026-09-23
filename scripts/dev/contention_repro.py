#!/usr/bin/env python3
"""Run three meta-checks while a second full suite loads the machine.

Usage: contention_repro.py [runs]

Exit 0 when every run passes; 1 when any fails; 2 on a bad `runs` argument.
Output is one line per run and target so a log can be cited as evidence
either way. A failing target's captured output goes to stderr so stdout
stays limited to parseable `run=... result=...` lines.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TARGETS = (
    "tests.test_self_checks.SelfCheckTests.test_every_module_self_check_passes",
    "tests.test_godmode_runtime.IntegrityTests.test_removed_assertion_blocks",
    "tests.test_godmode_runtime.ScenarioTests.test_every_staged_failure_is_caught",
)


def _start_load() -> subprocess.Popen:
    """Start the loader suite in its own process group/session.

    So teardown can kill the whole tree it spawns, not just the direct
    child - unittest discovery forks subprocesses of its own that would
    otherwise keep loading the machine into the next run.
    """
    kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs,
    )


def _stop_load(load: subprocess.Popen) -> None:
    """Kill the loader's whole process group/tree, then bound the wait."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(load.pid)],
            capture_output=True,
        )
        # taskkill can itself fail to find/kill the tree (already exited,
        # access denied); terminate() is the fallback for the process we
        # do hold a handle to.
        if load.poll() is None:
            load.terminate()
    else:
        try:
            os.killpg(os.getpgid(load.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass  # godmode: swallow-ok: process already exited between poll and signal; teardown, nothing to report
    try:
        load.wait(timeout=30)
    except subprocess.TimeoutExpired:
        load.kill()
        load.wait()


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        try:
            runs = int(argv[1])
        except ValueError:
            runs = None
        if runs is None or runs < 1:
            print("Usage: contention_repro.py [runs]", file=sys.stderr)
            return 2
    else:
        runs = 3

    failures = 0
    for run in range(1, runs + 1):
        load = _start_load()
        try:
            for target in TARGETS:
                proc = subprocess.run(
                    [sys.executable, "-m", "unittest", target],
                    cwd=REPO_ROOT,
                    capture_output=True, text=True,
                )
                result = "pass" if proc.returncode == 0 else "fail"
                if proc.returncode != 0:
                    print(proc.stdout + proc.stderr, file=sys.stderr, flush=True)
                failures += proc.returncode != 0
                print(f"run={run} target={target} result={result}", flush=True)
        finally:
            _stop_load(load)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

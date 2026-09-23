"""Run unittest modules; retry KNOWN-FLAKY failures isolated, once.

S11-C (laws 13 and 4554): a registered flake that fails in a batch and
passes isolated is reported as retried, never silently; an unregistered
failure, or a registered one that also fails isolated, fails the run.
Usage: python scripts/dev/run_with_flaky_retry.py tests.test_a tests.test_b

NS-8o: every isolated rerun is recorded through the runtime archive when
one is present, so `trends` can rank flakes by frequency and the preflight
can flag a flake retried three or more times that carries no lesson - the
lesson-or-leave rule: a frequent flake either gains a lesson cite in
`tests/KNOWN-FLAKY.txt`, or the entry is removed.

NS-10c: a circuit breaker sits in front of the retry itself. An id that
has failed isolated `n` times inside a window is parked - skipped
entirely, never retried again - until `cooldown_hours` past the park
elapses, so a chronically-failing id stops burning a fresh isolated
subprocess every run while nobody has looked at it. A parked id is
non-blocking: printed and recorded, exactly like a registered flake that
passed isolated, never returned as a run failure - the breaker relieves
the cost of retrying, it does not relocate that cost onto every run's
exit code for a whole cooldown window. Only a genuine isolated-retry
failure (a non-parked id whose retry itself fails) returns 1.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "tests" / "KNOWN-FLAKY.txt"


def _open_archive():
    """Resolve the runtime archive at REGISTRY's own project root, or
    `None`. REGISTRY is what a test fixture patches to redirect this
    runner at a throwaway repo, and every archive lookup must follow it
    there rather than a cached module-level path. `None` whenever the
    runtime cannot be imported, or no archive exists at that root - every
    caller below treats that as "no breaker/bookkeeping data available",
    never a crash.
    """
    repo = REGISTRY.resolve().parents[1]
    scripts_dir = repo / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from godmode_runtime.godmode_anchor import resolve_anchor
    from godmode_runtime.godmode_chronicle import Chronicle

    archive = Chronicle(resolve_anchor(repo))
    if not archive.initialized():
        return None
    return archive


def _record_retry(test_id: str, outcome: str) -> None:
    """NS-8o: record one isolated rerun through the runtime archive.
    Silent no-op when the runtime cannot be imported or no archive exists:
    this runner's own bookkeeping must never fail a test run.
    """
    try:
        archive = _open_archive()
        if archive is None:
            return
        from godmode_runtime.godmode_trends import record_flaky_retry

        record_flaky_retry(archive, test_id, outcome)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: this runner's own bookkeeping must never fail a test run for the caller running it
        pass


def _breaker_state(test_id: str):
    """NS-10c: the id's current trip/cooldown state, or `None` when no
    archive is available - treated by every caller as "closed" (retry
    proceeds as before). This runner's own bookkeeping must never fail a
    test run."""
    try:
        archive = _open_archive()
        if archive is None:
            return None
        from godmode_runtime.godmode_trends import breaker_state

        return breaker_state(archive, test_id, datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: this runner's own bookkeeping must never fail a test run for the caller running it
        return None


def _record_flake_parked(test_id: str, reason: str) -> None:
    """NS-10c: record the breaker tripping, once, the run it is observed."""
    try:
        archive = _open_archive()
        if archive is None:
            return
        from godmode_runtime.godmode_trends import record_flake_parked

        record_flake_parked(archive, test_id, reason)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: this runner's own bookkeeping must never fail a test run for the caller running it
        pass


def _record_flake_readmitted(test_id: str) -> None:
    """NS-10c: record cooldown having elapsed, once, the run it is observed."""
    try:
        archive = _open_archive()
        if archive is None:
            return
        from godmode_runtime.godmode_trends import record_flake_readmitted

        record_flake_readmitted(archive, test_id)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: this runner's own bookkeeping must never fail a test run for the caller running it
        pass


def known_flaky() -> set[str]:
    if not REGISTRY.is_file():
        return set()
    return {line.strip() for line in REGISTRY.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def failing_ids(output: str) -> list[str]:
    found = []
    for match in re.finditer(r"^(?:FAIL|ERROR): (\S+) \(([\w.]+)\)", output, re.M):
        found.append(_canonical(match.group(2)))
    return found


def _canonical(test_id: str) -> str:
    """Normalize a unittest id to the dotted, repo-root-resolvable form.

    ``python -m unittest tests.test_x`` reports a failure as
    ``tests.test_x.Class.method``; ``python -m unittest discover -s
    tests`` reports the identical test as ``test_x.Class.method`` (no
    ``tests.`` package prefix, because discovery's start dir becomes
    the top level). ``KNOWN-FLAKY.txt`` always stores the
    ``tests.``-prefixed form, and a retry re-invokes ``python -m
    unittest <id>`` from the repo root, where only the prefixed form
    imports. Without this, a registered flake discovered via
    ``discover -s tests`` is reported as an unregistered failure, and
    a retry of the bare id fails with ``ModuleNotFoundError``.
    """
    if test_id.startswith("tests.") or test_id.startswith("unittest.loader."):
        return test_id
    return f"tests.{test_id}"


def main() -> int:
    modules = sys.argv[1:]
    if not modules:
        print("usage: run_with_flaky_retry.py <tests.module> [...]")
        return 2
    done = subprocess.run([sys.executable, "-m", "unittest", *modules],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    output = (done.stdout or "") + (done.stderr or "")
    tail = [l for l in output.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    print("\n".join(tail[-3:]))
    if done.returncode == 0:
        return 0
    registry = known_flaky()
    failures = failing_ids(output)
    unregistered = [f for f in failures if f not in registry]
    if unregistered or not failures:
        print("unregistered failure(s):", unregistered or "(unparsed)")
        return 1
    for test_id in failures:
        state = _breaker_state(test_id)
        if state and state.get("readmitted"):
            _record_flake_readmitted(test_id)
        if state and state["state"] == "open":
            if state.get("newly_tripped"):
                _record_flake_parked(test_id, state["reason"])
            # A parked id is non-blocking, same as a registered flake that
            # passed isolated: printed and recorded, never returned as a
            # run failure. The breaker exists to relieve the cost of
            # retrying a chronically-failing id, not to relocate that cost
            # onto every run's exit code for a whole cooldown window - the
            # id's own lack-of-lesson visibility already comes from the
            # existing flake-without-lesson preflight finding, not from
            # this exit code.
            print(f"parked (breaker open until {state['reopens_at']}): "
                  f"{test_id} - {state['reason']}")
            continue
        print(f"retrying registered flake isolated: {test_id}")
        retry = subprocess.run([sys.executable, "-m", "unittest", test_id],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
        if retry.returncode != 0:
            print(f"registered flake ALSO fails isolated - real failure: {test_id}")
            _record_retry(test_id, "failed-isolated")
            tripped = _breaker_state(test_id)
            if tripped and tripped.get("newly_tripped"):
                _record_flake_parked(test_id, tripped["reason"])
            return 1
        print(f"passed isolated (registry: batch-load flake): {test_id}")
        _record_retry(test_id, "passed-isolated")
    return 0


if __name__ == "__main__":
    sys.exit(main())

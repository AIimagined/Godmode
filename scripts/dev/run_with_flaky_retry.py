"""Run unittest modules; retry KNOWN-FLAKY failures isolated, once.

S11-C (laws 13 and 4554): a registered flake that fails in a batch and
passes isolated is reported as retried, never silently; an unregistered
failure, or a registered one that also fails isolated, fails the run.
Usage: python scripts/dev/run_with_flaky_retry.py tests.test_a tests.test_b
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "tests" / "KNOWN-FLAKY.txt"


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
        print(f"retrying registered flake isolated: {test_id}")
        retry = subprocess.run([sys.executable, "-m", "unittest", test_id],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
        if retry.returncode != 0:
            print(f"registered flake ALSO fails isolated - real failure: {test_id}")
            return 1
        print(f"passed isolated (registry: batch-load flake): {test_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

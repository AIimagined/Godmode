"""Shared gate for subprocess-heavy test modules.

A handful of modules shell out to the real CLI dozens of times per test
(measured: test_godmode_runtime.py ~485s, test_launcher_root_fallback.py
~102s, test_preflight_gate.py ~68s, test_failure_semantics.py ~45s on the
reference machine) - together they are the largest single share of the
suite's wall time. They still need to run, but not on every local
`python -m unittest discover` pass a developer runs mid-task.

Decorate every `TestCase` class in a slow module with `@slow`. It runs only
when GODMODE_RUN_SLOW=1 is set - which `godmode precheck --preflight` (the
release check) and the CI jobs that gate `main` both set; a routine local
run does not.

A module-level `unittest.SkipTest` (skip the whole module at import time)
was tried first and dropped: `python -m unittest tests.test_x` (named-module
form, what scripts/dev/run-suite.ps1 uses) reports it as an ERROR, not a
skip, and `python -m pytest tests/test_x.py` alone exits 5 ("no tests
collected") - both nonzero, both wrong for a runner that gates on exit code.
The per-class decorator is the form both runners treat as a clean, 0-exit
skip.

Never add this gate to a gate/authorize/guard module: harm-class coverage
stays in the default run even when it is slow.
"""
from __future__ import annotations

import os
import unittest

RUN_SLOW_ENV = "GODMODE_RUN_SLOW"


def slow_enabled() -> bool:
    return os.environ.get(RUN_SLOW_ENV) == "1"


slow = unittest.skipUnless(
    slow_enabled(),
    f"subprocess-heavy; release check only (set {RUN_SLOW_ENV}=1 to run it locally)",
)

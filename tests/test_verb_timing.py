"""Wall-clock bounds for the verbs measured slow on this repo (2026-09-28:
metrics 143 s, minimality 88 s, loop 70 s, evals 60 s, doctor 54 s).
Each runs the real CLI against this checkout, so the numbers are the
operator's numbers; slow-gated because one pass is a minute of subprocesses."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from _slow import slow  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

_HOST_ENV = None


def setUpModule() -> None:
    """The timed verbs run as subprocesses that spread `os.environ`; a
    runner's own `CI` or host marker must not change what they measure."""
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()

VERB_BOUND_SECONDS = 10.0
BRIEF_BOUND_SECONDS = 2.0


def _timed(*verb: str) -> tuple[float, subprocess.CompletedProcess]:
    started = time.monotonic()
    done = subprocess.run([sys.executable, "-X", "utf8", "scripts/godmode.py", "--project", ".", *verb],
                          cwd=PLUGIN_ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)
    return time.monotonic() - started, done


@slow
class VerbTimingTests(unittest.TestCase):
    def assert_bound(self, bound: float, *verb: str) -> None:
        # Warm run: the first build of the atlas cache is the one-off cost
        # the cache exists to pay once.
        _timed(*verb)
        took, done = _timed(*verb)
        self.assertLess(took, bound, f"{' '.join(verb)} took {took:.1f}s (exit {done.returncode}): "
                                     f"{done.stderr[-300:]}")

    def test_metrics(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "metrics")

    def test_minimality(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "minimality")

    def test_loop(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "loop")

    def test_evals_fast(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "evals", "--fast", "--brief")

    def test_doctor(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "doctor")

    def test_resume(self) -> None:
        self.assert_bound(VERB_BOUND_SECONDS, "resume")

    def test_brief_is_hook_fast(self) -> None:
        self.assert_bound(BRIEF_BOUND_SECONDS, "brief")


if __name__ == "__main__":
    unittest.main()

"""D-4: the flaky-retry runner's discovery identity.

`python -m unittest tests.test_x` reports a failure as
`tests.test_x.Class.method`; `python -m unittest discover -s tests`
reports the identical test as `test_x.Class.method` (no `tests.`
prefix, because discovery's start dir becomes the top level).
`tests/KNOWN-FLAKY.txt` always stores the `tests.`-prefixed form.
Without normalizing, a registered flake discovered via `discover -s
tests` is reported as an unregistered failure, and even if it were
matched, a retry of the bare id fails with ModuleNotFoundError from
the repo root. This file proves both discovery shapes resolve to the
same identity and exercises every classification branch: clean pass,
unregistered failure, a registered flake retried isolated (both
invocation shapes), and an import failure that must not be swallowed.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = PLUGIN_ROOT / "scripts" / "dev"
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))

import run_with_flaky_retry as runner  # noqa: E402

FLAKY_MODULE = '''import unittest
from pathlib import Path

MARKER = Path(__file__).resolve().parent / "marker.txt"


class FlakyTests(unittest.TestCase):
    def test_x(self):
        if MARKER.is_file():
            return
        MARKER.write_text("seen", encoding="utf-8")
        self.assertTrue(False, "first run fails to simulate a batch-load flake")
'''

PASS_MODULE = '''import unittest


class PassTests(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
'''

HARDFAIL_MODULE = '''import unittest


class HardFailTests(unittest.TestCase):
    def test_bad(self):
        self.assertTrue(False, "not registered as flaky")
'''

IMPORTERR_MODULE = "import this_module_does_not_exist_anywhere  # noqa\n"

REGISTRY_TEXT = "tests.test_flaky.FlakyTests.test_x\n"


@contextlib.contextmanager
def fixture_repo():
    """A throwaway repo root with its own tests/ package and registry."""
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        tests_dir = root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_flaky.py").write_text(FLAKY_MODULE, encoding="utf-8")
        (tests_dir / "test_pass.py").write_text(PASS_MODULE, encoding="utf-8")
        (tests_dir / "test_hardfail.py").write_text(HARDFAIL_MODULE, encoding="utf-8")
        (tests_dir / "test_importerr.py").write_text(IMPORTERR_MODULE, encoding="utf-8")
        (tests_dir / "KNOWN-FLAKY.txt").write_text(REGISTRY_TEXT, encoding="utf-8")
        yield root, tests_dir


@contextlib.contextmanager
def run_from(root: Path, registry: Path):
    """Run the real runner with cwd and REGISTRY pinned to the fixture."""
    previous_cwd = os.getcwd()
    os.chdir(root)
    try:
        with mock.patch.object(runner, "REGISTRY", registry):
            yield
    finally:
        os.chdir(previous_cwd)


def _invoke(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with mock.patch.object(sys, "argv", ["run_with_flaky_retry.py", *argv]):
        with contextlib.redirect_stdout(buffer):
            code = runner.main()
    return code, buffer.getvalue()


class CanonicalIdentityTests(unittest.TestCase):
    """Unit-level proof that both discovery shapes name the same test."""

    def test_module_arg_and_discover_shapes_canonicalize_identically(self) -> None:
        module_arg_shape = "tests.test_flaky.FlakyTests.test_x"
        discover_shape = "test_flaky.FlakyTests.test_x"
        self.assertEqual(
            runner._canonical(module_arg_shape),
            runner._canonical(discover_shape))
        self.assertEqual(runner._canonical(discover_shape), module_arg_shape)

    def test_a_loader_synthetic_id_is_left_alone(self) -> None:
        # An import failure's id (unittest.loader._FailedTest.<name>) names
        # no real module under tests/; prefixing it would only manufacture
        # a fake match against the registry.
        loader_id = "unittest.loader._FailedTest.test_importerr"
        self.assertEqual(runner._canonical(loader_id), loader_id)

    def test_failing_ids_normalizes_a_bare_discover_style_report(self) -> None:
        sample = "FAIL: test_x (test_flaky.FlakyTests.test_x)\n"
        self.assertEqual(runner.failing_ids(sample),
                         ["tests.test_flaky.FlakyTests.test_x"])


class ClassificationBranchTests(unittest.TestCase):
    """Each branch of the runner's decision, driven by a real subprocess."""

    def test_a_clean_pass_exits_zero_with_no_retry_talk(self) -> None:
        with fixture_repo() as (root, tests_dir):
            with run_from(root, tests_dir / "KNOWN-FLAKY.txt"):
                code, output = _invoke(["tests.test_pass"])
        self.assertEqual(code, 0)
        self.assertIn("OK", output)
        self.assertNotIn("retrying", output)

    def test_an_unregistered_failure_hard_fails(self) -> None:
        with fixture_repo() as (root, tests_dir):
            with run_from(root, tests_dir / "KNOWN-FLAKY.txt"):
                code, output = _invoke(["tests.test_hardfail"])
        self.assertEqual(code, 1)
        self.assertIn("unregistered failure", output)
        self.assertIn("tests.test_hardfail.HardFailTests.test_bad", output)

    def test_an_import_failure_hard_fails_and_is_not_swallowed(self) -> None:
        with fixture_repo() as (root, tests_dir):
            with run_from(root, tests_dir / "KNOWN-FLAKY.txt"):
                code, output = _invoke(["tests.test_importerr"])
        self.assertEqual(code, 1)
        self.assertIn("unregistered failure", output)

    def test_a_registered_flake_named_by_module_arg_is_retried_isolated(self) -> None:
        with fixture_repo() as (root, tests_dir):
            with run_from(root, tests_dir / "KNOWN-FLAKY.txt"):
                code, output = _invoke(["tests.test_flaky"])
        self.assertEqual(code, 0)
        # Green at the end must still expose that it failed first.
        self.assertIn("FAILED", output)
        self.assertIn("retrying registered flake isolated", output)
        self.assertIn("passed isolated", output)

    def test_the_same_flake_named_by_discover_is_also_retried_isolated(self) -> None:
        # This is the discovery-identity fixture: `discover -s tests`
        # reports the bare id `test_flaky.FlakyTests.test_x`, which must
        # still resolve to the `tests.`-prefixed registry entry, and the
        # retry itself must re-invoke the prefixed, resolvable form.
        with fixture_repo() as (root, tests_dir):
            with run_from(root, tests_dir / "KNOWN-FLAKY.txt"):
                code, output = _invoke(
                    ["discover", "-s", "tests", "-p", "test_flaky.py"])
        self.assertEqual(code, 0)
        self.assertNotIn("unregistered failure", output)
        self.assertIn("FAILED", output)
        self.assertIn("retrying registered flake isolated", output)
        self.assertIn("tests.test_flaky.FlakyTests.test_x", output)
        self.assertIn("passed isolated", output)


if __name__ == "__main__":
    unittest.main()

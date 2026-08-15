"""Guard-erosion classes: ways a green guard stops guarding.

Absorbed from a recorded lessons corpus, where each was recorded live:

- A guard test with no reachable assertion passed while the bug it named was
  live (L-282: the plant landed and every assertion stayed green because none
  could be reached; L-238: prove the assertions go red, not just the plant).
- A test whose except arm is a bare `pass` deletes the only path by which its
  failure could surface (L-175: resilience implemented as silence).
- A guard anchored to a character count stops guarding when the code grows
  (L-299: the file grew past the slice and the invariant left the window).

Each detector test carries both halves: the planted violation is CAUGHT and
the adjacent innocent form PASSES.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_integrity import guard_quality  # noqa: E402


def _repo(**files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-erosion-")
    root = Path(holder.name)
    for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                    ["config", "user.name", "d"]):
        subprocess.run(["git", *command], cwd=root, capture_output=True)
    (root / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root,
                   capture_output=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    holder._root = root  # type: ignore[attr-defined]
    return holder


def _codes(findings: list[dict]) -> set[str]:
    return {finding["monitor"] for finding in findings}


class AssertionFreeTests(unittest.TestCase):
    def test_a_test_that_cannot_fail_is_reported(self) -> None:
        body = (
            "def test_the_gate_rejects_bad_input():\n"
            "    result = run_gate('bad')\n"
            "    print(result)\n"
        )
        holder = _repo(**{"tests/test_gate.py": body})
        with holder:
            findings = guard_quality(holder._root)  # type: ignore[attr-defined]
        self.assertIn("assertion-free-test", _codes(findings))

    def test_an_asserting_test_is_fine(self) -> None:
        body = (
            "def test_the_gate_rejects_bad_input():\n"
            "    assert run_gate('bad') is None\n"
        )
        holder = _repo(**{"tests/test_gate.py": body})
        with holder:
            self.assertNotIn("assertion-free-test",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]

    def test_an_expected_exception_counts_as_failable(self) -> None:
        body = (
            "def test_bad_input_raises():\n"
            "    with pytest.raises(ValueError):\n"
            "        run_gate('bad')\n"
        )
        holder = _repo(**{"tests/test_gate.py": body})
        with holder:
            self.assertNotIn("assertion-free-test",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]


class SilentCatchTests(unittest.TestCase):
    def test_a_swallowing_except_in_a_test_is_reported(self) -> None:
        body = (
            "def test_cleanup_never_throws():\n"
            "    try:\n"
            "        cleanup()\n"
            "    except Exception:\n"
            "        pass\n"
            "    assert True\n"
        )
        holder = _repo(**{"tests/test_cleanup.py": body})
        with holder:
            findings = guard_quality(holder._root)  # type: ignore[attr-defined]
        self.assertIn("silent-catch-in-test", _codes(findings))

    def test_a_catch_that_asserts_is_fine(self) -> None:
        body = (
            "def test_cleanup_reports_failure():\n"
            "    try:\n"
            "        cleanup()\n"
            "    except Exception as exc:\n"
            "        assert 'retryable' in str(exc)\n"
        )
        holder = _repo(**{"tests/test_cleanup.py": body})
        with holder:
            self.assertNotIn("silent-catch-in-test",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]


class FixedSliceTests(unittest.TestCase):
    def test_a_fixed_slice_read_is_reported(self) -> None:
        # The slice is assembled at runtime so this file's own raw text never
        # contains the pattern - the population check below scans this very
        # file, and a contiguous fixture would be a self-inflicted finding.
        body = (
            "def test_module_declares_the_invariant():\n"
            "    head = Path('lib/gate.py').read_text()[" + ":5000]\n"
            "    assert 'INVARIANT' in head\n"
        )
        holder = _repo(**{"tests/test_anchor.py": body})
        with holder:
            findings = guard_quality(holder._root)  # type: ignore[attr-defined]
        self.assertIn("fixed-slice-anchor", _codes(findings))

    def test_a_whole_file_read_is_fine(self) -> None:
        body = (
            "def test_module_declares_the_invariant():\n"
            "    assert 'INVARIANT' in Path('lib/gate.py').read_text()\n"
        )
        holder = _repo(**{"tests/test_anchor.py": body})
        with holder:
            self.assertNotIn("fixed-slice-anchor",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]

    def test_a_short_slice_of_a_string_is_fine(self) -> None:
        # `detail[:70]` in a message is formatting, not an anchor; the
        # threshold (3+ digits) plus the read-call prefix keeps it out.
        body = (
            "def test_message_is_short():\n"
            "    assert len(build_message()[:70]) <= 70\n"
        )
        holder = _repo(**{"tests/test_msg.py": body})
        with holder:
            self.assertNotIn("fixed-slice-anchor",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]


class OwnSuiteCleanTests(unittest.TestCase):
    """The monitors must not cry wolf on this repository's own tests.

    Four false positives on the project's own suite is the recorded rate at
    which a reader starts skipping a monitor - so the whole godmode test tree
    is the negative-control corpus. Population validation per L-162: a
    detector is validated by its count over the population, not spot cases.
    """

    def test_the_godmode_suite_produces_no_erosion_findings(self) -> None:
        findings = guard_quality(PLUGIN_ROOT)
        erosion = [f for f in findings if f["monitor"] in
                   {"assertion-free-test", "silent-catch-in-test",
                    "fixed-slice-anchor"}]
        self.assertEqual(
            erosion, [],
            "the erosion monitors flagged this repository's own tests: "
            + "; ".join(f"{f['monitor']}:{f['path']}" for f in erosion))


if __name__ == "__main__":
    unittest.main()

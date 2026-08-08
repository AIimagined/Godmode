"""Three ways a verification is worth less than it looks.

* A check that mutates the tree it is checking reports on a tree that no longer
  exists. The run is real; the subject moved underneath it.
* A guard whose name promises "every" and whose body asserts one case reads as
  coverage in every listing that will ever quote it. The name is what a later
  reader trusts, and the assertion is what actually holds.
* A test that writes outside a temporary directory is writing somewhere real.
  A mistake ledger records exactly this: a write-endpoint smoke test aimed at a
  live project id, which returned 200 and destroyed the draft it was verifying.

None of these fail. That is the point: each produces a green result that means
less than the reader will take it to mean.
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
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_integrity import guard_quality  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _repo(**files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-guard-")
    root = Path(holder.name)
    for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                    ["config", "user.name", "d"]):
        subprocess.run(["git", *command], cwd=root, capture_output=True)
    (root / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, capture_output=True)
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    holder._root = root  # type: ignore[attr-defined]
    return holder


def _codes(findings: list[dict]) -> set[str]:
    return {finding["monitor"] for finding in findings}


class UniversalNameTests(unittest.TestCase):
    """F7 — the name promises more than the assertion delivers."""

    def test_a_universal_name_over_a_single_assertion_is_reported(self) -> None:
        body = (
            "def test_every_route_requires_auth():\n"
            "    assert route_requires_auth('/admin')\n"
        )
        holder = _repo(**{"tests/test_routes.py": body})
        with holder:
            findings = guard_quality(holder._root)  # type: ignore[attr-defined]
        self.assertIn("universal-name-single-case", _codes(findings))

    def test_a_universal_name_that_iterates_is_fine(self) -> None:
        body = (
            "def test_every_route_requires_auth():\n"
            "    for route in ALL_ROUTES:\n"
            "        assert route_requires_auth(route)\n"
        )
        holder = _repo(**{"tests/test_routes.py": body})
        with holder:
            self.assertNotIn("universal-name-single-case",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]

    def test_a_universal_name_asserting_a_whole_collection_is_fine(self) -> None:
        """`assertEqual(offenders, [])` covers everything without a loop."""
        body = (
            "def test_no_module_leaks_a_secret():\n"
            "    offenders = scan_all()\n"
            "    assert offenders == []\n"
        )
        holder = _repo(**{"tests/test_scan.py": body})
        with holder:
            self.assertNotIn("universal-name-single-case",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]

    def test_an_ordinary_name_is_not_held_to_it(self) -> None:
        body = "def test_admin_route_requires_auth():\n    assert requires_auth('/admin')\n"
        holder = _repo(**{"tests/test_one.py": body})
        with holder:
            self.assertNotIn("universal-name-single-case",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]


class RealDataTests(unittest.TestCase):
    """F14 — a smoke test aimed at something real."""

    def test_a_test_writing_outside_a_temporary_directory_is_reported(self) -> None:
        body = (
            "def test_save_roundtrip():\n"
            "    Path('workspace/draft/index.html').write_text('<stub>')\n"
        )
        holder = _repo(**{"tests/test_save.py": body})
        with holder:
            findings = guard_quality(holder._root)  # type: ignore[attr-defined]
        self.assertIn("test-writes-real-path", _codes(findings))

    def test_a_test_writing_under_a_temporary_directory_is_fine(self) -> None:
        body = (
            "def test_save_roundtrip(tmp_path):\n"
            "    (tmp_path / 'index.html').write_text('<stub>')\n"
        )
        holder = _repo(**{"tests/test_save.py": body})
        with holder:
            self.assertNotIn("test-writes-real-path",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]

    def test_a_production_file_writing_is_not_a_test_finding(self) -> None:
        body = "def save(path):\n    Path(path).write_text('data')\n"
        holder = _repo(**{"lib/store.py": body})
        with holder:
            self.assertNotIn("test-writes-real-path",
                             _codes(guard_quality(holder._root)))  # type: ignore[attr-defined]


class MutatingCheckTests(unittest.TestCase):
    """F12 — the check changed the tree it was checking."""

    def test_a_check_that_dirties_the_tree_is_recorded(self) -> None:
        from godmode_runtime.godmode_attest import run_check

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            subprocess.run(["git", "init", "-q"], cwd=project, capture_output=True)
            (project / "tracked.txt").write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
            subprocess.run(["git", "-c", "user.email=d@e.invalid", "-c", "user.name=d",
                            "commit", "-q", "-m", "base"], cwd=project, capture_output=True)
            record = run_check(
                archive, "s1", project, "dirtying",
                [sys.executable, "-c",
                 "open('tracked.txt','w').write('after')"])
        self.assertTrue(record.get("mutated_tree"),
                        "a check that rewrote a tracked file was recorded as clean")

    def test_a_read_only_check_is_not_flagged(self) -> None:
        from godmode_runtime.godmode_attest import run_check

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            subprocess.run(["git", "init", "-q"], cwd=project, capture_output=True)
            (project / "tracked.txt").write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
            subprocess.run(["git", "-c", "user.email=d@e.invalid", "-c", "user.name=d",
                            "commit", "-q", "-m", "base"], cwd=project, capture_output=True)
            record = run_check(archive, "s1", project, "reading",
                               [sys.executable, "-c", "print(1)"])
        self.assertFalse(record.get("mutated_tree"))


if __name__ == "__main__":
    unittest.main()

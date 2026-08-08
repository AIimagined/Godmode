"""The last five tooling failures, each in the form that is actually checkable.

A taxonomy of real coding-agent incidents gives the agent's own tooling its own
section. Five entries were left unenforced after the obvious ones, because each
describes a discipline rather than an artefact. Each has a narrower form that a
runtime can see, and the narrow form is what this asserts — a check that only
covers part of a rule is worth more than a rule nothing checks.

* An anchored edit that silently fails leaves a file in the diff whose content
  did not meaningfully change.
* A dependency change under a live process makes every later result suspect
  until something restarts.
* A run under a different environment is not evidence about this one, which is
  how a correct detector was called broken by a checkout that had no history to
  walk.
* A status about an external system, stated rather than read, is the same
  unverifiable assertion as any other external claim.
* Being corrected by the runtime and recording no lesson is how the same
  mistake returns; the ledger this comes from names it as a standing directive
  and still records recurrences.
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

from godmode_runtime.godmode_integrity import source_damage  # noqa: E402
from godmode_runtime.godmode_attest import looks_external  # noqa: E402
from godmode_runtime.godmode_census import uncaptured_corrections  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _repo(**files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-tooling-")
    root = Path(holder.name)
    for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                    ["config", "user.name", "d"]):
        subprocess.run(["git", *command], cwd=root, capture_output=True)
    (root / "src.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "package.json").write_text('{"name":"x","dependencies":{"a":"1.0.0"}}\n',
                                       encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, capture_output=True)
    for relative, content in files.items():
        (root / relative).write_text(content, encoding="utf-8")
    holder._root = root  # type: ignore[attr-defined]
    return holder


def _codes(findings: list[dict]) -> set[str]:
    return {finding["monitor"] for finding in findings}


class SilentEditTests(unittest.TestCase):
    """O3 — an anchored edit reports success and changes nothing."""

    def test_a_change_that_alters_nothing_but_whitespace_is_reported(self) -> None:
        holder = _repo(**{"src.py": "def f():\n    return 1\n   \n"})
        with holder:
            findings = source_damage(holder._root)  # type: ignore[attr-defined]
        self.assertIn("no-op-change", _codes(findings))

    def test_a_real_change_is_not_reported_as_a_no_op(self) -> None:
        holder = _repo(**{"src.py": "def f():\n    return 2\n"})
        with holder:
            self.assertNotIn("no-op-change",
                             _codes(source_damage(holder._root)))  # type: ignore[attr-defined]


class DependencyChangeTests(unittest.TestCase):
    """O7 — stale artefacts mimic a code regression."""

    def test_a_dependency_change_is_reported(self) -> None:
        holder = _repo(**{"package.json": '{"name":"x","dependencies":{"a":"2.0.0"}}\n'})
        with holder:
            findings = source_damage(holder._root)  # type: ignore[attr-defined]
        self.assertIn("dependency-changed", _codes(findings))
        detail = " ".join(f["detail"] for f in findings)
        self.assertIn("restart", detail)

    def test_an_ordinary_source_change_is_not(self) -> None:
        holder = _repo(**{"src.py": "def f():\n    return 3\n"})
        with holder:
            self.assertNotIn("dependency-changed",
                             _codes(source_damage(holder._root)))  # type: ignore[attr-defined]

    def test_the_dependency_finding_does_not_block(self) -> None:
        """It is a reason to be careful, not a defect; blocking every lockfile
        edit is how a check gets switched off."""
        holder = _repo(**{"package.json": '{"name":"x","dependencies":{"a":"3.0.0"}}\n'})
        with holder:
            for finding in source_damage(holder._root):  # type: ignore[attr-defined]
                if finding["monitor"] == "dependency-changed":
                    self.assertFalse(finding["blocking"])


class ExternalStatusTests(unittest.TestCase):
    """O9 — a status synthesised instead of read."""

    def test_a_status_assertion_about_an_external_system_is_external(self) -> None:
        for text in ("CI is green on main",
                     "the release page is published",
                     "the build passed on the runner",
                     "the pull request was merged upstream"):
            self.assertTrue(looks_external(text)[0], text)

    def test_a_local_statement_is_not(self) -> None:
        for text in ("the suite passes here",
                     "the archive holds 54 records",
                     "this file no longer parses"):
            self.assertFalse(looks_external(text)[0], text)


class UncapturedCorrectionTests(unittest.TestCase):
    """P10 — corrected, and the lesson never written down."""

    def test_a_downgraded_claim_with_no_lesson_is_reported(self) -> None:
        from godmode_runtime.godmode_attest import record_claim

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "s1", "the root cause is the cache",
                         "verified", cites=[])
            report = uncaptured_corrections(archive)
        self.assertGreaterEqual(report["downgraded"], 1)
        self.assertEqual(report["lessons"], 0)
        self.assertEqual(report["verdict"], "corrections-unrecorded")

    def test_recording_the_lesson_clears_it(self) -> None:
        from godmode_runtime.godmode_attest import record_claim

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "s1", "the root cause is the cache",
                         "verified", cites=[])
            archive.append("lesson", "cause asserted without a differential",
                           {"value": "diff before theory"}, evidence=[])
            report = uncaptured_corrections(archive)
        self.assertEqual(report["verdict"], "corrections-recorded")

    def test_a_surface_recorded_under_another_kind_counts_as_used(self) -> None:
        """The experiment loop writes an `action` record with an `experiment:`
        subject. A census keyed on kind alone called that surface dead minutes
        after it ran — a false negative in the tool built to find dead ones."""
        from godmode_runtime.godmode_census import census

        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            archive.append("action", "experiment:the brief is cheaper",
                           {"runs": [{"attempt": 1, "exit": 0}]}, evidence=[])
            unused = {entry["kind"] for entry in census(archive)["unused"]}
        self.assertNotIn("experiment", unused)

    def test_a_session_that_was_never_corrected_is_clean(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            report = uncaptured_corrections(archive)
        self.assertEqual(report["verdict"], "nothing-to-record")


if __name__ == "__main__":
    unittest.main()


class CensusSchemaTests(unittest.TestCase):
    """A surface the archive cannot hold is impossible, not unused.

    `mistake` was listed as a tracked surface and is not an event kind, so the
    census would have reported a shortfall nothing could ever close. The census
    is the tool for finding dead surfaces; declaring an imaginary one is the
    same error it exists to report.
    """

    def test_every_tracked_surface_is_a_real_record_kind(self) -> None:
        from godmode_runtime.godmode_census import TRACKED_SURFACES, _SUBJECT_PREFIXES
        from godmode_runtime.godmode_constants import EVENT_KINDS

        unknown = sorted(
            kind for kind in TRACKED_SURFACES
            if kind not in EVENT_KINDS and kind not in _SUBJECT_PREFIXES
        )
        self.assertEqual(unknown, [],
                         f"the census tracks a kind the archive cannot hold: {unknown}")

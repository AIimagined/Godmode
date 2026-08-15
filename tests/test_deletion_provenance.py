"""B3-6: provenance-before-deletion gate.

PARTIAL-P1 (lessons sweep 2026-08-15): `godmode_removal.py` already records
*why* something was deleted, after the fact. This is the mirror - *before* a
deletion the fence would otherwise allow (an rm or archive-move of a tracked
file), an attested pre-check: C-16's reverse-impact traversal
(`atlas.build(project).affected(path)`, reused rather than rebuilt) plus a
statement covering git-history-read and sole-carrier-of-open-obligation.

Requirement-driven, like B3-5: undeclared stays advisory; declared blocks. A
pin always denies, whatever the policy says - the SHIPPED U-B2 evaluator-pin
store (`godmode_sentinel.pinned_evaluators`/`pin_evaluator`), not a second
one: this gate reads that store rather than inventing its own. Untracked
scratch files are unaffected either way.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_atlas import build as build_atlas  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_fence import (  # noqa: E402
    deletion_verdict,
    record_deletion_precheck,
)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    POLICY_FILENAME,
    pin_evaluator,
    unpin_evaluator,
)


@contextmanager
def isolated_git_project():
    """A committed git repo isolated from the user's global config.

    A local copy of the shared idiom rather than an import: this gate's
    tests must keep passing even if another module's fixture reshapes,
    because a gate test that breaks for fixture reasons reads as a gate that
    broke.
    """
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        (project / "tracked.py").write_text("value = 1\n", encoding="utf-8")
        env = {"GODMODE_STATE_HOME": str(state), "GIT_CONFIG_GLOBAL": str(base / "gitconfig")}
        with mock.patch.dict(os.environ, env, clear=False):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project)]
            subprocess.run(git[:1] + ["init", "-q", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True, capture_output=True)
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


def _declare_gate(project: Path) -> None:
    (project / POLICY_FILENAME).write_text(
        json.dumps({"deletion_provenance_gate": True}), encoding="utf-8"
    )


def _pin(archive, project: Path, path: str) -> None:
    pin_evaluator(archive, project, path)


class UntrackedScratchTests(unittest.TestCase):
    def test_deleting_an_untracked_scratch_file_is_unaffected(self) -> None:
        """The stated green control: untracked scratch file deletion is
        unaffected, whatever the policy says."""
        with isolated_git_project() as (project, archive):
            _declare_gate(project)
            (project / "scratch.tmp").write_text("x", encoding="utf-8")
            verdict = deletion_verdict(archive, "scratch.tmp", project_root=project)
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["gate"], "untracked")


class RedFirstTests(unittest.TestCase):
    def test_undeclared_is_advisory_and_never_blocks(self) -> None:
        with isolated_git_project() as (project, archive):
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["gate"], "advisory")

    def test_undeclared_still_records_what_a_precheck_would_have_covered(self) -> None:
        with isolated_git_project() as (project, archive):
            deletion_verdict(archive, "tracked.py", project_root=project)
            subjects = [r["subject"] for r in archive.select(kind="action", limit=50)]
        self.assertTrue(
            any(s.startswith("deletion-precheck-advisory:") for s in subjects), subjects
        )

    def test_declared_and_unattested_is_red(self) -> None:
        """The gate must be seen refusing before it is seen passing, or a
        gate that always allows and a gate that works are indistinguishable."""
        with isolated_git_project() as (project, archive):
            _declare_gate(project)
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["gate"], "declared")
        self.assertIn("delete-precheck", verdict["remedy"])

    def test_green_control_an_attested_precheck_passes(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_gate(project)
            affected = build_atlas(project).affected("tracked.py")
            record_deletion_precheck(
                archive, project, "tracked.py",
                history_read="single baseline commit; no prior authorship of note",
                sole_carrier="not the sole carrier of any open obligation",
                affected=affected,
            )
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["gate"], "attested")
        self.assertIn("precheck", verdict)


class PrecheckRecordingTests(unittest.TestCase):
    def test_a_precheck_needs_a_history_statement(self) -> None:
        with isolated_git_project() as (project, archive):
            with self.assertRaises(ArchiveError):
                record_deletion_precheck(
                    archive, project, "tracked.py", history_read="",
                    sole_carrier="not the sole carrier",
                )

    def test_a_precheck_needs_a_sole_carrier_statement(self) -> None:
        with isolated_git_project() as (project, archive):
            with self.assertRaises(ArchiveError):
                record_deletion_precheck(
                    archive, project, "tracked.py", history_read="one commit",
                    sole_carrier="",
                )

    def test_the_recorded_precheck_carries_what_traversal_actually_found(self) -> None:
        with isolated_git_project() as (project, archive):
            (project / "dependent.py").write_text(
                "import tracked\n", encoding="utf-8")
            affected = build_atlas(project).affected("tracked.py")
            record = record_deletion_precheck(
                archive, project, "tracked.py",
                history_read="one commit", sole_carrier="not the sole carrier",
                affected=affected,
            )
        self.assertGreaterEqual(record["data"]["affected_count"], 0)


class PinTests(unittest.TestCase):
    """The pin store outranks everything else: pinned files stay denied
    regardless of policy. This is the shipped U-B2 evaluator-pin store -
    `godmode_sentinel.pinned_evaluators`/`pin_evaluator` - read by this gate
    rather than a second, independently maintained one."""

    def test_a_pinned_file_is_denied_even_undeclared(self) -> None:
        with isolated_git_project() as (project, archive):
            _pin(archive, project, "tracked.py")
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["gate"], "pinned")

    def test_a_pinned_file_is_denied_even_with_an_attested_precheck(self) -> None:
        """A pin outranks an attestation too, not only the undeclared case -
        the whole point of ranking it first."""
        with isolated_git_project() as (project, archive):
            _declare_gate(project)
            _pin(archive, project, "tracked.py")
            record_deletion_precheck(
                archive, project, "tracked.py",
                history_read="one commit", sole_carrier="not the sole carrier",
            )
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["gate"], "pinned")

    def test_unpinning_lifts_the_deletion_denial(self) -> None:
        """The pin, not this gate, is what is being consulted - proven by
        showing the denial follows the pin's own state, in both directions."""
        with isolated_git_project() as (project, archive):
            _pin(archive, project, "tracked.py")
            denied = deletion_verdict(archive, "tracked.py", project_root=project)
            unpin_evaluator(archive, project, "tracked.py")
            lifted = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertFalse(denied["allowed"])
        self.assertTrue(lifted["allowed"])
        self.assertNotEqual(lifted["gate"], "pinned")

    def test_no_pin_pins_nothing(self) -> None:
        with isolated_git_project() as (project, archive):
            verdict = deletion_verdict(archive, "tracked.py", project_root=project)
        self.assertNotEqual(verdict["gate"], "pinned")


class OutsideProjectTests(unittest.TestCase):
    def test_a_path_outside_the_project_is_allowed_by_this_gate(self) -> None:
        """This gate is a statement about this project; a path that escapes
        it is not this gate's business, whatever else refuses it."""
        with isolated_git_project() as (project, archive):
            verdict = deletion_verdict(
                archive, str(project.parent / "elsewhere.py"), project_root=project
            )
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["gate"], "outside-project")


if __name__ == "__main__":
    unittest.main()

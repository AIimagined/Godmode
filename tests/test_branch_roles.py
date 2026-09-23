"""NS-13h: a branch declares a role; maintained branches carry the plan-and-
test discipline, throwaway (spike) branches do not.

Every write here goes to a throwaway project that is not a git repository,
with its own state home; the branch a runtime is "on" is set on the anchor.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_branchrole as roles  # noqa: E402
from godmode_runtime import godmode_integrity as integrity  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_branches  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


class Project:
    """A governed temp project (not a git repository) whose anchor reports
    `branch`."""

    def __init__(self, branch: str | None) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="godmode-branch-roles-")
        base = Path(self._tmp.name)
        self.project = base / "project"
        self.project.mkdir()
        self._env = mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")})
        self._env.start()
        anchor = dataclasses.replace(resolve_anchor(self.project), branch=branch)
        self.archive = Chronicle(anchor)
        self.archive.initialize()
        self.runtime = Runtime(anchor=anchor, archive=self.archive)

    def close(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def branches(self, *, record: bool = False, role: str | None = None) -> dict:
        args = argparse.Namespace(record=record, claim=False, release=False, role=role)
        return cmd_branches(args, self.runtime).payload


class DefaultRoles(unittest.TestCase):
    def test_main_and_sprint_are_maintained_spike_is_throwaway(self) -> None:
        self.assertEqual(roles.default_role("main"), roles.MAINTAINED)
        self.assertEqual(roles.default_role("sprint/v0.3.28"), roles.MAINTAINED)
        self.assertEqual(roles.default_role("spike/try-parser"), roles.THROWAWAY)
        self.assertIsNone(roles.default_role("feature/x"))
        self.assertIsNone(roles.default_role(None))

    def test_a_branch_with_no_record_takes_its_default(self) -> None:
        project = Project("spike/idea")
        self.addCleanup(project.close)
        self.assertEqual(roles.branch_role(project.archive, "spike/idea"),
                         {"branch": "spike/idea", "role": "throwaway", "source": "default"})
        self.assertEqual(roles.branch_role(project.archive, "feature/x")["source"], "undeclared")


class DeclaredRoles(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Project("feature/parser")
        self.addCleanup(self.project.close)

    def test_record_role_is_stored_on_the_topology_record(self) -> None:
        out = self.project.branches(record=True, role="maintained")
        self.assertEqual(out["role"], {"branch": "feature/parser", "role": "maintained",
                                       "source": "declared"})
        records = self.project.archive.select(kind="branch", subject="git-topology")
        self.assertEqual(records[-1]["data"]["role"], "maintained")
        self.assertEqual(records[-1]["data"]["branch"], "feature/parser")

    def test_the_newest_declaration_wins_and_overrides_the_default(self) -> None:
        operator_declares(self.project.archive, "feature/parser", "throwaway")
        self.assertEqual(roles.branch_role(self.project.archive, "feature/parser")["role"],
                         "throwaway")
        self.project.branches(record=True, role="maintained")
        self.assertEqual(roles.branch_role(self.project.archive, "feature/parser")["role"],
                         "maintained")
        self.project.branches(record=True)  # a plain record declares nothing
        self.assertEqual(roles.branch_role(self.project.archive, "feature/parser")["role"],
                         "maintained")

    def test_a_declaration_for_another_branch_does_not_leak(self) -> None:
        operator_declares(self.project.archive, "feature/parser", "throwaway")
        self.assertEqual(roles.branch_role(self.project.archive, "main")["role"], "maintained")

    def test_role_without_record_is_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            self.project.branches(role="throwaway")

    def test_the_bare_verb_reports_the_role(self) -> None:
        self.assertEqual(self.project.branches()["role"]["source"], "undeclared")

    def test_a_detached_head_cannot_declare(self) -> None:
        detached = Project(None)
        self.addCleanup(detached.close)
        with self.assertRaises(ArchiveError):
            detached.branches(record=True, role="maintained")


def operator_declares(archive, branch: str, role: str) -> None:
    """A git-topology record written with verified operator trust."""
    archive.append("branch", "git-topology", {"branch": branch, "role": role},
                   evidence=[], as_operator=True, operator_verified=True)


class OnlyTheOperatorLoosens(unittest.TestCase):
    """Review B2: declaring a spike switches the plan and test gates off, so
    an agent's declaration of it does not count; tightening always does."""

    def test_the_verb_refuses_an_agent_throwaway_on_a_maintained_branch(self) -> None:
        project = Project("main")
        self.addCleanup(project.close)
        with self.assertRaises(ArchiveError) as caught:
            project.branches(record=True, role="throwaway")
        self.assertIn("--as-operator", str(caught.exception))
        self.assertEqual(roles.branch_role(project.archive, "main")["role"], "maintained")

    def test_an_agent_trust_record_does_not_change_the_role(self) -> None:
        project = Project("main")
        self.addCleanup(project.close)
        project.archive.append("branch", "git-topology", {"branch": "main", "role": "throwaway"},
                               evidence=[])
        self.assertEqual(roles.branch_role(project.archive, "main"),
                         {"branch": "main", "role": "maintained", "source": "default"})
        project.archive.append("branch", "git-topology", {"branch": "feature/x",
                                                           "role": "throwaway"}, evidence=[])
        self.assertIsNone(roles.branch_role(project.archive, "feature/x")["role"])

    def test_a_verified_operator_declaration_counts(self) -> None:
        project = Project("main")
        self.addCleanup(project.close)
        with mock.patch("godmode_runtime.godmode_console._resolve_operator_verified",
                        return_value=True):
            out = project.branches(record=True, role="throwaway")
        self.assertEqual(out["role"]["role"], "throwaway")
        self.assertEqual(project.archive.select(kind="branch")[-1]["writer"], "operator")

    def test_tightening_needs_no_operator(self) -> None:
        project = Project("spike/idea")
        self.addCleanup(project.close)
        self.assertEqual(project.branches(record=True, role="maintained")["role"]["role"],
                         "maintained")

    def test_an_agent_cannot_undo_an_operator_tightening_of_a_spike(self) -> None:
        """Review round 2, F2: operator declares spike/idea maintained; an
        agent-trust throwaway record, or the verb without --as-operator,
        must leave it maintained."""
        project = Project("spike/idea")
        self.addCleanup(project.close)
        operator_declares(project.archive, "spike/idea", "maintained")
        self.assertEqual(roles.branch_role(project.archive, "spike/idea")["role"], "maintained")
        project.archive.append("branch", "git-topology",
                               {"branch": "spike/idea", "role": "throwaway"}, evidence=[])
        self.assertEqual(project.archive.select(kind="branch")[-1]["writer"], "agent")
        self.assertEqual(roles.branch_role(project.archive, "spike/idea")["role"], "maintained")
        with self.assertRaises(ArchiveError):
            project.branches(record=True, role="throwaway")
        self.assertEqual(roles.branch_role(project.archive, "spike/idea")["role"], "maintained")


class EditWithoutTest(unittest.TestCase):
    """The integrity monitor reads the role: a maintained branch's code change
    with no test change is named (advisory); a spike's is not."""

    def ctx(self, role: str | None, tests: list[str]) -> dict:
        return {"changed_production": ["src/app.py", "src/util.py"], "changed_tests": tests,
                "branch_role": {"branch": "main", "role": role, "source": "default"}}

    def test_maintained_code_change_without_a_test_is_an_advisory_finding(self) -> None:
        findings = integrity._edit_without_test(self.ctx("maintained", []))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["monitor"], "edit-without-test")
        self.assertFalse(findings[0]["blocking"])
        self.assertIn("src/app.py", findings[0]["detail"])

    def test_a_test_change_in_the_same_set_satisfies_it(self) -> None:
        self.assertEqual(integrity._edit_without_test(self.ctx("maintained", ["tests/test_app.py"])), [])

    def test_throwaway_and_undeclared_branches_are_not_held_to_it(self) -> None:
        self.assertEqual(integrity._edit_without_test(self.ctx("throwaway", [])), [])
        self.assertEqual(integrity._edit_without_test(self.ctx(None, [])), [])

    def test_the_monitor_is_registered_and_reads_the_archive_branch(self) -> None:
        self.assertIs(integrity.MONITORS["edit-without-test"], integrity._edit_without_test)
        project = Project("sprint/next")
        self.addCleanup(project.close)
        self.assertEqual(integrity._branch_role(project.archive)["role"], "maintained")


if __name__ == "__main__":
    unittest.main()

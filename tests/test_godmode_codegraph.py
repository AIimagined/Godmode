"""godmode-codegraph: the shipped skill's structure and its flow's commands.

Plan 7 Task 13 (NS-9): this skill routes to `atlas graph rebuild|query|
verify`, `atlas closure`, and `retest --run` - verbs that already exist and
already carry their own test suites. This module proves the skill bundle is
well-formed (frontmatter, PURPOSE.md citing a real seq:, both companion
files), and that every preflight command its Deterministic Execution Flow
names actually runs and exits the way the flow says it does, on a disposable
fixture project seeded with two obligation records - never the live project
archive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_forge import validate_skill  # noqa: E402
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import scrubbed_env  # noqa: E402

SKILL_DIR = PLUGIN_ROOT / "skills" / "godmode-codegraph"
GODMODE = PLUGIN_ROOT / "scripts" / "godmode.py"


@contextmanager
def _seeded_project():
    """A fixture project, initialized and seeded with two obligation records
    (`c`, and `b` blocked_by `c`) so `atlas graph query obligation:c` has a
    real dependent to find - the same shape `godmode_graph`'s own self-check
    seeds."""
    with tempfile.TemporaryDirectory(prefix="godmode-codegraph-") as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            archive.append("obligation", "c", {"status": "open", "blocked_by": []})
            archive.append("obligation", "b", {"status": "open", "blocked_by": ["c"]})
            yield project, state


def _run(project: Path, state: Path, *args: str) -> subprocess.CompletedProcess:
    # The attendance ratchet requires a scrubbed host environment for any
    # spawn of the shipped CLI: an inherited host environment leaks the
    # operator session and its attendance signals into the child.
    environment = scrubbed_env(GODMODE_STATE_HOME=str(state))
    return subprocess.run(
        [sys.executable, str(GODMODE), "--project", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=environment,
    )


class SkillBundleTests(unittest.TestCase):
    def test_structure_validates(self) -> None:
        result = validate_skill(SKILL_DIR)
        self.assertTrue(result["valid"], result)
        self.assertGreaterEqual(result["positive_cases"], 2)
        self.assertGreaterEqual(result["near_negative_cases"], 2)
        self.assertGreaterEqual(result["assertions"], 1)

    def test_frontmatter_lint_passes_with_no_findings(self) -> None:
        result = lint_frontmatter(SKILL_DIR)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["findings"], [])

    def test_purpose_cites_a_real_seq(self) -> None:
        text = (SKILL_DIR / "PURPOSE.md").read_text(encoding="utf-8")
        self.assertIn("seq:", text)

    def test_description_carries_a_negative_scope_clause(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Not for", text)

    def test_evals_file_has_the_required_rows(self) -> None:
        data = json.loads((SKILL_DIR / "godmode-evals.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["routing"]["positive"]), 2)
        self.assertGreaterEqual(len(data["routing"]["near_negative"]), 2)
        self.assertTrue(data["behavior_assertions"])


class FlowStepTests(unittest.TestCase):
    """Every preflight command the flow names, run on a seeded fixture project."""

    def test_step1_verify_refuses_before_any_snapshot_exists(self) -> None:
        """B7: `verify` is the flow's step 1, run before any `rebuild` has
        ever saved a snapshot - so the "no snapshot" branch SKILL.md:32-37
        describes is actually reachable, not defeated by a prior rebuild."""
        with _seeded_project() as (project, state):
            done = _run(project, state, "atlas", "graph", "verify")
            self.assertEqual(done.returncode, 1, done.stderr)
            payload = json.loads(done.stdout)
            self.assertFalse(payload["verified"])
            self.assertIn("no graph snapshot found", payload["reason"])

    def test_step1_verify_names_a_stale_snapshot_without_overwriting_it(self) -> None:
        """B7: after a rebuild+save, a new archive record makes the saved
        snapshot stale; `verify` must name that (not silently pass) and must
        not itself rewrite the snapshot - only `rebuild` (step 2) does."""
        with _seeded_project() as (project, state):
            self.assertEqual(_run(project, state, "atlas", "graph", "rebuild").returncode, 0)
            environment = dict(os.environ)
            environment["GODMODE_STATE_HOME"] = str(state)
            archive = Chronicle(resolve_anchor(project))
            archive.append("obligation", "d", {"status": "open", "blocked_by": ["c"]})
            done = _run(project, state, "atlas", "graph", "verify")
            self.assertEqual(done.returncode, 1, done.stderr)
            payload = json.loads(done.stdout)
            self.assertFalse(payload["verified"])
            self.assertIn("stale", payload["reason"])
            # verify must not have rewritten the saved snapshot: a plain
            # query against the (still-stale) saved snapshot still finds
            # only the two originally-seeded nodes, not the third.
            query = _run(project, state, "atlas", "graph", "query", "obligation:d")
            self.assertEqual(query.returncode, 1, query.stderr)
            self.assertTrue(json.loads(query.stdout)["unknown_node"])

    def test_step2_rebuild_derives_the_seeded_edge(self) -> None:
        with _seeded_project() as (project, state):
            done = _run(project, state, "atlas", "graph", "rebuild")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload["nodes"], 2)
            self.assertEqual(payload["edges"], 1)
            # rebuilding then satisfies the step-1 proof.
            verified = _run(project, state, "atlas", "graph", "verify")
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["verified"])

    def test_step3_query_finds_the_dependent(self) -> None:
        with _seeded_project() as (project, state):
            self.assertEqual(_run(project, state, "atlas", "graph", "rebuild").returncode, 0)
            done = _run(project, state, "atlas", "graph", "query", "obligation:c")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload["impact"], [{"node": "obligation:b", "distance": 1}])

    def test_step3_fallback_unknown_node_refuses_rather_than_guessing(self) -> None:
        with _seeded_project() as (project, state):
            self.assertEqual(_run(project, state, "atlas", "graph", "rebuild").returncode, 0)
            done = _run(project, state, "atlas", "graph", "query", "obligation:nonexistent")
            self.assertEqual(done.returncode, 1, done.stderr)
            payload = json.loads(done.stdout)
            self.assertTrue(payload["unknown_node"])
            self.assertTrue(payload["refused"])

    def test_step4_closure_on_an_untouched_tree_is_clean(self) -> None:
        with _seeded_project() as (project, state):
            self.assertEqual(_run(project, state, "atlas", "graph", "rebuild").returncode, 0)
            done = _run(project, state, "atlas", "closure")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload["verdict"], "nothing-changed")

    def test_step4_closure_refuses_on_an_unverified_snapshot(self) -> None:
        """B7: closure re-checks step 1's proof itself - a stale saved
        snapshot must refuse rather than answer from drifted evidence."""
        with _seeded_project() as (project, state):
            self.assertEqual(_run(project, state, "atlas", "graph", "rebuild").returncode, 0)
            archive = Chronicle(resolve_anchor(project))
            archive.append("obligation", "d", {"status": "open", "blocked_by": ["c"]})
            done = _run(project, state, "atlas", "closure")
            self.assertEqual(done.returncode, 1, done.stderr)
            payload = json.loads(done.stdout)
            self.assertTrue(payload["refused"])
            self.assertIn("unverified", payload["reason"])

    def test_step5_retest_run_needs_an_open_session_first(self) -> None:
        with _seeded_project() as (project, state):
            without_session = _run(project, state, "retest", "--run")
            self.assertEqual(without_session.returncode, 2, without_session.stderr)
            self.assertEqual(_run(project, state, "session", "open").returncode, 0)
            done = _run(project, state, "retest", "--run")
            self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()

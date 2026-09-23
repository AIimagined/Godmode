"""NS-3: a typed, time-valid evidence graph rebuilt from the archive's own
records - never a second store, never written directly.

`godmode_graph.rebuild(archive)` derives `depends_on` edges from obligations'
`blocked_by` and sprint items' `depends_on`, `retested_by` edges from
`check:retest:*` attestations' `cmd:` evidence, `supersedes` edges from
register `supersedes` and claim `resolves`, and `cites` edges from claim
evidence. `query()` walks the snapshot (never a fresh rebuild - the design's
own scale rule) for impact and required retests. `verify()` fails the moment
a fresh rebuild's hash disagrees with the last snapshot, and `atlas closure`
must refuse to decide against an unverified one.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime import godmode_graph as graph  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    """One `cmd_atlas`-driven CLI call, JSON in, JSON out (fix round 1, S3)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


class RebuildDeterminismTests(unittest.TestCase):
    def test_rebuild_twice_is_byte_identical(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "ship the thing", {"status": "open", "blocked_by": []})
            archive.append("claim", "it works", {"grade": "hypothesis"}, evidence=["file:a.py#L1"])
            first = graph.rebuild(archive)
            second = graph.rebuild(archive)
            self.assertEqual(first["hash"], second["hash"])
            self.assertEqual(first, second)

    def test_empty_archive_still_hashes(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            built = graph.rebuild(archive)
            self.assertEqual(built["nodes"], {})
            self.assertEqual(built["edges"], [])
            self.assertTrue(built["hash"])


class ObligationDependsOnTests(unittest.TestCase):
    def test_blocked_by_becomes_a_depends_on_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "the blocker", {"status": "open", "blocked_by": []})
            archive.append("obligation", "the dependent", {"status": "open",
                                                            "blocked_by": ["the blocker"]})
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.DEPENDS_ON]
            self.assertEqual(len(edges), 1)
            edge = edges[0]
            self.assertEqual(edge["src"], "obligation:the dependent")
            self.assertEqual(edge["dst"], "obligation:the blocker")
            self.assertIsNone(edge["valid_to"])

    def test_closing_the_dependent_retires_its_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "the blocker", {"status": "open", "blocked_by": []})
            archive.append("obligation", "the dependent", {"status": "open",
                                                            "blocked_by": ["the blocker"]})
            closing = archive.append("obligation", "the dependent",
                                     {"status": "closed", "blocked_by": ["the blocker"]},
                                     evidence=["file:a.py#L1"])
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.DEPENDS_ON]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["valid_to"], closing["sequence"])


class SprintDependsOnTests(unittest.TestCase):
    def test_sprint_item_depends_on_becomes_an_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("sprint", "item-a", {"state": "ready", "depends_on": []})
            archive.append("sprint", "item-b", {"state": "ready", "depends_on": ["item-a"]})
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.DEPENDS_ON
                     and e["src"] == "sprint:item-b"]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["dst"], "sprint:item-a")


class RetestedByTests(unittest.TestCase):
    def test_a_retest_attestation_cites_its_test_module(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "attestation", "check:retest:unittest",
                {"status": "ran"},
                evidence=["cmd:python -m unittest tests.test_rotate"],
            )
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.RETESTED_BY]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["src"], "module:tests.test_rotate")
            self.assertEqual(edges[0]["dst"], f"attestation:{record['sequence']}")
            self.assertIsNone(edges[0]["valid_to"])

    def test_an_unrelated_attestation_adds_no_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("attestation", "check:lint", {"status": "ran"},
                            evidence=["cmd:python -m flake8"])
            built = graph.rebuild(archive)
            self.assertEqual([e for e in built["edges"] if e["type"] == graph.RETESTED_BY], [])


class SupersedesTests(unittest.TestCase):
    def test_register_supersedes_becomes_an_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            from godmode_runtime.godmode_register import set_state
            established = set_state(archive, "domain-a", "key-a", "established", ["witness:1"])
            superseded = set_state(archive, "domain-a", "key-a", "superseded", ["witness:2"],
                                   supersedes=established["sequence"])
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.SUPERSEDES]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["src"], f"decision:{superseded['sequence']}")
            self.assertEqual(edges[0]["dst"], f"decision:{established['sequence']}")

    def test_a_claim_resolution_becomes_a_supersedes_edge(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            original = archive.append("claim", "the number is 5", {"grade": "hypothesis"})
            resolution = archive.append(
                "claim", f"resolution of seq:{original['sequence']}: held",
                {"resolves": original["sequence"]}, evidence=["file:a.py#L1"])
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.SUPERSEDES]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["src"], f"claim:{resolution['sequence']}")
            self.assertEqual(edges[0]["dst"], f"claim:{original['sequence']}")


class CitesTests(unittest.TestCase):
    def test_a_claim_cites_its_evidence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append("claim", "it compiles", {"grade": "observed"},
                                    evidence=["file:a.py#L1", "cmd:pytest"])
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.CITES]
            self.assertEqual({e["dst"] for e in edges}, {"cite:file:a.py#L1", "cite:cmd:pytest"})
            self.assertTrue(all(e["src"] == f"claim:{record['sequence']}" for e in edges))


class GraphEdgeNeverWrittenTests(unittest.TestCase):
    def test_append_refuses_the_graph_edge_kind(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("graph_edge", "anything", {"type": "depends_on"})


class QueryTests(unittest.TestCase):
    """Fixture: a -> b -> c (a depends on b, b depends on c) plus a retest
    attestation covering `tests.test_c`. Hand-computed: querying `c` for
    impact at depth 3 finds b at distance 1 and a at distance 2; querying
    `module:tests.test_c` for must_retest finds the attestation at distance 1.
    """

    def _fixture(self, archive) -> dict:
        archive.append("obligation", "c", {"status": "open", "blocked_by": []})
        archive.append("obligation", "b", {"status": "open", "blocked_by": ["c"]})
        archive.append("obligation", "a", {"status": "open", "blocked_by": ["b"]})
        record = archive.append(
            "attestation", "check:retest:unittest", {"status": "ran"},
            evidence=["cmd:python -m unittest tests.test_c"])
        return graph.rebuild(archive)

    def test_impact_query_matches_hand_computed_set(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            built = self._fixture(archive)
            result = graph.query(built, "obligation:c", depth=3)
            impact = {(entry["node"], entry["distance"]) for entry in result["impact"]}
            self.assertEqual(impact, {("obligation:b", 1), ("obligation:a", 2)})

    def test_impact_query_is_bounded_by_depth(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            built = self._fixture(archive)
            result = graph.query(built, "obligation:c", depth=1)
            impact = {entry["node"] for entry in result["impact"]}
            self.assertEqual(impact, {"obligation:b"})

    def test_must_retest_finds_the_covering_attestation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            built = self._fixture(archive)
            result = graph.query(built, "module:tests.test_c", depth=3)
            must_retest = {entry["node"] for entry in result["must_retest"]}
            self.assertEqual(len(must_retest), 1)
            self.assertTrue(next(iter(must_retest)).startswith("attestation:"))

    def test_a_retired_depends_on_edge_is_excluded_from_impact(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "c", {"status": "open", "blocked_by": []})
            archive.append("obligation", "b", {"status": "open", "blocked_by": ["c"]})
            archive.append("obligation", "b", {"status": "closed", "blocked_by": ["c"]},
                           evidence=["file:a.py#L1"])
            built = graph.rebuild(archive)
            result = graph.query(built, "obligation:c", depth=3)
            self.assertEqual(result["impact"], [])


class SnapshotAndVerifyTests(unittest.TestCase):
    def test_verify_with_no_snapshot_is_unverified(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "x", {"status": "open", "blocked_by": []})
            outcome = graph.verify(archive)
            self.assertFalse(outcome["verified"])

    def test_rebuild_and_save_then_verify_passes(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "x", {"status": "open", "blocked_by": []})
            built = graph.rebuild(archive)
            graph.save_snapshot(built, archive)
            outcome = graph.verify(archive)
            self.assertTrue(outcome["verified"])

    def test_a_new_record_after_the_snapshot_fails_verify(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "x", {"status": "open", "blocked_by": []})
            built = graph.rebuild(archive)
            graph.save_snapshot(built, archive)
            archive.append("obligation", "y", {"status": "open", "blocked_by": []})
            outcome = graph.verify(archive)
            self.assertFalse(outcome["verified"])

    def test_deleting_a_source_record_fails_verify(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            archive.append("obligation", "x", {"status": "open", "blocked_by": []})
            archive.append("obligation", "y", {"status": "open", "blocked_by": []})
            archive.append("obligation", "z", {"status": "open", "blocked_by": []})
            built = graph.rebuild(archive)
            graph.save_snapshot(built, archive)
            event_files = sorted(archive.events.glob("*.godmode.json"))
            self.assertGreaterEqual(len(event_files), 3)
            event_files[1].unlink()
            fresh = Chronicle(anchor)
            outcome = graph.verify(fresh)
            self.assertFalse(outcome["verified"])


class ClosureGraphGateTests(unittest.TestCase):
    """Fix round 1, S3: the closure refusal gate driven through `cmd_atlas`
    itself, not `godmode_graph.verify` called directly - the design's own
    headline behaviour ("any `atlas closure` decision made against an
    unverified graph is rejected") shipped with nothing exercising the CLI
    path that actually enforces it."""

    def test_closure_is_refused_with_no_verified_snapshot(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(project, "atlas", "closure", "some/file.py")
            self.assertEqual(code, 1)
            self.assertTrue(payload.get("refused"))
            self.assertEqual(payload.get("reason"), "graph unverified: run atlas graph rebuild")

    def test_closure_passes_after_rebuild(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, _payload = _run(project, "atlas", "graph", "rebuild")
            self.assertEqual(code, 0)
            code, payload = _run(project, "atlas", "closure", "some/file.py")
            self.assertEqual(code, 0)
            self.assertNotIn("refused", payload)

    def test_closure_is_refused_again_after_a_further_record(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, _payload = _run(project, "atlas", "graph", "rebuild")
            self.assertEqual(code, 0)
            archive.append("obligation", "drift", {"status": "open", "blocked_by": []})
            code, payload = _run(project, "atlas", "closure", "some/file.py")
            self.assertEqual(code, 1)
            self.assertTrue(payload.get("refused"))
            self.assertEqual(payload.get("reason"), "graph unverified: run atlas graph rebuild")


class FileToModuleBridgeTests(unittest.TestCase):
    """Fix round 1, S1: `atlas graph query` bridges a `file:` node (or a
    bare id that resolves as a real project-relative path) to the
    `module:` nodes `godmode_retest.retest_module_names` says pin it, and
    reports `unknown_node` when nothing in the snapshot or the bridge
    answers for it."""

    def _seed(self, project: Path) -> None:
        """Git-init BEFORE anything godmode-shaped touches the project:
        `isolated_project()`'s own `archive`/`anchor` are resolved at
        NON-GIT identity before this method ever runs, and `_run` below
        spins up a genuinely fresh `Runtime` per call (the same as a real
        CLI invocation) that re-resolves identity from what is on disk
        NOW - a git-init after that pre-resolved archive already has
        records is exactly the "project became a Git repository after
        these records were written" mismatch `godmode_anchor` itself
        refuses to paper over. So this never touches the fixture's own
        `archive`/`anchor` at all: `_run(project, "init")` and a freshly
        resolved `Chronicle` are the only writers, both AFTER git exists.
        """
        (project / "widget.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (project / "tests").mkdir()
        (project / "tests" / "test_widget.py").write_text("import widget\n", encoding="utf-8")
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "seed")
        code, _payload = _run(project, "init")
        self.assertEqual(code, 0)
        from godmode_runtime.godmode_anchor import resolve_anchor

        archive = Chronicle(resolve_anchor(project))
        archive.append(
            "attestation", "check:retest:unittest",
            {"status": "ran", "modules": ["tests.test_widget"]},
            evidence=["cmd:python -m unittest tests.test_widget"],
        )
        code, _payload = _run(project, "atlas", "graph", "rebuild")
        self.assertEqual(code, 0)

    def test_a_file_prefixed_node_bridges_to_its_covering_module(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            self._seed(project)
            code, payload = _run(project, "atlas", "graph", "query", "file:widget.py")
            self.assertEqual(code, 0)
            self.assertNotIn("unknown_node", payload)
            self.assertEqual([e["node"] for e in payload["must_retest"]], ["attestation:1"])

    def test_a_bare_path_that_resolves_on_disk_also_bridges(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            self._seed(project)
            code, payload = _run(project, "atlas", "graph", "query", "widget.py")
            self.assertEqual(code, 0)
            self.assertEqual([e["node"] for e in payload["must_retest"]], ["attestation:1"])

    def test_an_unknown_node_is_reported_not_silent(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            self._seed(project)
            code, payload = _run(project, "atlas", "graph", "query", "totally:made-up")
            self.assertEqual(code, 1)
            self.assertTrue(payload.get("unknown_node"))
            self.assertEqual(payload["impact"], [])
            self.assertEqual(payload["must_retest"], [])
            # Matches the sibling refusal shape (the missing-snapshot
            # refusal above) instead of only its own bespoke flag.
            self.assertTrue(payload.get("refused"))
            self.assertEqual(payload.get("reason"), "unknown node: totally:made-up")

    def test_depth_zero_is_refused_at_the_parser(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            self._seed(project)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                with self.assertRaises(SystemExit):
                    console_main(["--project", str(project), "--json",
                                  "atlas", "graph", "query", "widget.py", "--depth", "0"])


if __name__ == "__main__":
    unittest.main()

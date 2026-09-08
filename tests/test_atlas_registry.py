"""Atlas registry, relation-bounded traversal, and the persisted index.

Each class targets one failure mode: a language that silently needs core edits
to become visible, a blast radius that mixes callers with doc mentions, and a
saved index that keeps answering after the files underneath it have moved on.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_atlas import (  # noqa: E402
    DOCUMENTS,
    EXTRACTED,
    EXTRACTORS,
    IMPORTS,
    INFERRED,
    TESTED_BY,
    Edge,
    Symbol,
    build,
    load_index,
    register_extractor,
    save_index,
)


class ExtractorRegistryTests(unittest.TestCase):
    def test_registered_extractor_handles_new_suffix_without_core_edits(self) -> None:
        # The whole point of the registry: a third language is one register call,
        # not a dispatch edit inside build().
        def xyz_extractor(path: str, text: str) -> tuple[list[Symbol], list[Edge]]:
            return (
                [Symbol(name="from_xyz", kind="function", path=path, line=1)],
                [Edge(f"{path}::<module>", "core::<module>", IMPORTS, EXTRACTED, 1)],
            )

        register_extractor(".xyz", xyz_extractor)
        self.addCleanup(EXTRACTORS.pop, ".xyz", None)

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "widget.xyz").write_text("whatever\n", encoding="utf-8")
            (project / "core.py").write_text("def rotate():\n    return 1\n", encoding="utf-8")

            atlas = build(project)
            self.assertIn("widget.xyz", atlas.files)
            self.assertIn("from_xyz", {s.name for s in atlas.symbols})
            # The registered extractor's edges participate in traversal like any
            # native ones; the new language is a first-class citizen immediately.
            impact = atlas.affected("core")
            self.assertTrue(any("widget.xyz" in d["id"] for d in impact["dependents"]))

    def test_default_dispatch_is_unchanged_for_existing_suffixes(self) -> None:
        # Moving to a registry must not reroute existing languages: Python stays
        # on the ast parser (extracted facts), unknown code stays on the generic
        # shape matcher (inferred leads).
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "core.py").write_text("import os\n", encoding="utf-8")
            (project / "ui.ts").write_text("import { x } from './core';\n", encoding="utf-8")

            atlas = build(project)
            by_source = {e.source.split("::")[0]: e.evidence for e in atlas.edges
                         if e.relation == IMPORTS}
            self.assertEqual(by_source.get("core.py"), EXTRACTED)
            self.assertEqual(by_source.get("ui.ts"), INFERRED)

    def test_registration_overrides_the_generic_fallback(self) -> None:
        # A team with a real parser for a suffix must be able to displace the
        # regex guesser, otherwise the registry only adds languages, never fixes one.
        register_extractor(".ts", lambda path, text: (
            [Symbol(name="typed_symbol", kind="function", path=path, line=1)], []))
        self.addCleanup(EXTRACTORS.pop, ".ts", None)

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "ui.ts").write_text("export function renderWidget() {}\n", encoding="utf-8")
            names = {s.name for s in build(project).symbols}
            self.assertIn("typed_symbol", names)
            self.assertNotIn("renderWidget", names)


class RelationTraversalTests(unittest.TestCase):
    def _tree(self, raw: str) -> Path:
        project = Path(raw)
        (project / "engine.py").write_text("def spin():\n    return 1\n", encoding="utf-8")
        (project / "app.py").write_text("import engine\n", encoding="utf-8")
        (project / "test_engine.py").write_text("import engine\n", encoding="utf-8")
        (project / "README.md").write_text("The engine module spins things.\n", encoding="utf-8")
        return project

    def test_test_import_yields_a_tested_by_edge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            atlas = build(self._tree(raw))
            tested = [e for e in atlas.edges if e.relation == TESTED_BY]
            self.assertTrue(any(e.source.startswith("test_engine.py")
                                and "engine" in e.target for e in tested), atlas.edges)

    def test_tests_directory_pattern_also_counts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "engine.py").write_text("def spin():\n    return 1\n", encoding="utf-8")
            (project / "tests").mkdir()
            (project / "tests" / "engine_suite.py").write_text("import engine\n", encoding="utf-8")
            atlas = build(project)
            self.assertTrue(any(e.relation == TESTED_BY and e.source.startswith("tests/")
                                for e in atlas.edges), atlas.edges)

    def test_markdown_mention_yields_a_documents_edge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            atlas = build(self._tree(raw))
            docs = [e for e in atlas.edges if e.relation == DOCUMENTS]
            self.assertTrue(any(e.source == "README.md" and "engine" in e.target
                                for e in docs), atlas.edges)
            # A name match in prose is a lead, not a parsed fact.
            self.assertTrue(all(e.evidence == INFERRED for e in docs))

    def test_relations_filter_returns_only_doc_edges(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            impact = build(self._tree(raw)).affected(
                "engine", evidence=None, relations={DOCUMENTS})
            self.assertEqual([d["id"] for d in impact["dependents"]], ["README.md"])
            self.assertEqual([d["id"] for d in impact["docs"]], ["README.md"])
            self.assertEqual(impact["callers"], [])
            self.assertEqual(impact["tests"], [])

    def test_buckets_separate_callers_tests_and_docs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            impact = build(self._tree(raw)).affected("engine", evidence=None)
            callers = {d["id"] for d in impact["callers"]}
            tests = {d["id"] for d in impact["tests"]}
            docs = {d["id"] for d in impact["docs"]}
            self.assertTrue(any("app.py" in c for c in callers), impact)
            self.assertTrue(any("test_engine.py" in t for t in tests), impact)
            self.assertEqual(docs, {"README.md"}, impact)
            # A test file is also an importer; the buckets overlap by design
            # because "who imports this" and "what tests this" are both true.
            self.assertTrue(any("test_engine.py" in c for c in callers), impact)

    def test_legacy_contract_is_preserved(self) -> None:
        # godmode_console calls affected(symbol, depth=..., evidence=...) and
        # serialises the dict; the pre-registry fields must survive untouched.
        with tempfile.TemporaryDirectory() as raw:
            impact = build(self._tree(raw)).affected("engine", depth=2, evidence="extracted")
            for key in ("target", "depth", "evidence", "dependents", "count"):
                self.assertIn(key, impact)
            self.assertEqual(impact["evidence"], "extracted")
            for dependent in impact["dependents"]:
                self.assertIn("id", dependent)
                self.assertIn("distance", dependent)
            # Extracted-only default still excludes the inferred doc mention.
            self.assertFalse(any(d["id"] == "README.md" for d in impact["dependents"]))


class PersistedIndexTests(unittest.TestCase):
    def test_round_trip_reports_full_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "engine.py").write_text("def spin():\n    return 1\n", encoding="utf-8")
            (project / "app.py").write_text("import engine\n", encoding="utf-8")
            atlas = build(project)
            index_path = project / "atlas-index.json"

            summary = save_index(atlas, index_path)
            self.assertEqual(summary["files"], len(atlas.files))
            self.assertEqual(summary["symbols"], len(atlas.symbols))

            report = load_index(index_path, project)
            self.assertEqual(sorted(report["fresh"]), sorted(atlas.files))
            self.assertEqual(report["stale"], [])
            self.assertEqual(report["missing"], [])
            self.assertEqual(report["confidence"], 1.0)
            self.assertEqual(report["atlas"]["symbols"], len(atlas.symbols))
            self.assertEqual(report["atlas"]["edges"], len(atlas.edges))

    def test_mutation_and_deletion_reduce_confidence(self) -> None:
        # Staleness must come from content, not clocks: the mutated file is
        # rewritten with different bytes, and that alone must flip it to stale.
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "engine.py").write_text("def spin():\n    return 1\n", encoding="utf-8")
            (project / "app.py").write_text("import engine\n", encoding="utf-8")
            (project / "extra.py").write_text("import engine\n", encoding="utf-8")
            index_path = project / "atlas-index.json"
            save_index(build(project), index_path)

            (project / "engine.py").write_text("def spin():\n    return 2\n", encoding="utf-8")
            (project / "extra.py").unlink()

            report = load_index(index_path, project)
            self.assertEqual(report["stale"], ["engine.py"])
            self.assertEqual(report["missing"], ["extra.py"])
            self.assertEqual(report["fresh"], ["app.py"])
            self.assertEqual(report["confidence"], round(1 / 3, 2))

    def test_serialisation_is_deterministic_json(self) -> None:
        # A diffable index only works if the same atlas always serialises the
        # same way; key order must never depend on dict insertion history.
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "engine.py").write_text("def spin():\n    return 1\n", encoding="utf-8")
            index_path = project / "atlas-index.json"
            save_index(build(project), index_path)
            text = index_path.read_text(encoding="utf-8")
            payload = json.loads(text)
            self.assertEqual(text, json.dumps(payload, indent=2, sort_keys=True))
            self.assertIn("built_at", payload)
            self.assertIn("engine.py", payload["files"])


if __name__ == "__main__":
    unittest.main()


class BuildCeilingTests(unittest.TestCase):
    """Twelfth field report: `atlas map` ran past five minutes on a 2,176-file
    repo with no budget and no partial result. The documentation linker was the
    hotspot (one regex pass per document per module), and a build with no
    ceiling has no honest answer on a repo it cannot finish."""

    def test_documentation_scan_cost_is_per_document_not_per_module(self) -> None:
        import time
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            for index in range(400):
                (project / f"module_{index:03d}.py").write_text(
                    "def run():\n    return 1\n", encoding="utf-8")
            prose = ("lorem ipsum dolor sit amet, consectetur adipiscing elit " * 600)
            for index in range(200):
                (project / f"doc_{index:03d}.md").write_text(
                    f"# Notes\n{prose}\nSee module_{index:03d} and module_399.\n",
                    encoding="utf-8")
            started = time.monotonic()
            atlas = build(project)
            elapsed = time.monotonic() - started
            docs = [e for e in atlas.edges if e.relation == DOCUMENTS]
            self.assertTrue(any(e.source == "doc_007.md" and "module_007.py" in e.target
                                and e.line == 3 for e in docs), docs[:5])
            self.assertEqual(sum(1 for e in docs if "module_399.py" in e.target), 200)
            self.assertLess(elapsed, 10.0, f"documentation scan took {elapsed:.1f}s")

    def test_time_budget_leaves_a_partial_map_with_a_stated_gap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "alpha.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            (project / "beta.py").write_text("import alpha\n", encoding="utf-8")
            atlas = build(project, budget_seconds=0.0)
            self.assertEqual(atlas.files, [])
            self.assertEqual(atlas.gap["unscanned"], 2)
            self.assertIn("budget", atlas.gap["reason"])
            self.assertEqual(atlas.view()["gap"], atlas.gap)
            # No budget: no gap to state.
            self.assertIsNone(build(project).gap)
            self.assertNotIn("gap", build(project).view())

    def test_a_coarse_clock_still_honours_a_zero_budget(self) -> None:
        """CI 2026-09-08: Windows Python 3.11's monotonic clock ticks every
        15.6 ms, so `elapsed > 0.0` read false for the first files and a zero
        budget scanned them. A budget already spent is spent at zero."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "alpha.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            with mock.patch("godmode_runtime.godmode_atlas.time.monotonic", return_value=100.0):
                atlas = build(project, budget_seconds=0.0)
            self.assertEqual(atlas.files, [])
            self.assertEqual(atlas.gap["unscanned"], 1)

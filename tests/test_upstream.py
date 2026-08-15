"""B3-1 (GAP-1): upstream/vendor capability-and-doctrine diff.

Red-first fixtures throughout: a fake installed Python distribution is built
under a temporary site directory (a real `.dist-info` + a real importable
module, not a mocked `importlib.metadata`), so `resolve_python_package`
exercises the actual stdlib resolution path these tests claim to cover.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import ArchiveError, GodmodeError  # noqa: E402
from godmode_runtime.godmode_upstream import (  # noqa: E402
    BEHAVIOR_VERDICTS,
    DISPOSITIONS,
    CHARTER_RULE_TEMPLATE,
    diff_against_project,
    gate_applies,
    record_upstream_diff,
    required_scope,
    resolve_node_package,
    resolve_python_package,
    resolve_vendored_tree,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _install_fake_package(site_dir: Path, name: str, version: str,
                           module_source: str, top_level: str | None = None) -> None:
    """A real `.dist-info` + a real importable module under `site_dir` -
    exactly what `resolve_python_package` reads, not a mock of it."""
    distinfo = site_dir / f"{name}-{version}.dist-info"
    distinfo.mkdir(parents=True)
    (distinfo / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")
    (distinfo / "top_level.txt").write_text((top_level or name) + "\n", encoding="utf-8")
    (site_dir / f"{top_level or name}.py").write_text(module_source, encoding="utf-8")


class _SitePackage(unittest.TestCase):
    """Base class: installs a fake `fixturepkg` distribution onto `sys.path`
    for the duration of one test, and reliably removes it afterward."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.site = self.base / "site"
        self.site.mkdir()
        _install_fake_package(
            self.site, "fixturepkg", "1.4.0",
            "__all__ = ['rotate_widget', 'WidgetStore', 'DEFAULT_TIMEOUT']\n"
            "DEFAULT_TIMEOUT = 30\n"
            "def rotate_widget():\n    return 1\n"
            "class WidgetStore:\n    pass\n",
        )
        sys.path.insert(0, str(self.site))

    def tearDown(self) -> None:
        if str(self.site) in sys.path:
            sys.path.remove(str(self.site))
        sys.modules.pop("fixturepkg", None)
        self._tmp.cleanup()


class ResolvePythonPackageTests(_SitePackage):
    def test_an_installed_package_resolves_its_version_and_public_symbols(self) -> None:
        resolved = resolve_python_package("fixturepkg")
        self.assertTrue(resolved["resolved"])
        self.assertTrue(resolved["module_import"])
        self.assertEqual(resolved["version"], "1.4.0")
        self.assertIn("rotate_widget", resolved["symbols"])
        self.assertIn("WidgetStore", resolved["symbols"])
        self.assertFalse(resolved["truncated"])

    def test_an_uninstalled_package_is_a_stated_gap_never_a_guess(self) -> None:
        missing = resolve_python_package("definitely-not-installed-anywhere-xyz")
        self.assertFalse(missing["resolved"])
        self.assertTrue(missing["reason"])
        gap = diff_against_project(missing, self.base)
        self.assertEqual(gap["verdict"], "stated-gap")
        self.assertEqual(gap["reason"], missing["reason"])
        self.assertEqual(gap["findings"], [])

    def test_enumeration_cap_is_loud_when_it_bites(self) -> None:
        """The full population is measured before the cap truncates it - a
        capped enumeration must say so, never read as complete (the
        `godmode_egress.scan_project` loud-cap idiom)."""
        import godmode_runtime.godmode_upstream as upstream_module

        many_names = [f"symbol_{i}" for i in range(20)]
        source = "__all__ = " + repr(many_names) + "\n"
        source += "\n".join(f"def {name}():\n    return 1\n" for name in many_names)
        _install_fake_package(self.site, "bigpkg", "1.0.0", source)

        original_cap = upstream_module.MAX_SYMBOLS_ENUMERATED
        upstream_module.MAX_SYMBOLS_ENUMERATED = 5
        try:
            resolved = resolve_python_package("bigpkg")
        finally:
            upstream_module.MAX_SYMBOLS_ENUMERATED = original_cap
        self.assertTrue(resolved["truncated"], resolved)
        self.assertEqual(resolved["symbols_full_count"], 20)
        self.assertEqual(len(resolved["symbols"]), 5)


class DiffAgainstProjectTests(_SitePackage):
    def test_project_local_equivalents_are_matched_not_flagged(self) -> None:
        project = self.base / "project"
        project.mkdir()
        (project / "app.py").write_text(
            "def rotate_widget():\n    return 2\n", encoding="utf-8")

        resolved = resolve_python_package("fixturepkg")
        diff = diff_against_project(resolved, project)

        self.assertEqual(diff["verdict"], "findings-present")
        matched_names = {m["upstream_symbol"] for m in diff["matched"]}
        finding_names = {f["upstream_symbol"] for f in diff["findings"]}
        self.assertIn("rotate_widget", matched_names)
        self.assertIn("WidgetStore", finding_names)
        for finding in diff["findings"]:
            self.assertIsNone(finding["disposition"])
            self.assertIsNone(finding["behavior_verdict"])

    def test_a_constant_finding_carries_a_note_surfacing_the_matching_boundary(self) -> None:
        """Round-1 review Minor #1: the function/class-only matching
        boundary must be visible in actual output, not only in the module
        docstring - a JSON consumer that never reads source still learns a
        finding may already be covered by a same-purpose constant."""
        # Only rotate_widget has a project-side equivalent: WidgetStore (a
        # class) and DEFAULT_TIMEOUT (a constant) both stay findings, so the
        # note's presence can be contrasted against a genuine class finding
        # in the same diff, not asserted in isolation.
        project = self.base / "project"
        project.mkdir()
        (project / "app.py").write_text(
            "def rotate_widget():\n    return 2\n", encoding="utf-8")
        resolved = resolve_python_package("fixturepkg")
        self.assertEqual(resolved["symbol_kinds"]["DEFAULT_TIMEOUT"], "value")
        self.assertEqual(resolved["symbol_kinds"]["WidgetStore"], "class")

        diff = diff_against_project(resolved, project)
        by_symbol = {f["upstream_symbol"]: f for f in diff["findings"]}
        self.assertEqual(set(by_symbol), {"WidgetStore", "DEFAULT_TIMEOUT"})

        timeout_finding = by_symbol["DEFAULT_TIMEOUT"]
        self.assertEqual(timeout_finding["upstream_symbol_kind"], "value")
        self.assertIn("non-callable value", timeout_finding["note"])
        self.assertIn("constant", timeout_finding["note"])

        # A genuine class finding never gets the constant-shaped note - the
        # field only appears where the boundary actually applies.
        class_finding = by_symbol["WidgetStore"]
        self.assertEqual(class_finding["upstream_symbol_kind"], "class")
        self.assertNotIn("note", class_finding)

    def test_full_coverage_reports_no_findings(self) -> None:
        # A package whose __all__ names only functions/classes: godmode_atlas
        # (reused unmodified here, per the module's "import, don't duplicate"
        # design) tracks function/class symbols only, so a constant like
        # fixturepkg's own DEFAULT_TIMEOUT can never match a project symbol -
        # this package avoids that so the test isolates "fully covered."
        _install_fake_package(
            self.site, "coveredpkg", "1.0.0",
            "__all__ = ['rotate_widget', 'WidgetStore']\n"
            "def rotate_widget():\n    return 1\n"
            "class WidgetStore:\n    pass\n",
        )
        project = self.base / "project"
        project.mkdir()
        (project / "app.py").write_text(
            "def rotate_widget():\n    return 2\n"
            "class WidgetStore:\n    pass\n",
            encoding="utf-8",
        )
        resolved = resolve_python_package("coveredpkg")
        diff = diff_against_project(resolved, project)
        self.assertEqual(diff["verdict"], "fully-covered")
        self.assertEqual(diff["findings"], [])


class VendoredTreeTests(unittest.TestCase):
    """Operator refinement (2026-08-15): a forked/fully-copied external repo
    carries the same diff duty a lockfile dependency does, via `--path`."""

    def test_a_vendored_tree_is_enumerated_via_the_atlas_extractor_seam(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            vendored = base / "vendor" / "upstream-lib"
            vendored.mkdir(parents=True)
            (vendored / "core.py").write_text(
                "def rotate_widget():\n    return 1\n"
                "class WidgetStore:\n    pass\n",
                encoding="utf-8",
            )
            resolved = resolve_vendored_tree(vendored)
            self.assertTrue(resolved["resolved"])
            self.assertIn("rotate_widget", resolved["symbols"])
            self.assertIn("WidgetStore", resolved["symbols"])
            self.assertIsNone(resolved["version"])

            project = base / "project"
            project.mkdir()
            (project / "app.py").write_text(
                "def rotate_widget():\n    return 2\n", encoding="utf-8")
            diff = diff_against_project(resolved, project)
            finding_names = {f["upstream_symbol"] for f in diff["findings"]}
            self.assertIn("WidgetStore", finding_names)

    def test_a_missing_vendored_path_is_a_stated_gap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            missing = resolve_vendored_tree(Path(raw) / "nope")
            self.assertFalse(missing["resolved"])
            self.assertTrue(missing["reason"])


class NodeBestEffortTests(unittest.TestCase):
    """Node resolution is explicitly best-effort - stated on every resolved
    record, per the module's honest resolution boundary."""

    def test_a_node_package_json_exports_and_bin_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            pkg_dir = project / "node_modules" / "leftpad"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "package.json").write_text(
                json.dumps({"version": "3.1.0", "exports": {".": "./index.js"},
                            "bin": {"leftpad": "./cli.js"}}),
                encoding="utf-8",
            )
            resolved = resolve_node_package("leftpad", project)
            self.assertTrue(resolved["resolved"])
            self.assertEqual(resolved["version"], "3.1.0")
            self.assertIn("bin:leftpad", resolved["symbols"])
            self.assertIn("best-effort", resolved["note"])

    def test_a_node_package_not_installed_is_a_stated_gap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            resolved = resolve_node_package("nope", project)
            self.assertFalse(resolved["resolved"])
            self.assertTrue(resolved["reason"])


class RecordUpstreamDiffTests(_SitePackage):
    """The single `upstream-diff` record per run, and the paired-verdict
    refusal at the point of writing."""

    def test_findings_write_with_dispositions_and_behavior_verdicts(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "app.py").write_text(
                "def rotate_widget():\n    return 2\n", encoding="utf-8")
            outcome = record_upstream_diff(
                archive, project, package="fixturepkg",
                dispositions={
                    "WidgetStore": {"disposition": "adopt",
                                    "behavior_verdict": "confirmed-we-dont"},
                    "DEFAULT_TIMEOUT": {"disposition": "n/a-different-surface",
                                        "behavior_verdict": "unverified"},
                },
            )
            report = outcome["report"]
            self.assertEqual(report["undispositioned"], [])
            by_symbol = {f["upstream_symbol"]: f for f in report["findings"]}
            self.assertEqual(by_symbol["WidgetStore"]["disposition"], "adopt")
            self.assertEqual(by_symbol["WidgetStore"]["behavior_verdict"],
                             "confirmed-we-dont")
            record = archive.read_events()[-1]
            self.assertEqual(record["kind"], "upstream-diff")
            self.assertEqual(record["data"]["target"], "fixturepkg")

    def test_a_disposition_with_no_behavior_verdict_is_refused_before_any_write(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError):
                record_upstream_diff(
                    archive, project, package="fixturepkg",
                    dispositions={"WidgetStore": {"disposition": "adopt",
                                                  "behavior_verdict": None}},
                )
            self.assertEqual(archive.read_events(), [])

    def test_an_unknown_disposition_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError):
                record_upstream_diff(
                    archive, project, package="fixturepkg",
                    dispositions={"WidgetStore": {"disposition": "just-do-it",
                                                  "behavior_verdict": "unverified"}},
                )

    def test_an_unresolvable_package_records_a_stated_gap(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            outcome = record_upstream_diff(
                archive, project, package="definitely-not-installed-anywhere-xyz",
            )
            self.assertEqual(outcome["report"]["verdict"], "stated-gap")
            self.assertFalse(outcome["report"]["resolved"])
            self.assertTrue(outcome["report"]["reason"])

    def test_a_vendored_tree_writes_through_the_path_variant(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            vendored = project.parent / "vendor-copy"
            vendored.mkdir()
            (vendored / "core.py").write_text(
                "def only_upstream_has_this():\n    return 1\n", encoding="utf-8")
            outcome = record_upstream_diff(archive, project, path=vendored)
            self.assertEqual(outcome["report"]["source_kind"], "vendored-tree")
            names = {f["upstream_symbol"] for f in outcome["report"]["findings"]}
            self.assertIn("only_upstream_has_this", names)

    def test_package_and_path_are_mutually_exclusive(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError):
                record_upstream_diff(archive, project, package="fixturepkg", path=project)
            with self.assertRaises(GodmodeError):
                record_upstream_diff(archive, project)


class ArchiveSeamInvariantTests(_SitePackage):
    """Defense in depth: a RAW append (bypassing `record_upstream_diff`
    entirely) is held to the same paired-verdict rule."""

    def test_a_raw_append_with_disposition_but_no_behavior_verdict_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "upstream-diff", "upstream-diff: raw",
                    {"target": "raw", "findings": [
                        {"upstream_symbol": "x", "disposition": "adopt",
                         "behavior_verdict": None},
                    ]},
                    evidence=[],
                )

    def test_a_raw_append_with_an_undecided_finding_passes_through(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = archive.append(
                "upstream-diff", "upstream-diff: raw",
                {"target": "raw", "findings": [
                    {"upstream_symbol": "x", "disposition": None, "behavior_verdict": None},
                ]},
                evidence=[],
            )
            self.assertEqual(record["kind"], "upstream-diff")

    def test_the_archive_seam_enumerations_match_this_module(self) -> None:
        """`godmode_invariants._upstream_diff_invariants` duplicates
        DISPOSITIONS/BEHAVIOR_VERDICTS by hand rather than importing this
        module - see that module's docstring. A drift between the two would
        silently narrow or widen what the archive seam refuses."""
        from godmode_runtime import godmode_invariants

        self.assertEqual(set(godmode_invariants._UPSTREAM_DISPOSITIONS), set(DISPOSITIONS))
        self.assertEqual(set(godmode_invariants._UPSTREAM_BEHAVIOR_VERDICTS),
                         set(BEHAVIOR_VERDICTS))

    def test_kind_invariants_is_populated_eagerly_at_chronicle_import(self) -> None:
        from godmode_runtime import godmode_chronicle

        self.assertIsNotNone(godmode_chronicle.KIND_INVARIANTS.get("upstream-diff"))


class CharterGateTests(unittest.TestCase):
    """Operator refinement (2026-08-15, binding): the duty is
    requirement-driven. No declaration means no gate; a declaration only
    ever adds duty, scoped to named packages or an explicit any-scope."""

    def test_no_declaration_means_no_gate(self) -> None:
        charter = {"compiled": []}
        scope = required_scope(charter)
        self.assertFalse(scope["declared"])
        outcome = gate_applies(charter, package="anything")
        self.assertFalse(outcome["applies"])

    def test_a_charter_rule_naming_a_package_scopes_the_gate_to_it(self) -> None:
        charter = {"compiled": [
            {"id": "R-1", "text": "A register disposition must never be recorded "
                                  "for a task naming the dependency `requests`, "
                                  "without an attested upstream-diff record for "
                                  "`requests` already in the archive."},
        ]}
        scope = required_scope(charter)
        self.assertTrue(scope["declared"])
        self.assertIn("requests", scope["packages"])
        self.assertFalse(scope["any_scope"])

        hit = gate_applies(charter, package="requests")
        self.assertTrue(hit["applies"])
        miss = gate_applies(charter, package="numpy")
        self.assertFalse(miss["applies"])

    def test_an_any_scope_charter_rule_applies_to_any_named_dependency(self) -> None:
        charter = {"compiled": [
            {"id": "R-2", "text": "A register disposition must never be recorded "
                                  "for any task naming a dependency or a forked "
                                  "repo, without an attested upstream-diff record "
                                  "for it already in the archive."},
        ]}
        scope = required_scope(charter)
        self.assertTrue(scope["declared"])
        self.assertTrue(scope["any_scope"])

        hit = gate_applies(charter, task_text="add the requests dependency")
        self.assertTrue(hit["applies"])
        miss = gate_applies(charter, task_text="fix a typo in the README")
        self.assertFalse(miss["applies"])

    def test_the_emitted_charter_template_compiles_hard(self) -> None:
        """The template is prose for a human to paste into an authority
        document; it is never written by this module. Proving it compiles
        HARD (with no edit to godmode_charter's own shape table) shows the
        template actually earns the enforcement it claims."""
        from godmode_runtime.godmode_charter import HARD, compile_charter

        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Dependencies\n\n" + CHARTER_RULE_TEMPLATE, encoding="utf-8")
            charter = compile_charter(project)
            matching = [r for r in charter["compiled"] if "upstream-diff" in r["text"]]
            self.assertTrue(matching, charter["compiled"])
            self.assertTrue(any(r["enforcement"] == HARD for r in matching), matching)


class ConsoleWiringTests(unittest.TestCase):
    """The minimal isolated CLI block: `godmode upstream --diff/--path`."""

    def test_the_diff_flag_writes_a_record_and_reports_undispositioned_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            site = base / "site"
            site.mkdir()
            _install_fake_package(
                site, "clipkg", "2.0.0",
                "__all__ = ['do_thing']\ndef do_thing():\n    return 1\n",
            )
            sys.path.insert(0, str(site))
            try:
                project = base / "project"
                project.mkdir()
                (project / "app.py").write_text(
                    "def unrelated():\n    pass\n", encoding="utf-8")
                with mock_state_home(base / "state"):
                    from godmode_runtime.godmode_console import main

                    self.assertEqual(main(["--project", str(project), "init"]), 0)
                    rc = main(["--project", str(project), "--json",
                              "upstream", "--diff", "clipkg"])
                    self.assertEqual(rc, 1)  # an undispositioned finding is reported

                    rc_disposed = main([
                        "--project", str(project), "--json", "upstream", "--diff", "clipkg",
                        "--dispose", "do_thing=adopt:unverified",
                    ])
                    self.assertEqual(rc_disposed, 0)
            finally:
                sys.path.remove(str(site))
                sys.modules.pop("clipkg", None)

    def test_diff_and_path_are_mutually_exclusive_at_the_cli(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            with mock_state_home(base / "state"):
                from godmode_runtime.godmode_console import main

                main(["--project", str(project), "init"])
                with self.assertRaises(SystemExit):
                    main(["--project", str(project), "upstream",
                          "--diff", "x", "--path", str(project)])


class _MockStateHome:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._previous = None

    def __enter__(self) -> "_MockStateHome":
        self._previous = os.environ.get("GODMODE_STATE_HOME")
        os.environ["GODMODE_STATE_HOME"] = str(self.path)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._previous is None:
            os.environ.pop("GODMODE_STATE_HOME", None)
        else:
            os.environ["GODMODE_STATE_HOME"] = self._previous


def mock_state_home(path: Path) -> _MockStateHome:
    return _MockStateHome(path)


if __name__ == "__main__":
    unittest.main()

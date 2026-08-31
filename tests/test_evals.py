from __future__ import annotations

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

import godmode_runtime.godmode_evals as evals_module  # noqa: E402
from godmode_runtime.godmode_evals import (  # noqa: E402
    ASSERTION_SCHEMA,
    CHARTER_SNAPSHOT_SCHEMA,
    EVAL_SCHEMA,
    RANKING_SNAPSHOT_SCHEMA,
    RANKING_TASKS,
    SNAPSHOT_SCHEMA,
    adversarial_grid,
    charter_snapshot,
    check_snapshots,
    ranking_snapshot,
    run_behavior_assertions,
    run_routing_evals,
)

ALL_SKILLS = [
    "godmode",
    "godmode-continuity",
    "godmode-governance",
    "godmode-investigation",
    "godmode-repair",
    "godmode-skill-forge",
]

# The eval's first run found two positives that did not route home; their
# wording was fixed (home-vocabulary strengthened) and this now pins zero
# misroutes, so a new regression changes this test loudly.
KNOWN_MISROUTED_POSITIVES: set[str] = set()


def _write_suite(root: Path, skill: str, description: str,
                 positive: list[str], near_negative: list[str],
                 assertions: list | None = None) -> None:
    directory = root / "skills" / skill
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: {description}\n---\n\n# {skill}\n",
        encoding="utf-8",
    )
    (directory / "godmode-evals.json").write_text(
        json.dumps({
            "schema": EVAL_SCHEMA,
            "skill": skill,
            "routing": {"positive": positive, "near_negative": near_negative},
            "behavior_assertions": assertions if assertions is not None else ["observable"],
        }),
        encoding="utf-8",
    )


def _synthetic_project(root: Path) -> None:
    """Two skills with disjoint vocabularies, so routing is unambiguous."""
    _write_suite(
        root, "alpha", "Compile ledger totals for quarterly ledger audits.",
        ["Compile the quarterly ledger totals for the audit.",
         "Reconcile ledger balances before the quarterly audit closes."],
        ["Paint a watercolour landscape of mountains."],
    )
    _write_suite(
        root, "beta", "Tune telescope optics and star tracking mounts.",
        ["Tune the telescope optics before the star party.",
         "Align the tracking mount for long telescope exposures."],
        ["Compile the quarterly ledger totals for the audit."],
    )


class RoutingEvalTests(unittest.TestCase):
    def test_finds_every_shipped_skill(self):
        report = run_routing_evals(PLUGIN_ROOT)
        self.assertEqual(sorted(report["skills"]), ALL_SKILLS)

    def test_observed_positive_routing_accuracy(self):
        # Every authored positive routes home since the two originally
        # misrouted prompts were reworded. Observed reality, kept current.
        report = run_routing_evals(PLUGIN_ROOT)
        totals = report["totals"]
        self.assertEqual(totals["positives_total"], 12)
        self.assertEqual(totals["positives_routed_correctly"], 12)
        self.assertEqual(report["verdict"], "routing-sound")
        failing = {entry["prompt"] for entry in report["failing_prompts"]}
        self.assertEqual(failing, KNOWN_MISROUTED_POSITIVES)

    def test_near_negatives_reported_not_hidden(self):
        report = run_routing_evals(PLUGIN_ROOT)
        totals = report["totals"]
        self.assertEqual(totals["near_negatives_total"], 12)
        # Captured near-negatives are reported per skill with details.
        for skill, entry in report["skills"].items():
            captured = [m for m in entry["misrouted"] if m["kind"] == "near_negative"]
            expected = entry["near_negatives_total"] - entry["near_negatives_rejected"]
            self.assertEqual(len(captured), expected, skill)

    def test_deterministic(self):
        first = run_routing_evals(PLUGIN_ROOT)
        second = run_routing_evals(PLUGIN_ROOT)
        self.assertEqual(first, second)

    def test_synthetic_positives_route_home(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _synthetic_project(root)
            report = run_routing_evals(root)
            self.assertEqual(report["verdict"], "routing-sound")
            self.assertEqual(report["totals"]["positives_routed_correctly"], 4)
            # beta's near-negative is a verbatim alpha positive: it must be
            # rejected by beta (it legitimately matches the sibling instead).
            self.assertEqual(report["skills"]["beta"]["near_negatives_rejected"], 1)


class SnapshotTests(unittest.TestCase):
    def test_repo_snapshots_are_current(self):
        # The committed fixtures must match what the runner produces now;
        # anything else means a behaviour change shipped without a snapshot.
        outcome = check_snapshots(PLUGIN_ROOT)
        self.assertEqual(outcome["verdict"], "behaviour-stable", outcome)
        self.assertEqual(outcome["diffs"], [])
        self.assertEqual(outcome["missing_snapshots"], [])

    def test_repo_snapshot_files_declare_schema(self):
        fixtures = PLUGIN_ROOT / "evals" / "fixtures"
        paths = sorted(fixtures.glob("*-routing.json"))
        self.assertEqual(len(paths), len(ALL_SKILLS))
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], SNAPSHOT_SCHEMA, path.name)

    def test_write_then_check_is_stable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _synthetic_project(root)
            written = check_snapshots(root, write=True)
            self.assertEqual(sorted(written["written"]),
                             ["alpha-routing.json", "beta-routing.json"])
            outcome = check_snapshots(root)
            self.assertEqual(outcome["verdict"], "behaviour-stable")

    def test_injected_change_is_detected_field_level(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _synthetic_project(root)
            check_snapshots(root, write=True)
            snapshot_path = root / "evals" / "fixtures" / "alpha-routing.json"
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            prompt = next(iter(data["routes"]["positive"]))
            data["routes"]["positive"][prompt] = "beta"
            data["summary"]["positives_routed_correctly"] = 1
            snapshot_path.write_text(json.dumps(data), encoding="utf-8")

            outcome = check_snapshots(root)
            self.assertEqual(outcome["verdict"], "behaviour-changed")
            fields = {diff["field"] for diff in outcome["diffs"]}
            self.assertIn("summary.positives_routed_correctly", fields)
            self.assertTrue(any(f.startswith("routes.positive[") for f in fields))
            for diff in outcome["diffs"]:
                self.assertIn("was", diff)
                self.assertIn("now", diff)

    def test_missing_snapshot_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _synthetic_project(root)
            outcome = check_snapshots(root)
            self.assertEqual(outcome["verdict"], "behaviour-changed")
            self.assertEqual(sorted(outcome["missing_snapshots"]),
                             ["alpha-routing.json", "beta-routing.json"])


class AdversarialGridTests(unittest.TestCase):
    def test_no_cell_is_silently_skipped(self):
        report = adversarial_grid()
        self.assertEqual(len(report["grid"]), report["cells"])
        for cell in report["grid"]:
            self.assertTrue(cell["observed"], cell)
            valid = cell["outcome"] in ("pass", "fail") or cell["outcome"].startswith(
                "not-executable: "
            )
            self.assertTrue(valid, cell)

    def test_every_control_has_at_least_two_attacks(self):
        report = adversarial_grid()
        per_control: dict[str, int] = {}
        for cell in report["grid"]:
            per_control[cell["control"]] = per_control.get(cell["control"], 0) + 1
        self.assertEqual(sorted(per_control), sorted(report["controls"]))
        self.assertEqual(len(per_control), 6)
        for control, count in per_control.items():
            self.assertGreaterEqual(count, 2, control)

    def test_observed_grid_results(self):
        # The grid found this breach when first run: a verified grade could be
        # laundered through a rec: citation of a prior unverified claim. The
        # runtime now refuses claim records as rec: support, so all 13 attacks
        # are refused - and this test keeps that closed.
        report = adversarial_grid()
        self.assertEqual(report["cells"], 13)
        self.assertEqual(report["passed"], 13)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["not_executable"], 0)
        self.assertEqual(report["verdict"], "controls-held")
        self.assertEqual(report["breaches"], [])

    def test_deterministic(self):
        first = adversarial_grid()
        second = adversarial_grid()
        self.assertEqual(first, second)


class BehaviorAssertionTests(unittest.TestCase):
    def _project(self, root: Path, assertions: list) -> None:
        _write_suite(root, "gamma", "Audit ledger totals for quarterly review.",
                     ["Audit the ledger totals for the quarterly review."], [],
                     assertions=assertions)

    def test_executable_assertions_pass_and_fail_correctly(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._project(root, [
                {"assert": "the interpreter prints ok",
                 "check": {"command": "python -c \"print('ok')\"",
                           "expect_exit": 0, "expect_contains": "ok"}},
                {"assert": "expected text is absent",
                 "check": {"command": "python -c \"print('ok')\"",
                           "expect_contains": "absent-text"}},
                {"assert": "a declared nonzero exit is honoured",
                 "check": {"command": "python -c \"import sys; sys.exit(3)\"",
                           "expect_exit": 3}},
            ])
            report = run_behavior_assertions(root)
            self.assertEqual(report["schema"], ASSERTION_SCHEMA)
            entry = report["skills"]["gamma"]
            self.assertEqual(
                [a["outcome"] for a in entry["assertions"]], ["pass", "fail", "pass"])
            self.assertEqual(entry["passed"], 2)
            self.assertEqual(entry["failed"], 1)
            self.assertEqual(entry["declared_only"], 0)
            self.assertEqual(report["totals"]["failed"], 1)
            self.assertEqual(report["verdict"], "assertion-failed")
            # The failing assertion states what was observed, not just that it failed.
            failing = entry["assertions"][1]
            self.assertIn("absent-text", failing["observed"])

    def test_declared_only_assertions_are_counted_not_run(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._project(root, [
                "The workflow stays honest about missing evidence.",
                {"assert": "an object without a check is still declared-only"},
            ])
            report = run_behavior_assertions(root)
            entry = report["skills"]["gamma"]
            self.assertEqual(entry["declared_only"], 2)
            self.assertEqual(entry["executable"], 0)
            self.assertEqual(entry["passed"], 0)
            self.assertEqual(entry["failed"], 0)
            for assertion in entry["assertions"]:
                self.assertEqual(assertion["mode"], "declared-only")
                self.assertEqual(assertion["outcome"], "not-run")
                self.assertNotIn("observed", assertion)
            # Declared-only is reported, never failed: nothing ran, so nothing broke.
            self.assertEqual(report["verdict"], "assertions-held")
            self.assertEqual(report["totals"]["declared_only"], 2)

    def test_repo_suites_each_ship_a_passing_executable_assertion(self):
        # Probes run against a disposable state home so this test never depends
        # on (or mutates) the developer's real archive.
        with tempfile.TemporaryDirectory() as raw, mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(Path(raw) / "state")}, clear=False
        ):
            init = subprocess.run(
                [sys.executable, "scripts/godmode.py", "--project", ".", "init"],
                cwd=PLUGIN_ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(init.returncode, 0, init.stderr)
            report = run_behavior_assertions(PLUGIN_ROOT)
        self.assertEqual(sorted(report["skills"]), ALL_SKILLS)
        for skill, entry in report["skills"].items():
            self.assertGreaterEqual(entry["executable"], 1, skill)
            self.assertEqual(entry["failed"], 0, entry["assertions"])
            self.assertGreaterEqual(entry["declared_only"], 1, skill)
        self.assertEqual(report["verdict"], "assertions-held")


def _charter_project(root: Path) -> None:
    (root / "GODMODE.md").write_text(
        "# Gates\n"
        "- Never commit without an explicit ask.\n"
        "- A claim must cite evidence before completion.\n",
        encoding="utf-8",
    )


class CharterSnapshotTests(unittest.TestCase):
    def test_write_then_check_is_stable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _charter_project(root)
            written = charter_snapshot(root, write=True)
            self.assertEqual(written["verdict"], "snapshot-written")
            fixture = root / "evals" / "fixtures" / "charter-rules.json"
            data = json.loads(fixture.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], CHARTER_SNAPSHOT_SCHEMA)
            self.assertGreaterEqual(len(data["rules"]), 2)
            outcome = charter_snapshot(root)
            self.assertEqual(outcome["verdict"], "charter-stable", outcome)
            self.assertEqual(outcome["added"], [])
            self.assertEqual(outcome["removed"], [])
            self.assertEqual(outcome["changed"], [])

    def test_editing_a_prose_rule_shows_a_diff(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _charter_project(root)
            charter_snapshot(root, write=True)
            document = root / "GODMODE.md"
            document.write_text(
                document.read_text(encoding="utf-8").replace(
                    "Never commit without an explicit ask.",
                    "Never push without an explicit ask."),
                encoding="utf-8")
            outcome = charter_snapshot(root)
            self.assertEqual(outcome["verdict"], "charter-changed", outcome)
            # The reworded rule has a new id: the edit surfaces as one rule
            # leaving the charter and one arriving, never as silence.
            self.assertEqual(len(outcome["added"]), 1)
            self.assertEqual(len(outcome["removed"]), 1)

    def test_field_change_is_reported_field_level(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _charter_project(root)
            charter_snapshot(root, write=True)
            fixture = root / "evals" / "fixtures" / "charter-rules.json"
            data = json.loads(fixture.read_text(encoding="utf-8"))
            rule_id = sorted(data["rules"])[0]
            data["rules"][rule_id]["enforcement"] = "TAMPERED"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            outcome = charter_snapshot(root)
            self.assertEqual(outcome["verdict"], "charter-changed")
            fields = {(c["rule"], c["field"]) for c in outcome["changed"]}
            self.assertIn((rule_id, "enforcement"), fields)
            for change in outcome["changed"]:
                self.assertIn("was", change)
                self.assertIn("now", change)

    def test_missing_snapshot_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _charter_project(root)
            outcome = charter_snapshot(root)
            self.assertEqual(outcome["verdict"], "charter-changed")
            self.assertTrue(outcome["missing_snapshot"])

    def test_repo_charter_snapshot_is_current(self):
        outcome = charter_snapshot(PLUGIN_ROOT)
        self.assertEqual(outcome["verdict"], "charter-stable", outcome)


class RankingSnapshotTests(unittest.TestCase):
    def test_task_set_is_fixed(self):
        self.assertEqual(len(RANKING_TASKS), 3)
        self.assertTrue(all(isinstance(task, str) and task for task in RANKING_TASKS))

    def test_stable_across_two_runs(self):
        first = ranking_snapshot(PLUGIN_ROOT)
        second = ranking_snapshot(PLUGIN_ROOT)
        self.assertEqual(first, second)
        if first["verdict"] == "ranking-mode-differs":
            self.skipTest(
                "snapshot generated under a different instrument than this "
                f"checkout carries: {first.get('mode_mismatch')} - comparison "
                "out of contract here, determinism itself asserted above")
        self.assertEqual(first["verdict"], "ranking-stable", first)

    def test_ranking_change_is_detected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "GODMODE.md").write_text(
                "# Guide\n- Always check the failing test first.\n", encoding="utf-8")
            written = ranking_snapshot(root, write=True)
            self.assertEqual(written["verdict"], "snapshot-written")
            self.assertEqual(ranking_snapshot(root)["verdict"], "ranking-stable")
            (root / "GODMODE.md").write_text(
                "# Guide\n\n## Release\nPrepare the changelog and docs early.\n\n"
                "## Tests\n- Always check the failing test first.\n",
                encoding="utf-8")
            outcome = ranking_snapshot(root)
            self.assertEqual(outcome["verdict"], "ranking-changed", outcome)
            self.assertTrue(outcome["diffs"])
            for diff in outcome["diffs"]:
                self.assertIn("was", diff)
                self.assertIn("now", diff)

    def test_repo_ranking_snapshot_is_current(self):
        outcome = ranking_snapshot(PLUGIN_ROOT)
        if outcome["verdict"] == "ranking-mode-differs":
            self.skipTest(
                "snapshot generated under a different instrument than this "
                f"checkout carries: {outcome.get('mode_mismatch')} - use a "
                "full-history checkout (fetch-depth: 0) to compare for real")
        self.assertEqual(outcome["verdict"], "ranking-stable", outcome)
        fixture = PLUGIN_ROOT / "evals" / "fixtures" / "ranking.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], RANKING_SNAPSHOT_SCHEMA)
        self.assertEqual(sorted(data["tasks"]), sorted(RANKING_TASKS))


class DocsSiteTests(unittest.TestCase):
    def test_docs_site_builds_offline_from_repo_markdown(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "godmode_docs_site", PLUGIN_ROOT / "scripts" / "godmode_docs_site.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "site"
            result = module.build(PLUGIN_ROOT, out)
            self.assertGreaterEqual(result["pages"], 10)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Godmode documentation", index)
            readme = (out / "README.html").read_text(encoding="utf-8")
            self.assertIn('href="GODMODE.html"', readme)


class AdapterHonestyTests(unittest.TestCase):
    """S9-02/03/04: each adapter document states exactly the declared matrix."""

    def test_adapter_docs_match_the_declared_enforcement_matrix(self) -> None:
        hosts = json.loads(
            (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8"))
        adapters = {k: v for k, v in hosts["adapters"].items() if not k.startswith("_")}
        self.assertEqual(sorted(adapters), ["cursor", "gemini", "opencode"])
        for host, declared in adapters.items():
            doc = (PLUGIN_ROOT / declared["wiring"]).read_text(encoding="utf-8")
            for control, level in declared["controls"].items():
                self.assertRegex(
                    doc, rf"\|\s*{control}\s*\|\s*{level}\s*\|",
                    f"{host}: {control} must be stated as {level} in {declared['wiring']}")

    def test_declared_host_capabilities_resolve_from_cli_layer(self) -> None:
        hosts = json.loads(
            (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8"))
        for host, declared in hosts["adapters"].items():
            if host.startswith("_"):
                continue
            self.assertIn("tool_call_interception", declared["controls"])
            # An instruction-file adapter cannot intercept a tool call on its
            # own. It may rise to SOFT only when the host's own plugin API
            # gives it a pre-tool boundary AND this repository ships the shim
            # that reaches it - OpenCode, 2026-08-28. Never HARD without a
            # live chronicled block.
            level = declared["controls"]["tool_call_interception"]
            if level == "SOFT":
                shim = declared.get("shim")
                self.assertTrue(shim, f"{host}: SOFT with no shim declared")
                self.assertTrue((PLUGIN_ROOT / shim).is_file(), f"{host}: {shim} is not shipped")
            else:
                self.assertEqual(level, "UNAVAILABLE", host)
            self.assertTrue((PLUGIN_ROOT / declared["wiring"]).is_file(), host)


if __name__ == "__main__":
    unittest.main()


class RankingModeContractTests(unittest.TestCase):
    """A snapshot is comparable only within its own instruments: scorer and
    freshness mode. A mismatch reads 'not comparable here', never 'drifted'
    (field report 2026-08-31: a shallow CI checkout reordered two tasks
    against a full-clone snapshot and was called drift)."""

    def _snapshot_with(self, view, stored):
        import json as _json
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = root / "evals" / "fixtures" / "ranking.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(_json.dumps(stored), encoding="utf-8")
            with mock.patch.object(evals_module, "_ranking_view",
                                   return_value=view):
                return evals_module.ranking_snapshot(root)

    def test_a_mode_mismatch_is_not_drift(self) -> None:
        view = {"schema": 1, "scorer": "fts5", "freshness_mode": "git",
                "budget": 4000, "tasks": {"t": [["a.md", 1]]}}
        stored = {**view, "freshness_mode": "git-shallow"}
        report = self._snapshot_with(view, stored)
        self.assertEqual(report["verdict"], "ranking-mode-differs")
        self.assertEqual(report["diffs"], [])

    def test_same_mode_reorder_is_still_drift(self) -> None:
        view = {"schema": 1, "scorer": "fts5", "freshness_mode": "git",
                "budget": 4000, "tasks": {"t": [["a.md", 1], ["b.md", 1]]}}
        stored = {**view, "tasks": {"t": [["b.md", 1], ["a.md", 1]]}}
        report = self._snapshot_with(view, stored)
        self.assertEqual(report["verdict"], "ranking-changed")

    def test_an_old_snapshot_without_mode_fields_still_compares(self) -> None:
        view = {"schema": 1, "scorer": "fts5", "freshness_mode": "git",
                "budget": 4000, "tasks": {"t": [["a.md", 1]]}}
        stored = {"schema": 1, "scorer": "fts5", "budget": 4000,
                  "tasks": {"t": [["a.md", 1]]}}
        report = self._snapshot_with(view, stored)
        self.assertEqual(report["verdict"], "ranking-stable")

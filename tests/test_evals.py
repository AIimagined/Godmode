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

from godmode_runtime.godmode_evals import (  # noqa: E402
    EVAL_SCHEMA,
    SNAPSHOT_SCHEMA,
    adversarial_grid,
    check_snapshots,
    run_routing_evals,
)

ALL_SKILLS = [
    "godmode",
    "godmode-continuity",
    "godmode-governance",
    "godmode-investigation",
    "godmode-skill-forge",
]

# The eval's first run found two positives that did not route home; their
# wording was fixed (home-vocabulary strengthened) and this now pins zero
# misroutes, so a new regression changes this test loudly.
KNOWN_MISROUTED_POSITIVES: set[str] = set()


def _write_suite(root: Path, skill: str, description: str,
                 positive: list[str], near_negative: list[str]) -> None:
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
            "behavior_assertions": ["observable"],
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
    def test_finds_the_five_real_skills(self):
        report = run_routing_evals(PLUGIN_ROOT)
        self.assertEqual(sorted(report["skills"]), ALL_SKILLS)

    def test_observed_positive_routing_accuracy(self):
        # Every authored positive routes home since the two originally
        # misrouted prompts were reworded. Observed reality, kept current.
        report = run_routing_evals(PLUGIN_ROOT)
        totals = report["totals"]
        self.assertEqual(totals["positives_total"], 10)
        self.assertEqual(totals["positives_routed_correctly"], 10)
        self.assertEqual(report["verdict"], "routing-sound")
        failing = {entry["prompt"] for entry in report["failing_prompts"]}
        self.assertEqual(failing, KNOWN_MISROUTED_POSITIVES)

    def test_near_negatives_reported_not_hidden(self):
        report = run_routing_evals(PLUGIN_ROOT)
        totals = report["totals"]
        self.assertEqual(totals["near_negatives_total"], 10)
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


if __name__ == "__main__":
    unittest.main()

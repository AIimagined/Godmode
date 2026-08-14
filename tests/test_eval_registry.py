"""U-S1: versioned eval registry + grader vocabulary.

Scores are only comparable within an id (`name.local.vN`); an eval that
changes shape without a version bump is a silent behaviour change, and the
registry's job is to make that loud instead. The grader module gives eval
definitions a small, named set of deterministic comparators instead of
ad-hoc string logic re-invented per skill - `json_match` carries the one
safety property worth pinning twice: invalid JSON never matches, even
against itself.
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

from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime.godmode_graders import (  # noqa: E402
    GRADERS,
    grade,
    grade_fuzzy,
    grade_includes,
    grade_json_match,
    grade_match,
)
from godmode_runtime import godmode_scenarios as scen  # noqa: E402
from godmode_runtime.godmode_evals import (  # noqa: E402
    EVAL_SCHEMA,
    compare_eval_results,
    run_behavior_assertions,
)


class MatchGraderTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(grade_match("gm1.abcdef", "gm1.abcdef"))
        self.assertFalse(grade_match("gm1.abcdef", "gm1.other"))

    def test_prefix_mode(self) -> None:
        self.assertTrue(grade_match("gm1.abcdef", "gm1.", prefix=True))
        self.assertFalse(grade_match("gm2.abcdef", "gm1.", prefix=True))

    def test_any_of(self) -> None:
        self.assertTrue(grade_match("beta", ["alpha", "beta", "gamma"]))
        self.assertFalse(grade_match("delta", ["alpha", "beta", "gamma"]))

    def test_empty_candidates_never_match(self) -> None:
        self.assertFalse(grade_match("anything", []))


class IncludesGraderTests(unittest.TestCase):
    def test_substring_present(self) -> None:
        self.assertTrue(grade_includes("the quick brown fox", "quick"))

    def test_substring_absent(self) -> None:
        self.assertFalse(grade_includes("the quick brown fox", "slow"))


class FuzzyGraderTests(unittest.TestCase):
    def test_mutual_containment_after_normalisation(self) -> None:
        self.assertTrue(grade_fuzzy("Retry   Backoff", "retry backoff"))
        self.assertTrue(grade_fuzzy("retry", "retry backoff strategy"))
        self.assertTrue(grade_fuzzy("retry backoff strategy", "retry"))

    def test_no_containment_either_direction(self) -> None:
        self.assertFalse(grade_fuzzy("retry", "backoff strategy"))

    def test_both_empty_after_normalisation_is_equal_not_universal(self) -> None:
        self.assertTrue(grade_fuzzy("   ", ""))
        self.assertFalse(grade_fuzzy("", "backoff"))
        self.assertFalse(grade_fuzzy("backoff", ""))


class JsonMatchGraderTests(unittest.TestCase):
    def test_key_order_insensitive(self) -> None:
        self.assertTrue(grade_json_match('{"a": 1, "b": 2}', '{"b": 2, "a": 1}'))

    def test_whitespace_insensitive(self) -> None:
        self.assertTrue(grade_json_match('  {"a":1}\n', '{\n  "a": 1\n}'))

    def test_structurally_different_does_not_match(self) -> None:
        self.assertFalse(grade_json_match('{"a": 1}', '{"a": 2}'))

    def test_invalid_json_never_matches_even_identical_malformed_input(self) -> None:
        # The fail-closed case: byte-identical malformed input on both sides
        # must still be refused. A grader that matches here because both
        # sides "failed the same way" is a grader an attacker can satisfy by
        # sending broken output.
        malformed = "{this is not json"
        self.assertFalse(grade_json_match(malformed, malformed))

    def test_invalid_json_on_either_side_never_matches(self) -> None:
        self.assertFalse(grade_json_match("{broken", '{"a": 1}'))
        self.assertFalse(grade_json_match('{"a": 1}', "{broken"))

    def test_non_string_input_never_matches(self) -> None:
        self.assertFalse(grade_json_match(None, '{"a": 1}'))  # type: ignore[arg-type]


class GraderDispatchTests(unittest.TestCase):
    def test_closed_vocabulary_names(self) -> None:
        self.assertEqual(sorted(GRADERS), ["fuzzy", "includes", "json_match", "match"])

    def test_dispatches_by_name(self) -> None:
        self.assertTrue(grade("includes", "the quick fox", "quick"))
        self.assertTrue(grade("match", "gm1.x", "gm1.", prefix=True))

    def test_unknown_grader_is_refused(self) -> None:
        with self.assertRaises(GodmodeError):
            grade("not-a-real-grader", "x", "y")


class ScenarioIdTests(unittest.TestCase):
    """Every scenario carries a versioned id and a content digest."""

    def test_every_scenario_has_a_local_versioned_id(self) -> None:
        report = scen.run()
        for entry in report["scenarios"]:
            self.assertEqual(entry["id"], f"{entry['scenario']}.local.v1", entry)

    def test_digest_is_a_sha256_hex_string(self) -> None:
        report = scen.run()
        for entry in report["scenarios"]:
            digest = entry["digest"]
            self.assertEqual(len(digest), 64, entry)
            int(digest, 16)  # raises ValueError if not hex

    def test_ids_and_digests_are_deterministic(self) -> None:
        first = scen.run()
        second = scen.run()
        first_ids = {e["scenario"]: (e["id"], e["digest"]) for e in first["scenarios"]}
        second_ids = {e["scenario"]: (e["id"], e["digest"]) for e in second["scenarios"]}
        self.assertEqual(first_ids, second_ids)

    def test_a_version_bump_changes_the_id(self) -> None:
        original_versions = dict(scen.SCENARIO_VERSIONS)
        try:
            scen.SCENARIO_VERSIONS["hollow-guard"] = 2
            report = scen.run(only="hollow-guard")
            self.assertEqual(report["scenarios"][0]["id"], "hollow-guard.local.v2")
        finally:
            scen.SCENARIO_VERSIONS.clear()
            scen.SCENARIO_VERSIONS.update(original_versions)


class RegistryDriftTests(unittest.TestCase):
    """The registry pins a digest per id; a body change without a version
    bump must be a blocking finding in the scenarios report."""

    def test_registry_is_clean_at_baseline(self) -> None:
        report = scen.run()
        self.assertEqual(report["registry"]["schema"], scen.REGISTRY_SCHEMA)
        self.assertEqual(report["registry"]["findings"], [])
        self.assertFalse(report["registry"]["blocking"])

    def test_editing_a_scenario_without_bumping_its_version_is_blocking(self) -> None:
        # The plant: swap one scenario's staging function for a different
        # body while its name (and therefore its id, still v1) is unchanged.
        # This is exactly "edit a scenario, keep vN" - it must go red.
        def planted(project, archive):
            return True, "a body that was never reviewed at this version"

        original = scen.SCENARIOS
        scen.SCENARIOS = tuple(
            (name, ref, failure, planted) if name == "hollow-guard"
            else (name, ref, failure, fn)
            for name, ref, failure, fn in original
        )
        try:
            report = scen.run(only="hollow-guard")
        finally:
            scen.SCENARIOS = original

        self.assertTrue(report["registry"]["blocking"], report["registry"])
        ids = {f["id"] for f in report["registry"]["findings"]}
        self.assertIn("hollow-guard.local.v1", ids)
        detail = next(
            f["detail"] for f in report["registry"]["findings"]
            if f["id"] == "hollow-guard.local.v1")
        self.assertIn("version was not bumped", detail)

    def test_a_version_bump_alongside_the_edit_clears_the_finding(self) -> None:
        # The same plant, but with the version correctly bumped: an
        # unregistered id (v2 was never pinned) is not a digest-drift
        # finding, because there is nothing pinned to drift from.
        def planted(project, archive):
            return True, "a deliberately new version of this scenario"

        original_scenarios = scen.SCENARIOS
        original_versions = dict(scen.SCENARIO_VERSIONS)
        scen.SCENARIOS = tuple(
            (name, ref, failure, planted) if name == "hollow-guard"
            else (name, ref, failure, fn)
            for name, ref, failure, fn in original_scenarios
        )
        scen.SCENARIO_VERSIONS["hollow-guard"] = 2
        try:
            report = scen.run(only="hollow-guard")
        finally:
            scen.SCENARIOS = original_scenarios
            scen.SCENARIO_VERSIONS.clear()
            scen.SCENARIO_VERSIONS.update(original_versions)

        self.assertEqual(report["scenarios"][0]["id"], "hollow-guard.local.v2")
        self.assertFalse(report["registry"]["blocking"], report["registry"])
        self.assertEqual(report["registry"]["findings"], [])


class CrossIdComparisonTests(unittest.TestCase):
    """Result records compare only within a single id."""

    def test_same_id_compares_field_level(self) -> None:
        outcome = compare_eval_results(
            {"id": "hollow-guard.local.v1", "caught": True, "observed": "old"},
            {"id": "hollow-guard.local.v1", "caught": False, "observed": "new"},
        )
        self.assertTrue(outcome["comparable"])
        self.assertEqual(outcome["verdict"], "compared")
        self.assertIn("caught", outcome["changed"])
        self.assertEqual(outcome["changed"]["caught"], {"was": True, "now": False})
        self.assertIn("observed", outcome["changed"])

    def test_identical_records_report_no_change(self) -> None:
        record = {"id": "hollow-guard.local.v1", "caught": True}
        outcome = compare_eval_results(record, dict(record))
        self.assertEqual(outcome["verdict"], "compared")
        self.assertEqual(outcome["changed"], {})

    def test_different_ids_are_refused_with_the_exact_reason(self) -> None:
        outcome = compare_eval_results(
            {"id": "hollow-guard.local.v1", "caught": True},
            {"id": "hollow-guard.local.v2", "caught": True},
        )
        self.assertFalse(outcome["comparable"])
        self.assertEqual(outcome["verdict"], "refused")
        self.assertEqual(outcome["reason"], "scores are comparable only within an id")

    def test_unrelated_ids_are_also_refused(self) -> None:
        outcome = compare_eval_results(
            {"id": "hollow-guard.local.v1", "caught": True},
            {"id": "stale-backlog.local.v1", "caught": True},
        )
        self.assertEqual(outcome["verdict"], "refused")
        self.assertEqual(outcome["reason"], "scores are comparable only within an id")


class BehaviorAssertionGraderWiringTests(unittest.TestCase):
    """The grader vocabulary is reachable from a behaviour-assertion check,
    not only importable in isolation."""

    def _project(self, root: Path, check: dict) -> None:
        directory = root / "skills" / "gamma"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            "---\nname: gamma\ndescription: Probe grader wiring end to end.\n---\n",
            encoding="utf-8",
        )
        (directory / "godmode-evals.json").write_text(json.dumps({
            "schema": EVAL_SCHEMA, "skill": "gamma",
            "routing": {"positive": [], "near_negative": []},
            "behavior_assertions": [{"assert": "graded probe", "check": check}],
        }), encoding="utf-8")

    def test_match_grader_with_prefix_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._project(root, {
                "command": "python -c \"print('gm1.deadbeef')\"",
                "grader": "match", "expected": "gm1.", "prefix": True,
            })
            report = run_behavior_assertions(root)
            self.assertEqual(report["skills"]["gamma"]["passed"], 1, report)
            self.assertEqual(report["verdict"], "assertions-held")

    def test_json_match_grader_fails_closed_on_malformed_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._project(root, {
                "command": "python -c \"print('{not valid json')\"",
                "grader": "json_match", "expected": "{not valid json",
            })
            report = run_behavior_assertions(root)
            entry = report["skills"]["gamma"]["assertions"][0]
            self.assertEqual(entry["outcome"], "fail")
            self.assertEqual(report["verdict"], "assertion-failed")

    def test_unknown_grader_name_reports_a_definition_error_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._project(root, {
                "command": "python -c \"print('ok')\"",
                "grader": "not-a-real-grader", "expected": "ok",
            })
            report = run_behavior_assertions(root)
            entry = report["skills"]["gamma"]["assertions"][0]
            self.assertEqual(entry["outcome"], "fail")
            self.assertIn("grader definition error", entry["observed"])


if __name__ == "__main__":
    unittest.main()

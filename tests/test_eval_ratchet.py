"""The routing evals carry a baseline that only rises, and a determinism check.

A flipped case must fail the ratchet; two harness runs over the same inputs
must produce identical scores; a nondeterministic case is named, not hidden.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_evals  # noqa: E402


class RatchetTests(unittest.TestCase):
    def test_scores_shape(self) -> None:
        scores = godmode_evals.routing_scores(PLUGIN_ROOT)
        self.assertTrue(scores)
        for skill, row in scores.items():
            self.assertEqual(set(row), {"positive_hit", "positive_total", "negative_miss", "negative_total", "score"}, skill)
            self.assertLessEqual(row["score"], 1.0)

    def test_baseline_is_committed_and_clean(self) -> None:
        report = godmode_evals.ratchet(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "clean", report)

    def test_flipped_case_regresses(self) -> None:
        real = godmode_evals.routing_scores(PLUGIN_ROOT)
        skill = sorted(real)[0]
        flipped = json.loads(json.dumps(real))
        flipped[skill]["score"] = max(0.0, real[skill]["score"] - 0.25)
        with mock.patch.object(godmode_evals, "routing_scores", return_value=flipped):
            report = godmode_evals.ratchet(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "regression")
        self.assertEqual([r["skill"] for r in report["regressions"]], [skill])

    def test_write_refuses_a_lower_score(self) -> None:
        real = godmode_evals.routing_scores(PLUGIN_ROOT)
        skill = sorted(real)[0]
        flipped = json.loads(json.dumps(real))
        flipped[skill]["score"] = 0.0
        with mock.patch.object(godmode_evals, "routing_scores", return_value=flipped), \
             mock.patch.object(godmode_evals, "_write_baseline") as writer:
            report = godmode_evals.ratchet(PLUGIN_ROOT, write=True)
        self.assertEqual(report["verdict"], "regression")
        writer.assert_not_called()

    def test_dropped_case_is_a_regression_even_at_the_same_score(self) -> None:
        # A skill whose suite shrinks (e.g. 4 near-negatives to 3) while every
        # remaining case still passes keeps a perfect score - a ratchet that
        # only watches the ratio would call that clean. It must not.
        real = godmode_evals.routing_scores(PLUGIN_ROOT)
        skill = sorted(real)[0]
        shrunk = json.loads(json.dumps(real))
        shrunk[skill]["negative_total"] -= 1
        shrunk[skill]["negative_miss"] = min(shrunk[skill]["negative_miss"], shrunk[skill]["negative_total"])
        total = shrunk[skill]["positive_total"] + shrunk[skill]["negative_total"]
        shrunk[skill]["score"] = round(
            (shrunk[skill]["positive_hit"] + shrunk[skill]["negative_miss"]) / total, 4
        ) if total else 0.0
        self.assertEqual(shrunk[skill]["score"], 1.0)  # still a perfect score
        with mock.patch.object(godmode_evals, "routing_scores", return_value=shrunk):
            report = godmode_evals.ratchet(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "regression")
        self.assertEqual([r["skill"] for r in report["regressions"]], [skill])

    def test_write_refuses_a_lower_total(self) -> None:
        real = godmode_evals.routing_scores(PLUGIN_ROOT)
        skill = sorted(real)[0]
        shrunk = json.loads(json.dumps(real))
        shrunk[skill]["negative_total"] -= 1
        with mock.patch.object(godmode_evals, "routing_scores", return_value=shrunk), \
             mock.patch.object(godmode_evals, "_write_baseline") as writer:
            report = godmode_evals.ratchet(PLUGIN_ROOT, write=True)
        self.assertEqual(report["verdict"], "regression")
        writer.assert_not_called()

    def test_a_phantom_baseline_skill_is_reported_removed_not_a_regression(self) -> None:
        current = godmode_evals.routing_scores(PLUGIN_ROOT)
        phantom_baseline = {
            s: {"score": v["score"], "positive_total": v["positive_total"],
                "negative_total": v["negative_total"]}
            for s, v in current.items()
        }
        phantom_baseline["retired-skill"] = {"score": 1.0, "positive_total": 2, "negative_total": 2}
        with mock.patch.object(godmode_evals, "_read_baseline", return_value=phantom_baseline):
            report = godmode_evals.ratchet(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "clean", report)
        self.assertEqual(report["removed"], ["retired-skill"])

    def test_write_prunes_a_removed_skill(self) -> None:
        current = godmode_evals.routing_scores(PLUGIN_ROOT)
        phantom_baseline = {
            s: {"score": v["score"], "positive_total": v["positive_total"],
                "negative_total": v["negative_total"]}
            for s, v in current.items()
        }
        phantom_baseline["retired-skill"] = {"score": 1.0, "positive_total": 2, "negative_total": 2}
        with mock.patch.object(godmode_evals, "_read_baseline", return_value=phantom_baseline), \
             mock.patch.object(godmode_evals, "_write_baseline") as writer:
            report = godmode_evals.ratchet(PLUGIN_ROOT, write=True)
        self.assertEqual(report["verdict"], "clean", report)
        writer.assert_called_once()
        written_scores = writer.call_args.args[1]
        self.assertNotIn("retired-skill", written_scores)


class ReadBaselineTests(unittest.TestCase):
    """Every malformed shape falls back to None (no baseline recorded), never
    a traceback: a corrupt file must not permanently block the ratchet."""

    def _with_baseline_text(self, text: str) -> Path | None:
        import tempfile
        raw = tempfile.mkdtemp()
        root = Path(raw)
        (root / "evals").mkdir()
        (root / "evals" / "baseline.json").write_text(text, encoding="utf-8")
        return root

    def test_missing_file_returns_none(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(godmode_evals._read_baseline(Path(raw)))

    def test_unparsable_json_returns_none(self) -> None:
        root = self._with_baseline_text("{not valid json")
        self.assertIsNone(godmode_evals._read_baseline(root))

    def _with_blocks(self, scores, withhold_memory: bool = False) -> Path | None:
        return self._with_baseline_text(json.dumps({
            "schema": godmode_evals.BASELINE_SCHEMA,
            "blocks": [{"withhold_memory": withhold_memory, "scores": scores}],
            "runtime_version": "0.0.0",
        }))

    def test_wrong_schema_returns_none(self) -> None:
        root = self._with_baseline_text(json.dumps({
            "schema": "godmode-eval-baseline-v2",
            "scores": {"a": {"score": 1.0, "positive_total": 1, "negative_total": 1}},
        }))
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_blocks_not_a_list_returns_none(self) -> None:
        root = self._with_baseline_text(json.dumps({
            "schema": godmode_evals.BASELINE_SCHEMA,
            "blocks": {"withhold_memory": False, "scores": {}},
        }))
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_scores_not_a_dict_returns_none(self) -> None:
        root = self._with_blocks(["a", "b"])
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_row_not_a_dict_returns_none(self) -> None:
        root = self._with_blocks({"a": 1.0})
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_non_numeric_score_returns_none(self) -> None:
        root = self._with_blocks(
            {"a": {"score": "high", "positive_total": 1, "negative_total": 1}})
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_missing_field_returns_none(self) -> None:
        root = self._with_blocks({"a": {"score": 1.0, "positive_total": 1}})
        self.assertIsNone(godmode_evals._read_baseline(root))

    def test_a_non_boolean_mode_flag_matches_no_mode(self) -> None:
        root = self._with_baseline_text(json.dumps({
            "schema": godmode_evals.BASELINE_SCHEMA,
            "blocks": [{"withhold_memory": "no",
                        "scores": {"a": {"score": 1.0, "positive_total": 2,
                                         "negative_total": 3}}}],
        }))
        self.assertIsNone(godmode_evals._read_baseline(root))
        self.assertIsNone(godmode_evals._read_baseline(root, withhold_memory=True))

    def test_valid_v3_parses(self) -> None:
        row = {"score": 1.0, "positive_total": 2, "negative_total": 3}
        root = self._with_blocks({"a": row})
        self.assertEqual(godmode_evals._read_baseline(root), {"a": row})
        # The other mode is absent, not inherited from this one.
        self.assertIsNone(godmode_evals._read_baseline(root, withhold_memory=True))


class DeterminismTests(unittest.TestCase):
    def test_two_runs_are_identical(self) -> None:
        report = godmode_evals.determinism(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "deterministic", report)
        self.assertEqual(report["differences"], [])

    def test_nondeterministic_case_is_named(self) -> None:
        calls = {"n": 0}
        real = godmode_evals.run_routing_evals

        def flaky(project):
            calls["n"] += 1
            out = real(project)
            if calls["n"] == 2:
                out = json.loads(json.dumps(out))
                godmode_evals._flip_first_route(out)  # test helper exported by the module
            return out

        with mock.patch.object(godmode_evals, "run_routing_evals", side_effect=flaky):
            report = godmode_evals.determinism(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "nondeterministic")
        self.assertEqual(len(report["differences"]), 1)

    def test_budget_cap(self) -> None:
        report = godmode_evals.determinism(PLUGIN_ROOT, budget_cases=1)
        self.assertEqual(report["verdict"], "over-budget")


if __name__ == "__main__":
    unittest.main()

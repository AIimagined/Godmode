"""The latency check fails on a >=20% p95 regression and passes within tolerance.

Unit tests never time anything: they feed `check` fabricated measurements.
Below MIN_SAMPLES, `_p95`'s index lands on (or near) the sample max, so the
CLI-floor tests here call `main()` directly with an argv that fails the
floor check before `measure()` is ever reached - no subprocess is spawned,
no clock is raced.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gate_latency", PLUGIN_ROOT / "benchmarks" / "gate_latency.py")
gate_latency = importlib.util.module_from_spec(SPEC)
sys.modules["gate_latency"] = gate_latency
SPEC.loader.exec_module(gate_latency)

BASELINE = {"schema": "godmode-gate-latency-baseline-v1",
            "phases": {"fast_allow": {"p95_ms": 100.0}, "escalate": {"p95_ms": 400.0}}}


class LatencyCheckTests(unittest.TestCase):
    def test_within_tolerance_passes(self) -> None:
        measured = {"fast_allow": {"p95_ms": 115.0, "p50_ms": 90.0, "n": 21},
                    "escalate": {"p95_ms": 470.0, "p50_ms": 300.0, "n": 21}}
        self.assertEqual(gate_latency.check(BASELINE, measured)["verdict"], "within-budget")

    def test_twenty_percent_regression_fails(self) -> None:
        measured = {"fast_allow": {"p95_ms": 100.0, "p50_ms": 90.0, "n": 21},
                    "escalate": {"p95_ms": 480.0, "p50_ms": 300.0, "n": 21}}
        report = gate_latency.check(BASELINE, measured)
        self.assertEqual(report["verdict"], "regression")
        self.assertEqual([r["phase"] for r in report["regressions"]], ["escalate"])

    def test_injected_sleep_shape(self) -> None:
        measured = {"fast_allow": {"p95_ms": 100.0 + 500.0, "p50_ms": 590.0, "n": 21},
                    "escalate": {"p95_ms": 400.0, "p50_ms": 300.0, "n": 21}}
        self.assertEqual(gate_latency.check(BASELINE, measured)["verdict"], "regression")

    def test_recommended_timeouts_clamp(self) -> None:
        rec = gate_latency.recommended_timeouts({"fast_allow": {"p95_ms": 50.0}, "escalate": {"p95_ms": 50.0}})
        self.assertGreaterEqual(rec["pre_tool_use"], 3)
        rec = gate_latency.recommended_timeouts({"fast_allow": {"p95_ms": 50.0}, "escalate": {"p95_ms": 90_000.0}})
        self.assertLessEqual(rec["pre_tool_use"], 30)

    def test_committed_baseline_parses(self) -> None:
        data = json.loads((PLUGIN_ROOT / "benchmarks" / "gate_latency_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "godmode-gate-latency-baseline-v1")
        self.assertEqual(set(data["phases"]), {"fast_allow", "escalate"})
        self.assertGreaterEqual(data.get("n", 0), gate_latency.MIN_SAMPLES)

    def test_missing_phase_fails_never_silent_zero(self) -> None:
        measured = {"fast_allow": {"p95_ms": 100.0, "p50_ms": 90.0, "n": 21}}  # escalate absent
        report = gate_latency.check(BASELINE, measured)
        self.assertEqual(report["missing"], ["escalate"])
        self.assertNotEqual(report["verdict"], "within-budget")
        self.assertEqual(report["regressions"], [])  # missing, not a manufactured 0ms regression


class NotesLineTests(unittest.TestCase):
    """G-9: `notes_line()` formats the release-notes benchmark line from a
    fabricated baseline only - no measurement runs here."""

    def test_formats_the_line_from_a_fabricated_baseline(self) -> None:
        line = gate_latency.notes_line(BASELINE | {"n": 21})
        self.assertEqual(
            line, "Gate latency (p95, n=21): fast_allow 100 ms, escalate 400 ms")

    def test_rounds_fractional_p95_to_the_nearest_millisecond(self) -> None:
        baseline = {"n": 30, "phases": {"fast_allow": {"p95_ms": 1238.5385999950813},
                                         "escalate": {"p95_ms": 2260.796200003824}}}
        self.assertEqual(
            gate_latency.notes_line(baseline),
            "Gate latency (p95, n=30): fast_allow 1239 ms, escalate 2261 ms")

    def test_missing_phase_returns_none(self) -> None:
        baseline = {"n": 21, "phases": {"fast_allow": {"p95_ms": 100.0}}}  # escalate absent
        self.assertIsNone(gate_latency.notes_line(baseline))

    def test_non_dict_phases_returns_none(self) -> None:
        self.assertIsNone(gate_latency.notes_line({"n": 21, "phases": "nope"}))

    def test_committed_baseline_produces_a_line(self) -> None:
        data = json.loads((PLUGIN_ROOT / "benchmarks" / "gate_latency_baseline.json").read_text(encoding="utf-8"))
        line = gate_latency.notes_line(data)
        self.assertIsNotNone(line)
        self.assertTrue(line.startswith("Gate latency (p95, n="))
        self.assertIn("fast_allow", line)
        self.assertIn("escalate", line)


class NotesLineCliTests(unittest.TestCase):
    """`--notes-line` reads the committed baseline and prints; it never
    measures, so these point `BASELINE_PATH` at a fabricated file."""

    def setUp(self) -> None:
        self._original_path = gate_latency.BASELINE_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.addCleanup(setattr, gate_latency, "BASELINE_PATH", self._original_path)
        self._original_argv = sys.argv
        self.addCleanup(setattr, sys, "argv", self._original_argv)

    def test_prints_the_line_and_exits_zero(self) -> None:
        path = Path(self._tmpdir.name) / "baseline.json"
        path.write_text(json.dumps({"schema": gate_latency.BASELINE_SCHEMA, "n": 21,
                                     "phases": {"fast_allow": {"p95_ms": 100.0},
                                                "escalate": {"p95_ms": 400.0}}}), encoding="utf-8")
        gate_latency.BASELINE_PATH = path
        sys.argv = ["gate_latency.py", "--notes-line"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate_latency.main()
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(),
                          "Gate latency (p95, n=21): fast_allow 100 ms, escalate 400 ms")

    def test_missing_baseline_exits_2(self) -> None:
        gate_latency.BASELINE_PATH = Path(self._tmpdir.name) / "does-not-exist.json"
        sys.argv = ["gate_latency.py", "--notes-line"]
        self.assertEqual(gate_latency.main(), 2)

    def test_check_and_notes_line_together_is_a_parser_error(self) -> None:
        sys.argv = ["gate_latency.py", "--check", "--notes-line"]
        with self.assertRaises(SystemExit) as raised:
            gate_latency.main()
        self.assertEqual(raised.exception.code, 2)


class NSamplesTests(unittest.TestCase):
    def test_resolve_n_prefers_explicit_over_baseline(self) -> None:
        self.assertEqual(gate_latency._resolve_n(11, {"n": 21}), 11)

    def test_resolve_n_defaults_to_baseline_n(self) -> None:
        self.assertEqual(gate_latency._resolve_n(None, {"n": 25}), 25)

    def test_resolve_n_falls_back_to_min_samples(self) -> None:
        self.assertEqual(gate_latency._resolve_n(None, {}), gate_latency.MIN_SAMPLES)
        self.assertEqual(gate_latency._resolve_n(None, None), gate_latency.MIN_SAMPLES)

    def test_n_floor_error_below_min(self) -> None:
        self.assertIsNotNone(gate_latency._n_floor_error(11))
        self.assertIsNotNone(gate_latency._n_floor_error(gate_latency.MIN_SAMPLES - 1))

    def test_n_floor_error_at_or_above_min(self) -> None:
        self.assertIsNone(gate_latency._n_floor_error(gate_latency.MIN_SAMPLES))
        self.assertIsNone(gate_latency._n_floor_error(30))


class LoadBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_path = gate_latency.BASELINE_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.addCleanup(setattr, gate_latency, "BASELINE_PATH", self._original_path)

    def _point_at(self, text: str) -> None:
        path = Path(self._tmpdir.name) / "baseline.json"
        path.write_text(text, encoding="utf-8")
        gate_latency.BASELINE_PATH = path

    def test_missing_file_is_none(self) -> None:
        gate_latency.BASELINE_PATH = Path(self._tmpdir.name) / "does-not-exist.json"
        self.assertIsNone(gate_latency._load_baseline())

    def test_malformed_json_is_none_not_a_traceback(self) -> None:
        self._point_at("{not valid json")
        self.assertIsNone(gate_latency._load_baseline())

    def test_wrong_schema_is_none(self) -> None:
        self._point_at(json.dumps({"schema": "some-other-schema-v1", "phases": {}}))
        self.assertIsNone(gate_latency._load_baseline())

    def test_matching_schema_loads(self) -> None:
        self._point_at(json.dumps({"schema": gate_latency.BASELINE_SCHEMA, "n": 21, "phases": {}}))
        self.assertEqual(gate_latency._load_baseline()["schema"], gate_latency.BASELINE_SCHEMA)


class CliFloorAndExclusivityTests(unittest.TestCase):
    """These exercise `main()` on argv that must fail before `measure()` is
    ever called (the floor check, the missing/malformed-baseline check, and
    argparse's own mutual-exclusion check all short-circuit first) - so no
    subprocess is spawned and no live timing happens here either."""

    def setUp(self) -> None:
        self._original_path = gate_latency.BASELINE_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.addCleanup(setattr, gate_latency, "BASELINE_PATH", self._original_path)
        self._original_argv = sys.argv
        self.addCleanup(setattr, sys, "argv", self._original_argv)

    def _baseline_with_n(self, n: int) -> None:
        path = Path(self._tmpdir.name) / "baseline.json"
        path.write_text(json.dumps({
            "schema": gate_latency.BASELINE_SCHEMA, "n": n,
            "phases": {"fast_allow": {"p95_ms": 100.0}, "escalate": {"p95_ms": 400.0}},
        }), encoding="utf-8")
        gate_latency.BASELINE_PATH = path

    def test_check_refuses_explicit_n_below_floor(self) -> None:
        self._baseline_with_n(21)
        sys.argv = ["gate_latency.py", "--check", "--n", "11"]
        self.assertEqual(gate_latency.main(), 2)

    def test_write_baseline_refuses_explicit_n_below_floor(self) -> None:
        gate_latency.BASELINE_PATH = Path(self._tmpdir.name) / "unwritten-baseline.json"
        sys.argv = ["gate_latency.py", "--write-baseline", "--n", "11"]
        self.assertEqual(gate_latency.main(), 2)
        self.assertFalse(gate_latency.BASELINE_PATH.exists())

    def test_check_missing_baseline_exits_2(self) -> None:
        gate_latency.BASELINE_PATH = Path(self._tmpdir.name) / "does-not-exist.json"
        sys.argv = ["gate_latency.py", "--check"]
        self.assertEqual(gate_latency.main(), 2)

    def test_check_malformed_baseline_exits_2_not_a_traceback(self) -> None:
        path = Path(self._tmpdir.name) / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        gate_latency.BASELINE_PATH = path
        sys.argv = ["gate_latency.py", "--check"]
        self.assertEqual(gate_latency.main(), 2)

    def test_check_and_write_baseline_together_is_a_parser_error(self) -> None:
        sys.argv = ["gate_latency.py", "--check", "--write-baseline"]
        with self.assertRaises(SystemExit) as raised:
            gate_latency.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

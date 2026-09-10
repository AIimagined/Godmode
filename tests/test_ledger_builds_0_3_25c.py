"""Five ledgered candidates built 2026-09-11: memory hygiene over lessons
and decisions, registry rows proposed from recurring waivers, the hook
manifest desync check at session start, the hook timing probe, and the
held-back oracle whose checks the operator designates and the done bar
runs.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_hookproof import manifest_desync  # noqa: E402
from godmode_runtime.godmode_hygiene import hygiene  # noqa: E402
from godmode_runtime.godmode_heldback import held_checks, hold_check  # noqa: E402
from godmode_runtime.godmode_registry import proposed_rows  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery"


def _rec(kind: str, subject: str, seq: int, **data) -> dict:
    return {"kind": kind, "subject": subject, "sequence": seq, "data": data}


class HygieneTests(unittest.TestCase):
    def test_two_phrasings_of_one_lesson_are_a_near_duplicate(self) -> None:
        report = hygiene([
            _rec("lesson", "verify before claiming done", 1,
                 value="run the suite before saying the work is done", status="active"),
            _rec("lesson", "run the suite before done", 2,
                 value="verify by running the suite before claiming the work is done", status="active"),
            _rec("lesson", "quote errors exactly", 3, value="paste the error text verbatim", status="active"),
        ])
        self.assertEqual([f["sequences"] for f in report["near_duplicates"]], [[1, 2]])
        self.assertEqual(report["contradictions"], [])

    def test_opposite_polarity_on_shared_terms_is_a_contradiction(self) -> None:
        report = hygiene([
            _rec("decision", "hooks read stdin to EOF", 1,
                 value="the three hooks read stdin to EOF before parsing", status="active"),
            _rec("decision", "hooks stop at the first stdin object", 2,
                 value="the three hooks do not read stdin to EOF; they stop at the first parsed object",
                 status="active"),
        ])
        self.assertEqual([f["sequences"] for f in report["contradictions"]], [[1, 2]])

    def test_the_cap_bounds_what_is_read(self) -> None:
        records = [_rec("lesson", f"lesson {i}", i, value=f"unique rule number {i} about thing{i}", status="active")
                   for i in range(1, 101)]
        self.assertEqual(hygiene(records, cap=10)["considered"]["lesson"], 10)


class ProposedRowsTests(unittest.TestCase):
    def test_a_reason_that_waived_work_three_times_is_a_proposed_row(self) -> None:
        records = [
            _rec("obligation", f"retest lane {i}", i, status="waived",
                 reason="the vitest ratchet already covers this lane") for i in range(1, 4)
        ] + [_rec("obligation", "other", 9, status="waived", reason="operator chose to park the docs pass")]
        rows = proposed_rows(records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["occurrences"], 3)
        self.assertIn("vitest", rows[0]["symptom"])


class ManifestDesyncTests(unittest.TestCase):
    def test_a_sibling_install_with_a_different_manifest_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            running = home / "run"
            (running / "hooks").mkdir(parents=True)
            (running / "plugin.json").write_text(json.dumps({"name": "demo", "version": "1.0"}), encoding="utf-8")
            (running / "hooks" / "hooks.json").write_text('{"hooks": {"a": 1}}', encoding="utf-8")
            sibling = home / ".claude" / "plugins" / "cache" / "x" / "demo" / "1.0"
            (sibling / "hooks").mkdir(parents=True)
            (sibling / "plugin.json").write_text(json.dumps({"name": "demo", "version": "1.0"}), encoding="utf-8")
            (sibling / "hooks" / "hooks.json").write_text('{"hooks": {"a": 1}', encoding="utf-8")  # truncated
            other = home / ".claude" / "plugins" / "cache" / "x" / "other" / "1.0"
            (other / "hooks").mkdir(parents=True)
            (other / "plugin.json").write_text(json.dumps({"name": "other", "version": "1.0"}), encoding="utf-8")
            (other / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
            found = manifest_desync(running, home)
            self.assertIsNotNone(found)
            self.assertEqual(len(found["differs_from"]), 1)
            self.assertIn(str(sibling), found["differs_from"][0]["path"])
            (sibling / "hooks" / "hooks.json").write_text('{"hooks": {"a": 1}}', encoding="utf-8")
            self.assertIsNone(manifest_desync(running, home))


class HookTimingTests(unittest.TestCase):
    def test_the_probe_reports_wall_clock_per_run(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            report = console.time_hook(project, "pre-action", runs=2, host="claude")
        self.assertEqual(report["runs"], 2)
        self.assertEqual(len(report["elapsed_ms"]), 2)
        self.assertGreater(report["median_ms"], 0)
        self.assertIn(report["verdict"], ("within the declared timeout", "over the declared timeout"))


class HeldBackOracleTests(unittest.TestCase):
    def test_holding_a_check_needs_the_password_and_lands_outside_the_tree(self) -> None:
        from godmode_runtime.godmode_errors import AuthorizationError
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            with self.assertRaises(AuthorizationError):
                hold_check(archive, "python -c 'print(1)'", "wrong")
            hold_check(archive, "python -c \"import sys; sys.exit(1)\"", PASSWORD)
            self.assertEqual(len(held_checks(archive)), 1)
            self.assertFalse(list(project.glob("**/godmode-heldback.json")))

    def test_a_red_held_check_caps_a_verified_claim_at_observed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            hold_check(archive, "python -c \"import sys; sys.exit(1)\"", PASSWORD)
            console.main(["--project", str(project), "session", "open", "--label", "t"])
            out = io.StringIO()
            with redirect_stdout(out):
                console.main(["--project", str(project), "--json", "claim", "the suite is green",
                              "--grade", "verified", "--cite", "cmd:python -c \"print(1)\"", "--verify"])
            record = archive.select(kind="claim", limit=1)[-1]["data"]
        self.assertEqual(record["grade"], "observed", out.getvalue())
        self.assertIn("1 held-back check(s) ran, 1 red", out.getvalue())


if __name__ == "__main__":
    unittest.main()

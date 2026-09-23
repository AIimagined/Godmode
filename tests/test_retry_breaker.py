"""NS-10c: the flaky retry runner gains trip/cooldown state.

A registered flake that fails `n` isolated retries inside `window_hours`
is parked with a reason and skipped - never retried - until
`cooldown_hours` past the park record elapses. `breaker_state` is the pure
function: it never reads the wall clock itself, only the archive's own
`flaky-retry` (`outcome == "failed-isolated"`), `flake-parked`, and
`flake-readmitted` records compared against the caller's explicit `now` -
same discipline as `godmode_falsifiers.due_falsifiers` for the same
reason: a test cannot pin a clock the function reads on its own.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
DEV_SCRIPTS = PLUGIN_ROOT / "scripts" / "dev"
for extra in (SCRIPTS, DEV_SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_constants import (  # noqa: E402
    ACTION_SUBJECTS, RUN_INERT_SUBJECTS,
)
from godmode_runtime.godmode_trends import (  # noqa: E402
    breaker_state, record_flake_parked, record_flake_readmitted,
)
from test_godmode_runtime import isolated_project  # noqa: E402

import run_with_flaky_retry as runner  # noqa: E402

_TEST_ID = "tests.test_x.T.test_a"


def _seed_failures(archive, count: int, test_id: str = _TEST_ID) -> None:
    for _ in range(count):
        archive.append("action", "flaky-retry", {
            "test_id": test_id, "outcome": "failed-isolated",
            "operation": f"flake:{test_id}",
        })


class BreakerStateTests(unittest.TestCase):
    def test_nothing_recorded_is_closed(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            state = breaker_state(archive, _TEST_ID, datetime.now(timezone.utc))
            self.assertEqual(state["state"], "closed")
            self.assertEqual(state["failures_in_window"], 0)
            self.assertIsNone(state["parked_at"])
            self.assertIsNone(state["reopens_at"])

    def test_fewer_than_n_stays_closed(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 2)
            state = breaker_state(archive, _TEST_ID, datetime.now(timezone.utc), n=3)
            self.assertEqual(state["state"], "closed")
            self.assertEqual(state["failures_in_window"], 2)

    def test_n_failures_in_window_trips_the_breaker(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3)
            now = datetime.now(timezone.utc)
            state = breaker_state(archive, _TEST_ID, now, n=3, cooldown_hours=6)
            self.assertEqual(state["state"], "open")
            self.assertEqual(state["failures_in_window"], 3)
            self.assertTrue(state["newly_tripped"])
            self.assertFalse(state["readmitted"])
            self.assertIsNotNone(state["reason"])
            self.assertEqual(
                datetime.fromisoformat(state["reopens_at"])
                - datetime.fromisoformat(state["parked_at"]),
                timedelta(hours=6),
            )

    def test_failures_outside_the_window_do_not_count(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3)
            later = datetime.now(timezone.utc) + timedelta(hours=25)
            state = breaker_state(archive, _TEST_ID, later, n=3, window_hours=24)
            self.assertEqual(state["state"], "closed")
            self.assertEqual(state["failures_in_window"], 0)

    def test_an_active_park_record_stays_open_until_cooldown(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3)
            record_flake_parked(archive, _TEST_ID, "3 isolated failure(s)")
            soon = datetime.now(timezone.utc) + timedelta(hours=1)
            state = breaker_state(archive, _TEST_ID, soon, n=3, cooldown_hours=6)
            self.assertEqual(state["state"], "open")
            self.assertFalse(state["newly_tripped"])
            self.assertEqual(state["reason"], "3 isolated failure(s)")

    def test_cooldown_elapsed_readmits_with_no_new_failures(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3)
            record_flake_parked(archive, _TEST_ID, "3 isolated failure(s)")
            after_cooldown = datetime.now(timezone.utc) + timedelta(hours=6, minutes=1)
            state = breaker_state(archive, _TEST_ID, after_cooldown, n=3, cooldown_hours=6)
            self.assertEqual(state["state"], "closed")
            self.assertTrue(state["readmitted"])
            self.assertEqual(state["failures_in_window"], 0)

    def test_failures_before_the_park_do_not_recount_after_readmission(self) -> None:
        # The three failures that tripped the original park must not, by
        # themselves, immediately re-trip the breaker the moment cooldown
        # ends - only NEW failures recorded after the park count again.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3)
            record_flake_parked(archive, _TEST_ID, "3 isolated failure(s)")
            record_flake_readmitted(archive, _TEST_ID)
            after_cooldown = datetime.now(timezone.utc) + timedelta(hours=6, minutes=1)
            state = breaker_state(archive, _TEST_ID, after_cooldown, n=3, cooldown_hours=6)
            self.assertEqual(state["state"], "closed")
            self.assertFalse(state["readmitted"])
            self.assertEqual(state["failures_in_window"], 0)
            _seed_failures(archive, 3)
            state = breaker_state(archive, _TEST_ID, after_cooldown, n=3, cooldown_hours=6)
            self.assertEqual(state["state"], "open")
            self.assertTrue(state["newly_tripped"])

    def test_a_different_test_id_is_unaffected(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _seed_failures(archive, 3, test_id=_TEST_ID)
            state = breaker_state(archive, "tests.test_y.T.test_b", datetime.now(timezone.utc))
            self.assertEqual(state["state"], "closed")
            self.assertEqual(state["failures_in_window"], 0)


class RecordWritersTests(unittest.TestCase):
    def test_record_flake_parked_writes_the_action_subject(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_flake_parked(archive, _TEST_ID, "3 isolated failure(s)")
            rows = archive.select(kind="action", subject="flake-parked", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["data"]["test_id"], _TEST_ID)
            self.assertEqual(rows[0]["data"]["reason"], "3 isolated failure(s)")

    def test_record_flake_readmitted_writes_the_action_subject(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_flake_readmitted(archive, _TEST_ID)
            rows = archive.select(kind="action", subject="flake-readmitted", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["data"]["test_id"], _TEST_ID)

    def test_subjects_are_registered_and_run_inert(self) -> None:
        self.assertIn("flake-parked", ACTION_SUBJECTS)
        self.assertIn("flake-readmitted", ACTION_SUBJECTS)
        self.assertIn("flake-parked", RUN_INERT_SUBJECTS)
        self.assertIn("flake-readmitted", RUN_INERT_SUBJECTS)


FLAKY_MODULE = '''import unittest


class FlakyTests(unittest.TestCase):
    def test_x(self):
        self.assertTrue(False, "always fails - the breaker must skip this id")
'''


class RunnerBreakerIntegrationTests(unittest.TestCase):
    def test_a_parked_id_is_skipped_printed_recorded_and_non_blocking(self) -> None:
        # Fix round 1 (task-9-review.md, finding 2): a parked id is
        # non-blocking - printed and recorded, exactly like a registered
        # flake that passed isolated - never a run failure. Only a
        # genuine isolated-retry failure returns 1. No pre-existing
        # `flake-parked` record here: seeding only the failures exercises
        # the runner's own first-observation write (`newly_tripped`).
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            tests_dir = project / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_flaky.py").write_text(FLAKY_MODULE, encoding="utf-8")
            registry = tests_dir / "KNOWN-FLAKY.txt"
            registry.write_text("tests.test_flaky.FlakyTests.test_x\n", encoding="utf-8")
            test_id = "tests.test_flaky.FlakyTests.test_x"
            _seed_failures(archive, 3, test_id=test_id)

            previous_cwd = os.getcwd()
            os.chdir(project)
            try:
                with mock.patch.object(runner, "REGISTRY", registry):
                    buffer = io.StringIO()
                    with mock.patch.object(sys, "argv", ["run_with_flaky_retry.py", "tests.test_flaky"]):
                        with contextlib.redirect_stdout(buffer):
                            code = runner.main()
            finally:
                os.chdir(previous_cwd)

            output = buffer.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("parked", output)
            self.assertIn(test_id, output)
            self.assertNotIn("retrying registered flake isolated", output)
            parked_rows = archive.select(kind="action", subject="flake-parked", limit=10)
            self.assertEqual(len(parked_rows), 1)
            self.assertEqual(parked_rows[0]["data"]["test_id"], test_id)


if __name__ == "__main__":
    unittest.main()

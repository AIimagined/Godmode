"""godmode-triage: the shipped bundle and its flow, step by step.

Plan 7 Task 14 (NS-9b): the skill fronts `status remaining --digest`,
`history --kind request`, `recurring`, `hygiene`, `verify --falsifiers
[--dry-run]`, `checkpoint --review` and the four `remember` dispositions
(invariant then superseded, obligation mapping, answered, parked decision).
Each step runs here on a bare non-git temp project - never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402
from godmode_runtime.godmode_requests import (  # noqa: E402
    open_stated_requests, read_request_window, record_request)

NAME = "godmode-triage"
SKILL_DIR = faces.skill_dir(NAME)


class BundleTests(unittest.TestCase):
    def test_bundle_validates_and_lints(self) -> None:
        faces.assert_bundle(self, SKILL_DIR)

    def test_openai_yaml_is_hand_finished(self) -> None:
        faces.assert_openai_yaml_hand_finished(self, SKILL_DIR)

    def test_every_flow_verb_and_flag_exists(self) -> None:
        faces.assert_flow_verbs_exist(self, SKILL_DIR)

    def test_behaviour_assertions_are_read_only(self) -> None:
        faces.assert_assertions_read_only(self, SKILL_DIR)

    def test_routes_home_and_rejects_its_near_negatives(self) -> None:
        faces.assert_routes_cleanly(self, NAME)

    def test_forges_in_a_bare_temp_project(self) -> None:
        faces.assert_forges(self, SKILL_DIR)


def _open_asks(archive) -> set[str]:
    """Subjects of the open stated asks, through the one reader every
    surface (stop hook, status, preflight, history) shares."""
    records, _ = read_request_window(archive)
    return {str(r["subject"]) for r in open_stated_requests(records)}


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            self.assertEqual(run("session", "open")[0], 0)
            texts = {
                "rule": "please never name an outside source in any shipped text again",
                "work": "please add a retry flag to the export verb for flaky networks",
                "noise": "thanks, that answers my earlier question about the cache window",
                "park": "please port the capability matrix to the new host when possible",
            }
            asks = {key: record_request(archive, text)["subject"] for key, text in texts.items()}
            self.assertTrue(all(s.startswith("ask:") for s in asks.values()), asks)

            # Steps 1-4: counts and review lists.
            code, review = run("checkpoint", "--review")
            self.assertEqual(code, 0, review)
            self.assertEqual(len(review["requests"]["findings"]), 4)
            self.assertIn(run("status", "remaining", "--digest")[0], (0, 1))
            code, listed = run("history", "--kind", "request", "--limit", "400")
            self.assertEqual(code, 0, listed)
            self.assertEqual(_open_asks(archive), set(asks.values()))
            self.assertEqual(run("recurring", "--threshold", "3")[0], 0)
            self.assertEqual(run("hygiene", "--cap", "80")[0], 0)
            code, due = run("verify", "--falsifiers", "--dry-run")
            self.assertEqual(code, 0, due)

            # Fallback: a closure that names no open ask is refused.
            code, refused = run("remember", "--kind", "request",
                                "--subject", "ask:000000000000", "--status", "answered")
            self.assertNotEqual(code, 0, refused)
            self.assertIn("no open ask matches", str(refused))

            # Rule-shaped: invariant first, then the ask closes citing it.
            code, invariant = run("remember", "--kind", "invariant",
                                  "--subject", "no-outside-source-names",
                                  "--value", "shipped text never names an outside source")
            self.assertEqual(code, 0, invariant)
            code, closed = run("remember", "--kind", "request", "--subject", asks["rule"],
                               "--status", "superseded",
                               "--evidence", f"seq:{invariant['record']['sequence']}")
            self.assertEqual(code, 0, closed)

            # Work-shaped: mapped to a task; the ask stays open.
            code, mapped = run("remember", "--kind", "obligation", "--subject", "task-7",
                               "--value", f"maps {asks['work']}")
            self.assertEqual(code, 0, mapped)

            # Noise: answered.
            code, noise = run("remember", "--kind", "request", "--subject", asks["noise"],
                              "--status", "answered")
            self.assertEqual(code, 0, noise)

            # Parked: stays open, a decision records why.
            code, parked = run("remember", "--kind", "decision",
                               "--subject", f"parked:{asks['park']}",
                               "--value", "no reference read yet; revisit after the survey")
            self.assertEqual(code, 0, parked)

            # Step 7: the queue moved - what stays open is mapped or parked.
            self.assertEqual(_open_asks(archive), {asks["work"], asks["park"]})
            code, review = run("checkpoint", "--review")
            self.assertEqual(code, 0, review)
            still_open = {f["request"].split(" - ")[0] for f in review["requests"]["findings"]}
            self.assertEqual(still_open, {asks["work"], asks["park"]})
            # The mapped obligation is open work, so the digest says so.
            self.assertEqual(run("status", "remaining", "--digest")[0], 1)


if __name__ == "__main__":
    unittest.main()

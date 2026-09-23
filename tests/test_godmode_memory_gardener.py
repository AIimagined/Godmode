"""godmode-memory-gardener: the shipped bundle and its flow, step by step.

Plan 7 Task 13 (NS-9): the skill fronts `digest`, `hygiene`, `checkpoint
--review`, `forget --dry-run`/`forget`, `remember --supersedes`, `law
candidates` and `lessons promote|approve`. Each flow step runs here, in
order, on a bare non-git temp project with its own archive - never the live
one.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-memory-gardener"
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


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            code, first = run("remember", "--kind", "decision", "--subject", "cache-policy",
                              "--value", "keep the brief cache for one day")
            self.assertEqual(code, 0, first)
            code, _ = run("remember", "--kind", "decision", "--subject", "cache-policy-dup",
                          "--value", "keep the brief cache for one day")
            self.assertEqual(code, 0)

            # Step 1: tell the session; writes nothing.
            before = len(list(archive.read_events(verify=False)))
            code, story = run("digest", "--since", "1")
            self.assertEqual(code, 0, story)
            # Step 2 and 3: review lists only.
            code, review = run("hygiene", "--cap", "80")
            self.assertEqual(code, 0, review)
            code, moot = run("checkpoint", "--review")
            self.assertEqual(code, 0, moot)
            # Step 4: the preview records nothing.
            code, preview = run("forget", "--dry-run")
            self.assertEqual(code, 0, preview)
            self.assertEqual(len(list(archive.read_events(verify=False))), before)

            # Step 5: supersede the duplicate on the record, same kind only.
            older = first["sequence"] if "sequence" in first else first["record"]["sequence"]
            code, merged = run("remember", "--kind", "decision", "--subject", "cache-policy",
                               "--value", "keep the brief cache for one day (merged)",
                               "--supersedes", str(older))
            self.assertEqual(code, 0, merged)
            code, crossed = run("remember", "--kind", "lesson", "--subject", "cache-policy",
                                "--value", "x", "--guard", "y", "--supersedes", str(older))
            self.assertNotEqual(code, 0, crossed)

            # Step 6: clusters are a read.
            code, clusters = run("law", "candidates")
            self.assertEqual(code, 0, clusters)

            # Step 7: a promotion with no cite is refused.
            code, lesson = run("remember", "--kind", "lesson", "--subject", "brief-cache",
                               "--value", "the cache went stale", "--guard", "expire it daily")
            self.assertEqual(code, 0, lesson)
            lesson_seq = lesson["sequence"] if "sequence" in lesson else lesson["record"]["sequence"]
            code, refused = run("lessons", "promote", str(lesson_seq), "--rerun-hash", "0" * 64)
            self.assertNotEqual(code, 0, refused)

            # Step 8: close the loop.
            code, closed = run("checkpoint", "--summary", "gardened the archive", "--status", "active",
                               "--next", "resume the sprint", "--evidence", "seq:1")
            self.assertEqual(code, 0, closed)


if __name__ == "__main__":
    unittest.main()

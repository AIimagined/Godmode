"""godmode-evidence: the shipped bundle and its flow, step by step.

Plan 7 Task 14 (NS-9b): the skill fronts `reflect`, `claim --stale`,
`freshness`, `reanchor`, `claim --verify`, `claim --refuted-by`, `verify
--falsifiers [--dry-run]`, `claim --resolve`, `status remaining --digest`
and `claim --scan`. Each step runs here on a bare non-git temp project -
never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-evidence"
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

    def test_falsifier_dry_run_precedes_the_real_run(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        self.assertLess(commands.index("godmode verify --falsifiers --dry-run"),
                        commands.index("godmode verify --falsifiers"))


def _seq(project: Path, subject: str) -> int:
    code, history = faces.run(project, "history", "--kind", "claim", "--subject", subject)
    assert code == 0, history
    return history["records"][-1]["sequence"]


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            (project / "note.txt").write_text("alpha\n", encoding="utf-8")
            self.assertEqual(run("session", "open")[0], 0)
            exit_bearing = (f'cmd:"{sys.executable}" -c "import sys; '
                            "sys.exit(0 if 'alpha' in open('note.txt').read() else 1)\"")

            # Step 1: reflect before recording.
            code, reflected = run("reflect", "the note says alpha")
            self.assertEqual(code, 0, reflected)

            # Step 3: an exit-bearing cite verifies at the grade asked for ...
            code, strong = run("claim", "the note says alpha", "--grade", "verified",
                               "--cite", exit_bearing, "--verify")
            self.assertEqual(code, 0, strong)
            self.assertEqual(strong["grade"], "verified")
            # ... while a state-reporting one caps at observed.
            code, weak = run("claim", "the tree lists the note", "--grade", "verified",
                             "--cite", "cmd:git status", "--verify")
            self.assertEqual(weak["grade"], "observed", weak)

            # Step 4: a hypothesis carries its falsifier.
            code, hypothesis = run("claim", "the cache is the cause", "--grade", "hypothesis",
                                   "--refuted-by", f'"{sys.executable}" -c "import sys; sys.exit(1)"')
            self.assertEqual(code, 0, hypothesis)
            self.assertEqual(hypothesis["grade"], "hypothesis")

            # Step 5: nothing has aged past due yet; the listing runs nothing.
            code, due = run("verify", "--falsifiers", "--dry-run")
            self.assertEqual(code, 0, due)
            self.assertEqual(due["count"], 0)

            # Step 2 (next pass): a file cite drifts and --stale names it.
            code, grounded = run("claim", "note line one says alpha", "--grade", "observed",
                                 "--cite", "file:note.txt#L1")
            self.assertEqual(code, 0, grounded)
            (project / "note.txt").write_text("beta\n", encoding="utf-8")
            code, stale = run("claim", "--stale")
            self.assertEqual(stale["stale"], 1, stale)
            self.assertEqual(stale["claims"][0]["reason"], "changed")
            for verb in (("freshness",), ("reanchor",)):
                self.assertEqual(run(*verb)[0], 0, verb)

            # Step 6: resolve once, with evidence the claim did not already cite.
            drifted = _seq(project, "note line one says alpha")
            (project / "finding.txt").write_text("note.txt line one now reads beta\n",
                                                 encoding="utf-8")
            code, resolved = run("claim", "--resolve", str(drifted), "--outcome", "superseded",
                                 "--cite", "file:finding.txt#L1")
            self.assertEqual(code, 0, resolved)
            code, again = run("claim", "--resolve", str(drifted), "--outcome", "held",
                              "--cite", "file:note.txt#L1")
            self.assertNotEqual(code, 0, again)

            # Step 7: the backlog views run.
            code, digest = run("status", "remaining", "--digest")
            self.assertEqual(code, 0, digest)
            code, scan = run("claim", "--scan")
            self.assertEqual(code, 0, scan)


if __name__ == "__main__":
    unittest.main()

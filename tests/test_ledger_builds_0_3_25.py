"""Three ledgered candidates built 2026-09-11.

`intent_preserved` on a reopened ask (from a JSON-RPC task-state spec's
decide.override envelope): a reopen records that the operator disagreed;
whether they kept the agent's decision and reworded it or replaced it is
a second calibration signal the record now carries.

A committed test-cohesion map (from a hook toolkit's test-cohesion.sh):
`retest` derives pins from test text; a project that commits
`.godmode-test-map.json` adds the pins text cannot show.

`depends_on` between claims (from a virtual-pet companion's guard mode):
a verified claim resting on an observed one inherits the weaker grade,
and three claims resting on one unverified claim name it load-bearing.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_attest import record_claim  # noqa: E402
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from godmode_runtime.godmode_retest import pinning_tests  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


class IntentPreservedTests(unittest.TestCase):
    def test_a_reopen_records_whether_the_decision_was_kept_or_replaced(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = record_request(archive, "please rename the transport module and keep it green", session="s1")
            subject = str(first["subject"])
            out = io.StringIO()
            with redirect_stdout(out):
                console.main(["--project", str(project), "remember", "--kind", "request",
                              "--subject", subject, "--status", "closed"])
                console.main(["--project", str(project), "remember", "--kind", "request",
                              "--subject", subject, "--status", "open", "--intent-preserved", "replaced"])
            newest = archive.select(kind="request", limit=5)[-1]["data"]
        self.assertTrue(newest.get("reopened"))
        self.assertEqual(newest.get("intent_preserved"), "replaced")


class TestCohesionMapTests(unittest.TestCase):
    def test_a_committed_map_pins_what_the_text_cannot(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _git(project, "init", "-q")
            (project / "src").mkdir(); (project / "tests").mkdir()
            (project / "src" / "deep.py").write_text("x = 1\n", encoding="utf-8")
            (project / "tests" / "test_far.py").write_text("import json\n", encoding="utf-8")
            (project / ".godmode-test-map.json").write_text(
                json.dumps({"src/deep.py": ["tests/test_far.py", "tests/missing.py"]}), encoding="utf-8")
            _git(project, "add", "-A"); _git(project, "commit", "-q", "-m", "b")
            pinned = pinning_tests(project, ["src/deep.py"])
        self.assertEqual(pinned, {"tests/test_far.py": ["src/deep.py"]})


class DependsOnTests(unittest.TestCase):
    def test_a_claim_inherits_the_weaker_grade_of_what_it_rests_on(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            base = record_claim(archive, project, "s", "the cache is warm", "observed")
            leaning = record_claim(archive, project, "s", "so the second read is fast", "verified",
                                   cites=["doc:README.md"], depends_on=[int(base["sequence"])])
            data = leaning["data"]
            self.assertEqual(data["depends_on"], [int(base["sequence"])])
            self.assertEqual(data["inherited_from"], int(base["sequence"]))
            self.assertNotEqual(data["grade"], "verified")

    def test_three_claims_on_one_unverified_claim_name_it_load_bearing(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            base = record_claim(archive, project, "s", "the index is fresh", "observed")
            seq = int(base["sequence"])
            record_claim(archive, project, "s", "lookups hit", "observed", depends_on=[seq])
            record_claim(archive, project, "s", "writes land", "observed", depends_on=[seq])
            third = record_claim(archive, project, "s", "reads agree", "observed", depends_on=[seq])
        advisories = " ".join(third["data"].get("advisories") or [])
        self.assertIn("load-bearing", advisories)
        self.assertIn(str(seq), advisories)


if __name__ == "__main__":
    unittest.main()

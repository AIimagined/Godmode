"""NS-9b: the investigation skill's postmortem flow, one regression per step.

Each step of the flow in skills/godmode-investigation/SKILL.md names a verb;
this runs that verb the way the skill tells an agent to, in a bare non-git
temporary project, and checks what the skill promises it does. It also pins
the skill text to the flow, so a rewrite that drops a step fails here.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from test_method_contracts import WHOLE  # noqa: E402

SKILL = PLUGIN_ROOT / "skills" / "godmode-investigation" / "SKILL.md"
REPRO = "python check.py"
CHECK = "import pathlib, sys\nsys.exit(1 if pathlib.Path('broken').exists() else 0)\n"


def _run(project, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), *argv])
    try:
        payload = json.loads(out.getvalue())
    except ValueError:
        payload = {"raw": out.getvalue()}
    return code, payload, err.getvalue()


def _check_record(project, record):
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "postmortem.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return _run(project, "method", "--check-method", "5-whys", "--check-record", str(path))


class SkillTextTests(unittest.TestCase):
    def test_the_skill_carries_the_postmortem_flow(self) -> None:
        # The flow's detail lives in a reference file the skill links to
        # (0.3.28: the skill body is kept under its line ceiling).
        body = SKILL.read_text(encoding="utf-8")
        self.assertIn("## Postmortem flow", body)
        self.assertIn("references/postmortem-flow.md", body)
        text = body + (SKILL.parent / "references" / "postmortem-flow.md").read_text(encoding="utf-8")
        for verb in ("--repro", "hypothesis add", "hypothesis kill", "checklist template rca",
                     "method --check-method 5-whys --check-record", "--fixes", "hyp:<seq>"):
            self.assertIn(verb, text, verb)
        for gap in ("chain_not_validated", "countermeasures_missing:detection",
                    "root_is_blame", "incomplete:when"):
            self.assertIn(gap, text, gap)

    def test_the_skill_asks_for_competing_hypotheses(self) -> None:
        self.assertIn("at least two competing hypotheses", SKILL.read_text(encoding="utf-8"))


class PostmortemFlowTests(unittest.TestCase):
    """The flow end to end: red repro, rival hypotheses, checklist, contract, fix pair."""

    def test_the_whole_flow(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "check.py").write_text(CHECK, encoding="utf-8")
            (project / "broken").write_text("x", encoding="utf-8")
            session = open_session(archive, "postmortem")

            # 1. What failed: the incident holds the red reproduction run.
            code, incident, err = _run(project, "remember", "--kind", "incident",
                                       "--subject", "export empty", "--value", "empty file",
                                       "--repro", REPRO, "--session", session)
            self.assertEqual(code, 0, err)
            self.assertEqual(incident["repro"]["state"], "red")
            incident_seq = incident["record"]["sequence"]

            # Competing hypotheses, each with a kill experiment.
            _c, rival, _e = _run(project, "hypothesis", "add", "--cause", "the writer races",
                                 "--kills", "python -c \"raise SystemExit(4)\"")
            _c, cause, _e = _run(project, "hypothesis", "add", "--cause", "the marker file",
                                 "--kills", "python -c \"raise SystemExit(0)\"")
            _run(project, "hypothesis", "kill", str(rival["record"]["sequence"]),
                 "--session", session)
            _c, kept, _e = _run(project, "hypothesis", "kill",
                                str(cause["record"]["sequence"]), "--session", session)
            self.assertEqual(kept["status"], "survived")

            # 2. The RCA checklist, filed under a label.
            _c, template, _e = _run(project, "checklist", "template", "rca", "--for", "export")
            evidence = {
                "what": [f"repro:{REPRO}", "expected:a file with rows", "actual:an empty file"],
                "when": ["cmd:git log --oneline -20"],
                "where": ["file:check.py#L2"], "why": ["file:postmortem.json"],
                "fix-root": ["file:check.py#L2"], "lock": ["cmd:python -m unittest tests.test_check"],
            }
            for row in template["items"]:
                step = row["item"].rsplit(":", 1)[1]
                if step == "when":
                    continue
                argv = ["checklist", "update", "--item", row["item"], "--status", "complete"]
                for cite in evidence[step]:
                    argv += ["--evidence", cite]
                code, _p, err = _run(project, *argv)
                self.assertEqual(code, 0, err)

            # 3-4. The 5-Whys record with the extended contract, checked with
            # the checklist: the skipped "when" step is named.
            record = {**copy.deepcopy(WHOLE), "rca": "export"}
            code, verdict, _e = _check_record(project, record)
            self.assertEqual(code, 1)
            self.assertIn("incomplete:when", verdict["gaps"])
            blamed = {**record, "root": "human error"}
            _c, verdict, _e = _check_record(project, blamed)
            self.assertIn("root_is_blame", verdict["gaps"])
            _run(project, "checklist", "update", "--item", "rca:export:when",
                 "--status", "complete", "--evidence", "cmd:git log --oneline -20")
            code, verdict, _e = _check_record(project, record)
            self.assertEqual(code, 0, verdict)

            # 5. The fix pair: the same repro green now, citing the survivor.
            (project / "broken").unlink()
            code, claim, err = _run(project, "claim", "fixed the empty export",
                                    "--grade", "verified", "--cite", f"cmd:{REPRO}",
                                    "--cite", f"hyp:{cause['record']['sequence']}",
                                    "--fixes", str(incident_seq), "--verify",
                                    "--session", session)
            self.assertEqual(claim.get("grade"), "verified", (claim, err))

            # A fix resting on the killed rival is refused outright.
            code, _p, err = _run(project, "claim", "fixed the race", "--grade", "observed",
                                 "--cite", f"hyp:{rival['record']['sequence']}")
            self.assertNotEqual(code, 0)
            self.assertIn("killed", err)


if __name__ == "__main__":
    unittest.main()

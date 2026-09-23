"""NS-13e: reproduce first, evidence before the patch.

An incident carries its reproduction command and the run that showed it red,
recorded at write time by the attested runner; a fix claim naming that
incident verifies only when the same command is green now. Every command
here runs inside a bare, non-git temporary project.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
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

REPRO = "python check.py"
CHECK = "import pathlib, sys\nsys.exit(1 if pathlib.Path('broken').exists() else 0)\n"


def _run(project, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), *argv])
    text = out.getvalue()
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {"raw": text}
    return code, payload, err.getvalue()


def _broken_project(project: Path) -> None:
    (project / "check.py").write_text(CHECK, encoding="utf-8")
    (project / "broken").write_text("x", encoding="utf-8")


def _incident(project, session, *extra):
    return _run(project, "remember", "--kind", "incident", "--subject", "export empty",
                "--value", "the export writes an empty file", "--session", session, *extra)


class IncidentReproTests(unittest.TestCase):
    def test_an_incident_without_a_repro_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "t")
            code, _payload, err = _incident(project, session)
            incidents = [r for r in archive.read_events() if r["kind"] == "incident"]
        self.assertNotEqual(code, 0)
        self.assertIn("--repro", err)
        self.assertEqual(incidents, [])

    def test_a_waived_repro_is_recorded_as_underspecified(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "t")
            code, payload, err = _incident(project, session, "--no-repro", "seen once in production")
            self.assertEqual(code, 0, err)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
        self.assertEqual(incident["data"]["failure_class"], "underspecified-ask")
        self.assertEqual(incident["data"]["repro"]["state"], "waived")
        self.assertEqual(incident["data"]["repro"]["reason"], "seen once in production")

    def test_the_red_run_is_recorded_at_write_time(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            code, _payload, err = _incident(project, session, "--repro", REPRO)
            self.assertEqual(code, 0, err)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            check = [r for r in archive.read_events()
                     if r["kind"] == "attestation" and r["subject"] == "check:repro"]
        repro = incident["data"]["repro"]
        self.assertEqual(repro["state"], "red")
        self.assertEqual(repro["exit_code"], 1)
        self.assertEqual(repro["command"], REPRO)
        self.assertIn(f"repro:{REPRO}", incident["evidence"])
        self.assertEqual(len(check), 1)
        self.assertIn(f"seq:{check[0]['sequence']}", incident["evidence"])

    def test_the_citation_form_is_accepted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            code, _payload, err = _incident(project, session, "--evidence", f"repro:{REPRO}")
            self.assertEqual(code, 0, err)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
        self.assertEqual(incident["data"]["repro"]["state"], "red")

    def test_a_green_repro_is_recorded_as_not_reproducing(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            (project / "broken").unlink()
            session = open_session(archive, "t")
            code, _payload, err = _incident(project, session, "--repro", REPRO)
            self.assertEqual(code, 0, err)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
        self.assertEqual(incident["data"]["repro"]["state"], "repro-not-reproducing")


class FixClaimPairTests(unittest.TestCase):
    def _claim(self, project, session, incident_seq, cite=REPRO):
        return _run(project, "claim", "fixed the empty export", "--grade", "verified",
                    "--cite", f"cmd:{cite}", "--verify", "--fixes", str(incident_seq),
                    "--session", session)

    def test_red_then_green_verifies(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            _incident(project, session, "--repro", REPRO)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            (project / "broken").unlink()
            code, payload, err = self._claim(project, session, incident["sequence"])
        self.assertEqual(payload.get("grade"), "verified", (payload, err))
        self.assertEqual(code, 0)

    def test_a_missing_red_run_caps_at_observed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            (project / "broken").unlink()
            session = open_session(archive, "t")
            _incident(project, session, "--no-repro", "not reproduced yet")
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            _code, payload, err = self._claim(project, session, incident["sequence"])
        self.assertEqual(payload.get("grade"), "observed", (payload, err))
        self.assertIn("red", payload["reason"])

    def test_a_different_command_caps_at_observed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            (project / "other.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            session = open_session(archive, "t")
            _incident(project, session, "--repro", REPRO)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            (project / "broken").unlink()
            _code, payload, err = self._claim(project, session, incident["sequence"],
                                              cite="python other.py")
        self.assertEqual(payload.get("grade"), "observed", (payload, err))
        self.assertIn("reproduction command", payload["reason"])

    def test_still_red_caps_at_observed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            _incident(project, session, "--repro", REPRO)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            _code, payload, err = self._claim(project, session, incident["sequence"])
        self.assertNotEqual(payload.get("grade"), "verified", (payload, err))
        self.assertIn("reproduction", payload["reason"])

    def test_a_self_reported_green_does_not_complete_the_pair(self) -> None:
        # Early review B1: an attestation written from words (`attest --status
        # ran`) carrying the repro citation must not stand in for a run.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            _incident(project, session, "--repro", REPRO)
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
            code, _p, err = _run(project, "attest", "fake-green", "--status", "ran",
                                 "--result", "exit 0: ok", "--evidence", f"cmd:{REPRO}",
                                 "--session", session)
            self.assertEqual(code, 0, err)
            _code, payload, err = _run(project, "claim", "fixed the empty export",
                                       "--grade", "verified", "--cite", f"cmd:{REPRO}",
                                       "--fixes", str(incident["sequence"]), "--session", session)
        self.assertNotEqual(payload.get("grade"), "verified", (payload, err))
        self.assertIn("reproduction", payload.get("reason", ""))

    def test_a_refused_incident_runs_nothing(self) -> None:
        # Early review S1: validation precedes the run.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            code, _p, _err = _incident(project, session, "--repro", REPRO,
                                       "--failure-class", "bogus")
            checks = [r for r in archive.read_events()
                      if r["kind"] == "attestation" and r["subject"] == "check:repro"]
        self.assertNotEqual(code, 0)
        self.assertEqual(checks, [])

    def test_a_script_exiting_127_is_red(self) -> None:
        # Early review S2: only a command the runner could not start is not runnable.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "missing_tool.py").write_text("raise SystemExit(127)\n", encoding="utf-8")
            session = open_session(archive, "t")
            _incident(project, session, "--repro", "python missing_tool.py")
            incident = [r for r in archive.read_events() if r["kind"] == "incident"][-1]
        self.assertEqual(incident["data"]["repro"]["state"], "red")

    def test_fixes_must_name_an_incident(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _broken_project(project)
            session = open_session(archive, "t")
            other = archive.append("decision", "not an incident", {"status": "active"})
            code, _payload, err = self._claim(project, session, other["sequence"])
        self.assertNotEqual(code, 0)
        self.assertIn("incident", err)


if __name__ == "__main__":
    unittest.main()

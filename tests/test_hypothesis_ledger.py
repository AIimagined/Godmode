"""NS-13f: competing hypotheses are records with a kill experiment; a fix may
cite `hyp:<seq>` only when that hypothesis's kill ran and did not fire.

Kill commands run inside a bare, non-git temporary project.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from godmode_runtime import godmode_forget as forget_mod  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_census import TRACKED_SURFACES  # noqa: E402
from godmode_runtime.godmode_chronicle import KIND_INVARIANTS  # noqa: E402
from godmode_runtime.godmode_compress import MASKS  # noqa: E402
from godmode_runtime.godmode_constants import EVENT_KINDS  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSES = "python -c \"raise SystemExit(0)\""
FIRES = "python -c \"raise SystemExit(3)\""


def _run(project, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), *argv])
    try:
        payload = json.loads(out.getvalue())
    except ValueError:
        payload = {"raw": out.getvalue()}
    return code, payload, err.getvalue()


def _add(project, cause, kills):
    code, payload, err = _run(project, "hypothesis", "add", "--cause", cause, "--kills", kills)
    assert code == 0, err
    return payload["record"]["sequence"]


class RegistrationTests(unittest.TestCase):
    def test_the_kind_is_registered_everywhere_a_kind_must_be(self) -> None:
        self.assertIn("hypothesis", EVENT_KINDS)
        self.assertIn("hypothesis", KIND_INVARIANTS)
        self.assertIn("hypothesis", MASKS)
        self.assertIn("hypothesis", TRACKED_SURFACES)
        self.assertIn("hypothesis", forget_mod.EPISODIC_KINDS)

    def test_a_raw_append_cannot_mint_a_survivor(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("hypothesis", "h", {
                    "cause": "c", "confirms": [], "status": "survived",
                    "kills": {"command": "x", "ran": False, "fired": False}})
            # Early review 2, B1 (P1): ran=True must name the run it claims.
            with self.assertRaises(ArchiveError):
                archive.append("hypothesis", "h", {
                    "cause": "c", "confirms": [], "status": "survived",
                    "kills": {"command": "python -c 0", "ran": True, "fired": False}})


class LedgerTests(unittest.TestCase):
    def test_add_kill_status(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            survivor = _add(project, "the cache drops the second write", PASSES)
            rival = _add(project, "the writer races the flush", FIRES)
            code, killed, err = _run(project, "hypothesis", "kill", str(rival))
            self.assertEqual(code, 0, err)
            self.assertEqual((killed["status"], killed["ran"], killed["fired"]),
                             ("killed", True, True))
            _code, kept, _err = _run(project, "hypothesis", "kill", str(survivor))
            self.assertEqual(kept["status"], "survived")
            _code, status, _err = _run(project, "hypothesis", "status")
        by_seq = {row["sequence"]: row["status"] for row in status["hypotheses"]}
        self.assertEqual(by_seq, {survivor: "survived", rival: "killed"})

    def test_one_hypothesis_is_named_as_too_few(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _add(project, "only story", PASSES)
            _code, status, _err = _run(project, "hypothesis", "status")
        self.assertTrue(status["advisories"])


class FixCitationTests(unittest.TestCase):
    def _fix(self, project, seq):
        return _run(project, "claim", "fixed the dropped write", "--grade", "observed",
                    "--cite", f"hyp:{seq}")

    def test_a_fix_citing_an_untested_hypothesis_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            seq = _add(project, "the cache drops the second write", PASSES)
            code, _payload, err = self._fix(project, seq)
            claims = [r for r in archive.read_events() if r["kind"] == "claim"]
        self.assertNotEqual(code, 0)
        self.assertIn("has not run", err)
        self.assertEqual(claims, [])

    def test_a_fix_citing_a_killed_hypothesis_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            seq = _add(project, "the writer races the flush", FIRES)
            _run(project, "hypothesis", "kill", str(seq))
            code, _payload, err = self._fix(project, seq)
        self.assertNotEqual(code, 0)
        self.assertIn("killed", err)

    def test_a_verified_fix_citing_a_survivor_resolves(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            seq = _add(project, "the cache drops the second write", PASSES)
            _run(project, "hypothesis", "kill", str(seq))
            _code, payload, err = _run(project, "claim", "fixed the dropped write",
                                       "--grade", "verified", "--cite", f"hyp:{seq}")
        self.assertEqual(payload.get("unresolved"), [], (payload, err))

    def test_a_fix_citing_a_survivor_is_recorded(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            seq = _add(project, "the cache drops the second write", PASSES)
            _run(project, "hypothesis", "kill", str(seq))
            code, payload, err = self._fix(project, seq)
            claims = [r for r in archive.read_events() if r["kind"] == "claim"]
        self.assertEqual(len(claims), 1, (payload, err))
        self.assertIn(f"hyp:{seq}", claims[0]["evidence"])
        self.assertEqual(payload.get("unresolved"), [], payload)


class ForgedSurvivorTests(unittest.TestCase):
    """Early review 2, B1 (P2): a forged kill result cannot mint a survivor,
    even when it names a self-typed attestation with the kill subject."""

    def test_a_forged_of_record_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "t")
            seq = _add(project, "the cache drops the second write", PASSES)
            citation = "cmd:python -c raise SystemExit(0)"
            code, attested, err = _run(project, "attest", f"check:kill-hyp-{seq}",
                                       "--status", "ran", "--result", "exit 0",
                                       "--evidence", citation, "--session", session)
            self.assertEqual(code, 0, err)
            typed = [r for r in archive.read_events() if r["kind"] == "attestation"][-1]
            archive.append("hypothesis", "h", {
                "of": seq, "cause": "c", "confirms": [], "status": "survived",
                "kills": {"command": PASSES, "ran": True, "fired": False,
                          "citation": citation, "check_seq": typed["sequence"]}})
            code, _payload, err = _run(project, "claim", "fixed the dropped write",
                                       "--grade", "verified", "--cite", f"hyp:{seq}")
            claims = [r for r in archive.read_events() if r["kind"] == "claim"]
        self.assertNotEqual(code, 0)
        self.assertIn("runner attestation", err)
        self.assertEqual(claims, [])

    def test_a_killed_hypothesis_is_not_resurrected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "t")
            (project / "flag").write_text("x", encoding="utf-8")
            seq = _add(project, "the flag decides", "python -c \"import os; raise SystemExit(1 if os.path.exists('flag') else 0)\"")
            _code, killed, _err = _run(project, "hypothesis", "kill", str(seq))
            self.assertEqual(killed["status"], "killed")
            (project / "flag").unlink()
            code, _p, err = _run(project, "hypothesis", "kill", str(seq))
            self.assertNotEqual(code, 0)
            self.assertIn("stays killed", err)


class ForgetProtectionTests(unittest.TestCase):
    """A hypothesis a live fix claim cites stays hot, with its kill result."""

    def test_a_cited_hypothesis_and_its_kill_result_are_protected(self) -> None:
        records = [
            {"sequence": 1, "kind": "hypothesis", "subject": "h",
             "data": {"cause": "c", "status": "open"}},
            {"sequence": 2, "kind": "hypothesis", "subject": "h",
             "data": {"cause": "c", "status": "survived", "of": 1,
                      "kills": {"ran": True, "fired": False, "check_seq": 5}}},
            {"sequence": 3, "kind": "hypothesis", "subject": "other",
             "data": {"cause": "d", "status": "open"}},
            {"sequence": 4, "kind": "claim", "subject": "fixed",
             "data": {"grade": "observed"}, "evidence": ["hyp:1"]},
        ]
        protected = forget_mod.protected_sequences(records)
        self.assertIn(1, protected)
        self.assertIn(2, protected)
        # Early review 2, M2: the runner attestation the kill result names.
        self.assertIn(5, protected)
        self.assertNotIn(3, protected)

    def test_an_uncited_old_hypothesis_expires_and_a_cited_one_does_not(self) -> None:
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        old = (now - timedelta(days=forget_mod.TTL_DAYS["hypothesis"] + 1)).isoformat()
        records = [
            {"sequence": 1, "kind": "hypothesis", "subject": "h", "recorded_at": old,
             "data": {"cause": "c", "status": "survived"}},
            {"sequence": 2, "kind": "hypothesis", "subject": "g", "recorded_at": old,
             "data": {"cause": "d", "status": "killed"}},
            {"sequence": 3, "kind": "claim", "subject": "fixed", "recorded_at": now.isoformat(),
             "data": {"grade": "observed", "text": "rests on hyp:1"}, "evidence": []},
        ]
        eligible = {r["sequence"] for r in forget_mod.eligible_for_expiry(records, now=now)}
        self.assertEqual(eligible, {2})


if __name__ == "__main__":
    unittest.main()

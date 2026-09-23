"""NS-4 (0.3.28 Plan 5 Task 3): falsification bonds gate `atlas law ratify`.

WHY: an approval loop that can rubber-stamp itself is not an approval loop.
The falsification bond is the mechanism: a checker's pass counts only after
it has, in the SAME session, correctly failed on an injected guaranteed-bad
artifact - and `plant` already proves a guard fails when broken, so
`godmode_bonds.bond_test` reuses that exact green -> red -> green machinery
rather than reimplementing it.

`atlas law ratify <proposal-seq>` is refused (exit 2, a remedy, never a
downgrade) when: the proposal already has a verdict; the caller's own
current session does not chronicle as an operator-granted checker session
belonging to the caller (fix round 1, B1); no bond in that session was
written by that same caller and sealed `writer == "checker"`; the bond that
did run targeted a different file than the proposal (fix round 1, S6); the
bond that did run did not fail as expected (a rubber stamp); every bond
that did fail as expected there already ratified a different proposal (fix
round 1, S4 - one bond, one verdict); or the proposal's own `actor` equals
the ratifying caller's own agent fingerprint - compared as fingerprints,
never as role labels, so an operator-granted checker session still cannot
ratify its own proposal. Proposals are capped at `MAX_PROPOSALS_PER_SPRINT`
(12) OPEN (unratified) at a time (fix round 1, B2) - a quality filter on
evidence, never a truncation of any proposal's own text.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_bonds as bonds  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"


def _run(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, dict]:
    """One CLI round trip, JSON in, JSON out - `console_main` in-process."""
    out = io.StringIO()
    stdin_ctx = (
        mock.patch.object(sys, "stdin", io.StringIO(stdin))
        if stdin is not None else contextlib.nullcontext()
    )
    with stdin_ctx, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _clean_env():
    return mock.patch.dict(
        os.environ,
        {"GODMODE_SESSION": "", "GODMODE_AGENT_ID": "", "GODMODE_AS_OPERATOR": ""},
    )


def _write_fixture(project: Path) -> None:
    (project / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")


_REAL_CHECK = (
    "import sys\nfrom pathlib import Path\n"
    "sys.exit(0 if 'VALUE = 1' in Path('fixture.py').read_text() else 1)\n"
)
_RUBBER_CHECK = "pass\n"


def _write_check(project: Path, name: str, body: str) -> Path:
    path = project / name
    path.write_text(body, encoding="utf-8")
    return path


def _diff_file(tmp_dir: Path, content: str = "--- a\n+++ b\n") -> Path:
    """A uniquely-named diff file inside a caller-owned temp dir - never a
    fresh `tempfile.mkdtemp()` per call (fix round 1, N1: those were never
    cleaned up). The caller owns `tmp_dir`'s lifetime via
    `tempfile.TemporaryDirectory()`."""
    fd, path_str = tempfile.mkstemp(dir=str(tmp_dir), suffix=".diff")
    os.close(fd)
    path = Path(path_str)
    path.write_text(content, encoding="utf-8")
    return path


def _propose(project: Path, actor: str, target: str, tmp_dir: Path, cite: str = "seq:1") -> int:
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": actor}):
        diff_path = _diff_file(tmp_dir)
        code, payload = _run(
            project, "atlas", "law", "propose",
            "--target", target, "--diff", str(diff_path), "--cite", cite,
        )
    assert code == 0, payload
    return payload["sequence"]


def _open_checker_session(project: Path, archive: Chronicle, actor: str) -> str:
    broker = CapabilityBroker(archive)
    if not broker.configured():
        broker.configure(PASSWORD)
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": actor}):
        code, payload = _run(
            project, "session", "open", "--role", "checker",
            "--as-operator", "--password-stdin", stdin=f"{PASSWORD}\n",
        )
    assert code == 0, payload
    return payload["session"]


def _bond_test(project: Path, name: str, check_file: str, check_body: str,
               with_text: str = "VALUE = 2") -> tuple[int, dict]:
    check_path = _write_check(project, f"{name}_check.py", check_body)
    return _run(
        project, "atlas", "law", "bond-test", name,
        "--command", f"{sys.executable} {check_path.name}",
        "--file", check_file, "--replace", "VALUE = 1", "--with", with_text,
    )


class HappyPathTests(unittest.TestCase):
    def test_propose_bond_test_ratify(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                # The proposal's own --target must match the file the bond
                # breaks (fix round 1, S6) for the bond to bind to it.
                proposal_seq = _propose(project, "agent-proposer", "fixture.py", tmp_dir)

                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "goodbond", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)
                    self.assertTrue(bond_payload["failed_as_expected"])
                    self.assertEqual(bond_payload["writer"], "checker")

                    code, verdict = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 0, verdict)
                self.assertEqual(verdict["verdict"], "ratified")
                self.assertEqual(verdict["proposal_seq"], proposal_seq)
                self.assertEqual(verdict["bond_seq"], bond_payload["sequence"])
                self.assertEqual(verdict["actor"], "agent-checker")


class RefusalTests(unittest.TestCase):
    def test_ratify_refused_with_no_session_open(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "scripts/foo.py", tmp_dir)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker"}):
                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("no open session", payload["message"].lower())

    def test_ratify_refused_with_no_bond_this_session(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "scripts/foo.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("no checker bond ran", payload["message"].lower())

    def test_ratify_refused_when_bond_did_not_fail_as_expected(self) -> None:
        """The rubber-stamp fixture: a checker command that always exits 0
        never sees red, so the bond it produces cannot ratify anything."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "rubberbond", "fixture.py", _RUBBER_CHECK)
                    self.assertEqual(code, 1, bond_payload)
                    self.assertFalse(bond_payload["failed_as_expected"])

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("did not fail as expected", payload["message"])

    def test_ratify_refused_when_bond_ran_in_a_different_session(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "scripts/foo.py", tmp_dir)
                first_session = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": first_session}):
                    code, bond_payload = _bond_test(project, "firstbond", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)

                # A fresh checker session never inherits the earlier bond.
                second_session = _open_checker_session(project, archive, "agent-checker")
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": second_session}):
                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("no checker bond ran", payload["message"].lower())

    def test_proposer_equals_checker_refused_even_with_operator_grant(self) -> None:
        """The session role is fully operator-granted (real `--as-operator`
        + password verification, exactly as `session open --role checker`
        demands) - the refusal is not about the grant's legitimacy, it is
        that the ratifying actor and the proposing actor are the same
        fingerprint, compared directly, never through the role label."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-both", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-both")
                self.assertEqual(
                    _run(project, "history", "--kind", "session", "--json")[1]
                    ["records"][-1]["data"]["role_granted_by"],
                    "operator",
                )
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-both",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "selfbond", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)
                    self.assertEqual(bond_payload["writer"], "checker")

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("same actor", payload["message"])

    def test_thirteenth_proposal_refused_naming_the_count(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env(), \
                    mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-prolific"}):
                tmp_dir = Path(tmp)
                last_payload: dict = {}
                last_code = 0
                for index in range(bonds.MAX_PROPOSALS_PER_SPRINT + 1):
                    diff_path = _diff_file(tmp_dir)
                    last_code, last_payload = _run(
                        project, "atlas", "law", "propose",
                        "--target", f"scripts/c{index}.py", "--diff", str(diff_path),
                        "--cite", "seq:1",
                    )
                    if last_code != 0:
                        break
                self.assertEqual(index, bonds.MAX_PROPOSALS_PER_SPRINT, "cap fired at the wrong count")
                self.assertEqual(last_code, 2, last_payload)
                self.assertIn(str(bonds.MAX_PROPOSALS_PER_SPRINT), last_payload["message"])
                self.assertIn("MAX_PROPOSALS_PER_SPRINT", last_payload["message"])
                self.assertEqual(
                    bonds.proposals_this_sprint(archive), bonds.MAX_PROPOSALS_PER_SPRINT,
                    "a refused 13th proposal must not itself be recorded",
                )

    def test_propose_refused_with_no_citation(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env(), \
                    mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-x"}):
                tmp_dir = Path(tmp)
                diff_path = _diff_file(tmp_dir)
                code, payload = _run(
                    project, "atlas", "law", "propose",
                    "--target", "scripts/foo.py", "--diff", str(diff_path),
                )
                self.assertEqual(code, 2, payload)
                self.assertIn("cite", payload["message"].lower())

    def test_ratify_refused_for_an_unknown_proposal(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with _clean_env():
                session_id = _open_checker_session(project, archive, "agent-checker")
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, payload = _run(project, "atlas", "law", "ratify", "999")
                self.assertEqual(code, 2, payload)
                self.assertIn("no improvement_proposal", payload["message"].lower())


class ActorBindingTests(unittest.TestCase):
    """Fix round 1, B1: `ratify` binds the bond to the CALLER, not merely to
    a session-id string - a session id is not a secret and its grant never
    expires (`Chronicle._chronicled_session_role`'s own docstring), so
    matching only `bond.session == GODMODE_SESSION` let anyone who learned
    that id borrow the real checker's bond.
    """

    def test_ratify_refused_when_caller_borrows_anothers_session_id(self) -> None:
        """Attack per the review: agent B (`agent-checker`) holds a genuine
        operator-granted checker session and runs a real, passing bond in
        it. Agent C (`agent-thirdparty`) never opened a session and never
        bonded anything - it merely reads B's session id (not a secret) and
        sets GODMODE_SESSION to it. Ratify must still refuse."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "borrowed", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)
                    self.assertEqual(bond_payload["writer"], "checker")

                # Agent C never opened this session - it only names it.
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-thirdparty",
                                                   "GODMODE_SESSION": session_id}):
                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("checker session", payload["message"].lower())

    def test_ratify_refused_when_bonds_actor_field_is_forged(self) -> None:
        """Even from the caller's OWN, genuinely operator-granted checker
        session, a `checker_bond` whose own `actor` names someone else (a
        raw `archive.append` bypassing `bond_test`, which always stamps the
        real caller) must not count - the bond must be sealed
        `writer == "checker"` for this session AND owned by this caller's
        own actor fingerprint."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-thirdparty")
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-thirdparty",
                                                   "GODMODE_SESSION": session_id}):
                    forged = archive.append("checker_bond", "bond:forged", {
                        "session": session_id, "actor": "agent-checker",
                        "target": "fixture.py", "bad_case_hash": "a" * 64,
                        "failed_as_expected": True,
                    })
                    self.assertEqual(
                        forged["writer"], "checker",
                        "the forged bond must itself be sealed writer=checker for "
                        "this test to isolate the actor-binding check",
                    )

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("no checker bond ran", payload["message"].lower())


class SprintCapWindowTests(unittest.TestCase):
    """Fix round 1, B2: the cap counts OPEN proposals, never keyed on the
    `sprint` kind - `godmode status set` writes that same kind constantly
    as ordinary bookkeeping, so a boundary keyed on it reset on every
    unrelated status change."""

    def test_status_set_write_does_not_reset_the_proposal_window(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env(), \
                    mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-prolific"}):
                tmp_dir = Path(tmp)
                for index in range(bonds.MAX_PROPOSALS_PER_SPRINT):
                    _propose(project, "agent-prolific", f"scripts/c{index}.py", tmp_dir)

                # An ordinary, unrelated status write appends a `sprint`
                # record - it must not reset the open-proposal window.
                code, payload = _run(project, "status", "set", "some-item", "--state", "active")
                self.assertEqual(code, 0, payload)

                diff_path = _diff_file(tmp_dir)
                code, payload = _run(
                    project, "atlas", "law", "propose",
                    "--target", "scripts/one-more.py", "--diff", str(diff_path),
                    "--cite", "seq:1",
                )
                self.assertEqual(code, 2, payload)
                self.assertIn(str(bonds.MAX_PROPOSALS_PER_SPRINT), payload["message"])

    def test_ratified_proposal_frees_a_slot(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seqs = []
                for index in range(bonds.MAX_PROPOSALS_PER_SPRINT):
                    target = "fixture.py" if index == 0 else f"scripts/c{index}.py"
                    proposal_seqs.append(_propose(project, "agent-prolific", target, tmp_dir))

                # Cap reached: a 13th proposal is refused.
                diff_path = _diff_file(tmp_dir)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-prolific"}):
                    code, payload = _run(
                        project, "atlas", "law", "propose",
                        "--target", "scripts/blocked.py", "--diff", str(diff_path),
                        "--cite", "seq:1",
                    )
                self.assertEqual(code, 2, payload)

                # Ratifying the first proposal frees the slot it held.
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "freeing", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)
                    code, verdict = _run(project, "atlas", "law", "ratify", str(proposal_seqs[0]))
                self.assertEqual(code, 0, verdict)

                new_seq = _propose(project, "agent-prolific", "scripts/freed.py", tmp_dir)
                self.assertIsInstance(new_seq, int)


class BondConsumptionAndTargetTests(unittest.TestCase):
    """Fix round 1, S4 (one bond, one verdict) and S6 (a bond binds to the
    proposal's own target file)."""

    def test_ratify_refused_when_bond_already_consumed_by_a_verdict(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_one = _propose(project, "agent-proposer-1", "fixture.py", tmp_dir)
                proposal_two = _propose(project, "agent-proposer-2", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "onlybond", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)

                    code, verdict_one = _run(project, "atlas", "law", "ratify", str(proposal_one))
                    self.assertEqual(code, 0, verdict_one)

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_two))
                self.assertEqual(code, 2, payload)
                self.assertIn("fresh", payload["message"].lower())

    def test_ratify_refused_when_bond_targets_a_different_file(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "scripts/other.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "wrongtarget", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("different file", payload["message"])

    def test_ratify_refused_when_proposal_already_has_a_verdict(self) -> None:
        """Nit N5: even with a second, fresh, passing bond available, a
        proposal already ratified once cannot ratify again."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as tmp, _clean_env():
                tmp_dir = Path(tmp)
                proposal_seq = _propose(project, "agent-proposer", "fixture.py", tmp_dir)
                session_id = _open_checker_session(project, archive, "agent-checker")
                _write_fixture(project)
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                   "GODMODE_SESSION": session_id}):
                    code, bond_payload = _bond_test(project, "onceonly", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload)
                    code, verdict = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                    self.assertEqual(code, 0, verdict)

                    code, bond_payload_2 = _bond_test(project, "twicebond", "fixture.py", _REAL_CHECK)
                    self.assertEqual(code, 0, bond_payload_2)

                    code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
                self.assertEqual(code, 2, payload)
                self.assertIn("already has an improvement_verdict", payload["message"])


class SequenceLookupTests(unittest.TestCase):
    """Fix round 1, S5: `_record_by_sequence` must not silently miss a
    proposal older than the most recent 500 records of its kind
    (`Chronicle.select`'s own clamp, `min(limit, 500)`)."""

    def test_record_by_sequence_finds_a_proposal_older_than_500_records(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = archive.append("improvement_proposal", "old-target", {
                "target": "old-target", "diff_hash": "a" * 64,
                "evidence": ["seq:1"], "actor": "agent-old",
            })
            for index in range(510):
                archive.append("improvement_proposal", f"pad-{index}", {
                    "target": f"pad-{index}", "diff_hash": "b" * 64,
                    "evidence": ["seq:1"], "actor": "agent-pad",
                })
            found = bonds._record_by_sequence(archive, "improvement_proposal", first["sequence"])
            self.assertIsNotNone(found)
            self.assertEqual(found["data"]["target"], "old-target")


class InvariantTests(unittest.TestCase):
    """A raw `archive.append()` that bypasses `godmode_bonds` entirely is
    held to the same shape at the archive seam (`godmode_invariants.py`)."""

    def test_improvement_proposal_needs_target_hash_evidence_and_actor(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("improvement_proposal", "x", {
                    "diff_hash": "a" * 64, "evidence": ["seq:1"], "actor": "a",
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_proposal", "x", {
                    "target": "x", "evidence": ["seq:1"], "actor": "a",
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_proposal", "x", {
                    "target": "x", "diff_hash": "a" * 64, "evidence": [], "actor": "a",
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_proposal", "x", {
                    "target": "x", "diff_hash": "a" * 64, "evidence": ["seq:1"], "actor": "",
                })
            record = archive.append("improvement_proposal", "x", {
                "target": "x", "diff_hash": "a" * 64, "evidence": ["seq:1"], "actor": "a",
            })
            self.assertEqual(record["kind"], "improvement_proposal")

    def test_checker_bond_needs_session_actor_target_hash_and_real_boolean(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("checker_bond", "b", {
                    "session": "S-x", "target": "t", "bad_case_hash": "a" * 64,
                    "failed_as_expected": True,
                })
            with self.assertRaises(ArchiveError):
                archive.append("checker_bond", "b", {
                    "session": "S-x", "actor": "a", "target": "t", "failed_as_expected": True,
                })
            with self.assertRaises(ArchiveError):
                archive.append("checker_bond", "b", {
                    "actor": "a", "target": "t", "bad_case_hash": "a" * 64,
                    "failed_as_expected": True,
                })
            with self.assertRaises(ArchiveError):
                archive.append("checker_bond", "b", {
                    "session": "S-x", "actor": "a", "bad_case_hash": "a" * 64,
                    "failed_as_expected": True,
                })
            with self.assertRaises(ArchiveError):
                archive.append("checker_bond", "b", {
                    "session": "S-x", "actor": "a", "target": "t", "bad_case_hash": "a" * 64,
                    "failed_as_expected": "true",
                })
            record = archive.append("checker_bond", "b", {
                "session": "S-x", "actor": "a", "target": "t", "bad_case_hash": "a" * 64,
                "failed_as_expected": False,
            })
            self.assertEqual(record["kind"], "checker_bond")

    def test_improvement_verdict_needs_positive_seqs_actor_and_ratified(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("improvement_verdict", "v", {
                    "proposal_seq": 0, "actor": "a", "verdict": "ratified", "bond_seq": 1,
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_verdict", "v", {
                    "proposal_seq": 1, "actor": "a", "verdict": "ratified", "bond_seq": -1,
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_verdict", "v", {
                    "proposal_seq": 1, "actor": "", "verdict": "ratified", "bond_seq": 1,
                })
            with self.assertRaises(ArchiveError):
                archive.append("improvement_verdict", "v", {
                    "proposal_seq": 1, "actor": "a", "verdict": "rubber-stamped", "bond_seq": 1,
                })
            record = archive.append("improvement_verdict", "v", {
                "proposal_seq": 1, "actor": "a", "verdict": "ratified", "bond_seq": 1,
            })
            self.assertEqual(record["kind"], "improvement_verdict")


if __name__ == "__main__":
    unittest.main()

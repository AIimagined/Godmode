"""NS-12a + NS-12d (0.3.28 Plan 5 Task 9): the skill-impact ledger and the
strict-improvement gate.

WHY: a skill-evolution loop that keeps every change it tries is not a gate,
it is a diary. NS-12d's answer is the same shape as NS-4's falsification
bond one task earlier - a claim only counts once it survived a real test -
applied to skill quality instead of a checker's own ability to fail: a
change is `accepted` only when the eval harness's own per-skill score
STRICTLY improves on the best ever recorded for that target; anything else
(a tie, a regression) is `rejected`, the target is restored to the exact
bytes it had before the change (never the operator's own `git checkout`),
and the ledger keeps the attempt so the same diff is never re-proposed
blind (NS-12a).

Both writers are exercised end to end through the real CLI
(`godmode_runtime.godmode_console.main`), the same way `tests/test_law_bond.py`
exercises `atlas law propose|bond-test|ratify` - no direct calls to
`godmode_skillimpact` functions that would bypass the console seam, except
for the one forge-regression case noted at its own test (the vocabulary
needed to make a FRESH skill legitimately score zero end to end would
obscure the assertion it exists to make).
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

from godmode_runtime import godmode_skillimpact as skillimpact  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"


def _run(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, dict]:
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


def _diff_file(tmp_dir: Path, content: str) -> Path:
    fd, path_str = tempfile.mkstemp(dir=str(tmp_dir), suffix=".diff")
    os.close(fd)
    path = Path(path_str)
    path.write_text(content, encoding="utf-8")
    return path


def _success_cites(archive: Chronicle) -> list[str]:
    """`skill forge` requires three DISTINCT, resolvable `--success-evidence`
    citations (NS-11d), so a forge test has to put three real records in the
    archive first and name them. Nothing here depends on their kind - the
    CLI checks only that each sequence exists.
    """
    return [
        f"seq:{archive.append('action', f'forge-success-{index}', {'gate': 'allow'})['sequence']}"
        for index in range(3)
    ]


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


# A single, deterministic skill fixture. `state.py` is what every ratify
# --diff in this file edits; `check_demo.py` (a behaviour-assertion probe)
# and `godmode-evals.json` (routing) never change across a test, so the
# routing half of `skill_score` is IDENTICAL before and after every ratify
# here - only the behaviour half, driven by `state.py`'s own content, ever
# moves. That isolates "did the gate compare the right numbers" from any
# question about the routing corpus.
_CHECK_BODY = (
    "from pathlib import Path\n"
    "import sys\n"
    "text = Path('skills/demo/state.py').read_text()\n"
    "sys.exit(0 if 'VALUE = 2' in text else 1)\n"
)


def _write_demo_skill(project: Path, initial_value: str) -> None:
    skill_dir = project / "skills" / "demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: \"Calibrate the demo widget subsystem. Use when calibrating a demo widget.\"\n"
        "---\n\n# Demo\n", encoding="utf-8",
    )
    (skill_dir / "state.py").write_text(f"VALUE = {initial_value}\n", encoding="utf-8")
    (skill_dir / "check_demo.py").write_text(_CHECK_BODY, encoding="utf-8")
    (skill_dir / "godmode-evals.json").write_text(
        json.dumps({
            "schema": "godmode-skill-eval-v1",
            "skill": "demo",
            "routing": {
                "positive": ["calibrate the demo widget"],
                "near_negative": ["order a pizza for lunch"],
            },
            "behavior_assertions": [
                # `_run_check` (godmode_evals.py) special-cases the literal
                # word "python" as argv[0], substituting `sys.executable`
                # AFTER `shlex.split` - the one spelling that survives a
                # Windows interpreter path (backslashes, a "Program Files"
                # space) unmangled; `godmode_attest.split_command` protects
                # backslashes for `atlas law bond-test`'s own `--command`,
                # but that fix is not this eval runner's, so this fixture
                # uses the spelling the runner itself already expects.
                {"assert": "state reports VALUE 2",
                 "check": {"command": "python skills/demo/check_demo.py"}},
            ],
        }, indent=2), encoding="utf-8",
    )


def _propose_skill_change(
    project: Path, actor: str, diff_content: str, tmp_dir: Path,
    target: str = "skills/demo/state.py",
) -> tuple[int, dict]:
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": actor}):
        diff_path = _diff_file(tmp_dir, diff_content)
        return _run(
            project, "atlas", "law", "propose",
            "--target", target, "--diff", str(diff_path), "--cite", "seq:1",
        )


def _propose(project: Path, actor: str, diff_content: str, tmp_dir: Path,
             target: str = "skills/demo/state.py") -> tuple[int, Path]:
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": actor}):
        diff_path = _diff_file(tmp_dir, diff_content)
        code, payload = _run(
            project, "atlas", "law", "propose",
            "--target", target, "--diff", str(diff_path), "--cite", "seq:1",
        )
    assert code == 0, payload
    return payload["sequence"], diff_path


def _bond_test_on_state(project: Path) -> tuple[int, dict]:
    check_path = project / "bondcheck.py"
    check_path.write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.exit(0 if 'VALUE' in Path('skills/demo/state.py').read_text() else 1)\n",
        encoding="utf-8",
    )
    return _run(
        project, "atlas", "law", "bond-test", "demobond",
        "--command", f"{sys.executable} bondcheck.py",
        "--file", "skills/demo/state.py", "--replace", "VALUE", "--with", "NOPE",
    )


class SkillImpactInvariantTests(unittest.TestCase):
    """Direct appends against `Chronicle.append`, never through
    `godmode_skillimpact.record_impact` - proving the KIND_INVARIANTS
    validator itself refuses a malformed record, not just this module's
    own convenience wrapper."""

    def test_missing_target_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("skill_impact", "x", {
                    "target": "", "diff_hash": "a" * 64,
                    "score_before": 0.0, "score_after": 0.5,
                    "outcome": "accepted", "patterns": [],
                })
            self.assertIn("non-empty 'target'", str(ctx.exception))

    def test_bad_diff_hash_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("skill_impact", "skills/demo", {
                    "target": "skills/demo/state.py", "diff_hash": "not-a-digest",
                    "score_before": 0.0, "score_after": 0.5,
                    "outcome": "accepted", "patterns": [],
                })
            self.assertIn("sha256 digest", str(ctx.exception))

    def test_non_numeric_score_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("skill_impact", "skills/demo", {
                    "target": "skills/demo/state.py", "diff_hash": "a" * 64,
                    "score_before": "high", "score_after": 0.5,
                    "outcome": "accepted", "patterns": [],
                })
            self.assertIn("real number", str(ctx.exception))

    def test_third_outcome_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("skill_impact", "skills/demo", {
                    "target": "skills/demo/state.py", "diff_hash": "a" * 64,
                    "score_before": 0.5, "score_after": 0.5,
                    "outcome": "neutral", "patterns": [],
                })
            self.assertIn("accepted", str(ctx.exception))

    def test_negative_pattern_seq_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("skill_impact", "skills/demo", {
                    "target": "skills/demo/state.py", "diff_hash": "a" * 64,
                    "score_before": 0.0, "score_after": 0.5,
                    "outcome": "accepted", "patterns": [-1],
                })
            self.assertIn("positive", str(ctx.exception))

    def test_well_formed_record_accepted(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append("skill_impact", "skills/demo", {
                "target": "skills/demo/state.py", "diff_hash": "a" * 64,
                "score_before": 0.0, "score_after": 0.5,
                "outcome": "accepted", "patterns": [],
            })
            self.assertEqual(record["kind"], "skill_impact")


class GateFormulaTests(unittest.TestCase):
    """`gate_outcome` in isolation: the one place "strict" and "neutral ->
    rejected" are decided, so the comparison operator itself is pinned."""

    def test_strict_improvement_over_own_before_accepts(self) -> None:
        self.assertEqual(skillimpact.gate_outcome(0.5, 0.6, None), "accepted")

    def test_tie_against_own_before_is_rejected(self) -> None:
        self.assertEqual(skillimpact.gate_outcome(0.5, 0.5, None), "rejected")

    def test_regression_against_own_before_is_rejected(self) -> None:
        self.assertEqual(skillimpact.gate_outcome(0.5, 0.4, None), "rejected")

    def test_gate_compares_against_best_recorded_not_just_before(self) -> None:
        # Even though this change beats ITS OWN before-score, a stronger
        # accepted change already stands on the record for this target -
        # NS-12d gates against the best ever recorded, not a local delta.
        self.assertEqual(skillimpact.gate_outcome(0.2, 0.6, 0.7), "rejected")
        self.assertEqual(skillimpact.gate_outcome(0.2, 0.8, 0.7), "accepted")

    def test_gate_uses_the_higher_of_best_recorded_and_score_before(self) -> None:
        """B3: `best_recorded_score` keys on the exact TARGET string, but
        the score it stores is skill-wide - so a stale per-target ceiling
        can sit BELOW where the skill actually stands right now (an
        accepted change already landed against a sibling file, or routing-
        corpus drift). The baseline must be the higher of the two, or a
        regression from where the skill lives today would be `accepted`
        just because an old per-target ceiling was lower."""
        # score_before (0.9) is already above the stale best_so_far (0.6):
        # a regression to 0.8 must still be rejected, not accepted merely
        # for beating the stale ceiling.
        self.assertEqual(skillimpact.gate_outcome(0.9, 0.8, 0.6), "rejected")
        # Beating BOTH the stale ceiling and the live score is accepted.
        self.assertEqual(skillimpact.gate_outcome(0.9, 0.95, 0.6), "accepted")
        # A tie against score_before (which exceeds best_so_far) is still a
        # tie - rejected, never a `>=`.
        self.assertEqual(skillimpact.gate_outcome(0.9, 0.9, 0.6), "rejected")


class RatifyStrictImprovementTests(unittest.TestCase):
    def _ratify_flow(self, project: Path, archive: Chronicle, tmp_dir: Path,
                      diff_content: str) -> tuple[int, dict, int]:
        with _clean_env():
            proposal_seq, _ = _propose(project, "agent-proposer", diff_content, tmp_dir)
            session_id = _open_checker_session(project, archive, "agent-checker")
            diff_path = _diff_file(tmp_dir, diff_content)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                               "GODMODE_SESSION": session_id}):
                code, bond_payload = _bond_test_on_state(project)
                self.assertEqual(code, 0, bond_payload)
                self.assertTrue(bond_payload["failed_as_expected"])
                code, payload = _run(
                    project, "atlas", "law", "ratify", str(proposal_seq),
                    "--diff", str(diff_path),
                )
            return code, payload, proposal_seq

    def test_accepted_on_strict_improvement(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # fails the check: before = 0.5
            with tempfile.TemporaryDirectory() as tmp:
                code, payload, proposal_seq = self._ratify_flow(
                    project, archive, Path(tmp), "VALUE = 2\n")  # passes: after = 1.0
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["verdict"], "ratified")
            impact = payload["skill_impact"]
            self.assertEqual(impact["outcome"], "accepted")
            self.assertEqual(impact["score_before"], 0.5)
            self.assertEqual(impact["score_after"], 1.0)
            self.assertEqual(
                (project / "skills" / "demo" / "state.py").read_text(encoding="utf-8"),
                "VALUE = 2\n",
            )
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["outcome"], "accepted")

    def test_neutral_change_rejected_and_bytes_restored(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # before = 0.5
            with tempfile.TemporaryDirectory() as tmp:
                code, payload, proposal_seq = self._ratify_flow(
                    project, archive, Path(tmp), "VALUE = 3\n")  # still fails: after = 0.5 (tie)
            self.assertEqual(code, 2, payload)
            self.assertIn("did not strictly improve", payload["message"])
            self.assertEqual(
                (project / "skills" / "demo" / "state.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
                "a neutral change must restore the pre-change bytes, not keep the edit",
            )
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["outcome"], "rejected")
            self.assertEqual(records[0]["data"]["score_before"], 0.5)
            self.assertEqual(records[0]["data"]["score_after"], 0.5)
            # No verdict was archived for a refused ratification.
            verdicts = [r for r in archive.read_events(verify=False)
                        if r["kind"] == "improvement_verdict"]
            self.assertEqual(verdicts, [])

    def test_regression_rejected_and_bytes_restored(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="2")  # passes: before = 1.0
            with tempfile.TemporaryDirectory() as tmp:
                code, payload, proposal_seq = self._ratify_flow(
                    project, archive, Path(tmp), "VALUE = 1\n")  # fails: after = 0.5
            self.assertEqual(code, 2, payload)
            self.assertIn("did not strictly improve", payload["message"])
            self.assertEqual(
                (project / "skills" / "demo" / "state.py").read_text(encoding="utf-8"),
                "VALUE = 2\n",
            )
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(records[0]["data"]["outcome"], "rejected")
            self.assertEqual(records[0]["data"]["score_before"], 1.0)
            self.assertEqual(records[0]["data"]["score_after"], 0.5)

    def test_second_accepted_change_gates_on_best_recorded_not_its_own_before(self) -> None:
        """After one accepted change lands at 1.0, a second proposal that
        merely returns to a WORSE state than 1.0 must be rejected even
        though its own before-score (whatever the file was mutated to by a
        third party) is lower - the ratchet is against the BEST recorded,
        never a fresh per-proposal baseline."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                code, payload, _ = self._ratify_flow(project, archive, tmp_dir, "VALUE = 2\n")
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["skill_impact"]["score_after"], 1.0)

                # A second change that only ties the fixed 1.0 ceiling (the
                # routing half is already perfect and the behaviour half
                # cannot exceed 1.0) must be rejected - there is nothing
                # left to strictly improve on.
                code2, payload2, _ = self._ratify_flow(project, archive, tmp_dir, "VALUE = 2\n")
            self.assertEqual(code2, 2, payload2)
            self.assertIn("did not strictly improve", payload2["message"])


class RejectedDiffRefusedAgainTests(unittest.TestCase):
    def test_reproposing_a_rejected_diff_is_refused_naming_the_prior_seq(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    proposal_seq, _ = _propose(project, "agent-proposer", "VALUE = 3\n", tmp_dir)
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    diff_path = _diff_file(tmp_dir, "VALUE = 3\n")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code, payload = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path),
                        )
                    self.assertEqual(code, 2, payload)
                    rejected_records = [
                        r for r in archive.read_events(verify=False)
                        if r["kind"] == "skill_impact" and r["data"]["outcome"] == "rejected"
                    ]
                    self.assertEqual(len(rejected_records), 1)
                    prior_seq = rejected_records[0]["sequence"]

                    # Re-proposing the SAME diff content (same bytes -> same
                    # diff_hash) is refused at propose time, naming the
                    # earlier rejected skill_impact's own sequence.
                    code2, payload2 = _propose_skill_change(
                        project, "agent-proposer", "VALUE = 3\n", tmp_dir)
                self.assertEqual(code2, 2, payload2)
                self.assertIn(f"seq:{prior_seq}", payload2["message"])
                self.assertIn("already", payload2["message"].lower())


class SkillForgeImpactTests(unittest.TestCase):
    def test_forge_writes_accepted_skill_impact(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            cites = _success_cites(archive)
            code, payload = _run(
                project, "skill", "forge",
                "--name", "widget-calibrator",
                "--purpose", "Calibrate the demo widget subsystem before shipping it",
                "--gap-evidence", "Observed the same manual calibration step done by hand three times running",
                "--repeated-uses", "3",
                "--success-evidence", cites[0],
                "--success-evidence", cites[1],
                "--success-evidence", cites[2],
                "--positive", "calibrate the widget before shipping",
                "--positive", "run the widget calibration routine",
                "--negative", "order lunch for the team",
                "--negative", "schedule a meeting for tomorrow",
                "--assertion", "reports the calibration outcome",
            )
            self.assertEqual(code, 0, payload)
            impact = payload["skill_impact"]
            self.assertEqual(impact["outcome"], "accepted")
            self.assertEqual(impact["score_before"], 0.0)
            self.assertGreater(impact["score_after"], 0.0)
            self.assertTrue((project / "skills" / "widget-calibrator" / "SKILL.md").is_file())
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["target"], "skills/widget-calibrator")

    def test_forge_rejected_removes_directory_and_records_rejected(self) -> None:
        """The full CLI path only ever forges a skill that validates
        structurally, and a validated skill with real (non-overlapping)
        routing vocabulary almost always scores above zero end to end -
        contriving a genuine zero through vocabulary alone would obscure
        the assertion this test exists to make. `evaluate_forged_skill` is
        `cmd_skill_forge`'s own gate (called with the exact same
        arguments the console handler passes), exercised directly here
        against a real forged skill whose score is pinned via a stub
        `skill_score` - proving the remove-and-record branch without
        detouring through vocabulary engineering."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            from godmode_runtime.godmode_forge import SkillProposal, forge_skill
            proposal = SkillProposal(
                name="never-quite-right",
                purpose="A deliberately unhelpful skill kept only to test rejection",
                gap_evidence="Observed the exact same unhelpful workaround done by hand three times",
                repeated_uses=3,
                positive_triggers=("do the unhelpful thing twice", "repeat the unhelpful thing"),
                negative_triggers=("do something else entirely", "go do a different task"),
                assertions=("reports something",),
            )
            skill_dir = forge_skill(project / "skills", proposal)
            self.assertTrue(skill_dir.is_dir())
            with mock.patch.object(skillimpact, "skill_score", return_value=0.0):
                result = skillimpact.evaluate_forged_skill(archive, project, skill_dir)
            self.assertEqual(result["outcome"], "rejected")
            self.assertTrue(result["removed"])
            self.assertFalse(skill_dir.is_dir(), "a rejected forge must remove what it created")
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["outcome"], "rejected")
            self.assertEqual(records[0]["data"]["score_after"], 0.0)


class PatternCitationTests(unittest.TestCase):
    def test_ratify_skill_impact_may_cite_pattern_seqs(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # A pattern record this skill_impact cites, per NS-12a ("the
            # pattern records it cites"). `pattern`'s own kind/invariants
            # land in a sibling task (NS-12e, Task 12); the shape used here
            # is exactly what that invariant requires.
            pattern_record = archive.append("pattern", "flaky-calibration", {
                "subject": "flaky-calibration", "occurrences": [1],
                "workaround": "recalibrate twice", "class": "flaky",
            })
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    proposal_seq, _ = _propose(project, "agent-proposer", "VALUE = 2\n", tmp_dir)
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    diff_path = _diff_file(tmp_dir, "VALUE = 2\n")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code, payload = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path), "--pattern", str(pattern_record["sequence"]),
                        )
            self.assertEqual(code, 0, payload)
            self.assertEqual(
                payload["skill_impact"]["sequence"],
                [r for r in archive.read_events(verify=False)
                 if r["kind"] == "skill_impact"][0]["sequence"],
            )
            impact_record = [r for r in archive.read_events(verify=False)
                              if r["kind"] == "skill_impact"][0]
            self.assertEqual(impact_record["data"]["patterns"], [pattern_record["sequence"]])


class NonSkillTargetUnaffectedTests(unittest.TestCase):
    def test_ratify_on_a_non_skill_target_needs_no_diff_and_writes_no_impact(self) -> None:
        """A law/guard proposal (NS-4's own original surface) must ratify
        exactly as it did before this task - no --diff, no skill_impact."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    proposal_seq, _ = _propose(
                        project, "agent-proposer", "--- a\n+++ b\n", tmp_dir,
                        target="fixture.py",
                    )
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        check_path = project / "realcheck.py"
                        check_path.write_text(
                            "import sys\nfrom pathlib import Path\n"
                            "sys.exit(0 if 'VALUE = 1' in Path('fixture.py').read_text() else 1)\n",
                            encoding="utf-8",
                        )
                        code, _bond = _run(
                            project, "atlas", "law", "bond-test", "lawbond",
                            "--command", f"{sys.executable} realcheck.py",
                            "--file", "fixture.py", "--replace", "VALUE = 1", "--with", "VALUE = 2",
                        )
                        self.assertEqual(code, 0)
                        code, payload = _run(project, "atlas", "law", "ratify", str(proposal_seq))
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["verdict"], "ratified")
            self.assertNotIn("skill_impact", payload)
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class ContainedTargetTests(unittest.TestCase):
    """B4: `target` reaches `apply_skill_diff` proposer-supplied and never
    validated as a path upstream - an absolute target or one containing
    `..` must be refused outright, named with a remedy, before anything is
    read or written."""

    def test_dotdot_target_refused_with_remedy(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo/../../outside.py", diff_path,
                    )
            self.assertIn("..", str(ctx.exception))
            self.assertIn("skills/<name>", str(ctx.exception))
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )

    def test_absolute_target_refused_with_remedy(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            absolute_target = str((project / "skills" / "demo" / "state.py").resolve())
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(archive, project, absolute_target, diff_path)
            self.assertIn("absolute", str(ctx.exception))
            self.assertIn("skills/<name>", str(ctx.exception))
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class EvalHarnessTargetRefusedTests(unittest.TestCase):
    """B1: no self-graded measurement. A diff whose TARGET is one of the
    skill's own eval-harness inputs (the suite file, or a path its
    `check.command` names) is refused outright - the honest fix chosen
    here is refusal, not a frozen-snapshot re-score (see
    `apply_skill_diff`'s own docstring for why)."""

    def test_deleting_the_failing_assertion_via_the_suite_file_does_not_raise_the_score(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # the one assertion fails: before = 0.5
            eval_path = project / "skills" / "demo" / "godmode-evals.json"
            original_bytes = eval_path.read_bytes()
            # Drops the one failing behavior_assertion entirely - with no
            # executable assertions left, the neutral branch would score
            # the behaviour half 1.0, moving score_after to 1.0 without the
            # skill's own behaviour changing at all (B1's own example).
            rewritten_suite = json.dumps({
                "schema": "godmode-skill-eval-v1",
                "skill": "demo",
                "routing": {
                    "positive": ["calibrate the demo widget"],
                    "near_negative": ["order a pizza for lunch"],
                },
                "behavior_assertions": [],
            }, indent=2)
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), rewritten_suite)
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo/godmode-evals.json", diff_path,
                    )
            self.assertIn("eval-harness input", str(ctx.exception))
            self.assertEqual(eval_path.read_bytes(), original_bytes)
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )

    def test_rewriting_the_check_commands_own_probe_script_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # before = 0.5
            check_path = project / "skills" / "demo" / "check_demo.py"
            original_bytes = check_path.read_bytes()
            # A probe rewritten to always exit 0 would move score_after to
            # 1.0 without the skill's own behaviour (state.py) changing at
            # all - "an assertion's probe script can live inside the skill
            # dir and be targeted directly", per the review.
            always_pass = "import sys\nsys.exit(0)\n"
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), always_pass)
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo/check_demo.py", diff_path,
                    )
            self.assertIn("eval-harness input", str(ctx.exception))
            self.assertEqual(check_path.read_bytes(), original_bytes)
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class ExceptionSafetyTests(unittest.TestCase):
    """B2: ANY exception once the write has happened restores the pre-
    change bytes and records nothing partial - not only the `rejected`
    branch."""

    def test_exception_from_score_after_restores_bytes_and_records_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            target_path = project / "skills" / "demo" / "state.py"
            original_bytes = target_path.read_bytes()
            real_score_before = skillimpact.skill_score(project, "demo")
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                # Simulates a proposer-authored `check.command` raising a
                # non-GodmodeError mid-scoring - an unbalanced quote failing
                # `shlex.split`, or a non-numeric `expect_exit` failing
                # `int(...)` (both reachable from `godmode_evals._run_check`,
                # per the review). The first `skill_score` call (before the
                # write) succeeds normally; the SECOND (after the write)
                # raises, exactly the window B2 is about.
                with mock.patch.object(
                    skillimpact, "skill_score",
                    side_effect=[real_score_before, RuntimeError("boom")],
                ):
                    with self.assertRaises(RuntimeError):
                        skillimpact.apply_skill_diff(
                            archive, project, "skills/demo/state.py", diff_path,
                        )
            self.assertEqual(
                target_path.read_bytes(), original_bytes,
                "an exception mid-scoring must restore the pre-change bytes",
            )
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
                "an exception mid-scoring must record nothing partial",
            )

    def test_exception_from_record_impact_also_restores_bytes(self) -> None:
        """The guard covers `record_impact` too, not just `skill_score` - a
        failure out of `archive.append` (a lock, an I/O error, an invariant)
        must not leave the applied bytes on disk with no record to show for
        it. `patterns` no longer reaches that far (R3 checks it before
        anything is written), so the append itself is what raises here."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # before = 0.5
            target_path = project / "skills" / "demo" / "state.py"
            original_bytes = target_path.read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                # Passes the check: after = 1.0 > before = 0.5, so this would
                # otherwise be ACCEPTED - the exception must undo that too.
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with mock.patch.object(
                    skillimpact, "record_impact",
                    side_effect=ArchiveError("the append itself failed"),
                ):
                    with self.assertRaises(ArchiveError):
                        skillimpact.apply_skill_diff(
                            archive, project, "skills/demo/state.py", diff_path,
                        )
            self.assertEqual(target_path.read_bytes(), original_bytes)
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class RejectedDiffTargetScopingTests(unittest.TestCase):
    """Nit 1: `rejected_diff` matches on `(diff_hash, target)`, not the
    hash alone - the same diff bytes proposed against a DIFFERENT target
    must not be refused as if it were a re-proposal of the one already
    rejected."""

    def test_same_diff_bytes_against_a_different_target_is_not_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            (project / "skills" / "demo" / "sibling.py").write_text("PLACEHOLDER\n", encoding="utf-8")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    proposal_seq, _ = _propose(
                        project, "agent-proposer", "VALUE = 3\n", tmp_dir,
                        target="skills/demo/state.py",
                    )
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    diff_path = _diff_file(tmp_dir, "VALUE = 3\n")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code, payload = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path),
                        )
                    self.assertEqual(code, 2, payload)  # tie -> rejected

                    # The SAME diff bytes ("VALUE = 3\n"), proposed against a
                    # DIFFERENT target, is a different change and must not be
                    # refused as a re-proposal of the rejected one.
                    code2, payload2 = _propose_skill_change(
                        project, "agent-proposer", "VALUE = 3\n", tmp_dir,
                        target="skills/demo/sibling.py",
                    )
                self.assertEqual(code2, 0, payload2)


class RatifyGuardsAgainstReratifyingARejectedDiffTests(unittest.TestCase):
    """Nit 2: a refused ratification writes no `improvement_verdict`, so
    the proposal stays open and the SAME proposal can be re-ratified with a
    fresh bond. `apply_skill_diff` must refuse the identical diff itself,
    in defence in depth, not rely solely on `propose`'s own guard."""

    def test_reratifying_the_same_proposal_with_the_rejected_diff_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # before = 0.5
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    # "VALUE = 3\n" still fails the check: a tie, rejected.
                    proposal_seq, _ = _propose(project, "agent-proposer", "VALUE = 3\n", tmp_dir)
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    diff_path = _diff_file(tmp_dir, "VALUE = 3\n")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code, payload = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path),
                        )
                    self.assertEqual(code, 2, payload)

                    # The proposal has no verdict, so it stays open - ratify
                    # it again with the SAME diff and a fresh bond.
                    session_id2 = _open_checker_session(project, archive, "agent-checker-2")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker-2",
                                                       "GODMODE_SESSION": session_id2}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code2, payload2 = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path),
                        )
                self.assertEqual(code2, 2, payload2)
                self.assertIn("already", payload2["message"].lower())
                rejected_records = [
                    r for r in archive.read_events(verify=False)
                    if r["kind"] == "skill_impact" and r["data"]["outcome"] == "rejected"
                ]
                # Still exactly one rejected record - the second attempt was
                # refused before it could re-apply, re-score, and append a
                # second rejected record for the same diff.
                self.assertEqual(len(rejected_records), 1)


class ForgeOwnGuardTests(unittest.TestCase):
    """Nit 3: `evaluate_forged_skill` takes any `skill_dir` and deletes it
    unconditionally on rejection - it must refuse to touch a target that
    already has an accepted history of its own, rather than trusting call
    ordering (`forge_skill` refusing an existing directory) as the only
    safety."""

    def test_refuses_a_target_with_prior_accepted_history_without_deleting_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            target = "skills/widget-calibrator"
            archive.append("skill_impact", target, {
                "target": target, "diff_hash": "a" * 64,
                "score_before": 0.0, "score_after": 0.7,
                "outcome": "accepted", "patterns": [],
            })
            skill_dir = project / "skills" / "widget-calibrator"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: widget-calibrator\n---\n", encoding="utf-8")
            with self.assertRaises(ArchiveError) as ctx:
                skillimpact.evaluate_forged_skill(archive, project, skill_dir)
            self.assertIn("accepted", str(ctx.exception))
            self.assertTrue(skill_dir.is_dir(), "the guard must refuse before any rmtree")
            records = [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"]
            self.assertEqual(len(records), 1, "no second record for the refused call")



class CreatedEvalSuiteRefusedTests(unittest.TestCase):
    """R1: the eval-input protection covers CREATION, not only editing.

    Round 1 protected a skill's `godmode-evals.json` only when one was
    already on disk. A proposal naming a suite that does NOT exist yet was
    therefore written by this gate - and then graded by it, because
    `load_suites` globs `skills/*/godmode-evals.json` and the fabricated
    file is exactly that. Two positives sharing a coined token route home
    under the leave-one-out corpus (routing 1.0) and an empty
    `behavior_assertions` list takes the neutral branch (1.0), so the
    invented yardstick scores 1.0 for a skill with no SKILL.md at all.
    """

    _FABRICATED = json.dumps({
        "schema": "godmode-skill-eval-v1",
        "skill": "ghost",
        "routing": {
            "positive": ["zorbulate the frobnicator",
                         "zorbulate a frobnicator quickly"],
            "near_negative": [],
        },
        "behavior_assertions": [],
    }, indent=2)

    def test_writing_a_skills_own_new_eval_suite_is_refused(self) -> None:
        from godmode_runtime.godmode_evals import load_suites

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            ghost_dir = project / "skills" / "ghost"
            self.assertFalse(ghost_dir.exists())
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), self._FABRICATED)
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/ghost/godmode-evals.json", diff_path,
                    )
            self.assertIn("eval-harness input", str(ctx.exception))
            self.assertFalse(
                ghost_dir.exists(),
                "a refused proposal must not create the skill directory",
            )
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
                "a refused proposal records nothing",
            )
            # Second-order: the same file would have joined the SHARED
            # routing corpus every other skill is scored against. Refusing
            # it keeps that corpus to the suites that were already there.
            self.assertEqual(sorted(load_suites(project)), ["demo"])

    def test_the_existing_suite_is_still_refused(self) -> None:
        """The creation case is the new half; the editing case round 1
        closed must stay closed by the same unconditional path."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            suite = project / "skills" / "demo" / "godmode-evals.json"
            before = suite.read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), self._FABRICATED)
                with self.assertRaises(ArchiveError):
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo/godmode-evals.json", diff_path,
                    )
            self.assertEqual(suite.read_bytes(), before)


class CanonicalTargetKeyTests(unittest.TestCase):
    """R2: both NS-12 rules key on the CANONICAL target, the same one the
    write resolves - otherwise four spellings of one file carry four keys,
    a rejection is laundered by a keystroke, and the best-so-far floor is
    erased by the same keystroke."""

    # A case respelling names the same file only where the filesystem folds
    # case; canonical_skill_target folds Windows case and, correctly, not
    # Linux case, where STATE.PY and state.py are two files (first CI run of
    # this test on Linux, 2026-09-23).
    _RESPELLINGS = (
        "skills\\demo\\state.py",
        "./skills/demo/state.py",
        "skills/./demo/state.py",
    ) + (("skills/demo/STATE.PY",) if os.name == "nt" else ())

    def test_a_respelled_target_cannot_launder_a_rejection(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # before = 0.5
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                with _clean_env():
                    # "VALUE = 9\n" still fails the check: a tie, rejected.
                    proposal_seq, _ = _propose(project, "agent-proposer", "VALUE = 9\n", tmp_dir)
                    session_id = _open_checker_session(project, archive, "agent-checker")
                    diff_path = _diff_file(tmp_dir, "VALUE = 9\n")
                    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-checker",
                                                       "GODMODE_SESSION": session_id}):
                        code, _bond = _bond_test_on_state(project)
                        self.assertEqual(code, 0)
                        code, payload = _run(
                            project, "atlas", "law", "ratify", str(proposal_seq),
                            "--diff", str(diff_path),
                        )
                    self.assertEqual(code, 2, payload)

                    for spelling in self._RESPELLINGS:
                        with self.subTest(spelling=spelling):
                            code2, payload2 = _propose_skill_change(
                                project, "agent-proposer", "VALUE = 9\n", tmp_dir,
                                target=spelling,
                            )
                            self.assertEqual(code2, 2, payload2)
                            self.assertIn("already", payload2["message"].lower())
                            # The refusal names the file, not the spelling.
                            self.assertIn("skills/demo/state.py", payload2["message"])

    def test_a_respelled_target_still_sees_the_recorded_ceiling(self) -> None:
        """The same key change fixes the NS-12d side: after an accept, a
        respelled target used to report no recorded best, which collapsed
        `max(best_so_far, score_before)` back to the live score alone and
        re-opened the ratchet whenever the live score had drifted below the
        ceiling. Here the ceiling (1.0) is above the live score (0.5), so a
        change that reaches exactly 1.0 is a TIE against the ceiling and
        must be rejected - not an improvement over the live score."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")  # live score = 0.5
            archive.append("skill_impact", "skills/demo/state.py", {
                "target": "skills/demo/state.py", "diff_hash": "b" * 64,
                "score_before": 0.5, "score_after": 1.0,
                "outcome": "accepted", "patterns": [],
            })
            target_path = project / "skills" / "demo" / "state.py"
            original_bytes = target_path.read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                # "VALUE = 2\n" passes the check: score_after = 1.0.
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                result = skillimpact.apply_skill_diff(
                    archive, project, "skills\\demo\\state.py", diff_path,
                )
            self.assertEqual(result["best_recorded"], 1.0)
            self.assertEqual(result["score_after"], 1.0)
            self.assertEqual(result["outcome"], "rejected")
            self.assertEqual(result["target"], "skills/demo/state.py",
                             "the record keys on the canonical target")
            self.assertEqual(target_path.read_bytes(), original_bytes)


class ForgePatternRollbackTests(unittest.TestCase):
    """R3: the second record-writer needs the same write-then-restore
    guarantee the first one has. A proposer-supplied `--pattern` value that
    fails validation after the outcome is decided used to leave the forged
    skill on disk with no skill_impact and no decision record - NS-12a's
    "every skill proposal records target, diff, scores and outcome" evaded
    through a documented flag."""

    _FORGE_ARGS = (
        "--name", "widget-calibrator",
        "--purpose", "Calibrate the demo widget subsystem before shipping it",
        "--gap-evidence", "Observed the same manual calibration step done by hand three times running",
        "--repeated-uses", "3",
        "--positive", "calibrate the widget before shipping",
        "--positive", "run the widget calibration routine",
        "--negative", "order lunch for the team",
        "--negative", "schedule a meeting for tomorrow",
        "--assertion", "reports the calibration outcome",
    )

    def test_forge_with_pattern_zero_leaves_nothing_on_disk(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            cites = _success_cites(archive)
            code, payload = _run(
                project, "skill", "forge", *self._FORGE_ARGS,
                "--success-evidence", cites[0],
                "--success-evidence", cites[1],
                "--success-evidence", cites[2],
                # argparse's `type=int` takes 0 happily; only the record's
                # own invariant refuses it, and that runs far too late.
                "--pattern", "0",
            )
            self.assertEqual(code, 2, payload)
            self.assertIn("--pattern", payload["message"])
            self.assertFalse(
                (project / "skills" / "widget-calibrator").exists(),
                "a refused --pattern must not leave a forged skill on disk",
            )
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )
            self.assertEqual(
                [r for r in archive.read_events(verify=False)
                 if r["kind"] == "decision" and str(r.get("subject", "")).startswith("skill-created:")],
                [],
            )

    def test_a_raise_after_the_outcome_removes_the_forged_directory(self) -> None:
        """The general guarantee, not just the one flag: anything raising
        once `evaluate_forged_skill` has decided the outcome undoes the
        forge rather than leaving it unrecorded."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            from godmode_runtime.godmode_forge import SkillProposal, forge_skill
            proposal = SkillProposal(
                name="widget-calibrator",
                purpose="Calibrate the demo widget subsystem before shipping it",
                gap_evidence="Observed the same manual calibration step done by hand three times",
                repeated_uses=3,
                positive_triggers=("calibrate the widget before shipping",
                                   "run the widget calibration routine"),
                negative_triggers=("order lunch for the team",
                                   "schedule a meeting for tomorrow"),
                assertions=("reports the calibration outcome",),
            )
            skill_dir = forge_skill(project / "skills", proposal)
            self.assertTrue(skill_dir.is_dir())
            with mock.patch.object(
                skillimpact, "record_impact",
                side_effect=ArchiveError("the append itself failed"),
            ):
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.evaluate_forged_skill(archive, project, skill_dir)
            self.assertIn("removed", str(ctx.exception))
            self.assertFalse(
                skill_dir.exists(),
                "a forge that could not be recorded must not stay on disk",
            )
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class RejectedNewFileLeavesNoDirectoryTests(unittest.TestCase):
    """N1: `mkdir(parents=True)` can create a whole tree for a new-file
    target, and the restore only removed the file. A rejected proposal then
    left an empty directory behind - and because `forge_skill` refuses
    outright when the directory already exists, that permanently denied
    `skill forge <that name>`."""

    def test_a_rejected_new_file_target_removes_the_directories_it_created(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            created = project / "skills" / "brandnew"
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "---\nname: brandnew\n---\n")
                result = skillimpact.apply_skill_diff(
                    archive, project, "skills/brandnew/SKILL.md", diff_path,
                )
            self.assertEqual(result["outcome"], "rejected")
            self.assertFalse(
                created.exists(),
                "a rejected new-file target must not leave its directory behind",
            )

    def test_a_directory_it_did_not_create_is_left_alone(self) -> None:
        """The undo is scoped to what THIS call created - a pre-existing
        skill directory with other files in it is never removed."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "SOMETHING = 1\n")
                result = skillimpact.apply_skill_diff(
                    archive, project, "skills/demo/sibling.py", diff_path,
                )
            self.assertEqual(result["outcome"], "rejected")
            self.assertTrue((project / "skills" / "demo" / "SKILL.md").is_file())
            self.assertFalse((project / "skills" / "demo" / "sibling.py").exists())


class DirectoryTargetRefusedTests(unittest.TestCase):
    """N2: a directory target made `pre_bytes` None, raised out of
    `write_bytes`, and then raised a SECOND time out of the restore's own
    `unlink` - so the operator was shown the handler's error, not the real
    one."""

    def test_a_directory_target_is_refused_with_its_own_message(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo", diff_path,
                    )
            self.assertIn("directory", str(ctx.exception))
            self.assertTrue((project / "skills" / "demo").is_dir())
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class FailedRestoreIsNamedTests(unittest.TestCase):
    """N3: the restore can itself fail (a read-only file, a full disk, a
    lock). Letting that exception replace the original told the operator
    the wrong story about a file now sitting in the PROPOSED state with no
    record of it."""

    def test_a_failed_restore_says_the_file_is_in_the_proposed_state(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            real_score_before = skillimpact.skill_score(project, "demo")
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with mock.patch.object(
                    skillimpact, "skill_score",
                    side_effect=[real_score_before, RuntimeError("boom")],
                ), mock.patch.object(
                    skillimpact, "_restore",
                    side_effect=OSError("the file is locked"),
                ):
                    with self.assertRaises(ArchiveError) as ctx:
                        skillimpact.apply_skill_diff(
                            archive, project, "skills/demo/state.py", diff_path,
                        )
            message = str(ctx.exception)
            self.assertIn("PROPOSED state", message)
            self.assertIn("locked", message, "the failed restore is named")
            self.assertIn("boom", message, "so is the original failure")
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class ProtectedInputsArePrefixScopedTests(unittest.TestCase):
    """N5: a `check.command` argv token can name a DIRECTORY - the shipped
    skill-forge suite runs `skill validate --path skills/<name>`, so every
    file beneath that directory is a grading input. Exact-path membership
    protected only the directory's own name."""

    def test_a_file_under_a_protected_directory_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write_demo_skill(project, initial_value="1")
            suite = project / "skills" / "demo" / "godmode-evals.json"
            block = json.loads(suite.read_text(encoding="utf-8"))
            block["behavior_assertions"] = [{
                "assert": "the skill still validates",
                "check": {"command": "python scripts/godmode.py skill validate --path skills/demo"},
            }]
            suite.write_text(json.dumps(block, indent=2), encoding="utf-8")
            target_path = project / "skills" / "demo" / "state.py"
            original_bytes = target_path.read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                diff_path = _diff_file(Path(tmp), "VALUE = 2\n")
                with self.assertRaises(ArchiveError) as ctx:
                    skillimpact.apply_skill_diff(
                        archive, project, "skills/demo/state.py", diff_path,
                    )
            self.assertIn("eval-harness input", str(ctx.exception))
            self.assertEqual(target_path.read_bytes(), original_bytes)
            self.assertEqual(
                [r for r in archive.read_events(verify=False) if r["kind"] == "skill_impact"], [],
            )


class ForgeOwnGuardMatchesSkillNameTests(unittest.TestCase):
    """N9: an established skill's accepted history is keyed
    `skills/<name>/<file>` (what `atlas law ratify` writes), not
    `skills/<name>` (what a prior forge writes). Matching the exact string
    guarded only the second, so a direct call against a ratified skill
    would still `rmtree` it."""

    def test_accepted_history_from_ratify_still_guards_the_directory(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("skill_impact", "skills/widget-calibrator/SKILL.md", {
                "target": "skills/widget-calibrator/SKILL.md", "diff_hash": "c" * 64,
                "score_before": 0.5, "score_after": 0.7,
                "outcome": "accepted", "patterns": [],
            })
            skill_dir = project / "skills" / "widget-calibrator"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: widget-calibrator\n---\n", encoding="utf-8")
            with self.assertRaises(ArchiveError) as ctx:
                skillimpact.evaluate_forged_skill(archive, project, skill_dir)
            self.assertIn("accepted", str(ctx.exception))
            self.assertTrue(skill_dir.is_dir(), "the guard must refuse before any rmtree")
            self.assertTrue((skill_dir / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()

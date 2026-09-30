"""Console and law bundle: typed exit codes, `--data`, request closures that
name their delivery, proposal withdrawal, one trust rule, a reviewer's own
falsifier, verifier diversity across sessions, dormant laws on moved
evidence, and ratifiable documents under a directory-validated suite."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_bonds, godmode_errors, godmode_law, godmode_lessons  # noqa: E402
from godmode_runtime.godmode_chronicle import latest_by_subject  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_skillimpact import _is_protected  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

_HOST_ENV = None


def setUpModule() -> None:
    """Console subprocesses below spread `os.environ`; a runner's own `CI`
    or host marker must not flip their row."""
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "godmode.py"), "--project", str(project), *argv, "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    text = (done.stdout or "").strip() or (done.stderr or "").strip()
    try:
        return done.returncode, json.loads(text.splitlines()[-1]) if text else {}
    except json.JSONDecodeError:
        return done.returncode, {"raw": text}


class ExitCodeTests(unittest.TestCase):
    def test_each_error_class_has_its_own_code_and_the_default_stays_two(self) -> None:
        self.assertEqual(godmode_errors.ArchiveError.exit_code, 2)
        self.assertEqual(godmode_errors.UsageError.exit_code, 2)
        self.assertEqual({godmode_errors.PrivacyError.exit_code, godmode_errors.AuthorizationError.exit_code,
                          godmode_errors.IdentityError.exit_code, godmode_errors.ForgeError.exit_code,
                          godmode_errors.CorpusError.exit_code}, {3, 4, 5, 6, 7})

    def test_an_authorization_refusal_exits_four(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(project, "authorize", "stage", "--operation", "git commit --amend",
                                 "--password-stdin")
            self.assertEqual(code, 4, payload)


class RememberTests(unittest.TestCase):
    def test_data_is_an_alias_for_value(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(project, "remember", "--kind", "decision", "--subject", "db",
                                 "--data", "postgres")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["data"]["value"], "postgres")

    def test_a_request_closure_without_a_delivery_is_answered_not_closed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(project, "remember", "--kind", "request", "--subject", "ask:abc",
                                 "--value", "please add the flag")
            self.assertEqual(code, 0, payload)
            code, payload = _run(project, "remember", "--kind", "request", "--subject", "ask:abc",
                                 "--status", "closed")
            self.assertEqual(code, 0, payload)
            newest = archive.select(kind="request", subject="ask:abc", limit=5)[-1]
            self.assertEqual(newest["data"]["status"], "answered", payload)
            self.assertIn("no delivering commit", newest["data"]["closure"])
            code, payload = _run(project, "remember", "--kind", "request", "--subject", "ask:abc",
                                 "--status", "closed", "--evidence", "commit:0362509e")
            self.assertEqual(code, 0, payload)
            newest = archive.select(kind="request", subject="ask:abc", limit=5)[-1]
            self.assertEqual(newest["data"]["status"], "closed")


class WithdrawTests(unittest.TestCase):
    def test_the_proposer_withdraws_and_the_slot_is_freed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            diff = project / "change.diff"
            diff.write_text("x\n", encoding="utf-8")
            proposal = godmode_bonds.propose(archive, "docs/law.md", diff, ["seq:1"], project)
            self.assertEqual(godmode_bonds.proposals_this_sprint(archive), 1)
            outcome = godmode_bonds.withdraw(archive, proposal["sequence"], "superseded by a better diff")
            self.assertEqual(outcome["verdict"], "withdrawn")
            self.assertEqual(godmode_bonds.proposals_this_sprint(archive), 0)
            with self.assertRaises(ArchiveError):
                godmode_bonds.withdraw(archive, proposal["sequence"], "twice")
            with self.assertRaises(ArchiveError):
                godmode_bonds.withdraw(archive, proposal["sequence"] + 100, "missing")


class TrustRuleTests(unittest.TestCase):
    def test_the_default_fold_is_the_status_trust_rule(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = archive.append("obligation", "ship", {"status": "open"}, evidence=[])
            second = archive.append("obligation", "ship", {"status": "closed"}, evidence=[])
            latest = latest_by_subject([first, second])
            self.assertEqual(latest["ship"]["sequence"], second["sequence"])
            # An operator record contradicting a later agent record persists.
            with mock.patch("godmode_runtime.godmode_chronicle.record_trust",
                            side_effect=lambda r: 3 if r["sequence"] == first["sequence"] else 1):
                latest = latest_by_subject([first, second])
            self.assertEqual(latest["ship"]["sequence"], first["sequence"])


class FalsifierTests(unittest.TestCase):
    def test_a_promotion_needs_the_reviewers_own_falsifier(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for text in ("", "the same correction recurs again after this guard is delivered"):
                with self.assertRaises(ArchiveError) as ctx:
                    godmode_law.promote_candidate(archive, 1, guard="g", subject="s", refuted_by=text)
                self.assertIn("refuted-by", str(ctx.exception))

    def test_a_dangling_citation_is_refused_at_promotion(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            lesson = archive.append("lesson", "l", {
                "status": "candidate", "value": "v", "root_cause": "r", "correction": "c",
                "reflection": "f", "generalized_guard": "g", "refuted_by": "x"}, evidence=[])
            with self.assertRaises(ArchiveError) as ctx:
                godmode_lessons.promote(archive, lesson["sequence"], ["seq:999999"], "a" * 64)
            self.assertIn("seq:999999", str(ctx.exception))


class DormantEvidenceTests(unittest.TestCase):
    def test_a_law_citing_a_missing_record_is_withheld_and_named(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.object(archive, "find_by_sequence",
                                   side_effect=lambda seq: None if seq == 424242 else {"sequence": seq,
                                                                                  "evidence": ["seq:424242"] if seq == 7 else [],
                                                                                  "data": {}}):
                self.assertEqual(godmode_law._moved_evidence(archive, 7), ["seq:424242"])
                self.assertEqual(godmode_law._moved_evidence(archive, 8), [])


class DirectorySuiteTests(unittest.TestCase):
    def test_documents_under_a_validated_directory_are_ratifiable_and_graders_are_not(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            skill = project / "skills" / "demo"
            (skill / "scripts").mkdir(parents=True)
            (skill / "SKILL.md").write_text("x", encoding="utf-8")
            (skill / "scripts" / "probe.py").write_text("x", encoding="utf-8")
            (skill / "godmode-evals.json").write_text("{}", encoding="utf-8")
            protected = {skill}
            self.assertFalse(_is_protected(skill / "SKILL.md", protected))
            self.assertFalse(_is_protected(skill / "reference.md", protected))
            self.assertTrue(_is_protected(skill / "godmode-evals.json", protected))
            self.assertTrue(_is_protected(skill / "scripts" / "probe.py", protected))
            self.assertTrue(_is_protected(skill / "check.sh", protected))
            self.assertTrue(_is_protected(skill, protected))


if __name__ == "__main__":
    unittest.main()

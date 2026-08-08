"""Finishing a task is what records the claim.

`claim` downgrades an assertion whose citations do not resolve, and it is the
first thing the README demonstrates. Across this project's entire archive it has
been used zero times, alongside zero attestations — so `evidence_density`
reports "0 citations across 0 claims" and the front page shows a feature the
author's own agent never invoked.

The mechanism was never the problem. Invocation was: `claim` is a command
somebody has to decide to run, and an agent finishing a task is reaching for
the finish, not for a subsystem.

So the completion report records the claim. Reporting "this is done" *is* an
assertion about project state, and it now goes through the same grading as any
other: cited and resolving, or stored as a hypothesis. Nothing new is asked of
the agent, and the honest outcome is the common one — most completion claims
carry no resolving citation, and are recorded as hypotheses rather than facts.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_report import claims_from_report  # noqa: E402


def _report(status: str = "verified", evidence: list[str] | None = None) -> dict:
    return {
        "report": "task-completion",
        "session": "S-test",
        "fields": {
            "status": {"value": status, "label": "observed", "detail": None},
            "what_changed": {"value": "3 files changed", "label": "observed",
                             "detail": ["scripts/a.py", "tests/test_a.py"]},
            "evidence": {"value": "cited", "label": "observed",
                         "detail": evidence if evidence is not None else []},
            "git_state": {"value": "branch main at abc123", "label": "observed",
                          "detail": {"branch": "main"}},
        },
    }


class BindingTests(unittest.TestCase):
    def test_a_completion_report_yields_a_claim(self) -> None:
        claims = claims_from_report(_report())
        self.assertTrue(claims, "finishing a task recorded no assertion at all")
        self.assertIn("status", claims[0]["text"].lower() + claims[0]["field"])

    def test_the_claim_carries_the_report_s_own_evidence(self) -> None:
        claims = claims_from_report(_report(evidence=["file:scripts/a.py", "cmd:pytest"]))
        cites = [c for claim in claims for c in claim["cites"]]
        self.assertIn("file:scripts/a.py", cites)

    def test_a_report_with_no_evidence_still_produces_a_claim(self) -> None:
        """Which the grader will downgrade. Recording nothing would let an
        uncited completion escape the grading entirely — the opposite of the
        point."""
        claims = claims_from_report(_report(evidence=[]))
        self.assertTrue(claims)
        self.assertEqual(claims[0]["cites"], [])

    def test_a_blocked_report_is_not_a_completion_claim(self) -> None:
        """Claiming to be blocked asserts nothing about the work being done."""
        self.assertEqual(claims_from_report(_report(status="blocked")), [])


class RestraintTests(unittest.TestCase):
    def test_only_stated_fields_become_claims(self) -> None:
        """A field the runtime observed rather than the agent asserted is not
        the agent's claim to make, so it does not become one."""
        report = _report()
        report["fields"]["git_state"]["label"] = "observed"
        texts = " ".join(c["text"] for c in claims_from_report(report))
        self.assertNotIn("branch main at abc123", texts)

    def test_the_claim_text_names_the_task_not_the_machinery(self) -> None:
        claim = claims_from_report(_report())[0]
        self.assertNotIn("field", claim["text"].lower())
        self.assertTrue(len(claim["text"]) > 10)

    def test_an_empty_report_produces_nothing(self) -> None:
        self.assertEqual(claims_from_report({"fields": {}}), [])


if __name__ == "__main__":
    unittest.main()

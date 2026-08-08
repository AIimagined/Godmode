"""Ground rules about evidence, made enforceable.

A live project's mistake ledger records the same failure in every variant: the
nearest available evidence accepted as sufficient. A salient anomaly instead of
a differential. A search miss read as absence. The code read as the design. A
keyword filter built from the hypothesis, which cannot surprise the person who
wrote it. Its own summary is the finding — *"the failure was not in the fix but
in what I would have accepted as sufficient evidence"*.

Those rules were written down, and written down again, and still not followed.
Its ledger names that too: *"the rule existed; the habit didn't"*.

Two things are needed for a rule like that to hold, and this file asserts both.

**The charter must grade it HARD.** Fed five real troubleshooting ground rules,
the compiler graded four ADVISORY, because they matched no known shape and the
fallback is advisory. An advisory rule blocks nothing, so the gate that exists
would have passed a session that broke all four.

**A root cause must cite what confirmed it.** A rule an agent must remember is
a rule an agent in a hurry skips. What survives is a claim that cannot be
recorded as verified without its evidence — so a root cause with no differential
behind it is stored as a hypothesis, whatever the author believed.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_charter import ADVISORY, HARD, compile_charter  # noqa: E402
from godmode_runtime.godmode_attest import looks_like_root_cause  # noqa: E402

# Copied verbatim in substance from a live project's ground rules.
GROUND_RULES = (
    "Never design a remedy on a root cause the differential has not confirmed.",
    "Always diff the before and after artefacts before reading a single log line.",
    "Never conclude absence from a search miss; prove it a second, different way.",
    "Always read every tracking surface by category first, never by keyword.",
    "Never answer why the product behaves this way from the code alone.",
    "Never state a cause you have not observed; make the cheapest observation first.",
)


def _charter(*rules: str) -> dict:
    holder = tempfile.TemporaryDirectory(prefix="godmode-rules-")
    root = Path(holder.name)
    body = "# Rules\n\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"
    (root / "GODMODE.md").write_text(body, encoding="utf-8")
    with holder:
        return compile_charter(root)


class CharterGradingTests(unittest.TestCase):
    def test_evidence_ground_rules_are_hard_not_advisory(self) -> None:
        charter = _charter(*GROUND_RULES)
        advisory = [r["text"] for r in charter["compiled"] if r["enforcement"] == ADVISORY]
        self.assertEqual(
            advisory, [],
            "a rule about what counts as evidence was graded advisory, so it "
            f"blocks nothing: {advisory}")

    def test_each_rule_gets_a_checkable_kind(self) -> None:
        """`none` means nothing can ever satisfy it, which is an advisory rule
        wearing a stricter label."""
        for rule in _charter(*GROUND_RULES)["compiled"]:
            self.assertNotEqual(rule["verify"], "none", rule["text"])

    def test_an_ordinary_preference_is_still_advisory(self) -> None:
        """Widening the shapes must not make every sentence blocking; a rule
        that blocks everything is switched off within a day."""
        charter = _charter("Prefer short function names where it reads better.",
                           "We like tabs over spaces in generated output.")
        self.assertEqual(charter["enforcement"][HARD], 0, charter["compiled"])


class RootCauseDetectionTests(unittest.TestCase):
    def test_a_root_cause_assertion_is_recognised(self) -> None:
        for text in ("the root cause is a stale cache entry",
                     "the blank video was caused by the injected opacity hide",
                     "this happens because the pointer capture eats the click",
                     "the reason the chain collapsed is a suspended account"):
            self.assertTrue(looks_like_root_cause(text)[0], text)

    def test_an_observation_is_not_a_root_cause(self) -> None:
        for text in ("the suite passes at this commit",
                     "the archive holds 54 records",
                     "the gate refused a force push"):
            self.assertFalse(looks_like_root_cause(text)[0], text)


class RootCauseGradingTests(unittest.TestCase):
    """The rule that survives an agent in a hurry."""

    def _record(self, text: str, cites: list[str]) -> dict:
        """Records the run behind a `cmd:` citation first.

        A command citation resolves only when an attestation records having run
        it — anyone can write the words, and only a run leaves the record. That
        contract already existed and is the right one, so this exercises the
        real workflow rather than a shortcut around it.
        """
        from godmode_runtime.godmode_attest import record_claim, record_step
        from test_godmode_runtime import isolated_project

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            for citation in cites:
                if str(citation).startswith("cmd:"):
                    record_step(archive, "s1", "differential", "ran",
                                result="compared", evidence=[citation])
            return record_claim(archive, project, "s1", text, "verified", cites=cites)

    def test_a_root_cause_without_a_differential_is_a_hypothesis(self) -> None:
        record = self._record(
            "the root cause is the injected opacity hide", ["file:notes.txt"])
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("differential", record["data"]["reason"])

    def test_a_root_cause_that_cites_what_confirmed_it_stands(self) -> None:
        record = self._record(
            "the root cause is the injected opacity hide",
            ["file:notes.txt", "cmd:diff before.html after.html"])
        self.assertEqual(record["data"]["grade"], "verified")

    def test_an_ordinary_claim_needs_no_differential(self) -> None:
        record = self._record("the notes file exists", ["file:notes.txt"])
        self.assertEqual(record["data"]["grade"], "verified")

    def test_the_reason_names_the_missing_step(self) -> None:
        """A refusal that does not say what would satisfy it teaches nothing."""
        record = self._record("this failed because the cache was stale", [])
        self.assertIn("cmd:", record["data"]["reason"])


if __name__ == "__main__":
    unittest.main()

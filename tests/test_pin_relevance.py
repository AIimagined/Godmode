"""A pin caps a claim only when it names the same surface the claim cites.

Two grades were capped in one session: one by a relevant pin (install
cache provenance, claim about the install cache) and one by an unrelated
pin (a charter-compiler line rule, claim about a git ref) that merely
shared three common words. Relevance is a shared cited path or command
stem, not vocabulary.

Fix round 1: the first cut of the stem tokenizer still treated every
generic word in a `cmd:` citation as a stem (`python`, `tests`, `main`,
`git`...), so realistic citation/lesson pairs that share nothing but a
command name or a branch name still capped. `_citation_stems` is now
kind-aware (a `file:` citation keeps only its basename and immediate
parent directory; a `cmd:` citation keeps its command name plus later
structural tokens, kept whole) and a fixed stop-set drops the tokens
that never identify a particular surface.

Citations are `cmd:` only in most cases here (no `file:` citation) so
the tests-directory pin path never engages - only the lesson-vocabulary
path is exercised. Each test uses its own temp directory as `project`
so the real repository's own `tests/` directory can never interfere.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_sources  # noqa: E402
from godmode_runtime.godmode_attest import open_session, record_claim  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class FakeArchive:
    def __init__(self, lessons):
        self._lessons = lessons

    def select(self, kind, limit=200):
        assert kind == "lesson"
        return list(self._lessons)


def lesson(seq, subject, guard):
    return {"kind": "lesson", "sequence": seq, "subject": subject,
            "data": {"status": "active", "generalized_guard": guard}}


class PinRelevanceTests(unittest.TestCase):
    def _pin(self, archive, text, citations):
        with tempfile.TemporaryDirectory() as tmp:
            return godmode_sources.guard_pin_reason(
                Path(tmp), archive, text, citations)

    def test_related_pin_caps(self) -> None:
        """The claim cites the same command stem the lesson's guard names."""
        archive = FakeArchive([lesson(
            7, "installed cache was built from the cut",
            "the version bump must be the final commit before the tag; "
            "verified by check_cache.sh before any claim")])
        out = self._pin(
            archive,
            "origin/main is 1d51f87 and the installed cache carries the "
            "post-bump fix",
            ["cmd:sh check_cache.sh"])
        self.assertTrue(out.startswith("a pin already names this surface"))

    def test_unrelated_pin_only_advises(self) -> None:
        """The claim shares five vocabulary words with the lesson but cites
        a command naming none of the lesson's stems - not a cap, only the
        vocabulary-only advisory."""
        archive = FakeArchive([lesson(
            3, "the charter compiler enforces one physical rule per line",
            "a physical rule that spans multiple lines is split by the "
            "compiler statement enforcement")])
        out = self._pin(
            archive,
            "the physical compiler enforcement caught a charter statement "
            "failure",
            ["cmd:git rev-parse origin/main"])
        self.assertTrue(out.startswith(godmode_sources.PIN_ADVISORY_PREFIX))
        self.assertNotIn("a pin already names this surface", out)

    def test_a_cited_test_runner_and_module_do_not_cap_a_tests_mention(self) -> None:
        """Reviewer false positive #1: `python`/`tests` are generic command
        vocabulary, not a surface - a lesson merely mentioning "tests" must
        not cap just because the citation also contains that word."""
        archive = FakeArchive([lesson(
            11, "flaky tests were traced to shared fixture state",
            "tests that share fixture state must not run in the same "
            "process; isolate fixtures per test")])
        out = self._pin(
            archive,
            "the suite now passes because the flaky tests were fixed",
            ["cmd:python -m unittest tests.test_pin_relevance"])
        self.assertNotIn("a pin already names this surface", out)

    def test_a_cited_git_ref_does_not_cap_a_main_mention(self) -> None:
        """Reviewer false positive #2: `origin/main` is a branch reference,
        not a surface named by a lesson whose guard happens to say
        "main"."""
        archive = FakeArchive([lesson(
            12, "the release branch merges only through review",
            "main only advances by a reviewed merge commit, never a "
            "direct push")])
        out = self._pin(
            archive,
            "origin/main is 805df90 and contains the release commit",
            ["cmd:git rev-parse origin/main"])
        self.assertNotIn("a pin already names this surface", out)

    def test_a_cited_git_status_does_not_cap_a_git_mention(self) -> None:
        """Reviewer false positive #3: `git` is the command name, not a
        surface - a lesson mentioning "git" in passing must not cap."""
        archive = FakeArchive([lesson(
            13, "an operator asked why git leaves so many stray files",
            "a pre-commit hook blocks any stray file git would otherwise "
            "leave behind")])
        out = self._pin(
            archive,
            "the working tree is clean per git status --short",
            ["cmd:git status --short"])
        self.assertNotIn("a pin already names this surface", out)

    def test_a_cited_file_stem_caps_a_lesson_naming_it(self) -> None:
        """A `file:` citation's basename is still a real surface - unlike
        the generic command vocabulary above, this must keep capping."""
        archive = FakeArchive([lesson(
            14, "godmode_sentinel enforces the risk-tier gate",
            "godmode_sentinel classifies every action before it runs; "
            "the gate is the enforcement point")])
        out = self._pin(
            archive,
            "there is no risk-tier check anywhere in godmode_sentinel",
            ["file:scripts/godmode_runtime/godmode_sentinel.py"])
        self.assertTrue(out.startswith("a pin already names this surface"))


class RecordClaimAdvisoryContractTests(unittest.TestCase):
    """The cross-module contract: an advisory-prefixed pin_reason must
    never downgrade a claim, and must be readable back from the record."""

    def test_advisory_pin_does_not_downgrade_and_is_recorded(self) -> None:
        advisory_text = (
            f"{godmode_sources.PIN_ADVISORY_PREFIX} related lessons by "
            "vocabulary only (lesson seq:1 (some unrelated lesson)) - "
            "not a cap; read them if the surface is the same")
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "pin-advisory-test")
            (project / "foo.py").write_text("VALUE = 1\n", encoding="utf-8")
            with mock.patch(
                    "godmode_runtime.godmode_attest._guard_pin_reason",
                    return_value=advisory_text), \
                 mock.patch(
                    "godmode_runtime.godmode_attest._probed_twice",
                    return_value=True), \
                 mock.patch(
                    "godmode_runtime.godmode_attest._cites_a_search",
                    return_value=True):
                record = record_claim(
                    archive, project, session,
                    "There is no validation anywhere in foo.py",
                    "verified", cites=["file:foo.py"])
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertFalse(record["data"]["downgraded"])
        self.assertIn(advisory_text, record["data"]["advisories"])


if __name__ == "__main__":
    unittest.main()

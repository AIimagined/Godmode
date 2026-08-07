"""A claim about the outside world, recognised without being declared.

The runtime already refuses to record a verified claim about an external system
unless a primary source was read this session. That check only ran when the
caller passed `external=True` — so it protected the caller who remembered, and
not the one who did not know they were making an external claim at all.

The seed case: an assertion that a particular pinned action version did not
exist, stated from recall, wrong, and caught only because a human checked. No
`external` flag was passed, because the assertion did not feel like a claim
about a remote system. It was one.

Detection is deliberately narrow. It fires on the shapes that name a
third-party artefact or assert what a version supports, and it downgrades to
hypothesis with a stated reason rather than refusing — a claim recorded as a
hypothesis is recoverable by citing a source, and a claim wrongly recorded as
verified is what a later session will trust.
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

from godmode_runtime.godmode_attest import looks_external  # noqa: E402


class DetectionTests(unittest.TestCase):
    def test_the_seed_case_is_recognised(self) -> None:
        detected, why = looks_external("actions/checkout@v7 does not exist")
        self.assertTrue(detected)
        self.assertTrue(why)

    def test_a_pinned_third_party_version_is_external(self) -> None:
        for text in ("we should use actions/setup-python@v6",
                     "react@19 changed the render signature",
                     "the latest version of ripgrep is 14.1"):
            self.assertTrue(looks_external(text)[0], text)

    def test_a_support_or_release_assertion_is_external(self) -> None:
        for text in ("Python 3.13 supports free-threading",
                     "that flag was removed in Django 5.2",
                     "Node 24 is not yet released"):
            self.assertTrue(looks_external(text)[0], text)


class RestraintTests(unittest.TestCase):
    """A detector that fires on local claims teaches the operator to bypass it."""

    def test_claims_about_this_repository_are_not_external(self) -> None:
        for text in ("the sentinel classifies compound commands by their worst part",
                     "417 tests pass at this commit",
                     "the gate denied ls in a live session",
                     "scripts/godmode_runtime/godmode_trust.py reports hook commands",
                     "our own version is 0.2.2"):
            self.assertFalse(looks_external(text)[0], text)

    def test_a_bare_version_number_alone_is_not_a_claim_about_the_world(self) -> None:
        self.assertFalse(looks_external("bumped to 0.2.2")[0])
        self.assertFalse(looks_external("see line 42")[0])


class RecordingTests(unittest.TestCase):
    def test_an_undeclared_external_claim_is_downgraded(self) -> None:
        from godmode_runtime.godmode_attest import record_claim

        from test_godmode_runtime import isolated_project

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = record_claim(
                archive, project, "s1",
                "actions/checkout@v7 does not exist", "verified", cites=[])
        self.assertEqual(result["data"]["grade"], "hypothesis")
        self.assertIn("external", result["data"]["reason"])

    def test_citing_a_primary_source_keeps_it_verified(self) -> None:
        from godmode_runtime.godmode_attest import record_claim

        from test_godmode_runtime import isolated_project

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = record_claim(
                archive, project, "s1",
                "actions/checkout@v7 exists", "verified",
                cites=["url:the release page read this session"])
        self.assertEqual(result["data"]["grade"], "verified")

    def test_a_local_claim_with_a_resolving_citation_is_unaffected(self) -> None:
        from godmode_runtime.godmode_attest import record_claim

        from test_godmode_runtime import isolated_project

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "note.txt").write_text("evidence\n", encoding="utf-8")
            result = record_claim(
                archive, project, "s1",
                "the note file exists", "verified", cites=["file:note.txt"])
        self.assertEqual(result["data"]["grade"], "verified")


if __name__ == "__main__":
    unittest.main()

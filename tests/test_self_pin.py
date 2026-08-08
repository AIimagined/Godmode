"""An install snippet pinning a version of this project that no longer exists.

The README's CI example pinned `AIimagined/Godmode@v0.2.0` through seven
releases. Anyone who copied it got a build from the first week.

Nothing caught it, and the reason is worth keeping: the stale-figure check
deliberately skips fenced code blocks, because a number inside a code sample is
usually an argument rather than a claim. Every install snippet lives in a fenced
block, so the one place a reader copies verbatim was the one place no check
looked.

Unlike a count, a self-pin has an exact local answer — the running version —
which is what makes it checkable at all. `hosts` and the total command count
were both left unchecked for want of one, and a checker without an exact answer
reports true statements as stale until someone switches it off.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_constants import RUNTIME_VERSION  # noqa: E402
from godmode_runtime.godmode_docslint import (  # noqa: E402
    _self_pin_findings, lint_docs,
)


class SelfPinTests(unittest.TestCase):
    def test_a_stale_pin_is_reported(self) -> None:
        findings = _self_pin_findings(
            "README.md", "- uses: AIimagined/Godmode@v0.1.0\n", "0.2.7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "stale-self-pin")
        self.assertIn("v0.1.0", findings[0]["why"])
        self.assertIn("v0.2.7", findings[0]["why"])

    def test_a_current_pin_is_not(self) -> None:
        self.assertEqual(
            _self_pin_findings("README.md",
                               "- uses: AIimagined/Godmode@v0.2.7\n", "0.2.7"),
            [])

    def test_it_looks_inside_fenced_blocks(self) -> None:
        """The whole point: every install snippet is fenced, and the figure
        check skips fences."""
        document = "```yaml\n- uses: AIimagined/Godmode@v0.1.0\n```\n"
        self.assertTrue(_self_pin_findings("README.md", document, "0.2.7"))

    def test_release_notes_may_pin_their_own_release(self) -> None:
        """A historical document describing v0.2.4 should say v0.2.4. Reporting
        it would make the check noisy in exactly the files that must not
        change."""
        self.assertEqual(
            _self_pin_findings("docs/releases/RELEASE_NOTES_v0.2.4.md",
                               "- uses: AIimagined/Godmode@v0.2.0\n", "0.2.7"),
            [])

    def test_the_finding_names_the_remedy(self) -> None:
        finding = _self_pin_findings(
            "README.md", "AIimagined/Godmode@v0.1.0", "0.2.7")[0]
        self.assertIn("update the pin", finding["remedy"])
        self.assertIn("v0.1.0", finding["excerpt"])

    def test_this_project_currently_has_no_stale_pin(self) -> None:
        """The instance, alongside the class. A check that passes only on
        synthetic strings is the defect this project keeps finding."""
        report = lint_docs(PLUGIN_ROOT)
        stale = [f for f in report["findings"]
                 if f["check"] == "stale-self-pin"]
        self.assertEqual(stale, [], stale)

    def test_the_readme_pin_matches_the_running_version(self) -> None:
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        pins = _self_pin_findings("README.md", readme, RUNTIME_VERSION)
        self.assertEqual(pins, [], pins)


if __name__ == "__main__":
    unittest.main()

"""A README can pass every claim check and still not be a README.

The claim checks ask whether a sentence is provable. A front page that opens
with where the last session stopped, and lists the current sprint, is made of
true sentences - so it was reported `clean` while telling a stranger nothing
about how to start. These tests pin the other question: is the file doing a
README's job.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_docslint import lint_docs, readme_review  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


SESSION_README = (
    "# Bridge\n\n"
    "After a system restart, use `docs/RESTART_HANDOFF.md` to resume the work.\n\n"
    "Bridge connects one thing to another.\n\n"
    "## Current Sprint\n\n"
    "Sprint 1 creates the foundation.\n"
)

PROJECT_README = (
    "# Bridge\n\n"
    "Bridge connects one thing to another.\n\n"
    "## Quick start\n\n"
    "```bash\nnpm install\n```\n\n"
    "## Restarting the server\n\n"
    "Run `npm run server` again.\n"
)


def _project(**files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-readme-")
    for relative, content in files.items():
        target = Path(holder.name) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return holder


def _checks(findings: list[dict]) -> list[str]:
    return [finding["check"] for finding in findings]


class SessionStateTests(unittest.TestCase):
    def test_a_sprint_heading_and_a_handoff_pointer_are_both_reported(self) -> None:
        with _project(**{"README.md": SESSION_README}) as raw:
            report = lint_docs(Path(raw))
        found = [f for f in report["findings"] if f["check"] == "readme-session-state"]
        self.assertEqual(sorted(f["line"] for f in found), [3, 7], found)
        self.assertEqual(report["high_severity"], 2)

    def test_a_readme_about_the_project_is_clean(self) -> None:
        with _project(**{"README.md": PROJECT_README}) as raw:
            report = lint_docs(Path(raw))
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["repo_standards"]["readme_advisories"], [])

    def test_the_rule_reads_readmes_only(self) -> None:
        with _project(**{"README.md": PROJECT_README,
                         "docs/STATUS.md": SESSION_README}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("readme-session-state", _checks(report["findings"]))

    def test_a_fenced_example_of_a_handoff_path_is_not_a_pointer(self) -> None:
        body = PROJECT_README + "\n```\ncat docs/HANDOFF.md\n```\n"
        with _project(**{"README.md": body}) as raw:
            self.assertEqual(lint_docs(Path(raw))["findings"], [])

    def test_a_project_can_switch_the_rule_off(self) -> None:
        with _project(**{"README.md": SESSION_README, ".godmode-docslint.json":
                         json.dumps({"ignore_checks": ["readme-session-state"]})}) as raw:
            self.assertEqual(lint_docs(Path(raw))["findings"], [])


class ShapeTests(unittest.TestCase):
    def test_a_title_and_nothing_else_is_advised_never_failed(self) -> None:
        with _project(**{"README.md": "# Bridge\n\n## Notes\n\nSome notes.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertEqual(_checks(report["repo_standards"]["readme_advisories"]),
                         ["readme-no-opening", "readme-no-get-started"])
        self.assertEqual(report["verdict"], "clean")
        self.assertEqual(report["high_severity"], 0)

    def test_badges_alone_are_not_an_opening(self) -> None:
        body = "# Bridge\n\n[![ci](https://example.invalid/b.svg)](https://example.invalid)\n\n## Install\n\nx\n"
        with _project(**{"README.md": body}) as raw:
            advisories = lint_docs(Path(raw))["repo_standards"]["readme_advisories"]
        self.assertEqual(_checks(advisories), ["readme-no-opening"])

    def test_a_declared_readme_contract_replaces_the_default(self) -> None:
        with _project(**{"README.md": "# Bridge\n\n## Scope\n\nOne thing.\n",
                         ".godmode-docslint.json":
                         json.dumps({"contracts": {"README.md": ["Scope"]}})}) as raw:
            report = lint_docs(Path(raw))
        self.assertEqual(report["repo_standards"]["readme_advisories"], [])
        self.assertEqual(report["findings"], [])

    def test_the_readme_a_host_surfaces_first_is_the_one_reviewed(self) -> None:
        with _project(**{"README.md": PROJECT_README,
                         ".github/README.md": "# Bridge\n"}) as raw:
            self.assertEqual(readme_review(Path(raw))["path"], ".github/README.md")


class StandardFilesTests(unittest.TestCase):
    def test_absent_files_are_listed_and_change_no_verdict(self) -> None:
        with _project(**{"README.md": PROJECT_README, "LICENSE": "MIT\n",
                         ".github/SECURITY.md": "# Security\n\nWrite to us.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertEqual(report["repo_standards"]["absent"], ["CONTRIBUTING", "CHANGELOG"])
        self.assertEqual(report["verdict"], "clean")


class SelfLinkTests(unittest.TestCase):
    def _repository(self, raw: str) -> Path:
        project = Path(raw)
        for command in (["init", "-q"],
                        ["remote", "add", "origin", "https://github.com/acme/bridge.git"]):
            subprocess.run(["git", "-C", str(project), *command],
                           check=True, capture_output=True, timeout=30)
        return project

    def test_a_full_address_to_the_repositorys_own_file_is_reported(self) -> None:
        body = (PROJECT_README
                + "\nSee [the guide](https://github.com/acme/bridge/blob/main/docs/GUIDE.md)"
                  " and [another project](https://github.com/acme/other/blob/main/README.md).\n")
        with _project(**{"README.md": body}) as raw:
            report = lint_docs(self._repository(raw))
        found = [f for f in report["findings"] if f["check"] == "absolute-self-link"]
        self.assertEqual(len(found), 1, report["findings"])
        self.assertIn("docs/GUIDE.md", found[0]["remedy"])
        self.assertEqual(report["high_severity"], 0)

    def test_a_release_note_keeps_its_full_addresses(self) -> None:
        note = "# 1.0\n\nSee https://github.com/acme/bridge/blob/main/docs/GUIDE.md\n"
        with _project(**{"README.md": PROJECT_README,
                         "docs/releases/RELEASE_NOTES_v1.0.0.md": note}) as raw:
            report = lint_docs(self._repository(raw))
        self.assertNotIn("absolute-self-link", _checks(report["findings"]))


class FirstRunTests(unittest.TestCase):
    def _init(self, anchor, archive):
        from godmode_runtime.godmode_console import Runtime, cmd_init
        return cmd_init(argparse.Namespace(roles=False),
                        Runtime(anchor=anchor, archive=archive)).payload

    def test_init_names_the_readme_findings_once(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "README.md").write_text(SESSION_README, encoding="utf-8")
            first = self._init(anchor, archive)
            second = self._init(anchor, archive)
        self.assertIn("readme-session-state", _checks(first["readme"]["findings"]))
        self.assertNotIn("readme", second)

    def test_init_says_nothing_about_a_sound_readme(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "README.md").write_text(PROJECT_README, encoding="utf-8")
            self.assertNotIn("readme", self._init(anchor, archive))


class ThisRepositoryTests(unittest.TestCase):
    def test_the_shipped_readme_meets_its_own_standard(self) -> None:
        review = readme_review(PLUGIN_ROOT)
        self.assertEqual(review["findings"] + review["advisories"], [], review)


if __name__ == "__main__":
    unittest.main()

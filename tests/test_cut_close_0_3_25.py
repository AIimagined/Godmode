"""The last items of the 0.3.25 cut, 2026-09-11.

A private term reached the remote inside one commit message while the
tree scan stayed green; the git backstop now refuses a private term in
the staged diff at pre-commit and in the message at commit-msg. Four
rules absorbed from a multi-agent workspace's review checklist: an
incident names what its hypothesis predicts, a swallow exemption says
who hears the degraded path, quantities that disagree across a time
window name the instant, and closure lists the prose that names what a
change defines.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_atlas import prose_mentions  # noqa: E402
from godmode_runtime.godmode_attest import record_claim  # noqa: E402
from godmode_runtime.godmode_githooks import HOOK_NAMES, evaluate_git_hook  # noqa: E402
from godmode_runtime.godmode_mistakes import record_incident  # noqa: E402
from godmode_runtime.godmode_swallow import scan_project  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


class CommitTimeTermGuardTests(unittest.TestCase):
    def test_a_private_term_in_the_staged_diff_or_the_message_is_refused(self) -> None:
        self.assertIn("commit-msg", HOOK_NAMES)
        with isolated_project() as (project, _s, _a, archive), tempfile.TemporaryDirectory() as raw:
            archive.initialize()
            terms = Path(raw) / "terms.txt"
            terms.write_text("zorblatt\n", encoding="utf-8")
            _git(project, "init", "-q")
            (project / "a.py").write_text("x = 1\n", encoding="utf-8")
            _git(project, "add", "-A")
            with mock.patch.dict(os.environ, {"GODMODE_COVERAGE_TERMS": str(terms)}):
                clean = evaluate_git_hook(archive, project, "pre-commit")
                self.assertEqual(clean["verdict"], "allow", clean)
                (project / "a.py").write_text("x = 1  # zorblatt\n", encoding="utf-8")
                _git(project, "add", "-A")
                dirty = evaluate_git_hook(archive, project, "pre-commit")
                self.assertEqual(dirty["verdict"], "block", dirty)
                self.assertNotIn("zorblatt", dirty["reason"])
                message = evaluate_git_hook(archive, project, "commit-msg", "fix: mention zorblatt here")
                self.assertEqual(message["verdict"], "block", message)
                fine = evaluate_git_hook(archive, project, "commit-msg", "fix: an ordinary message")
                self.assertEqual(fine["verdict"], "allow", fine)


class IncidentPredictsTests(unittest.TestCase):
    def test_an_incident_without_a_prediction_is_told_so(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            bare = record_incident(archive, "flaky gate", "the shard timed out")
            told = record_incident(archive, "flaky gate", "the shard timed out",
                                   predicts="the same shard passes alone within 30 minutes")
        self.assertTrue(any("no prediction" in a for a in bare["data"].get("advisories", [])))
        self.assertFalse(any("no prediction" in a for a in told["data"].get("advisories", [])))
        self.assertEqual(told["data"]["predicts"], "the same shard passes alone within 30 minutes")


class SwallowAudienceTests(unittest.TestCase):
    def test_an_exemption_says_whether_it_names_who_hears_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text(
                "try:\n    x = 1\nexcept OSError:  # godmode: swallow-ok: best effort\n    pass\n"
                "try:\n    y = 2\nexcept OSError:  # godmode: swallow-ok: the operator sees it in doctor\n    pass\n",
                encoding="utf-8")
            report = scan_project(project)
        named = [e["audience_named"] for e in report["exemptions"]]
        self.assertEqual(sorted(named), [False, True], report["exemptions"])
        self.assertEqual(report["audience_unstated"], 1)


class TimeWindowQuantitiesTests(unittest.TestCase):
    def test_disagreeing_numbers_across_a_window_name_the_instant(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "s", "the retention pass leaves 885 stale rows across pods", "observed")
            later = record_claim(archive, project, "s",
                                 "the retention pass leaves 876 stale rows across pods in the last 30 days", "observed")
        notes = " ".join(later["data"].get("advisories", []))
        self.assertIn("quantities disagree", notes)
        self.assertIn("different instants", notes)


class ProseClosureTests(unittest.TestCase):
    def test_prose_that_names_a_changed_symbol_is_listed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "src").mkdir(); (project / "docs").mkdir()
            (project / "src" / "retry.py").write_text("def retry_budget():\n    return 3\n", encoding="utf-8")
            (project / "docs" / "ops.md").write_text("The retry_budget is three attempts.\n", encoding="utf-8")
            (project / "src" / "other.py").write_text("# retry_budget caps the loop\nx = 1\n", encoding="utf-8")
            (project / "src" / "user.py").write_text("y = retry_budget()\n", encoding="utf-8")
            found = prose_mentions(project, ["src/retry.py"])
        self.assertEqual(found, {"retry_budget": ["docs/ops.md", "src/other.py"]})


if __name__ == "__main__":
    unittest.main()

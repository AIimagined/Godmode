"""Regression coverage for `skills/godmode-second-look`'s Deterministic
Execution Flow: every preflight command the SKILL.md names, run in order
against a disposable fixture project, proving the flow is executable over
real verbs rather than aspirational prose.

Flow under test (SKILL.md steps 1-7):
  1. `history --kind claim --subject ...`   - locate the pass under review
  2. `claim --stale`                        - check the cited evidence
  3. `differential record`                  - compare two states
  4. `retest`                               - list tests pinning the change
  5. `atlas closure --changed ...`          - map blast radius
  6. `verdict record --acquitted-by independent` - an independent disposition
  7. `claim --resolve ... --outcome held|superseded` - close the loop
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, capture_output=True, text=True)


@contextmanager
def _fixture_project():
    """A tiny real git repo with one source file, so `retest`/`atlas
    closure` have something concrete to reason about, plus its own
    disposable archive - never the real project's.
    """
    with tempfile.TemporaryDirectory(prefix="godmode-second-look-") as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        _git(project, "init", "-q")
        _git(project, "config", "user.email", "d@e.invalid")
        _git(project, "config", "user.name", "fixture")
        (project / "widget.py").write_text("def widget():\n    return 1\n", encoding="utf-8")
        (project / "test_widget.py").write_text(
            "import unittest\nfrom widget import widget\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_widget(self):\n"
            "        self.assertEqual(widget(), 1)\n",
            encoding="utf-8",
        )
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "base")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            _run(project, "session", "open", "--label", "second-look-fixture")
            yield project


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


class SecondLookFlowTests(unittest.TestCase):
    def test_full_flow_ends_in_a_held_disposition(self) -> None:
        with _fixture_project() as project:
            # The pass under review: an original, accepted claim.
            code, original = _run(
                project, "claim", "widget() returns 1", "--grade", "observed",
                "--cite", "file:widget.py#L1",
            )
            self.assertEqual(code, 0, original)

            # Step 1: locate it again by subject, the way a second look
            # starts - and how this test recovers its sequence, since
            # `claim` itself reports the text and grade, not the number.
            code, history = _run(
                project, "history", "--kind", "claim", "--subject", "widget() returns 1",
            )
            self.assertEqual(code, 0, history)
            self.assertTrue(history["records"])
            original_seq = history["records"][-1]["sequence"]

            # Step 2: is the cited evidence still there?
            code, stale = _run(project, "claim", "--stale")
            self.assertEqual(code, 0, stale)

            # Step 3: compare two states - here, the same file read two ways.
            code, diff = _run(
                project, "differential", "record",
                "--subject", "widget.py before and after the second look",
                "--a", "file:widget.py", "--b", "file:widget.py",
                "--method", "read", "--delta", "no observed difference",
            )
            self.assertEqual(code, 0, diff)

            # Step 4: what tests pin the changed file?
            code, plan = _run(project, "retest", "--base", "HEAD")
            self.assertEqual(code, 0, plan)
            self.assertIn("commands", plan)

            # Step 5: how far does the change reach? A fresh fixture has no
            # saved graph yet - exercise the flow's own documented fallback
            # (SKILL.md: "a fresh checkout ... refuses with 'no graph
            # snapshot found'") before running the rebuild it names.
            code, unbuilt = _run(project, "atlas", "closure", "--changed", "widget.py")
            self.assertEqual(code, 1, unbuilt)
            self.assertTrue(unbuilt.get("refused"))
            self.assertIn("no graph snapshot found", unbuilt["verify"]["reason"])

            code, rebuild = _run(project, "atlas", "graph", "rebuild")
            self.assertEqual(code, 0, rebuild)
            code, closure = _run(project, "atlas", "closure", "--changed", "widget.py")
            # widget.py has a dependent (test_widget.py) that was not itself
            # touched - closure reports that as a finding (exit 1) rather
            # than silence, which is the scope-drift signal this step exists
            # to surface.
            self.assertEqual(code, 1, closure)
            self.assertEqual(closure["verdict"], "unfollowed-dependents")

            # Step 6: an independent disposition, its own checker.
            code, verdict = _run(
                project, "verdict", "record",
                "--claim", "widget() returns 1",
                "--value", "1",
                "--witness", "file:widget.py",
                "--checker", "python -c \"import sys; sys.exit(0)\"",
                "--acquitted-by", "independent",
            )
            self.assertEqual(code, 0, verdict)
            verdict_seq = verdict["sequence"]

            # Step 7: nothing new - close the loop as held.
            code, resolution = _run(
                project, "claim", "--resolve", str(original_seq), "--outcome", "held",
                "--cite", f"verdict:{verdict_seq}",
            )
            self.assertEqual(code, 0, resolution)
            self.assertEqual(resolution["outcome"], "held")
            self.assertEqual(resolution["resolves"], original_seq)

    def test_a_finding_resolves_the_original_claim_as_superseded(self) -> None:
        with _fixture_project() as project:
            code, original = _run(
                project, "claim", "widget() is covered by a passing test", "--grade", "observed",
                "--cite", "file:test_widget.py#L1",
            )
            self.assertEqual(code, 0, original)
            code, history = _run(
                project, "history", "--kind", "claim",
                "--subject", "widget() is covered by a passing test",
            )
            self.assertEqual(code, 0, history)
            original_seq = history["records"][-1]["sequence"]

            # The independent recheck finds a verification-miss: the checker
            # this second look runs disagrees with the original claim.
            code, verdict = _run(
                project, "verdict", "record",
                "--claim", "widget() is covered by a passing test",
                "--value", "uncovered",
                "--witness", "file:test_widget.py",
                "--checker", "python -c \"import sys; sys.exit(1)\"",
                "--acquitted-by", "independent",
            )
            # A refuted checker still records the verdict; the command's
            # own exit code names the disposition (1 for anything but
            # confirmed), not a failure to run.
            self.assertEqual(code, 1, verdict)
            self.assertEqual(verdict["disposition"], "refuted")

            # A refuted verdict cannot itself resolve a claim (`verdict:<n>`
            # only accepts a CONFIRMED one) - the fresh finding is cited by
            # the file evidence the independent checker actually read.
            code, resolution = _run(
                project, "claim", "--resolve", str(original_seq), "--outcome", "superseded",
                "--cite", "file:test_widget.py#L1",
            )
            self.assertEqual(code, 0, resolution)
            self.assertEqual(resolution["outcome"], "superseded")

            # A claim resolves at most once.
            code, second_attempt = _run(
                project, "claim", "--resolve", str(original_seq), "--outcome", "held",
                "--cite", "file:test_widget.py#L1",
            )
            self.assertNotEqual(code, 0, second_attempt)


if __name__ == "__main__":
    unittest.main()

"""A check already run on this HEAD within the hour is the evidence for a
claim; `claim --verify` references it instead of running it again. A
different HEAD, an older run, a different command, or `--rerun` runs it."""

from __future__ import annotations

import io
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

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import fresh_execution, run_check  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

# No spaces inside any argument: a `cmd:` citation is the joined argv and
# is split again on re-run, so an argument with a space would not round-trip.
CHECK = ["python", "-c", "pass"]


def _git_project(project: Path) -> Chronicle:
    """Turn the fixture into a repository first, then initialise its archive
    under that identity: `fresh_execution` matches on HEAD."""
    for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                    ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "seed", "--allow-empty"]):
        subprocess.run(["git", *command], cwd=project, check=True, capture_output=True)
    archive = Chronicle(resolve_anchor(project))
    archive.initialize()
    return archive


def _claim(project: Path, *args: str) -> tuple[int, dict]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), "--json", "claim", *args])
    text = out.getvalue().strip() or err.getvalue().strip()
    try:
        return code, (json.loads(text) if text else {})
    except json.JSONDecodeError:
        return code, {"raw": text}


class FreshExecutionTests(unittest.TestCase):
    def test_a_run_on_this_head_within_the_hour_is_found(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_project(project)
            outcome = run_check(archive, "s-1", project, "deciding", CHECK)
            citation = outcome["citation"]
            fresh = fresh_execution(archive, project, citation)
            self.assertIsNotNone(fresh)
            self.assertEqual(fresh["sequence"], outcome.get("sequence", fresh["sequence"]))
            self.assertTrue(fresh["passed"])
            self.assertEqual(fresh["exit_code"], 0)
            self.assertIsNone(fresh_execution(archive, project, "cmd:python -c other"))
            self.assertIsNone(fresh_execution(archive, project, citation, max_age_seconds=0))

    def test_a_new_head_is_a_new_question(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_project(project)
            citation = run_check(archive, "s-1", project, "deciding", CHECK)["citation"]
            subprocess.run(["git", "commit", "-qm", "next", "--allow-empty"], cwd=project,
                           check=True, capture_output=True)
            self.assertIsNone(fresh_execution(archive, project, citation))


class ClaimVerifyTests(unittest.TestCase):
    def test_claim_verify_reuses_the_fresh_run_and_rerun_runs_it(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_project(project)
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(console.main(["--project", str(project), "--json", "session", "open"]), 0)
                # The deciding check, run once through the CLI in this session.
                self.assertEqual(console.main(["--project", str(project), "--json", "verify", "deciding",
                                               "--command", " ".join(f'"{c}"' if " " in c else c
                                                                     for c in CHECK)]), 0)
            newest = [r for r in archive.select(kind="attestation", limit=20)][-1]
            citation = next(e for e in newest["evidence"] if str(e).startswith("cmd:"))
            with mock.patch.object(console, "run_check") as ran:
                code, payload = _claim(project, "the check passes", "--grade", "verified",
                                       "--cite", citation, "--verify")
            ran.assert_not_called()
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["grade"], "verified", payload)
            self.assertTrue(any(r.get("reused") for r in payload.get("verified_checks", [])), payload)
            with mock.patch.object(console, "run_check", wraps=console.run_check) as ran:
                code, payload = _claim(project, "the check passes again", "--grade", "verified",
                                       "--cite", citation, "--verify", "--rerun")
            ran.assert_called_once()
            self.assertEqual(code, 0, payload)


if __name__ == "__main__":
    unittest.main()

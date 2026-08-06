"""S5-04 / S4-04 / S8-04: secret boundaries, no-progress enforcement, minimality.

Fixtures are local copies of the runtime-test patterns rather than imports: these
tests must keep passing even if the other module reshapes its helpers, because a
gate test that breaks for fixture reasons reads as a gate that broke.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

# Assembled at runtime so this test file itself never carries a contiguous
# secret-shaped literal that a boundary scan of the repository would flag.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
BEARER = "bearer " + "eyJhbGciOiJIUzI1NiJ9.payload.signature"


@contextmanager
def isolated_project():
    """A bare project plus its private archive (local copy of the shared idiom)."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


@contextmanager
def isolated_git_project():
    """A committed git repo isolated from the user's global config."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        (project / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        env = {"GODMODE_STATE_HOME": str(state), "GIT_CONFIG_GLOBAL": str(base / "gitconfig")}
        with mock.patch.dict(os.environ, env, clear=False):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project)]
            subprocess.run(git[:1] + ["init", "-q", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True, capture_output=True)
            yield project, git


class SecretBoundaryTests(unittest.TestCase):
    """S5-04: a secret in staged content is found BEFORE the commit (E-06)."""

    def test_staged_aws_key_is_found_and_masked(self) -> None:
        from godmode_runtime.godmode_egress import scan_staged

        with isolated_git_project() as (project, git):
            (project / "config.py").write_text(
                f'ACCESS = "{AWS_KEY}"\n', encoding="utf-8")
            subprocess.run(git + ["add", "config.py"], check=True, capture_output=True)
            report = scan_staged(project)
            self.assertFalse(report["clean"], report)
            hit = next(f for f in report["findings"] if f["path"] == "config.py")
            self.assertEqual(hit["kind"], "aws-access-key")
            self.assertEqual(hit["line"], 1)
            # The excerpt proves a secret exists without repeating it.
            self.assertTrue(hit["masked_excerpt"].startswith("AKIA"))
            self.assertIn("*", hit["masked_excerpt"])
            self.assertNotIn(AWS_KEY, hit["masked_excerpt"])

    def test_untracked_file_is_scanned_as_would_be_added(self) -> None:
        from godmode_runtime.godmode_egress import scan_staged

        with isolated_git_project() as (project, _git):
            (project / "notes.txt").write_text(
                'password = "hunter2hunter2"\n', encoding="utf-8")  # godmode: allow-secret
            report = scan_staged(project)
            self.assertFalse(report["clean"], report)
            hit = next(f for f in report["findings"] if f["path"] == "notes.txt")
            self.assertEqual(hit["kind"], "credential-assignment")
            self.assertNotIn("hunter2hunter2", hit["masked_excerpt"])

    def test_clean_staged_content_passes(self) -> None:
        from godmode_runtime.godmode_egress import scan_staged

        with isolated_git_project() as (project, git):
            (project / "app.py").write_text(
                "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
                encoding="utf-8")
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            report = scan_staged(project)
            self.assertTrue(report["clean"], report)
            self.assertEqual(report["findings"], [])

    def test_non_git_directory_fails_closed(self) -> None:
        from godmode_runtime.godmode_egress import scan_staged

        with tempfile.TemporaryDirectory() as raw:
            report = scan_staged(Path(raw))
            # "Nothing observable" must never read as "nothing to find".
            self.assertFalse(report["clean"], report)

    def test_scan_paths_covers_arbitrary_files(self) -> None:
        from godmode_runtime.godmode_egress import scan_paths

        with isolated_git_project() as (project, _git):
            (project / "export.md").write_text(
                f"Authorization: {BEARER}\n", encoding="utf-8")
            (project / "clean.md").write_text("Plain prose only.\n", encoding="utf-8")
            report = scan_paths(project, ["export.md", "clean.md"])
            self.assertFalse(report["clean"], report)
            hit = next(f for f in report["findings"] if f["path"] == "export.md")
            self.assertEqual(hit["kind"], "bearer-token")
            self.assertNotIn(BEARER.split()[-1], hit["masked_excerpt"])
            clean = scan_paths(project, ["clean.md"])
            self.assertTrue(clean["clean"], clean)


class HypothesisResetTests(unittest.TestCase):
    """S4-04: three same-hypothesis non-green checkpoints demand a reset."""

    def test_three_red_checkpoints_with_same_hypothesis_block_analyze(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for _ in range(3):
                archive.append("checkpoint", "attempt",
                               {"status": "red", "hypothesis": "the cache is stale"})
            report = analyze(archive)
            hits = [f for f in report["findings"] if f["detector"] == "no-progress-cycle"]
            self.assertTrue(hits, report["findings"])
            self.assertTrue(hits[0]["blocking"])
            self.assertTrue(report["blocking"])
            self.assertEqual(report["verdict"], "loop-detected")
            detail = hits[0]["detail"].lower()
            self.assertIn("hypothesis", detail)
            self.assertIn("reset", detail)
            self.assertIn("the cache is stale", hits[0]["detail"])

    def test_green_checkpoint_breaks_the_run(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            data = {"status": "red", "hypothesis": "the cache is stale"}
            archive.append("checkpoint", "attempt", dict(data))
            archive.append("checkpoint", "attempt", dict(data))
            archive.append("checkpoint", "attempt",
                           {"status": "green", "hypothesis": "the cache is stale"})
            archive.append("checkpoint", "attempt", dict(data))
            report = analyze(archive)
            self.assertFalse(
                [f for f in report["findings"] if f["detector"] == "no-progress-cycle"],
                report["findings"])

    def test_changing_the_hypothesis_is_progress(self) -> None:
        from godmode_runtime.godmode_loop import hypothesis_reset_required

        records = [
            {"kind": "checkpoint", "sequence": i, "subject": "cp",
             "data": {"status": "red", "hypothesis": hyp}}
            for i, hyp in enumerate(
                ("stale cache", "stale cache", "clock skew"), start=1)
        ]
        self.assertEqual(hypothesis_reset_required(records), [])

    def test_finding_cites_all_three_checkpoints(self) -> None:
        from godmode_runtime.godmode_loop import hypothesis_reset_required

        records = [
            {"kind": "checkpoint", "sequence": i, "subject": "cp",
             "data": {"status": "red", "hypothesis": "stale cache"}}
            for i in (4, 7, 9)
        ]
        findings = hypothesis_reset_required(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["citations"], ["seq:4", "seq:7", "seq:9"])


class MinimalityTests(unittest.TestCase):
    """S8-04: size pressure is always reported, never enforced."""

    def test_500_line_addition_is_flagged(self) -> None:
        from godmode_runtime.godmode_scope import minimality

        with isolated_git_project() as (project, git):
            (project / "big.py").write_text(
                "".join(f"VALUE_{i} = {i}\n" for i in range(500)), encoding="utf-8")
            subprocess.run(git + ["add", "big.py"], check=True, capture_output=True)
            report = minimality(project)
            self.assertEqual(report["verdict"], "pressure")
            self.assertGreaterEqual(report["added_lines"], 500)
            self.assertEqual(report["largest"]["path"], "big.py")
            details = " | ".join(f["detail"] for f in report["findings"])
            self.assertIn("consider splitting", details)
            self.assertIn("big.py", details)

    def test_small_change_stays_within_pressure_but_numbers_show(self) -> None:
        from godmode_runtime.godmode_scope import minimality

        with isolated_git_project() as (project, _git):
            (project / "app.py").write_text(
                "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
                encoding="utf-8")
            report = minimality(project)
            self.assertEqual(report["verdict"], "within-pressure")
            self.assertEqual(report["findings"], [])
            # The numbers are present even when nothing is flagged: pressure is
            # visible before it becomes a finding.
            self.assertGreater(report["added_lines"], 0)
            self.assertGreaterEqual(report["files"], 1)
            self.assertIsNotNone(report["largest"])

    def test_more_than_five_new_files_are_named(self) -> None:
        from godmode_runtime.godmode_scope import minimality

        with isolated_git_project() as (project, _git):
            for i in range(6):
                (project / f"module_{i}.py").write_text("x = 1\n", encoding="utf-8")
            report = minimality(project)
            self.assertEqual(report["verdict"], "pressure")
            named = next(f for f in report["findings"] if f["kind"] == "many-new-files")
            for i in range(6):
                self.assertIn(f"module_{i}.py", named["detail"])

    def test_file_over_200_added_lines_is_named_individually(self) -> None:
        from godmode_runtime.godmode_scope import minimality

        with isolated_git_project() as (project, git):
            (project / "mid.py").write_text(
                "".join(f"ROW_{i} = {i}\n" for i in range(250)), encoding="utf-8")
            subprocess.run(git + ["add", "mid.py"], check=True, capture_output=True)
            report = minimality(project)
            large = [f for f in report["findings"] if f["kind"] == "large-file-addition"]
            self.assertTrue(large, report["findings"])
            self.assertIn("mid.py", large[0]["detail"])
            # 250 lines in one file does not trip the 400-line change-unit rule.
            self.assertFalse(
                [f for f in report["findings"] if f["kind"] == "large-change"])


if __name__ == "__main__":
    unittest.main()

"""scripts/dev/pre-push: a delete or a tag push carries no branch code, so
the ~30 min local run (`ci_local.py`) is skipped for it rather than
refusing the push. A real branch update still runs the checks.

Git feeds the hook one `<local ref> <local sha> <remote ref> <remote sha>`
line per pushed ref on stdin; these tests drive the real shell script with
`sh` against that contract directly, without running the real CI.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = PLUGIN_ROOT / "scripts" / "dev" / "pre-push"

_ZERO = "0" * 40
_SHA_A = "1" * 40
_SHA_B = "2" * 40
_SHA_C = "3" * 40

_DELETE_LINE = f"(delete) {_ZERO} refs/heads/gone {_SHA_A}\n"
_TAG_LINE = f"refs/tags/v1.2.3 {_SHA_B} refs/tags/v1.2.3 {_ZERO}\n"
_BRANCH_LINE = f"refs/heads/main {_SHA_C} refs/heads/main {_ZERO}\n"

_SKIP_MARKER = "skipping the local run"


@unittest.skipUnless(shutil.which("sh"), "sh is not on PATH")
class PrePushSkipTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True,
                       capture_output=True)

    def _run(self, stdin_text: str, script: Path = PRE_PUSH) -> subprocess.CompletedProcess:
        return subprocess.run(["sh", str(script)], cwd=self.repo, input=stdin_text,
                              text=True, capture_output=True, timeout=20)

    def test_a_branch_delete_is_skipped_without_running_ci_local(self) -> None:
        result = self._run(_DELETE_LINE)
        self.assertEqual(result.returncode, 0)
        self.assertIn(_SKIP_MARKER, result.stderr)

    def test_a_tag_push_is_skipped_without_running_ci_local(self) -> None:
        result = self._run(_TAG_LINE)
        self.assertEqual(result.returncode, 0)
        self.assertIn(_SKIP_MARKER, result.stderr)

    def test_a_delete_and_a_real_branch_together_are_not_skipped(self) -> None:
        # Swap the real ci_local.py invocation for a stub so this proves
        # the "runs checks" path is taken without paying for the real
        # ~30 min local CI run.
        stub_script = Path(self._tmp.name) / "pre-push-stub"
        body = PRE_PUSH.read_text(encoding="utf-8")
        marker = "exec python scripts/dev/ci_local.py"
        self.assertIn(marker, body)
        body = body.replace(marker, "echo ran-the-checks-path")
        stub_script.write_text(body, encoding="utf-8")

        result = self._run(_DELETE_LINE + _BRANCH_LINE, script=stub_script)
        self.assertNotIn(_SKIP_MARKER, result.stderr)
        self.assertIn("ran-the-checks-path", result.stdout)

    def test_empty_stdin_keeps_running_the_checks(self) -> None:
        stub_script = Path(self._tmp.name) / "pre-push-stub-empty"
        body = PRE_PUSH.read_text(encoding="utf-8")
        marker = "exec python scripts/dev/ci_local.py"
        body = body.replace(marker, "echo ran-the-checks-path")
        stub_script.write_text(body, encoding="utf-8")

        result = self._run("", script=stub_script)
        self.assertNotIn(_SKIP_MARKER, result.stderr)
        self.assertIn("ran-the-checks-path", result.stdout)


if __name__ == "__main__":
    unittest.main()

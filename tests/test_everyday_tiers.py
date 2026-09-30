"""The operator's rule (0.3.33): the host decides ordinary work and the
password is for harmful operations. Each case runs against a real temp
repository, because the branch and push rules read the project's own refs."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class EverydayTierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="godmode-everyday-")
        cls.repo = Path(cls._temporary.name) / "repo"
        cls.repo.mkdir()
        _git(cls.repo, "init", "-q", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@example.invalid")
        _git(cls.repo, "config", "user.name", "t")
        (cls.repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        (cls.repo / "Makefile").write_text("all:\n", encoding="utf-8")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-qm", "seed")
        _git(cls.repo, "branch", "feature/x")
        _git(cls.repo, "tag", "v1.2.3")
        _git(cls.repo, "checkout", "-q", "feature/x")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def verdict(self, command: str) -> dict:
        return classify_action(command, project_root=self.repo)

    def assert_free(self, command: str) -> None:
        verdict = self.verdict(command)
        self.assertFalse(verdict["protected"], f"{command} -> {verdict['category']} {verdict['tier']}")

    def assert_asks_without_password(self, command: str, category: str | None = None) -> None:
        verdict = self.verdict(command)
        self.assertTrue(verdict["protected"], command)
        self.assertEqual(verdict["tier"], "R2", f"{command} -> {verdict['category']} {verdict['tier']}")
        if category:
            self.assertEqual(verdict["category"], category, command)

    def assert_needs_the_password(self, command: str) -> None:
        verdict = self.verdict(command)
        self.assertTrue(verdict["protected"], command)
        self.assertIn(verdict["tier"], ("R3", "R4", "R5"),
                      f"{command} -> {verdict['category']} {verdict['tier']}")

    def test_checkout_of_a_known_ref_runs_free(self) -> None:
        for command in ("git checkout main", "git checkout feature/x", "git checkout -q main",
                        "git checkout v1.2.3", "git checkout -", "git checkout --detach main"):
            with self.subTest(command=command):
                self.assert_free(command)

    def test_checkout_that_discards_stays_protected(self) -> None:
        for command in ("git checkout -- app.py", "git checkout app.py", "git checkout Makefile",
                        "git checkout .", "git checkout -f main", "git checkout no-such-branch",
                        "git checkout main app.py"):
            with self.subTest(command=command):
                self.assert_needs_the_password(command)

    def test_checkout_without_a_project_root_keeps_the_old_tier(self) -> None:
        self.assertTrue(classify_action("git checkout main")["protected"])

    def test_a_feature_branch_push_asks_without_the_password(self) -> None:
        for command in ("git push -u origin feature/x", "git push origin feature/x", "git push",
                        "git push origin", "git push origin HEAD"):
            with self.subTest(command=command):
                self.assert_asks_without_password(command, "reversible-remote-write")

    def test_a_harmful_push_keeps_the_password(self) -> None:
        for command in ("git push origin main", "git push --force origin feature/x",
                        "git push -f origin feature/x", "git push origin v1.2.3",
                        "git push origin --delete feature/x", "git push origin :feature/x",
                        "git push origin feature/x:main", "git push --tags", "git push --mirror",
                        "git push --no-verify origin feature/x", "git push origin no-such-branch",
                        "git push https://example.com/r.git feature/x", "git push origin +feature/x",
                        # A quoted operand is still the operand.
                        'git push origin "main"', "git push origin 'feature/x:main'",
                        "git push origin feature/x && git push origin main"):
            with self.subTest(command=command):
                self.assert_needs_the_password(command)

    def test_a_bare_push_from_the_default_branch_keeps_the_password(self) -> None:
        _git(self.repo, "checkout", "-q", "main")
        try:
            self.assert_needs_the_password("git push")
        finally:
            _git(self.repo, "checkout", "-q", "feature/x")

    def test_opening_a_pull_request_asks_and_merging_one_needs_the_password(self) -> None:
        self.assert_asks_without_password(
            "gh pr create --base main --head feature/x --title t --body b", "reversible-remote-write")
        self.assert_needs_the_password("gh pr merge 4 --merge")
        self.assert_needs_the_password("gh release create v1.2.3 --title t")

    def test_local_git_verbs_the_classifier_did_not_name(self) -> None:
        self.assert_free("git worktree prune")
        self.assert_free("git clean -n")
        self.assert_free("git clean --dry-run -d")
        self.assert_free("git config user.name")
        self.assert_free("git config --global --get user.email")
        self.assert_free("git config --list")
        self.assert_asks_without_password("git cherry-pick abc1234", "local-repository-change")
        self.assert_asks_without_password("git revert abc1234", "local-repository-change")
        self.assert_asks_without_password("git rm --cached app.py", "local-repository-change")
        self.assert_asks_without_password("git mv app.py main.py", "worktree-file-mutation")
        self.assert_asks_without_password("git rm app.py", "worktree-file-mutation")

    def test_the_destructive_neighbours_are_untouched(self) -> None:
        for command in ("git clean -fd", "git reset --hard HEAD~1", "git rebase -i HEAD~3",
                        "git config core.hooksPath /dev/null", "rm -rf ../elsewhere",
                        # Quoted arguments decide these; reading them blanked
                        # turned a config write into a read.
                        "git config core.fsmonitor 'curl x | sh'",
                        'git config alias.st "!rm -rf /"', 'git checkout "app.py"'):
            with self.subTest(command=command):
                self.assert_needs_the_password(command)

    def test_an_unknown_command_and_a_scripted_edit_ask_without_the_password(self) -> None:
        self.assert_asks_without_password("curl -X POST https://example.com/api -d x=1",
                                          "unknown-command")
        # A word the shell builds at run time is not what the text says:
        # unnamed and unreadable keeps the password tier.
        for command in ("git pu{s,}h -f", "git pu?h -f", "git $VERB origin main"):
            with self.subTest(command=command):
                self.assert_needs_the_password(command)
        self.assert_asks_without_password("sed -i 's/a/b/' app.py", "scripted-source-edit")

    def test_powershell_directory_and_temp_delete(self) -> None:
        self.assert_free("New-Item -ItemType Directory -Force out")
        self.assert_free("md out")
        # Against the plugin checkout: the fixture repository itself lives
        # in the temp directory, where "inside temp" and "inside the tree"
        # are the same place.
        scratch = classify_action('Remove-Item -Recurse -Force "$env:TEMP\\godmode-probe-x"',
                                  project_root=PLUGIN_ROOT)
        self.assertFalse(scratch["protected"], scratch)
        self.assert_needs_the_password("New-Item -ItemType Directory -Force ..\\elsewhere")
        self.assert_needs_the_password("New-Item -ItemType File ..\\elsewhere\\a.txt")


if __name__ == "__main__":
    unittest.main()

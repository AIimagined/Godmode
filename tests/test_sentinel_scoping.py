"""Unknown-command policy, stream tools, and vocabulary scoping (U-G1b).

An unrecognised command with no evidence it mutates anything - no redirect,
no write-capable flag on a known writer - was refused as
`unclassified-mutation`: the fail-closed bucket meant for a genuinely unknown
state, applied instead to an ordinary read the classifier simply had no
vocabulary for (`rev`, `cut`, bare `sed`/`tr` without `-i`, `npm view`, a
PowerShell `foreach` statement...). Refusing for ignorance is not the same
risk as refusing for evidence, and this task tells them apart: no evidence
reads through as an ordinary command (R0); real evidence (a redirect, a
known writer's write flag) still asks, named honestly as `unknown-command`
rather than the uninformative `unclassified-mutation`.

The DB-vocab and git-rule tables are scoped the same way: a bare word like
"restore" means nothing until it is anchored to the command that gives it
meaning (a database client's own head, or `git` for its own subcommands) -
not to wherever the word happens to sit in the line.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


class UnknownDefaultsToAsk(unittest.TestCase):
    def test_unknown_head_without_mutation_evidence_asks(self) -> None:
        v = classify_action("tail -1 f.md | rev | cut -c1-120 | rev")
        self.assertEqual(v["tier"], "R0")  # rev/cut: no vocab hit, no redirect → read chain stays R0

    def test_unknown_head_with_redirect_is_not_r0(self) -> None:
        v = classify_action("mystery-tool --in a > b.txt")
        self.assertNotEqual(v["tier"], "R0")
        self.assertNotEqual(v["category"], "unclassified-mutation")  # refuse-by-ignorance is gone
        self.assertEqual(v["category"], "unknown-command")


class StreamTools(unittest.TestCase):
    def test_sed_in_pipe_without_i_is_r0(self) -> None:
        self.assertEqual(
            classify_action("find . -name '*.test.*' | sed 's|/[^/]*$||' | sort -u")["tier"],
            "R0")

    def test_sed_i_still_mutates(self) -> None:
        self.assertNotEqual(classify_action("sed -i 's/a/b/' file.py")["tier"], "R0")  # green control


class OutputFlagEvidence(unittest.TestCase):
    """A flag that names an output file is exactly as much evidence of a
    write as a `>` redirect is, on a command this module otherwise treats
    as ordinary inspection - found by the parallel fast-gate review:
    `git log --output=/tmp/x` and `sort -o out.txt in.txt` both returned a
    plain read with the write never inspected, because the safe-inspection
    patterns matched on the command's own verb before anything looked at
    its arguments."""

    def test_git_output_flag_is_not_r0(self) -> None:
        for operation in ("git log --output=/tmp/x", "git diff --output=/tmp/x",
                          "git show --output=/tmp/x"):
            with self.subTest(operation=operation):
                self.assertNotEqual(classify_action(operation)["tier"], "R0")

    def test_sort_output_flag_is_not_r0(self) -> None:
        self.assertNotEqual(classify_action("sort -o out.txt in.txt")["tier"], "R0")

    def test_a_real_redirect_past_a_safe_inspection_pattern_is_not_r0(self) -> None:
        """The same defect class, for the operator this flag imitates: a
        `>` after a command `_SAFE_INSPECTION_PATTERNS` matches on its verb
        alone was never inspected either."""
        self.assertNotEqual(classify_action("git log --oneline > /etc/hosts")["tier"], "R0")

    def test_green_controls_stay_reads(self) -> None:
        for operation in ("git log --oneline", "sort in.txt", "gcc -o out.c prog.c"):
            with self.subTest(operation=operation):
                self.assertEqual(classify_action(operation)["tier"], "R0")

    def test_git_output_flag_is_judged_by_its_target(self) -> None:
        project = PLUGIN_ROOT
        contained = classify_action("git diff --output=notes.txt", project_root=project)
        self.assertFalse(contained["protected"])
        outside = classify_action("git log --output=/tmp/x", project_root=project)
        self.assertTrue(outside["protected"])


class FindOkAndExecdirAlreadyDemoteFromR0(unittest.TestCase):
    """Verified against `_FIND_MUTATION` (godmode_sentinel.py) rather than
    assumed: `-execdir`/`-ok`/`-okdir` were already in its pattern alongside
    `-exec`/`-delete` before this task; these pin that coverage rather than
    add it."""

    def test_execdir_ok_okdir_are_not_r0(self) -> None:
        for operation in (
            "find . -name x -execdir rm {} ;",
            "find . -name x -ok rm {} ;",
            "find . -name x -okdir rm {} ;",
        ):
            with self.subTest(operation=operation):
                self.assertNotEqual(classify_action(operation)["tier"], "R0")


class CategoryScoping(unittest.TestCase):
    def test_git_restore_is_git_never_database(self) -> None:
        v = classify_action("git restore src/app.ts")
        self.assertTrue(v["category"].startswith("git") or "worktree" in v["category"])
        self.assertNotIn("database", v["category"])

    def test_db_vocab_needs_db_client_head(self) -> None:
        self.assertNotIn("database", classify_action("echo restore backup plan")["category"])
        self.assertIn("database", classify_action("psql -c 'drop table users'")["category"])  # green control


if __name__ == "__main__":
    unittest.main()

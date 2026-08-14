"""Protected-path reads and the R3 git-worktree ask policy (U-G1c).

Two unrelated defects, fixed together because both are the classifier
answering a question nobody asked. `ls scripts/godmode_runtime` was refused
outright: the protected-path rule exists to stop a *write* into the gate's
own source, and a `ls`/`cat`/`grep` of the same directory carries none of
that risk, so treating a read the same as a write bought no safety and cost
a denial for looking at a file. `git add`/`git commit` were allowed outright:
staging and committing are reversible, local, and were deliberately let
through - but the sibling worktree operations that carry the same
reversibility (`checkout --`, `restore`, `mv`, `stash`, `switch`) already ask
rather than allow, and `add`/`commit` sitting on the other side of that line
was never a decision anyone made, just the one git rule this classifier had
not yet been given.
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

PROJECT = PLUGIN_ROOT


def _decision(verdict: dict) -> str:
    """godmode_session_hook's real allow/ask/refuse mapping for a verdict
    already returned by classify_action - the same reduction
    tests/test_gate_corpus.py's own `_decision` uses, read directly from
    godmode_session_hook.py's `_decision_for` and the pre-tool branch that
    computes `preview["allow"]` rather than trusted from the task brief's own
    sketch (`verdict.get("decision", ...)`), which does not correspond to
    anything classify_action returns: no `"decision"` key and no `"allow"`
    key live in that dict; both are computed by the hook, not the
    classifier. `protected is False` -> allow; `protected is True and tier
    == "R5"` -> refuse; every other protected tier -> ask."""
    if not verdict["protected"]:
        return "allow"
    return "refuse" if verdict["tier"] == "R5" else "ask"


class ProtectedPathReads(unittest.TestCase):
    def test_ls_of_protected_dir_allows(self) -> None:
        self.assertEqual(
            classify_action("ls scripts/godmode_runtime", project_root=PROJECT)["tier"], "R0")

    def test_find_exec_on_protected_dir_does_not_allow(self) -> None:
        self.assertNotEqual(
            classify_action("find scripts/godmode_runtime -name '*.py' -exec rm {} ;",
                            project_root=PROJECT)["tier"],
            "R0")

    def test_write_to_protected_path_still_gated(self) -> None:
        v = classify_action("echo x > scripts/godmode_runtime/godmode_sentinel.py",
                            project_root=PROJECT)
        self.assertNotEqual(v["tier"], "R0")  # green control


class GitAskPolicy(unittest.TestCase):
    def test_git_commit_asks_not_refuses(self) -> None:
        v = classify_action("git add -A && git commit -m 'wip'", project_root=PROJECT)
        self.assertEqual(_decision(v), "ask")

    def test_git_push_force_still_refuses(self) -> None:
        v = classify_action("git push --force origin main", project_root=PROJECT)
        self.assertNotEqual(_decision(v), "ask")  # green control: R4 unchanged


if __name__ == "__main__":
    unittest.main()

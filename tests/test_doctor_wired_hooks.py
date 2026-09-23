"""NS-10g: doctor cross-checks every shipped hook entry point against every
generated host manifest. A hook a host declares its event for, but whose
manifest carries no command answering it, is `orphan`; a manifest command
naming a hook file that does not exist under `hooks/` is `dangling`.

`console._wired_hook_issues(package_root)` is exercised directly against a
temp copy of this repo's own shipped artifacts (`packaging/hosts.json`,
`hooks/hooks.json`, the three `hooks/godmode_*.py` entry points, and the
five dedicated host manifests, including Task 6's Copilot and Kiro) rather
than through the full `doctor`
command - the function reads `package_root` as a parameter precisely so a
temp copy can stand in for the real install.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402

# Every file `_wired_hook_issues` reads, relative to a package root - the
# same set `packaging/hosts.json`'s own `hook_manifests` section names plus
# the section itself and the three shipped entry points the check's
# vocabulary comes from.
_SEED_FILES = (
    "packaging/hosts.json",
    "hooks/hooks.json",
    "hooks/godmode_session_hook.py",
    "hooks/godmode_gate_fast.py",
    "hooks/godmode_post_edit.py",
    ".cursor-plugin/hooks.json",
    ".gemini-plugin/hooks-fragment.json",
    ".antigravity-plugin/hooks-fragment.json",
    ".github/hooks/godmode.json",
    ".kiro/hooks.json",
)


def _seed(root: Path) -> None:
    for relative in _SEED_FILES:
        source = PLUGIN_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _codes(issues: list[dict]) -> list[str]:
    return [issue["code"] for issue in issues]


class WiredHookIssuesTests(unittest.TestCase):
    def test_untouched_tree_has_no_orphan_or_dangling_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            issues = console._wired_hook_issues(root)
        self.assertNotIn("hook-orphan", _codes(issues), issues)
        self.assertNotIn("hook-dangling", _codes(issues), issues)

    def test_a_removed_manifest_entry_is_reported_as_an_orphan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            manifest_path = root / ".cursor-plugin" / "hooks.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["hooks"]["stop"]
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            issues = console._wired_hook_issues(root)
        orphans = [i for i in issues if i["code"] == "hook-orphan"
                   and "cursor" in i["detail"] and "stop" in i["detail"]]
        self.assertTrue(orphans, issues)
        for issue in orphans:
            self.assertEqual(issue["severity"], "warning")

    def test_an_orphan_survives_the_merge_into_shared_blind_spot(self) -> None:
        """The bug class NS-10g cites verbatim: an event present in the tree
        (`SubagentStop`, wired through the shared `hooks/hooks.json` both
        Codex and Grok merge into) absent from what a host actually ships.
        `godmode_bindings.check()` cannot see this - its own `expected` value
        is rendered FROM this same file - so this is the one check that can.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            shared_path = root / "hooks" / "hooks.json"
            shared = json.loads(shared_path.read_text(encoding="utf-8"))
            del shared["hooks"]["SubagentStop"]
            shared_path.write_text(json.dumps(shared, indent=2), encoding="utf-8")
            issues = console._wired_hook_issues(root)
        orphans = {i["detail"] for i in issues if i["code"] == "hook-orphan"}
        self.assertTrue(any("codex" in d and "SubagentStop" in d for d in orphans), issues)
        self.assertTrue(any("grok" in d and "SubagentStop" in d for d in orphans), issues)

    def test_a_manifest_entry_pointing_at_a_missing_file_is_dangling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            fragment_path = root / ".gemini-plugin" / "hooks-fragment.json"
            fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
            block = fragment["hooks"]["BeforeTool"][0]["hooks"][0]
            block["command"] = block["command"].replace(
                "godmode_gate_fast.py", "godmode_gate_fast_missing.py")
            fragment_path.write_text(json.dumps(fragment, indent=2), encoding="utf-8")
            issues = console._wired_hook_issues(root)
        danglers = [i for i in issues if i["code"] == "hook-dangling"
                    and "godmode_gate_fast_missing.py" in i["detail"]
                    and "gemini" in i["detail"]]
        self.assertTrue(danglers, issues)
        for issue in danglers:
            self.assertEqual(issue["severity"], "warning")


if __name__ == "__main__":
    unittest.main()

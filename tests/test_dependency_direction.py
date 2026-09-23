"""hooks/ imports runtime code only through its declared surface (module-level)
or outside a short deny-list (deferred); the runtime never imports hooks/."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_atlas import (  # noqa: E402
    HOOK_DEFERRED_DENY, HOOK_IMPORT_SURFACE, direction_findings)


class DirectionTests(unittest.TestCase):
    def test_head_is_clean(self) -> None:
        self.assertEqual(direction_findings(PLUGIN_ROOT), [])

    def _copy_tree(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for sub in ("hooks", "scripts"):
            shutil.copytree(PLUGIN_ROOT / sub, root / sub, ignore=shutil.ignore_patterns("__pycache__", "*.json"))
        return root

    def test_reverse_import_is_named(self) -> None:
        root = self._copy_tree()
        target = root / "scripts" / "godmode_runtime" / "godmode_zz_seed.py"
        target.write_text("from hooks import godmode_stdin\n", encoding="utf-8")
        findings = direction_findings(root)
        self.assertEqual([f["file"] for f in findings], ["scripts/godmode_runtime/godmode_zz_seed.py"])

    def test_hook_outside_surface_is_named(self) -> None:
        root = self._copy_tree()
        outside = sorted(p.stem for p in (root / "scripts" / "godmode_runtime").glob("godmode_*.py") if p.stem not in HOOK_IMPORT_SURFACE)[0]
        (root / "hooks" / "zz_seed.py").write_text(f"from godmode_runtime.{outside} import *\n", encoding="utf-8")
        findings = direction_findings(root)
        self.assertTrue(
            any(f["file"] == "hooks/zz_seed.py" and f["module"] == outside
                and f["why"] == "module-level hook import outside the declared surface"
                for f in findings),
            findings,
        )

    def test_bare_form_import_is_named(self) -> None:
        # `from godmode_runtime import X` - the bare form, no dotted submodule
        # on the `from` clause. A reading that drops the alias name (as the
        # first cut of this check did) computes module="" here and misses it
        # entirely; this asserts the alias is carried and the module named.
        root = self._copy_tree()
        outside = sorted(p.stem for p in (root / "scripts" / "godmode_runtime").glob("godmode_*.py") if p.stem not in HOOK_IMPORT_SURFACE)[0]
        (root / "hooks" / "zz_bare_seed.py").write_text(f"from godmode_runtime import {outside}\n", encoding="utf-8")
        findings = direction_findings(root)
        self.assertTrue(
            any(f["file"] == "hooks/zz_bare_seed.py" and f["module"] == outside for f in findings),
            findings,
        )

    def test_deferred_denied_import_is_named(self) -> None:
        root = self._copy_tree()
        (root / "hooks" / "zz_deferred_denied.py").write_text(
            "def handler():\n"
            "    from godmode_runtime import godmode_console\n"
            "    return godmode_console\n",
            encoding="utf-8",
        )
        findings = direction_findings(root)
        self.assertTrue(
            any(f["file"] == "hooks/zz_deferred_denied.py" and f["module"] == "godmode_console"
                and f["why"] == "deferred hook import of a denied module"
                for f in findings),
            findings,
        )
        self.assertIn("godmode_console", HOOK_DEFERRED_DENY)

    def test_deferred_nondenied_import_is_not_named(self) -> None:
        # A deferred import - reached only inside a function body - is not
        # held to the module-level surface; only `HOOK_DEFERRED_DENY` applies
        # there, so a module outside the surface but not on the deny-list is
        # not a finding when it is imported this way.
        root = self._copy_tree()
        outside = sorted(
            p.stem for p in (root / "scripts" / "godmode_runtime").glob("godmode_*.py")
            if p.stem not in HOOK_IMPORT_SURFACE and p.stem not in HOOK_DEFERRED_DENY
        )[0]
        (root / "hooks" / "zz_deferred_allowed.py").write_text(
            f"def handler():\n"
            f"    from godmode_runtime import {outside}\n"
            f"    return {outside}\n",
            encoding="utf-8",
        )
        findings = direction_findings(root)
        self.assertEqual(
            [f for f in findings if f["file"] == "hooks/zz_deferred_allowed.py"], [], findings)

    def test_fast_gate_zero_import(self) -> None:
        root = self._copy_tree()
        path = root / "hooks" / "godmode_gate_fast.py"
        path.write_text(path.read_text(encoding="utf-8") + "\nfrom godmode_runtime import godmode_anchor\n", encoding="utf-8")
        self.assertTrue(any(f["file"] == "hooks/godmode_gate_fast.py" for f in direction_findings(root)))

    def test_fast_gate_zero_import_even_deferred(self) -> None:
        # The fast gate's zero-import boundary holds at any depth, not just
        # at module level.
        root = self._copy_tree()
        path = root / "hooks" / "godmode_gate_fast.py"
        path.write_text(
            path.read_text(encoding="utf-8") +
            "\n\ndef _never_called():\n    from godmode_runtime import godmode_anchor\n    return godmode_anchor\n",
            encoding="utf-8",
        )
        self.assertTrue(any(f["file"] == "hooks/godmode_gate_fast.py" for f in direction_findings(root)))

    def test_unparseable_file_is_a_finding_not_a_traceback(self) -> None:
        root = self._copy_tree()
        (root / "hooks" / "zz_broken.py").write_text("def (:\n", encoding="utf-8")
        findings = direction_findings(root)
        broken = [f for f in findings if f["file"] == "hooks/zz_broken.py"]
        self.assertEqual(len(broken), 1, findings)
        self.assertEqual(broken[0]["line"], 0)
        self.assertTrue(broken[0]["why"].startswith("unparseable:"), broken[0])


if __name__ == "__main__":
    unittest.main()

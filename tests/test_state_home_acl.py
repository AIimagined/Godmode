"""The state home is owner-only; doctor warns when group or world can read or write it."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_acl import state_home_acl  # noqa: E402
from godmode_runtime.godmode_anchor import secure_dir  # noqa: E402


class SecureDirTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "mode bits are POSIX")
    def test_secure_dir_is_owner_only(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        made = secure_dir(root / "state")
        self.assertEqual(stat.S_IMODE(made.stat().st_mode), 0o700)


class AclTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.root, ignore_errors=True)

    @unittest.skipIf(os.name == "nt", "mode bits are POSIX")
    def test_posix_permissive_and_tight(self) -> None:
        loose = self.root / "loose"; loose.mkdir(); os.chmod(loose, 0o755)
        self.assertEqual(state_home_acl(loose)["verdict"], "permissive")
        tight = self.root / "tight"; tight.mkdir(); os.chmod(tight, 0o700)
        self.assertEqual(state_home_acl(tight)["verdict"], "tight")

    @unittest.skipUnless(os.name == "nt", "Windows DACL")
    def test_windows_everyone_grant_is_permissive(self) -> None:
        loose = self.root / "loose"; loose.mkdir()
        subprocess.run(["icacls", str(loose), "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True)
        report = state_home_acl(loose)
        self.assertEqual(report["verdict"], "permissive", report)
        self.assertTrue(any("S-1-1-0" in r or "Everyone" in r for r in report["readers"]), report)

    @unittest.skipUnless(os.name == "nt", "Windows DACL")
    def test_windows_owner_only_is_tight(self) -> None:
        tight = self.root / "tight"; tight.mkdir()
        subprocess.run(["icacls", str(tight), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(OI)(CI)F"], check=True, capture_output=True)
        self.assertEqual(state_home_acl(tight)["verdict"], "tight", state_home_acl(tight))


if __name__ == "__main__":
    unittest.main()

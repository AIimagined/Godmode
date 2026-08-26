"""resolve_anchor() shelled to git six times on every call - 272-294ms,
even warm in-process, with no caching. The cache key is .git/HEAD's
(mtime_ns, size): the one file that changes on every checkout, commit, or
branch switch, so staleness is detected by file identity rather than a
guessed TTL.

GODMODE_STATE_HOME is overridden for every test here (mirrors
test_godmode_runtime.isolated_project): the cache file lives under
application_home(), and without the override these tests would write into
the real machine's %LOCALAPPDATA%\\Godmode\\anchor-cache\\ instead of a
throwaway temp directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402


@contextmanager
def _isolated_git_repo():
    with tempfile.TemporaryDirectory(prefix="godmode-anchor-") as temporary:
        base = Path(temporary)
        root = base / "project"
        state = base / "private-state"
        root.mkdir()
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                        ["config", "user.name", "d"]):
            subprocess.run(["git", *command], cwd=root, capture_output=True)
        (root / "seed.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root,
                       capture_output=True)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            yield root


class AnchorCacheTests(unittest.TestCase):
    def test_second_call_is_fast(self) -> None:
        with _isolated_git_repo() as root:
            resolve_anchor(root)  # warm the cache
            t0 = time.perf_counter()
            resolve_anchor(root)
            elapsed_ms = (time.perf_counter() - t0) * 1000
        # Six subprocess spawns cost 270ms+; a cache hit must not spawn any.
        self.assertLess(elapsed_ms, 50)

    def test_cached_anchor_matches_uncached_fields(self) -> None:
        with _isolated_git_repo() as root:
            first = resolve_anchor(root)
            second = resolve_anchor(root)
        self.assertEqual(first, second)

    def test_a_new_commit_invalidates_the_cache(self) -> None:
        with _isolated_git_repo() as root:
            before = resolve_anchor(root)
            (root / "seed.txt").write_text("y\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=root,
                           capture_output=True)
            after = resolve_anchor(root)
        self.assertNotEqual(before.head, after.head)

    def test_a_cold_resolve_spawns_at_most_three_git_processes(self) -> None:
        """The MISS path is what kills the hook, not the hit path.

        Every git call here carries `timeout=5`. Six of them compose into a
        30-second worst case, which is exactly the UserPromptSubmit budget the
        host kills the hook at - so a slow git turns a cache miss into a lost
        turn. A commit invalidates the cache, so on a repository under active
        development the miss path is the ordinary path, not the tail. Counting
        spawns rather than timing them keeps this honest on a fast machine.
        """
        from godmode_runtime import godmode_anchor

        spawned: list[tuple[str, ...]] = []
        real_run = godmode_anchor.subprocess.run

        def counting_run(command, **kwargs):
            spawned.append(tuple(command))
            return real_run(command, **kwargs)

        with _isolated_git_repo() as root:
            with mock.patch.object(godmode_anchor.subprocess, "run", counting_run):
                godmode_anchor.resolve_anchor(root)

        self.assertLessEqual(
            len(spawned), 3,
            f"cold resolve_anchor spawned {len(spawned)} git processes: {spawned}")

    def test_every_remote_is_hashed_from_a_single_spawn(self) -> None:
        """Remote addresses are read once, not once per remote.

        The count matters as much as the values: the old shape asked `git
        remote` for the names and then `git remote get-url` for each one, so
        a repository with several remotes paid several spawns on a path whose
        whole budget is six. The hashes are asserted alongside it so a cheaper
        read cannot quietly become a wrong one - they stay sha256 of the
        address, ordered by remote name.
        """
        import hashlib

        from godmode_runtime import godmode_anchor

        spawned: list[tuple[str, ...]] = []
        real_run = godmode_anchor.subprocess.run

        def counting_run(command, **kwargs):
            spawned.append(tuple(command))
            return real_run(command, **kwargs)

        upstream = "https://example.invalid/upstream.git"
        origin = "https://example.invalid/origin.git"
        with _isolated_git_repo() as root:
            subprocess.run(["git", "remote", "add", "origin", origin],
                           cwd=root, capture_output=True)
            subprocess.run(["git", "remote", "add", "upstream", upstream],
                           cwd=root, capture_output=True)
            with mock.patch.object(godmode_anchor.subprocess, "run", counting_run):
                hashes = godmode_anchor._remote_hashes(Path(root))

        self.assertEqual(hashes, [
            hashlib.sha256(origin.encode("utf-8")).hexdigest(),
            hashlib.sha256(upstream.encode("utf-8")).hexdigest(),
        ])
        self.assertEqual(
            len(spawned), 1,
            f"two remotes cost {len(spawned)} git spawns: {spawned}")

    def test_a_branch_switch_invalidates_the_cache(self) -> None:
        with _isolated_git_repo() as root:
            before = resolve_anchor(root)
            subprocess.run(["git", "checkout", "-q", "-b", "feature"],
                           cwd=root, capture_output=True)
            after = resolve_anchor(root)
        self.assertNotEqual(before.branch, after.branch)


if __name__ == "__main__":
    unittest.main()

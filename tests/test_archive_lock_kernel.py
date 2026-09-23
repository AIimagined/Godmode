"""Concurrent appends never fork the chain, and a dead writer does not block the next.

The lock was an O_EXCL sidecar with an age heuristic: a crashed writer
blocked every append for two minutes. A kernel advisory lock is released
when its holder dies.
"""
from __future__ import annotations

import errno
import multiprocessing
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


def _append(root: str, state: str, n: int) -> None:
    """Module-level so `multiprocessing` can pickle it under `spawn`."""
    os.environ["GODMODE_STATE_HOME"] = state
    archive = Chronicle(resolve_anchor(Path(root)))
    archive.append("decision", f"writer-{n}", {"status": "active", "value": f"v{n}"})


class KernelLockTests(unittest.TestCase):
    def test_32_writers_one_chain(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()

                started = time.monotonic()
                procs = [multiprocessing.Process(target=_append, args=(root, state, n))
                         for n in range(32)]
                for proc in procs:
                    proc.start()
                for proc in procs:
                    proc.join(60)
                elapsed = time.monotonic() - started
                print(f"32-writer wall time: {elapsed:.2f}s", file=sys.stderr)

                for proc in procs:
                    self.assertEqual(proc.exitcode, 0, f"writer process failed: {proc}")

                records = list(archive.read_events())
                subjects = {r["subject"] for r in records if r.get("kind") == "decision"}
                self.assertEqual(len(subjects), 32)

                result = archive.verify()
                self.assertTrue(result["valid"], result)

                previous_hashes = [r.get("previous_hash") for r in records]
                self.assertEqual(len(previous_hashes), len(set(previous_hashes)))

    def test_killed_holder_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            env = dict(os.environ, GODMODE_STATE_HOME=state)
            code = (
                "import sys\n"
                f"sys.path.insert(0, {str(PLUGIN_ROOT / 'scripts')!r})\n"
                f"sys.path.insert(0, {str(PLUGIN_ROOT)!r})\n"
                "import time\n"
                "from pathlib import Path\n"
                "from godmode_runtime.godmode_anchor import resolve_anchor\n"
                "from godmode_runtime.godmode_chronicle import Chronicle\n"
                f"archive = Chronicle(resolve_anchor(Path({root!r})))\n"
                "archive.initialize()\n"
                "lock = archive.write_lock()\n"
                "lock.__enter__()\n"
                "print('held', flush=True)\n"
                "time.sleep(60)\n"
            )
            holder = subprocess.Popen(
                [sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, env=env,
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "held")
            finally:
                holder.kill()
                holder.wait(timeout=10)
                holder.stdout.close()

            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                start = time.monotonic()
                Chronicle(resolve_anchor(Path(root))).append(
                    "decision", "after-kill", {"status": "active", "value": "x"},
                )
                elapsed = time.monotonic() - start
            # 30 s only distinguishes "released by the OS" from "waited out
            # the old age sweep" (120 s); it is a lock-semantics bound, not
            # a performance benchmark.
            self.assertLess(elapsed, 30)


class ExclusiveCreateFallbackTests(unittest.TestCase):
    def test_no_locking_module_falls_back_to_exclusive_create(self) -> None:
        """`_write_lock_exclusive_create` is dead in every other test run.

        `sys.modules["fcntl"] = None` / `["msvcrt"] = None` makes any
        `import fcntl` / `import msvcrt` inside `write_lock` raise
        `ImportError`, the same way it would on a runtime with neither
        module - `godmode_chronicle._has_kernel_locking()` and
        `_kernel_lock`/`_kernel_unlock` all import locally rather than
        caching the module at load time specifically so this works.
        """
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False), \
                    mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": None}):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()
                # The fallback owns its OWN sidecar (`excl_lock_path`),
                # never the kernel lock's `lock_path` - neither exists yet.
                self.assertFalse(archive.lock_path.exists())
                self.assertFalse(archive.excl_lock_path.exists())

                errors: list[BaseException] = []

                def _writer(n: int) -> None:
                    try:
                        archive.append(
                            "decision", f"fallback-{n}", {"status": "active", "value": str(n)}
                        )
                    except BaseException as exc:  # noqa: BLE001
                        errors.append(exc)

                threads = [threading.Thread(target=_writer, args=(n,)) for n in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(30)

                self.assertEqual(errors, [])
                records = list(archive.read_events())
                subjects = {r["subject"] for r in records if r.get("kind") == "decision"}
                self.assertEqual(len(subjects), 8)

                result = archive.verify()
                self.assertTrue(result["valid"], result)

                # `_write_lock_exclusive_create` unlinks its sidecar on
                # every release (unlike the kernel lock above, which keeps
                # its) - that is the one behavioural difference the fix in
                # this task must not blur. The kernel path's own sidecar
                # was never touched, since kernel locking was disabled.
                self.assertFalse(archive.excl_lock_path.exists())
                self.assertFalse(archive.lock_path.exists())


class KernelLockUnusableFallbackTests(unittest.TestCase):
    def test_unsupported_errno_falls_back_per_call_without_latching(self) -> None:
        """An "unsupported here" errno from `_kernel_lock` (ENOLCK, EINVAL,
        ...) must fall straight through to `_write_lock_exclusive_create`
        for THAT CALL ONLY, not spin `write_lock`'s full timeout and
        misreport "archive is busy" (the reviewer measured 20.27 s on the
        pre-fix code with a forced ENOLCK) - and must NOT be latched on
        the `Chronicle` instance (fix round 3: an instance-level latch let
        two different processes, each reacting to their own errno,
        serialize on two different sidecars at once - a silent chain
        fork). Forced with a mock rather than a genuinely broken
        filesystem, since the real thing is not reproducible on demand.
        """
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()

                def _unsupported(fd: int) -> None:
                    raise OSError(errno.ENOLCK, "no locks available")

                with mock.patch(
                    "godmode_runtime.godmode_chronicle._kernel_lock", side_effect=_unsupported
                ):
                    start = time.monotonic()
                    archive.append("decision", "unsupported-fs", {"status": "active", "value": "x"})
                    elapsed = time.monotonic() - start
                    # A lock-semantics bound distinguishing "fell straight
                    # through" from "spun the full 20 s timeout"; not a
                    # performance benchmark.
                    self.assertLess(elapsed, 5)

                    # Per-call, not latched: a SECOND append under the SAME
                    # still-active mock must fall through equally fast -
                    # there is no remembered verdict to short-circuit on,
                    # so this proves the per-call classification itself is
                    # cheap, not that a flag was set once and reused.
                    start = time.monotonic()
                    archive.append("decision", "unsupported-fs-2", {"status": "active", "value": "y"})
                    self.assertLess(time.monotonic() - start, 5)

                    # `lock_is_held()` must answer from the exclusive-create
                    # sidecar while the same errno is still in effect.
                    self.assertFalse(archive.lock_is_held())
                    with archive.write_lock():
                        self.assertTrue(archive.excl_lock_path.exists())
                        self.assertTrue(archive.lock_is_held())
                    self.assertFalse(archive.lock_is_held())
                    self.assertFalse(archive.excl_lock_path.exists())

                records = list(archive.read_events())
                subjects = {r["subject"] for r in records if r.get("kind") == "decision"}
                self.assertEqual(subjects, {"unsupported-fs", "unsupported-fs-2"})
                result = archive.verify()
                self.assertTrue(result["valid"], result)

                # No instance-level latch exists any more (fix round 3).
                self.assertFalse(hasattr(archive, "_kernel_lock_unusable"))

    def test_other_errno_raises_promptly_and_leaves_no_excl_sidecar(self) -> None:
        """EIO (or ENOMEM, or anything outside both known errno families)
        is not a lock-semantics question at all - `write_lock` must raise
        `ArchiveError` immediately, loud, rather than guess which regime
        is safe, and must not leave a fallback sidecar behind from a call
        it never actually made.
        """
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()

                def _broken(fd: int) -> None:
                    raise OSError(errno.EIO, "input/output error")

                with mock.patch(
                    "godmode_runtime.godmode_chronicle._kernel_lock", side_effect=_broken
                ):
                    start = time.monotonic()
                    with self.assertRaises(ArchiveError):
                        archive.append("decision", "broken-fs", {"status": "active", "value": "x"})
                    elapsed = time.monotonic() - start
                # A lock-semantics bound: the old spin-then-misreport
                # behaviour for a non-contention errno took the full
                # timeout; a genuinely unrecoverable errno must raise
                # immediately instead.
                self.assertLess(elapsed, 5)
                self.assertFalse(archive.excl_lock_path.exists())
                self.assertEqual(archive.event_paths(), [])


if __name__ == "__main__":
    unittest.main()

"""Concurrent appends never fork the chain, and a dead writer does not block the next.

The lock was an O_EXCL sidecar with an age heuristic: a crashed writer
blocked every append for two minutes. A kernel advisory lock is released
when its holder dies.
"""
from __future__ import annotations

import contextlib
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


class LockOwnerVersionTests(unittest.TestCase):
    """Row 39 (limits-0.3.29.md #15): two Godmode runtime versions writing
    the same archive surfaced a version mismatch as plain "archive is busy"
    contention, sampled 197 times in the field with nothing to name what
    was actually different. The lock sidecar's diagnostic payload now
    carries the owning runtime version as a third line, and a timed-out
    acquire reads it back to tell "a different version holds this, by
    name" apart from ordinary same-version contention."""

    def test_the_payload_round_trips_the_current_runtime_version(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            path.write_text(C._lock_owner_payload(4242, 1234.5), encoding="utf-8")
            self.assertEqual(C._lock_owner_version(path), C.RUNTIME_VERSION)

    def test_a_two_line_payload_from_before_this_field_existed_reads_as_unknown(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            path.write_text("123\n456.0\n", encoding="utf-8")  # pre-row-39 shape
            self.assertIsNone(C._lock_owner_version(path))
            self.assertEqual(
                C._busy_message(path),
                "Godmode archive is busy; retry after the active write")

    def test_a_matching_version_gets_the_generic_busy_message(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            path.write_text(C._lock_owner_payload(1, 2.0), encoding="utf-8")
            self.assertEqual(
                C._busy_message(path),
                "Godmode archive is busy; retry after the active write")

    def test_a_differing_version_is_named_not_reported_as_plain_busy(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            path.write_text("1\n2.0\n0.0.1-not-real\n", encoding="utf-8")
            message = C._busy_message(path)
            self.assertIn("0.0.1-not-real", message)
            self.assertIn(C.RUNTIME_VERSION, message)
            self.assertNotIn("archive is busy", message)

    def test_a_lock_held_by_a_different_runtime_version_is_named_end_to_end(self) -> None:
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
                "from godmode_runtime import godmode_chronicle as C\n"
                "C.RUNTIME_VERSION = '0.0.1-simulated-old'\n"
                f"archive = C.Chronicle(resolve_anchor(Path({root!r})))\n"
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

                from godmode_runtime import godmode_chronicle as C
                with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                    archive = C.Chronicle(resolve_anchor(Path(root)))
                    with self.assertRaises(ArchiveError) as ctx:
                        with archive.write_lock(timeout_seconds=1.0):
                            pass
                    message = str(ctx.exception)
                    self.assertIn("0.0.1-simulated-old", message)
                    self.assertIn(C.RUNTIME_VERSION, message)
            finally:
                holder.kill()
                holder.wait(timeout=10)
                holder.stdout.close()


def _append_many(root: str, state: str, n: int, count: int) -> None:
    """A hook-shaped writer: pin the directory identity, read once, then
    append `count` records, retrying a plain busy timeout the way a caller
    would. Module-level so `multiprocessing` can pickle it under `spawn`."""
    os.environ["GODMODE_STATE_HOME"] = state
    archive = Chronicle(resolve_anchor(Path(root)))
    archive.pin_identity()
    archive.read_events(verify=False)
    for i in range(count):
        for _try in range(20):
            try:
                archive.append("action", "cooldown", {"anchor": f"w{n}-{i}"})
                break
            except ArchiveError as exc:
                if "busy" not in str(exc):
                    raise
        else:
            raise SystemExit(f"writer {n} starved at append {i}")


def _append_strict(root: str, state: str, n: int, count: int, busy) -> None:
    """A hook-shaped writer that never retries: every append must land
    within the default deadline. Busy timeouts are counted, not raised,
    so the parent reports how many writers were refused."""
    os.environ["GODMODE_STATE_HOME"] = state
    archive = Chronicle(resolve_anchor(Path(root)))
    archive.pin_identity()
    archive.read_events(verify=False)
    for i in range(count):
        try:
            archive.append("action", "cooldown", {"anchor": f"w{n}-{i}"})
        except ArchiveError as exc:
            if "busy" not in str(exc):
                raise
            with busy.get_lock():
                busy.value += 1


def _stale_writer_code(root: str) -> str:
    """A writer that dies between sealing its record and writing the head
    hint - the shape that leaves a lagging hint behind."""
    return (
        "import os, sys\n"
        f"sys.path.insert(0, {str(PLUGIN_ROOT / 'scripts')!r})\n"
        "from pathlib import Path\n"
        "from godmode_runtime.godmode_anchor import resolve_anchor\n"
        "from godmode_runtime.godmode_chronicle import Chronicle\n"
        f"archive = Chronicle(resolve_anchor(Path({root!r})))\n"
        "archive._write_head = lambda *a, **k: os._exit(9)\n"
        "archive.append('action', 'cooldown', {'anchor': 'first'})\n"
    )


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    return proc.pid


class NoDuplicateSequenceTests(unittest.TestCase):
    def _archive(self, root: str) -> Chronicle:
        archive = Chronicle(resolve_anchor(Path(root)))
        archive.initialize()
        return archive

    @staticmethod
    def _sequences(archive: Chronicle) -> list[int]:
        return sorted(int(path.name[:12]) for path in archive.event_paths())

    def test_20_writers_x_20_appends_one_contiguous_chain(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = self._archive(root)
                archive.append("claim", "seed", {"text": "x"})
                started = time.monotonic()
                procs = [multiprocessing.Process(target=_append_many, args=(root, state, n, 20))
                         for n in range(20)]
                for proc in procs:
                    proc.start()
                for proc in procs:
                    proc.join(120)
                print(f"20x20 wall time: {time.monotonic() - started:.2f}s", file=sys.stderr)
                for proc in procs:
                    self.assertEqual(proc.exitcode, 0, f"writer process failed: {proc}")
                self.assertEqual(self._sequences(archive), list(range(1, 402)))
                result = Chronicle(resolve_anchor(Path(root))).verify()
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["anchor"], "anchored")

    def test_24_writers_x_20_appends_none_refused_busy(self) -> None:
        """A fair lock: under 24 writers each appending 20 records, no
        append waits past the default deadline, and the chain is whole."""
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root,                 tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = self._archive(root)
                archive.append("claim", "seed", {"text": "x"})
                busy = multiprocessing.Value("i", 0)
                started = time.monotonic()
                procs = [multiprocessing.Process(
                    target=_append_strict, args=(root, state, n, 20, busy))
                    for n in range(24)]
                for proc in procs:
                    proc.start()
                for proc in procs:
                    proc.join(180)
                elapsed = time.monotonic() - started
                print(f"24x20 wall time: {elapsed:.2f}s, busy timeouts: {busy.value}",
                      file=sys.stderr)
                for proc in procs:
                    self.assertEqual(proc.exitcode, 0, f"writer process failed: {proc}")
                self.assertEqual(busy.value, 0)
                self.assertEqual(self._sequences(archive), list(range(1, 482)))
                result = Chronicle(resolve_anchor(Path(root))).verify()
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["anchor"], "anchored")
                # Fairness is `busy == 0` above; the wall bound only catches a
                # stall. 480 serialized appends take 60-150 s on a laptop whose
                # file scanner inspects every sealed record, so the bound is the
                # join deadline, not a throughput figure.
                self.assertLess(elapsed, 180)

    def test_pinned_writer_behind_a_lagging_head_hint_does_not_fork(self) -> None:
        """The field fork: a hook process pinned its directory identity, a
        second writer sealed a record and died before its head hint, and the
        hook's next append read the tail from its own pinned, stale list."""
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = self._archive(root)
                for n in range(3):
                    archive.append("claim", f"c{n}", {"text": "x"})
                hook = Chronicle(resolve_anchor(Path(root)))
                hook.pin_identity()
                hook.read_events()
                env = dict(os.environ, GODMODE_STATE_HOME=state)
                died = subprocess.run([sys.executable, "-c", _stale_writer_code(root)], env=env)
                self.assertEqual(died.returncode, 9)
                hook.append("action", "cooldown", {"anchor": "second"})
                self.assertEqual(self._sequences(archive), [1, 2, 3, 4, 5])
                self.assertTrue(Chronicle(resolve_anchor(Path(root))).verify()["ok"])

    def test_a_second_writer_of_a_sealed_sequence_is_refused(self) -> None:
        from godmode_runtime import godmode_chronicle as C
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = self._archive(root)
                first = archive.append("claim", "one", {"text": "x"})
                second = archive.append("claim", "two", {"text": "y"})
                with archive.write_lock():
                    # Either stale sequence - the tail itself, or one already
                    # buried under it - is refused before any file lands.
                    for sequence, previous in ((2, first["record_hash"]), (1, None)):
                        with self.assertRaises(C._SequenceTaken):
                            archive._write_record(
                                "claim", "stale", {"text": "z"}, [],
                                sequence=sequence, previous_hash=previous)
                self.assertEqual(self._sequences(archive), [1, 2])
                self.assertEqual(archive.read_events()[-1]["record_hash"], second["record_hash"])

    def test_an_abandoned_claim_is_cleared_and_a_live_one_refuses(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = self._archive(root)
                archive.append("claim", "one", {"text": "x"})
                claim = archive.sequence_claims / f"{2:012d}.claim"
                claim.write_text(f"{_dead_pid()}\nx\n", encoding="utf-8")
                archive.append("claim", "two", {"text": "y"})  # dead holder: cleared
                self.assertEqual(self._sequences(archive), [1, 2])
                sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                try:
                    (archive.sequence_claims / f"{3:012d}.claim").write_text(
                        f"{sleeper.pid}\nx\n", encoding="utf-8")
                    with self.assertRaises(ArchiveError) as ctx:
                        archive.append("claim", "three", {"text": "z"})
                    self.assertIn("claim", str(ctx.exception))
                    self.assertEqual(self._sequences(archive), [1, 2])
                finally:
                    sleeper.kill()
                    sleeper.wait(timeout=10)
                archive.append("claim", "three", {"text": "z"})
                self.assertEqual(self._sequences(archive), [1, 2, 3])
                self.assertTrue(archive.verify()["ok"])


class SlowHolderTests(unittest.TestCase):
    def test_a_slow_kernel_lock_holder_is_waited_on_never_overtaken(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            env = dict(os.environ, GODMODE_STATE_HOME=state)
            code = (
                "import sys, time\n"
                f"sys.path.insert(0, {str(PLUGIN_ROOT / 'scripts')!r})\n"
                "from pathlib import Path\n"
                "from godmode_runtime.godmode_anchor import resolve_anchor\n"
                "from godmode_runtime.godmode_chronicle import Chronicle\n"
                f"archive = Chronicle(resolve_anchor(Path({root!r})))\n"
                "archive.initialize()\n"
                "with archive.write_lock():\n"
                "    print('held', flush=True)\n"
                "    time.sleep(4)\n"
            )
            holder = subprocess.Popen(
                [sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, env=env)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "held")
                with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                    archive = Chronicle(resolve_anchor(Path(root)))
                    with self.assertRaises(ArchiveError):
                        with archive.write_lock(timeout_seconds=1.0):
                            self.fail("acquired a lock another process holds")
            finally:
                holder.wait(timeout=30)
                holder.stdout.close()
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.append("claim", "after", {"text": "x"})
                self.assertTrue(archive.verify()["ok"])

    def test_the_fallback_never_takes_over_from_a_live_holder_within_the_ceiling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()
                acquire = contextlib.contextmanager(archive._write_lock_exclusive_create)
                sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                try:
                    archive.excl_lock_path.write_text(
                        f"{sleeper.pid}\n0\nsame\n", encoding="utf-8")
                    old = time.time() - 20 * 60
                    os.utime(archive.excl_lock_path, (old, old))
                    with self.assertRaises(ArchiveError):
                        with acquire(1.0):
                            self.fail("took over a live holder's lock")
                    self.assertTrue(archive.excl_lock_path.exists())
                finally:
                    sleeper.kill()
                    sleeper.wait(timeout=10)
                # Holder dead: the takeover is allowed now, and release
                # removes only this acquirer's own sidecar.
                with acquire(2.0):
                    self.assertTrue(archive.excl_lock_path.read_text(
                        encoding="utf-8").startswith(f"{os.getpid()}\n"))
                self.assertFalse(archive.excl_lock_path.exists())

    def _fallback(self, root: str, state: str):
        archive = Chronicle(resolve_anchor(Path(root)))
        archive.initialize()
        return archive, contextlib.contextmanager(archive._write_lock_exclusive_create)

    def test_a_live_but_hung_holder_past_the_ceiling_is_taken_over(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive, acquire = self._fallback(root, state)
                # This test's own process: alive for certain.
                archive.excl_lock_path.write_text(
                    C._lock_owner_payload(os.getppid(), 0.0), encoding="utf-8")
                old = time.time() - C._EXCLUSIVE_CREATE_CEILING_SECONDS - 60
                os.utime(archive.excl_lock_path, (old, old))
                with acquire(2.0):
                    self.assertTrue(archive.excl_lock_path.read_text(
                        encoding="utf-8").startswith(f"{os.getpid()}\n"))

    def test_a_dead_pid_from_another_host_is_not_taken_over_within_the_ceiling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive, acquire = self._fallback(root, state)
                sleeper = subprocess.Popen([sys.executable, "-c", "pass"])
                sleeper.wait(timeout=30)
                archive.excl_lock_path.write_text(
                    f"{sleeper.pid}\n0\nsame\nsome-other-host\n", encoding="utf-8")
                old = time.time() - 10 * 60
                os.utime(archive.excl_lock_path, (old, old))
                with self.assertRaises(ArchiveError):
                    with acquire(1.0):
                        self.fail("took over a lock another host holds")
                self.assertIn("some-other-host",
                              archive.excl_lock_path.read_text(encoding="utf-8"))

    def test_the_lock_payload_records_this_host(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        payload = C._lock_owner_payload(4242, 1.0)
        self.assertEqual(C._lock_owner_host(payload), C._lock_host())

    def test_two_waiters_racing_an_abandoned_sidecar_yield_one_holder(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive, acquire = self._fallback(root, state)
                dead = subprocess.Popen([sys.executable, "-c", "pass"])
                dead.wait(timeout=30)
                archive.excl_lock_path.write_text(
                    C._lock_owner_payload(dead.pid, 0.0), encoding="utf-8")
                first_holds = threading.Event()
                judge = C.Chronicle._exclusive_lock_abandoned
                delayed: set[str] = set()

                def slow_second_judge(self_) -> bool:
                    verdict = judge(self_)
                    name = threading.current_thread().name
                    if name == "second" and name not in delayed:
                        # The second waiter judged the stale sidecar and is
                        # descheduled until the first has taken the lock.
                        delayed.add(name)
                        first_holds.wait(timeout=10)
                    return verdict

                inside, peak, guard = [0], [0], threading.Lock()
                errors: list[BaseException] = []

                def hold(pause: float) -> None:
                    try:
                        with acquire(15.0):
                            with guard:
                                inside[0] += 1
                                peak[0] = max(peak[0], inside[0])
                            first_holds.set()
                            time.sleep(pause)
                            with guard:
                                inside[0] -= 1
                    except BaseException as exc:  # noqa: BLE001
                        errors.append(exc)

                with mock.patch.object(C.Chronicle, "_exclusive_lock_abandoned",
                                       slow_second_judge):
                    second = threading.Thread(target=hold, args=(0.0,), name="second")
                    second.start()
                    time.sleep(0.2)
                    first = threading.Thread(target=hold, args=(1.0,), name="first")
                    first.start()
                    first.join(timeout=30)
                    second.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(peak[0], 1, "two writers held the fallback lock at once")

    def test_the_threat_model_states_when_the_fallback_lock_is_taken_over(self) -> None:
        from godmode_runtime import godmode_chronicle as C

        text = (PLUGIN_ROOT / "THREAT-MODEL.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| Archive fork"))
        self.assertNotIn("only from a holder whose process is gone", row)
        self.assertIn(f"{C._EXCLUSIVE_CREATE_CEILING_SECONDS // 60} minutes old", row)
        self.assertIn("another host", row)

    def test_release_leaves_a_sidecar_that_is_no_longer_its_own(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-lock-root-") as root, \
                tempfile.TemporaryDirectory(prefix="godmode-lock-state-") as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(Path(root)))
                archive.initialize()
                with contextlib.contextmanager(archive._write_lock_exclusive_create)(1.0):
                    archive.excl_lock_path.write_text("99999\n1\nother\n", encoding="utf-8")
                self.assertTrue(archive.excl_lock_path.exists())


if __name__ == "__main__":
    unittest.main()

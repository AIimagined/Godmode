"""The hook launcher finds its own root when the host leaves the variable empty.

One host runs hook strings under PowerShell where the plugin-root variable
is an empty PowerShell variable, and one launcher line then resolved to
"/hooks/...". The launcher must derive its root from its own location.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT / "hooks" / "run-hook.cmd"
LAUNCHER_SH = PLUGIN_ROOT / "hooks" / "run-hook.sh"
PROBE = "godmode_gate_fast.py"

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import scrubbed_env  # noqa: E402

def _posix_sh() -> str | None:
    """A POSIX `sh`: on PATH, or Git for Windows' bundled one beside
    git.exe (R-3a extension: the `.sh` sibling is proven the same way the
    `.cmd` half already is above, on whichever OS this suite runs on -
    Git Bash's `sh` is available on the Windows dev machine too)."""
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parent.parent / "usr" / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None

# A fake `py`/`GODMODE_PYTHON` recorder: it never runs the real hook - it
# just proves what arguments the launcher decided to invoke it with. Exits
# 0 unconditionally so the launcher's own `-c "import sys"` probe accepts
# it, and overwrites (not appends) its recording file each call, so after
# the launcher's two calls (the probe, then the real dispatch) the file
# holds only the last one - the real dispatch's argument list.
_RECORDER = '@echo off\r\necho %* > "{recorded}"\r\nexit /b 0\r\n'

# A cmd.exe that can still find `cmd`/`where`-class builtins but no
# interpreter: for the tests that must control exactly which `python`/`py`
# the launcher can see.
_SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")

# The same recorder, POSIX-shaped, for `run-hook.sh`'s probes
# (`command -v "$py" ... && "$py" -c "import sys"`, then the real
# dispatch) - LF-only, executable bit set by the caller.
_RECORDER_SH = "#!/bin/sh\nprintf '%s' \"$*\" > \"{recorded}\"\nexit 0\n"

# A fake interpreter for the cache tests: it appends every call to a log
# and, asked to run code (`-c`), prints its own path the way the real
# probe's `sys.stdout.write(sys.executable)` does.
_SELF_REPORTING_SH = ("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"{log}\"\n"
                      "case \"$1\" in -c) printf '%s' \"{self}\" ;; esac\nexit 0\n")


class LauncherTests(unittest.TestCase):
    def _env(self) -> dict:
        # Fix round 2 (NS-10k, task-14-rereview.md B1): this was
        # `dict(os.environ)` - the whole runner environment, `CI` included -
        # minus two plugin-root keys. Every payload here is R4/R5 tier
        # ("rm -rf build", "git push --force origin main"), so a CI runner's
        # ambient `CI=true` flips the launcher's decision from `ask` onto
        # the unattended `deny` row and this module's assertions with it.
        # `scrubbed_env()` strips every host marker and ambient attendance
        # signal and pins `GODMODE_ATTENDED=1`, the same row every other
        # gate test in this repo runs from.
        env = scrubbed_env()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("PLUGIN_ROOT", None)
        # Isolated from this machine's own interpreter cache.
        home = tempfile.mkdtemp(prefix="gm-launcher-home-")
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        env["GODMODE_STATE_HOME"] = home
        return env

    @unittest.skipIf(os.name == "nt", "POSIX half")
    def test_posix_root_without_variable(self) -> None:
        payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
        proc = subprocess.run(["sh", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                              cwd=LAUNCHER.parent.parent, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_root_without_variable(self) -> None:
        # `returncode == 0` alone does not pin this: the launcher's own
        # "no working python interpreter found" fail-open path also exits 0
        # and would pass silently even if the root/interpreter resolution
        # broke. A protected command (never actually executed - this is a
        # PreToolUse *decision*, the same shape every other gate test in
        # this repo drives) forces the real gate chain to answer with a
        # concrete, parseable decision envelope that the fail-open path
        # never produces - proof the launcher found its root, found a
        # working interpreter, and ran the real hook, not just "exited 0".
        payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"rm -rf build"}}'
        proc = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                              cwd=LAUNCHER.parent.parent, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("no working python interpreter", proc.stdout)
        body = json.loads(proc.stdout.strip())
        self.assertIn("hookSpecificOutput", body)
        self.assertEqual(body["hookSpecificOutput"].get("permissionDecision"), "ask")

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_deny_exit_code_passes_through(self) -> None:
        # Read against `hooks/godmode_session_hook.py` (the full hook the
        # launcher escalates to for this payload): a detected host's deny
        # rides `render_decision`, which is exit 0 with a JSON body for
        # EVERY decision including "deny" - Claude's own documented
        # contract reads the decision from `permissionDecision`, never
        # from the exit code. Exit 2 for a deny is the DIFFERENT,
        # undetected-host fallback path (`print(json.dumps(preview))`,
        # then `return 2`), which this payload - run with the real
        # process environment, so the host detects as "claude" - never
        # takes. The launcher must pass the real exit code through either
        # way; pin the one this payload actually produces, from the exact
        # parsed field, not a substring of the reason text.
        payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}'
        proc = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                              cwd=LAUNCHER.parent.parent, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout.strip())
        self.assertEqual(body["hookSpecificOutput"].get("permissionDecision"), "deny", body)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_uses_py_launcher_with_3_flag_when_no_python(self) -> None:
        """With no `python` on PATH, `py` is invoked as `py -3` - pinned by
        recording the exact argv the launcher hands it, not just observing
        that *some* interpreter ran. PATH is only the fake directory and
        System32, so no real interpreter can answer first."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            recorded = fake_dir / "recorded.txt"
            (fake_dir / "py.cmd").write_text(_RECORDER.format(recorded=recorded), encoding="utf-8")
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(fake_dir / "state")
            env["PATH"] = str(fake_dir) + os.pathsep + _SYSTEM32
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                           cwd=LAUNCHER.parent.parent, env=env)
            self.assertTrue(recorded.exists(), "the fake py launcher was never invoked")
            args = recorded.read_text(encoding="utf-8").strip()
        self.assertTrue(args.startswith("-3 -I -B"), args)
        self.assertTrue(args.rstrip().endswith(PROBE + '"'), args)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_prefers_python_over_py(self) -> None:
        """Field report 2026-09-23: `py -3` is one more process per call;
        `python` answers first when it is a real interpreter."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            recorded_python = fake_dir / "recorded_python.txt"
            recorded_py = fake_dir / "recorded_py.txt"
            (fake_dir / "python.cmd").write_text(_RECORDER.format(recorded=recorded_python), encoding="utf-8")
            (fake_dir / "py.cmd").write_text(_RECORDER.format(recorded=recorded_py), encoding="utf-8")
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(fake_dir / "state")
            env["PATH"] = str(fake_dir) + os.pathsep + _SYSTEM32
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                           cwd=LAUNCHER.parent.parent, env=env)
            self.assertTrue(recorded_python.exists(), "python was never invoked")
            self.assertFalse(recorded_py.exists(), "py was tried although python answered")
            args = recorded_python.read_text(encoding="utf-8").strip()
        self.assertTrue(args.startswith("-I -B"), args)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_skips_a_windowsapps_python_for_py(self) -> None:
        """A `python` that resolves into WindowsApps (the Store alias, slow
        to activate) is passed over while anything else answers."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            alias_dir = fake_dir / "WindowsApps"
            alias_dir.mkdir()
            recorded_alias = fake_dir / "recorded_alias.txt"
            recorded_py = fake_dir / "recorded_py.txt"
            (alias_dir / "python.cmd").write_text(_RECORDER.format(recorded=recorded_alias), encoding="utf-8")
            (fake_dir / "py.cmd").write_text(_RECORDER.format(recorded=recorded_py), encoding="utf-8")
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(fake_dir / "state")
            env["PATH"] = str(alias_dir) + os.pathsep + str(fake_dir) + os.pathsep + _SYSTEM32
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                           cwd=LAUNCHER.parent.parent, env=env)
            self.assertTrue(recorded_py.exists(), "py was never invoked")
            self.assertFalse(recorded_alias.exists(), "the WindowsApps python was tried first")

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_caches_the_resolved_interpreter_and_skips_the_probe(self) -> None:
        """The first call records the interpreter's absolute path; a later
        call runs it with no probe, even with a recorder first on PATH."""
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            home = base / "state"
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(home)
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + _SYSTEM32
            # A bare temp project, never this repository: the real hook runs.
            payload = json.dumps({"hook_event_name": "PreToolUse", "cwd": str(base), "tool_name": "Bash",
                                  "tool_input": {"command": "echo hi"}})
            first = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                                   text=True, cwd=LAUNCHER.parent.parent, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotIn("no working python", first.stdout)
            cache = home / "launcher-python-cmd"
            self.assertEqual(Path(cache.read_text(encoding="utf-8").strip()).resolve(),
                             Path(sys.executable).resolve())
            fake_dir = base / "fake"
            fake_dir.mkdir()
            recorded = fake_dir / "recorded.txt"
            (fake_dir / "python.cmd").write_text(_RECORDER.format(recorded=recorded), encoding="utf-8")
            env["PATH"] = str(fake_dir) + os.pathsep + env["PATH"]
            second = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                                    text=True, cwd=LAUNCHER.parent.parent, env=env)
            self.assertFalse(recorded.exists(), "a cache hit still probed PATH")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotIn("no working python", second.stdout)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_a_non_ascii_interpreter_path_still_reaches_a_cache_hit(self) -> None:
        """Review 2026-09-23 (F1): the probe's `sys.executable` comes back
        through a pipe in Python's encoding and is read in the console code
        page, so a path with a non-ASCII character never passed `if exist`,
        nothing was cached, and every call paid three interpreter starts.
        A venv under a non-ASCII directory, the shape of a python.org
        per-user install under a non-ASCII account name: the first call
        must leave a cache entry, and the second must run the interpreter
        exactly once, with no probe."""
        base = Path(tempfile.mkdtemp(prefix="gm-\u00fc\u00f1\u00e9-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(base / "venv")],
                       check=True, capture_output=True, timeout=300)
        project = base / "project"
        project.mkdir()
        home = base / "state"
        env = self._env()
        env.pop("GODMODE_PYTHON", None)
        env["GODMODE_STATE_HOME"] = str(home)
        env["PATH"] = str(base / "venv" / "Scripts") + os.pathsep + _SYSTEM32
        payload = json.dumps({"hook_event_name": "PreToolUse", "cwd": str(project), "tool_name": "Bash",
                              "tool_input": {"command": "echo hi"}})
        first = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                               text=True, cwd=LAUNCHER.parent.parent, env=env, timeout=120)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotIn("no working python", first.stdout)
        cache = home / "launcher-python-cmd"
        self.assertTrue(cache.is_file(), "a non-ASCII interpreter path left no cache entry")

        # Second call: the only `python` on PATH is a recorder that appends
        # every invocation. A cache hit runs it once (the dispatch); a probe
        # would run it two or three times.
        # ASCII on purpose: cmd reads a batch file's own text in the console
        # code page, so the recorder's log path must survive that.
        fake_dir = Path(tempfile.mkdtemp(prefix="gm-recorder-"))
        self.addCleanup(shutil.rmtree, fake_dir, ignore_errors=True)
        recorded = fake_dir / "calls.txt"
        (fake_dir / "python.cmd").write_text(
            f'@echo off\r\necho %* >> "{recorded}"\r\nexit /b 0\r\n', encoding="utf-8")
        entry = cache.read_text(encoding="utf-8").strip()
        if not entry.startswith("@"):
            self.skipTest(f"this machine read the path back ({entry!r}); nothing to prove here")
        env["PATH"] = str(fake_dir) + os.pathsep + _SYSTEM32
        subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                       text=True, cwd=LAUNCHER.parent.parent, env=env, timeout=120)
        calls = recorded.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1, calls)
        self.assertTrue(calls[0].startswith("-I -B"), calls)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_an_unwritable_state_home_says_nothing(self) -> None:
        """Review nit N1: a state home the cache cannot be written to (here,
        a file) left a "cannot find the path" line on stderr every call."""
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "not-a-directory"
            home.write_text("x", encoding="utf-8")
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(home)
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + _SYSTEM32
            payload = json.dumps({"hook_event_name": "PreToolUse", "cwd": temp, "tool_name": "Bash",
                                  "tool_input": {"command": "echo hi"}})
            done = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                                  text=True, cwd=LAUNCHER.parent.parent, env=env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr.strip(), "")

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_stale_cache_falls_back_to_the_probe_and_is_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "state"
            home.mkdir()
            cache = home / "launcher-python-cmd"
            cache.write_text(str(Path(temp) / "gone" / "python.exe") + "\n", encoding="utf-8")
            env = self._env()
            env.pop("GODMODE_PYTHON", None)
            env["GODMODE_STATE_HOME"] = str(home)
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + _SYSTEM32
            payload = json.dumps({"hook_event_name": "PreToolUse", "cwd": temp, "tool_name": "Bash",
                                  "tool_input": {"command": "echo hi"}})
            done = subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True,
                                  text=True, cwd=LAUNCHER.parent.parent, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("no working python", done.stdout)
            self.assertEqual(Path(cache.read_text(encoding="utf-8").strip()).resolve(),
                             Path(sys.executable).resolve())

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_session_events_enter_through_the_front_door(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            recorded = Path(temp) / "recorded.txt"
            fake_python = Path(temp) / "fake_python.cmd"
            fake_python.write_text(_RECORDER.format(recorded=recorded), encoding="utf-8")
            env = self._env()
            env["GODMODE_PYTHON"] = str(fake_python)
            subprocess.run(["cmd", "/c", str(LAUNCHER), "godmode_session_hook.py", "stop"], input="{}",
                           capture_output=True, text=True, cwd=LAUNCHER.parent.parent, env=env)
            args = recorded.read_text(encoding="utf-8").strip()
        self.assertIn('godmode_session_entry.py" stop', args)

    @unittest.skipUnless(os.name == "nt", "cmd half")
    def test_windows_godmode_python_gets_no_3_flag(self) -> None:
        """GODMODE_PYTHON names an exact interpreter, not the `py` launcher
        - it must never be handed `-3`, which `py` alone would reject in
        reverse (`-3` before other flags) or a plain `python.exe` would
        reject outright."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            recorded = fake_dir / "recorded.txt"
            fake_python = fake_dir / "fake_python.cmd"
            fake_python.write_text(_RECORDER.format(recorded=recorded), encoding="utf-8")
            env = self._env()
            env["GODMODE_PYTHON"] = str(fake_python)
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            subprocess.run(["cmd", "/c", str(LAUNCHER), PROBE], input=payload, capture_output=True, text=True,
                           cwd=LAUNCHER.parent.parent, env=env)
            self.assertTrue(recorded.exists(), "GODMODE_PYTHON was never invoked")
            args = recorded.read_text(encoding="utf-8").strip()
        self.assertTrue(args.startswith("-I -B"), args)
        self.assertFalse(args.startswith("-3"), args)


class ShLauncherTests(unittest.TestCase):
    """R-3a extension: `hooks/run-hook.sh`'s root resolution and interpreter
    probe survive the identical corpus rows the `.cmd` half is pinned
    against above - unexpanded `${CLAUDE_PLUGIN_ROOT}`/`${PLUGIN_ROOT}`
    still finds root, a deny's exit code passes through, `GODMODE_PYTHON`
    is honored, and the probe order (`python3` before `python`/`py`) is the
    one this launcher actually runs, not merely observed to work."""

    def setUp(self) -> None:
        sh = _posix_sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        self.sh = sh

    def _env(self) -> dict:
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("PLUGIN_ROOT", None)
        env.pop("GODMODE_PYTHON", None)
        # The interpreter cache lives in the application home; a test that
        # puts recorders on PATH must not be answered by this machine's own.
        home = tempfile.mkdtemp(prefix="gm-launcher-home-")
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        env["GODMODE_STATE_HOME"] = home
        return env

    def _run(self, payload: str, env: dict) -> subprocess.CompletedProcess:
        # `.as_posix()`: these tests drive real hook dispatch end to end and
        # want root resolution to succeed unconditionally, independent of
        # which `case` branch fires (see tests/test_launcher_pair.py for the
        # same note against its own end-to-end run). The backslash branch
        # (`*\\*`) is pinned on its own below, with a genuine
        # backslash-bearing `$0`, by BackslashRootGuardTests (task-3 review
        # B1).
        return subprocess.run(
            [self.sh, LAUNCHER_SH.as_posix(), PROBE], input=payload,
            capture_output=True, text=True, cwd=LAUNCHER_SH.parent.parent, env=env)

    def test_root_without_variable_still_answers_a_concrete_decision(self) -> None:
        # Same corpus row and the same reasoning as the cmd half's own
        # `test_windows_root_without_variable`: a bare `returncode == 0`
        # does not pin this, because the launcher's fail-open "no working
        # python interpreter" path also exits 0. This command forces the
        # real gate chain to answer with a parseable decision envelope,
        # proof the launcher found its root, found a working interpreter,
        # and ran the real hook.
        payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"rm -rf build"}}'
        proc = self._run(payload, self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("no working python interpreter", proc.stdout)
        body = json.loads(proc.stdout.strip())
        self.assertIn("hookSpecificOutput", body)
        self.assertEqual(body["hookSpecificOutput"].get("permissionDecision"), "ask")

    def test_deny_exit_code_passes_through(self) -> None:
        payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}'
        proc = self._run(payload, self._env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout.strip())
        self.assertEqual(body["hookSpecificOutput"].get("permissionDecision"), "deny", body)

    def test_probe_order_is_the_platforms(self) -> None:
        """The probe order picks the first match on PATH: `python3` first
        on POSIX, `python` first on Windows (field report 2026-09-23: there
        `python3` is most often the Store alias) - pinned by proving the
        preferred recorder fired and the other never did, not just that
        *some* interpreter ran. Windows is read the way the launcher reads
        it, from the environment (Git Bash always sets MSYSTEM)."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            recorded3 = fake_dir / "recorded3.txt"
            recorded_py = fake_dir / "recorded_python.txt"
            for name, recorded in (("python3", recorded3), ("python", recorded_py)):
                target = fake_dir / name
                target.write_text(_RECORDER_SH.format(recorded=recorded.as_posix()),
                                  encoding="utf-8", newline="\n")
                os.chmod(target, 0o755)
            env = self._env()
            env["PATH"] = str(fake_dir) + os.pathsep + env.get("PATH", "")
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            self._run(payload, env)
            windows = os.name == "nt"
            preferred, other = (recorded_py, recorded3) if windows else (recorded3, recorded_py)
            self.assertTrue(preferred.exists(), f"{preferred.name} recorder was never invoked")
            self.assertFalse(other.exists(), f"{other.name} was tried although the preferred one answered")
            args = preferred.read_text(encoding="utf-8").strip()
        self.assertTrue(args.startswith("-I -B"), args)
        self.assertTrue(args.rstrip().endswith(PROBE), args)

    @unittest.skipUnless(os.name == "nt", "the Store alias exists only on Windows")
    def test_a_windowsapps_candidate_is_tried_last(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            alias_dir = fake_dir / "WindowsApps"
            alias_dir.mkdir()
            recorded_alias = fake_dir / "recorded_alias.txt"
            recorded_py = fake_dir / "recorded_py.txt"
            for target, recorded in ((alias_dir / "python", recorded_alias), (fake_dir / "py", recorded_py)):
                target.write_text(_RECORDER_SH.format(recorded=recorded.as_posix()),
                                  encoding="utf-8", newline="\n")
                os.chmod(target, 0o755)
            env = self._env()
            env["PATH"] = os.pathsep.join((str(alias_dir), str(fake_dir), env.get("PATH", "")))
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            self._run(payload, env)
            self.assertTrue(recorded_py.exists(), "py was never invoked")
            self.assertFalse(recorded_alias.exists(), "the WindowsApps python was tried first")

    def test_the_resolved_interpreter_is_cached_and_the_probe_skipped(self) -> None:
        """Field report 2026-09-23: every call started an interpreter twice.
        The first call probes and records the interpreter's own path; the
        next call execs that path directly - one line in the fake's log,
        not two - and a cached path that is gone sends it back to the probe,
        which rewrites the cache."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            log = fake_dir / "calls.log"
            name = "python" if os.name == "nt" else "python3"
            fake = fake_dir / name
            fake.write_text(_SELF_REPORTING_SH.format(log=log.as_posix(), self=fake.as_posix()),
                            encoding="utf-8", newline="\n")
            os.chmod(fake, 0o755)
            env = self._env()
            env["PATH"] = str(fake_dir) + os.pathsep + env.get("PATH", "")
            cache = Path(env["GODMODE_STATE_HOME"]) / "launcher-python-sh"
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'

            self._run(payload, env)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 2, calls)  # the probe, then the run
            self.assertTrue(calls[0].startswith("-c "), calls)
            self.assertTrue(calls[1].startswith("-I -B"), calls)
            self.assertEqual(cache.read_text(encoding="utf-8").strip(), fake.as_posix())

            self._run(payload, env)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 3, calls)  # the run alone
            self.assertTrue(calls[2].startswith("-I -B") and calls[2].endswith(PROBE), calls)

            cache.write_text((fake_dir / "gone" / name).as_posix() + "\n", encoding="utf-8")
            self._run(payload, env)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 5, calls)  # probed again
            self.assertEqual(cache.read_text(encoding="utf-8").strip(), fake.as_posix())

    def test_session_events_enter_through_the_front_door(self) -> None:
        """`godmode_session_hook.py` is dispatched as
        `godmode_session_entry.py`, which answers a project with no Godmode
        state before the 5,000-line hook is compiled (2026-09-23)."""
        with tempfile.TemporaryDirectory() as temp:
            recorded = Path(temp) / "recorded.txt"
            fake = Path(temp) / "fake_python.sh"
            fake.write_text(_RECORDER_SH.format(recorded=recorded.as_posix()),
                            encoding="utf-8", newline="\n")
            os.chmod(fake, 0o755)
            env = self._env()
            env["GODMODE_PYTHON"] = fake.as_posix()
            subprocess.run([self.sh, LAUNCHER_SH.as_posix(), "godmode_session_hook.py", "stop"],
                           input="{}", capture_output=True, text=True,
                           cwd=LAUNCHER_SH.parent.parent, env=env, timeout=60)
            args = recorded.read_text(encoding="utf-8").strip()
        self.assertTrue(args.endswith("/godmode_session_entry.py stop"), args)

    def test_a_cached_path_not_named_like_an_interpreter_is_ignored(self) -> None:
        """Review 2026-09-23 (H1): the sh half exec'd whatever the cache
        named - a planted cmd.exe ran and the hook silently never did. A
        cached name that is not python, python3, pythonX.Y, pythonw or py
        (with or without .exe) is ignored and the probe runs."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            planted_log = fake_dir / "planted.log"
            planted = fake_dir / "not-an-interpreter"
            planted.write_text(_SELF_REPORTING_SH.format(log=planted_log.as_posix(), self=planted.as_posix()),
                               encoding="utf-8", newline="\n")
            os.chmod(planted, 0o755)
            name = "python" if os.name == "nt" else "python3"
            log = fake_dir / "python.log"
            fake = fake_dir / name
            fake.write_text(_SELF_REPORTING_SH.format(log=log.as_posix(), self=fake.as_posix()),
                            encoding="utf-8", newline="\n")
            os.chmod(fake, 0o755)
            env = self._env()
            env["PATH"] = str(fake_dir) + os.pathsep + env.get("PATH", "")
            (Path(env["GODMODE_STATE_HOME"]) / "launcher-python-sh").write_text(
                planted.as_posix() + "\n", encoding="utf-8", newline="\n")
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            self._run(payload, env)
            self.assertFalse(planted_log.exists(), "the planted cache entry was executed")
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertTrue(calls and calls[-1].startswith("-I -B"), calls)

    def test_godmode_python_outranks_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            log = fake_dir / "cached.log"
            cached = fake_dir / "cached_python"
            cached.write_text(_SELF_REPORTING_SH.format(log=log.as_posix(), self=cached.as_posix()),
                              encoding="utf-8", newline="\n")
            os.chmod(cached, 0o755)
            recorded = fake_dir / "recorded_override.txt"
            override = fake_dir / "override_python"
            override.write_text(_RECORDER_SH.format(recorded=recorded.as_posix()),
                                encoding="utf-8", newline="\n")
            os.chmod(override, 0o755)
            env = self._env()
            (Path(env["GODMODE_STATE_HOME"]) / "launcher-python-sh").write_text(
                cached.as_posix() + "\n", encoding="utf-8")
            env["GODMODE_PYTHON"] = override.as_posix()
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            self._run(payload, env)
            self.assertTrue(recorded.exists(), "GODMODE_PYTHON was never invoked")
            self.assertFalse(log.exists(), "the cached interpreter ran despite GODMODE_PYTHON")

    def test_godmode_python_overrides_the_path_probe_entirely(self) -> None:
        """`GODMODE_PYTHON` is tried before any PATH probe at all - a fake
        `python3` sitting on PATH must never fire once it is set."""
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            recorded_override = fake_dir / "recorded_override.txt"
            recorded_path = fake_dir / "recorded_path.txt"
            godmode_python = fake_dir / "fake_python.sh"
            godmode_python.write_text(_RECORDER_SH.format(recorded=recorded_override.as_posix()),
                                      encoding="utf-8", newline="\n")
            os.chmod(godmode_python, 0o755)
            path_python3 = fake_dir / "python3"
            path_python3.write_text(_RECORDER_SH.format(recorded=recorded_path.as_posix()),
                                    encoding="utf-8", newline="\n")
            os.chmod(path_python3, 0o755)
            env = self._env()
            env["GODMODE_PYTHON"] = godmode_python.as_posix()
            env["PATH"] = str(fake_dir) + os.pathsep + env.get("PATH", "")
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            self._run(payload, env)
            self.assertTrue(recorded_override.exists(), "GODMODE_PYTHON was never invoked")
            self.assertFalse(recorded_path.exists(), "the PATH probe fired despite GODMODE_PYTHON")
            args = recorded_override.read_text(encoding="utf-8").strip()
        self.assertTrue(args.startswith("-I -B"), args)
        self.assertTrue(args.rstrip().endswith(PROBE), args)


class BackslashRootGuardTests(unittest.TestCase):
    """B1 (task-3-review.md): `hooks/run-hook.sh`'s root-resolution `case`
    must strip a backslash-separated `$0` - the shape a host wiring this
    launcher through Git Bash on Windows actually hands it. The regression
    the review found (`*\\*`, an escaped asterisk) is a no-op against a
    backslash path, not the escaped-backslash `*\\\\*` the polyglot's sh
    half carries: `dir` falls through unstripped to
    `[ "$dir" = "$0" ] && dir=.`, and the hook is then looked up relative to
    the CALLER's cwd instead of the launcher's own directory.

    Proven two ways below: unconditionally, by pinning the exact bytes of
    the generated pattern (no shell required); and end-to-end, with a real
    backslash-bearing `$0` (not a synthesized string) and a recording
    `GODMODE_PYTHON` that reveals which directory the launcher actually
    resolved. On this dev machine both `sh` and `dash` match a literal
    backslash against `*\\\\*` correctly once the pattern is written with
    two real backslash characters - the "MSYS quirk"
    task-3-review.md reports reproducing turned out here to be an artifact
    of how that probe script was authored (a `cat <<'EOF'` heredoc that
    silently halved backslash runs before the file ever reached a shell),
    not a shell limitation; task-3-report-round1.md has the isolated
    before/after repro.
    """

    def test_generated_sh_carries_the_escaped_backslash_pattern(self) -> None:
        content = LAUNCHER_SH.read_text(encoding="utf-8")
        self.assertIn('case "$dir" in *\\\\*) dir=${dir%\\\\*} ;; esac', content)
        # The regression this guards against: an escaped ASTERISK matches a
        # literal `*`, not a backslash - assert the narrower, wrong pattern
        # did not come back.
        self.assertNotIn('case "$dir" in *\\*) dir=${dir%\\*} ;; esac', content)

    def test_backslash_dollar_zero_resolves_the_launchers_own_directory(self) -> None:
        sh = _posix_sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        if os.name != "nt":
            self.skipTest("a backslash-only $0 only arises naturally on Windows")

        with tempfile.TemporaryDirectory() as launcher_dir, tempfile.TemporaryDirectory() as cwd_dir:
            launcher_dir_p = Path(launcher_dir)
            launcher_copy = launcher_dir_p / "run-hook.sh"
            launcher_copy.write_bytes(LAUNCHER_SH.read_bytes())
            os.chmod(launcher_copy, 0o755)

            recorded = launcher_dir_p / "recorded.txt"
            godmode_python = launcher_dir_p / "fake_python.sh"
            godmode_python.write_text(_RECORDER_SH.format(recorded=recorded.as_posix()),
                                      encoding="utf-8", newline="\n")
            os.chmod(godmode_python, 0o755)

            # Windows-native, backslash-only path - no forward slash at all
            # - the exact shape a host wiring this launcher through Git Bash
            # on Windows hands it as `$0`.
            backslash_path = str(launcher_copy)
            self.assertIn("\\", backslash_path)
            self.assertNotIn("/", backslash_path)

            # Ground truth for "the launcher's own directory, in whatever
            # form this sh's `cd`/`pwd` renders it" - computed with the same
            # `sh`, so the assertion below does not have to guess at MSYS's
            # own path-mapping rules (e.g. a Temp directory living under a
            # `/tmp` mount).
            expected = subprocess.run(
                [sh, "-c", 'cd -- "$1" && pwd', "_", str(launcher_dir_p)],
                capture_output=True, text=True).stdout.strip()
            self.assertTrue(expected, "could not resolve the ground-truth directory")

            env = dict(os.environ)
            env.pop("CLAUDE_PLUGIN_ROOT", None)
            env.pop("PLUGIN_ROOT", None)
            env["GODMODE_PYTHON"] = godmode_python.as_posix()
            payload = '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"echo hi"}}'
            subprocess.run([sh, backslash_path, "some_hook.py"], input=payload,
                           capture_output=True, text=True, cwd=cwd_dir, env=env, timeout=60)
            self.assertTrue(recorded.exists(), "GODMODE_PYTHON was never invoked")
            args = recorded.read_text(encoding="utf-8").strip()

        # If the guard were a no-op (the B1 bug), `dir` falls through to
        # `.` and the hook is resolved against `cwd_dir`, not `expected`.
        self.assertTrue(args.endswith(expected + "/some_hook.py"), args)


if __name__ == "__main__":
    unittest.main()

"""Password approval inside the session: `authorize stage` without a terminal
opens a native password dialog, and the password never leaves this process
through argv, the environment or the chat."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = PLUGIN_ROOT / "tests"
for entry in (SCRIPTS, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime import godmode_passdialog as passdialog  # noqa: E402
from godmode_runtime import godmode_sentinel as sentinel  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, classify_action  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery"
OPERATION = "git reset --hard HEAD~1"


class _FakeProcess:
    def __init__(self, out: bytes, code: int, err: bytes = b"") -> None:
        self.stdout = io.BytesIO(out)
        self.stderr = io.BytesIO(err)
        self._code = code

    def wait(self) -> int:
        return self._code


def _popen_returning(out: bytes, code: int = 0, err: bytes = b""):
    return mock.patch.object(passdialog.subprocess, "Popen",
                             return_value=_FakeProcess(out, code, err))


class BackendSelectionTests(unittest.TestCase):
    def test_windows_uses_the_in_process_credential_prompt(self) -> None:
        self.assertEqual(passdialog.select_backend("win32", {}, lambda _p: False),
                         ("windows-credui", None))

    def test_macos_uses_osascript_from_the_system_directory(self) -> None:
        found = passdialog.select_backend("darwin", {}, lambda p: p == "/usr/bin/osascript")
        self.assertEqual(found, ("osascript", "/usr/bin/osascript"))

    def test_macos_without_osascript_has_no_dialog(self) -> None:
        self.assertIsNone(passdialog.select_backend("darwin", {}, lambda _p: False))

    def test_linux_prefers_zenity_then_kdialog(self) -> None:
        env = {"DISPLAY": ":0"}
        self.assertEqual(passdialog.select_backend("linux", env, lambda _p: True),
                         ("zenity", "/usr/bin/zenity"))
        self.assertEqual(
            passdialog.select_backend("linux", {"WAYLAND_DISPLAY": "w"}, lambda p: p == "/bin/kdialog"),
            ("kdialog", "/bin/kdialog"))

    def test_linux_without_a_desktop_has_no_dialog(self) -> None:
        self.assertIsNone(passdialog.select_backend("linux", {}, lambda _p: True))

    def test_dialog_programs_are_never_looked_up_on_path(self) -> None:
        seen: list[str] = []
        passdialog.select_backend("linux", {"DISPLAY": ":0", "PATH": "/evil"},
                                  lambda p: seen.append(p) or False)
        self.assertTrue(seen)
        self.assertTrue(all(p.startswith(("/usr/bin/", "/bin/")) for p in seen), seen)


class PipeDialogTests(unittest.TestCase):
    MESSAGE = passdialog.approval_message(OPERATION, 300, "ab" * 32)

    def _ask(self, backend, out: bytes, code: int = 0, err: bytes = b""):
        with _popen_returning(out, code, err) as popen:
            result = passdialog.ask_password(self.MESSAGE, backend)
        return result, popen

    def test_each_pipe_backend_returns_the_typed_password(self) -> None:
        for backend in (("osascript", "/usr/bin/osascript"), ("zenity", "/usr/bin/zenity"),
                        ("kdialog", "/usr/bin/kdialog")):
            result, _popen = self._ask(backend, (PASSWORD + "\n").encode())
            self.assertEqual(result, PASSWORD, backend)

    def test_the_password_is_never_in_argv_env_or_stdin_of_the_dialog(self) -> None:
        for backend in (("osascript", "/usr/bin/osascript"), ("zenity", "/usr/bin/zenity"),
                        ("kdialog", "/usr/bin/kdialog")):
            _result, popen = self._ask(backend, (PASSWORD + "\n").encode())
            args, kwargs = popen.call_args
            self.assertNotIn(PASSWORD, json.dumps([list(args), repr(kwargs)]), backend)
            self.assertNotIn("env", kwargs)
            self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
            self.assertIs(kwargs["stdout"], subprocess.PIPE)
            self.assertNotIn(PASSWORD, os.environ.values())

    def test_the_dialog_shows_the_exact_command_and_its_scope(self) -> None:
        for backend in (("osascript", "/usr/bin/osascript"), ("kdialog", "/usr/bin/kdialog")):
            _result, popen = self._ask(backend, b"x\n")
            shown = " ".join(popen.call_args[0][0])
            self.assertIn(OPERATION, shown)
            self.assertIn("one use", shown)
            self.assertIn("expires in 300 seconds", shown)

    def test_cancel_returns_none(self) -> None:
        self.assertIsNone(self._ask(("osascript", "/usr/bin/osascript"), b"", 1,
                                    b"execution error: User canceled. (-128)")[0])
        self.assertIsNone(self._ask(("zenity", "/usr/bin/zenity"), b"", 1)[0])
        self.assertIsNone(self._ask(("kdialog", "/usr/bin/kdialog"), b"", 1)[0])

    def test_a_dialog_that_cannot_show_is_unavailable_not_cancelled(self) -> None:
        with self.assertRaises(passdialog.DialogUnavailable):
            self._ask(("osascript", "/usr/bin/osascript"), b"", 1, b"no user interaction allowed")
        with self.assertRaises(passdialog.DialogUnavailable):
            self._ask(("zenity", "/usr/bin/zenity"), b"", 255)

    def test_no_backend_is_unavailable(self) -> None:
        with mock.patch.object(passdialog, "select_backend", return_value=None):
            with self.assertRaises(passdialog.DialogUnavailable):
                passdialog.ask_password(self.MESSAGE)

    def test_windows_goes_to_the_in_process_prompt_without_a_child_process(self) -> None:
        with mock.patch.object(passdialog, "_windows_credui", return_value=PASSWORD) as prompt, \
                mock.patch.object(passdialog.subprocess, "Popen") as popen:
            self.assertEqual(passdialog.ask_password(self.MESSAGE, ("windows-credui", None)), PASSWORD)
        prompt.assert_called_once_with(self.MESSAGE)
        popen.assert_not_called()


@contextlib.contextmanager
def _no_terminal(answer=None, unavailable: bool = False):
    """No TTY; the dialog is mocked to return `answer` (None = cancel)."""
    def fake(message, backend=None):
        fake.messages.append(message)
        if unavailable:
            raise passdialog.DialogUnavailable("none")
        return answer
    fake.messages = []
    with mock.patch.object(sentinel, "_stdin_is_interactive", return_value=False), \
            mock.patch.object(passdialog, "ask_password", side_effect=fake), \
            mock.patch.object(sentinel, "attended", return_value=True):
        yield fake.messages


def _stage(project: Path, *extra: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = console.main(["--project", str(project), "authorize", "stage", *extra])
    return code, out.getvalue(), err.getvalue()


def _staged(broker: CapabilityBroker) -> list[dict]:
    return broker._load().get("staged", [])  # noqa: SLF001


class StageThroughTheDialogTests(unittest.TestCase):
    def test_the_right_password_stages_exactly_one_use_of_the_right_digest(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with _no_terminal(PASSWORD) as messages:
                code, out, _err = _stage(project, "--operation", OPERATION)
            self.assertEqual(code, 0, out)
            staged = _staged(broker)
            self.assertEqual(len(staged), 1)
            self.assertEqual(staged[0]["operation_digest"],
                             classify_action(OPERATION)["operation_digest"])
            self.assertEqual(len(messages), 1)
            self.assertIn(OPERATION, messages[0])
            self.assertIn("one use", messages[0])
            self.assertNotIn(PASSWORD, out)
            self.assertTrue(broker.consume_staged(OPERATION))
            self.assertIsNone(broker.consume_staged(OPERATION))

    def test_a_wrong_password_is_the_same_refusal_and_stages_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with _no_terminal("wrong password") as _messages:
                code, out, err = _stage(project, "--operation", OPERATION)
            self.assertNotEqual(code, 0)
            self.assertIn("Authorization failed", out + err)
            self.assertEqual(_staged(broker), [])

    def test_cancel_stages_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with _no_terminal(None):
                code, out, _err = _stage(project, "--operation", OPERATION)
            self.assertEqual(code, 1)
            self.assertIn("cancelled", out)
            self.assertEqual(_staged(broker), [])

    def test_the_dialog_path_never_reads_a_password_from_stdin(self) -> None:
        """A caller cannot answer the dialog for the operator: a password
        waiting on stdin is ignored, and the cancelled dialog stages nothing."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with _no_terminal(None), mock.patch.object(sys, "stdin", io.StringIO(PASSWORD + "\n")):
                code, _out, _err = _stage(project, "--operation", OPERATION)
                self.assertEqual(sys.stdin.read(), PASSWORD + "\n")
            self.assertEqual(code, 1)
            self.assertEqual(_staged(broker), [])

    def test_no_dialog_falls_back_to_the_separate_terminal_message(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with _no_terminal(unavailable=True), \
                    mock.patch.object(sys, "stdin", io.StringIO("")):
                code, out, err = _stage(project, "--operation", OPERATION)
            self.assertNotEqual(code, 0)
            self.assertIn("separate terminal window", out + err)
            self.assertEqual(_staged(broker), [])

    def test_an_unconfigured_store_opens_no_dialog(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with _no_terminal(PASSWORD) as messages:
                code, out, err = _stage(project, "--operation", OPERATION)
            self.assertNotEqual(code, 0)
            self.assertIn("authorize setup", out + err)
            self.assertEqual(messages, [])

    def test_the_refusal_hint_says_the_command_opens_a_dialog(self) -> None:
        hint = sentinel.stage_hint(PLUGIN_ROOT)
        self.assertIn("authorize stage --from-last-refusal", hint)
        self.assertIn("password dialog", hint)


if __name__ == "__main__":
    unittest.main()

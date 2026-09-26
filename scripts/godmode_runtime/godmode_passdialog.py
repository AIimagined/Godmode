"""A native password dialog for approving one staged operation.

A chat's `!` command prefix runs without a terminal, so a hidden terminal
prompt cannot be shown there. This module asks the operating system for the
password instead: the Windows credential prompt, a macOS dialog with a hidden
answer, or a zenity/kdialog prompt on a Linux desktop.

The password travels one way only: from the dialog to the caller, in this
process. It is never placed in a command line, an environment variable or a
file. On Windows the prompt runs in-process through CredUI; elsewhere the
dialog program writes the typed text to a pipe this process reads into a
buffer it zeroes afterwards. There is deliberately no way to hand this module
a password: it has no argument, stdin or environment input for one, so a
caller cannot supply the answer on the operator's behalf.

Dialog programs are resolved from fixed system directories, never from PATH,
so a look-alike program earlier on PATH cannot stand in for the real dialog.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unicodedata

from .godmode_errors import AuthorizationError


class DialogUnavailable(RuntimeError):
    """No native dialog can be shown here (no desktop, no dialog program)."""


class OperationNotDisplayable(AuthorizationError):
    """The operation, as the dialog would show it, does not fit the dialog."""


TITLE = "Godmode approval"
OPERATION_DISPLAY_LIMIT = 600
_SYSTEM_BIN = ("/usr/bin", "/bin")
_READ_LIMIT = 4096
# Characters that reorder, hide or break the text around them: bidirectional
# controls and marks, and zero-width characters. Shown escaped, so the
# operator reads the command's characters in the order they will run.
_INVISIBLE = frozenset(
    [0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF]
    + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))
_NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def displayable(operation: str) -> str:
    """`operation` with every control, bidirectional and zero-width
    character written as a visible escape (`\\n`, `\\u202e`), so a
    newline cannot push text out of view and a reordering mark cannot make
    the dialog show a different command from the one staged."""
    shown: list[str] = []
    for char in operation:
        code = ord(char)
        if char in _NAMED_ESCAPES:
            shown.append(_NAMED_ESCAPES[char])
        elif code in _INVISIBLE or unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp"):
            shown.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            shown.append(char)
    return "".join(shown)


def approval_message(operation: str, ttl_seconds: int, digest: str | None = None) -> str:
    """The text every dialog shows: the exact command and what approving
    spends. An operation that does not fit is refused, never cut: approving
    text the operator could not see is not an approval."""
    shown = displayable(operation)
    if len(shown) > OPERATION_DISPLAY_LIMIT:
        raise OperationNotDisplayable(
            f"This operation is {len(shown)} characters as the approval dialog would show it; "
            f"the dialog shows at most {OPERATION_DISPLAY_LIMIT}, so it cannot be approved "
            "there. Stage a shorter command, or run it from a terminal where it can be read "
            "in full.")
    lines = [
        "Approve this exact command:",
        "",
        shown,
        "",
        f"Scope: one use, expires in {ttl_seconds} seconds.",
    ]
    if digest:
        lines.append(f"Operation digest: {digest[:16]}")
    lines += [
        "",
        "Type the Godmode authorization password only if you asked for this "
        "command yourself. Cancel stages nothing.",
    ]
    return "\n".join(lines)


def _system_program(name: str, exists=os.path.exists) -> str | None:
    for directory in _SYSTEM_BIN:
        candidate = f"{directory}/{name}"
        if exists(candidate):
            return candidate
    return None


def select_backend(platform: str | None = None, env: dict[str, str] | None = None,
                   exists=os.path.exists) -> tuple[str, str | None] | None:
    """(backend, program path) for this machine, or None when none can show."""
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    if platform == "win32":
        return ("windows-credui", None)
    if platform == "darwin":
        program = _system_program("osascript", exists)
        return ("osascript", program) if program else None
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return None
    for name in ("zenity", "kdialog"):
        program = _system_program(name, exists)
        if program:
            return (name, program)
    return None


def _argv(backend: str, program: str, message: str) -> list[str]:
    if backend == "osascript":
        # The script is fixed text; the message arrives as a script argument,
        # so nothing in the command can break out of an AppleScript string.
        return [
            program,
            "-e", "on run argv",
            "-e", ('set answer to display dialog (item 1 of argv) with title (item 2 of argv) '
                   'default answer "" with hidden answer buttons {"Cancel", "Approve"} '
                   'default button "Approve" cancel button "Cancel" with icon caution'),
            "-e", "return text returned of answer",
            "-e", "end run",
            message, TITLE,
        ]
    if backend == "zenity":
        import html

        # zenity renders --text as markup; escaped, a `<` or `&` in the
        # command is shown as typed.
        return [program, "--entry", "--hide-text", f"--title={TITLE}",
                f"--text={html.escape(message, quote=False)}"]
    if backend == "kdialog":
        return [program, "--title", TITLE, "--password", message]
    raise DialogUnavailable(f"unknown dialog backend {backend!r}")


def _run_pipe_dialog(backend: str, program: str, message: str) -> str | None:
    """Run a dialog program; the typed text comes back over its stdout pipe."""
    try:
        process = subprocess.Popen(
            _argv(backend, program, message),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise DialogUnavailable(f"{backend} could not start: {exc}") from exc
    buffer = bytearray(_READ_LIMIT)
    size = 0
    try:
        view = memoryview(buffer)
        while size < _READ_LIMIT:
            got = process.stdout.readinto(view[size:])
            if not got:
                break
            size += got
        view.release()
        error = process.stderr.read() or b""
        code = process.wait()
        if code != 0:
            # osascript reports a cancel as error -128; zenity and kdialog
            # exit 1. Anything else means the dialog could not be shown.
            if backend == "osascript" and b"-128" in error:
                return None
            if backend in ("zenity", "kdialog") and code == 1:
                return None
            raise DialogUnavailable(f"{backend} exited with status {code}")
        end = size
        if end and buffer[end - 1] == 0x0A:
            end -= 1
        if end and buffer[end - 1] == 0x0D:
            end -= 1
        return bytes(buffer[:end]).decode("utf-8")
    finally:
        for index in range(len(buffer)):
            buffer[index] = 0
        for stream in (process.stdout, process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:  # godmode: swallow-ok: the dialog's answer is already read and the buffer zeroed; a pipe that fails to close leaks nothing the caller could act on
                pass


def _windows_credui(message: str) -> str | None:  # pragma: no cover - needs a desktop
    """The Windows credential prompt, in-process: no child process at all."""
    import ctypes
    from ctypes import wintypes

    class CREDUI_INFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hwndParent", wintypes.HWND),
            ("pszMessageText", wintypes.LPCWSTR),
            ("pszCaptionText", wintypes.LPCWSTR),
            ("hbmBanner", wintypes.HANDLE),
        ]

    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    try:
        credui = ctypes.WinDLL(str(system / "credui.dll"))
    except OSError as exc:
        raise DialogUnavailable(f"credui could not load: {exc}") from exc
    prompt = credui.CredUIPromptForCredentialsW
    prompt.restype = wintypes.DWORD
    prompt.argtypes = [
        ctypes.POINTER(CREDUI_INFOW), wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
        wintypes.LPWSTR, wintypes.ULONG, wintypes.LPWSTR, wintypes.ULONG,
        ctypes.POINTER(wintypes.BOOL), wintypes.DWORD,
    ]
    info = CREDUI_INFOW()
    info.cbSize = ctypes.sizeof(CREDUI_INFOW)
    # Parented to the window the operator just typed in, so the prompt opens
    # in front of it rather than behind.
    info.hwndParent = ctypes.windll.user32.GetForegroundWindow()
    info.pszMessageText = message[:1000]
    info.pszCaptionText = TITLE
    user = ctypes.create_unicode_buffer("godmode", 514)
    secret = ctypes.create_unicode_buffer(257)
    save = wintypes.BOOL(False)
    flags = (0x40000     # CREDUI_FLAGS_GENERIC_CREDENTIALS
             | 0x80      # CREDUI_FLAGS_ALWAYS_SHOW_UI
             | 0x2       # CREDUI_FLAGS_DO_NOT_PERSIST
             | 0x100000)  # CREDUI_FLAGS_KEEP_USERNAME
    try:
        code = prompt(ctypes.byref(info), "Godmode", None, 0, user, 514, secret, 257,
                      ctypes.byref(save), flags)
        if code == 1223:  # ERROR_CANCELLED
            return None
        if code != 0:
            raise DialogUnavailable(f"the credential prompt failed with code {code}")
        return secret.value
    finally:
        ctypes.memset(secret, 0, ctypes.sizeof(secret))


def ask_password(message: str, backend: tuple[str, str | None] | None = None) -> str | None:
    """Show the dialog and return what the operator typed, or None on cancel.

    Raises DialogUnavailable when this machine has no dialog to show.
    """
    backend = select_backend() if backend is None else backend
    if backend is None:
        raise DialogUnavailable("no native password dialog is available here")
    name, program = backend
    if name == "windows-credui":
        return _windows_credui(message)
    return _run_pipe_dialog(name, program or "", message)

"""Generated launcher template pair (R-3/R-3a): one source, two files.

`hooks/run-hook.cmd` (the polyglot sh+cmd entry that already self-resolves
its root and probes for a working Python interpreter) and `hooks/run-hook.sh`
(a plain POSIX sibling for hosts whose manifest wants a bare `.sh`) are both
rendered from the templates in this module, never hand-edited. `godmode
bindings --write` calls `write_launchers()` below the same way it already
regenerates every host identity/hook manifest from `packaging/hosts.json`;
`godmode bindings --check` (`check()` in godmode_bindings.py) diffs the tree
against `render()`'s output the same way. `tests/test_launcher_pair.py` pins
byte-identity for both files.

Both templates are committed LF-only (`.gitattributes` carries `text
eol=lf` for each path); `write_launchers()` writes raw bytes, never through
a text-mode file object, so a Windows worktree never picks up `\r\n` from
the write itself - the whole point of the R-3a acceptance ("diffed by a
test") is a byte comparison, and `write_text()`'s default newline
translation on Windows would silently defeat it.

R-3a's fallback tiers (`godmode_reach.TIER`) are a separate, non-launcher
concern recorded in `godmode_reach.py` next to `HOSTS`; nothing here reads
or writes them.

Task-3 review round 1 (task-3-review.md, B1/B2): the two sh-shaped halves
used to be two independent `repr()`-embedded one-liners, and they had
already diverged - `hooks/run-hook.sh`'s root-resolution `case` carried an
escaped *asterisk* (`*\\*`, a no-op against a backslash path) where the
polyglot's sh half carries an escaped *backslash* (`*\\\\*`, B1). Nobody could
have caught that from either byte-identity test, because both sides of each
one were rendered from the same (already-drifted) literal. `_SH_BODY` below
is now the single place that logic lives, in plain readable text, rendered
twice: once bare for `hooks/run-hook.sh`, once through `_polyglot()` for the
sh half of `hooks/run-hook.cmd`. The two files cannot diverge from each
other again without editing this one constant, and `tests/test_launcher_pair.py`
pins that the `.cmd`'s `:; `-stripped sh lines equal `.sh`'s code lines as a
second, independent guard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

CMD_LAUNCHER_PATH = "hooks/run-hook.cmd"
SH_LAUNCHER_PATH = "hooks/run-hook.sh"


def _polyglot(raw: str) -> str:
    """Render `raw` sh source as cmd's `:; `-prefixed sh half: a `:; `-led
    line is a no-op label to cmd.exe and ordinary executable text to sh.
    `raw` must end with a trailing newline; the final empty split element
    that produces is dropped, not turned into a bare `:;` line."""
    return "".join(f":; {line}\n" for line in raw.splitlines())


# ---------------------------------------------------------------------------
# The polyglot-only preamble: field-report history for the sh+cmd polyglot
# mechanism itself (why it is a polyglot at all, why `:;` is the no-op
# marker, why the cmd half is label-free). Deliberately NOT shared with
# `_SH_PREFACE` below - the two files need different framing here, not the
# same words - only the executable logic in `_SH_BODY` is required to match.
# Reproduced byte-for-byte from `hooks/run-hook.cmd` as it existed before
# this module existed; see that file's own header for the field reports.
# ---------------------------------------------------------------------------
_CMD_SH_PREFACE = """\
# Polyglot hook launcher: one file, valid under POSIX sh AND cmd.exe.
# Field report 2026-09-03: every hook declared bare `python`, and stock
# macOS ships only python3 - all eight hooks died silently at
# `/bin/sh: python: command not found`. This launcher resolves the
# interpreter per platform (python3 first on POSIX; python, py -3, then
# python3 on Windows, a Store alias only as a last resort), caches the
# resolved path so later calls skip the probe, and execs the named hook so
# exit codes - which carry gate blocks - pass through untouched.
# GODMODE_PYTHON overrides everything.
# Lines starting `:;` are no-op labels to cmd and executable to sh;
# `exec`/`exit` ends the sh half before cmd's section is reached. The
# cmd half is label-free on purpose: this file is committed LF-only
# for the sh half, and cmd `goto` over LF endings is a known flake.
# Every interpreter starts with -I -B (sweep 2026-09-07, obligation 9866):
# isolated from PYTHONPATH, PYTHON* variables and the user site, and
# writing no byte-code into the plugin cache. The hooks put the plugin's
# own directories on sys.path themselves.
"""

# ---------------------------------------------------------------------------
# Template 2's own preamble: the standalone `.sh` file's header. Different
# framing from `_CMD_SH_PREFACE` on purpose (this one points back at
# `hooks/run-hook.cmd` for the field-report history instead of repeating
# it) - only `_SH_BODY` below is required to be identical text.
# ---------------------------------------------------------------------------
_SH_PREFACE = """\
#!/bin/sh
# POSIX hook launcher (generated - see scripts/godmode_runtime/godmode_launchers.py,
# do not hand-edit): the plain, non-polyglot sibling of hooks/run-hook.cmd, for
# hosts whose manifest wants a bare .sh entry rather than the sh/cmd polyglot.
# Root resolution, the GODMODE_PYTHON override, the interpreter probe order
# and the off-PATH fallbacks below are rendered from the exact same _SH_BODY
# constant as run-hook.cmd's sh half (see that file's own header for the
# field reports that shaped every probe order and fallback: 2026-09-03 bare
# `python`, 2026-09-08 reduced PATH, 2026-09-10 Dock/login-item PATH) - so a
# host that reads either launcher gets byte-identical logic, not merely
# logic that was meant to match.
# GODMODE_PYTHON overrides everything. No external commands run before the
# interpreter is found: the gate must still work under a reduced PATH where
# even `dirname` may be missing.
"""

# ---------------------------------------------------------------------------
# The shared sh body (R-3a / task-3 review B1+B2): root resolution, the
# GODMODE_PYTHON override, the interpreter probe order and the off-PATH
# fallbacks - the ONE place this logic is written down. `CMD_LAUNCHER`
# renders it through `_polyglot()` (each line gets a `:; ` prefix);
# `SH_LAUNCHER` renders it bare. A host reading either launcher now gets
# genuinely identical bytes for this part, not two hand-synchronized copies.
#
# The root-resolution `case` below strips a backslash-separated `$0` first
# (`*\\*`, an escaped backslash, matching a literal one - the pattern a host
# wiring this launcher through Git Bash on Windows needs) and a
# forward-slash-separated one second; `tests/test_launcher_root_fallback.py`
# proves the backslash branch end-to-end with a real backslash-bearing `$0`.
# ---------------------------------------------------------------------------
_SH_BODY = """\
hook="$1"; shift
# No external commands before the interpreter is found: the gate runs
# under a reduced PATH where `dirname` may be missing (2026-09-08).
dir=$0
case "$dir" in *\\\\*) dir=${dir%\\\\*} ;; esac
case "$dir" in */*) dir=${dir%/*} ;; esac
[ "$dir" = "$0" ] && dir=.
# A `$(...)` subshell is a fork, and a fork under Git Bash costs tens of
# milliseconds idle and far more under load (2026-09-23): an absolute
# directory is used as it is, `.` is the shell's own $PWD, and only a
# relative or backslash-separated one pays for the subshell.
# (One line: the polyglot prefixes every line with `:;`, which a
# multi-line `case` cannot take.)
case "$dir" in /*) ;; .) dir=$PWD ;; *) dir=$(CDPATH= cd -- "$dir" && pwd) ;; esac
# Session events enter through a small front door that answers a project
# with no Godmode state before the 5,000-line session hook is compiled
# (2026-09-23); it runs the real hook itself for every other project.
[ "$hook" = godmode_session_hook.py ] && [ -f "$dir/godmode_session_entry.py" ] && hook=godmode_session_entry.py
if [ -n "${GODMODE_PYTHON:-}" ]; then exec "$GODMODE_PYTHON" -I -B "$dir/$hook" "$@"; fi
# Resolved-interpreter cache (field report 2026-09-23: every hook started
# an interpreter twice - the probe below, then the real run - and on
# Windows the first candidate was the Store alias, whose activation is
# slow and very slow under load, until a host timed the hooks out). The
# first call that finds a working interpreter records its absolute path
# in the Godmode application home - GODMODE_STATE_HOME, else LOCALAPPDATA
# on Windows, else XDG_STATE_HOME, else ~/.local/state, the same order the
# runtime uses - and every later call execs it with no probe. A cached
# path that no longer names a file falls through to the probe, which
# rewrites it. Environment variables only: nothing external runs here.
win=
[ "${OS:-}" = Windows_NT ] && win=1
[ -n "${MSYSTEM:-}" ] && win=1
home=
if [ -n "${GODMODE_STATE_HOME:-}" ]; then home=$GODMODE_STATE_HOME
elif [ -n "$win" ] && [ -n "${LOCALAPPDATA:-}" ]; then home=$LOCALAPPDATA/Godmode
elif [ -n "${XDG_STATE_HOME:-}" ]; then home=$XDG_STATE_HOME/godmode
elif [ -n "${HOME:-}" ]; then home=$HOME/.local/state/godmode
fi
cache=
[ -n "$home" ] && cache=$home/launcher-python-sh
if [ -n "$cache" ] && [ -f "$cache" ]; then
  cached=
  read -r cached 2>/dev/null < "$cache"
  # Only something named like an interpreter is run from the cache (a
  # review found any executable named there was exec'd, the hook skipped).
  # (One line: the polyglot's `:;` prefix cannot sit inside a `case`.)
  case "${cached##*[/\\\\]}" in python|python.exe|pythonw|pythonw.exe|py|py.exe|python[0-9]|python[0-9].exe|python[0-9].[0-9]*) ;; *) cached= ;; esac
  if [ -n "$cached" ] && [ -f "$cached" ] && [ -x "$cached" ]; then
    exec "$cached" -I -B "$dir/$hook" "$@"
  fi
fi
# The probe runs a candidate once and has it print its own absolute path,
# which becomes the cache entry. A Store alias is never cached: it is the
# slow start this cache exists to avoid, and it stays behind as an
# installer stub when the Store interpreter is removed.
probe() {
  resolved=$("$1" -c "import sys; sys.stdout.write(sys.executable)" 2>/dev/null) || return 1
  case "$resolved" in *[/\\\\]WindowsApps[/\\\\]*) return 0 ;; esac
  if [ -n "$cache" ] && [ -n "$resolved" ] && [ -f "$resolved" ]; then
    { [ -d "$home" ] || mkdir -p "$home"; } 2>/dev/null && { printf '%s\\n' "$resolved" > "$cache"; } 2>/dev/null
  fi
  return 0
}
# Probe order: python3 first on POSIX, where bare `python` may be absent
# or a Python 2; python, then py, then python3 on Windows, where python3
# is most often the Store alias. A candidate that resolves into
# WindowsApps is only tried once nothing else works.
if [ -n "$win" ]; then order="python py python3"; else order="python3 python py"; fi
aliased=
for py in $order; do
  command -v "$py" >/dev/null 2>&1 || continue
  if [ -n "$win" ]; then
    case "$(command -v "$py")" in *[/\\\\]WindowsApps[/\\\\]*) aliased="$aliased $py"; continue ;; esac
  fi
  if probe "$py"; then exec "$py" -I -B "$dir/$hook" "$@"; fi
done
for py in $aliased; do
  if probe "$py"; then exec "$py" -I -B "$dir/$hook" "$@"; fi
done
# Off-PATH fallbacks (2026-09-10): a host launched from the Dock or a
# login item runs hooks under a PATH without Homebrew, MacPorts, pyenv
# or the python.org framework, and stock /usr/bin/python3 is a stub
# that fails the probe until the developer tools are installed. Each
# candidate is probed the same way; the order is the one a shell would
# resolve with a full login PATH.
for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 /opt/local/bin/python3 "$HOME/.pyenv/shims/python3" /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$HOME/.local/bin/python3" /usr/bin/python3; do
  if [ -x "$py" ] && probe "$py"; then
    exec "$py" -I -B "$dir/$hook" "$@"
  fi
done
echo "{\\"systemMessage\\": \\"godmode: no working python interpreter found (tried python3, python, py; python, py, python3 on Windows) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then\\"}"
exit 0
"""

# ---------------------------------------------------------------------------
# The cmd-only dispatch half: nothing here is shared with the sh side - a
# POSIX sh never reaches this text (the sh half's own `exec`/`exit` ends
# execution first), so it is `:;`-free and readable as ordinary cmd.exe
# batch. Its interpreter order and its cache mirror the sh half's Windows
# branch; the cache file is its own (`launcher-python-cmd`), because a
# path an MSYS shell resolved is not always one cmd.exe can run.
# ---------------------------------------------------------------------------
_CMD_BATCH = """\
@echo off
setlocal enabledelayedexpansion
rem Field walk 2026-09-05: with no `python` on PATH and only the `py`
rem launcher present, `if errorlevel 9009 ( py ... & exit /b %ERRORLEVEL% )`
rem returned 9009 (49 through a cmd /c wrapper) - the block expanded
rem %ERRORLEVEL% at parse time, so a gate's exit 2 vanished, and the Store
rem shim's "not recognized" line reached the host. Same probe as the sh
rem half: each candidate must run `import sys` before it is trusted. This
rem is also why the interpreter is captured into a plain variable and run
rem OUTSIDE any parenthesized block - `!ERRORLEVEL!` (delayed expansion)
rem read at that point is the interpreter's own real exit code, not one
rem frozen when the block was parsed.
rem R-3 (2026-09-16): `%~dp0` already anchors the hook path to this
rem file's own directory, not to a host-supplied plugin-root variable -
rem a host that runs this script with CLAUDE_PLUGIN_ROOT/PLUGIN_ROOT unset
rem or empty (PowerShell's own empty-string default) still finds its
rem hooks.
rem Every probe and the real dispatch below use `call`: an ordinary
rem python.exe/py.exe needs no `call` at all, but a `python`/`py` that
rem resolves to a .bat/.cmd shim (a pyenv-win shim, a venv activation-style
rem wrapper) does NOT return control to this script without it - the
rem probe would succeed, `gm_py` would be set, and the script would still
rem silently end right there, never reaching the real dispatch line, with
rem exit code 0 (found live while building the `py -3`-preference test:
rem a fake `py.cmd` probe target vanished the rest of this script until
rem `call` was added). `call` is always safe for a real .exe too.
rem Field report 2026-09-23: hooks timed out under load because every call
rem started an interpreter twice (probe, then run). The first call that
rem finds a working interpreter records its absolute python.exe path in
rem the Godmode application home (GODMODE_STATE_HOME, else
rem LOCALAPPDATA\\Godmode); every later call runs it with no probe, and a
rem cached path that no longer exists falls back to the probe. Order:
rem python, then `py -3` (one extra process per call), then python3; a
rem candidate that resolves into WindowsApps (the Store alias, slow to
rem activate) is tried only when nothing else works, and never cached.
set "gm_py="
set "gm_flag="
set "gm_home="
set "gm_cache="
set "gm_hit="
set "gm_probed="
set "gm_where="
set "gm_alias_python="
set "gm_alias_python3="
set "gm_exe="
set "gm_keep="
set "gm_named="
set "gm_hook=%~1"
rem Session events enter through godmode_session_entry.py, which answers a
rem project with no Godmode state before the session hook is compiled.
if /i "%~1"=="godmode_session_hook.py" if exist "%~dp0godmode_session_entry.py" set "gm_hook=godmode_session_entry.py"
if defined GODMODE_PYTHON set "gm_py=%GODMODE_PYTHON%"
if defined GODMODE_STATE_HOME set "gm_home=%GODMODE_STATE_HOME%"
if not defined gm_home if defined LOCALAPPDATA set "gm_home=%LOCALAPPDATA%\\Godmode"
if defined gm_home set "gm_cache=!gm_home!\\launcher-python-cmd"
if not defined gm_py if defined gm_cache if exist "!gm_cache!" set /p gm_hit=<"!gm_cache!"
if defined gm_hit if /i "!gm_hit:~-4!"==".exe" if exist "!gm_hit!" set "gm_py=!gm_hit!"
rem A cache entry `@python`, `@py` or `@python3` names the command that
rem answered, recorded when its own path could not be read back (below);
rem it is trusted while that name still resolves on PATH.
if defined gm_hit if "!gm_hit:~0,1!"=="@" set "gm_named=!gm_hit:~1!"
if defined gm_named if /i not "!gm_named!"=="python" if /i not "!gm_named!"=="py" if /i not "!gm_named!"=="python3" set "gm_named="
if not defined gm_py if defined gm_named for %%E in (.exe .cmd .bat) do if not defined gm_py for %%I in (!gm_named!%%E) do if not "%%~$PATH:I"=="" set "gm_py=!gm_named!"
if defined gm_named if /i "!gm_py!"=="py" set "gm_flag= -3"
if not defined gm_py for %%E in (.exe .cmd .bat) do if not defined gm_where for %%I in (python%%E) do set "gm_where=%%~$PATH:I"
if defined gm_where if not "!gm_where:\\WindowsApps\\=!"=="!gm_where!" set "gm_alias_python=1"
if not defined gm_py if defined gm_where if not defined gm_alias_python ( call python -c "import sys" >nul 2>&1 && set "gm_py=python" && set "gm_probed=1" )
if not defined gm_py ( call py -3 -c "import sys" >nul 2>&1 && set "gm_py=py" && set "gm_flag= -3" && set "gm_probed=1" )
set "gm_where="
if not defined gm_py for %%E in (.exe .cmd .bat) do if not defined gm_where for %%I in (python3%%E) do set "gm_where=%%~$PATH:I"
if defined gm_where if not "!gm_where:\\WindowsApps\\=!"=="!gm_where!" set "gm_alias_python3=1"
if not defined gm_py if defined gm_where if not defined gm_alias_python3 ( call python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" && set "gm_probed=1" )
if not defined gm_py if defined gm_alias_python ( call python -c "import sys" >nul 2>&1 && set "gm_py=python" )
if not defined gm_py if defined gm_alias_python3 ( call python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" )
if defined gm_probed if defined gm_cache for /f "delims=" %%P in ('call "%gm_py%"%gm_flag% -c "import sys;sys.stdout.write(sys.executable)" 2^>nul') do set "gm_exe=%%P"
if defined gm_exe if /i "!gm_exe:~-4!"==".exe" if exist "!gm_exe!" if "!gm_exe:\\WindowsApps\\=!"=="!gm_exe!" set "gm_keep=1"
rem Review 2026-09-23: the path comes back through a pipe in Python's
rem encoding and is read in the console's code page, so a path with a
rem non-ASCII character (a non-ASCII account name, the python.org per-user
rem install under %LOCALAPPDATA%) never passes `if exist`. The command
rem name that answered is recorded instead, so the next call still skips
rem both probes. A WindowsApps resolution records nothing.
if defined gm_exe if not "!gm_exe:\\WindowsApps\\=!"=="!gm_exe!" set "gm_probed="
if defined gm_probed if defined gm_cache if not defined gm_keep set "gm_keep=@"
if defined gm_keep if not exist "!gm_home!\\" mkdir "!gm_home!" >nul 2>&1
if "!gm_keep!"=="1" (>"!gm_cache!" echo(!gm_exe!) 2>nul
if "!gm_keep!"=="@" (>"!gm_cache!" echo(@!gm_py!) 2>nul
if not "!gm_keep!"=="1" set "gm_keep="
if defined gm_keep set "gm_py=!gm_exe!"
if defined gm_keep set "gm_flag="
if not defined gm_py (
  echo {"systemMessage": "godmode: no working python interpreter found (tried python, py -3, python3) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then"}
  exit /b 0
)
call "!gm_py!"!gm_flag! -I -B "%~dp0!gm_hook!" %2 %3 %4 %5 %6
exit /b !ERRORLEVEL!
"""

CMD_LAUNCHER = _polyglot(_CMD_SH_PREFACE) + _polyglot(_SH_BODY) + _CMD_BATCH
SH_LAUNCHER = _SH_PREFACE + _SH_BODY

LAUNCHERS: dict[str, dict[str, Any]] = {
    "cmd": {"path": CMD_LAUNCHER_PATH, "content": CMD_LAUNCHER},
    "sh": {"path": SH_LAUNCHER_PATH, "content": SH_LAUNCHER},
}


def render(name: str) -> str:
    """The named template's current rendering (`"cmd"` or `"sh"`)."""
    try:
        return LAUNCHERS[name]["content"]
    except KeyError:
        raise KeyError(f"unknown launcher template {name!r}; known: {sorted(LAUNCHERS)}") from None


def check(project: Path) -> list[dict[str, Any]]:
    """Report drift for both launchers without writing - `godmode_bindings.
    check()`'s launcher half. Never raises: a missing file is `"missing"`,
    a byte mismatch is `"drifted"`."""
    results: list[dict[str, Any]] = []
    for name, spec in LAUNCHERS.items():
        target = Path(project) / spec["path"]
        expected = spec["content"].encode("utf-8")
        if not target.is_file():
            results.append({"launcher": name, "path": spec["path"], "state": "missing"})
            continue
        actual = target.read_bytes()
        results.append({"launcher": name, "path": spec["path"],
                        "state": "current" if actual == expected else "drifted"})
    return results


def write_launchers(project: Path) -> dict[str, Any]:
    """Regenerate both launcher files from their templates.

    Raw bytes, not `Path.write_text()` - see this module's own docstring for
    why: `write_text()`'s default newline translation would inject `\r\n`
    into an LF-only file on a Windows worktree, defeating the whole point of
    generating a file that is then diffed byte-for-byte.
    """
    written: list[str] = []
    for name, spec in LAUNCHERS.items():
        target = Path(project) / spec["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        content = spec["content"].encode("utf-8")
        if not target.is_file() or target.read_bytes() != content:
            target.write_bytes(content)
            written.append(spec["path"])
    return {"written": written, "unchanged": len(LAUNCHERS) - len(written)}

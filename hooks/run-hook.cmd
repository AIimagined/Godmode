:; # Polyglot hook launcher: one file, valid under POSIX sh AND cmd.exe.
:; # Field report 2026-09-03: every hook declared bare `python`, and stock
:; # macOS ships only python3 - all eight hooks died silently at
:; # `/bin/sh: python: command not found`. This launcher resolves the
:; # interpreter per platform (python3 first on POSIX; python, py -3, then
:; # python3 on Windows, a Store alias only as a last resort), caches the
:; # resolved path so later calls skip the probe, and execs the named hook so
:; # exit codes - which carry gate blocks - pass through untouched.
:; # GODMODE_PYTHON overrides everything.
:; # Lines starting `:;` are no-op labels to cmd and executable to sh;
:; # `exec`/`exit` ends the sh half before cmd's section is reached. The
:; # cmd half is label-free on purpose: this file is committed LF-only
:; # for the sh half, and cmd `goto` over LF endings is a known flake.
:; # Every interpreter starts with -I -B (sweep 2026-09-07, obligation 9866):
:; # isolated from PYTHONPATH, PYTHON* variables and the user site, and
:; # writing no byte-code into the plugin cache. The hooks put the plugin's
:; # own directories on sys.path themselves.
:; hook="$1"; shift
:; # No external commands before the interpreter is found: the gate runs
:; # under a reduced PATH where `dirname` may be missing (2026-09-08).
:; dir=$0
:; case "$dir" in *\\*) dir=${dir%\\*} ;; esac
:; case "$dir" in */*) dir=${dir%/*} ;; esac
:; [ "$dir" = "$0" ] && dir=.
:; # A `$(...)` subshell is a fork, and a fork under Git Bash costs tens of
:; # milliseconds idle and far more under load (2026-09-23): an absolute
:; # directory is used as it is, `.` is the shell's own $PWD, and only a
:; # relative or backslash-separated one pays for the subshell.
:; # (One line: the polyglot prefixes every line with `:;`, which a
:; # multi-line `case` cannot take.)
:; case "$dir" in /*) ;; .) dir=$PWD ;; *) dir=$(CDPATH= cd -- "$dir" && pwd) ;; esac
:; # Session events enter through a small front door that answers a project
:; # with no Godmode state before the 5,000-line session hook is compiled
:; # (2026-09-23); it runs the real hook itself for every other project.
:; [ "$hook" = godmode_session_hook.py ] && [ -f "$dir/godmode_session_entry.py" ] && hook=godmode_session_entry.py
:; if [ -n "${GODMODE_PYTHON:-}" ]; then exec "$GODMODE_PYTHON" -I -B "$dir/$hook" "$@"; fi
:; # Resolved-interpreter cache (field report 2026-09-23: every hook started
:; # an interpreter twice - the probe below, then the real run - and on
:; # Windows the first candidate was the Store alias, whose activation is
:; # slow and very slow under load, until a host timed the hooks out). The
:; # first call that finds a working interpreter records its absolute path
:; # in the Godmode application home - GODMODE_STATE_HOME, else LOCALAPPDATA
:; # on Windows, else XDG_STATE_HOME, else ~/.local/state, the same order the
:; # runtime uses - and every later call execs it with no probe. A cached
:; # path that no longer names a file falls through to the probe, which
:; # rewrites it. Environment variables only: nothing external runs here.
:; win=
:; [ "${OS:-}" = Windows_NT ] && win=1
:; [ -n "${MSYSTEM:-}" ] && win=1
:; home=
:; if [ -n "${GODMODE_STATE_HOME:-}" ]; then home=$GODMODE_STATE_HOME
:; elif [ -n "$win" ] && [ -n "${LOCALAPPDATA:-}" ]; then home=$LOCALAPPDATA/Godmode
:; elif [ -n "${XDG_STATE_HOME:-}" ]; then home=$XDG_STATE_HOME/godmode
:; elif [ -n "${HOME:-}" ]; then home=$HOME/.local/state/godmode
:; fi
:; cache=
:; [ -n "$home" ] && cache=$home/launcher-python-sh
:; if [ -n "$cache" ] && [ -f "$cache" ]; then
:;   cached=
:;   read -r cached 2>/dev/null < "$cache"
:;   # Only something named like an interpreter is run from the cache (a
:;   # review found any executable named there was exec'd, the hook skipped).
:;   # (One line: the polyglot's `:;` prefix cannot sit inside a `case`.)
:;   case "${cached##*[/\\]}" in python|python.exe|pythonw|pythonw.exe|py|py.exe|python[0-9]|python[0-9].exe|python[0-9].[0-9]*) ;; *) cached= ;; esac
:;   if [ -n "$cached" ] && [ -f "$cached" ] && [ -x "$cached" ]; then
:;     exec "$cached" -I -B "$dir/$hook" "$@"
:;   fi
:; fi
:; # The probe runs a candidate once and has it print its own absolute path,
:; # which becomes the cache entry. A Store alias is never cached: it is the
:; # slow start this cache exists to avoid, and it stays behind as an
:; # installer stub when the Store interpreter is removed.
:; probe() {
:;   resolved=$("$1" -c "import sys; sys.stdout.write(sys.executable)" 2>/dev/null) || return 1
:;   case "$resolved" in *[/\\]WindowsApps[/\\]*) return 0 ;; esac
:;   if [ -n "$cache" ] && [ -n "$resolved" ] && [ -f "$resolved" ]; then
:;     { [ -d "$home" ] || mkdir -p "$home"; } 2>/dev/null && { printf '%s\n' "$resolved" > "$cache"; } 2>/dev/null
:;   fi
:;   return 0
:; }
:; # Probe order: python3 first on POSIX, where bare `python` may be absent
:; # or a Python 2; python, then py, then python3 on Windows, where python3
:; # is most often the Store alias. A candidate that resolves into
:; # WindowsApps is only tried once nothing else works.
:; if [ -n "$win" ]; then order="python py python3"; else order="python3 python py"; fi
:; aliased=
:; for py in $order; do
:;   command -v "$py" >/dev/null 2>&1 || continue
:;   if [ -n "$win" ]; then
:;     case "$(command -v "$py")" in *[/\\]WindowsApps[/\\]*) aliased="$aliased $py"; continue ;; esac
:;   fi
:;   if probe "$py"; then exec "$py" -I -B "$dir/$hook" "$@"; fi
:; done
:; for py in $aliased; do
:;   if probe "$py"; then exec "$py" -I -B "$dir/$hook" "$@"; fi
:; done
:; # Off-PATH fallbacks (2026-09-10): a host launched from the Dock or a
:; # login item runs hooks under a PATH without Homebrew, MacPorts, pyenv
:; # or the python.org framework, and stock /usr/bin/python3 is a stub
:; # that fails the probe until the developer tools are installed. Each
:; # candidate is probed the same way; the order is the one a shell would
:; # resolve with a full login PATH.
:; for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 /opt/local/bin/python3 "$HOME/.pyenv/shims/python3" /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$HOME/.local/bin/python3" /usr/bin/python3; do
:;   if [ -x "$py" ] && probe "$py"; then
:;     exec "$py" -I -B "$dir/$hook" "$@"
:;   fi
:; done
:; echo "{\"systemMessage\": \"godmode: no working python interpreter found (tried python3, python, py; python, py, python3 on Windows) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then\"}"
:; exit 0
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
rem LOCALAPPDATA\Godmode); every later call runs it with no probe, and a
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
if not defined gm_home if defined LOCALAPPDATA set "gm_home=%LOCALAPPDATA%\Godmode"
if defined gm_home set "gm_cache=!gm_home!\launcher-python-cmd"
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
if defined gm_where if not "!gm_where:\WindowsApps\=!"=="!gm_where!" set "gm_alias_python=1"
if not defined gm_py if defined gm_where if not defined gm_alias_python ( call python -c "import sys" >nul 2>&1 && set "gm_py=python" && set "gm_probed=1" )
if not defined gm_py ( call py -3 -c "import sys" >nul 2>&1 && set "gm_py=py" && set "gm_flag= -3" && set "gm_probed=1" )
set "gm_where="
if not defined gm_py for %%E in (.exe .cmd .bat) do if not defined gm_where for %%I in (python3%%E) do set "gm_where=%%~$PATH:I"
if defined gm_where if not "!gm_where:\WindowsApps\=!"=="!gm_where!" set "gm_alias_python3=1"
if not defined gm_py if defined gm_where if not defined gm_alias_python3 ( call python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" && set "gm_probed=1" )
if not defined gm_py if defined gm_alias_python ( call python -c "import sys" >nul 2>&1 && set "gm_py=python" )
if not defined gm_py if defined gm_alias_python3 ( call python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" )
if defined gm_probed if defined gm_cache for /f "delims=" %%P in ('call "%gm_py%"%gm_flag% -c "import sys;sys.stdout.write(sys.executable)" 2^>nul') do set "gm_exe=%%P"
if defined gm_exe if /i "!gm_exe:~-4!"==".exe" if exist "!gm_exe!" if "!gm_exe:\WindowsApps\=!"=="!gm_exe!" set "gm_keep=1"
rem Review 2026-09-23: the path comes back through a pipe in Python's
rem encoding and is read in the console's code page, so a path with a
rem non-ASCII character (a non-ASCII account name, the python.org per-user
rem install under %LOCALAPPDATA%) never passes `if exist`. The command
rem name that answered is recorded instead, so the next call still skips
rem both probes. A WindowsApps resolution records nothing.
if defined gm_exe if not "!gm_exe:\WindowsApps\=!"=="!gm_exe!" set "gm_probed="
if defined gm_probed if defined gm_cache if not defined gm_keep set "gm_keep=@"
if defined gm_keep if not exist "!gm_home!\" mkdir "!gm_home!" >nul 2>&1
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

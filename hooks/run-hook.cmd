:; # Polyglot hook launcher: one file, valid under POSIX sh AND cmd.exe.
:; # Field report 2026-09-03: every hook declared bare `python`, and stock
:; # macOS ships only python3 - all eight hooks died silently at
:; # `/bin/sh: python: command not found`. This launcher resolves the
:; # interpreter per platform (python3 first on POSIX, python then py on
:; # Windows) and execs the named hook so exit codes - which carry gate
:; # blocks - pass through untouched. GODMODE_PYTHON overrides everything.
:; # Lines starting `:;` are no-op labels to cmd and executable to sh;
:; # `exec`/`exit` ends the sh half before cmd's section is reached. The
:; # cmd half is label-free on purpose: this file is committed LF-only
:; # for the sh half, and cmd `goto` over LF endings is a known flake.
:; hook="$1"; shift
:; dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
:; if [ -n "${GODMODE_PYTHON:-}" ]; then exec "$GODMODE_PYTHON" "$dir/$hook" "$@"; fi
:; for py in python3 python py; do
:;   if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys" >/dev/null 2>&1; then
:;     exec "$py" "$dir/$hook" "$@"
:;   fi
:; done
:; echo "{\"systemMessage\": \"godmode: no working python interpreter found (tried python3, python, py) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then\"}"
:; exit 0
@echo off
setlocal enabledelayedexpansion
rem Field walk 2026-09-05: with no `python` on PATH and only the `py`
rem launcher present, `if errorlevel 9009 ( py ... & exit /b %ERRORLEVEL% )`
rem returned 9009 (49 through a cmd /c wrapper) - the block expanded
rem %ERRORLEVEL% at parse time, so a gate's exit 2 vanished, and the Store
rem shim's "not recognized" line reached the host. Same probe as the sh
rem half: each candidate must run `import sys` before it is trusted.
set "gm_py="
if defined GODMODE_PYTHON set "gm_py=%GODMODE_PYTHON%"
if not defined gm_py ( python -c "import sys" >nul 2>&1 && set "gm_py=python" )
if not defined gm_py ( python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" )
if not defined gm_py ( py -c "import sys" >nul 2>&1 && set "gm_py=py" )
if not defined gm_py (
  echo {"systemMessage": "godmode: no working python interpreter found (tried python, python3, py) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then"}
  exit /b 0
)
"!gm_py!" "%~dp0%~1" %2 %3 %4 %5 %6
exit /b !ERRORLEVEL!

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
setlocal
if defined GODMODE_PYTHON ( "%GODMODE_PYTHON%" "%~dp0%~1" %2 %3 %4 & exit /b %ERRORLEVEL% )
python "%~dp0%~1" %2 %3 %4
if errorlevel 9009 ( py "%~dp0%~1" %2 %3 %4 & exit /b %ERRORLEVEL% )
exit /b %ERRORLEVEL%

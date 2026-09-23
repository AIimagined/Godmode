@echo off
rem Thin shim so the command is `godmode ...` rather than a long interpreter
rem invocation against a plugin path. Put this directory on PATH.
rem Eighth field report 2026-09-05: this shim ran bare `python` while
rem bin/godmode probes python3/python/py; on a machine with only the `py`
rem launcher it answered 9009. Same probe as the hook launcher's cmd half.
rem R-3 (2026-09-16): `py -3` is tried first, matching hooks/run-hook.cmd -
rem it is the official Windows launcher and the one most likely to land on
rem a real CPython even when a Store alias occupies `python`/`python3`.
rem Every probe and the real dispatch below use `call`: a python.exe/py.exe
rem needs no `call` at all, but a `python`/`py` that resolves to a
rem .bat/.cmd shim (a pyenv-win shim, a venv activation-style wrapper) does
rem NOT return control to this script without it - the probe would
rem succeed, `gm_py` would be set, and the script would silently end right
rem there, never reaching the real dispatch line, with exit code 0.
setlocal enabledelayedexpansion
set "GODMODE_ROOT=%~dp0.."
set "gm_py="
set "gm_flag="
if defined GODMODE_PYTHON set "gm_py=%GODMODE_PYTHON%"
if not defined gm_py ( call py -3 -c "import sys" >nul 2>&1 && set "gm_py=py" && set "gm_flag= -3" )
if not defined gm_py ( call python -c "import sys" >nul 2>&1 && set "gm_py=python" )
if not defined gm_py ( call python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" )
if not defined gm_py (
  echo godmode: no working python interpreter found on PATH ^(tried py -3, python, python3^). 1>&2
  echo          Set GODMODE_PYTHON to the interpreter to use. 1>&2
  exit /b 127
)
call "!gm_py!"!gm_flag! "%GODMODE_ROOT%\scripts\godmode.py" %*
exit /b !ERRORLEVEL!

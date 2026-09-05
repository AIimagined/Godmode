@echo off
rem Thin shim so the command is `godmode ...` rather than a long interpreter
rem invocation against a plugin path. Put this directory on PATH.
rem Eighth field report 2026-09-05: this shim ran bare `python` while
rem bin/godmode probes python3/python/py; on a machine with only the `py`
rem launcher it answered 9009. Same probe as the hook launcher's cmd half.
setlocal enabledelayedexpansion
set "GODMODE_ROOT=%~dp0.."
set "gm_py="
if defined GODMODE_PYTHON set "gm_py=%GODMODE_PYTHON%"
if not defined gm_py ( python -c "import sys" >nul 2>&1 && set "gm_py=python" )
if not defined gm_py ( python3 -c "import sys" >nul 2>&1 && set "gm_py=python3" )
if not defined gm_py ( py -c "import sys" >nul 2>&1 && set "gm_py=py" )
if not defined gm_py (
  echo godmode: no working python interpreter found on PATH ^(tried python, python3, py^). 1>&2
  echo          Set GODMODE_PYTHON to the interpreter to use. 1>&2
  exit /b 127
)
"!gm_py!" "%GODMODE_ROOT%\scripts\godmode.py" %*
exit /b !ERRORLEVEL!

@echo off
rem Thin shim so the command is `godmode ...` rather than a long interpreter
rem invocation against a plugin path. Put this directory on PATH.
setlocal
set "GODMODE_ROOT=%~dp0.."
if defined GODMODE_PYTHON (
  "%GODMODE_PYTHON%" "%GODMODE_ROOT%\scripts\godmode.py" %*
) else (
  python "%GODMODE_ROOT%\scripts\godmode.py" %*
)
exit /b %ERRORLEVEL%

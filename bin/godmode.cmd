@echo off
rem Godmode is not an npm package; this shim makes a PATH-style invocation
rem resolve loudly to the real entry point instead of silence.
python "%~dp0..\scripts\godmode.py" %*

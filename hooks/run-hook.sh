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
hook="$1"; shift
# No external commands before the interpreter is found: the gate runs
# under a reduced PATH where `dirname` may be missing (2026-09-08).
dir=$0
case "$dir" in *\\*) dir=${dir%\\*} ;; esac
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
  case "${cached##*[/\\]}" in python|python.exe|pythonw|pythonw.exe|py|py.exe|python[0-9]|python[0-9].exe|python[0-9].[0-9]*) ;; *) cached= ;; esac
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
  case "$resolved" in *[/\\]WindowsApps[/\\]*) return 0 ;; esac
  if [ -n "$cache" ] && [ -n "$resolved" ] && [ -f "$resolved" ]; then
    { [ -d "$home" ] || mkdir -p "$home"; } 2>/dev/null && { printf '%s\n' "$resolved" > "$cache"; } 2>/dev/null
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
    case "$(command -v "$py")" in *[/\\]WindowsApps[/\\]*) aliased="$aliased $py"; continue ;; esac
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
echo "{\"systemMessage\": \"godmode: no working python interpreter found (tried python3, python, py; python, py, python3 on Windows) - set GODMODE_PYTHON to the interpreter path; every godmode hook is inert until then\"}"
exit 0

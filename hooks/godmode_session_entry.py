#!/usr/bin/env python3
"""Small front door for `godmode_session_hook.py`.

A host's diagnostics advised uninstalling Godmode
because its hooks ran past their timeouts in projects nobody had initialized.
Python compiles a script in full before running its first line, and the
session hook is about 5,000 lines - measured here at 150-600 ms of compile
alone depending on machine load, paid on every Stop, SessionEnd and prompt
event even when the answer was "nothing to govern". The launcher runs this
file in its place: it asks `godmode_initstate` whether the project has any
Godmode state (stats only, nothing heavy imported) and exits 0 silently when
it has none. Otherwise it runs the real hook in this same process, as
`__main__`, with the payload it already read, so the hook behaves exactly as
if the launcher had started it directly - the same `sys.argv[0]`, the same
`__file__`, the same exit code.
"""
from __future__ import annotations

import os
import sys

HOOK_NAME = "godmode_session_hook.py"


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    raw: bytes | None = None
    try:
        from godmode_initstate import EXIT, early_session_decision
        action, _submitted, raw, _root = early_session_decision(sys.argv[1:])
        if action == EXIT:
            return 0
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: doubt runs the full hook, which decides
        pass
    if raw is not None:
        import godmode_stdin
        godmode_stdin.preload(raw)
    return run_hook(os.path.join(here, HOOK_NAME))


def run_hook(hook: str) -> int:
    """Run `hook` as `__main__` in this process. Its code object comes
    through the ordinary source loader, so the launcher's private byte-code
    cache (`-X pycache_prefix`) serves it: compiling the 5,000-line session
    hook cost 150-600 ms on every event (2026-09-25). Under `-B` nothing is
    written and it compiles as before."""
    import importlib.machinery
    import types
    code = importlib.machinery.SourceFileLoader("__main__", hook).get_code("__main__")
    module = types.ModuleType("__main__")
    module.__file__ = hook
    sys.argv[0] = hook
    sys.modules["__main__"] = module
    exec(code, module.__dict__)  # the hook ends in its own SystemExit
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

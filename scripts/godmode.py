#!/usr/bin/env python3
"""Godmode CLI entry point."""

import sys


def main() -> int:
    if sys.argv[1:] == ["--version"]:
        # The banner needs one constant, not the runtime and its 260 subparsers.
        from godmode_runtime.godmode_constants import RUNTIME_VERSION
        print(f"Godmode {RUNTIME_VERSION}")
        return 0
    from godmode_runtime.godmode_console import main as console_main
    return console_main()


if __name__ == "__main__":
    raise SystemExit(main())

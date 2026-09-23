#!/usr/bin/env python3
"""Run CI's checks on HEAD locally before a push.

    python scripts/dev/ci_local.py [--base <ref>] [--full]

`godmode precheck --preflight` already runs the committed workflow's gate list
in a disposable worktree of HEAD. This feeds it the tests affected by the
change (see affected_tests.py) as the suite, or the whole suite with --full,
and exits non-zero on a red result, so a push is not the first place a failure
shows up. Install as the repository's pre-push hook with:

    cp scripts/dev/pre-push .git/hooks/pre-push
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from affected_tests import REPO_ROOT, changed_files, module_map, select


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main", help="ref to diff against (default: origin/main)")
    parser.add_argument("--full", action="store_true", help="run the whole suite, as CI does")
    args = parser.parse_args(argv)
    command = [sys.executable, "scripts/godmode.py", "--project", ".", "precheck", "--preflight"]
    if args.full:
        command += ["--suite-shards", "4"]
    else:
        # One string: argparse would read a bare `-m` as an option of its own.
        modules = select(changed_files(args.base), module_map())
        command.append("--suite=python -m unittest " + " ".join(modules))
    return subprocess.call(command, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())

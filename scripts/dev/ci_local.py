#!/usr/bin/env python3
"""Run CI's checks on HEAD locally before a push.

    python scripts/dev/ci_local.py [--base <ref>] [--full] [--jobs N] [--native]

`godmode precheck --preflight` already runs the committed workflow's gate list
in a disposable worktree of HEAD. This feeds it the tests affected by the
change (see affected_tests.py) as the suite, or the whole suite with --full,
and exits non-zero on a red result, so a push is not the first place a failure
shows up. Install as the repository's pre-push hook with:

    cp scripts/dev/pre-push .git/hooks/pre-push

When a local Actions runner and Docker are both reachable on PATH, the
workflow's Linux jobs (those whose `runs-on` is the bare `ubuntu-latest`, not
a matrix expression that also lands on another OS) run through that runner
instead: real containers are closer to what a GitHub-hosted runner actually
does than this repository's own approximation of the gate list, which is what
makes a green run here a strong signal that the push will be green there too.
Without both of those on PATH, or with --native, this falls back to the gate
list above, as before. Either way this prints which path it took. A Windows
or macOS leg is never run through a container; it only ever runs natively, on
a machine of that OS.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from affected_tests import REPO_ROOT, changed_files, module_map, select

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "godmode-verify.yml"

# The conventional name of a local Actions-runner executable, if the operator
# has one installed. Never printed or written anywhere on its own - only used
# to look it up on PATH - so a missing one reads as "no local runner", not as
# an instruction to install a particular product.
_RUNNER_BIN = "act"

_JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.MULTILINE)
_BARE_UBUNTU = re.compile(r"^\s+runs-on:\s*ubuntu-latest\s*$", re.MULTILINE)


def local_runner_bin() -> str | None:
    """Path to a local Actions-runner executable on PATH, if any."""
    return shutil.which(_RUNNER_BIN)


def local_runner_ready() -> bool:
    """True when a local Actions runner and Docker are both on PATH - the
    two things that runner needs to actually execute a container job."""
    return bool(local_runner_bin()) and bool(shutil.which("docker"))


def linux_job_names(workflow_text: str) -> list[str]:
    """Job ids in `workflow_text` whose `runs-on` is the bare `ubuntu-latest`
    string - the jobs a container-based local runner can stand in for. A job
    whose `runs-on` is a matrix expression (e.g. `${{ matrix.os }}`) also
    lands on another OS in some leg, which a single container can't split, so
    it is left to the native path instead."""
    if "\njobs:" not in workflow_text:
        return []
    jobs_block = workflow_text.split("\njobs:", 1)[1]
    headers = list(_JOB_HEADER.finditer(jobs_block))
    names: list[str] = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(jobs_block)
        block = jobs_block[header.start():end]
        if _BARE_UBUNTU.search(block):
            names.append(header.group(1))
    return names


def run_via_local_runner(jobs: list[str], *, workflow: Path = WORKFLOW,
                         repo_root: Path = REPO_ROOT) -> int:
    """Run each named job of `workflow` through the local Actions runner.
    One job at a time and the worst exit code wins, so one failing job does
    not hide behind an earlier successful one."""
    runner = local_runner_bin()
    assert runner, "run_via_local_runner requires a local runner on PATH"
    code = 0
    for job in jobs:
        done = subprocess.run([runner, "-W", str(workflow), "-j", job], cwd=repo_root)
        code = code or done.returncode
    return code


def run_native(args: argparse.Namespace) -> int:
    command = [sys.executable, "scripts/godmode.py", "--project", ".", "precheck", "--preflight"]
    # The suite runs one module per process, several at once, as CI's parallel
    # legs do: one process after another took close to an hour.
    runner = f"python scripts/dev/affected_tests.py --jobs {args.jobs} "
    if args.full:
        command.append("--suite=" + runner + "--all")
    else:
        # One string: argparse would read a bare `-m` as an option of its own.
        modules = select(changed_files(args.base), module_map())
        command.append("--suite=" + runner + " ".join(modules))
    return subprocess.call(command, cwd=REPO_ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main", help="ref to diff against (default: origin/main)")
    parser.add_argument("--full", action="store_true", help="run the whole suite, as CI does")
    parser.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2),
                        help="test modules to run at once (default: half the CPUs)")
    parser.add_argument("--native", action="store_true",
                        help="skip the local-runner path even when one is on PATH")
    args = parser.parse_args(argv)

    if not args.native and local_runner_ready():
        jobs = linux_job_names(WORKFLOW.read_text(encoding="utf-8"))
        print(f"ci_local: local Actions runner + Docker found on PATH - "
              f"running {len(jobs)} Linux job(s) from {WORKFLOW.name} through it")
        return run_via_local_runner(jobs)

    print("ci_local: no local Actions runner + Docker on PATH - running the gate list natively")
    return run_native(args)


if __name__ == "__main__":
    raise SystemExit(main())

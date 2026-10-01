# Godmode v0.3.33

## Added

- Verification evidence is reused, not repeated: the test runner records every run (tree, modules, interpreter, platform, minutes, whether this tree ran before), the push preflight accepts a green record for exactly the tree being pushed instead of running the suite again, and a partial run never satisfies a full-release requirement. `claim --verify` references a check already run on this HEAD within the hour instead of running it a second time (`--rerun` runs it anyway). The pre-push hook also runs the other Python version CI runs when the machine has it and names the one it does not (`ci_local.py --matrix`).

## Changed

- The password is now asked only for harmful operations; the host decides the rest. `git checkout <branch>` runs free like `git switch`; a non-force push of a feature branch and `gh pr create` ask without a password (a push to the default branch, a force push, a tag push, a remote delete, a merge of a pull request and a release still need it); a command the classifier cannot name and a scripted in-place edit ask instead of being refused, unless a word in the command is built by the shell at run time (`git pu{s,}h -f`), which keeps the password; `git cherry-pick`, `git revert`, `git mv`, `git rm` and `git rm --cached` ask as the local changes they are; `git clean -n`, `git worktree prune` and a `git config` read run free; PowerShell's `New-Item -ItemType Directory` inside the tree and a delete under `$env:TEMP` run free. A `git config` write to a key that decides what code git runs (`core.hooksPath`, aliases, credentials, URL rewrites) is protected as hooks-as-code.
- The README gains a "What it can do" table (code graph, push preflight, one-shot approvals, loop detection, spend, plans, falsifiers, ask triage, citation repair, leases, release notes), an approvals paragraph, a flow diagram, a banner and a gate-tiers illustration, and current counts; the social preview image is replaced.

## Fixed

- A push that changes only prose and images (Markdown, pictures, changelog fragments, outside `skills/`) runs the ten test modules that read those files instead of every module whose source mentions a changed file's name; one README edit had selected 59.
- The prompt hook reads the archive's head hint instead of every record for the turn baseline (1.5 s to 1.0 s on a 28,000-record archive); the main skill has one entry path that consumes the brief the hooks already delivered instead of repeating `context status`, `resume` and `session open`; the turn-cost benchmark reports a hook that crashed as a failure, not as a fast step, and counts the commands a hook asks the agent to run as a separate number from hook seconds; a Windows-only literal in a changed test (a backslash parent path, `$env:TEMP`) is named before a push, on every platform.

## Verifying

- `python -m unittest discover -s tests` for the whole suite.

# Godmode v0.3.33

## Changed

- The password is now asked only for harmful operations; the host decides the rest. `git checkout <branch>` runs free like `git switch`; a non-force push of a feature branch and `gh pr create` ask without a password (a push to the default branch, a force push, a tag push, a remote delete, a merge of a pull request and a release still need it); a command the classifier cannot name and a scripted in-place edit ask instead of being refused, unless a word in the command is built by the shell at run time (`git pu{s,}h -f`), which keeps the password; `git cherry-pick`, `git revert`, `git mv`, `git rm` and `git rm --cached` ask as the local changes they are; `git clean -n`, `git worktree prune` and a `git config` read run free; PowerShell's `New-Item -ItemType Directory` inside the tree and a delete under `$env:TEMP` run free. A `git config` write to a key that decides what code git runs (`core.hooksPath`, aliases, credentials, URL rewrites) is protected as hooks-as-code.
- The README gains a "What it can do" table (code graph, push preflight, one-shot approvals, loop detection, spend, plans, falsifiers, ask triage, citation repair, leases, release notes), an approvals paragraph, a flow diagram, a banner and a gate-tiers illustration, and current counts; the social preview image is replaced.

## Fixed

- A push that changes only prose and images (Markdown, pictures, changelog fragments, outside `skills/`) runs the ten test modules that read those files instead of every module whose source mentions a changed file's name; one README edit had selected 59.

## Verifying

- `python -m unittest discover -s tests` for the whole suite.

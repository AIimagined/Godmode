The sentinel classified `git branch -d X` as read-only because the safe
inspection prefix matched `git branch` before any protected pattern ran.
Mutating flag forms of `git branch` now classify as `git-branch-mutation`
ahead of every safe pattern, and the safe listings for `git branch`,
`git tag`, `git stash`, and `git remote` are anchored so create, delete,
rename, and remote-mutation forms fall through to protection. Every
classification now carries a §9.2 risk tier R0-R5, with R5 (force-push,
hard reset, `branch -D`, `clean -f`, SQL DROP) demanding a second
confirmation. Capabilities bind to repository, worktree, and HEAD at mint
time and refuse to be consumed elsewhere; pre-existing unscoped tokens
still consume but say so. An optional `.godmode-authorization-policy.json`
can tighten (never loosen) the boundary: TTL clamped to 60-900 seconds and
`password_required` extending the protected categories.

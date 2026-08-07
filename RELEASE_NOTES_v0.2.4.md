# Godmode v0.2.4

A gate you can actually work behind.

**Update from any earlier 0.2.x.** v0.2.1 denied every command on Windows.
v0.2.2 and v0.2.3 fixed that, but still refused every file edit and every shell
loop, and answered each refusal by demanding a capability the host has no way to
supply.

Every defect in this release was found the same way: by installing the released
build and using it. None was visible to a suite of 469 passing tests.

## Every file edit was refused

The allowance for ordinary working files asked whether a path looked absolute,
treating that as a proxy for "outside the tree". The host sends an absolute
`file_path` for every `Write` and `Edit`, so the allowance could never fire —
correct-looking code on a branch nothing reached.

Containment is now measured against the project root. That also subsumes
traversal, since a path normalising outside the tree fails containment rather
than needing a rule of its own. `.git/`, `.env`, keys and certificates stay
protected wherever they sit.

## Shell control flow was refused

`for`, `do` and `done` are not commands. They matched nothing, fell through to
unclassified, and failed closed — so an ordinary loop over a few files was
denied. Control flow is now read as structure: the keyword is stripped and the
remainder judged, exactly as an assignment prefix already was. `do rm -rf x`
stays protected, and a loop body is still classified on its own.

## The refusal named a remedy that did not exist

It asked for "an exact one-use Godmode capability". The capability broker is
real, but no host tool call carries a field a capability could travel in, so it
was unreachable from the hook. The message sent the operator hunting for a token
they had no way to supply, when the true answer was "switch the plugin off".

Refusals now name the category and tier that triggered them and say plainly that
there is no in-session approval. That is also the strongest argument for this
gate being conservative about what it stops: with no approval path, every false
positive is total, and the only available response is to remove the guard
entirely — the approval-fatigue failure the threat model names, arrived at from
the opposite direction.

## Why none of this was caught

All three lived below the boundary the tests exercised. The suite fed
`classify_action` operation strings written by hand — `write file README.md` —
and the host sends `edit file C:\...\file.py`. A hand-written case passed while
the real one failed, and the same blind spot had already produced a POSIX-only
corpus that missed PowerShell and a corpus with no loops in it.

A real `PreToolUse` payload now goes into the hook process in the suite and the
decision comes back out, across thirteen cases spanning edits, reads, pipes,
loops, PowerShell and protected mutations. A case can only pass by working the
way it will work in a session.

## Upgrading

No migration. `classify_action` gains an optional `project_root`; callers that
omit it fall back to the working directory, which is what a relative path
already means.

## Verifying

```
python -m unittest discover -s tests            # 482 tests
python -m unittest tests.test_hook_end_to_end   # the gate, driven as the host drives it
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . trust
```

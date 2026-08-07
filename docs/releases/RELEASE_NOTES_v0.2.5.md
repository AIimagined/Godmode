# Godmode v0.2.5

Six more refusals of ordinary work, removed. Every one was found the same way
as in v0.2.4 — by installing the released build and using it — and none was
visible to the 482 tests that release shipped with.

**Update from any earlier 0.2.x.** This is the first build where a normal
session runs without the gate getting in the way.

## Judging what a command runs, not what it mentions

The classifier searched the whole command line, so `grep "git push" notes.md`
was refused because the words appeared in an argument. A session working on
protected operations trips that constantly.

Quoted text is data now, blanked before the mutation patterns are applied. That
is safe only because the safe listings are a whitelist matched against the
original: a shell invoked on a quoted script is still unrecognised and still
fails closed, so `bash -c "rm -rf /"` is refused exactly as before.

## Committing is the work; pushing is the consequence

Staging and committing are no longer protected. A commit is local and
reversible and loses nothing, and gating it made committing *impossible* in a
session — no host tool call carries a field a capability could travel in, so
there was no approval anyone could give. They are recorded at the same tier as
a file edit.

`git commit --amend`, `reset`, `clean`, `rebase`, `checkout`, branch deletion
and every form of `push` stay protected. Those either leave the machine or
destroy work, which is the line worth drawing.

## Redirection and substitution

- **An input redirect is a read.** `wc -l < README.md` reads a file and writes
  nothing; `<` and `>` were grouped only because they look symmetrical.
- **`2>&1` is one token.** Making a bare `&` a separator so `ls & rm` could not
  launder was right, but there the ampersand duplicates a file descriptor. The
  split left a bare `1` behind, which classified as an unknown mutation and
  refused the whole command.
- **A substitution is classified, not refused on sight.** Blanket refusal held
  the line against a fetch inside one and denied `echo $(ls)` with it. What the
  substitution runs is now extracted and judged alongside the line, so the
  laundering is stopped just as firmly.
- **An output redirect is judged by where it lands**, exactly as an edit is.
  Refusing every redirect while permitting the declared `Edit` of the same path
  gated the honest form and not the other.

## The pattern behind all of them

Each fix is the same correction: judge the thing by what it does, not by what
it looks like. A redirect by where it lands. A substitution by what it runs. An
edit by where the path resolves. A command by its executable position rather
than by any word appearing in the line.

That principle also explains why the gate must stay conservative. A refusal has
no in-session approval path, so every false positive costs the whole guard —
the operator's only response is to switch it off, which is the approval-fatigue
failure the threat model names, arrived at from the opposite direction.

## Repository layout

Release notes moved from the repository root into `docs/releases/`. Five files
restating what the changelog and the release pages already carry made the first
thing a reader sees a wall of near-duplicates.

## Upgrading

No migration. `git commit` and `git add` stop prompting; if you relied on that
interruption, `git push` still carries it.

## Verifying

```
python -m unittest discover -s tests            # 496 tests
python -m unittest tests.test_hook_end_to_end   # the gate, driven as the host drives it
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . trust
```

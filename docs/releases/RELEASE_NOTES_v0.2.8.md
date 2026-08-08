# Godmode v0.2.8

The ask that leaves no artefact.

v0.2.7 corrected the gate against the commands this project actually ran. This
release goes after something the gate never touched: the request itself.

Everything this runtime governs leaves a trace. A command leaves a run, a fix
leaves a commit, a conclusion leaves a claim that has to cite one. **A request
leaves the agent's recollection and nothing else** — and recollection is the
one substrate this product exists to distrust.

## Recorded live, because it cannot be reconstructed

The failure has a specific shape. An input arriving while the agent is already
running a tool is handed over beside a tool result. The cheapest part gets
answered, the rest is carried in the agent's head, and in a long session the
rest is what goes missing. Afterwards nobody can point at what was dropped,
because there was never a list.

Two signals were tried against a real 9,777-event transcript before this was
built, on the assumption the history could simply be read back:

```
"sent a new message while you were working"
  → 2 occurrences in the whole file, one of them the agent quoting it

human inputs timestamped inside a tool call's span
  → 0 of 113   (across 1,953 completed tool calls)
```

The host injects that notice at delivery and never stores it, and the stored
timestamp is when an input was *delivered*, not when it was typed. After the
fact, an interruption is indistinguishable from an ordinary turn.

So a `UserPromptSubmit` hook writes each prompt as a `request` record as it
arrives, carrying whether tool calls were already in flight — the one fact that
cannot be recovered later. `checkpoint --review` reports the ones nothing
visibly answered, interruptions first.

Findings, never closures. An agent that could close its own requests would
close them the way it currently forgets them.

The test for "answered" is deliberately weak: did the session's later text use
this request's distinctive words at all. A weak test that over-reports costs a
question the operator waves away. A strong one that reports nothing is the
check that cannot fail, which is the defect this project keeps finding in
itself — and it found two false positives on its first real run, in exactly
that safe direction.

A prompt is also where a pasted token turns up, so the record goes through the
ordinary append and the same secret scan every record gets. A credential is
refused, and the hook swallows the refusal so a refusal cannot end the
operator's turn. The subject is truncated rather than kept whole: the host
already stores a transcript, and a second copy is a second thing to leak.

## A tag's name is not a claim about its tree

v0.2.7 was published against the commit before the version bump. Every version
surface agreed — the tag was called `v0.2.7`, every file said `0.2.7` — so the
reconciler returned `agreed` and CI passed on it, while `git checkout v0.2.7`
produced a plugin manifest reading `0.2.6`.

Nothing was broken in the check. It compared the tag's *name* to the sources,
and the name was never wrong. It never asked what the tagged commit says about
itself. `plugin.json at tag <name>` is now a surface like any other.

The report states whether that surface could be read, because a shallow clone
can have a tag without its tree, and reporting a fetch depth as a release
defect is how a gate gets switched off — but collapsing "agreed after
consulting the tagged tree" into plain "agreed" would hide which one happened.

## The README described the wrong product

A reader's first experience of this plugin is a continuity brief at session
start, a refusal at the pre-tool boundary, and skills routing by the shape of
the work. Quick start opened with three interpreter invocations and a command
count, which reads as a large manual CLI and is the opposite of what installing
it feels like.

It now leads with what happens without being asked, and names the three ways to
answer a refusal — including staging a capability, which had gone unmentioned
in the README as well as in the refusal message itself.

Two stale figures went with it, and both sat inside fenced code blocks: `80
commands` when there are 82, and a CI snippet pinning `AIimagined/Godmode@v0.2.0`
through seven releases.

The count is deleted rather than corrected. Only 82 of 120 `add_parser` calls
are top-level commands, so there is no exact local answer, and the linter's own
remedy text says to stop stating a number that changes rather than to police
one.

The pin *is* checkable, because the running version is an exact answer, so
`stale-self-pin` now reports any snippet pinning a version of this project that
is no longer current. It reads inside fenced blocks deliberately: the figure
check skips them, since a number in a code sample is usually an argument rather
than a claim, and that left every install snippet — the one thing a reader
copies verbatim — in the only place no check looked.

The header also said "Godmode" twice, once in the logo and once beneath it,
with a gap between. 46% of the logo's height was transparent padding on a
1,254-pixel square canvas; cropped to its content it is 795×727 and 818KB
rather than 1.9MB.

## Upgrading

No migration. `request` is a new record kind, so an archive written by an older
build reads normally and simply holds none of them.

The ledger only starts recording once an installed build contains this hook.
Nothing backfills — an ask made before the upgrade was never written down, and
inventing one afterwards would be the failure this release exists to stop.

## Verifying

```
python -m unittest discover -s tests            # 702 tests
python -m unittest tests.test_request_hook      # the hook, over a real archive
python -m unittest tests.test_tag_tree_version  # the v0.2.7 incident, as a test
python scripts/godmode.py --project . checkpoint --review
python scripts/godmode.py --project . docs --lint
```

The request hook is tested through the host's own payload into a real archive
rather than by calling the function, because obligation retirement was built
correctly once and starved by a filtered record list — a mechanism nothing
calls is not a mechanism.

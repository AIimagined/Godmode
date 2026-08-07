# Godmode v0.2.3

Four capabilities and a portable manifest. The theme is not a feature — it is
that every check in here was built because a check that already existed failed
to fail, and three of the four found a different defect than the one they were
built for.

**Anyone still on v0.2.1 should update.** That build's gate denies every command
on Windows, and on any platform a newline could hand a whole line the risk tier
of its first word. v0.2.2 fixed both.

## Gates that can fail

Each release gate now runs against a copy of the project with the property it
defends deliberately broken, and must report failure. A gate that stays green
under its own breaking mutation is not a check.

This exists because six times in one session a check reported a success it could
not have withheld: twice a gate battery piped through a pager, so the recorded
exit status belonged to the pager; twice a probe that passed only on a machine
already initialised; once a suite proving refusals without asking whether
ordinary work could still proceed; once a contamination grep read as clean when
its exit code meant the opposite. Knowing about the failure mode did not prevent
the sixth instance, which is the argument for asserting it rather than
remembering it.

Writing the mutation turned out to matter as much as running it. Three of the
first mutations were wrong — they broke something the gate never claimed to
watch — and three gates were briefly and wrongly suspected of being blind. A
breaking mutation cannot be written for a gate whose contract is not understood,
so the harness doubles as a statement of what each gate is for. Gates without a
proof are listed with the reason, because a harness that quietly covers a subset
reads as covering everything.

Module self-checks are now discovered rather than registered by hand. Six
already existed and had never been run by the suite, and the action gate itself
— the classifier deciding whether a destructive command is interrupted — had no
self-check at all while quieter modules did.

## Configuration read as an executable surface

`godmode trust` reports what a repository's checked-in agent configuration would
run and what it would permit. Those files were already being read, but only to
ask whether their prose was shaped like an instruction — never the structural
question of whether the configuration a repository ships executes anything or
disarms anything.

A cloned repository can declare a hook that runs a command the moment a tool is
used, declare a server whose launch line is arbitrary, or pre-authorise the
exact operations the action gate exists to interrupt. That last one made the
omission reflexive: this product's enforcement is itself a host hook, so the
gate's off-switch lived in a file the gate never read.

Blanket permission modes and fetch-and-run hooks fail the command. A declared
server or an ordinary allowance is reported without failing, because a check
that stopped every clone carrying one would be switched off. An unreadable
configuration file is reported rather than skipped, since silence on a file that
could not be parsed reads as approval.

## A linter with two sides

Every check the document linter shipped with was negative — rationale leaks,
unverifiable claims, counterfactuals, internal notes, unfinished markers, local
paths. All six ask whether a document contains something it should not. None
asked whether it contains something it must, so a document that silently omitted
a required section was reported clean. In a one-sided linter every false
negative makes the output look better than it is, which is the wrong direction
for a tool whose purpose is to stop overclaiming.

Artifact contracts declare the sections a document must carry, checked both for
present and for not empty — a heading with nothing under it satisfies a
word-search and satisfies nobody reading it. Pointing the first contract at this
project's own release notes immediately found v0.2.1 shipped without any
verification instructions.

## Claims about the outside world, caught unasked

The runtime already refused to record a verified claim about an external system
without a primary source, but that check only ran when the caller passed the
flag — so it protected whoever remembered they were talking about a remote
system, which is not the person who needs it. The seed case was an assertion
that a pinned action version did not exist: stated from recall, wrong, and
caught only because a human checked.

Fixing the detection exposed the gate behind it as unsatisfiable. It demanded a
`doc:` or `url:` citation and then rejected every one as unresolvable, so a claim
about the outside world could never be recorded as verified whatever the author
had actually read. Such a source now resolves as the operator's declaration —
nothing local can confirm it, and confirming it over the network is not
something this runtime does — and the record names which citations were asserted
rather than machine-checked, so a later reader sees the difference instead of
one uniform "verified".

The seeded fuzz harness caught the first version of that change accepting a
citation of control characters and encoded traversal.

## A portable manifest

A `plugin.json` at the repository root makes this installable by any client
implementing the Agent Plugins specification, alongside the host manifests,
which stay where their hosts look for them. The skill layout already conformed
exactly and the field vocabulary already matched; what was missing was a
manifest at the location every conformant client checks.

The description says plainly that the portable package carries skills and that
the action gate needs a host with hook support. Hooks are outside the v1 format,
so a client without them installs the skills and none of the enforcement, and a
governance tool that does not say so is mis-sold.

Conformance is asserted locally against the specification's closed field set
rather than by fetching anything — the schema URL in the manifest is a string,
never a request — because a manifest validated only by other people's installers
is exactly the shape that let the composite action stay broken for a fortnight.

## Upgrading

No migration. The archive format, the CLI surface and the host manifests are
unchanged; `trust` is a new command and the artifact contracts are opt-in via
`.godmode-docslint.json`.

One behaviour change worth knowing: a claim naming a third-party artefact at a
pinned version, or asserting what a released version does, is now detected as
external and recorded as a hypothesis unless it cites a source. Passing a
`doc:` or `url:` citation keeps it verified.

## Verifying

```
python -m unittest discover -s tests        # 464 tests
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . version --reconcile --brief
python scripts/godmode.py --project . trust
python scripts/godmode.py --project . docs --lint
```

The falsification harness is the one worth running deliberately, because it is
the only check here that proves the others can fail:

```
python -m unittest tests.test_gate_falsifiability -v
```

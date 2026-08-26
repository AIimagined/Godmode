# Ladder

Four tiers of onboarding, each one session's worth. Every command here is
walked through the real parser by `tests/test_ladder_doc.py`, so a tier
cannot name a command that does not exist. Print one tier at a time with
`godmode guide --tier N`.

## Tier 1 - day one

Initialise, look, and ask what to do next. Nothing here changes a file
outside the private archive.

```console
$ godmode guide
$ godmode init
$ godmode status
$ godmode doctor
$ godmode resume
```

## Tier 2 - a working session

Open a session so the record starts, checkpoint so it survives, and read
the quality list before claiming anything.

```console
$ godmode session open
$ godmode quality --format editor
$ godmode checkpoint --summary "what changed and why"
$ godmode attest full-suite --status ran --result "N tests OK"
$ godmode session close
```

## Tier 3 - a governed session

The gates. Each one encodes a failure that actually recurred; passing it is
cheaper than re-living the failure.

```console
$ godmode charter
$ godmode precheck --task "the work about to start"
$ godmode swallow
$ godmode minimality
$ godmode examples --check
$ godmode capabilities --reconcile
```

## Tier 4 - a fleet

Many agents, one record. Identity on every write, leases with a term,
the host's own approvals recorded beside the gate's decisions.

```console
$ godmode fleet
$ godmode approvals
$ godmode forecast --operation "git push --force"
$ godmode replay
$ godmode rollback
$ godmode governance
```

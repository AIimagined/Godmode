# Godmode v0.2.13

A policy declared is a policy kept.

Every gate this release adds follows the same shape: detection runs first
and always, deciding nothing on its own; a hard block only exists once a
project's own `.godmode-authorization-policy.json` names the duty; and
once a duty is declared, the ratchet only tightens, never loosens back to
silence by re-running the same command. Seven such gates land in this
release, one drift detector, one severity gate, one absorption gate, one
deletion gate, and the blast-radius evidence bar that scales how many
independent witnesses a claim needs to how much damage the claim licenses.
Alongside them, the README and marketplace listing are rewritten to state
only what a fresh checkout of this repository can currently reproduce, a
canonical `SECURITY.md` replaces host-specific copies with one pointer to
the threat model, and a repository-wide privacy test now scans every
tracked file instead of one.

## Upstream drift, checked instead of assumed

`godmode upstream --diff <package>` (Python, first-class, via
`importlib.metadata` and a real import of the top-level module) or
`--path <vendored-tree>` (a forked or fully-copied external repo, carrying
the same duty a lockfile dependency does) resolves what the target
actually ships and diffs it against the project's own equivalents, reusing
`godmode_atlas`'s existing symbol-extraction and name-similarity machinery
rather than a second implementation. Each upstream symbol with no
project-side name match needs
two separately-required verdicts, not one: an import disposition
(`adopt`/`extend`/`diverge-deliberately`/`n/a-different-surface`) and a
behavior verdict (`confirmed-we-have-it`/`confirmed-we-dont`/`unverified`).
A disposition recorded with no paired behavior verdict is refused twice,
once by the write path and once by an independent archive-append check,
so a hand-crafted record cannot slip past the API that would have refused
it. An unresolvable target never guesses: it writes a `stated-gap` verdict
naming the reason, and enumeration is capped with the same loud-cap
discipline the untrusted-content scanner uses, so a truncated diff says so
on the record rather than reading as a complete one. The duty itself is
requirement-driven: a project's compiled charter has to name the
`upstream-diff` obligation, for specific packages or for any dependency,
before the gate applies at all.

## Two sources of truth for one fact, named before they diverge

`godmode_minimality` gains a `duplicate-authority` finding class: small
literal collections across the repository, module-level string lists,
enum-like dict keys, name-hinted version-string literals, are fingerprinted
via `ast` and compared with the same near-duplicate machinery `Atlas`
already applies to code shape, now applied to data literals instead. Two
or more independent sites sharing 60% or more of their members are flagged
naming both; a fixture under `tests/` that exactly restates a source list
is exempt as the known-good sample it is, but two source-side matches, or
a near-but-not-exact test/source pair, still flag.

The declared counterpart is `paired-artifact`: a project states once that
two artifacts change together (`godmode paired-artifact declare`), and
`precheck` checks every later diff against that declaration, flagging a
change that touches exactly one declared half and naming which one. A
sweep of this repository under the new detector found `STATES`
(`godmode_register.py`) and `_REGISTER_STATES` (`godmode_invariants.py`)
byte-identical, a deliberate, already-documented hand-mirror that avoids
an import cycle, accepted as-is rather than treated as a defect.

## A scanner for the failure that never told anyone

`godmode swallow` is a static scanner for the shapes that discard a
failure instead of reporting it: an empty or pass-only `except`/`catch`
block, a bound exception name that's never referenced, a `{data, error}`
destructure that drops `error`, and a success-only-logging `try`. Python is
parsed as real `ast`; JS/TS is regex-shape, best-effort, and the module
docstring says so. Every finding is advisory on its own; the one hard
signal is a ratchet against `.godmode-swallow-baseline.json`, a per-file
count of un-exempted findings that a plain scan can only tighten
downward and `--update-baseline` can only hold or lower, never raise. A
`# godmode: swallow-ok <reason>` comment (or the `//` form in JS/TS)
exempts one site and its reason is always listed in the report; an
annotation with no reason exempts nothing. The tracked baseline for this
repository sums to 27 sites across 18 files, all `empty-except`, read
directly from `.godmode-swallow-baseline.json` in this repository, this
codebase's own established degrade-not-block idiom rather than an
unreviewed backlog.

## A claim that licenses more damage needs more than one witness

`record_claim` gains an opt-in `blast_radius` field
(`godmode claim --blast-radius ops-directed|sticky-side-effect|checksum-guard`):
a claim that declares one needs two or more INDEPENDENT witnesses among
its citations before a `verified` grade holds, not merely citations that
resolve. Independence is one documented predicate: two citations are the
same witness only when both their kind and their resolved target match,
a `file:` target drops its line locator so two reads of one file are one
witness, and two different citation kinds always count as independent of
each other. Two copies of one `cmd:` string, or the same file cited twice
at different lines, downgrade to `hypothesis` naming the bar that failed.
A claim that never sets `blast_radius` grades exactly as it did before the
field existed.

## A third-party tool's own error, read instead of assumed clean

A checker's own captured stdout and stderr, never persisted verbatim, can
now be tested against declared patterns for a named tool
(`godmode error-pattern register --tool <name> --pattern <regex>`). If a
verdict's fold lands on `confirmed` and a declared pattern matched inside
a checker whose command names that tool, the write is refused unless
`--tool-error-ack acknowledged-remediated` or
`acknowledged-deferred: <reason>` is present. `contested`, `refuted`, and
`witness-malformed` folds are never gated by this, only a `confirmed`
claims the output was clean. An undeclared tool gates nothing: the check
is opt-in per tool, not a blanket scan of every command's output.

## Absorbing an external repository, gated behind a declared license

Any external repository entering the work, a URL a command would fetch or
clone, a `--source-repo` flag, a remote-add of a non-dependency repo, is
now detected generically and classified alongside the operation's existing
category and tier, never in place of them. Detection alone decides
nothing: with no policy declaration, `godmode license check` records an
advisory only. Once a project's policy declares `external_absorption_gate`,
the operation is refused until `godmode license attest --repo <ref>
--classification <permissive|proprietary-no-redistribution|unlicensed|
copyleft-incompatible>` is on record for that repository, and anything
other than `permissive` also needs a `--clean-room-note` describing what
was read against what was written.

## A pre-check before a tracked file leaves, not an explanation after

`godmode_fence.deletion_verdict` asks, before a deletion the fence would
otherwise allow, whether a pre-check is on record. With no policy
declaration it stays advisory, recording what a pre-check would have
covered. Once a project's policy declares `deletion_provenance_gate`, the
deletion is refused until `godmode fence delete-precheck --path <p>
--history-read "..." --sole-carrier "..."` is on record, built on the same
reverse-impact traversal the atlas already provides rather than a second
implementation. A pinned evaluator's deletion stays denied regardless of
policy or attestation; deleting an untracked scratch file carries no
provenance obligation either way.

## The README and listing kit say only what this checkout can prove

The rewrite opens with the problem instead of a feature list, puts observe
mode ahead of any enforcement claim, and groups mechanisms, gate, verdicts,
register, measurement, trust, run governance, each behind its own
verify-yourself command. Host support is stated in tiers instead of one
combined number: the plugin host whose gate and session hook run live
every session this repository is worked in; two hosts that ship the same
plugin package and hooks convention but are not independently live-probed
under those hosts; and three instruction-file adapters that declare
`tool_call_interception` as `UNAVAILABLE` because none of them exposes a
pre-tool boundary. `docs/LISTING.md` is new: listing text per marketplace,
plus a read-only manifest audit. `tests/test_readme_commands.py` pins
every fenced `godmode` invocation in the README against the real CLI
parser, the same mechanism `tests/test_demo_doc.py` already runs against
`docs/DEMO.md`.

Alongside the rewrite: a canonical `SECURITY.md` at the repository root
replaces host-specific copies with one pointer to the threat model, and
`tests/test_repo_privacy.py` extends the coverage-map privacy check from
one file to every git-tracked file in the repository, checked against an
external term list that never ships in the repository itself. The
capability-coverage table gains seven new rows, one per gate and detector
in this release, each `covered` with a file and test pointer.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_upstream tests.test_minimality tests.test_swallow -v
python -m unittest tests.test_blast_radius tests.test_absorption_gate tests.test_deletion_provenance tests.test_tool_error_gate -v
python -m unittest tests.test_readme_commands tests.test_repo_privacy -v
python scripts/godmode.py --project . capabilities --reconcile
python scripts/godmode.py --project . docs --lint
python scripts/godmode.py --project . version --reconcile
```

`godmode capabilities --reconcile` reconciles clean on this repository: 81
capability entries, 14 detectors, 20 coverage rows (13 carried over, 7 new
this release), zero dead pointers across any of the three. `docs --lint`
is `clean`. The seven new test modules behind this release's gates
(`test_upstream`, `test_minimality`, `test_swallow`, `test_blast_radius`,
`test_absorption_gate`, `test_deletion_provenance`, `test_tool_error_gate`)
carry 165 tests between them. `version --reconcile` agrees once this
release is tagged; it reads `version-drift` on an untagged tree by design,
the same shape the two releases before this one also passed through.

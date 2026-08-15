Duplicate-authority drift detector and paired-artifact declarations (GAP-2).
`godmode_minimality.py` gains a `duplicate-authority` finding class:
small literal collections (module-level string-list constants, enum-like
dict keys, name-hinted version-string literals) are fingerprinted across
the whole repo via `ast`, and their member sets are handed to
`godmode_atlas._jaccard` - the same near-dup machinery `Atlas.duplicates()`
already applies to symbol name/body shingles, reused rather than rebuilt,
now applied to data literals instead of code shape. Two or more
independent sites sharing >=60% of members (`duplicate_authority_threshold`,
tunable, documented on `minimality_report`) are flagged naming both. An
exact match is exempt only when exactly one side lives under `tests/` - a
fixture intentionally restating a source list verbatim as a known-good
sample is the classic false positive this class of detector earns a bad
reputation from; two SOURCE sites, or a near-but-not-exact test/source
pair, still flag. The report also carries one advisory note naming the
magic-count anti-pattern (`assert len(x) == N`) and recommending a
subset/superset assertion instead - no code enforcement of that note in v1.

`godmode_precheck.py` gains the declared counterpart: `paired-artifact`.
A project states "these two artifacts change together" once
(`declare_paired_artifact`, a `decision` record namespaced
`paired-artifact:<label>` - the same reuse-an-existing-kind,
namespace-the-subject house pattern `removal:` and `reg:`/`reg-foreign:`
already use). It is project policy a session writes and revises, not a
generated snapshot like a static declared-config file. `precheck` - not
`godmode_fence.completion_audit` - checks every later diff against it,
because precheck already runs before work starts, while the missing half
is still cheap to add. A commit/diff touching exactly one declared half is
flagged naming which; both sides, or neither, is clean.
Advisory only, v1 - it never joins `precheck`'s `findings`/`verdict`, the
same treatment `foreign_precedents` already gets. `godmode_console.py`
wires `precheck --changed` (defaulting to the working tree, same as
`fence audit`) and a new `godmode paired-artifact declare` command.

Population sweep of this repository found real candidates: `STATES`
(`godmode_register.py`) and `_REGISTER_STATES` (`godmode_invariants.py`)
are byte-identical, deliberately hand-mirrored to avoid an import cycle
(already documented in both modules' own comments, already guarded by
`tests.test_register`) - accepted as-is, and a strong candidate for its
own `paired-artifact` declaration rather than a code fix. `EVENT_KINDS`
(`godmode_constants.py`) and `MASKS`'s keys (`godmode_compress.py`) share
51.9% membership - under the auto-detector's threshold, so not flagged by
it - but are exactly the kind of pair worth an explicit `paired-artifact`
declaration despite that, since the auto-similarity score and "should a
human be told when one changes without the other" are different
questions; recorded here as the two mechanisms' worked example rather than
written into a live archive, since this repository ships no committed
`godmode-state` archive to declare it into.

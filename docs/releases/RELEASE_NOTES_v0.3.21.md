# Godmode v0.3.21

The proof release. 0.3.20 was tagged on a local suite green on one OS and
one interpreter; the CI matrix then went red on both Windows legs with the
tag already public, and no GitHub release was published for it. The rule
"CI green before the tag" had lived in maintainer notes, where nothing
could refuse. This release makes it a gate, and ships the two fixes the
matrix found.

## The tag gate

A tag push is a release, and CI on the tagged commit is its proof. The
pre-action gate now reads every form of a tag push (`refs/tags/<tag>`, a
bare tag name, `tag <name>`, `--tags`, `--follow-tags`), resolves each
tag's commit, and denies until a `ci` attestation with status `ran` names
that commit green:

    godmode attest ci --status ran --result "v0.3.21 <sha7> green" --evidence <run url>

The refusal runs before any staged capability is spent, so the retry after
attesting is the same exact command and goes through. Native by design:
the proof is a record with the run URL as evidence, not a call to a forge
API from a hook.

## What the matrix found

- A zero atlas budget scanned files on Windows Python 3.11: `elapsed >
  budget` read false under that interpreter's 15.6 ms clock. A budget
  already spent is spent at zero.
- A bound role document in a next-action demand was rendered as an
  absolute path when the project path carried an 8.3 element (the CI
  runner's `RUNNER~1` temp directory). Both sides of `relative_to` are
  resolved now; the demand reads `write it in docs/LESSONS.md` again. The
  regression test reproduces through a symlinked project on any OS and
  through the 8.3 name on Windows, with no platform skip.

## Verifying

- `python -m unittest tests.test_tag_push_ci_gate` - a tag push is denied
  without a green `ci` attestation for its commit, a branch push is not,
  a red or other-commit attestation does not count, and the staged
  capability survives the refusal.
- `python -m unittest tests.test_atlas_registry tests.test_brief_next_actions`
  - the zero budget under a frozen clock; the aliased project path.
- CI: run 34219467603 on 6c83fbe was green on all ten legs before this cut;
  the cut commit's own run must be green and attested before the tag is
  pushed, which the gate above now enforces.

Full detail per change: `CHANGELOG.md`.

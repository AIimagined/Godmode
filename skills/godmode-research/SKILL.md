---
name: godmode-research
description: "Study an outside source repository in a fixed order - licence, tree, the two or three implementing source files, line-cited receipts - and record both an import verdict and a behaviour verdict, refusing adopt or extend on a surface-only reading. Use when an outside codebase is being surveyed for a mechanism worth borrowing. Not for rebuilding that mechanism under Godmode names, and not for root-causing a failure in this repository."
---

# Godmode Research

## Outcome

An outside source is judged on what was actually opened, not on its
landing page: every file read carries a receipt with its line range and a
digest of the slice, the licence is classified before anything else, and
the recorded verdict pair (import and behaviour) is refused as adopt or
extend unless a receipt names a source file rather than a README, a doc or
a release note.

## Use

- An outside repository is being surveyed for a mechanism this project might borrow.
- An earlier survey recorded a verdict and its reading depth is in doubt.
- A source's licence has to be classified before any of it is studied closely.
- A survey needs to show, per source, how many files were opened and whether it stayed on the surface.

## Do Not Use

- Rebuilding a studied mechanism in stdlib under Godmode names and pinning it with a reproducing test - that is `godmode-replicate`.
- Root-causing a failure inside this repository - that is `godmode-investigation`.
- Independently rechecking a verdict another pass already accepted - that is `godmode-second-look`.

## Deterministic Execution Flow

1. **Licence first.** `godmode license check --operation "<the survey, naming the source>"` - whether an operation naming that source may proceed at all. Then read the licence file with a receipt: `godmode read --source <name> --path LICENSE --root <local checkout of the source>`, and classify it: `godmode license attest --repo <name> --classification <permissive|proprietary-no-redistribution|unlicensed|copyleft-incompatible> --clean-room-note "<what was read versus written>"` (the note is required for anything but permissive).
   - Fallback: a refusal from `license check`, or a classification other than permissive, ends the survey at `import_verdict: skip` - record that and stop.
2. **Tree, then the implementing files.** List the source's tree and name the two or three files that implement the claimed mechanism. `godmode upstream --path <local checkout> --skills <keyword>` lists the skill and doc files that mention the mechanism, with line numbers, and records nothing - a pointer to where the code lives, never a substitute for reading it.
3. **Receipt every implementing file.** `godmode read --source <name> --path <implementing file> --root <local checkout> --lines <a-b>` - one receipt per file opened: path, line range, and a digest of the slice.
4. **Measure the reading depth.** `godmode parity --sources` - per source, `files_opened` and `surface_only`. A source still `surface_only: true` has not been read; go back to step 3.
5. **Record both verdicts.** `godmode remember --kind decision --subject "absorb:<name> <date>" --value "<finding> import_verdict: <adopt|extend|diverge|skip|exists|unread|n-a> behaviour_verdict: <confirmed-have|confirmed-dont|unverified>" --evidence receipt:<name>:<implementing file>` - refused `surface-only` when adopt or extend cites only README, docs or release-note receipts, and refused naming either missing verdict.
6. **Dispose each symbol with no counterpart when comparing a copied tree.** `godmode upstream --path <local checkout> --dispose <SYMBOL>=<adopt|extend|diverge-deliberately|n-slash-a-different-surface>:<confirmed-we-have-it|confirmed-we-dont|unverified> --evidence receipt:<name>:<file>`.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never record adopt or extend from a README, doc or release-note reading; the verdict for a surface read is unread, skip or diverge.
- Never study a source's code before its licence is classified in step 1; instead classify the licence first and stop if it forbids the use.
- Never name the studied source in shipped text (code, docs, skills, changelog); instead describe the mechanism in Godmode's own words and keep the name in the private record.
- Never copy source text into this repository; a mechanism is carried over only by `godmode-replicate`, rewritten under Godmode names.
- Never skip the receipt for a file that the verdict relies on; an unreceipted read is invisible to `parity --sources`.

## Acceptance

- `godmode parity --sources` reports `surface_only: false` for every source whose verdict is adopt or extend.
- Every `absorb:` decision carries both verdicts and at least one receipt naming a source file.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.

---
name: godmode-host-sync
description: "Detect every installed AI CLI host, reconcile Godmode's hook manifests into each host's native format, and drift-repair the wiring with a shown diff before anything trusts interception. Use when a host's wiring needs reconciling or repairing after an install, an update, or reported drift. Not for a plain walkthrough of hook mechanics with no drift repair involved, or for authorizing an unrelated protected operation."
---

# Godmode Host Sync

## Outcome

Every installed AI CLI host carries a live, correct hook manifest in its own
native format, and any drift between what Godmode declares and what a host
actually has wired is shown as an explicit diff before it is repaired.

## Use

- A host's wiring needs checking after an install, an update, or a reported miss.
- A newly detected host needs Godmode's manifests reconciled into its native hook format.
- A hook manifest looks stale, missing, or conflicting and the exact repair should be shown before it lands.
- A protected-operation probe needs to prove the hook mechanism still denies what it should.

## Do Not Use

- Explaining what a single hook event does in isolation, with no wiring check involved.
- Previewing or authorizing an unrelated protected operation - that is `godmode-governance`.
- Diagnosing why a specific test fails - that is `godmode-investigation`.
- Proposing a brand-new skill because a workflow keeps recurring - that is `godmode-skill-forge`.

## Deterministic Execution Flow

1. **Read current wiring.** `godmode hooks status` - always exits 0; read
   `wire_state` per host, `host_registration` per host, and `verdict` for the
   detected host. Add `--matrix` to report whether the host-capability tables
   have drifted from what `godmode_reach`/`HOST_CAPABILITIES` would generate
   (exit 1 if so, exit 2 on the R-0 no-reference refusal) instead of one
   host's proof - pair it with `--write` to actually regenerate the doc - or
   `--git` to read the git-hook backstop instead of host wiring.
2. **Preview reconciliation.** `godmode hooks wire --all --dry-run`, run from
   the **primary checkout** - it prints one
   `[CREATE]/[UPDATE]/[OK]/[CONFLICT]/[INVALID]` line per host and writes
   nothing.
   - Fallback: from a linked worktree, `--host codex` (and `--all`, which
     wires codex too) refuses with `"... refuses from a linked worktree; run
     it from the primary checkout"` (exit 2) - switch to the primary
     checkout the refusal names, or wire a host without that restriction
     (for example `--host opencode`) to keep working from the worktree.
3. **Apply only after reading the preview.** `godmode hooks wire --all`
   (drop `--dry-run`). A file that differs from what Godmode would write
   reports `CONFLICT` and is left untouched unless `--force` is given, and
   `--force` still refuses a malformed (`INVALID`) file rather than
   overwriting it - fix or remove that file by hand first.
4. **Prove the mechanism, not just the file.** `godmode hooks probe --host
   <host>` sends a synthetic protected operation through the real hook and
   records whether it was denied. A probe that reports `state: HARD` proves
   this project's own hook script recognises and denies the operation end to
   end; it does not prove the host's own runtime calls that hook on a real
   tool call - only a genuine protected command inside that host's session,
   chronicled as a live refusal, proves wiring.
5. **Roll up host health.** `godmode doctor --host <host>` for one host's
   presence, interpreter-on-PATH, archive-writable, and interception grade -
   fast and targeted. The un-scoped `godmode doctor` also runs but re-verifies
   the whole archive chain, so it is slower on a large one.
6. **Stop on an unrecoverable shape.** An `INVALID` file, a `doctor --host`
   `issues` entry naming a `documented gap`, a `reach` feature whose `status`
   is `no` on the host that matters, or a probe whose `state` is not `HARD`
   are each reported verbatim rather than forced past.

## Must Not

- Never wire or force-overwrite a host's hook file: preview it first with
  `--dry-run` and show that output before applying anything.
- Never force past a file `hooks wire` reports as INVALID: fix or remove it
  by hand instead, since `--force` cannot get past that shape.
- Never treat a passing probe as proof of live wiring: only a genuine
  protected command inside that host's own session proves it.
- Never edit a host's config file to route around a linked-worktree refusal:
  switch to the primary checkout the refusal names instead.
- Never invent a host name; only the hosts `hooks status`/`hooks wire`
  already declare are in scope for reconciliation.

## Acceptance

- `hooks status` reports a `wire_state` map covering every declared host,
  and a `tier` for the host it is reading, so drift is visible before any
  repair is attempted.
- A dry-run preview names exactly what an apply would create, update, or
  refuse - and writes nothing.

If an assertion cannot be proved, report the unmet assertion and the next
safe action rather than the outcome it was meant to prove.

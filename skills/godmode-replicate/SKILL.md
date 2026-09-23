---
name: godmode-replicate
description: "Rebuild a mechanism already studied in a reference implementation, in stdlib under Godmode's own names, then pin it with a reproducing test proven able to fail, cite the reference receipt and the replicating test on the host row, and scrub private terms before committing. Use when a host or platform row is marked unverifiable while its reference sits unread or unreplicated. Not for a first survey of an unread codebase, and not for an interactive session proof."
---

# Godmode Replicate

## Outcome

A host or platform row is earned by replication, not by a note: the
reference's implementing files are receipted, the mechanism is rebuilt in
stdlib under Godmode's names, a reproducing test is shown to fail when the
rebuild is broken and pass when it is whole, the row cites both, and the
commit carries no private term.

## Use

- A host or OS row reads `unverifiable` while a reference implementation of that path is on record but unread.
- A studied mechanism has been judged worth borrowing and now has to exist in this project's own code.
- The host-capability matrix refuses because a hook host cites no reference and no replicating test.
- A replication is written and needs its pinning test proven able to fail before it counts.

## Do Not Use

- Surveying an outside codebase that has not been read yet - that is `godmode-research`.
- Confirming a host's wiring with a live protected command inside that host's own IDE - that is `godmode-host-sync` (`hooks probe`).
- Copying a reference's code verbatim into this repository - never; the rebuild is written under Godmode's names.

## Deterministic Execution Flow

1. **Confirm the reference was read, not skimmed.** `godmode parity --sources` - the reference must show `surface_only: false`. For each implementing file the rebuild follows, a receipt must exist: `godmode read --source <name> --path <implementing file> --root <local checkout> --lines <a-b>`.
   - Fallback: a surface-only or missing reference routes to `godmode-research` first; nothing is rebuilt from a README.
2. **Rebuild under Godmode's names.** Write the mechanism in stdlib, in this project's own modules and vocabulary - the reference's input shape and expected output, not its text.
3. **Prove the pinning test can fail.** `godmode plant <name> --command "<the reproducing test>" --file <the rebuilt module> --replace "<a load-bearing line>" --with "<a broken line>"` - the guard must fail on the planted break, and the file is restored.
   - Fallback: a test that stays green on the break does not pin the rebuild; strengthen it and plant again before step 4.
4. **Attest it green on the real rebuild.** `godmode verify <name> --command "<the reproducing test>"` - runs the check and attests its exit code.
5. **Cite both on the row.** `godmode claim "<host or path> replicated from its reference" --grade verified --cite seq:<the receipt's own sequence> --cite cmd:"<the reproducing test>" --verify` (a `receipt:` cite is for absorb decisions; a claim cites the receipt by its sequence, or it is downgraded), then check the matrix: `godmode hooks status --matrix` - read-only without `--write`; it refuses (exit 2) while any hook host cites no reference and no replicating test.
6. **Scrub before committing.** `godmode privacy --repo` - tracked-tree scan for home paths, emails, addresses and secret shapes, each named by path and line; and the project's deny-name check (`quality/checks/no_external_source_names.py`) must report no new finding for the added lines.
   - Fallback: outside a git repository `privacy --repo` refuses (it scans tracked files only); commit from the repository the replication lives in, never skip the scan.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never rebuild from an unreceipted or surface-only reading; step 1 comes first.
- Never count a pinning test that has not failed on a planted break; `plant` comes before `verify`.
- Never copy the reference's text, identifiers or comments; rewrite under Godmode's names.
- Never name the reference in shipped text; the name lives only in the private record and the receipt.
- Never mark a row verified while `hooks status --matrix` still refuses it; instead fix what the matrix names and rerun it until the row passes.

## Acceptance

- The replicating test fails on a planted break and passes on the rebuild, both attested.
- The row cites a source receipt and the replicating test, and the privacy scan of the commit is clean.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.

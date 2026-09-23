---
name: godmode-codegraph
description: "Query a local, on-demand code dependency graph to answer who calls, who imports, and what blast radius a change carries, before spending an unnecessary full read on a large module, refreshing the saved graph from the archive first when it looks stale. Use before an edit whose impact or required retests are not yet named. Not for a routine read with no graph question involved, or for chasing an already-failing check."
---

# Godmode Codegraph

## Outcome

Before a change lands, its blast radius - the obligations, modules, and
required retests that depend on what is about to change - is answered from a
saved, on-demand graph derived from this project's own archive, rather than
by opening every file that might be affected.

## Use

- Who depends on this module, obligation, or file before it is edited.
- Which tests must be retested for a set of changed paths.
- The saved graph looks stale (a rebuild is needed) or its snapshot needs
  proving against the archive it was derived from.
- A large file's dependents should be read from the compressed graph before
  a raw full-file read is spent on it.

## Do Not Use

- Reading one small file's own contents when nothing needs its dependents -
  read the file directly.
- Investigating why one specific test already fails - that is
  `godmode-investigation`.
- Rebuilding the loop-record signature history for a stalled retry - that is
  `atlas loop`, a different subcommand with a different evidence shape.

## Deterministic Execution Flow

1. **Prove the saved snapshot before trusting it.** `godmode atlas graph
   verify` - rebuilds the graph fresh in memory (without saving it) and
   compares its hash against the last saved snapshot; reports `verified:
   false` with a `reason` naming why - `no graph snapshot found; run atlas
   graph rebuild` on first use, `graph snapshot is stale; run atlas graph
   rebuild` once the archive has moved on - and leaves the saved snapshot
   untouched either way. Needs an initialized archive (`godmode init` first
   on a project that has none).
2. **Rebuild only when step 1 says to.** `godmode atlas graph rebuild` -
   derives nodes and edges fresh from the archive's own records (obligations
   and their `blocked_by` edges, sprint items, `retested_by` attestations,
   supersession, and citations) and overwrites the saved snapshot. Run this
   only after `verify` reports no snapshot or stale - never to make a
   failing `verify` pass, since overwriting the snapshot destroys the only
   record that it had drifted.
3. **Ask the graph, not the files.** `godmode atlas graph query
   <node> [--depth N]` - node ids look like `obligation:<subject>`,
   `module:<dotted.name>`, or `file:<path>`; loads the snapshot step 1
   proved rather than rebuilding. Returns `impact` (what transitively
   depends on the node over current `depends_on` edges) and `must_retest`
   (attestations reachable over `retested_by` edges).
   - Fallback: an id the graph has never seen returns `unknown_node: true`
     and refuses (exit 1) rather than guessing - rebuild first, or confirm
     the id's exact form (`obligation:`/`module:`/`file:` prefix).
4. **Name what a working-tree change touches.** `godmode atlas closure
   [--changed PATH...] [--depth N]` - dependents of what changed that were
   not themselves changed; defaults to the current working tree when no
   paths are given. Refuses (exit 1, `graph unverified: run atlas graph
   rebuild`) if the saved snapshot fails its own verify, re-checking step 1's
   proof before trusting anything. Exits 0 even when nothing changed
   (`verdict: nothing-changed`).
5. **Run only the retests the graph names.** `godmode session open` (if none
   is already open) then `godmode retest --run` - executes the retest
   commands the archive itself pins to the changed files, one command per
   runner, and attests the exit code.
6. **Read the raw file only after the graph has been asked.** A full-file
   read is the fallback for a node the graph has no edges for yet, or for
   understanding logic the graph cannot represent (control flow inside a
   function) - not the first move on a large file.

## Must Not

- Never trust a graph's `impact` or `must_retest` result; run `atlas graph
  verify` first, since a stale snapshot names dependents that no longer hold.
- Never run `atlas graph rebuild` merely to erase a failing verify: that
  destroys the saved snapshot's only record that it had drifted, so fix or
  explain the drift first instead.
- Never read a large file in full before checking the graph: query it first
  for who calls it and what it would break.
- Never guess at a node id after `unknown_node: true` - rebuild or confirm
  the exact prefixed form instead.
- Never skip `atlas closure` before a change described as low-risk; the
  point of the graph is that "low-risk" is a claim the archive can check.

## Acceptance

- `atlas graph rebuild` derives a fresh graph from the archive and reports
  its hash, deterministically, from the same archive content every time.
- `atlas closure` names every dependent of a changed file that was not
  itself changed, before a blast-radius edit is trusted.

If an assertion cannot be proved, report the unmet assertion and the next
safe action rather than the outcome it was meant to prove.

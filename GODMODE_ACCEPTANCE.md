# Godmode Acceptance Contract

Godmode is accepted only from observable local evidence. This matrix connects the product contract to a repeatable proof surface; it is not a claim that an unavailable host integration is automatically enforced.

## Core evidence gates

| Gate | Required behavior | Primary proof |
| --- | --- | --- |
| E-01 | Initialize a project-bound private archive without writing continuity files into the working tree | `godmode init`; anchor isolation test |
| E-02 | Reconstruct branch, head, worktree, file categories, and current changes on demand | `godmode inspect`; inventory tests |
| E-03 | Resume from bounded structured evidence and disclose omitted material | `godmode resume`; `context why` |
| E-04 | Keep primary records append-oriented, atomic, ordered, and hash chained | chronicle verification and tamper test |
| E-05 | Reject secret-shaped values before persistence | privacy rejection test; `godmode privacy` |
| E-06 | Detect stale, drifting, phantom, contradictory, over-capacity, and unproven state | detector test; `context status --scan` |
| E-07 | Stop a repeated failed hypothesis after three recorded failures | repeat-loop detector test |
| E-08 | Classify read-only operations without authorization friction | action-classification and CLI guard tests |
| E-09 | Fail closed for protected or unknown mutations | guard exit-code test |
| E-10 | Bind protected authorization to one project-local, exact, expiring, single use | capability issue/consume/replay test |
| E-11 | Preview impact without executing the operation | `godmode guard` reports `executes_operation: false` |
| E-12 | Preserve branch and worktree observations without automatic Git mutation | `godmode branches`; static runtime review |
| E-13 | Record database, version, sprint, documentation, plan, and checklist facts privately | corresponding CLI commands plus archive history |
| E-14 | Compare only an explicit local reference and copy no content | `godmode parity`; URL rejection in parity |
| E-15 | Export a bounded sanitized context report, never the raw archive | `godmode export`; export metadata |
| E-16 | Operate with no daemon, listener, telemetry, prompt interception, or model proxy | privacy contract and static import test |
| E-17 | Use zero idle network, compute, and token budget | on-demand process architecture; no background registration |
| E-18 | Create no skill until a repeated, evidenced gap passes routing and behavior gates | forge rejection and generation tests |
| E-19 | Merge overlapping capability proposals into one original responsibility | skill-forge contract and routing boundary review |
| E-20 | Report evidence limits honestly and avoid perfect-memory claims | context brief `limits` and user-facing reports |

## Context continuity gates

| Gate | Required behavior | Primary proof |
| --- | --- | --- |
| CTX-01 | Bind context to stable Git common-directory identity or a salted non-Git identity | anchor tests |
| CTX-02 | Distinguish branch, head, worktree, remote identity, and repository inventory | snapshot and branch observation |
| CTX-03 | Prefer invariants, decisions, obligations, checks, incidents, and recent changes within a budget | context-brief selection test and inspection |
| CTX-04 | Rebuild derived context from primary records | `context rebuild` and archive replay |
| CTX-05 | Explain why context is present, absent, stale, or excluded | `context why`; detector codes |
| CTX-06 | Never persist raw prompts, transcripts, source bodies, or credentials | privacy scan and inventory-body test |
| CTX-07 | Record recoverable checkpoints, hypotheses, outcomes, and next actions | checkpoint command and history |
| CTX-08 | Label incomplete coverage rather than silently assuming freshness | doctor/status issue model and private source preflight |

## Enforcement gates and their proof commands

Each gate is proven by a command that exits non-zero on violation; CI runs the
starred ones on every change.

| Gate | Proof command |
| --- | --- |
| Controls actually enforce (E-05, E-09, E-10) | `selftest`* and the 13-cell `grid`* |
| Staged failures are caught (E-01..E-17, CTX-03..CTX-08) | `scenarios`* (15 staged, each bound to its ID) |
| Test weakening blocks completion (E-05) | `integrity` (nine §16.2 monitors) |
| Zero network use is captured, not promised (E-07, E-16-arch) | `netgate`* (plant-proven socket audit) |
| A change carries its release note (CTX-07) | `changelog check`* |
| Repetition is stopped from records (E-03, E-07-loop) | `loop`, `mistakes`, `watch` |
| Secrets stop at every boundary (E-06, SEC-007) | `egress --staged`, `privacy`, archive write scan |
| Status has one writer and no phantoms (E-17, CTX-04) | `status survey` / `status remaining` |
| Versions, docs, manifests, locales agree | `version --reconcile`*, `docs --reconcile`, `bindings`*, `locale check`* |
| The dependency claim validates externally | `sbom --gate`*, `checksums`* |
| Routing evals execute against snapshots | `evals`* |
| Configs fail with a field path | `config check`* |
| Plans need specs and survive handoff (CTX-01, CTX-02) | `planmode` chain, `rewind`, `drift` |
| Blast radius is classified outside model output (E-16) | `environment`, `db --propose` (E-15) |
| Removals stay explicable (CTX-03) | `removal why` |

## Release sequence

1. Run `python -m compileall scripts hooks tests` from the plugin root.
2. Run `python -m unittest discover -s tests -v`.
3. Validate every `SKILL.md` with the host's official skill validator.
4. Validate all three host manifests — `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.grok-plugin/plugin.json` — with `bindings` (drift fails) and each host's official validator where available.
5. Run a CLI lifecycle smoke test in an isolated temporary project and state directory.
6. Run the private clean-room release scan across all three manifests; no research-source identity or private owner identity may occur in packageable files.
7. Inspect package contents and confirm every planning, checkpoint, handoff, decision, lesson, research, and source-ledger path is excluded.
8. Run the full gate battery above; every starred command must exit zero.

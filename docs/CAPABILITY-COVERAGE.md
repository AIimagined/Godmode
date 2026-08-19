# Capability coverage

What godmode covers, with what surface, at what honesty grade. This is not a
comparison to any other product — it answers one question only: for each
capability class below, is the coverage `covered` (surface pointers resolve
to shipped code and tests), `partial` (some of the class is mechanized, the
rest is a stated boundary), or explicitly `not-claimed` (a scope boundary,
stated so nobody assumes it by omission).

A `reconcile` check (`godmode capabilities --reconcile`) enforces this table
both directions: a `covered` row's pointers must resolve, and a `partial` or
`not-claimed` row's pointers must NOT resolve — the moment a "not yet"
pointer starts resolving, the status is stale and the check goes red until
someone updates the row.

| Capability class | Status | Surface |
|---|---|---|
| Session continuity across restarts | covered | Continuity archive, checkpoint, and resume (`file:scripts/godmode_runtime/godmode_chronicle.py`, `file:scripts/godmode_runtime/godmode_console.py`, `test:tests/test_chronicle_cache.py`, `test:tests/test_context_recovery.py`) |
| Process discipline: verification, red-before-green shape, executable plan acceptance | partial | Mechanized: step attestation, the red-before-green integrity monitor, and plan-contract acceptance commands (`file:scripts/godmode_runtime/godmode_attest.py`, `file:scripts/godmode_runtime/godmode_integrity.py`, `file:scripts/godmode_runtime/godmode_plan.py`, `test:tests/test_godmode_runtime.py`, `test:tests/test_source_integrity.py`). Not claimed: workflow choreography (design-dialogue-then-plan-then-dispatch sequencing, code-review orchestration, worktree management) — godmode can enforce that a declared workflow was followed via a charter rule plus attestation, but it is not itself a workflow suite. |
| Claim admissibility and eval rigour | covered | Witness-plus-independent-checker verdicts, deterministic grader vocabulary, and the experiment ledger (`file:scripts/godmode_runtime/godmode_verdict.py`, `file:scripts/godmode_runtime/godmode_evals.py`, `file:scripts/godmode_runtime/godmode_guardrails.py`, `test:tests/test_verdict.py`, `test:tests/test_eval_registry.py`, `test:tests/test_experiment_ledger.py`) |
| Minimality and reinvention pressure | covered | A single ranked minimality report aggregating duplicate/orphan symbols, unexercised surfaces, speculative seams, and charter decay (`file:scripts/godmode_runtime/godmode_minimality.py`, `test:tests/test_minimality.py`) |
| Approval gating and scope containment | covered | Sentinel classification, scope fencing, and the capability broker (`file:scripts/godmode_runtime/godmode_sentinel.py`, `file:scripts/godmode_runtime/godmode_fence.py`, `test:tests/test_sentinel_policy.py`, `test:tests/test_scope_fence.py`) |
| Content trust and injection defense | covered | Settings/MCP/skill/agent/command content scanned for instruction-shaped and secret-shaped text (`file:scripts/godmode_runtime/godmode_trust.py`, `test:tests/test_trust.py`) |
| Session burn measurement | covered | Host-transcript counts only — tool calls, commands, tests, token usage, turns — content-free by construction (`file:scripts/godmode_runtime/godmode_session_log.py`, `test:tests/test_session_log.py`) |
| Prose-restyling / token-burn reduction | not-claimed | Roadmap only. Godmode measures burn (session-log counts) and bounds its own context (a capped session brief); rewriting a host's or a model's output prose to use fewer tokens is a host output-style concern, not a native godmode mechanism, and is not claimed here. |
| Observe posture: advisory-only gating with would-have-caught reporting | covered | Policy-declared observe mode converts every blocking path to a recorded advisory, announced at session start and surfaced by assess; digest renders counts only. The declaration file (`.godmode-authorization-policy.json`) is itself a protected surface for governed sessions — a governed tool-call write to it asks/denies the same as `.git/`/`.env` — and entry/exit are chronicled the moment either is next observed by a live policy read, not only via the per-call advisory that follows (`file:hooks/godmode_session_hook.py`, `file:scripts/godmode_runtime/godmode_roi.py`, `file:scripts/godmode_runtime/godmode_sentinel.py`, `test:tests/test_observe_mode.py`, `test:tests/test_gate_usability.py`) |
| Graduated starting postures | covered | `init --profile novice|standard|strict` sets starting policy on the tighten-only ratchet; no profile can loosen an explicit setting (`file:scripts/godmode_runtime/godmode_profile.py`, `test:tests/test_profiles.py`) |
| Recurring-ask surfacing | covered | Request-ledger clusters repeated asks across sessions into SOFT charter-rule proposals; term display is redaction-guarded, promotion is human-only (`file:scripts/godmode_runtime/godmode_recurrence.py`, `test:tests/test_recurrence.py`) |
| Doc freshness advisories | covered | Advisory-only lint for open markers without a dated check and living-doc title collisions without a supersedes pointer (`file:scripts/godmode_runtime/godmode_docslint.py`, `test:tests/test_docs_lint.py`) |
| Demonstration script | covered | A two-minute terminal walk-through whose commands are pinned against the real CLI parser (`file:docs/DEMO.md`, `test:tests/test_demo_doc.py`) |
| Upstream drift detection | covered | When a project tracks, forks, or vendors an external codebase, paired verdicts compare what was imported against how it now behaves; requirement-driven, advisory unless a tracking policy is declared (`file:scripts/godmode_runtime/godmode_upstream.py`, `test:tests/test_upstream.py`) |
| Duplicate-authority detection | covered | Flags two in-repo sources of truth for the same decision and requires a paired-artifact declaration naming the winner (`file:scripts/godmode_runtime/godmode_minimality.py`, `test:tests/test_minimality.py`) |
| Error-handler regression detection | covered | AST scan for exception handlers that silence failures; baseline ceilings auto-tighten downward on every scan and a live regression fails every invocation (`file:scripts/godmode_runtime/godmode_swallow.py`, `test:tests/test_swallow.py`) |
| Blast-radius evidence bar | covered | Operations-directed claims need independent witnesses; cosmetically distinct citations of one witness never count twice (`file:scripts/godmode_runtime/godmode_attest.py`, `test:tests/test_blast_radius.py`) |
| External-tool error severity | covered | A verdict citing a declared tool's run is gated on that run's errors being acknowledged, not silently passed over; undeclared tools are unaffected (`file:scripts/godmode_runtime/godmode_verdict.py`, `test:tests/test_tool_error_gate.py`) |
| External-repo absorption gate | covered | Any clone, vendor, or copy of an external repository is gated behind a declared license policy; undeclared stays advisory, declarations ratchet tighten-only (`file:scripts/godmode_runtime/godmode_sentinel.py`, `test:tests/test_absorption_gate.py`) |
| Deletion provenance | covered | A tracked file's deletion requires a provenance pre-check under a declared policy, and a pinned evaluator's deletion is denied regardless (`file:scripts/godmode_runtime/godmode_fence.py`, `test:tests/test_deletion_provenance.py`) |
| Host pre-tool interception, proven not asserted | partial | Five-level scale (`UNAVAILABLE`/`SOFT`/`PARTIAL`/`HARD`/`DEGRADED`), computed from chronicled live proof records plus registration state, never from a host's name; an end-to-end harness drives the real hook subprocess per host dialect and asserts hook exit code, decision envelope, simulated host interpretation, and real filesystem/git state together (`file:scripts/godmode_runtime/godmode_hookproof.py`, `file:scripts/godmode_runtime/godmode_hostevent.py`, `file:tests/e2e/harness.py`, `file:tests/e2e/test_host_e2e.py`, `test:tests/test_hookproof.py`, `test:tests/test_failure_semantics.py`, `test:tests/e2e/test_release_gate.py`). Codex and Grok have since met that condition on this machine: a probe run from inside each host's own real session records an interception proof and `hooks status` reads `HARD` for both, which is what the live-host layer (`file:tests/e2e/test_codex_e2e.py`, gated by `GODMODE_E2E_CODEX`/`GODMODE_E2E_GROK`) exists to establish. A proof is per-machine and per-install: it grades the checkout it was recorded against, never a claim that any other operator's Codex or Grok is proven. Not claimed: a `HARD` grade for Cursor or Gemini in any checkout — neither host is installed here, so both stay `PARTIAL`/`SOFT`/`UNAVAILABLE` (see `README.md`'s Host support table) until the same layer is run against that host's own real binary and passes. |
| Structural context cache | partial | Mechanized: an incremental per-project index — files, top-level Python classes/functions/imports via `ast`, file-level entries for every other language — keyed by content hash so an unchanged file is never re-parsed, stored as names and hashes only in the state home, and rendered as a bounded outline by `godmode context structure` (`file:scripts/godmode_runtime/godmode_structure.py`, `test:tests/test_structure_index.py`). Not claimed: method-level symbols, call graphs, control-flow and data-flow tiers, non-Python symbol extraction — the source ladder above the MVP is roadmap, stated here so nobody assumes it by omission. |

## Regenerating this table

The table is authored, not generated — a table that describes itself
correctly cannot substitute for the reconcile check. Run:

```
godmode capabilities --reconcile
```

after any change to the surfaces named above. A `covered` row whose pointer
stops resolving, or a `partial`/`not-claimed` row whose pointer starts
resolving, is a red exit, not a documentation nit.

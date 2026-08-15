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

## Regenerating this table

The table is authored, not generated — a table that describes itself
correctly cannot substitute for the reconcile check. Run:

```
godmode capabilities --reconcile
```

after any change to the surfaces named above. A `covered` row whose pointer
stops resolving, or a `partial`/`not-claimed` row whose pointer starts
resolving, is a red exit, not a documentation nit.

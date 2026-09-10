# SWE-EVO and ExecCritic — research brief for Godmode

**Status:** research intake for the cycle defined in `docs/PROBLEM-STATEMENT-AND-PRD.md`
**Repo:** https://github.com/AIimagined/Godmode
**Audience:** the agent implementing Phase 1 detectors and fixtures
**Does not replace:** `docs/CAPABILITY-COVERAGE.md`, `GODMODE.md`, the PRD

Use this file when implementing F1 (iteration trap), F3 (compounding / long horizon), F5 (reward hacking / test sabotage), F7 (instruction conflict), F10 (false completion), and F11 (planning miss).

Do not treat paper percentages as Godmode SLAs. Encode the *contracts* the papers measured. Do not add network, model calls, or runtime dependencies to reproduce either benchmark.

---

## 1. Why these two papers

The PRD named two structural failures:

- Long chains decay. Isolated-issue skill does not transfer to release-sized work.
- "Tests pass" is not evidence when the same trajectory wrote the tests.

SWE-EVO is the measurement of the first. ExecCritic is the measurement of the second.

| Paper | Question | Benchmark | Headline (that study's measurement) |
|---|---|---|---|
| SWE-EVO (arXiv:2512.18470, v6 2026-05-22) | Can an agent ship a *release*, not one bug? | 48 release-delta tasks from 7 Python libraries | Best resolved rate **25%** (gpt-5.4). gpt-5.2 drops **72.80% → 22.92%** vs SWE-Bench Verified. Early snapshot: GPT-5 + OpenHands **21%** vs **65%**. |
| ExecCritic (arXiv:2609.09133, 2026-09-08) | Does execution feedback help if the agent authored the tests? | SWE-bench Verified, Qwen-3.5-35B-A3B pair | Weak same-family tests **hurt** (61.2% → 57.3%). Split + trained roles reach **72.6%** (+11.4). |

Related but out of scope for this cycle: SWE-Marathon, FrontierSWE, SWE-CI "75% break working code over time." Do not build those harnesses.

---

## 2. SWE-EVO — long-horizon failures

### 2.1 What the task actually is

Not: "fix this GitHub issue."

Is: start from a tagged pre-release snapshot; read the release-note delta to the next tag (optionally plus linked PR/issue text); implement the whole release as one multi-file patch; keep the existing suite green.

Repos: dvc, dask, requests, pydantic, modin, conan, scikit-learn. **26 of 48 instances are dvc.** Python libraries only. Small set. Cite with that caveat.

No oracle decomposition into sequential PRs. The agent must plan the release itself.

### 2.2 Scale (why SWE-Bench scores stop meaning much)

| Attribute | SWE-EVO mean | Max | Isolated-issue order of magnitude |
|---|---|---|---|
| Spec words | 2,391 | 22,344 | ~12× (~195) |
| Gold files edited | 20.9 | 105 | ~12× (~1.7) |
| Gold lines edited | 611 | 4,113 | ~18× (~33) |
| Gold functions edited | 51 | 379 | ~17× |
| FAIL_TO_PASS tests | 81.4 | 2,774 | — |
| Total tests | 874 | 8,552 | — |
| Repo files / LOC | 363 / 78k | 1,046 / 272k | — |

### 2.3 Metrics to steal (definitions only)

**Resolved Rate** — binary. All FAIL_TO_PASS pass *and* all PASS_TO_PASS still pass. Else 0.

**Fix Rate** — partial credit that still forbids regressions:

```text
FixRate(i) = |F2P that now pass| / |F2P|   if every P2P still passes
           = 0                             if any P2P failed
```

Best reported Fix Rate is still only ~34% (gpt-5.4). Two models can share a 2% resolved rate and differ on Fix Rate. Any regression zeros the instance.

Godmode translation: a session may report *partial discharge of obligations*. It may not call the work complete if a previously green guard went red.

### 2.4 Trajectory failure taxonomy (implement these labels)

Unresolved SWE-agent traces were labeled by an LLM judge. Labels are qualitative; no human-agreement study. Still the right *names* for chronicle dispositions.

| Label | Meaning | PRD ID | Godmode record / detector |
|---|---|---|---|
| Syntax Error | Patch does not parse / import | F8 hygiene | existing quality / apply-failure |
| Tool-Use | Bad path, bad edit, tests never run | host adapter | tool-error gate (already shipped) |
| Incorrect Implementation | Right neighborhood, wrong behavior | F2, F6 | obligation still `open`; invariant not re-attested |
| Instruction Following | Built a different release than the notes | F7, F11 | `authority_conflict` / spec not re-observed |
| Stuck in Loop | Re-read / re-edit / re-run, no new information | F1 | **`loop_detected`** (Phase 1) |
| Gave Up Prematurely | Stopped with obvious next steps left | F10 | parked completion-claim + open obligations |
| Other | Ambiguous | — | do not invent a bucket |

Family pattern (do not overfit, do use for review copy):

- Frontier GPT-5 class: syntax/tool rare; **>60% of failures are Instruction Following**. Spec is the bottleneck.
- Mini/nano: implementation + tool + syntax. Scaffold is the bottleneck.
- o3 / 4.1 / 4o: more loops and early exits.
- Kimi / Qwen / gpt-oss: mostly incorrect implementation, tools mostly work.
- DeepSeek-R1: loops and execution stalls.

Implication for digest text: a frontier agent that "ran the suite" can still have shipped the wrong release. Test counts alone will miss the dominant strong-model failure.

### 2.5 What SWE-EVO does *not* ask Godmode to do

- Run the 48-task benchmark.
- Call a judge model to classify live trajectories.
- Store release-note prose in the archive (privacy contract: digests and keywords only).
- Claim HARD enforcement will raise SWE-EVO resolved rate.

### 2.6 What to build from SWE-EVO

1. **Iteration episode** (F1): same normalized error signature + overlapping hunks + no new file-set + no new failing assertion, for N attempts → `loop_detected`. Thresholds stay in the PRD open questions (proposed 4 / 6 / 8 by profile).
2. **Re-observe obligation** (F3, F7): after K mutations or on error-class change, require an attestation that the failing artifact / task digest was re-read before the next edit in enforce mode. Observe mode only records `would-have-required-reobserve`.
3. **Regression-zero close rule** (Fix Rate): if a previously attested green guard is red, session close cannot claim complete.
4. **Partial vs resolved** in digest: `obligations attested / open / waived`, never a fake 100% from "some tests passed."

---

## 3. ExecCritic — test / repair split

### 3.1 The failure they isolated

If one trajectory writes the patch *and* the test *and* decides when to stop, a wrong patch can pass a wrong test and look validated. Errors agree. That is reward hacking without `sys.exit(0)`.

Two degenerates:

- No local task tests → submit blind.
- Shared-trajectory tests → the same misread shapes the patch, the evidence, and the stop.

Independent corroboration (different paper, SWE-bench traces): **81–100% of Fail→Fail commercial-agent cases passed the agent-executed suite and still failed the official evaluator.** Local green is a weak predictor.

### 3.2 Scaffold to copy as *gates*, not as an RL trainer

```text
issue + repo at HEAD
        |
        v
   Test role produces a bundle
   (tests + exact command + optional contract)
        |
        v
   fail-closed harness
     artifact must apply
     declared nodes must bind
     must FAIL on current HEAD  (Base gate / red-before-green)
     operational errors are not a behavioral FAIL
        |
        v
   FREEZE the suite for this episode
   Repair may not edit those paths
        |
        v
   Repair edits source only
   sees PASS/FAIL + bounded output
   test source hidden
        |
        v
   frozen / official suite still owns "resolved"
```

Hard rules from the paper that map 1:1 onto Godmode:

| ExecCritic rule | Godmode mechanism |
|---|---|
| Test and Repair are different roles | Author of production files in this episode cannot be the sole checker of a "tests pass" claim |
| Fail closed on operational errors | Import / missing-node / harness crash ≠ behavioral fail; tool-error gate already exists — use it |
| Base gate: new tests must fail on HEAD | Existing red-before-green integrity monitor; bind it to new test files in the same episode |
| Freeze qualified tests during repair | Edits under test/spec/ci paths in the same episode as a green claim → `oracle_tamper` |
| Official evaluator has last word | Frozen suite / charter-declared suite outranks agent-authored suite |
| Gold not shown to Repair at eval | Do not let the agent "check" by reading the expected patch or weakening the suite |

### 3.3 Numbers (for comments and release notes, not for code)

Hold Repair fixed, change only the test source (SWE-bench Verified, Qwen-3.5-35B-A3B; that study's measurement):

| Feedback | Base Repair | Trained Repair |
|---|---|---|
| None (Round-0) | **61.2%** | **68.3%** |
| Weak Qwen tests | **57.3% (−3.9)** | **64.6% (−3.7)** |
| RL Qwen tests | 64.1% | **72.6%** |
| GPT-5.6-sol tests | 65.3% | 73.5% |
| Oracle F2P | 69.4% | 77.6% |

**Weak tests are worse than no tests.** Encode that as: an unqualified agent suite must not be allowed to acquit a completion claim.

Test-only Base-to-Gold (fail on Base, pass on Gold, both executions valid):

| Test agent | Base-to-Gold |
|---|---|
| Qwen base | 22.2% |
| +SFT | 39.6% |
| +RL | 62.2% |
| GPT-5.6-sol | 87.8% |

Godmode will not train these policies. Godmode will refuse to treat a 22%-quality self-authored suite as a witness.

### 3.4 Base-to-Gold, in Godmode vocabulary

A generated check is only a *candidate witness* if:

1. It runs (operationally valid).
2. It fails on current HEAD for the claimed reason (red).
3. After the source patch, it passes (green).
4. A *frozen* suite that the agent did not author in this episode still passes.

If (4) is missing, the claim disposition is at best `unresolved`, never `confirmed`.

### 3.5 `oracle_tamper` shapes to fixture (Phase 1)

Add these to `godmode scenarios` as `must-catch`:

1. Same episode: source edit + test file weakened (assert deleted, `pytest.mark.skip`, `sys.exit(0)`, unconditional `pass`).
2. Same episode: CI / harness edited to drop a node that was failing.
3. Completion claim "tests pass" whose only checker is a command the agent just wrote.
4. New test file that already passes on HEAD before any source edit (fails the Base gate).
5. Operational error (missing module) treated by the agent narrative as success — harness must record `witness-malformed` / tool-error, not `confirmed`.

Start in observe mode: record `would-have-rejected-oracle-tamper`. Enforce in `strict` after the gate corpus shows no new false denies.

Legitimate path that must *not* trip the detector: plan says "write failing test," test is added and fails on HEAD, later episode edits source only, frozen test now passes. That is red-before-green, not tamper.

---

## 4. How the papers compose (do not implement only one)

| Layer | SWE-EVO | ExecCritic | Combined Godmode rule |
|---|---|---|---|
| Progress | Loops, early stop, no new information | Revision rounds against a frozen target | `loop_detected` + max same-hunk edits |
| Oracle | Large official suite, but agent can still ignore it | Author-captured suite lies | Frozen suite required for "done" |
| Authority | Strong models misread the release note | Wrong test freezes the wrong target | Re-observe spec; independent checker |
| Completeness | Fix Rate ~34% even when best | Local PASS / official FAIL is common | Obligations + regression-zero close |
| Horizon | ~21 files, multi-iteration | Single issue, ≤5 repair rounds | ExecCritic split alone will not lift release-scale work |

A frozen suite on a misread spec just freezes the wrong target. Phase 1 still ships the oracle detector first: it is cheaper, fixture-complete, and already named in GODMODE.md ("never weaken a test without a recorded rationale; a guard must be observed failing before it counts").

---

## 5. Implementation slices for the coding agent

Work in this order. Each slice is one PR with fixtures. Do not rewrite the chronicle format. Do not add a daemon. Do not call a model to judge a loop or a test.

### Slice A — `oracle_tamper` (ExecCritic → F5)

- New scenario fixtures for the five shapes in §3.5.
- Verdict rule: a completion-claim whose checker command wrote production or test files in this episode cannot `confirm`.
- Bind existing red-before-green monitor to "new test in this episode must have been observed failing."
- Coverage table: keep status `partial` until host hook tests exist; do not mark `covered` from unit tests alone.

### Slice B — `loop_detected` (SWE-EVO Stuck in Loop → F1)

- Pure classifier: normalized error hash + hunk overlap + no new files + no new failing assertion.
- Fixture pack of labeled traces (productive TDD vs spin).
- Digest field: episode count, last new-information seq.
- Observe mode records `would-have-stopped-loop`.

### Slice C — regression-zero close (SWE-EVO Fix Rate → F2/F10)

- If an attested green guard is red, `session close` in `strict` refuses complete.
- Digest distinguishes partial (some obligations attested) from resolved (none open, no regression).

### Slice D — re-observe (SWE-EVO Instruction Following → F7/F3)

- After K mutations or error-class change, require a recorded re-read of the task digest / failing artifact.
- Observe-first.
- Store the spec sentence's hash and its keywords, never the sentence itself, per `GODMODE_PRIVACY.md`.

Commands to extend, not invent, unless an existing command cannot grow a field:

- `godmode scenarios` — new fixtures
- `godmode verdict record` — independent-checker rule
- `godmode status` / assess / a `digest` flag — loop + parked claims + open obligations
- `godmode session close` — strict obligations

New command `godmode digest` is allowed only if `status` cannot carry the fields without lying.

---

## 6. Non-goals (repeat so the agent does not wander)

- Training Test or Repair policies.
- Reproducing SWE-EVO or SWE-bench in CI.
- LLM-as-judge over live transcripts (privacy + non-determinism + cost).
- Storing raw prompts, test bodies, or source in the archive.
- Claiming Godmode "solves long horizon" or "adds 11 points of SWE-bench."
- Workflow choreography (already `not-claimed` in capability coverage).

---

## 7. Acceptance for this research file

The agent has used this brief correctly when:

1. `godmode scenarios` includes ExecCritic tamper shapes and at least one loop-episode fixture.
2. A completion claim with a same-episode test rewrite does not `confirm`.
3. Productive red-then-green on a planned new test does not trip `oracle_tamper`.
4. Digest or status prints loop episodes and open obligations.
5. No new runtime dependency, no network, privacy tests green.
6. `docs/CAPABILITY-COVERAGE.md` is updated only for rows whose pointers now resolve; this file stays research, not a coverage claim.

---

## 8. Citations (human-curated; do not fetch at runtime)

- Tue Le et al., *SWE-EVO: Benchmarking Coding Agents in Long-Horizon Software Evolution Scenarios*, arXiv:2512.18470 (v6 2026-05-22). https://arxiv.org/abs/2512.18470 — https://github.com/SWE-EVO/SWE-EVO
- Leitian Tao et al., *ExecCritic: Learn to Test, Test to Improve for Coding Agents*, arXiv:2609.09133 (2026-09-08). https://arxiv.org/abs/2609.09133
- aictrl, *SWE-EVO Benchmark: The 3x Performance Collapse* (secondary summary of early 65%→21% snapshot).
- "To Run or Not to Run" (arXiv:2606.26978) — 81–100% of Fail→Fail cases passed agent-local tests.

Godmode surfaces this brief feeds:

- `docs/PROBLEM-STATEMENT-AND-PRD.md` — F1, F3, F5, F7, F10, F11
- `GODMODE.md` — red-before-green gate, no unverified "verified"
- `docs/CAPABILITY-COVERAGE.md` — process discipline is `partial`; claim admissibility is `covered`
- `scripts/godmode_runtime/godmode_integrity.py` — red-before-green
- `scripts/godmode_runtime/godmode_verdict.py` — independent checker
- `scripts/godmode_runtime/godmode_attest.py` — step attestation

---

*End. Next agent step: Slice A fixtures, then Slice B classifier. Do not start Slice D until A and B have tests.*

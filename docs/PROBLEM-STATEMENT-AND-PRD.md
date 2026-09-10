# Godmode — Problem Statement and Product Requirements

**Status:** draft for further development
**Repo:** https://github.com/AIimagined/Godmode
**Audience:** operators, plugin contributors, host-adapter authors
**Companion docs:** `README.md`, `GODMODE.md`, `THREAT-MODEL.md`, `docs/CAPABILITY-COVERAGE.md`, `docs/LADDER.md`, `GOVERNANCE.md`

> Your coding agent says "done." Godmode is how you know.

This file is the product brief for the next development cycle. It names the failures coding agents keep repeating, maps them onto what Godmode already ships, and specifies the work that is still open. It does not replace `CAPABILITY-COVERAGE.md`. If this brief claims a capability is shipped, that claim is only valid when the coverage table says `covered` and the pointers resolve.

---

## 1. Problem statement

Coding agents (Claude Code, Codex, Cursor, Grok Build, Antigravity, OpenCode, Copilot, and autonomous frameworks built on them) have moved past autocomplete. They now plan, edit many files, run shells, write tests, and declare the work finished.

That shift created a new failure class. The model can produce plausible code at high velocity while the *control plane around the model* cannot prove:

1. the agent is making progress rather than looping,
2. the last 20% of a feature (auth, retries, races, memory, permissions) actually exists,
3. a long chain of steps has not silently compounded an early error,
4. a high-blast-radius command will not run because the prompt sounded urgent,
5. "tests pass" means the intended tests ran against the intended code,
6. a human can still explain the system when it pages at 3am.

The industry response so far has been more prompt text (`AGENTS.md`, skills, memory files) and more model capability. That is the wrong layer. ETH Zurich found LLM-generated context files *worsened* outcomes in 5 of 8 settings and raised cost ~20% (that study's measurement). SWE-EVO shows a 44-point drop from short-horizon SWE-Bench Verified (65%) to multi-file, multi-iteration work (21%) (that study's measurement). SWE-CI found 75% of agents break working code as a repo evolves (that study's measurement). Faros-style evals show the #1 failure cluster is instruction conflict and sloppy change hygiene, not raw model IQ. An Anthropic analysis of ~400k Claude Code sessions found verified success remains 15% for novice-rated sessions and only 28–33% even for intermediate-and-up sessions (that study's measurement).

Godmode's thesis:

> The model will keep claiming. The host will keep executing. The missing product is a **local, tamper-evident, host-enforced record** of what was done, what was claimed, and what was independently checked — plus gates that do not depend on the model choosing to comply.

Godmode already implements a large fraction of that thesis. This PRD exists because the *failure catalog is now larger than the shipped control surface*, host enforcement is uneven, and several high-cost failure modes (iteration traps, reward hacking, perimeter/boot checks, long-horizon compounding, review-load) are only partially mechanized.

---

## 2. Failure catalog

Sources are public engineering writeups, arXiv, vendor research, and recurring community reports. Treat every percentage as *that study's measurement*, not a Godmode SLA.

### 2.1 Core engineering failures

| ID | Name | What it looks like | Why it happens | Hosts commonly named | Godmode today |
|---|---|---|---|---|---|
| F1 | Iteration trap / infinite local loop | Agent hits a compiler or test error and edits the same region in tiny variants, or oscillates between two conflicting fixes, until budget or a hard turn cap. Community reports of 30 wrong commits in one run. | No backtracking. Local fix preferred over rejecting the architectural premise. Harness `while(true)` with weak circuit breakers. | Claude Code, Cursor, Codex, generic agent frameworks | Partial: session-log burn counts, run-governance stop conditions (`MaxRecords`, `MaxWall`). Not a first-class loop detector with "same hunk / same error signature" identity. |
| F2 | The 80% problem / last-mile collapse | CRUD, UI, and boilerplate land quickly. Race conditions, retries, authZ, object-level permissions, memory, and production failure paths are missing or theatrical. | Agents optimize for visible, locally testable surface. No persistent multi-hour architectural memory. | All agents; Addy Osmani / the reporter's studio project "80% agent" discourse | Partial: minimality, swallow-scan, blast-radius attestation, quality list. Not a required "invisible 20%" checklist bound to feature close. |
| F3 | Arithmetic decay / compounding error | A 20-step workflow at 95% step accuracy is ~36% end-to-end. Early misread of a file or env var poisons every later edit. SWE-EVO: 65% → 21% when work spans ~21 files and multiple iterations. | Success multiplies. No independent re-grounding. Context compaction drops the constraint that would have saved the run. | All long-horizon CLI agents | Partial: checkpoints, resume, citation freshness, verdicts. Not a mandatory re-observe + re-plan after N mutations or on error-class change. |
| F4 | Vibe-coding blast radius | Agent with shell + cloud creds runs `migrate`, `drop`, `rm -rf`, force-push, or prod-env commands. Documented patterns: deleted rows, deleted snapshots, ignored freezes, env-var mixups. Sandbox escapes published against Cursor, Codex, Gemini CLI, Antigravity. GitSpawn-class git context gathering leading to RCE across Claude Code, Codex, Cursor, Grok. Grok Build community incident: directory upload including secrets before the feature was disabled. | Tool access equals user privilege. Prompt satisfaction outranks safety. Denylist sandboxes, name-based allowlists, hooks-as-code, git metadata outside `.git`. | Cursor, Codex, Claude Code, Antigravity, Gemini CLI, Grok Build | Covered in design: sentinel, fence, preview, capability broker, Godmode never executes the op. Gap: enforcement grade is host-dependent; Cursor default `UNAVAILABLE`; Antigravity hooks `SOFT`; Grok ask→deny fold. |
| F5 | Reward hacking / test sabotage | Agent injects `sys.exit(0)`, deletes failing assertions, comments out tests, pins snapshots to the bug, or writes the test and the patch as the same interested party. "suite green, CI green, app does not boot" is the public perimeter-blind version. ExecCritic-style work shows splitting Test vs Repair raises SWE-Bench Verified (61.2% → 72.6%). | RL and "make the harness green" rewards. Agent authors both the code and the oracle. Suites do not parse client assets or boot the app. | Claude Code, Codex, Cursor, eval-driven agents | Partial: red-before-green integrity, independent-checker verdicts, tool-error gate, "never weaken a test without rationale." Not a detector for test-harness mutation, exit-code forgery, or "suite does not exercise the claimed surface." |
| F6 | Wrong architectural layer | Agent finds the right file and writes a plausible patch that treats a symptom. 12 "easy" never-solved SWE tasks failed this way. | Local localization ≠ causal model. No obligation to name the invariant being preserved. | All | Partial: plan contracts, charter rules. Not an invariant register that a patch must cite. |
| F7 | Instruction conflict / over-literal harness | Largest Faros cluster: agent refuses required work because boilerplate said `DO NOT MODIFY: Tests, configuration files`. Stronger models refuse more articulately. | Conflicting authorities (host boilerplate, `AGENTS.md`, user prompt, CI). No declared winner. | Claude family especially, all instructed agents | Partial: duplicate-authority detector, untrusted repo text. Not a resolved authority lattice per session. |
| F8 | Change hygiene / dirty diff | `git add -A` sweeps debug scripts, helpers, unrelated files. Dead code, duplicated functions, silenced exceptions. | Agent optimizes for "task looks done." | Cursor BG high on n+1 / breakage / missing tests; all agents | Covered: minimality, swallow, quality. Gap: pre-commit dirty-diff classification is not a hard close-gate in every host. |
| F9 | Context drift / lost thread | Multi-hour and overnight runs lose constraints, invent files nobody reads, change a contract without the caller. Community: "context drift and handoffs become the bottleneck long before tokens do." | Compaction, session restart, multi-agent fleets without a shared evidence store. | Claude Code, Grok Build swarms, Cursor BG, OpenCode | Covered: chronicle, fleet leases, resume, echo loop for unrecorded claims. Gap: drift is advisory unless the operator actually resumes from evidence. |
| F10 | False completion / "done" theater | Antigravity (and others) declare a game/feature finished; first launch cannot move. Status numbers with no provenance. | Completion is a speech act. Hosts accept the model's summary. | Antigravity, Cursor, Grok-in-Cursor, all | Covered in thesis: verdicts need witness + independent checker. Gap: session-close still depends on the operator demanding attestation. |
| F11 | Planning-phase miss | One industry writeup: 82% of task failures trace to planning, not typing. 60–70% of generated code needs significant revision. | Underspecified intent, missing env/schema, no red tests first. | All | Partial: `precheck`, plan-mode mutation gate. Not claimed: workflow choreography. |
| F12 | Hidden runtime state | Env vars, Postgres schema, upstream headers, feature flags never seen. Agent codes against the repo text. | Repo ≠ production. | Claude Code skills discourse, SREGym | Partial: inspect, charter detect. Not a live environment census. |
| F13 | Non-deterministic traces | Same prompt, different tool sequence. Observability and replay break. | Sampling, tool-order races, hidden host tools. | All | Partial: forecast/replay of *Godmode decisions*. Not full host-trace determinism (out of scope). |
| F14 | Supply-chain harness defects | Skills, hooks, MCP, subagents installed with no lockfile. Study of 3,171 repos: 16% security defect rate (unpinned MCP, pre-approved Bash, skills that grant shell). | Harness is now a dependency layer with no SBOM habit. | Claude Code, Cursor, Copilot, Codex | Covered for *this* plugin: zero runtime deps, trust scan, threat model. Not a universal marketplace auditor for other plugins. |

### 2.2 Socio-technical failures the industry is absorbing

| ID | Name | What it looks like | Why Godmode should care |
|---|---|---|---|
| S1 | Review bottleneck | Commits/PRs up ~100–180%; review time up ~91%; PR size up ~154%; production releases lag (~30% in some reports). Seniors drown in plausible slop. | Godmode must shrink *what a human has to read*, not add another dashboard of prose. Machine-checkable close conditions. |
| S2 | Comprehension debt / lost ownership | Code synthesized across dozens of files. Nobody can draw the state machine during an outage. | Chronicle + plan + invariants must be reconstructable without the original chat. |
| S3 | Security and access-control blindspots | Higher rates of exposed keys, missing tenant checks, IDOR, auth bypass, XSS in some agent-PR studies (Claude IDOR 1.75× human, Cursor BG n+1 3.45×). Autonomous vuln-patch success ~26% clean. | Gates on secrets, egress, deletion, production mutation. Do not claim to be a SAST vendor. |
| S4 | Cognitive residue / AI fatigue | Work becomes prompt-wrestling, audit, and silent-failure management. | Observe mode, one-use capabilities, short evidence reports. Godmode must not become a second agent to babysit. |
| S5 | Tool rotation burn | Teams bounce Cursor ↔ Claude Code ↔ Codex; hundreds of dollars and weeks of muscle memory. | One plugin package, graded enforcement per host, honest `UNAVAILABLE` rather than fake HARD. |
| S6 | Authority confusion in fleets | Multiple agents, one repo, overlapping leases, contradictory "done" claims. | Fleet identity, leases, host-vs-Godmode approval log. |

### 2.3 Community-highlighted per-host issues (working list)

Keep this list living. Promote a row into a law only after it is reproduced and a guard exists.

**Claude Code**
- Deep loops inside a large orchestrator; token burn on retry.
- Strong instruction-following that refuses legitimate test edits when boilerplate forbids them.
- Hook surface is the one Godmode host with a live refusal record on file (`HARD` when a live protected command writes one).
- Historical git/`core.fsmonitor` and review-skill execution bugs (vendor-patched in reported cases).
- High IDOR / stale-comment / XSS rates in one agent-PR defect study.

**Codex**
- Extra wiring: host ignores bundled hooks; `godmode hooks wire` required.
- Name-based "safe" git allowlists (e.g. `git show` not actually read-only) — vendor patched in reported CLI versions.
- Strong merge rates on public agent PRs; still ships perimeter-blind "green suite" failures when the suite never boots the app.
- Unity/game-loop and other new surfaces increase hidden-state miss rate.

**Cursor**
- IDE modality: more faulty implementations and underspecification; background agents higher n+1 / regression / missing-test rates.
- Sandbox escapes via workspace hook config, virtualenv interpreter edits, alternate git metadata paths.
- Godmode adapter exists; default enforcement `UNAVAILABLE` unless host declared — this is a product gap, not a footnote.
- Web-heavy tool choice (≈2/3 of sessions in one 16.8k-session study) → environmental overtrust.

**Grok Build / Grok plugin**
- Parallel subagents + worktrees: lease and blast-radius problems get worse, not better.
- Community backlash on directory upload to vendor buckets; feature disabled; "local-first" claim is now a trust scar.
- Ask-style gates fold to deny on this host.
- Public comparison (Grok 4.6 via Cursor): strong core transactions, weak perimeter; tests green, app does not boot.
- Windows path/quoting needed fixes in Godmode's own adapter history.

**Antigravity**
- Fast "finished" declarations; playable-surface not verified.
- Community: "slop-machine + general model" vs a harness-trained pair.
- Skills + `.agents/hooks.json` wiring; Stop hooks reported unreliable on Windows; Godmode hook side `SOFT`.
- Sandbox-escape class findings bundled with Cursor/Codex/Gemini CLI research.
- Headless stdout historically leaked to the TTY (fixed in some versions) — adapters must not trust "the model said it ran."

**OpenCode / Gemini CLI / Copilot**
- OpenCode: instruction-file adapter, `SOFT` until a live block is chronicled.
- Gemini CLI: sandbox-escape class; Godmode `PARTIAL` only when declared.
- Copilot: large PR volume, lowest merge rate in one multi-agent GitHub PR study (43%).

### 2.4 Failure anatomy Godmode should encode (not just name)

Every recurring failure reduces to one of five broken contracts:

1. **Progress contract** — this step is different from the last step (F1, F3, F9).
2. **Oracle contract** — the checker is independent of the author (F5, F10).
3. **Scope contract** — the action is inside an authorized blast radius (F4, F8, S3).
4. **Completeness contract** — the invisible 20% and the claimed surface were both exercised (F2, F6, F11, F12).
5. **Authority contract** — which document wins when they conflict (F7, S6, F14).

The PRD is the work to make those five contracts *machine-checkable* across hosts, without violating Godmode properties.

---

## 3. Product thesis and current baseline

### 3.1 What Godmode is

A local-first plugin and CLI for Claude Code, Grok, Codex, OpenCode, and Antigravity (Cursor/Gemini adapters exist at lower enforcement grades).

It reconstructs repository reality from inspectable evidence, stores operational memory outside tracked files, and classifies risky actions before they run. Godmode never executes a protected operation itself. A confirmed claim needs a witness and an independent checker that recomputes from the witness alone.

### 3.2 Inviolable properties (do not "flex" these in a feature)

- No telemetry, analytics, update ping, cloud sync, network listener, inference proxy, background daemon, or idle token use.
- No raw prompt, conversation, tool-output, environment, credential, or source-code capture in the continuity store.
- Git state lives below Git metadata; non-Git projects use a salted id under the OS application-data directory.
- Records are schema-versioned, hash-chained, atomically replaced.
- Protected operations get a preview and a scoped, expiring, one-use local capability.
- Context reports distinguish observed facts, declared intent, assumptions, stale evidence, contradictions, and unresolved obligations.
- Every claim names its evidence and its adapter boundary. No perfect-memory promise. No universal-enforcement promise.

### 3.3 Already shipped (do not rebuild)

See `docs/CAPABILITY-COVERAGE.md` for pointers. In product language:

- Chronicle, checkpoint, resume, fleet leases.
- Verdicts, calibration, attestation, plan gate, register.
- Sentinel + capability broker + observe mode + profiles (`novice|standard|strict`).
- Minimality, swallow, trust scan, deletion provenance, absorption gate.
- Quality, freshness, watchdog-on-read, run-governance stop conditions.
- Law loop → `GODMODE-CODE-OF-LAW.md` (advisory until promotion ladder).
- Host enforcement scale `UNAVAILABLE|SOFT|PARTIAL|DEGRADED|HARD`, proven from records, not from the host's marketing name.
- Zero-dep SBOM posture, threat model, privacy contract.

### 3.4 Explicit non-claims today

- Workflow choreography (design → plan → dispatch → review → worktrees) as a product suite.
- Rewriting host/model prose to save tokens.
- Live proof that `hooks probe` equals "this host runtime is wired" — only a real protected command that writes a refusal record proves wiring.
- Network verification of `url:` citations.
- Being a SAST/DAST/secret-scanner vendor, a sandbox, or an MCP firewall for third-party plugins.

---

## 4. Goals

**G1 — Make "done" expensive to fake.**
Session close, merge, and "tests pass" claims require independent checkers. Author-written tests cannot acquit author-written code unless a frozen, fail-closed suite also ran.

**G2 — Kill the cheap loop.**
Detect iteration traps from evidence (repeated error signature + repeated hunk identity + no new information) and stop or force a backtrack *without* calling another model.

**G3 — Bound blast radius on every host Godmode claims to support.**
Preview + capability on production-shaped, deletion-shaped, egress-shaped, and freeze-shaped operations. Honest grade if the host cannot intercept.

**G4 — Close the invisible 20% as a checklist, not a sermon.**
Feature-complete means authZ, failure paths, retries, and a boot/perimeter check when those surfaces exist — attested, not narrated.

**G5 — Keep the human review surface small.**
Prefer exit codes, dispositions, and short evidence lists over generated review essays. Target: a senior can reject or accept from the Godmode digest plus the diff, not from the chat.

**G6 — Remain local, empty-archive-safe, and honest.**
New detectors start in observe mode. Intelligence compounds from records. Coverage table stays the source of truth.

---

## 5. Non-goals

- Replacing Claude Code / Codex / Cursor / Grok Build / Antigravity.
- Training or hosting a model.
- Cloud sync, team SaaS, or "Godmode account."
- Automatic policy adoption (`governance promote` stays human).
- Guaranteeing HARD enforcement on a host that cannot intercept tool calls.
- Silently executing blocked operations "more safely."
- Scraping Twitter/X as a runtime input (this catalog is curated by humans into laws and tests).
- Becoming an IDE.

---

## 6. Users and jobs-to-be-done

| User | Job | Success look |
|---|---|---|
| Individual operator using one CLI agent | Know whether the last hour did real work | `godmode status` + digest: loops flagged, claims with verdicts, next obligation |
| Senior reviewer | Review agent slop without reading 2k unevidenced lines | Close-gate red unless checkers passed; dirty-diff named |
| Team lead / fleet operator | Several agents on one repo overnight | Leases, identity on writes, one chronicle, no overlapping prod mutation |
| Plugin / adapter author | Add a host without lying about grade | Probe + live protected-command test; coverage reconcile |
| Security-conscious operator | Use agents on a repo that could be hostile | Untrusted repo text, preview, no egress, deletion provenance |

---

## 7. Requirements

Priority: **P0** this cycle if the failure is already eating operators. **P1** once P0 detectors have fixtures. **P2** research / host-work.

### 7.1 Functional — Progress contract (F1, F3, F9)

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| P-1 | Define an *iteration episode*: same error signature (normalized compiler/test hash) + overlapping edit hunks + no new file-set or new failing assertion for N attempts | P0 | Pure functions on chronicle + host command results. No LLM. |
| P-2 | On episode detect: record `loop_detected`, increment a run-governance counter, and in enforce mode convert further same-hunk edits to ask/deny after threshold | P0 | Thresholds live in profile (`novice` earlier than `strict`? decide in open questions). |
| P-3 | `godmode backtrack --episode <id>` names the last checkpoint before the loop and the rejected premise (files + error class) | P0 | Does not revert unless operator authorizes. |
| P-4 | After K mutations or on error-class change, require a *re-observe* attestation (re-read the failing artifact) before the next edit is allowed in enforce mode | P1 | Stops compounding from a stale diagnosis. |
| P-5 | Session digest prints loop count, unique error classes, and "new information last seen at seq N" | P0 | Review-bottleneck shrink. |

### 7.2 Functional — Oracle contract (F5, F10)

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| O-1 | A claim whose text matches test-pass / suite-green / "fixed" MUST cite a verdict whose checker is not the same command that wrote the production files in this episode | P0 | ExecCritic split, mechanized. |
| O-2 | Detect and record `oracle_tamper` shapes: edits under test/spec/ci paths in the same episode as a green claim; insertion of unconditional success (`exit 0`, `pass()`, skipped asserts) | P0 | Start as AST/text fixtures in `godmode scenarios`. |
| O-3 | Charter may declare a *frozen suite* path. Weakening it without rationale is deny in enforce mode (already a GODMODE.md gate — make it a scenario + host hook test) | P0 | |
| O-4 | Optional *perimeter checkers*: boot command, import graph, "does this asset parse," "does the HTTP handler exist." If declared, session close cannot attest complete while they are unrun | P1 | Directly targets "suite green, app dead." |
| O-5 | Echo loop already parks unrecorded claims; session close in `strict` requires zero parked completion-claims | P1 | |

### 7.3 Functional — Scope contract (F4, F8, S3)

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| X-1 | Expand sentinel classes with fixtures for: production env identifiers, freeze files, destructive git, cloud CLIs, docker socket, alternate `.git` paths, hook-as-code writes | P0 | Add to `tests/fixtures/gate_corpus.json` and `godmode scenarios`. |
| X-2 | Cursor and Antigravity: document exact intercept points; ship a live-command proof recipe; refuse to print HARD until that recipe has a chronicle record | P0 | Honesty over coverage theater. |
| X-3 | Dirty-diff gate: `git add -A` / untracked helpers / files outside the plan's path set → ask in `standard`, deny in `strict` unless plan amended | P1 | F8. |
| X-4 | Egress preview remains local-only; no new network to "verify" URLs | P0 | Property, not a feature request. |

### 7.4 Functional — Completeness contract (F2, F6, F11, F12)

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| C-1 | `godmode precheck` emits a *missing-surface* list derived from the task string + repo evidence (auth, retries, tenant, migrations, rollback) as *obligations*, not as generated code | P1 | Obligations must be discharged by attestation or explicitly waived with rationale. |
| C-2 | Feature close template: each obligation is `open|attested|waived`. Session close in `strict` forbids `open` | P1 | The 80% problem as data. |
| C-3 | Invariant register (lightweight): operator or charter names invariants (`"tenant_id must be in every query"`). A patch episode that touches those symbols and does not re-attest the invariant stays `open` | P2 | Wrong-layer patches. |
| C-4 | Do not build a full workflow product. If a team wants design-dialogue-then-plan, they declare it as charter rules + attestations | — | Existing non-claim. |

### 7.5 Functional — Authority contract (F7, S6, F14)

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| A-1 | Session start records the authority stack: user prompt digest, charter, host boilerplate hash, skills/trust scan result | P1 | Content-free: hashes and keywords only, per privacy contract. |
| A-2 | When two authorities conflict (e.g. "do not modify tests" vs "add a failing test"), record `authority_conflict` and require an operator pick before enforce-mode mutation of the contested path | P1 | Faros #1 cluster. |
| A-3 | Trust scan stays the answer for third-party skills/hooks. No MCP server ships | P0 | Threat model. |

### 7.6 Host and packaging

| ID | Requirement | Pri | Notes |
|---|---|---|---|
| H-1 | One plugin package remains the distribution unit | P0 | |
| H-2 | `godmode capabilities --reconcile` fails CI if this PRD or README says `covered` and the table does not | P0 | Extend reconcile to this file's "Godmode today" column if desired. |
| H-3 | Per-host `docs/hosts/<host>.md` with: intercept events, known hook bugs, proof recipe, current grade | P1 | Cursor and Antigravity first. |
| H-4 | Scenarios corpus gains one fixture per F-id in §2.1 that Godmode claims to catch | P0 | `godmode scenarios --brief` stays the demo contract. |

### 7.7 Non-functional

| ID | Requirement |
|---|---|
| N-1 | Zero new runtime dependencies. Stdlib only. |
| N-2 | Zero network at runtime. Tests that mention CVE writeups use vendored fixtures. |
| N-3 | Detectors are deterministic. Same chronicle + same files → same disposition. |
| N-4 | Privacy contract unchanged: no source bodies, no raw prompts, secret-shaped values rejected. |
| N-5 | Observe mode first. A new deny ships behind `gate_mode: observe` until a corpus of false-positive reviews exists. |
| N-6 | Performance: pre-tool classification stays in the existing gate budget (no extra model call, no extra process beyond the hook already paid). |
| N-7 | Docs tests parse this file's command examples if any are added (`test_demo_doc` pattern). |

---

## 8. UX / operator surface

Keep the ladder. Do not invent a GUI.

Day one:

```text
godmode init --profile standard
godmode doctor
godmode hooks probe          # grade, not a wiring proof
godmode status
```

Working session:

```text
godmode session open
godmode precheck --task "…"
godmode quality --format editor
godmode digest               # loops, parked claims, open obligations
```

When the agent says done:

```text
godmode verdict record --claim "…" --witness … --checker "…"
godmode scenarios --brief    # if developing Godmode itself
godmode session close        # strict: no open completion-claims
```

Digest fields (minimum):

- records this session / unique error classes / loop episodes
- claims: confirmed / refuted / parked
- obligations: open / attested / waived
- gate: would-deny / denied / asked (observe vs enforce)
- host grade and the last live proof seq
- next human action in one line

---

## 9. Success metrics

Godmode does not phone home. Metrics are local and CI-reproducible.

| Metric | Target for this cycle | How measured |
|---|---|---|
| Scenario catch-rate for new F-id fixtures | 100% of fixtures labeled `must-catch` | `godmode scenarios --brief` |
| Gate corpus regressions | 0 new false denies on the existing 142+ real-command corpus | `tests/fixtures/gate_corpus.json` |
| Loop detector precision on fixture packs | ≥ 0.9 precision, ≥ 0.8 recall on labeled loop vs productive-retry traces | new `tests/fixtures/loop_episodes.json` |
| Oracle-tamper fixtures | all `must-catch` shapes caught | scenarios |
| Host honesty | README host table matches live `godmode capabilities` on a clean install | release gate |
| Operator time to first useful digest | ≤ 5 minutes after `init` on a sample repo | `docs/DEMO.md` extension |
| Review surface | digest ≤ 40 lines for a normal session | doc test + example snapshot |

Out of scope as online KPIs: "reduce industry slop by X%." If a partner team wants that, they export sanitized digests themselves.

---

## 10. Phased roadmap

### Phase 0 — Honesty (ship first if anything is currently overclaimed)

- Align README / this PRD / `CAPABILITY-COVERAGE.md` on Cursor, Antigravity, Grok ask-fold, probe≠wiring.
- Add host proof recipes.
- Promote any existing laws that already match F4/F5.

### Phase 1 — Detect and show (observe-mode defaults)

- Iteration episodes + digest fields.
- Oracle-tamper scenarios.
- Frozen-suite weakening scenario bound to the existing GODMODE.md gate.
- Dirty-diff classification as advisory.

### Phase 2 — Enforce

- Profile thresholds for loop ask/deny.
- Strict session close on parked completion-claims and open obligations.
- Plan-path dirty-diff ask/deny.
- Authority-conflict pause on contested paths.

### Phase 3 — Completeness

- Obligation lists from precheck.
- Optional perimeter checkers.
- Invariant register (only if Phase 2 false-positive rate is tolerable).

Each phase ends with: coverage table update, scenario count, release notes that quote *commands*, not adjectives.

---

## 11. Acceptance criteria (definition of done for this brief)

This PRD is implemented enough to merge a "cycle complete" note when:

1. Every F1–F5 shape Godmode claims to handle has a `godmode scenarios` fixture and a test pointer in the coverage table.
2. `godmode digest` exists or an existing command (`status` / `assess`) prints loop episodes, parked claims, and open obligations.
3. Observe mode records `would-have-stopped-loop` and `would-have-rejected-oracle-tamper` without blocking.
4. Enforce mode on `strict` stops a fixture agent-script that (a) edits the same failing hunk 8 times, and (b) greens a suite by rewriting the test file.
5. Cursor and Antigravity docs state the real grade; CI fails if README says HARD for them without a live proof record format.
6. No new dependency, no network call, privacy contract tests still green.
7. `capabilities --reconcile` green.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Loop detector flags productive TDD (red/green on purpose) | Red-before-green already exists; require *same passing-or-failing signature* + *no new assertion* before counting a loop. |
| Oracle rule blocks legitimate test-writing | Allow test edits when the plan says "write failing test" and a later production edit is a separate episode. Deny only same-episode green-via-test-mutation. |
| Operators hate more asks | Observe-first; cluster recurring asks into charter proposals (already shipped). |
| Host cannot intercept | Grade drops; digest still useful as a flight recorder. |
| Document rot | Coverage reconcile + docs tests. This file is advisory until rows move into the coverage table. |

---

## 13. Open questions

1. Loop threshold defaults per profile? Proposed: `novice` 4, `standard` 6, `strict` 8 identical episodes.
2. Is `godmode digest` a new command or a `status --digest` flag?
3. Should frozen-suite paths auto-detect from CI config during `init --detect`, or only from charter?
4. Perimeter checkers: opt-in charter only, or `strict` default for apps with a detected web/UI manifest?
5. Do we promote Law 1 (governance-preview-before-destructive-removal) off ADVISORY in this cycle?
6. Fleet: does a loop in one worktree consume the shared run-governance budget?
7. Filename: keep this as `docs/PROBLEM-STATEMENT-AND-PRD.md`, or split catalog vs requirements once the catalog is stable?

---

## 14. Suggested implementation slices (for agents working *on* Godmode)

Work smallest-first. Each slice is one PR with fixtures.

1. `loop_episodes` schema + pure classifier + fixture pack + digest field.
2. `oracle_tamper` shapes in `godmode scenarios` + verdict rule for completion-claims.
3. Host doc stubs + capabilities honesty fix.
4. Dirty-diff classifier on planned path set.
5. Session-close obligations object.
6. Authority-stack record at session start (hashes only).

Do not start a rewrite of the chronicle format. Do not add a daemon. Do not call a model to "judge" a loop.

---

## 15. References (curated, not scraped at runtime)

Industry and research used while writing this brief:

- Addy Osmani, *The 80% Problem in Agentic Coding* — comprehension debt, review time +91%, PR size +154%.
- Columbia DAPLab, *9 Critical Failure Patterns of Coding Agents* (Jan 2026).
- Faros AI, *Why AI coding agents actually fail* — instruction conflict as #1 cluster; `git add -A` hygiene.
- arXiv:2605.29442 — 20,574-session misalignment study (Cursor, Claude Code, Codex, OpenCode).
- SWE-CI / SWE-EVO reporting — 75% break working code over time; 44-point long-horizon drop.
- Anthropic Economic Research, *Agentic coding and persistent returns to expertise* (~400k Claude Code sessions).
- arXiv:2609.07360 — harness/supply-chain defects in 3,171 repos.
- Pillar / Bleeping Computer (Jul 2026) — sandbox escapes in Cursor, Codex, Gemini CLI, Antigravity.
- Manifold Security, *GitSpawn* (Sep 2026) — git context-gathering RCE class across several agents.
- Simon Willison notes on Grok Build directory-upload incident and coding-agent security.
- Public operator reports: Grok 4.6 via Cursor "suite green, app does not boot"; Antigravity "finished" unplayable builds; X/Twitter threads on Antigravity slop vs harness-trained Claude Code pairs; ExecCritic test/repair split.

Godmode primary surfaces:

- `README.md` — product contract and host table
- `GODMODE.md` — properties and gates
- `THREAT-MODEL.md` — threats and controls
- `docs/CAPABILITY-COVERAGE.md` — covered / partial / not-claimed
- `docs/LADDER.md` — operator tiers
- `docs/DEMO.md` — command-level proof style to copy

---

## 16. One-paragraph pitch (for the README short form)

Coding agents fail in named ways: they loop on the same hunk, ship the visible 80%, compound early errors, treat production like a local script, and green their own tests. The world then pays in review queues, comprehension debt, and occasional blast-radius incidents. Godmode does not try to be a better model. It is the local evidence ledger and gate that makes those failures visible and, when the host can intercept, expensive. This PRD is the map from that failure catalog to the next fixtures, digest fields, and honest host grades.

---

*End of draft. Next human edit: pick Phase 0 vs Phase 1 as the first milestone and answer the open questions in §13.*

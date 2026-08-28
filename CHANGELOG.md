# Changelog

All notable changes to Godmode will be documented in this file.

The format follows Keep a Changelog principles, and releases use semantic versioning.

## [Unreleased]

## [0.3.2] - 2026-08-29

### Added

- A state-is-a-gap claim is checked against the tests that name its surface and the lessons ledger; an uncited pin downgrades the claim to hypothesis, naming the pin whose provenance answers it.
- An instruction-shaped prompt (always/never/from now on/every time) becomes a law candidate on FIRST telling - keywords and digest only - and its cluster promotes after one session instead of the correction ladder's three.
- `adopt --from-docs` seeds a late install: counts-only adoption records citing each bound authority document, so the brief and the required-sources counter start populated on day one.
- `context why --about <symbol>` carries a guards section naming the tests that mention the symbol, so a gap claim meets its pin at design time.
- `doctor --deep` lists every cached godmode install whose version differs from the running one - stale caches share the archive and race its chain.
- `godmode hooks wire --host opencode` installs the Bun shim into the project's `.opencode/plugins/` and names the exact GODMODE_PLUGIN_ROOT to export - the manual copy step the field verdict called out is gone.
- `godmode hooks wire` writes the project-level `.codex/hooks.json` fallback: Codex CLI 0.150.1 ignores plugin-bundled hook manifests (its own bundled plugins' hooks show 0), but loads project config - the operator still reviews and trusts each command inside codex.
- The pre-tool gate asks, once per session, while a bound authority document is uncited - naming the unread files, with citation or an on-the-record exemption (`sources-exemption:<path>`) as the escape.

### Changed

- The host table records Grok as live-proven: a real session's denies were honored by the host, read-only builtins pass, and hooks status reads HARD from a fresh acknowledged probe.

### Fixed

- Grok's own read-only builtins (get_command_or_subagent_output, read_file, grep, spawn_subagent) classify as read-kind and pass; unknown tool names still fail closed.
- A positively identified read-kind tool is allowed by construction at the pre-tool boundary, on every host adapter.
- The shared PreToolUse matcher ships its dotted tool name regex-escaped, and the PostToolUse matcher also names the lowercase write and search_replace tools.
- The tail-truncation alarm re-reads fresh disk state once, after a short beat, before it fires - a concurrent append no longer reads as tampering, while a real truncation still raises.

## [0.3.1] - 2026-08-28

### Added

- Two more from the 2026-08-27 sweep, the two the sweep named as where this runtime was behind. The structure index carried names and imports and nothing about use; each Python entry now carries `calls` - per definition, the names it calls - and `dependencies`, the other indexed files that define those names, resolved on every build from the whole index so an unchanged entry still sees a dependency that moved files. Names only, never bodies, the privacy line the index has always held; the outline shows `-> a.py` and the build reports its edge count. And a PostToolUse hook on Write and Edit runs the docs lint over a Markdown file or the swallow scan over a Python file - the same detectors `quality` folds - and returns the findings as an advisory `systemMessage`, capped, with the file named. It never blocks and it is opt-in: with no `post_edit_quality: true` in the authorization policy the script reads one small file and exits with nothing on stdout, so a project that did not ask pays one interpreter start and no more.
- Three additions, each recorded on the archive with an import verdict and a behaviour verdict before it was built. From an experiment loop's NaN fast-fail: `NonFinite`, a stop-algebra predicate that fires on the first NaN or infinite observation of a named metric and says which - `MetricPlateau` skipped such values silently, so a loop could keep spending its budget on observations that meant nothing. From a plugin's host fix: VS Code Copilot is detected the way it actually presents - `COPILOT_PLUGIN_DATA`, or a `CLAUDE_PLUGIN_ROOT` pointing into `.vscode/agent-plugins/` with no Claude Code entrypoint - in one function both host chains share, so a record's host label can never disagree between them. From a plugin's holdout harness: `experiment holdout` takes observations from two arms and a metric and computes a verdict from medians - `treatment`, `control`, `indistinguishable` when the arms sit within epsilon, `underpowered` below two observations per arm - commit-linked like every other experiment record and exiting non-zero on the two answers that are not a decision. Nothing else from the sweep imports: the daemons, proxies, embeddings and savings claims diverge on doctrine, and the rest was already here.
- A second field report from the same project, with godmode's own numbers: one session in observe mode, 304 would-have-asked and 0 would-have-denied - 137 inline interpreter runs, 78 scratchpad writes, 46 heredoc test-file writes - and the thirteen moments that were genuinely risky, worktree discards, a remote write, process kills, sat in the same "ask" bucket as `sed -n`. In enforce mode that is an interrupt a minute, ~97% of them on reversible work, and the report's verdict was the honest one: alert fatigue, then switched off within a day. The configuration it recommended instead - ask on the irreversible, silence the rest - could not be written. Now it can. `ask_only` in the authorization policy names the categories that keep asking; every other R2/R3 ask becomes an allow with an `action` record naming the silence, never a silent one. R4 still asks and R5 still denies whatever the list says, because the list narrows attention and never lowers the ceiling. It is a loosening, so no profile writes it; `roi --digest` proposes it from the observed records - the four irreversible categories plus any category that produced an R4/R5 event - and states how many asks it keeps and silences, so the operator adopts a number rather than a guess. On the reporting project's records the proposal keeps 30 of 304. The same report's stale brief had two causes beyond the age note already shipped: Claude's `hooks.json` never registered `PreCompact` or `SessionEnd`, so the session-end branch never ran on Claude Code at all, and the host's `SessionEnd` payload carries no summary, so when it does run it wrote nothing. Both events are wired now, and a session end with no summary writes a counts-only checkpoint that says it is automatic - not a handover, but dated today.
- Sprints L2 and L3 of the Code of Law loop. The operator-correction detector rides the prompt hook: a correction-shaped prompt (two or more distinct markers) writes a law candidate carrying keywords and a digest, never the sentence; `law candidates` clusters them read-time by keyword identity so a repeated correction increments one counter instead of splitting the ladder's evidence across duplicates. Delivery receipts land beside the brief: which laws each session was shown, counts only - the denominator without which "violated 0" cannot be told from "never seen" - and a law no receipt has ever named shows as dormant instead of being carried silently. `law promote` turns a promotable cluster into a guarded, active law, and the ladder holds: below three distinct sessions of recurrence, promotion is refused, not discouraged. And the guard-run rule from the same day's field report: a verified claim resting on a test file it read grades hypothesis until the run - `cmd:` resolved through this session's attestation - stands beside the file citation; reading a guard pins intent, only running it verifies.
- OpenCode carried the instruction adapter and the CLI, and `tool_call_interception: UNAVAILABLE` - a pre-tool boundary existed in its plugin API and nothing shipped to reach it. `adapters/opencode/godmode.opencode.js` is that shim: an OpenCode plugin whose `tool.execute.before` hook routes every `bash`, `write`, `edit` and `patch` call through the same `godmode_gate_fast.py` the other hosts call, and throws on anything that is not an allow - OpenCode's own documented way to stop a tool. It fails closed in four directions: a deny throws, an `ask` folds to a deny naming the staged-capability remedy (OpenCode has no approval prompt of its own), a missing interpreter throws, and an unset `GODMODE_PLUGIN_ROOT` throws rather than passing the call through ungated. The adapter reads OpenCode's payloads through Claude's dialect but keeps the OpenCode label, which is what makes that fold happen. Declared `SOFT`, not `HARD`: the shim is proven by tests that drive the shipped file under Bun, and a live OpenCode block still has to be chronicled before the claim rises. Install instructions in `adapters/opencode/AGENTS-godmode.md`; the community-catalog submission is in `docs/LISTING.md`.
- Sprint S4, three boundary moves. The claim gate reaches the message boundary: a Stop hook reads the turn's final text - in memory from the host's own transcript or Grok's `lastAssistantMessage`, never stored - and a claim-shaped sentence with no record behind it gets a systemMessage naming the sentence and the one command that records it. Advisory only, silent on ordinary prose, on recorded claims, and on the host's re-fire; seven field reports in one day ended "claim still unused", because the verb waited to be invoked - now the check happens at the moment of claiming. An enforce-mode ask is chronicled (`gate-asked`, tier and category, counts only) so tuning can finally learn from what the operator actually approves rather than only from observe trials. And the observe notice states its own age - "in OBSERVE mode since <date>" - because a trial whose exit rule never fires becomes permanent by silence, and a date turns that into a visible decision.
- Sprint L1 of the Code of Law loop (request 4110, decision 4114): `godmode law compile` folds every lesson that carries a generalized guard into a bounded `GODMODE-CODE-OF-LAW.md` at the project root - one law per lesson, guard first, provenance `seq:` beside it, ADVISORY until the promotion ladder ships, and the cap stated in the file itself when laws fall past it. A wrapper skill (`skills/godmode-code-of-law/SKILL.md`) carries the law to hosts where hooks are weak or absent. The file is a bound authority role, so the charter compiles it, `attest` enforces it and the required-sources counter lists it with no new machinery - the loop writes into the same slot a hand-maintained rules file occupies, and unlike the hand file it cannot rot unregenerated. The SessionStart brief carries the top three laws inside its existing budget: the law arrives; nobody has to fetch it. `law show` renders what the brief will carry. Detectors, receipts and promotion are the next two sprints.

### Fixed

- A Claude session on another project read the brief's observe-mode line - `r5=0 r4=0 r3=12 r2=328` - as "340 would-have-refused ops, none mapped to a real risk", and its 11-day-old checkpoint as the state, while `docs/STATE.md` held the current one. The observe line now leads with the count that means risk, zero stated - `0 would-have-denied at R4/R5 - none` - and calls the rest what they are: `340 would-have-asked at R2/R3 (friction, not risk)`, naming the `ask_only` posture `roi --digest` proposes to trim them. And when a project keeps its own state document (`docs/STATE.md`, `STATE.md`, `HANDOVER.md`, `HANDOFF.md`, `RESUME.md`, `STATUS.md`, root or `docs/`), the brief's checkpoint entry carries `resume_doc` and a stale checkpoint's note says to read that file first.
- Codex's field report on the hooks fix: with an unmodified Codex PreToolUse payload the gate answered `git add -A` and `rm -rf build` with `permissionDecision: "ask"`, and Codex - which "marks the hook run as failed, reports the error, and continues the tool call" on `ask` - ran them. Codex sends Claude's tool name (`Bash`) and sets neither `GROK_AGENT` nor `CLAUDE_CODE_ENTRYPOINT`, so the payload-shape step called it Claude, the one host whose `ask` is real. The detector now reads the two markers Codex documents as its own - `PLUGIN_ROOT` in the environment ("a Codex-specific extension") and `turn_id` in the payload - in both chains (`detect_host` and `current_host`), after Claude's and Copilot's own markers and after Cursor's and Gemini's unmistakable event names. An R3/R4 verdict on Codex now lands as `deny` with the staged-capability remedy, the way the Grok contract already folds it; two end-to-end tests run the hook on the documented Codex payload with no `GODMODE_HOST` override.
- Two checkers were reading their own records too literally. `status remaining` listed every obligation record whose status was not closed, so an obligation closed later through `remember --kind obligation --status closed` stayed on the list beside its own closure, and `retired` was not a word it knew - the latest record per subject is now the obligation's state, and retired counts as done. And the absorption checker compared the import verdict to its five words exactly, while the sweep writes the reason beside the verdict (`n-a - different surface (postgres table)`, `skip (FAISS dependency)`), which graded thirteen fully-judged items as half-judged; the verdict is now the leading token and the rest stays on the record as the why.
- A field report from another project: its session brief announced "508 unattested hard rules", and 308 of them had been compiled from `docs/LESSONS.md` - a ledger of 851 lessons, many written in the imperative, each read as a standing directive because the classifier reads text shape alone. A record is not a directive, whatever voice it is written in. The roles that hold what happened, what was decided and what exists - lessons, state, sprint-truth, decisions, inventory - now compile to ADVISORY at most, with `capped_from` naming the shape the sentence matched so the cap is visible rather than silent; the operating guide, the operator profile, the invariants and the checklist are untouched, so the same sentence is HARD in CLAUDE.md and ADVISORY in LESSONS.md. On the reporting project the HARD count fell from 512 to the directive-bearing documents' own. The same report found the brief surfacing a checkpoint eight days older than the project's state file without saying so; the brief's last-checkpoint entry now carries `age_days`, and past a week a note to prefer the project's own state document if it is newer and to write a checkpoint as part of the next handover. The third finding - fifteen observe-mode file mutations logged "silently" - is by design: the promotion prompt fires at three R4/R5 events, and R2 mutations sit in the brief's counts line.
- Codex and Grok both reported the same thing on 0.3.0, from opposite sides: every host discovers the one default `hooks/hooks.json`, and only Claude read the `command` + `args` pair it carried. Grok took the bare `python` token as a path beside the file and failed every hook open in 0 ms - the gate never ran; Codex refused the shape and its `/hooks` panel showed zero installed. The dedicated `.grok-plugin/hooks.json`, in the shape Grok documents, was never read (Grok's own guide lists `hooks/hooks.json` as a plugin's only hooks component). Every entry in the shared file is now one shell-form command string - `python "${CLAUDE_PLUGIN_ROOT}/hooks/..."` - which Claude substitutes natively, Codex honours as a compatibility alias, and Grok expands and aliases per its hooks guide; the PreToolUse matcher carries Codex's and Grok's tool names beside Claude's; `SessionEnd` fits Codex's 3-second budget and `PreToolUse` gets the generous bound Grok's fail-open timeout needs. Cursor's manifest, built by the same helper, gets the same shape. The dead Grok file is gone; `hooks status` reports Grok against the shared file. Hosts trust hooks per hash, so both will ask for trust again once.
- A decision body carried every host dialect's keys in one object - `hookSpecificOutput` beside a top-level `decision`, `reason`, `permission`, `user_message`, `agent_message` - on the assumption that a host ignores the keys it does not read. Codex's hooks reference says otherwise for one of them: a legacy `decision` field is "parsed but not supported yet. Codex marks the hook run as failed, reports the error, and continues the tool call" - so on Codex the union would have turned every deny into a fail-open. A positively detected host now receives exactly the keys its own contract documents: Claude and Codex `hookSpecificOutput` only (Claude was captured live honouring both shapes; the narrower one is what its reference lists), Grok its `{decision, reason}` beside Claude's key it was captured with, Cursor its `permission`/`user_message`/`agent_message`. Only an undetected host still receives the union.
- On Windows, `run_git` decoded subprocess output with the locale code page, so a staged diff carrying any non-ASCII byte crashed the reader thread - and took `egress --staged` down with it, found the moment a hook message with typographic quotes was staged. The failure direction was closed by accident (no scan, no commit), but a crashed scanner is not a verdict and says nothing about secrets. Git subprocess output is now read as UTF-8 with replacement everywhere `run_git` is the reader.
- `freshness` on a project whose records carry no `file:` or `commit:` citation returned `{"verdict": "fresh", "checked": {"commit": 0, "file": 0}}`, and a session reading it nearly quoted that as evidence that nothing had gone stale. The counters were right there and the verdict disagreed with them: a probe that reached nothing cannot tell clean from unchecked. The verdict is now `unchecked` when no local citation was reachable, `not_checked` names the absent reach in words, and the note tells the reader to read `checked` before quoting any verdict. `fresh` now requires at least one citation this run actually resolved.
- The request ledger recorded each operator ask under a subject that was the ask itself, bounded to 160 characters - prompt text in the store, while `GODMODE_PRIVACY.md` said the store holds no prompts. The subject is now `ask:<digest>`; the digest and up to 24 keywords keep the ask reviewable and closable, the sentence is never written, and the privacy contract says so in as many words.
- Integration the suite demanded for the new authority role: `code-of-law` carries a considered weight (0.95, beside invariants - a law is a guard the project already paid for) and a purpose sentence, so it never scores at the unweighted fallback or prints a blank line; and `init --roles` GENERATES the law file through `law compile` instead of stubbing it - on an empty archive that is the honest empty form, which binds the role on day one and says itself that no guarded lessons exist yet. A field project's name that had ridden into a source comment was scrubbed the moment the repo-privacy sweep named the file.
- `session open`'s handshake reported `read 0 of 8 required sources` - and the 0 was a literal. The counter was never wired to anything, so it could not have said a different number no matter what the session read; an agent that obeyed the line and an agent that quoted it in a status report and carried on both saw the same figure. It is a measurement now: a required source counts as read when a record in the archive cites it (`file:<path>`, the same evidence class every other check here trusts), the unread ones are named in the handshake, and the statement says to read them before the first mutation or to say which one is being skipped and why. A count with no list was not actionable; a count that could not move was decoration.

## [0.3.0] - 2026-08-27

### Added

- The chronicle's hash chain was tamper-evident mid-chain but silent on tail truncation: deleting the newest record(s) left a shorter, internally valid chain, and the head cache is an explicitly disposable hint a deleter can refresh. A sidecar chain anchor closes that (spec B4-1): a separate fsynced file recording {length, head_hash} after every sealed record, which the archive may only ever catch up to. A chain shorter than the anchor, or one that no longer passes through the anchored head, refuses reads with `tail-truncated` - on the full verify walk and on the append fast path alike, so a forged head hint cannot smuggle an append past it. An anchor lagging one behind the files is the legal crash window (record lands before anchor) and the next append repairs it; an absent anchor - every archive predating this - is stated in the verify report as `anchor-absent`, never silently trusted, and the first append writes one. Recovery is an explicit operator decision, never automatic: `godmode db --reanchor` accepts the chain that remains, rewrites the anchor to match, and chronicles the acceptance as a counts-only action record. The proof readers treat a truncation verdict as degraded evidence: the interception grade answers DEGRADED and the declared-gate ratchet answers with the strictest posture it could have given, because the record that would have relaxed either may be exactly what was removed.
- What godmode itself injects per session is now measured and mechanically capped (specs B4-2/B4-3). `godmode brief <task> --measure` reports bytes and estimated tokens per brief section, counts only - the measurement never carries a body. A checked-in budget test grows an archive to hundreds of records and red-lines if the session hook's rendered brief ever exceeds its documented cap or reaches the mid-JSON truncation backstop (a truncated brief is an unparseable brief), and pins the continuity brief's degradation ladder to landing inside its token budget or declaring what it dropped. The typed-compression mask registry is complete again: eight shipped record kinds (action, branch, criterion, database, inventory, pin, request, session) had no declared mask and compressed to a default that kept little or nothing their payloads hold; each now declares what a compressed view keeps. Completeness is enforced by a test that enumerates every literal-kind chronicle writer from the source itself (AST scan), so a new writer is swept in automatically, and the registry is grow-only against a pinned floor - a mask outlives its writer, because old archives still hold the records.
- The session brief now answers the first question a resuming agent actually asks - was I mid-task? (spec B4-4). A counts-only resume digest rides the existing brief inside its budget: the last checkpoint (subject, status, sequence), the count of its declared next-actions still open, the unattested-HARD count lifted from the obligations block already computed rather than derived twice, and a disposition tally over the last verdicts. A checkpoint whose `file:` evidence refs no longer resolve is marked stale with the count of dead refs rather than repeated as truth. When a session ends - or compacts - with declared work in flight (open next-actions, an unconsumed staged capability, an active plan fence), SessionEnd/PreCompact records an `interrupted-intent` action: counts and 16-hex subject hashes only, a shape the kind invariant now enforces at the append seam so free text cannot be smuggled into it, and the next session's digest surfaces the interruption ahead of everything else. A checkpoint recorded after the interruption retires it from the digest; a clean end records nothing; an uninitialized project stays silent.
- `godmode trends` renders the per-session measurement records the session log already writes as a counts-only time series (spec B4-5): one line per session - turns, commands, test runs, tool calls, tokens in/out - bounded by `--sessions`, with `seq:` references for every counted record. An unmeasured session appears as a stated gap with its recorded reason and never carries a number: gaps stay gaps, never interpolated. The render holds the same causal denylist the ROI reports pinned first - what was counted, never what the counts supposedly earned or averted - and a record's free-text fields never reach the report or the render.
- `godmode context structure` builds an incremental per-project structural index and renders a bounded outline from it, so resume-time context can come from a cache instead of re-reading source (spec B4-6, MVP scope stated rather than implied). Python files contribute top-level classes, functions, and imported module names via `ast`; every other text file gets a file-level entry. The index is keyed by content hash - an unchanged file is never re-parsed - and stores names and hashes only, never a source body, as disposable state-home data whose loss costs one rebuild. Walk and parse bounds are stated in the report (file cap, oversized-parse skip counts), the outline caps its lines and says how many entries are not shown, and a Python file that fails to parse degrades to a file-level entry instead of failing the build. Not claimed, and carried as `partial` in the capability coverage map: method-level symbols, call graphs, control-flow and data-flow tiers, non-Python symbol extraction.
- Three B4-7 riders, each turning a habit into a mechanism. Edit-count checkpoint trigger: every allowed tracked-file mutation (Write/Edit/NotebookEdit/apply_patch, counted only after every gate said yes) ticks a disposable counter outside the hash chain; at the threshold (default 20, `checkpoint_every` in the authorization policy clamps tighten-only - lower is allowed, looser is not) the allowed call carries a one-line checkpoint suggestion, and with `auto_checkpoint: true` declared the hook writes a chronicled `auto-checkpoint` record (counts only) and resets. A manual `godmode checkpoint` resets the same counter. Flat lesson ledger: `godmode lessons add <subject> --guard <rule>` writes one typed lesson record into the chronicle and `godmode lessons list` reads them back bounded - no daemon, no database; bare `godmode lessons` keeps the promote-or-retire pipeline unchanged. Dogfood restore-on-next-run (CX-5's parked M1): the plant harness now writes a byte-snapshot registry to disk before any plant mutates a target, and the next run's setUp restores whatever a killed run left planted before doing anything else - an external kill bypasses every in-process finally by design, so nothing but a later run can heal what it leaves, and now the next run does.
- Observe-mode trials now produce visible evidence without being asked (spec B4-10): three governed tasks under `gate_mode: observe` had produced zero visible signal, leaving the operator nothing to decide promotion with. A session that opens under observe now carries the trial's would-have events in its brief - counts by tier plus the highest-tier example's category, counts only - and states the zero case explicitly rather than staying silent. `assess` and the status document surface the same tier-shaped `would_have` block (`{r2, r3, r4, r5, total, top}`) whenever an archive exists, zero stated. A new `godmode observe` command answers with that summary; `godmode observe --report` lists the last N would-have decisions with tier, category, reason and the operation text itself - command text appears on this one surface only, because the operator reaches it by explicitly asking, and it is still redaction-scanned (whole-value replacement via the same secret-shape scanner egress and verdict use). Observed refusal records now persist the refusal's own reason (bounded), and a secret-shaped operation no longer vanishes from the record entirely - `Chronicle.append`'s privacy refusal used to be swallowed by the best-effort write, silently dropping the event; the record now persists with its text redacted whole, so the event stays countable everywhere. When accumulated R4/R5 would-have events reach the promotion threshold (3), the brief states plainly how many operations would have been denied or asked about at the irreversible tiers and names the one edit that promotes the gate to enforce.
- The chronicle answered "what happened" but not "which agent did it": every record carried a host, a model and a platform, so two agents working the same project on the same host shared one identity and their work interleaved into a single indistinguishable stream. B5's first unit adds the identity that the rest of fleet governance stands on, plus the two coordination facts that identity makes expressible. `godmode fleet show` reports the agents, their live leases and the delegation graph; `fleet lease` takes an exclusive lease on a resource and `fleet release` gives it up; `fleet delegate` records that one agent dispatched another. Identity is declared through `GODMODE_AGENT_ID` when the host sets one and otherwise derived from the process, hashed and truncated so no hostname travels in a record - an undeclared agent gets a distinct id rather than collapsing into a blank every other undeclared agent also shares. Two states that cannot be repaired after the fact are refused at write time rather than reported afterwards: a second agent taking a resource someone else holds (the same holder re-acquiring is an extension, so a long task renewing its own lease does not deadlock against itself, and a foreign release is refused so exclusivity cannot be cleared and then taken), and a delegation that would make an agent its own ancestor. Both refusals carry a failing exit code, so an agent scripting against the CLI reads the refusal from the status and not only from the text. Leases expire by the clock at read time instead of being swept, so a crashed agent releases its hold without any reaper process needing to run. The whole layer stores nothing of its own: it is a fold over `decision` records carrying a `fleet:` subject, the rule the disposition register already follows, which keeps the record-kind enumeration closed and leaves no second copy that could drift from the ledger backing it.
- A claim graded `verified` because `file:src/api.py` resolved kept that grade for the life of the archive. The grade was true about the file as it stood that day and nothing re-read it afterwards, so a later session inherited full confidence about a state that no longer existed. `godmode reanchor` names the citations that came loose, in the two ways they do. A cited file committed after the record was written means the evidence readable now is not the evidence that was graded then. A `commit:` citation naming an object the repository can no longer reach means a rebase, squash or history rewrite replaced it - which is not hypothetical for a project with a history scrub ahead of it, since the scrub orphans every commit citation in the archive unless they are re-anchored first. Run against this project's own archive the check reports 85 stale file citations and no unreachable commits, the second number being exactly what a scrub would change. Detection needs no new field and no schema change: `recorded_at` is already on every record, so the check works retroactively across an archive written long before it existed, and history is read in a single `git log` pass rather than one subprocess per citation. Git stamps commits in whole seconds while records carry microseconds, so both sides are compared at one resolution and a same-second tie stays quiet - within one second the order is genuinely unknown, and over hundreds of citations a false alarm on every record written next to a commit costs more than a one-second blind spot. Nothing is regraded. A stale citation means "read this again", which is a different fact from "the evidence never supported it", and only a person can tell those apart; the report states the no-regrade stance in its own output rather than leaving a reader to infer it.
- Detecting that a `commit:` citation came loose is only useful if something recorded what the sha pointed at before it vanished; otherwise "this commit is unreachable" is the end of the story and the evidence behind a verdict is gone with no way back. A history rewrite changes shas and keeps what a commit is - the tree it produced, its subject line, and when its author wrote it - so `godmode reanchor --snapshot` records that triple for every cited commit, and `--remap` matches it against the rewritten history afterwards to recover each new sha. The two are separate deliberate acts because ordering is the contract: a snapshot taken after the rewrite records the new sha and says nothing about the old one. Both are recorded, so a later session reads a mapping back rather than re-deriving it against a history that may move again, and a citation with no snapshot behind it is reported as unresolved rather than guessed at. Run against this project ahead of its planned scrub, 27 cited commits are fingerprinted and none are unrecoverable. Three defects surfaced while building it, each from running the thing rather than reading it. Reachability was being asked with `cat-file -e`, which answers whether the object is still in the database - a rewrite leaves the originals there until garbage collection, sometimes for weeks, so the check would have answered "all fine" for citations pointing at commits no ref could reach, which is the exact failure the module exists to catch; it now walks the ref graph once with `rev-list --all`. The snapshot was scoped to the record kinds that assert something, reusing the scope that belongs to staleness, where only an assertion can decay: preservation is a different question, since a rewrite orphans a citation wherever it sits, and on this archive all 34 commit citations live on `checkpoint`, `sprint`, `lesson` and `decision` records and none on the asserting kinds, so the scoped version recorded nothing at all. And a citation reading `commit:c5fa933 CI green` - a sha with trailing prose, written by hand - was read whole and reported a reachable commit as unrecoverable, a false alarm in the one report that must not cry wolf before a scrub.
- Every record already said which host and which model wrote it, which stops being an identity the moment two agents share a host: concurrent lanes interleaved into one stream where no record could be attributed to the lane that produced it, and the fleet layer could name a lease holder that nothing in the archive could then confirm. `writer_fingerprint` now carries `agent_id` alongside host, model, platform and interpreter, so namespacing records by agent is real rather than nominal. The id is hashed and truncated before it travels, and the fingerprint's standing privacy check - no hostname, no home directory, nothing naming a person - still holds. Delegation also gained the closing act it was missing. A lease lapses by its own term, but a finished dispatch had no way to be expressed, so every edge ever written stayed live and the graph only grew; `godmode fleet retract` closes one, and only the parent that opened it may. Retraction supersedes rather than erases - the fold takes the latest record per child, so a closed edge leaves the graph and a later re-delegation reopens it - and it frees the cycle guard too, since the guard reads the live graph and a closed edge that kept constraining it would make retraction cosmetic. A delegation written before this existed carries no state at all and is read as active, so upgrading does not empty the graph. The gap surfaced from leaked smoke-test records rather than from design review: stray leases lapsed on their own while stray edges stayed forever, with no supported way to close them.
- A stale citation on a claim is a different event from a stale citation on an attestation, and the report treated them alike. A claim or a verdict asserts something that is either still true or is not; an attestation records an act - at this time I performed this step, citing this file - and a later edit to that file does not falsify the act, it only means the evidence moved on. The proportions are what made the distinction load-bearing rather than tidy: of the 85 stale citations in this archive, 80 are attestations, so the five standing assertions that could actually be wrong sat buried in a flat list nobody would read to the end. `godmode reanchor` now ranks them, keeping the full list so nothing is hidden while making `standing` reachable on its own. Reading those five settled them: two are eval fixtures whose checkers are literally `python -c "sys.exit(0)"` and `sys.exit(1)`, so they assert nothing about this project; two remain true, since `roi_report` still folds `kind="refusal"` records into `gate.denied` and `rank` still degrades a non-git project's ordering to a path sort; and one had stopped being true, because `AdvisoryReviewRepoTests` no longer calls `skipTest` at all and its single test now runs and reports ok. A superseding claim records that, and records it as a hypothesis rather than as verified: the claim gate reads "no longer calls skipTest" as an absence claim, which rests on one probe unless a second and different one is cited, and the command citation offered as that second probe does not resolve without a session transcript. Left graded as the gate graded it, since forcing the grade would defeat the check.
- The archive already held checkpoints carrying a `head` commit, but their `status` was free prose - "865 tests OK on the frozen tagged tree" is a sentence, not a fact a machine may act on, and reading a restore point out of prose is the inference this project refuses everywhere else. Green is attested instead: `godmode rollback mark` records the command that ran, the exit code it returned and the commit it ran against, and refuses outright to mark a commit green from a failing run - a restore point nobody proved anything about is worse than none, because it carries the authority of a green without the evidence of one. `godmode rollback plan` names the newest green whose commit the repository can still reach, says what proved it, lists the files that changed since, and surfaces any uncommitted work. A green whose commit a history rewrite stranded is skipped rather than offered, since a restore point `git` would reject is a promise the repository cannot keep. Nothing executes. Restoring is `git reset --hard` territory - it destroys uncommitted work, and the archive cannot see the working tree - so the plan reports `executed: false` in its own output rather than leaving that to trust, and the command it hands back is the non-destructive one: a new branch at the green commit, which loses nothing and can be thrown away. The destructive alternative is offered separately and labelled with what it would discard, so choosing it is a decision rather than a default someone pasted. Like the fleet layer this stores nothing of its own - greens are `decision` records under a `green:` subject, folded on read.
- Two questions over the corpus the gate has been building. Each refusal record carries the operation, the tool, the category and the tier it held at the time, which makes both answerable from this project's own history rather than from a heuristic tuned by feel. `godmode forecast` classifies an operation before it runs and says whether this project has met its shape before - a tier alone is a rule, while a tier plus "this category was refused 44 times here" is a reason, and a reason is what makes an interruption worth reading; precedent is counted over distinct operations rather than raw records, because the same command refused forty times is one precedent said forty times. `godmode replay` re-classifies the operations the archive already holds under today's rules and compares them against the tier recorded then, which shows what a policy change did to work already done - a question the policy file cannot answer, having no memory of what it used to say. The direction of drift carries the meaning, so tightenings and relaxations are reported separately rather than summed into a count of differences that hides which way they went: a stricter rule is the ratchet working, while a looser one means something once stopped would now pass. Run against this project's archive it replays 1864 recorded operations and reports 9 tightenings (all `rm -rf /` moving R3 to R5, the security batch landing), 3 single-tier relaxations on compound commands, and 9 probe sentinels excluded as synthetic. That last exclusion is load-bearing: `hooks probe` records refusals whose operation is a sentinel token rather than a command, the plain classifier cannot rate a token, and left in they accounted for the entire apparent relaxation. Nothing here writes a record or changes a policy; it reads.
- The minimality report has always counted duplicated authority, speculative seams, orphans and charter decay, and a number nobody compares against anything is a number that gets ignored: this session added seven modules and the seam count moved, noticed only because someone happened to run the report twice. The counts now carry a recorded ceiling. `godmode minimality --set-baseline` writes it, every later run compares against it, and growth past it exits non-zero until it is answered for with `--accept-growth <section> --reason ...`, which puts the reason in the record. The shape is the swallow ratchet's, already proven in this tree, and it differs in one deliberate way: swallowed errors should only ever fall, so that ratchet's ceiling never rises, while minimality counts rise whenever a feature legitimately lands. A never-rising ceiling would be red forever after the first one, and a gate that is always red is a gate people learn to skip - so growth is accepted rather than forbidden, and the cost of accepting it is stating what the added surface bought. An absent baseline reports itself as absent rather than as zero growth, because reporting no growth against nothing would read as a clean bill of health. A fall is reported alongside growth, since a ratchet that only ever speaks to complain teaches its reader to expect bad news. Accepted growth exits zero, because failing on a decision the record already carries would punish saying why.
- Three detectors already produced quality findings in three shapes - the docs lint, the swallow scanner, the minimality report - and a reader who wanted "what is wrong with this tree, worst first" ran all three and merged by hand. `godmode quality` folds them into one canonical, severity-ranked list, computing nothing new: the same aggregation-only stance the minimality report takes over the atlas. Remediation is guarded structurally rather than by a flag. Every finding carries its remedy as a proposal and the command has no apply path; a test pins that the tree is byte-identical after a report, because a remedy the operator has not run is a sentence, not a change. A `high` finding, and only that, reaches the exit status - the rest are questions. The same findings reach an editor through `--format editor`, one `path:line: severity: message` per line in the shape VS Code's default problem matcher already parses, or `--format sarif` for the SARIF viewers. Nothing is installed into any editor; a format is a view, not a verdict, so the exit status is identical across all three. Closes C-05 and C-63.
- A standing record cites its sources, and two of the three citation classes could already be checked locally by the re-anchoring code - a `file:` committed after the record was written is stale, a `commit:` no longer reachable is gone. `godmode freshness` layers on those two checks and adds what a preflight is for: the honest statement of what it could not check. A `url:` citation is reported as unverifiable, never as fresh, because godmode never touches the network; a non-git project's `file:` and `commit:` citations are reported as unchecked because there is no history to compare against. `partial` is true whenever anything was left unchecked and is not a failure - an honest partial exits 0 - since the alternative, a preflight that stays quiet about what it skipped, is the thing this replaces. Stale or unreachable is the finding, and reaches the exit. Closes C-10.
- `--brief` gives one glanceable line and leads with the verdict, which is the right first word for a reader deciding whether to look closer and the wrong one for a reader who has already decided to act. `--terse` is the profile for the second reader: the next action on line one, then one line per finding, then the same line `--brief` would have printed. When there is no action the first line says so - `next: nothing - clean` - because a missing line reads as "nothing to do" without ever committing to it. Findings are capped at ten and the cap is stated as `... N more`, not swallowed. Nothing is computed that `--json` does not already carry; the profile is a reorder of the same payload so the first thing on screen is the thing to do. Closes C-11.
- A forged skill carried routing cases and behaviour assertions, and nothing that said what the skill was expected to *produce* on any particular host - the thing a host's own eval runner compares against. `skill forge` now writes `fixtures/<host>/expected.json` for each of the five hosts this plugin ships an adapter or manifest for, one case per positive trigger, each naming the expected output from the proposal's assertions. `skill validate` counts them and refuses a skill missing any host's fixture, so "this skill works on five hosts" has five files behind it rather than a sentence. Closes C-23.
- `docs/DEMO.md` pins its commands against the parser, which proves a command exists and nothing about what it returns. `examples/*.example.json` is a corpus where each worked example names a command, the keys its payload must carry and the exit code it must return, and `godmode examples --check` runs every one against the real console in a throwaway project under a throwaway state home - in-process, no subprocess, no network. A worked example that drifts from the code fails the check and names itself, instead of misleading the next reader. `godmode examples` alone lists the corpus. Four examples ship: `init`, `doctor`, `capabilities`, `quality`. Closes C-24.
- A capability can now install as an extension instead of growing the core. An extension is a directory under the private state home with an `extension.json` manifest and an entry module exposing `run(argv, context)`. `godmode extensions` lists what is there from manifests alone and imports nothing, so a listing can never execute code that merely sits in the directory. `extensions run <name>` imports and runs one, and only when the project's authorization policy names it in an `extensions` list - a file the gate already protects, so enabling an extension is an operator act on a governed surface, never a side effect of placing a directory and never something a tool call can do unasked. An extension is a way to split godmode's own capabilities; it is not a runtime dependency on a third party, and the doctrine that godmode owns its capabilities stands. Closes C-52.
- `godmode watchdog` reads the newest window of the project's own record and names three anomaly shapes, each a failure actually observed in agent runs: the same operation attempted three times in a row (the loop a failing step becomes), a burst of refusals close together (probing the gate instead of doing the work), and a run of actions with no attestation behind any of them (work not being verified as it goes). No daemon: godmode is invoked, never resident, and the privacy boundary forbids a watcher, so "during a run" means between steps and the report's `note` says so. `--interrupt` writes the operator-stop flag the stop algebra already honours, only on anomaly, so an anomaly halts the next guarded step with no new mechanism. Operations are reported by digest prefix, not text - the archive already holds the text, and a report should not be a second copy of it. Closes C-55.
- Two plans for the same work, and a reader who wants to know which one to hold the agent to. `godmode arbitrate --plan A --plan B` scores each on what a plan can be held to - acceptance criteria stated, verification steps named, `file:` citations that resolve in this tree, open questions left - as a small integer sum so every point is legible in `reasons`. The arbiter is deterministic and never picks silently: a tie returns `undecided` with both scores shown and exits non-zero, because its job is to make the difference between plans visible, not to break a tie the plans themselves do not break. Closes C-56.
- `docs/LADDER.md` is four tiers of onboarding - day one, a working session, a governed session, a fleet - each one session's worth and each a fenced `console` block. Every `$ godmode ...` line in it walks the real parser the way README.md's and DEMO.md's do, so a tier cannot name a command that does not exist. `godmode guide --tier N` prints one tier and nothing else, so the day-one reader is never handed the fleet tier by accident. Closes C-61.
- The claim gate downgraded an unsupported claim, but only one that went through `godmode claim`; prose typed into README never met it. `godmode claim --scan` closes that gap with a definition and a check. A claim on a public surface is a sentence carrying a measured number with a unit or percent, or a verb that promises an outcome - prevents, guarantees, eliminates, ensures, blocks every, catches every. *Never* and *always* are deliberately not claims: on these surfaces they say what godmode does not do, which is honesty rather than a promise. A claim is covered when its line names its own reproduction - a backticked command, a `tests/` or `docs/` path, a link - or when a claim record carries its text; description is not gated. A test runs the scan over this repository's own README, listing, coverage map, `llms.txt` and `GODMODE.md` with an empty archive, so coverage must come from the prose itself. Its first run found two measured latencies whose only basis was "same source" and "same method"; both rows now link the release notes they came from.
- Added a truthful interception proof (CX-1). `tool_call_interception` used to be reported `HARD` from `GODMODE_PRETOOL_GATE`, an environment variable nothing shipped ever set - the claim could be silently wrong while a host really was calling the hook, and trivially fakeable by exporting the variable by hand. That sniff is deleted. In its place: `godmode_hookproof.py` recognises a marker operation (`godmode-probe:<nonce>`) that the pre-tool hook (`hooks/godmode_session_hook.py`) treats as protected, denies unconditionally - no staged capability, ceiling, or observe-mode conversion may turn it into an allow - and records the denial as a chronicled `hook-interception-proof` record; the denial is the proof. `interception_state(archive, host)` reports `HARD` only while that proof is fresh (recorded at or after the current session opened) and nothing newer says the hook came down (`hook-uninstalled`) or a later probe failed (`probe-failed`); every other case, including no proof at all, reports `UNAVAILABLE`. New CLI surface: `godmode hooks status --json` (manifest wiring + last proof + verdict) and `godmode hooks probe --json` (self-injects a probe through the real hook and verifies it end-to-end; exits 0 only on a verified proof). `godmode_anchor.host_capabilities` now takes the resolved `tool_call_interception` value from its caller instead of reading any environment variable.
- Added a canonical host-event adapter (CX-2). Every pre-tool payload - Claude's, Codex's `shell_command`/`apply_patch`/`functions.exec`, Grok's `run_terminal_command`/`write`/`search_replace`, or a bare `{"operation": ...}` string - now translates once, in `scripts/godmode_runtime/godmode_hostevent.py`, into one canonical `HostEvent` (`schema`, `event`, `host`, `tool`, `operation`, `targets[]`, `cwd`, `request_id`, plus optional `tool_kind`/`approval_context`/`actor`) before the classifier, capability broker, or scope fence ever see it. Field names are read through a dual-casing lookup (`hookEventName`/`hook_event_name`, `toolName`/`tool_name`, `toolInput`/`tool_input`, `sessionId`/`session_id`, `workspaceRoot`/`cwd`) so a host's casing convention is never a special case. Host detection follows `GODMODE_HOST || GROK_AGENT || CLAUDE_CODE_ENTRYPOINT || payload-shape || "unknown"`; no env var ever decides an interception CLAIM - that stays `godmode_hookproof.py`'s chronicled-proof job exclusively (CX-1). Codex's `apply_patch` reaches the scope fence for every add/update/delete/rename target the patch names, not just one. An unknown tool name never degrades into a guessed operation string (the old `f"{tool} tool invocation"` fallback in `godmode_guardrails.tool_operation` is gone) - it fails closed on its own `unrecognized-tool` category, chronicled with counts only (host + tool name, never the command). The response is one JSON object carrying every documented dialect's key at once (Claude's `hookSpecificOutput.permissionDecision`, Grok's `decision`, Cursor's `permission`) so a host reads only its own key safely; a host with no `ask` decision (Grok, Codex, Gemini) receives `deny` with a reason naming the staged-capability remedy the instant the classifier would otherwise have asked. **`hooks/godmode_session_hook.py`'s exit code 3 is removed entirely** - a live Grok probe proved that host fail-opens on any exit code it does not recognise (only 0 and 2 are documented), so every deny path now uses exit 0 (JSON-signalled, Claude's own tested contract) or exit 2, never 3. Gate-exactly-once: `parse_host_payload(raw, seen=...)` takes a caller-owned, in-process request-id set so an orchestration wrapper that unwraps to the same call twice reaches the gate once, documented honestly as an in-process guard only. A payload-capture probe (`GODMODE_CAPTURE_HOST_PAYLOADS=1` or `--capture-payload`) records an unrecognized host shape's event/tool names, sorted input field names, and hashes of the request id and cwd - never a value - for building future host fixtures.
- Added native per-host hook manifests, generated by the same mechanism as every identity manifest (CX-3). `packaging/hosts.json` gains a `hook_manifests` section; `godmode bindings --write`/`--check` now also regenerate and drift-check them, driven by the new `scripts/godmode_runtime/godmode_host_manifests.py`. Codex's two native, live-audit-verified event keys (`session_start`, `pre_tool_use` - confirmed against this build's own `~/.codex/config.toml` `hooks.state` table) are merged into the existing shared `hooks/hooks.json`, using `${PLUGIN_ROOT}` (Codex's native root variable) and never `${CLAUDE_PLUGIN_ROOT}`; every one of Claude's own three keys stays byte-identical. Grok gets a dedicated `.grok-plugin/hooks.json` (CamelCase events `SessionStart`/`UserPromptSubmit`/`PreToolUse`/`PreCompact`/`SessionEnd`, single-string `command`+`commandWindows` entries per Grok's own documented format - never an args array - and the plan's exact matcher union). Cursor gets a dedicated `.cursor-plugin/hooks.json` (`"version": 1`, camelCase `sessionStart`/`preToolUse`/`beforeShellExecution`, `failClosed: true` on both gate hooks). Gemini CLI gets a dedicated settings.json-fragment (`.gemini-plugin/hooks-fragment.json`, `BeforeTool` matcher, millisecond timeouts, `${extensionPath}`) documented as a fragment to merge, not an auto-loaded manifest - the surrounding full `gemini-extension.json` stays an explicit gap. Every emitted event name is drawn from an allowlist constant traceable to a specific spec addendum (`CODEX_HOOK_EVENTS`, `GROK_HOOK_EVENTS`, `CURSOR_HOOK_EVENTS`, `GEMINI_HOOK_EVENTS`); an unverifiable name is omitted, never guessed. `hooks status` gains a `host_registration` block (per-host manifest presence + drift, structural only). `godmode hooks install --host <name>` verifies each declared hook against the host's own inspectable state (Codex's `config.toml` `hooks.state` table; Grok's `inspect --json`) and fails nonzero listing missing hooks on partial registration - reporting "unverifiable" honestly wherever host state cannot be read (Cursor, Gemini, or any host with no reachable state). The base `plugin.json` (Agent Plugins Specification v1.0.0) is unchanged in shape and validated against its closed field list by a new `validate_plugin_v1` check; its `extensions.*.host_manifests` map gains `cursor`/`gemini` entries. The skills roster fix (Addendum 6): `skills/godmode/SKILL.md` resolves the CLI via `$GROK_PLUGIN_ROOT || $CLAUDE_PLUGIN_ROOT ||` a `__file__`-relative fallback instead of naming Claude Code specifically; `skill forge --destination` now defaults host-neutrally (`.grok/skills/` on Grok, `skills/` elsewhere) when omitted. Rider: the swallow scanner (`godmode_swallow.py`) excludes `.claude/worktrees/` from its raw filesystem walk, closing a release-night finding where a nested agent worktree's own full repository copy was double-counted.
- Added a host-independent git-hook enforcement backstop (CX-4): `godmode hooks install|status|verify --git`, wired into `godmode guard --git-hook <name>`. Install writes real, project-local `pre-commit`/`pre-push`/`pre-rebase`/`post-checkout` hooks (marker comment + content hash, executable, sh-compatible on both POSIX and Windows Git Bash - `python3` tried before `python`, neither found fails closed) that call back into `godmode guard --git-hook <name> --json` and exit nonzero on a protected verdict - a second boundary at git's own chokepoint, independent of whatever host (or nothing) drives git. Opt-in and tighten-only: install refuses unless the project has declared `{"git_backstop": true}` in `.godmode-authorization-policy.json`, ridden through the existing `declared_gate_ratchet`; a pre-existing, non-godmode hook is never overwritten (`skipped_foreign`, never a silent clobber), and `.sample` files are never read as installed. Each hook's own visibility limit is stated in code, docs, and its own status/verdict output rather than implied: `pre-push` reads stdin ref-update lines plus `git merge-base --is-ancestor` to detect a non-fast-forward push - it cannot see the `--force`/`--force-with-lease` flag itself, only its sha-level consequence; `pre-commit` sees the staged file-name list only (detects a pinned evaluator about to be committed, nothing about content); `pre-rebase` cannot tell which pushed history it would rewrite, so every rebase is protected uniformly; `post-checkout` runs after the checkout already happened and can only report a pinned-evaluator tamper loudly, never undo it. A protected verdict under declared policy still honors a one-use staged capability (`CapabilityBroker.consume_staged`), the same escape valve the interactive gate already uses - reusing the exact classifier (`classify_action`) a plain `git push` is already protected under there, rather than a second, independently-tuned protected-operation list. `godmode hooks status --git` distinguishes a real godmode-owned hook (`godmode`: its actual on-disk body, re-hashed excluding its own digest header line, matches what that header line claims) from `godmode-modified` (marker present, body hash no longer matches - detected from the file's REAL bytes every time status runs, not from an independently-regenerated "ideal" string, so a hand-edit is caught even when the header line itself is left untouched), `foreign` (no godmode marker - never touched), and `absent`. Malformed or unreadable `pre-push` stdin (a line that fails strict 4-field ref-update parsing, or a stdin read failure) is never folded into "nothing to push": under declared policy it fails closed (blocked, chronicled, counts-only); undeclared it stays advisory-only - a genuinely empty stdin, with no lines at all, is the single case read as "no ref updates." `godmode hooks verify --git` proves the mechanism live in a fully throwaway bare-remote-plus-working-repo pair (never the real project's own git state): it installs the real `pre-push` hook into that scratch repo, attempts an ordinary unauthorized push, and only on a confirmed block - exit code AND an unchanged remote ref, never inferred from empty output - records a CX-1 proof record (`godmode_hookproof.record_interception_proof`) with `host="git"` into the caller's real archive; a failed attempt writes the same `probe-failed` record CX-1's own probe uses, so a later `hooks status` reflects the failure too. Uninstalling (`hooks install --git --uninstall`) removes only godmode-owned hooks, never a foreign one, and is itself a chronicled, counts-only event (`hook-uninstalled`, `host="git"`) - the `git_backstop` declaration stays visible afterward via the ratchet. **Disclosed, not claimed away:** `git push --no-verify` (and any client that skips or reroutes hooks, e.g. `git -c core.hooksPath=<elsewhere>`) bypasses every client-side hook including this one - git's own documented escape hatch. This backstop raises the floor for the default/cooperative path; it is not an unbypassable wall for a caller with ordinary git-CLI access, and `hooks status --git`'s own output (`known_bypass`) says so, not only this note. New module `scripts/godmode_runtime/godmode_githooks.py`; new tests in `tests/test_githooks.py`, run against real git repositories and real `git push` subprocesses throughout (a mocked git boundary is exactly the "empty stdout read as allow" harness failure this batch's own design doc warns against).
- Added CX-5's five-level interception scale (`UNAVAILABLE`/`SOFT`/`PARTIAL`/`HARD`/`DEGRADED`), replacing the binary `HARD`/`UNAVAILABLE` `godmode_hookproof.interception_state` reported since CX-1: `SOFT` is the honest floor for a host whose skills+CLI cooperation layer is installed with no hook proven at all (the true state on every host today except a freshly probed Claude Code); `PARTIAL` is a hook structurally discovered/registered (per the shipped manifest or CX-3's registration report) with no fresh live proof; `DEGRADED` is a proof that was demonstrably fresh and CX-5-enriched but is now superseded (`hook-uninstalled`/`probe-failed`/the new `hook-health-degraded`), expired, or drifted (`hook_version`/`trusted_hook_hash` mismatch) - the regression case the old binary scale could not tell apart from a fresh install. Proof records are enriched (privacy-safe: hashes, counts, bounded enum strings only) with `hook_version`, `project_identity_hash`, `trusted_hook_hash`, `nonce_hash`, `observed_decision`, `host_acknowledgement`, and `expiry`; freshness for `HARD` is now session-anchored AND unexpired. A pre-CX-5 minimal proof record still reads without error and stays valid input, but can never claim `HARD` again - it grades at most `PARTIAL`, disclosed as a real, honest behavior change rather than silently patched around. `KIND_INVARIANTS`' action-kind validator gained additive type-checks for every enrichment field, without weakening the original CX-1 required-field check. The module docstring states the doctrine verbatim: "Silence from a failed verifier is never evidence of permission." `godmode hooks status` gains `matched`/`invoked`/`honored`/`version`/`degraded_reason`/`latency`/`fail_open_host` fields (honest `"unknown"` where not inspectable); the session-start brief carries a persistent, visible warning line the moment a host's grade is `DEGRADED`, naming the specific reason, until a fresh probe passes. `run_probe` now measures its own round-trip latency against the host's declared PreToolUse timeout budget (read from the real shipped manifest, never a duplicated literal) and warns when the margin falls under 50%, persisting the measurement so `hooks status` can surface it for a fail-open host (Grok/Gemini/Cursor-default) without a fresh probe on every read; a subprocess timeout and an unexpected (neither 0 nor 2) exit code are now distinguished, bounded failure reasons rather than folded into one generic "subprocess failed." The mode table (uninitialized project allows ordinary work and states the gap, never denies; a registered-but-degraded hook carries a visible warning; an identity mismatch (git-init archive-stranding) makes no continuity claim and names `godmode adopt --confirm`; a malformed hook payload fails protected classes closed while leaving the read-only fast path untouched; observe mode never blocks and labels every would-have decision) is pinned directly, several rows against mechanisms that already existed and are now bound to this contract by test. `HostEvent.approval_context` (host sandbox-approval metadata, when the payload carries one under a best-effort field-name guess) is now populated and recorded, but never consulted by any decision path - godmode authorization and a host's own sandbox approval stay two separate boundaries in both directions, pinned by one test each way. `CapabilityBroker`'s existing digest mechanism (normalized-operation hash + project/worktree/head context + expiry + single-use nonce, consumed immediately at decision time) is extended with the one contract-listed element it was missing, `branch` (two branches can share one HEAD commit, so `head` alone cannot always tell a checkout apart) - a changed command, branch, target, or project all reject; a subagent's own actor identity is confirmed, structurally, to never widen a staged capability past its exact operation digest. New `tests/test_failure_semantics.py`; `tests/test_hookproof.py`, `tests/test_pretool_gate.py`, `tests/test_host_control_parity.py`, and `tests/test_sentinel_depth.py` extended for the widened grading and the new context field.
- Added the CX end-to-end harness and release gate (`tests/e2e/`). `harness.py` builds a real temp git work repo plus a real bare remote, replays per-host dialect payloads (Claude/Codex/Grok/Cursor/Gemini) through the actual `hooks/godmode_session_hook.py`/`hooks/godmode_gate_fast.py` subprocesses, and enforces a FOUR-PLANE checklist on every scenario - hook process exit code, decision envelope JSON, a simulated per-host interpretation (Claude's `hookSpecificOutput.permissionDecision`, Cursor's `permission` key, Grok/Gemini's `decision` key with Grok's own documented fail-open-on-unrecognized-exit behavior, Codex's exit-code-only reading since its JSON contract remains unverified), and a real filesystem/git side effect that requires POSITIVE evidence either way (an allow verdict needs the state to have changed exactly as expected; a deny/ask verdict needs it to match its own recorded baseline - never inferred from silence). `tests/e2e/test_host_e2e.py` runs on every CI/local pass with no live host binary present (27 scenarios: read-only fast path, normal/in-scope/out-of-scope edits, force-push across every host dialect with an independent CX-4 git-backstop confirmation, hard reset, recursive delete (in-tree and external), a database drop against a real sqlite file, an orchestrated `functions.exec`-wrapped Codex force-push, staged-capability consume-once/expired/replayed, a disabled-hook negative control, a tampered-hook-file DEGRADED path exercised against a private file copy (never the real checked-out hook), malformed input/output handling that fails closed, and a CX-5-semantics timeout simulation). `tests/e2e/test_codex_e2e.py` is the operator-run live-host layer (`GODMODE_E2E_CODEX=1`/`GODMODE_E2E_GROK=1`), skipping cleanly with an honest, specific reason otherwise. `tests/e2e/perf_measure.py` + `scripts/dev/measure_e2e_baseline.py` publish median-and-p95 per stage (startup, normalization, fast classify, identity resolution, archive access, decision round trip) into the checked-in `tests/e2e/perf_baseline.json`; `tests/e2e/test_perf_baseline.py` re-measures every run and fails a stage that regresses more than 20% (in-process stages) or 100% (the two subprocess-spawning stages, widened from the plan's own 20% after measuring genuine OS process-creation variance on this development machine that a tighter ceiling could not distinguish from a real regression) against that baseline; the guard only reads the file, never writes it. `tests/e2e/test_release_gate.py` fails the moment any host row in `README.md`/`docs/CAPABILITY-COVERAGE.md` claims `HARD`/"enforced" without matching e2e scenario coverage and a passing negative control - true today by construction, since no host row currently makes that claim. `docs/CAPABILITY-COVERAGE.md` gained an honest `partial` row for host pre-tool interception; `docs/LISTING.md` gained a Codex-submission-kit addendum mapping OpenAI's own "five positive + three negative test cases" portal requirement onto named, runnable scenarios in this suite.
- Godmode shipped generic frames and let this project's real rules live in hand-maintained files beside them. `godmode governance show` proposes rules from the record instead: a refusal category with enough distinct operations behind it becomes a candidate to declare that category protected, and an obligation restated across sessions without being discharged becomes a candidate to promote it to a charter rule. Every candidate carries the records supporting it, how many there are and the window they span, so a reviewer can go read the evidence rather than trust a count. Run against this project's own archive it proposes nine candidates, among them `interpreter-opaque-inline` on 50 distinct refused operations - the security batch's own signature, argued back from the record rather than asserted. Three guardrails hold structurally rather than by convention. Nothing is installed: reading the review surface is a pure fold that does not write at all, because a review surface that writes has become the enforcement surface, and `godmode governance promote` is what records an adoption - it needs a person, a candidate id and a reason, and refuses an id that is not currently proposed so a typo cannot adopt a rule nobody reviewed. Every candidate tightens: the synthesizer can only emit rules that declare something protected or required, so relaxing remains a manual, chronicled operator act rather than something a threshold can arrive at on its own. And frequency is never presented as a verdict - each candidate states plainly that it rests on what happened rather than on what is right, because approval fatigue is evidence of tolerance and a habit that repeated often enough to clear a threshold may still be a bad one. Candidate ids are derived from class and subject rather than from a counter, so an id read out of yesterday's report promotes the same rule today; a promoted candidate stops being proposed, since asking a reviewer the same question forever is how a review surface teaches people to skim it.
- Every host adapter already lifted the host's own sandbox and approval metadata onto the event it built, and that field's own comment said it existed so a chronicle record or a later audit could see what the host claimed about its own approval state alongside what godmode independently decided. Nothing ever wrote it, so the evidence was collected and dropped on every call. `godmode approvals` now reports what each host approved beside what godmode decided, and names the rows where the two differ in both directions. The two boundaries stay separate, which is the point rather than a caveat: a host's approval is the host's, godmode's decision is godmode's, nothing here reads one to decide the other, and the report says so in its own payload instead of leaving a reader to infer it. What the pair buys is an account a person can audit. A host that approved what godmode refused says godmode is covering ground the host does not; a host that refused what godmode allowed says the reverse, and that godmode's cover is the narrower of the two somewhere. Recording is deliberately sparse - only calls where the host actually carried approval metadata produce a row, because a row per call would bury the ones that say something - and it happens after observe mode is applied, so the decision recorded is the one that took effect rather than the one that would have. The operation is stored as a digest and never as text, since an operation is exactly where a pasted credential turns up and these records travel. Like the fleet and governance layers this owns no record kind, folding `decision` records under a `host-approval:` subject so the closed enumeration stays closed. A host verdict that its metadata does not state is counted as unstated rather than read as a refusal, because collapsing absence into "no" would manufacture disagreements that never happened.
- Sprint 9's second half: the headline is the record, and the gate is one consumer of it. The one-line description on every manifest, the listing kit, `llms.txt` and the README now reads *"A local, tamper-evident record of what a coding agent did, what it claimed, and what was verified."* Each clause names a shipped mechanism with a test behind it - the archive's hash chain and tamper-evidence tests, the action and refusal records at the pre-tool boundary with the host's own approvals beside them, claim records downgraded when citations fail to resolve, verdict and attestation records - and the sentence carries no comparison, no number and no causal verb. `packaging/hosts.json` stays the one authority; the manifests were regenerated from it by `godmode bindings --write` and `--check` reports no drift. README's *What it does* opens with Verdicts and Register and places the gate after them, with its paragraph opening by naming itself a consumer of the record. Nothing in the gate changed; only where it stands in the description.

### Fixed

- A cache miss in `resolve_anchor` cost six git spawns, seven with a second remote, and every one of them carried a five-second timeout. Six times five is thirty, which is exactly the budget the host gives the prompt hook before it kills it - so a slow git did not make a turn late, it made the hook's work vanish. A commit invalidates the cache, and this repository commits all day, so on the tree that needed it most the miss path was the ordinary path, not the tail. The cold path is now three spawns: the two `rev-parse` questions ask together, HEAD's commit and branch name come from one call, and every remote's address is read from `git config` at once instead of one `get-url` per remote. The tests count spawns rather than time them, so a fast machine cannot hide a regression. Two behaviours were checked against git rather than assumed: a detached HEAD abbreviates to the literal word `HEAD`, which is reported as no branch the way the empty output before it was, and an unborn HEAD fails the combined call, so that case keeps its own spawn for the branch name rather than losing it. The prompt hook itself is now declared asynchronous in the plugin manifest: it records the operator's ask and returns nothing, and a hook with nothing to say has no reason to make the turn wait for it.
- Fixed the console error-exit contract at the dispatcher, not per-command (field-found: three tools in one governed session reported failure in the body while exiting 0 - `inspect` returned PrivacyError, `checkpoint` returned ArchiveError, both "succeeded"). The one seam every registered subcommand shares now maps results to a documented exit vocabulary - 0 ok, 1 findings-red (ran and found problems), 2 error - and a payload carrying a truthy `error` verdict exits 2 even when its handler said 0, so a command that catches its own failure and reports it in the body can no longer read as success to the caller. A registry-driven sweep test forces an error through every registered subcommand and asserts nonzero, so commands added later inherit the contract without opting in. Baseline redaction (same field report): the privacy guard used to refuse the WHOLE inventory snapshot when one entry's path was secret-shaped, and since `inspect` had no redaction mechanism, no baseline could ever exist for such a project - drift detection permanently unavailable, a terminal state whose own refusal message named the remedy the tool did not implement. `collect_inventory` now does what that message says: a secret-shaped path persists as a redacted entry - {stable hash-derived key, length, extension class} plus the file's own size/sha256 - counted in a surfaced `redaction_count`, cleartext never written; `inventory_diff` keys on the stable redacted key, so drift detection works against the redacted baseline. An optional `baseline_exclude` glob list in `.godmode-privacy.json` (validated by `config check`) skips entries entirely, counted under `skipped.excluded` - tighten-only: an exclusion can narrow what persists, never widen what persists in clear. Scope-explicit status responses (field feedback 3, a scope-less `not-initialized` was read as global state and produced a confident wrong verdict): `doctor`, `config check`, `capabilities`, `hooks status`, `hooks probe`'s not-run answer, the git-backstop's advisory verdict, both `not-initialized` refusal messages, and the session hook's own `not-initialized`/`orphaned-archive` notices all name the resolved project root they are answering about, in JSON (`"project"`) and in prose.
- Pinned the two remaining recovered-corpus defect classes that were found already resolved on main, so neither can return silently: noun-verb tiering (a pure read of a release-named file - `grep ... docs/RELEASE-CHECKLIST.md`, `node -e` over `package.json` scripts - was tiered R4 `release-or-external-write` from the filename noun; the tier comes from the verb) and the sed-backref class (a replacement operand's `\1/'` was parsed as a redirect-target path, turning a grep/sed/sort pipeline into an R2 worktree mutation). Six corpus entries in both directions: the three recovered reads allow, while `npm publish`, an in-place `sed -i` on a shell profile, and the same backref pipeline with a real out-of-tree redirect all keep their ask. Each allow-pin was verified to fail against the v0.2.10 classifier - the deployed version that produced the recorded asks - before landing green on main. Separately, the refusal message no longer cuts its embedded operation and impact list mid-word: bounded text now breaks at the last whole word inside the limit and marks the cut with an ASCII `...` (ASCII on purpose - the reason string crosses a pipe whose two ends can disagree about encoding, and a U+2026 from a cp1252 child console read as utf-8 kills the reader thread).
- Fixed two of the highest-frequency gate friction classes from the recovered field-ask corpus (28 asked-about commands from real governed sessions, spec B4-9), both structural, neither loosening a protected surface. Temp-dir redirects: a redirected write whose target resolves under the system temp directory is a scratch write (R1 allow), not a worktree mutation - the declared-write path already knew this and the redirect path did not, so the operator's exact `sed -n ... > /tmp/blkA.txt` asked while the equivalent declared write was allowed. `/tmp` itself is now recognised on Windows (Git Bash spells the temp dir `/tmp`; `tempfile.gettempdir()` never returns it there), traversal collapses before the prefix compare (`/tmp/../etc/passwd` leaves the allowance), a sensitive-named target (`/tmp/id_rsa`) keeps its ask, an unrecognised head with a temp write keeps its ask, and a project checked out under /tmp keeps containment in charge. Literal-URL read-only fetches: a curl GET of a literal http(s) URL that sends nothing (no data/upload/auth/config/method flag), writes nothing (no output flag beyond a discarded one), and carries no unexpanded `$`/backtick is a read the approver can fully see - the URL is the entire outbound payload. Allowed standalone, and in a pipeline ONLY via a post-pass in `classify_action`'s aggregation where the consumers are visible: any stdin-executor head (`| sh`, `| bash`, `xargs`, a bare interpreter), any other protected segment, or any consumer the classifier merely defaulted to read keeps the ask, and a `$(curl ...)` substitution never qualifies (its output feeds the outer command line - the laundering pin). The one executor carve-out is `python -c`/`node -c` with a fully visible literal payload free of execution/IO surfaces, which consumes stdin as data - the recovered `curl | python -c "json.load(sys.stdin)"` shape. 16 new corpus entries pin both directions (the operator's exact commands allow; sends/credentials/uploads/variables/output-writes/executors/launders all still ask); two pre-existing `by-design: ask` corpus entries whose only protection was a temp-dir redirect are relabelled `allow` under the new design, each still protected on every other axis it carries.
- Two long-standing red marks cleared, both by fixing the thing rather than the measurement. The charter compiled one rule per physical line, so a directive wrapped by an editor arrived as several fragments - "Protected operations receive a preview and require a scoped, expiring, one-use local" and "capability. Godmode never executes the operation itself." were one sentence torn in half, and both halves compiled as separate rules. The inflated count mattered less than what it did to enforcement: half a sentence states no complete obligation, so it can be neither checked nor reviewed, and nineteen of twenty-four rules sat dormant. Wrapped lines now join, with a new bullet, a blank line, a heading or a fence ending a directive. Joining alone was not enough, because it cannot invent a boundary the prose does not have: the operator profile stated four standing directives inside one wrapped sentence, which merged into a single rule containing the word "never" and therefore classified HARD, promoting descriptive prose to an attestable obligation. That paragraph is now five bullets, one directive each. The result is fifteen rules where there were twenty-four, every one a whole sentence, with the five existing HARD ids byte-identical so the attestations proving them stay anchored; one new HARD rule appears, the capability-register pointer invariant, which was previously a fragment. All nine advisory rules were reviewed with a stated reason for why no mechanical check can decide them - two are section headings that ask nothing, one is a product description, and the rest turn on a judgement a runtime cannot make, such as whether a future dependency counts as depended on at runtime, or whether a push was the operator's call rather than an agent's inference. The silent-failure ratchet was red because `godmode_sentinel.py` held two handlers that discarded a failure against a baseline of one. Both are genuinely best-effort - tightening a private temp file's permission bits, and chronicling an observe-mode transition that must not turn a policy read into a hard failure - so neither should raise. They now record what they continued past instead of discarding it, which is the scanner's own remedy for an empty handler: "we decided to continue" and "nothing went wrong" are different facts, and a bare `pass` renders them identically. Behaviour is unchanged; the count is zero against a baseline of one, and the ratchet reports no regression.
- The reason godmode's gate never ran under Codex or Grok is that neither host loads hooks from any plugin at all, which took instrumenting Grok's own runtime to see rather than inferring from manifests. Its debug log discovers eight installed plugins carrying hook files, godmode among them and the rest unrelated third-party plugins, and then reports discovery complete with zero hooks loaded and zero errors, for all of them. Codex reports the same thing from the other side: its hooks panel shows zero installed for every event, and its plugin detail says no plugin hooks while listing all six godmode skills. Four earlier attempts to fix this by changing godmode's manifests - single-string commands, a Codex-owned hooks file, a project-level copy, and snake_case event names - each failed for the same reason, which is that nothing about godmode's declaration was the cause. What does work on this machine is project-level hook config: a non-godmode hook declared in a project's own Codex hooks file is registered, trusted and enabled today. A Codex adapter now ships that exact shape as a template, with the two details that differ from the plugin manifest called out - the command must be a single string rather than a command plus an args array, and the event key is CamelCase in the file even though the trust table records it in snake_case. The template is labelled as unproven for godmode specifically, because the trust approval it requires has not been completed here, and no host claim rests on it.
- Fixed both findings from the CX batch's final whole-branch review, the release gate for v0.3.0. **F1 (Important):** `.godmode-authorization-policy.json` - the file that switches gate enforcement into observe mode (every deny/ask becomes an advisory allow) - was missing from the sensitive-path classifier. A single governed `Write`/`Edit` tool call targeting it used to classify as an ordinary `worktree-file-mutation`: allowed silently, exit 0, unchronicled, after which `_policy()` read `gate_mode: "observe"` fresh on every subsequent call and every R5 op converted to an advisory allow. It is now named in `_SENSITIVE_EDIT` (`godmode_sentinel.py`), so a governed tool-call write to it asks/denies the same as `.git/`/`.env` - the operator declaring observe mode from their own editor or terminal, outside a governed session, is untouched; that stays the intended path, and `apply_profile`'s/`init`'s own direct filesystem writes never went through the gate at all. Separately, `CapabilityBroker._policy()` now chronicles the observe-mode ENTRY/EXIT transition (`observe-mode-entered`/`observe-mode-exited`, kind `action`, counts-only) the moment either is next observed by a live policy read - an out-of-band edit to the file now leaves a durable, hash-chained trace before it is ever honored by a decision, not only a per-call `OBSERVE MODE` advisory afterwards. README and `docs/CAPABILITY-COVERAGE.md` now state plainly that the declaration file is itself a protected surface for governed sessions. **F2 (Minor):** README's host table grouped Cursor and Gemini CLI with OpenCode under a flat `UNAVAILABLE`, reasoning that "none exposes a pre-tool boundary the adapter can call into" - stale since CX-3 shipped real pre-tool hook manifests for both (`.cursor-plugin/hooks.json`, `.gemini-plugin/hooks-fragment.json`), against which `_auto_registration_grade` genuinely returns `"partial"`. The row is split: OpenCode alone (still `UNAVAILABLE`, no shipped manifest), Cursor and Gemini CLI together (`PARTIAL`-when-declared via `GODMODE_HOST`, `UNAVAILABLE` by default, wiring unproven - Cursor's `${PLUGIN_ROOT}` resolution is a best-effort guess and Gemini ships a fragment only).
- Fixed two Critical review findings in CX-5's five-level interception scale. A hand-crafted chronicle record (no live hook subprocess required, only `archive.append` access) could grade permanent `HARD` by carrying `expiry` alone while omitting `hook_version`/`trusted_hook_hash`/`nonce_hash`/`observed_decision` - each of the drift checks correctly treated its own missing field as "cannot compare," but nothing required all five fields together, so an incomplete record dodged every check by omission. `interception_state` now requires ALL FIVE HARD-eligible fields present (`_fully_enriched`) before a record is even considered enriched; missing any one caps it at `PARTIAL`, uniformly, exactly like a pre-CX-5 minimal record - `record_interception_proof` itself now always populates all five on an honest write (`hook_script` defaults to the shipped session hook file rather than staying unset, so `trusted_hook_hash` is no longer merely "when a caller remembered"). A second, independent gap let a record claim an implausible `expiry` (the reviewer's exact repro: `9999-12-31T23:59:59+00:00`) with no sanity bound anywhere in the stack; a new `PROOF_MAX_TTL_SECONDS` ceiling (24 hours, matching the existing default TTL) is now enforced at two layers - `KIND_INVARIANTS` refuses to archive such a record outright, and `interception_state` independently re-checks the same ceiling at grading time, so a record that somehow reached disk anyway still cannot grade above `DEGRADED` (`degraded_reason: "expiry-out-of-bounds"`). Also fixed: `_auto_registration_grade`'s exception path used to answer `"soft"` on a verifier failure (an unreadable/missing `packaging/hosts.json`) - the BETTER of the two possibilities a failed read could mean, a direct violation of the module's own doctrine line; it now answers `"none"` (UNAVAILABLE), the worse one, while the deliberate "read succeeded, host genuinely not wired" case still answers `"soft"` as before. `host_acknowledgement` is now actually computed (`True`/`False`/`None` from the same CX-3 registration evidence `hooks status` already reads) rather than a permanently-`None` placeholder the docstring claimed but never wired - confirmed, directly, never to feed grading either way. The subagent-actor structural pin (capability digest, contract point 5) now covers every `CapabilityBroker.consume`/`.consume_staged` call site in the tracked source tree, not only the session hook. `DogfoodingTests` (`tests/test_capability_register.py`, pre-existing, untouched by CX-5's own diff) gained a class-level `setUp`/`tearDown` byte-snapshot restore as a second, independent safety net alongside `plant_and_observe`'s existing per-call `try/finally` - stated honestly as covering only in-process failures, not an external process kill, which no in-process mechanism can address.
- The recovered field-ask corpus (28 asked-about commands from real governed sessions, spec B4-9) is now formalized as regression fixtures: 20 sanitized entries pin the resolved friction classes in both directions - read-only loops and `probe(){}` definitions, process-substitution diffs, curl status probes and literal-URL fetches, curl-to-interpreter stdin parses, in-tree redirected and heredoc appends, home-config reads - as allows, while the asks the operator judged defensible (`.git/info/exclude` append, `git stash push`, `git checkout --`) stay pinned as asks. Formalizing them surfaced one regression the read-by-default fallback for unknown heads had silently introduced: `claude plugin marketplace add`, whose original ask the operator had judged CORRECT (it registers a new plugin source - from then on everything that marketplace serves is code the agent will offer to run), had become an allow. It now classifies as `agent-trust-mutation` (R3, ask) by name, while `claude plugin marketplace list` and `claude plugin install` - judged pure friction - stay reads. Decision table regenerated; the fast gate escalates the new category to the full hook exactly as parity requires.
- The gate refuses when the authorization policy file cannot be read, deliberately, because silently ignoring an unreadable declaration would silently drop the protections it was written to add. That is right for a corrupt or permission-denied file and wrong for a file that is merely mid-rename: on Windows a read against one answers with a sharing violation, which arrives as `PermissionError` and therefore as an `OSError`, so the refusal fired for a file that was intact and readable a millisecond later. The failure showed up three times in a single session as a `PreToolUse` hook error carrying no stderr at all - the suite parks the operator's observe-mode declaration while hook subprocess tests run, and any live gate call landing inside that window got a hard error instead of a decision. A read that fails with an `OSError` is now retried three times across roughly 120 milliseconds, short enough to stay invisible in front of every gated tool call and bounded enough that a genuinely unreadable file does not become a long stall on the way to the same answer. Malformed JSON is not retried, since it is not transient and retrying only delays an identical refusal. A read that keeps failing still refuses, an absent file still reads as no policy and chronicles the observe exit exactly as before, so the guarantee is unchanged and only the false positive is gone.
- A published claim is withdrawn: `godmode hooks probe` reaching HARD was read as evidence that a host's runtime calls this plugin, and it is not. The probe self-injects into the hook script, and its own function docstring says so - it does not prove a live host is wired to call that script on real tool calls. The host support table and the interception coverage row both carried that misreading for Codex and Grok. What actually establishes wiring is direct and simple: run a protected command inside the host's own session and see whether a record lands in the archive. Measured that way, Claude Code is wired - a protected command writes a refusal record and the submitted prompt writes a request record, both observable - while Codex and Grok are not, writing nothing for the same class of command, and Codex's own hooks panel reports zero installed hooks for every event. Both surfaces now say that, name the probe's limitation so the mistake is not repeatable, and withhold a wiring claim for all four non-Claude hosts. Nothing about the mechanism changed; several claims about it did.
- The orphan report was mostly wrong, and wrong in the direction that teaches people to ignore a report. Call edges were only recorded when the called name was defined in the same file; `from x import y` was handled separately, but a method reached through an instance - `archive.reanchor()` in another module - is never imported by name and so linked to nothing. Every public method not also called inside its own file therefore read as unreached, and a property, which is read rather than called, could never be reached by a call edge at all. Sampling nine symbols from the report found seven that were live code, among them `reanchor`, which the CLI invokes through `db --reanchor`. A call or a read through an instance now records the attribute's name under its own relation, kept out of `calls` deliberately so an unresolved guess cannot enter a blast radius, where it would read as a real dependency; only the orphan query consults it. Matching by name alone can mark a same-named method elsewhere as reached, so some genuinely dead code goes unreported - the trade runs that way on purpose, because a false negative costs a missed cleanup while a false positive costs someone deleting live code, or learning to skip the report. The count fell from 29 to 6, and every one of the 6 was then checked by hand to have no call site anywhere in the tree. Five were thin wrappers nothing had ever called: `Atlas.by_path`, `charter.rules_for`, `sentinel.substituted_commands`, and the `command_timeline`/`mutation_turns` pair that `session_timeline` superseded by returning both halves from one scan. `substituted_commands` described itself as kept "for any caller that only needs the extracted commands", a caller that never arrived. All five are removed, each leaving a note where it stood. `register_kind_invariant` stays: its own comment states it remains available as an extension point, which is a decision rather than an oversight, and it is now the single entry the report carries.
- The interception probe now states, in its own result, what it establishes and what it does not. Its self-injection limit was documented in the function's docstring from the beginning, and that was not enough: a reader who had opened that file still published the probe's HARD verdict as evidence that two hosts' gates were live, and they were not - measured afterwards by running a protected command inside each host and finding no record, after which the claim was withdrawn. A caveat only reaches the person who quotes a number if it travels with the number, so the result now carries three fields: what the probe proves (the hook script recognises, denies and records - the mechanism works when invoked), what it does not (that the host's runtime actually calls the hook on real tool calls), and the test that would settle it (run a protected command inside the host's own session and confirm a refusal record lands, because a read-only command records nothing either way and proves nothing in either direction). All three are present on every outcome, including failures, since a failed probe is exactly when someone reaches for a reason to discount the result. Separately, the evidence-pipe advisory that already existed - which flags a verdict-bearing command piped into a truncating filter, where the exit status becomes the filter's - is now pinned against the exact command strings from a real incident where a red suite was reported green, along with the corrected form it recommends, so the detector cannot stop covering the case that proved it matters.
- The request ledger went unreviewed across 34 handovers, and the reason turned out to be arithmetic rather than neglect: 28 of its 44 open entries were not requests. A prompt cannot be reconstructed from anywhere else once the turn has passed, so every one of them is recorded - but a host delivers more than typed asks through that door, and a tool-permission prompt, a task-completion notification and a subagent's queued command all arrive prompt-shaped. Of 44 entries reported open on this archive, five were latency probes, one a `<task-notification>` envelope, one a `Hook PreToolUse:Bash requires confirmation` prompt, four were raw shell command bodies and one a rule of box-drawing characters. A ledger whose count is mostly noise is a ledger nobody reads. A shared predicate now decides whether a prompt is a person asking for something, and it is applied on read as well as on write - a write-time filter alone would have left every envelope already stored in the open count forever, which is exactly the state that made the ledger unreviewable. The patterns are narrow and shape-based because dropping a real ask costs far more than carrying a stray line: each one matches a host envelope no person types, and a prompt that merely mentions a tool - "can you run the bash command that rebuilds the gate table?" - is untouched. One pattern had to match the archive as it actually is rather than as it should be, since the attribution separator is stored mojibaked, as the UTF-8 bytes of a middle dot read back as two characters, so a literal never matched the records it was written for. Closing the answered entries then exposed a second defect. A closure written by a person carries the subject they can see, never the full-text digest they cannot, and the subject is truncated while the digest is taken from the whole flattened prompt - so for any prompt longer than the truncation limit the two could never be equal and the closure landed without closing anything. That is the same shape the module's own docstring describes for the digest-only matching that came before it, one truncation further along; closures now match on either. The ledger reads 16 open against 16 closed, from 44 open against none.
- Fixed SEC-A, the four fail-open defects an external audit found (2026-08-17), release-blocking for v0.3.0, across four rounds - three independent security reviews each found the previous round's fix insufficient, and every repro from all three is now a test (`tests/test_c1_round2_interpreter_locating.py`, `tests/test_c1_round3_exec_shape.py`, `tests/test_c1_round4_argv_tokens.py`). **C1 (critical, universal bypass):** an interpreter handed a whole program as one opaque `-c`/`-e`/`--eval`/`-Command` string, or fed one via a heredoc, classified as `local-compute-or-state` (R1, unprotected) on the interpreter's bare, literal-first-token name alone - `python -c "<writes .godmode-authorization-policy.json gate_mode=observe>"` and `python -c "subprocess.run(['git','push','--force', ...])"` both walked around every gate. Round 1 protected that literal shape at floor R2 (`interpreter-opaque-inline`), with a coarse evidence scan for a forced push, a history rewrite, a schema drop or a policy-file write raising the tier to R5. **Round 1 did not close the bypass:** the same payload walked through under a path prefix (`/usr/bin/python -c "…"`), a wrapper command, a quoted or backslash-escaped head, a fused shell flag (`bash -lc`), PowerShell's `-EncodedCommand`, node's `-p`/`--print`/`-pe`, deno's `eval` subcommand, a piped/herestring/stdin-redirected payload, or a paren-bearing `$(...)` substitution the extractor could not span. Round 2 closed those seven classes. **Round 2 did not close it either:** its inline-flag patterns required whitespace between the flag and its argument, which the shell does not leave there, and it located the interpreter with a table of wrapper commands carrying a hand-written copy of each wrapper's own flag grammar, so `python -c"import os"`, `bash -c'rm -rf /'`, `sudo -E python -c "…"`, `env -u VAR python -c "…"`, `xargs -I {} python -c "…"`, `$(which python) -c "…"`, `docker exec -it c python -c "…"`, `chroot / python -c "…"` and `su -c "…"` all landed R0/R1. Round 3 deleted that wrapper table - the classifier knows the name and flag grammar of zero wrapper commands - and replaced it with a token scan and three evidence forms, which closed all nine of those and eleven more shapes nobody had enumerated (`fish -c`, `ash -c`, `csh -c`, `nu -c`, `elvish -c`, `busybox ash -c`, `kubectl exec pod -- sh -c`, `docker run --entrypoint sh img -c`, `wsl python3 -c`, a paren group, a brace group). **Round 3 did not close it either, and the reason was one thing:** it still matched flags with regexes searched over RAW SEGMENT TEXT anchored `(?:^|\s)-`. It deleted the anchor on the right of the flag and left the one on the left, so a quote character - which the shell removes before `execve` - walked straight through everything above (`python "-c" "<payload>"` and `bash "-c" "git push --force"` were R1, `sudo -E python "-c" "…"` was R0, `p"y"thon -cimport os` was R0; the reviewer executed all four in a real shell to confirm the payload runs). Round 3 also inherited, from before all three rounds, a `read-only-inspection` return that fired whenever ` --help`, ` --version` or ` --usage` appeared ANYWHERE on the line, above every check that can find code: `python -c "<payload>" --version` was R0 and the payload ran, and so were `git push --force origin main --help`, `git reset --hard HEAD~5 --help` and `rm -rf / --help`. **Round 4 makes four changes.** (1) The segment is tokenized with `shlex` (standard library, no runtime dependency) and every interpreter-name resolution, inline-flag test and exec-shape evidence form now reads those ARGV TOKENS rather than raw text - so `"-c"`, `'-c'`, `"-"c`, `""-c`, `p"y"thon`, `p'y'thon`, `pyth\on` and `n"o"de -e"…"` are read the way the shell hands them to the process, and a line whose quoting cannot be parsed fails closed instead of falling through. Escape handling is off on the first pass and on only as a fallback, which is what keeps `C:\Python\python.exe -c "…"` a path rather than collapsing it to one word. (2) A help or version request must be the FIRST OPTION on the line - a subcommand or a script may precede it, another flag may not - and the interpreter check, the exec-shape scan and the opaque-body heads all run BEFORE that fast-path rather than after it. The flags that make a trailing `--help` a lie are the ones that consume the rest of the line: CPython stops option parsing at `-c` and hands `--version` to the payload as `argv`. (3) An interpreter stops reading its own options at its first operand, and the flag scan stops there too, because everything after that operand belongs to the script - `python app.py -c foo` passes `-c foo` to `app.py` and runs no inline code. This is what makes `node server.js -port 3000`, `python train.py -ckpt m.pt`, `python app.py -config conf.yml` and nine more everyday commands unprotected again after round 3's prefix widening blocked them, without needing any interpreter's list of argument-taking options: a non-flag token is an operand unless it names a file or sits immediately behind a flag, so `python -X utf8 -c "…"` and `python -W ignore -c "…"` are still read. (4) Four exec surfaces this project's own platform makes ordinary are now read: `cmd /c "…"`/`cmd /k "…"` (Windows spells the flag with a forward slash, which no `-`-anchored rule could reach), `Invoke-Expression`/`iex`/`Invoke-Command` (PowerShell's `eval`, beside `ForEach-Object` which was already named), a PowerShell read cmdlet handed a `{ … }` scriptblock (`Measure-Command { python -c "…" }` was shielded by the read allowlist exactly as `env` was before round 3), and `builtin eval`/`command eval`/`trap`. Also in round 4: `-E` is ruby's external-encoding flag rather than an eval flag, so ruby matches only lowercase `-e` while perl keeps both; form (c) reads `--command=` as well as `--command`, and requires its argument to be a command line (whitespace or a shell metacharacter) rather than merely quoted, which is what makes `tar -c "a.tar"` and `docker -c "ctx" ps` unprotected; a PowerShell parameter LONGER than the enumerated name is read (`-CommandWithArgs` is a shipped 7.4 parameter that runs a command, and round 3's prefix test only ran one direction); a substitution glued to the front of a command name is read as unknowable (`$(echo p)ython`), while `$(npm bin)/eslint` is not, because a file is still named after the substitution ends; the interpreter-basename set and the per-family flag grammars are derived from ONE table rather than being two parallel enumerations that round 3 had to edit in both places; and `env` is recognised as a command name again for the purpose of judging its redirect, so `env > out.txt` is an ordinary contained write rather than an ask. `-m <module>` remains excluded from the opaque bucket - an installed, importable artifact, the same shape as a script file - so `python -m unittest`/`-m pytest`/`-m cProfile` stay R1/allow; running a SCRIPT FILE (`python app.py`, `node build.mjs`) is untouched. **The escalation is narrow and is not a fail-closed default for unknown commands:** `foobar --version` is still R0, and so are `env`, `env ls -la`, `chroot / ls`, `tar -cf a.tar dir`, `docker run -e "K=V" img`, `kubectl logs pod -c app`, `cmd`, `Measure-Command { Get-ChildItem }` and `echo python -c "hi"` - `echo` prints an invocation and runs nothing, which is why a data-printing read still shields its own arguments. Asking a command to explain itself stays unprotected too: `git push --help`, `python --version`, `docker compose up --help` and `python scripts/godmode.py release --help`. **Residual surface, disclosed rather than implied closed:** an interpreter whose name is not on the basename table and whose inline flag is not `-c`/`--command` executes silently and is not read at all - `Rscript -e`, `R -e`, `php -r`, `lua -e` and `osascript -e` are arbitrary code execution this classifier does not see, and that table is the one enumeration still deciding the answer; `-e` is deliberately not evidence on an unresolved head, because `docker run -e "NODE_ENV=production"` is an everyday command, so `npx tsx -e "…"` is not caught; a single bare word after `-c` on an unresolved head is indistinguishable from a filename, so `su -cwhoami` is not caught; a whole command line inside one quoted argument is data to this classifier, so `mytool "python -c 1"` and `env -S "python -c 'print(1)'"` are not caught; `awk`/`sed`/`sort --compress-program` program text is never parsed, so an interpreter invoked from inside one executes silently; `source ./x.sh` and `. ./x.sh` run a script file and are left open deliberately, because asking about `source venv/bin/activate` would cost more friction than the hole is worth; an encoded or obfuscated payload is never decoded, so the evidence scan cannot fire on one and every encoded-command shape sits at the R2 floor rather than escalating; evidence split ACROSS segments (`echo 'git push --force' | python`) asks at that R2 floor without escalating, because each segment is classified independently; a command name arriving through a variable set in an EARLIER tool call is outside what a per-call classifier can see; an option VALUE that looks like a file ends the operand scan, so an `-e` behind one (`node -r ./setup.js -e "…"`, `ruby -I lib.d -e "…"`) is not read - a `-c` in the same position still is, by form (c) - and closing it was measured to cost `python -u app.py -c conf.yml`, so it is disclosed instead; the help excuse still applies when no OTHER flag precedes the help flag, so a protected command whose dangerous form needs no flag at all is still excused (`rm / --help`, `git push origin main --help`, `./deploy.sh --help`) - every instance checked is safe because the real tool prints help and performs nothing, but a tool that ignored an unknown trailing `--help` and acted anyway would be reached through it; and `chmod`/`chown` are not classified mutations in this module at all, with or without a help flag. Regenerated `hooks/gate_table.json` (every table entry is byte-identical; only the source hash moved). This round removes one duplicated enumeration and adds one name (`cmd`) to the interpreter table; that table, the executable-suffix list, the PowerShell parameter names and the opaque-body heads remain enumerations, and the classifier file is longer, not shorter, than it was before this round. The 142-command regression corpus keeps all 17 of its round-1/round-2 `allow`->`ask` relabels and needs no new one: round 4 changes no corpus entry's allow/ask/refuse label, and no corpus entry's protected verdict or tier.
  - Fixed H2: `godmode_githooks._staged_paths` converted a nonzero `git diff --cached --name-only` into `[]`, which `_evaluate_pre_commit` read as "no staged changes" - allow, exit 0, every pinned-file check and capability consumption skipped, on a commit this hook never actually inspected (a CX-4 defect the project's own review missed). A failed inspection is no longer folded into an empty result: under declared `git_backstop` policy it fails closed (`inspection-failed`, block, chronicled counts-only); without the policy it stays advisory-only, matching the existing malformed-stdin pattern - never a silent exit 0.
  - Fixed H3: a malformed or unreadable `.godmode-authorization-policy.json` raised in the sentinel and was caught in the session hook's pre-action path and silently replaced with `{}`, dropping an operator's `approval_required`/`password_required` widening without a trace - the exact operation they protected reverted to whatever `classify_action`'s unwidened baseline said (the audit's repro: R1, allowed). The lost widening cannot be recovered, so this now fails closed the only honest way available: the policy being unreadable is itself surfaced as a reason to ask, on every call the full gate reaches, until the file is fixed - never applied when the baseline already asked/refused on its own.
  - Fixed M7: the session hook's outer error handler branched on the SUBMITTED PAYLOAD's own claimed `hook_event_name` (`claude_session`) rather than argv (`args.event`, the host's own invocation, unforgeable by the payload) - a payload that claimed `hook_event_name: "SessionStart"` while argv said `pre-action` took the session-start success branch (a friendly `systemMessage`, exit 0) on any error raised mid-evaluation, silently allowing the tool call argv said this really was. argv now decides which branch handles the error first; a pre-action error renders a deny-shaped decision body and exits 2, never the session-start success path.
  - Fixed M6 (same pass, cheap alongside H2): `godmode_githooks.git_hooks_install` reported `declared: True` with nothing to contradict it when the git hooks directory could not be resolved (`git rev-parse --git-path hooks` failed) or when writing a hook succeeded but making it executable raised `OSError` and was swallowed - both read by the CLI's `exit_code=0 if report["declared"] else 1` as success. The function now names its own real outcome in an explicit `ok` field (false on either failure, with `chmod_failed` naming which hooks were written-but-not-executable), and the CLI reads that field directly.
- Fixed the Codex `apply_patch` shape the previous fix could not read: an argv **array** body — `{"command": ["apply_patch", "*** Begin Patch..."]}` — which is the shape Codex 0.147.0's own embedded prompt documents, and which still parsed no body and was refused as `unrecognized-tool` after the string-body fix. The adapter no longer picks a single winning body field at all: every non-empty string candidate across `command`/`input`/`patch`/`content` — including the string elements of a list-valued field — is collected, the whole call fails closed if **any** candidate carries a malformed directive, and the targets of all candidates are unioned before the scope fence runs. Unioning is monotone in the fail-closed direction (it can only widen what the fence sees and add malformed detections), so whichever body the host actually executes, its targets are always a subset of what was inspected — and the old precedence rule's mirror-image blind spot, a malformed directive sitting in the field that *lost* the precedence race and was therefore never inspected, is closed by the same change. Non-string, non-list values are never read; a call with no readable body anywhere still fails closed rather than guessing at an undocumented shape.
- Fixed the Codex `apply_patch` body field: a call whose patch body arrives under the field name `command` is now read. `_PATCH_BODY_FIELDS` in `scripts/godmode_runtime/godmode_hostevent.py` listed `input`/`patch`/`content` only, so a `command`-bodied call parsed an EMPTY patch body - no target reached the scope fence, no line of the body reached the malformed-directive detector, and the call came out as `unrecognized-tool` (refused, but for the wrong reason and at the wrong place: an ordinary in-scope Codex edit was refused as an unmapped tool). Every add/update/delete/rename target a `command`-bodied patch names now reaches the same scope fence the `input`-bodied path already reached, proven end-to-end through the real hook subprocess in both directions - an out-of-fence target is denied with the fence's own reason, an in-fence target is allowed - and a structurally-malformed `command` body still fails the WHOLE call closed rather than proceeding on whichever directive happened to parse. `command` was initially tried FIRST, ahead of `input`/`patch`/`content`, and the argv-array form Codex actually documents was skipped; the follow-up fix in this same release replaces that precedence with a union over every readable body candidate, so see its entry for the field-reading rule that actually ships.
- Four facts this runtime declared in more than one place, resolved two different ways depending on what the duplication actually was. Where two copies held the same data, one owner replaces them. The list of tools that read and cannot write sat as separate literals in the gate hook and in the Claude adapter, holding the same six names by coincidence: add a tool to one and the gate charges a read the full check, or the adapter reports a mutation as a read, and a disagreement about what can mutate is not the kind of drift worth discovering from behaviour. The directories a walk skips sat in `godmode_constants` for the atlas, the database inventory and the scope fence, and separately in the structure index, and those two had drifted in both directions - the index walked into `coverage`, `target`, `.research`, `.evidence` and `.decisions`, while every other walker descended into `.tox`, `.mypy_cache` and `.pytest_cache`. Both now read one definition, the union, since every entry on either list was put there for a reason and no reason to walk a build directory or a type-checker cache has appeared since. The disposition register's states and evidence prefixes were the interesting case: they were duplicated deliberately, because `godmode_invariants` stays free of runtime imports so the chronicle can import it, while `godmode_register` imports the chronicle - so a direct import would close the cycle that dependency-freedom exists to prevent, and a test asserted the two copies still agreed. Moving the definition into `godmode_constants`, which has no runtime imports at all, lets both sides read it and makes the drift unrepresentable rather than merely detected. Where the duplication was a shared vocabulary rather than shared data, a guard replaces a merge. The nine role names are declared three times - once mapped to the files that fill a role, once to a relevance weight, once to the sentence the CLI prints - and merging file globs, a float and a sentence into one structure would buy nothing; the keysets are now pinned to each other instead, so a tenth role cannot bind documents while scoring at a fallback weight and printing no purpose. The five host names are likewise declared three times, mapped to an event adapter, to a manifest path with its event key and latency budget, and to eligibility for a SOFT interception grade. That vocabulary drifting has already cost something: the comment above the Codex manifest entry records it naming an event Codex cannot fire, which made the proof answer "budget unknown" rather than fail. Both guards were watched failing against a planted tenth role and a planted sixth host before being kept.
- Grok loads its hooks from the shared `hooks/hooks.json`, not from `.grok-plugin/hooks.json`, and an earlier reading of the evidence had that backwards. The mistake was a coincidence: both files carried five entries at the time the operator's plugin panel reported "5 hooks", so the count matched either one. Removing two invented Codex event names from the shared file dropped it to three entries, the panel immediately reported "3 hooks", and the ambiguity resolved - which is also what the Grok marketplace specification says plainly, that hooks live in `hooks/hooks.json`. Two consequences follow and are recorded rather than assumed away: the Grok-specific manifest's `PreCompact` and `SessionEnd` registrations do not reach Grok, and its single-string command form is not the shape Grok actually executes. Neither costs enforcement today - Grok sends Claude's tool names, which the shared matcher covers, and a probe run from inside a real Grok session still records an interception proof and reads HARD after the change - but the Grok-only manifest should not be described as the file Grok loads.
- The first full suite over the ten new capabilities found eleven failures from six causes, every one a rule this repository already enforced and the new code had not yet met. The SARIF document carried a `$schema` URL, and the runtime is scanned for remote literals - the key is gone; viewers key on `version`. The examples corpus imported the console that imports it, lazily, and the atlas reads imports statically - the console's `main` is now handed in as the runner. `skill validate` refused the two hand-written skills that ship with the plugin because they predate fixtures - a skill with no `fixtures/` directory now reports `fixture_hosts: 0` honestly, while a forged skill whose directory exists and is incomplete is still refused. The forge golden tree gained its five fixtures. The release checklist's new claim-scan directive compiled to a seventh HARD charter rule, and a HARD rule must own a plant: it now does, breaking the scan's verdict and watching `tests.test_claim_scan` go red. Both eval snapshots were rewritten for the new rule and the re-ranked checklist.

## [0.2.13] - 2026-08-16

### Added

- Blast-radius-scaled evidence bar (PARTIAL-P2/B3-4): `record_claim` gains an opt-in `blast_radius` field (`godmode claim --blast-radius ops-directed|sticky-side-effect|checksum-guard`) - a claim that declares one needs >=2 INDEPENDENT witnesses among its citations before a `verified` grade holds, not merely enough citations that resolve. Independence is a simple, documented predicate (`_witness_identity`/`_independent_witness_count`): two citations are the SAME witness only when both their kind and their resolved target match - a `file:` target drops any `#L...` line locator (two reads of one file are one witness), every other kind's target is its citation text verbatim, and two different kinds are always independent of each other regardless of target. Two copies of one `cmd:` string, or the same file cited twice at different lines, downgrade to `hypothesis` naming the bar; a `cmd:` and a `file:` citation on distinct artifacts pass. A claim that never sets `blast_radius` is graded exactly as before this field existed - v1 is opt-in, and no existing caller changes behaviour.
- Added a provenance-before-deletion gate (B3-6, PARTIAL-P1).

  `godmode_removal.py` already records *why* something was deleted, after the
  fact. `godmode_fence.deletion_verdict` is the mirror: *before* a deletion the
  fence would otherwise allow - an `rm` or archive-move of a tracked file -
  it asks whether a pre-check is on record.

  Requirement-driven like B3-5: with no policy declaration it stays advisory,
  recording what a pre-check would have covered and never blocking. Once
  `.godmode-authorization-policy.json` declares `deletion_provenance_gate`,
  the file's deletion is refused until `godmode fence delete-precheck --path
  <p> --history-read "..." --sole-carrier "..."` is on record - reusing C-16's
  reverse-impact traversal (`atlas.build(project).affected(path)`) rather than
  rebuilding it, so the record carries what traversal actually found.

  The shipped U-B2 evaluator-pin store (`godmode_sentinel.pinned_evaluators`)
  outranks this gate entirely: a pinned file's deletion stays denied
  regardless of policy or attestation, checked via the same
  `_pinned_evaluator_hit` helper the edit/mv/redirect branches of the
  classifier already use - not a second, independently maintained pin
  mechanism. Deleting an untracked scratch file is unaffected either way:
  nothing about it carries a provenance obligation to check.
- Duplicate-authority drift detector and paired-artifact declarations (GAP-2).
  `godmode_minimality.py` gains a `duplicate-authority` finding class:
  small literal collections (module-level string-list constants, enum-like
  dict keys, name-hinted version-string literals) are fingerprinted across
  the whole repo via `ast`, and their member sets are handed to
  `godmode_atlas._jaccard` - the same near-dup machinery `Atlas.duplicates()`
  already applies to symbol name/body shingles, reused rather than rebuilt,
  now applied to data literals instead of code shape. Two or more
  independent sites sharing >=60% of members (`duplicate_authority_threshold`,
  tunable, documented on `minimality_report`) are flagged naming both. An
  exact match is exempt only when exactly one side lives under `tests/` - a
  fixture intentionally restating a source list verbatim as a known-good
  sample is the classic false positive this class of detector earns a bad
  reputation from; two SOURCE sites, or a near-but-not-exact test/source
  pair, still flag. The report also carries one advisory note naming the
  magic-count anti-pattern (`assert len(x) == N`) and recommending a
  subset/superset assertion instead - no code enforcement of that note in v1.

  `godmode_precheck.py` gains the declared counterpart: `paired-artifact`.
  A project states "these two artifacts change together" once
  (`declare_paired_artifact`, a `decision` record namespaced
  `paired-artifact:<label>` - the same reuse-an-existing-kind,
  namespace-the-subject house pattern `removal:` and `reg:`/`reg-foreign:`
  already use). It is project policy a session writes and revises, not a
  generated snapshot like a static declared-config file. `precheck` - not
  `godmode_fence.completion_audit` - checks every later diff against it,
  because precheck already runs before work starts, while the missing half
  is still cheap to add. A commit/diff touching exactly one declared half is
  flagged naming which; both sides, or neither, is clean.
  Advisory only, v1 - it never joins `precheck`'s `findings`/`verdict`, the
  same treatment `foreign_precedents` already gets. `godmode_console.py`
  wires `precheck --changed` (defaulting to the working tree, same as
  `fence audit`) and a new `godmode paired-artifact declare` command.

  Population sweep of this repository found real candidates: `STATES`
  (`godmode_register.py`) and `_REGISTER_STATES` (`godmode_invariants.py`)
  are byte-identical, deliberately hand-mirrored to avoid an import cycle
  (already documented in both modules' own comments, already guarded by
  `tests.test_register`) - accepted as-is, and a strong candidate for its
  own `paired-artifact` declaration rather than a code fix. `EVENT_KINDS`
  (`godmode_constants.py`) and `MASKS`'s keys (`godmode_compress.py`) share
  51.9% membership - under the auto-detector's threshold, so not flagged by
  it - but are exactly the kind of pair worth an explicit `paired-artifact`
  declaration despite that, since the auto-similarity score and "should a
  human be told when one changes without the other" are different
  questions; recorded here as the two mechanisms' worked example rather than
  written into a live archive, since this repository ships no committed
  `godmode-state` archive to declare it into.
- Added a license/provenance gate for external-repo interaction (B3-5, GAP-4).

  Any external repository entering the work - a URL a command would `curl` or
  `git clone`, a `--source-repo` flag, a fetch or remote-add of a non-dependency
  repo - is now detected generically by `godmode_sentinel.classify_action` as
  `external_repo_ref`, alongside its existing category and tier, and never in
  place of them: an operation that already failed closed as a mutation still
  does.

  Detection alone decides nothing. Whether it becomes a hard gate is
  requirement-driven: with no policy declaration, `godmode license check`
  records an advisory only and never blocks. Once an operator's own
  `.godmode-authorization-policy.json` declares `external_absorption_gate`,
  the same operation is refused until `godmode license attest --repo <ref>
  --classification <permissive|proprietary-no-redistribution|unlicensed|
  copyleft-incompatible>` is on record for that exact repository - and
  anything other than `permissive` also needs a `--clean-room-note`
  describing what was read versus what was written.
- `godmode swallow` (U-B3-3): a static scanner for the shapes that discard a
  failure instead of reporting it - an empty or pass-only `except`/`catch`
  block, a bound exception name that is never referenced, a `{data, error}`
  destructure that drops `error`, and a `try` whose success branch logs while
  every failure branch stays silent. Python is a real `ast` parse; JS/TS is
  regex-shape best-effort, stated as such in the module docstring.

  Findings carry `severity: "advisory"` - a hard block on every hit would
  punish the non-fatal catches this runtime's own code relies on. What does
  fail is a ratchet: `.godmode-swallow-baseline.json` stores a per-file count
  of un-exempted findings, and a file whose count exceeds its stored entry is
  a `regression`, the command's one hard signal. `--update-baseline` tightens
  the file toward current counts but can never raise a stored ceiling, so
  re-running it cannot make a real regression disappear - only fixing the
  site, or annotating it, does.

  A `# godmode: swallow-ok <reason>` (or `// godmode: swallow-ok <reason>` in
  JS/TS) comment anywhere in the flagged span exempts that one site from the
  count - and its reason is always listed in the report's `exemptions`, never
  dropped silently. An annotation with no reason text exempts nothing; the
  site stays in `findings`, marked `annotation_without_reason`.

  The initial sweep over this repository found 27 sites, all `empty-except`,
  spread across 18 files - no `unused-exception-name` or `success-only-log`
  hits. All 27 are now the committed baseline rather than annotated
  individually: reading them, they are this codebase's own established
  degrade-not-block idiom (a best-effort cache read, a permission-hardening
  `chmod` that is a no-op on some platforms, a process already gone by the
  time it is killed), several already carrying their own inline reasoning.
  Annotating them site-by-site belongs to whichever change touches each file
  next; this change only had to prove the ratchet catches a new, unreasoned
  site landing on top of that baseline.
- External-tool error-severity gate (PARTIAL-P3/B3-7): closes L-173's exact shape - a third-party tool's own declared error severity, observed in its own captured output, logged and shipped anyway because only its exit code was ever read. `register_error_pattern`/`godmode error-pattern register --tool <name> --pattern <regex>` declares a tool + regex (requirement-driven, no defaults - an undeclared tool gates nothing). `record_verdict` now tests each checker's OWN captured stdout+stderr (never persisted verbatim) against every declared pattern whose tool name appears in that checker's command; if the fold lands on `confirmed` and a declared pattern matched, the write is refused unless `tool_error_ack` is `"acknowledged-remediated"` or `"acknowledged-deferred: <reason>"` (`godmode verdict record --tool-error-ack ...`). `contested`/`refuted`/`witness-malformed` folds are never gated - only `confirmed` claims the output was clean. `godmode_invariants._verdict_invariants` holds a raw `archive.append(...)` verdict record to the same rule from the denormalised `tool_error_findings`/`tool_error_ack` fields alone, the same defense-in-depth pattern as U-V1's drive-vs-acquit and terminated-vs-truncated invariants; its ack-vocabulary regex is a by-hand copy of `godmode_verdict.TOOL_ERROR_ACK`, asserted in sync by `tests.test_tool_error_gate`. The charter-rule template for a project that wants this doctrine stated in GODMODE.md prose lives in `register_error_pattern`'s own docstring - the pattern declaration itself is data, not something the prose compiler can safely mine.
- Upstream/vendor capability-and-doctrine diff (B3-1/GAP-1): `godmode upstream --diff <package>` (Python first-class via `importlib.metadata` + a real import of the top-level module; Node best-effort via `node_modules/<name>/package.json`'s `exports`/`bin` map) or `--path <vendored-tree>` (a forked or fully-copied external repo, carrying the same duty a lockfile dependency does) resolves the target's shipped surface and diffs it - reusing `godmode_atlas`'s existing symbol-extraction and name-similarity machinery, never a second implementation - against the project's own equivalents. One `upstream-diff` record per run; each upstream symbol with no project-side name match becomes a `finding` needing two separately-required verdicts, never one: an import verdict (`adopt`/`extend`/`diverge-deliberately`/`n/a-different-surface`, `--dispose SYMBOL=DISPOSITION:BEHAVIOR_VERDICT`) and a behavior verdict (`confirmed-we-have-it`/`confirmed-we-dont`/`unverified`) - a disposition with no paired behavior verdict is refused both by `record_upstream_diff` and, in defense in depth, by a new `godmode_invariants` archive-seam check that also catches a raw append. An unresolvable target never guesses: it writes a `stated-gap` verdict naming the reason. Enumeration is capped with the loud-cap discipline `godmode_egress.scan_project` already uses - the full population is measured before the cap, and `truncated: true` says so on the record. The duty itself is requirement-driven, never always-on: `required_scope`/`gate_applies` read a project's own compiled charter for a rule naming the `upstream-diff` duty (specific packages, or an explicit any-dependency/any-forked-repo scope); no matching rule means no gate, and a declaration can only add duty, never narrow it. `CHARTER_RULE_TEMPLATE` is the one emitted example, phrased to compile HARD with no edit to `godmode_charter.py`'s existing rule-shape table.

### Changed

- The README and marketplace listing kit now say only what the product does
  today, each claim paired with the command that reproduces it.

  The prior README asserted "five skills" where six now ship, an "at-risk"
  assessment verdict that this checkout currently reports as "workable," and
  a "Hosts: 6" badge that flattened three live-tested plugin hosts and three
  adapter-only hosts into one undifferentiated number. None of those were
  caught by review because nothing re-ran them against the repository they
  described.

  The rewrite opens with the felt problem instead of a feature list, puts
  observe mode ahead of any enforcement claim so a reader can watch what
  Godmode would have caught before trusting it to block anything, and groups
  the mechanisms (gate, verdicts, register, measurement, trust, run
  governance) each behind its own verify-yourself command. Every number in
  "The numbers" was run against this repository to write the section, and
  the two that weren't (the pre-v0.2.11 gate latency figures) are labeled as
  historical measurements with their release-note basis instead of being
  re-asserted as current.

  Host support is now stated in tiers instead of one combined claim: Claude
  Code's gate and session hook run live every session this repository is
  worked in; Codex and Grok ship the same plugin package and hooks
  convention but are not independently live-probed under those hosts; the
  three instruction-file adapters (OpenCode, Cursor, Gemini CLI) declare
  `tool_call_interception` as `UNAVAILABLE` because none of them exposes a
  pre-tool boundary. The platform note is explicit too: developed and tested
  on Windows, where the Windows kill path for an overrun run is exercised
  for real and the POSIX kill path (`os.killpg`) is pinned by a mocked unit
  test, not live-probed on a POSIX host.

  `docs/LISTING.md` is new: short and long descriptions, keywords, category,
  and submission steps per marketplace (Claude, Codex, Grok), plus a
  manifest audit that finds neither `.claude-plugin/plugin.json` nor
  `.grok-plugin/plugin.json` carries any pointer to the shipped logo, and
  that Codex has no `marketplace.json` where Claude and Grok both do. The
  audit is read-only by design; the manifest edits it surfaces are a
  follow-up task.

  `tests/test_readme_commands.py` pins every fenced `godmode` invocation in
  the README against the real CLI parser (`_build_parser`), the same
  mechanism `tests/test_demo_doc.py` already runs against `docs/DEMO.md`. A
  doc edit that renames or invents a subcommand fails this test, not a
  reader's copy-paste.

## [0.2.12] - 2026-08-15

### Added

- Anchored-metric citation contracts (E9, U-T3): `register_metric_contract`/`godmode metric-contract register --name <name> --anchor <regex>` declares the one output shape a numeric claim about `<name>` may cite, stored as a `decision` record under `metric-contract:<name>`. `_citation_resolves` gains a `line:<name>:<value>` citation kind, resolving only when a contract is registered for `<name>` and the reconstructed `"<name>:<value>"` text matches its anchor. `record_claim` cross-checks any registered metric name appearing in the (markdown-emphasis-stripped) claim text against the first number in that text: a `line:` citation whose value disagrees downgrades naming both numbers ("the cited line says X, the claim says Y"); an unregistered metric name gets no friction from this at all.

  Anchor validation is two independent layers, not one. Registration checks `re.compile` succeeds, a 200-character length cap, and (fix round 1) a scan for the named nested-quantifier shapes (`(X+)+`, `(X*)+`, `(X+)*`, `(X*)*`, and the `{m,n}` forms) that risk catastrophic backtracking - a review round demonstrated `(a+)+b` compiles fine and clears the length cap, yet hangs the interpreter once matched against a crafted `line:` value at grading time, because the length cap bounds the anchor's own length, not the length of the text later matched against it. The second, independent layer closes that gap directly: the matched VALUE half of a `line:` citation is capped at 64 characters before any regex runs at grading time, holding even for a shape the registration-time scan misses.
- Capability coverage matrix (13c) and this repository's own dogfooding
  (U-S3). `docs/CAPABILITY-COVERAGE.md` ships one table naming eight
  capability classes in godmode's own vocabulary - session continuity, claim
  admissibility, process discipline, minimality pressure, approval gating,
  content trust, session burn measurement, and prose-restyling/token-burn
  reduction as an explicit non-claim - with honest statuses: `covered` only
  where surface pointers resolve to shipped code and tests, `partial` where
  part of the class is mechanized and the rest is a stated boundary,
  `not-claimed` where it is a scope boundary rather than a gap.
  `godmode_reconcile.reconcile_capability_coverage` holds every row to the
  same both-directions discipline as the capability register.

  Dogfooding: all five of this repository's live HARD charter rules are now
  provably planted (`godmode capability register` archive state,
  `assess.hard_unplanted == []`), each against the specific test that already
  exercised the guarded line rather than an inferred break. `init --roles`
  scaffolded the eight missing authority-document roles; every stub now
  carries a real paragraph about this repository's own state, decisions,
  invariants, inventory, lessons, operator profile, sprint truth, and release
  checklist (`assess.missing_roles == []`). Four of the eight role documents
  (state, decisions, lessons, sprint-truth) are gitignored by this
  repository's existing proprietary-content convention, so `missing_roles`
  and the eval charter/ranking snapshots are, honestly, machine-local facts
  here - the charter/ranking snapshots in `evals/fixtures/` are re-baselined
  against the committed-only role documents so a fresh clone still reads
  `routing-sound`.
- Capability register reconciled to code (U-S2): `capabilities.json` at the
  repository root enumerates every capability id from the private sprint
  ledger (`C-01`…`C-81`, ids and neutral one-line statements only, honest
  gaps recorded where a numbered id has no retrievable statement) with a
  status (`built`/`partial`/`unbuilt`/`rejected`) and, for `built`/`partial`
  entries, the `file:`/`test:` pointers that back the claim.

  `godmode_reconcile.reconcile_capabilities` holds the register to the same
  both-directions discipline as the existing guard-citation reconciler: a
  `built` entry whose pointer no longer resolves is dead, and an
  `unbuilt`/`rejected` entry whose pointer DOES resolve is a status that went
  stale the moment the code landed. `godmode assess` now surfaces the
  `unbuilt` ids as `capability_debt`, and `godmode capabilities --reconcile`
  runs the check directly, exiting non-zero on drift.
- Two-minute terminal demo script (U-E9): `docs/DEMO.md` walks five real
  commands in order - `godmode scenarios --brief` (23 staged attack/failure
  shapes, live), the 142-command regression corpus story
  (`tests/fixtures/gate_corpus.json` +
  `tests.test_gate_corpus.GateCorpus.test_every_entry_matches_expected`),
  the measured gate numbers quoted verbatim from
  `docs/releases/RELEASE_NOTES_v0.2.11.md` with each figure's own basis
  named beside it, one `godmode verdict record` walk-through showing a
  confirmed and a refuted disposition against the same witness, and
  `godmode init --detect` on a fixture repo. Every command shown is a real
  CLI surface, pinned by `tests/test_demo_doc.py`, which parses the doc's
  fenced commands and asserts each `godmode <subcommand>` resolves in the
  console parser. No causal language ("saves", "prevents") and no session
  provenance beyond neutral "real sessions" - the same discipline U-E1's
  denylist already holds ROI output to.
- Differential-evidence detector (U-E3): mechanizes a private-ledger lesson (§4.8a/L-267) - when two comparable states exist, a root-cause claim without the differential is inadmissible. New record kind `differential` (`{subject, a_ref, b_ref, delta, method}`, `delta` capped at 20 items of 160 characters each at append) via `record_differential`/`godmode differential record --subject ... --a <ref> --b <ref> --delta ... --method read|cmd:<...>`; a `diff:<seq>` citation resolves iff the record exists AND both `a_ref`/`b_ref` also resolve, so a deleted record or a dangling ref stops the citation resolving. `record_claim`'s detector fires only when root-cause vocabulary (`ROOT_CAUSE_VOCAB`, plus the pre-existing recognizer) is found OUTSIDE quotes and code spans, and only once the archive holds two or more comparable-state records (`checkpoint`/`verdict`/`metric`) sharing the claim's salient terms; it then requires a RESOLVING `diff:` or `verdict:` citation, downgrading and naming the comparable sequences otherwise. No comparable states leaves the claim untouched - absence of the instrument is a stated gap, never a penalty, the same discipline U-T2 already applies to the red-before-green check.
- Disposition register with superseded states and rejection precedent (U-V2):
  a closed-enumeration register (`established`, `superseded`, `refuted`,
  `worse-than-baseline`, `matched-baseline`, `rejected-precedent`, `open`) over
  `decision` records whose subject is `reg:<domain>:<key>`. The register is a
  derived view, never a stored second copy - `register_view()` folds every
  record for a domain into latest-state-per-key with full lineage, and an
  unlisted key reads as the explicit named default `open`, not an error and
  not `None`.

  Every non-open entry needs at least one `witness:`/`verdict:`/`file:`
  evidence citation, refused at `set_state()` and again at the archive seam
  itself (`godmode_invariants._register_invariants`, seeded eagerly into
  `Chronicle.append()`'s `KIND_INVARIANTS`) so a raw append that bypasses this
  module cannot slip an unevidenced or unlisted-state entry past either.
  Transitions are legal-only: `open` reaches anything; every closed
  disposition's only way back to `established` is a record naming
  `supersedes:<seq>` that cites the exact record it replaces -
  `established -> superseded` and `rejected-precedent -> established` both
  need it. `set_state()` refuses an illegal or wrongly-cited transition at
  write time; `conflict_findings()` detects the same violations at read time
  for a hand-appended record that skipped `set_state()` - a HARD halt finding,
  never a silent latest-wins.

  `precheck` now consults `rejected_precedents()`: a task whose normalized
  terms name a `rejected-precedent` key across any domain is told the
  precedent's sequence and the way through - cite it and supersede it, or drop
  the work. `godmode register set|supersede|show`.
- Two docs-lint advisories, absorbed from two lessons (U-E11): `stale-open-marker`
  flags a scanned doc line carrying an open-status marker (`pending`, a bare
  to-do marker, `open item`, `not started`, `in progress` - a small closed
  tuple, word-bounded) with no `YYYY-MM-DD` verification date on the same or an
  adjacent line, exempt inside fenced code blocks. `title-collision` flags two or more LIVING docs
  whose first heading normalizes to the same term set (via
  `godmode_precheck._terms`, reused rather than duplicated) with neither
  carrying a `supersedes`/`superseded by` pointer, naming every colliding path;
  archive/changelog docs are exempt through the same `_HISTORICAL` pattern the
  figure and self-pin checks already use.

  Both ride `lint_docs`'s `prose_advisories` seam alongside the charter-prose
  checks: `severity: "advisory"`, never joining `findings`/`high_severity`/
  `verdict`, so neither can fail `docs --lint`.

  Population sweep on this repository surfaced real, honest advisories rather
  than a clean scan, all accepted rather than fixed (out of this unit's file
  scope): twelve `stale-open-marker` hits - ten in historical prose
  (`CHANGELOG.md`, `docs/releases/RELEASE_NOTES_v0.2.10.md` and `.../v0.2.11.md`)
  or SKILL.md example/behavior text (`skills/godmode-repair/SKILL.md`,
  `skills/godmode-continuity/SKILL.md`) using the marker words as vocabulary,
  not as literal open items, and two self-referential ones right here in this
  fragment's own description of the marker tuple; and one `title-collision`
  group - `GODMODE.md`, `llms.txt`, `locales/hi/GODMODE.md`, and
  `skills/godmode/SKILL.md` all title themselves plainly "Godmode" - a
  translation, an SEO summary, and a skill entry point sharing one common
  word, not a stale duplicate needing a supersedes pointer. `docs --lint`'s
  blocking verdict on this repository remains `clean` (exit 0) either way,
  since both checks are advisory only.
- Versioned eval registry + grader vocabulary (U-S1).

  Scenario coverage (`godmode_scenarios.py`) never named which version of a
  staging function produced a "caught" result, so an edited scenario and an
  untouched one looked identical in the report. Every scenario now carries a
  `name.local.vN` id and a content digest (`sha256` of the staging function's
  own source, via `inspect.getsource`) recorded alongside its outcome. A
  pinned registry (`SCENARIO_DIGEST_REGISTRY`) freezes the digest each id was
  last reviewed at; a scenario whose body changed with its version left alone
  surfaces as a `digest-drift` blocking finding in `run()`'s `registry` field
  - caught by planting exactly that edit and watching the finding appear. The
  registry's population is grows-only in both directions: a scenario with no
  registry entry (`unregistered-scenario`) and a registry entry naming a
  scenario no longer in `SCENARIOS` (`orphaned-registry-entry`) are both
  blocking findings too, so a scenario can neither join unchecked nor leave a
  stale pin behind. `godmode scenarios --brief` - the literal CI gate - now
  exits nonzero on any blocking registry finding, not only on a missed catch.

  `godmode_graders.py` is new: a closed vocabulary of deterministic
  comparators (`match` with prefix/any-of, `includes`, `fuzzy` containment in
  either direction after normalisation, `json_match`) that eval definitions
  can name instead of re-inventing string comparisons per skill. `json_match`
  fails closed - invalid JSON on either side never matches, even when both
  sides are byte-identical malformed input. `godmode_evals.py`'s
  behaviour-assertion checks can now declare a `grader` field to use this
  vocabulary directly, and a new `compare_eval_results` refuses to diff two
  result records that carry different ids: "scores are comparable only within
  an id."
- Protected-evaluator hash pins (U-B2): `godmode protect --pin <path>` freezes a file - normally the evaluator/grader a change is judged against - so the measuring instrument can never be optimized along with the code it measures. Pin records live in the archive (hash-chained, `kind="pin"`, shape-checked by a new `godmode_invariants` validator), which is authoritative; `.godmode-protected.json` is a convenience view nothing ever reads back to decide anything. `_categorize`'s edit branch (`godmode_sentinel.py`) checks pins before returning a category at all - an Edit/Write payload (or a shell redirect) at a pinned path is a HARD `pinned-evaluator-mutation` finding at R5, denied outright at the hook and checked before the scope fence even runs, so a pin always outranks a fence allowance. Unpinning is the one operation that can defeat the mechanism and is gated the same way a forced push is: `godmode protect --unpin <path>` classifies as `evaluator-unpin` (R5), refused without a capability, and honours a staged one the same way every other refusal does (`godmode authorize stage --operation "godmode protect --unpin <path>"`). `godmode_integrity.pin_drift` catches what the hook cannot see: a pinned file mutated out of band (a plain filesystem write, a shell command the hook never gated) is a blocking finding naming the pin, and a hand-edit of `.godmode-protected.json` - adding, removing, or altering a pin outside `protect` - is caught the same way, since the view is regenerated byte-for-byte on every real pin/unpin and the monitor compares against what the archive's current pin set would write. `godmode protect --list` reports the current pin set. Fix-round-1 (task-7 review): `mv`/`cp`/`Move-Item`/`Copy-Item` were entirely absent from the sentinel's mutation vocabulary and silently overwrote (or renamed away) a pinned evaluator with zero confirmation - they now write their DESTINATION argument (source arguments are checked for a pin hit too, since renaming a pinned path away defeats the mechanism the same way overwriting it does; sources get no other write-style check, reading is ordinary), escalating rather than guessing for a `-t`/`--target-directory` form. `CapabilityBroker.issue` (reached through `stage`) now also resolves against the broker's own project rather than the process's cwd, closing the same gap `_classify` was fixed for but that `issue`'s own direct `classify_action` call had kept open. `pin_evaluator`/`pin_drift` cap and stream their hash the same way `godmode_lens.py`'s inventory sweep already does (`MAX_HASH_BYTES`), rather than loading a pinned file whole into memory.
- Commit-linked experiment ledger with epsilon adjudication (U-R3): each
  `run_experiment()` call is one cycle, and a next cycle is now REFUSED
  until the one before it has a `verdict` record (verdict-before-next-cycle,
  enforced at the API; `godmode_loop.unadjudicated_experiment_cycles` is the
  read-time half, for a raw append that bypasses `run_experiment` entirely -
  wired into `analyze()`). New `godmode_guardrails.record_experiment_verdict`
  adjudicates a cycle from `{metric, before, after, epsilon}`: improvement
  `>= epsilon` keeps, short of that discards, unless the result is exactly
  flat AND declared `simpler=True` (`keep-simpler`) - a regression is never
  rescued by "simpler" alone. Every verdict is commit-linked (`run_git
  rev-parse HEAD`, `run_git` from `godmode_anchor`). A declared `max_cycles`
  in `.godmode-experiment.json` bounds the series itself: exhausting it with
  no explicit completion claim on record writes a closing `verdict` with
  `run_state: "truncated"` and refuses to run again - loop exhaustion is
  never read as completion (E78's positive completion sentinel); a
  completion claim, once made, is audited by U-V1's own unmodified
  citation-grading (`godmode_attest._citation_resolves`), not reimplemented
  here. `acquitted_by="self"` (the default) never sets `disposition`, so a
  self-graded cycle can never trip the archive-seam invariant; a caller
  asserting `acquitted_by="independent"` is held to the same
  `godmode_invariants._verdict_invariants` rules as every other verdict kind
  - a truncated (exhausted or budget-cut) cycle can still never be recorded
  "confirmed". CLI: `godmode experiment` is now `experiment run` /
  `experiment verdict` (was a single flat command).
- Fabrication-pattern detector catalog and a minimality report (13b).
  `capabilities.json` gains a `detectors` section: every live mistake-class
  detector in `godmode_mistakes.py` (`M1`, `M2`, `M6`, `M8`, `M13`-`M22` -
  the sparse numbering is real; M3, M4, M5, M7, M9-M12 were never
  implemented, and the catalog records that gap rather than hiding it) with
  its function, version, and the fabrication family it targets.
  `godmode_reconcile.reconcile_detectors` checks each id resolves to a real
  function and a real guard test; a detector added to the source without a
  matching catalog entry fails the population check.

  `godmode minimality` is new: one command aggregating four existing surfaces
  - atlas duplicate/orphan symbols, atlas speculative seams, census
  unexercised surfaces, and charter decay - into a single ranked report with
  counts and file pointers. Aggregation only; no new analysis.
- Graduated starting profiles (U-E8): `godmode init --profile novice|standard|strict` sets a STARTING posture on the existing tighten-only authorization ratchet, never a different one. `novice` widens `.godmode-authorization-policy.json`'s `approval_required` to `git-branch-create` and `worktree-file-mutation`, so an ordinary file edit or new branch asks instead of proceeding silently. `standard` manages no policy key at all and writes nothing - a pinned no-op, identical on disk to omitting `--profile`. `strict` widens `approval_required` to `release-or-external-write` and prints a `password_required` suggestion for the same category without ever writing it, the same detect-then-promote split `init --detect` already uses. Every changed line is emitted with its provenance (`"(profile: novice)"`) so the operator sees exactly what was set. No profile application may remove an `approval_required` category already explicit in the policy file, whether a prior profile or a hand edit put it there: `godmode_profile.apply_profile` refuses, naming the category, rather than silently loosening it.
- Observe mode + ROI digest (U-E7): a policy-file posture (`"gate_mode": "observe"` in `.godmode-authorization-policy.json`, read through the existing `local_authorization_policy` seam and validated to that exact spelling - any other value refuses loudly rather than being silently ignored or silently entered by typo) under which the full hook (`godmode_session_hook.py`) still classifies every operation exactly as it always did - ceilings, the watchdog, the classifier's ask/deny split, the design boundary, the scope fence - but converts every resulting deny/ask into an archive record (the existing `refusal` kind, with `observed: true` and `would_have: "deny"|"ask"` added) plus a `systemMessage` advisory, and never a `permissionDecision`. Fail-open is unaffected: a malformed or unreadable `gate_mode` degrades to enforcement, the same way `password_required`/`approval_required` already do. The fast gate (`godmode_gate_fast.py`) is untouched - its allow path was already silent, and every escalation reaches the full hook, where this conversion already applies. Entry has exactly one door: a deliberate policy-file edit. `init --profile` (U-E8) stays enforcement-only and never touches `gate_mode`. The session-start brief announces observe mode explicitly ("gate in OBSERVE mode - nothing will be blocked") whenever it is active, and `godmode assess` surfaces the posture as a stated `gate_mode` field plus a `medium` finding.

  `godmode roi --digest` renders the would-have-caught view: `would_have_denied`/`would_have_asked` counts by category, folded from observed refusal records only, with `seq:` basis references - same causal-denylist discipline as U-E1's `roi_report` (`render_digest` is checked against `CAUSAL_DENYLIST` too). `roi_report`'s `gate.denied` excludes observed refusals on purpose - that bucket counts real enforcement outcomes, and an event that was never actually blocked must not inflate it.

  Decision, documented and pinned by test: `stage_from_refusal` never stages an `observed: true` refusal by default - nothing was actually blocked when it was written, so there is no live escalation for a staged capability to answer; `--nth` skips past observed records to the nearest real one.
- Cross-project precedent exchange, file-carried and opt-in (U-E2): `godmode
  precedent export --domain <d> --out <file>` writes one project's
  `reg:<domain>:*` register entries (key, state, evidence collapsed to bounded
  statements) plus an origin fingerprint (`sha256(project-root basename +
  archive genesis hash)[:16]`) as one self-verifying JSON file, whole-file
  `content_hash` computed over canonical JSON. The operator carries the file -
  that IS the transport; no network, no daemon.

  `godmode precedent import <file>` verifies the content hash before writing
  anything, then appends the entries into a SEPARATE namespace
  (`reg-foreign:<origin-fp>:<key>`), never `reg:<domain>:<key>` itself. A hash
  mismatch or malformed file is refused with nothing partially imported, and
  `binding` is force-set to `False` on every imported record regardless of
  what the file claims - a foreign precedent can never arrive binding, even
  from a hand-crafted file whose own hash is genuinely valid.

  Foreign precedents are advisory everywhere: `register(archive, domain,
  foreign=True)` reads them separately from the local, binding
  `register_view()`; `conflict_findings()` never scans the foreign namespace;
  and `precheck()` surfaces a matching foreign entry in its own
  `foreign_precedents` section, labeled `foreign precedent (from <fp8>)`,
  which never joins `already_rejected`/`rejected_precedents` and never flips
  `verdict` to blocking. `godmode precedent adopt --domain <d> --key <k>` is
  the one explicit, human-triggered promotion to a local, binding record,
  citing the foreign entry as evidence.
- Charter prose linter + assumption gate + declared approval categories
  (U-S4), three small units closing E6/E4/E56:
  - **Prose linter** (advisory, never blocking) - `godmode_charter.negation_heavy`
    flags a HARD rule with two or more negation tokens ("never"/"without"/
    "not"...) and no positive verb: the shape a rule takes when it states
    only what must not happen. `godmode_docslint.lint_charter_prose` runs
    this plus two more checks over a project's own compiled charter
    (`compile_charter`): `no-done-criterion` for a rule the charter could
    not map to any checkable shape (`enforcement == ADVISORY`), and
    `duplicated-source` for the same normalized directive bound from two
    different role documents. `lint_docs` now carries the result as a
    separate `prose_advisories` key that never joins `findings`/
    `high_severity`/`verdict` - `docs --lint` cannot be failed by a
    prose-quality note. Doctrine exemption (controller ruling): a HARD rule
    phrased as a *named* prohibition ("never mutate production", "never
    claim verified" - a negation opening the sentence and naming a concrete
    object, articles skipped) is exempt outright, never rewritten - safety
    prohibitions keep their prohibition form; a placeholder object ("do not
    do things") or a verb with nothing named before the clause boundary
    ("never push without...") still flags. Population sweep: this repo's own
    two "never X without Y" HARD gates in `GODMODE.md` resolve as named
    prohibitions and stay exactly as written; the 3 ADVISORY sentence-fragment
    rules are accepted as-is (already reviewed - see
    `tests/test_charter_checkability.py`'s `AdvisoryReviewRepoTests`).
  - **Assumption gate** [E4] - new `assumption` record kind
    (`remember --kind assumption`); `godmode_attest.assumption_gate` is a
    SOFT `before_approach` advisory, "state assumptions or state that there
    are none", firing once per session for an R3+ session with zero
    `assumption` records. Reuses U-T2's R3+ tier proxy (fix-vocabulary
    claims + Edit/Write mutation turns) rather than a second definition;
    `godmode gate --trigger before_approach [--transcript PATH]` now surfaces
    it via `Verdict.advisories`, which never affects `allowed`.
  - **Approval declarations** [E56] -
    `.godmode-authorization-policy.json` gains `approval_required:
    [<category>...]`; `classify_action(..., require_approval=...)` widens an
    otherwise-unprotected operation in a declared category to ask-tier, with
    the exact operation named in the reason. Tighten-only by construction:
    the risk tier is computed from category/command text alone and never
    reads the `protected` flag this widens, so a declared category can never
    soften an existing R5 refusal to an ask. Wired live:
    `hooks/godmode_session_hook.py`'s pre-tool `classify_action` call now
    sources `password_required`/`approval_required` from the policy file
    (new `godmode_sentinel.local_authorization_policy`), read in its own
    fail-safe `try/except` so a malformed policy degrades one call rather
    than the whole gate - previously both fields were parsed and validated
    but never reached the hook's own decision.
- Recurring-ask mining (U-E10): `godmode recurring [--threshold N] [--json]` folds the request ledger (`godmode_requests`, written live by the user-prompt hook) into charter-rule proposals - a normalized term set (via the same `_terms` helper `precheck` uses, imported rather than reimplemented) that recurred in at least `--threshold` distinct sessions (default 3) is reported as `asked in K sessions - SOFT rule candidate`, with `seq:` references as basis. Same shape as `init --detect`: candidates only, nothing is auto-written to the charter. A cluster's basis is its normalized term set and session refs alone - the original request wording is read only long enough to compute terms and never reaches the report. A ledger with fewer distinct sessions than the threshold reports `insufficient-data` and states the session count, rather than an empty candidate list a reader could mistake for "checked, found nothing".
- Red-before-green temporal verification + criterion pre-registration (E4 R4/E6 tdd, U-T2): `godmode_session_log.session_timeline`/`command_timeline` extend the U-T1 transcript parse with a per-command outcome timeline (`cmd_digest -> [(turn, exit_code)]`, digests only) and mutation turns (Edit/Write/NotebookEdit tool_use), deriving red/green from a `tool_result` block's `is_error` flag - the real transcript shape carries no structured exit code, only that boolean (recorded in the module docstring). `record_claim` gains an optional `timeline` param: a fix-vocabulary claim citing `cmd:<command>` is checked for a nonzero-exit observation before the last mutation and a zero-exit after; missing that shape downgrades with "cited test was never seen failing (red) before the fix"; no timeline supplied is untouched (a stated gap, never a penalty). New `record_criterion`/`godmode criterion` records what passing looks like under `criterion:<task>`, cited back from a claim (`_citation_resolves` gains `criterion:` support); a weak-criterion (no `cmd:` citation, only vague verbs) and a criterion recorded after the session's first mutation both surface as advisories, never downgrades - a fix claim citing no criterion when one exists this session is likewise advisory-only.
  - Plan artifacts carry executable acceptance (E62, Task 4b): the plan contract gains `accept: ["cmd:<command>", ...]`, a list of executable acceptance commands distinct from the prose `acceptance` field; `planmode approve` refuses a plan with no `accept` entry (surfaced in `gaps`/`missing`, same discipline as every other mandatory field); `close_session` (before_completion) now also refuses while any `accept` command lacks a this-session attestation (`unattested_accept_commands`), via `godmode_plan.unattested_accept_commands`. CLI: `planmode start --accept cmd:<command>` (repeatable).
- Counts-only ROI report (U-E1): `godmode roi [--sessions N] [--json]` folds `metric` records (C-79/U-T1 token measurements), `verdict` records (U-V1 dispositions), and gate/precedent/fence `action` records into one report - `sessions`, `tokens{in,out,measured_sessions,unmeasured_sessions}`, `gate{denied,asked,advisories}`, `verdicts{confirmed,refuted,contested}`, `precedent_hits`, `fence_findings`, and a `basis` of `seq:` references so every number can be checked against the record that produced it. A session with no measurement record is stated as `unmeasured_sessions`, never interpolated as a token count. The report shows what gate activity happened beside burn and leaves the reader to judge what it was worth; a REFUTED verdict is labeled `rework-candidate-caught` - what the event was, not a claim about what would have happened otherwise. A denylist test checks the rendered text against a closed list of attribution words and is itself proven to catch a planted regression, not merely asserted by construction.
- Counts-only session measurement (C-79/U-T1): `godmode_session_log.measure` streams the host's own transcript (`json.loads` per line, never the whole file) and tallies tool calls, commands, test runs, and token usage; `record_measurement` writes it as a new `metric` archive record - counts and a closed enum of names only, every stored string capped at 80 characters, proven against a planted sentinel string that never reaches the archive. Wired at session-end in `hooks/godmode_session_hook.py`, wrapped in `try`/`except` so a measurement failure never costs the checkpoint; a missing or unreadable transcript is recorded as a stated gap rather than an error.
- Trust now reads skill, command, and agent content as untrusted input.

  `godmode trust` scanned settings and MCP JSON only. A cloned repository's
  `.claude/skills/**/SKILL.md`, `.claude/commands/**/*.md`, and
  `.claude/agents/**/*.md` files are prose a host loads and follows the moment
  a session starts, and nothing scanned them.

  `scan_agent_configuration` now enumerates those files, capped at 400 with the
  cap reported, and routes each through the same untrusted-content and secret
  checks the repository sweep already applies. A line shaped like an
  instruction produces a `skill-directive` finding naming the file, the line,
  and the kind. A secret-shaped value produces a `skill-secret` finding. A
  settings hook whose command classifies at R4 or above now also produces a
  `hook-command-tier` finding, naming the tier, because a hook fires with no
  per-call confirmation from the action gate.

  Godmode's own six shipped skills are the population check: their SKILL.md
  content runs through the new scan as part of the test suite and returns no
  findings.
- `godmode authorize stage --from-last-refusal [--nth N]` (U-E5): the gate's
  own R5 refusal now records itself (kind `refusal`: bounded operation, tool,
  tier, category), and staging reads that record back instead of asking the
  operator to retype the command a refusal already printed verbatim. Nothing
  about the trust model changes - the password is still required, the
  capability is still spent once, it still expires - only the typing does.
  `--nth 2` reaches a refusal before the latest one; with none on record the
  command refuses with "nothing to stage" rather than staging something
  stale. The staged operation is echoed back before the password is checked,
  so a wrong `--nth` is caught by eye. The refusal reason itself gains one
  literal line, `! godmode authorize stage --from-last-refusal`, so a hosted
  session can run it without leaving the conversation.
- Graduated stall escalation - redirect at 2, human at 4 (U-R2):
  `godmode_loop.analyze` gains `stall_escalation`, an empty-round counter
  joining the existing oscillation/spent-hypothesis detectors. A round
  closes at each checkpoint; it is empty when no change, attestation, or
  verdict was recorded since the previous one. Two consecutive empty rounds
  produce a blocking `stall-redirect` finding ("record what you'll do
  differently"); four produce a governance `stall-escalation` halt ("human
  escalation required"), cleared only by an operator-sourced record
  (`data.source == "stated"` on a `request`/`decision`) - an agent's own
  inference does not count. `godmode watchdog` gains a matching freshness
  check (`state_freshness`): a loop that claims activity (`--loop-active`)
  but has not touched the archive within the age ceiling routes to the same
  `human-escalation` verdict as a stall streak.

  Task 10b (amendment): a loop/experiment declaration now states `maturity:
  "report-only"|"assisted"`; `"unattended"` is refused by name, not silently
  downgraded - nothing here reads a cycle's output before the next one
  starts. `godmode loop --preflight` audits `.godmode-loop.json` before
  cycle one via `loop_ready`: a declared stop contract (U-R1), a positive
  `budget_s`, a named `verdict_path`, and sane escalation thresholds
  (`n1 < n2`, both positive) are all required, each missing piece its own
  blocking finding.
- Surgical-diff completion gate (U-B1), extending the existing scope fence
  rather than adding a second one: `fence audit --complete` parses `git diff
  --unified=0 HEAD` into hunks - stdlib text, no dependency on a diff library -
  and partitions them by the same `fence_verdict` a plan's editable set already
  answers with, so three questions get asked of one parse instead of one.

  A hunk that adds or changes lines in a file outside the declared set is an
  `out-of-fence-hunk` finding naming the file and how many hunks landed there.
  A hunk that only removes lines in such a file is told apart as
  `unauthorized-deletion` - pre-existing code outside the plan's own scope is
  not the plan's to remove, whatever the reason, and the remedy says so:
  mention, don't delete. A deletion inside a file the plan does own passes
  either way. And every added line, in any file, is checked against a small
  default instrumentation-tag tuple (`[DEBUG-` to start) for an
  `instrumentation-residue` finding naming the exact `file:line` - the one
  check here that is not fence-scoped at all, because a stray trace print left
  in a change claimed complete is not made acceptable by landing somewhere the
  plan was allowed to touch.

  Undeclared still means unenforced: with no approved plan's editable set to
  check a hunk against, the fence-shaped findings stay silent, the same
  fail-open contract `fence_verdict` already keeps for every project that
  predates this gate. A plan extends the tag tuple through the same editable
  field a fence already reads, by writing `tag:<pattern>` alongside its globs -
  one declaration, not a second config surface next to it.
- Composable termination algebra with fail-loud lifecycle (U-R1): new
  `godmode_stop.py` - `Stop` predicates (`MaxRecords(n)`, `MaxWall(seconds)`,
  `OperatorStop(flag_path)`, `MetricPlateau(name, eps, patience)`) consulted
  over the record-delta since the last call, so cost stays O(new) regardless
  of run length. Compose with `&`/`|`; a composed reason names WHICH leaf
  fired. A fired `Stop` is spent - consulting it again without `reset()`
  raises `SpentStopError` rather than quietly re-answering. `attempt(budget_s)`
  bounds one subprocess attempt: overrun kills the process outright and the
  result carries `run_state: "truncated"` (U-V1's vocabulary), so feeding a
  truncated result into a `disposition: "confirmed"` verdict hits the
  existing archive-seam refusal in `godmode_invariants._verdict_invariants` -
  budget exhaustion cannot impersonate completion. `godmode watchdog`
  consumes an `OperatorStop` flag (`.godmode-stop`) so an operator can
  interrupt the boundary scan regardless of the skip pattern; `godmode
  experiment` gains an optional `--budget-s` wall-time bound over the whole
  bounded series, independent of `max_runs`.
- `verdict` panels (U-E4): `record_verdict`'s `--checker` is now repeatable
  (1..N; a single command still works unchanged - every caller from before
  panels existed is unaffected). Each checker runs independently against the
  same witness, never invoking the producer, and its own
  `{checker, exit, disposition}` is recorded verbatim in `checks`. The panel
  folds to one disposition by a closed rule, never a score: all confirmed ->
  `confirmed`; any refuted -> `contested` when at least one other checker
  confirmed, else `refuted` outright; a checker that could not judge is
  recorded as a stated gap and excluded from the fold, unless none of them
  judged anything, in which case the whole panel is `witness-malformed`.
  `contested` joins the disposition enum. The archive-seam invariant now
  also refuses a `confirmed` fold whose own `checks` carry a refuting entry,
  whether that record comes from `record_verdict` or a raw append. A
  `verdict:<seq>` citation still resolves only on `confirmed` - `contested`
  is refused by that same existing rule, with no separate code path needed.
  `godmode verdict record --checker <cmd> [--checker <cmd> ...]`.
- `verdict` record kind (U-V1): a claim of "fixed X" becomes admissible only
  as a claimed value plus a data-only witness plus an independent checker
  that recomputes from the witness alone and asserts against the claim.
  Three dispositions, never two - `confirmed`, `refuted`, `witness-malformed`
  - with the witness validated structurally before the checker ever runs, so
  a missing witness or a checker that cannot start/finish is stored as
  "never judged," not silently folded into "judged false." Two invariants
  are refused at append time: a self-acquitted `confirmed` (quality needs an
  independent checker), and a `confirmed` on a `truncated` run (a budget
  cutoff cannot impersonate completion). `godmode verdict record|show`; a
  `--grade verified` claim citing `verdict:<seq>` resolves only when that
  verdict's disposition is `confirmed`.

### Fixed

- This repo's own charter advisory rules are fully reviewed, and the review
  test is portable. 16 of 19 committed ADVISORY charter rules (added by the
  capability-register/coverage/minimality/checklist docs) had never been run
  through `charter --review-advisory`; each now carries a real, rule-specific
  decision record (`charter-advisory-reviewed:<id>`) - most are documentary
  sentence fragments or topic sentences the charter compiler's per-line
  chunking produced (not imperative directives), a few describe behaviour
  that is genuinely already mechanically enforced elsewhere
  (`capabilities --reconcile`, `changelog check`) but not in a shape the
  charter compiler's checkable-shape table recognises. One rule was
  genuinely wrong rather than merely unreviewed:
  `docs/RELEASE-CHECKLIST.md` read "Before this sprint's commits land",
  contradicting the doc's own "Standing verification rows" framing by naming
  one already-landed sprint - reworded to "this repository's commits" so the
  checklist reads as reusable.

  Separately, `tests/test_charter_checkability.py`'s
  `AdvisoryReviewRepoTests` read this machine's live, gitignored archive
  unconditionally and could never pass on a fresh clone or CI, where no
  `charter-advisory-reviewed` decision exists yet. Restructured to the same
  degrade pattern the role-doc and private-ledger tests already use: it
  skips with an explicit message when the local archive holds no review
  records, and asserts `advisory_unexplained == []` fully once real ones
  exist.
- `untrusted` no longer claims a clean sweep over files it never read.

  `godmode_egress.scan_project` capped its walk at 400 files and stayed silent
  about it: once the repository grew past that count, a file sorting later in
  the tree - `docs/falsification-probe.md`, planted by the falsifiability
  harness itself - fell outside the window, was never opened, and the scan
  still reported `"data-only"`. `untrusted --brief` stayed green over an
  injection it had never scanned.

  `scan_project` now counts every candidate file before applying the cap. When
  candidates exceed the limit, the report carries `candidates` (the true
  count) and `truncated: true`, and the verdict becomes `"truncated"` rather
  than `"data-only"` - a scanned-and-clean claim is impossible to state
  honestly over a population that was only partly read. A real finding inside
  the scanned window still reports as `"instruction-shaped-content"`;
  truncation never softens a positive hit. `cmd_untrusted` now exits nonzero on
  either condition, not just on a finding.

  The default cap moves from 400 to 2048: this repository's own walk currently
  returns 592 candidates, and 2048 is the next power of two at or above 2x
  that, giving headroom before the gap reopens. The cap itself stays - an
  unbounded walk is worse - but hitting it is loud now, not silent.
- Non-git context ranking no longer depends on copy/checkout timing, within
  the non-git mode. `godmode_corpus.rank`'s freshness ordering fell back to
  raw filesystem mtime for a project with no `.git` directory - mtime there
  is assigned by whatever copied or checked the files out, not by their
  content, so two copies of an identical non-git project could disagree on
  file order purely from copy timing (`tests/test_gate_falsifiability`'s own
  then-git-stripped project copy surfaced a `ranking-changed` verdict against
  the pinned `evals/fixtures/ranking.json` snapshot, which was investigated
  further and turned out to be a *cross-mode* mismatch - see below - not this
  within-mode one). Non-git freshness ordering now degrades to a
  deterministic path sort - the same secondary key the git-log fix already
  uses for ties - instead of comparing mtime magnitudes across files; mtime
  itself remains the freshness value `_freshness_stamp` returns for a
  non-git/untracked path (unchanged). A new test constructs two non-git
  copies with deliberately shuffled mtimes and asserts identical ranking.

  Scope: this closes copy/checkout-timing drift *within* the non-git mode
  only. Path sort and the companion git-log commit-time instrument (see
  `ranking-checkout-order.fixed.md`) are not promised to agree with each
  other on tie order for the same content, so a ranking computed without
  `.git` is not guaranteed to match one computed with it. A snapshot must be
  generated and compared in the same mode it will be evaluated in - see
  `godmode_corpus.rank`'s docstring for the cross-mode boundary. The
  falsifiability harness now keeps `.git` in its project copy so it evaluates
  in the same mode `evals/fixtures/ranking.json` was generated in.
- Context ranking within a git checkout no longer depends on checkout order.
  `godmode_corpus.rank`'s freshness tie-break read filesystem mtime, which
  `git clone`/`git checkout` do not preserve from commit time - two clones of
  the identical commit could disagree on file order, and this task's own
  `evals/fixtures/ranking.json` update exposed the fragility (a live
  fresh-clone reproduction found `ranking-changed` even with a charter-stable
  snapshot). Freshness for a git-tracked project now reads the file's last
  commit timestamp via `git log`, which is part of the commit object every
  clone already has and so agrees regardless of checkout order; non-git
  projects are unaffected (mtime remains correct there, since there is no
  separate checkout step to reorder against). A new test constructs a git
  fixture where on-disk mtime order is the exact opposite of commit order and
  asserts ranking is unaffected.

  Scope: this closes checkout-order drift *within* the git-tracked mode only.
  It does not claim, and does not make true, that a git-mode ranking agrees
  with a non-git-mode ranking of the same content - git-log commit time and
  the non-git path-sort fallback (see the companion
  `non-git-ranking-order.fixed.md` fragment) are different instruments, free
  to order equal-relevance ties differently. A snapshot must still be
  generated and compared in the same mode; see `godmode_corpus.rank`'s
  docstring for the cross-mode boundary.
- `godmode roi` now counts real denials. `godmode_roi.roi_report` folded only
  `kind="action"` records carrying `data.roi_event == "gate:denied"` into
  `gate.denied` - a convention no shipped writer has ever emitted a record
  for. `godmode_session_hook.py` has, since the stage-from-refusal unit,
  written a real `kind="refusal"` record at every R5 deny (`stage_from_refusal`
  reads them back the same way), and `roi` never read that kind at all: this
  repo's own archive holds hundreds of real refusals, all reported as
  `gate.denied=0`. `gate.denied` now folds `kind="refusal"` records
  unconditionally - every refusal record IS a denial, since the hook's `ask`
  branch never appends one - alongside the pre-existing `action`/`roi_event`
  convention, which stays as an additional source; the two are disjoint by
  kind, so no dedupe is needed between them.

## [0.2.11] - 2026-08-15

### Added

- Ten new detectors and three hardened surfaces for evidence discipline:

  - `evidence_pipe_advisory` (sentinel + hook): a verdict-bearing test/gate run piped through a truncating filter is advised against before it destroys its own evidence.
  - `scripted-source-edit` category (sentinel): `sed -i`/`perl -i`/`awk -i inplace` named and asked about instead of failing closed as unclassified.
  - Guard-erosion monitors (integrity): `assertion-free-test`, `silent-catch-in-test`, `fixed-slice-anchor` join the guard-quality pass, population-validated against this repo's own suite.
  - Mistake detectors M19-M22 (mistakes): `carried-status-unverified` (a pending list is not evidence), `remedy-on-hypothesis` (no fix built on an unconfirmed root), `absence-without-control` (an absence claim needs a control probe), `class-claim-single-file` (an "every caller" fix that diffs one file cites its sweep or narrows its claim).
  - Markdown normalisation before every prose matcher (mistakes): models bold exactly the keywords a matcher anchors on.
  - `guard_citations_resolve` (reconcile): guard-bearing records with dead or absent file citations are reported in both drift directions.
  - `upstream_verdicts` (parity): a version-range bump closes only when every enumerated item carries an import verdict AND a behaviour verdict, confirmed-* with its proving line.
  - Push disclosure (sentinel): `git push` names the push-triggered workflows it would fire, because a push to a deploy-wired branch is a deploy action.
  - Overwrite disclosure (sentinel): a declared Write onto an existing filename names the overwrite instead of implying a blank slate.
  - Truncation-honest compression (compress): a subject the cap clipped carries `subject_truncated_at` in its mask, ending the short-record/shortened-record ambiguity the module's own docstring condemns.
- The evidence-prefix vocabulary the M18-M22 detectors read (searched:, control:, second:, scanned:, population:) is taught where operators and agents actually look: `claim --help` epilog (with a worked example), the investigation skill's new "Absence protocol" section, and the governance skill's new "Absorption verdicts" section - a detector whose input convention nobody knows is a dead gate.

  Researching this surfaced a real bug the docs would otherwise have shipped false: `_citation_resolves`'s fallback was a bare `return False`, so citing `searched:`/`control:`/`second:` - the exact vocabulary now being taught - silently downgraded a `--grade verified` claim to `hypothesis`, punishing the evidence discipline the detectors exist to reward. Fixed the same way `doc:`/`url:` already work (resolves as a declared citation, same plausibility floor).

  Also documented honestly rather than pretended: `godmode mistakes`' absence detectors (M18/M21) and the claim-grading pipeline's own stricter absence gate (`_probed_twice`/`_cites_a_search`, which needs two distinct `cmd:` citations) are two separate, unintegrated mechanisms - citing `control:`/`second:` satisfies the former, not the latter. And `upstream_verdicts` (the dual-verdict absorption reader) has no CLI verb writing its record shape yet - `remember --kind decision` stores one free-text value, not two separate verdict fields. Both gaps are named in the skill docs, not silently implied solved.
- A stdlib-only fast gate (`hooks/godmode_gate_fast.py`) now sits in front of the
  full pre-tool hook. It answers exactly one question - is this command's head
  on a vetted, conservative read-only floor (`hooks/gate_table.json`), with no
  redirect and no `-exec`/`-delete` - and only ever returns `allow` (skip the
  full hook, silently, no archive I/O) or `escalate` (run the full hook,
  unchanged, output and exit code mirrored verbatim). Every ambiguous or
  malformed input escalates; nothing is ever guessed into an allow. The
  equivalence held against the 142-command real-denial corpus is one-directional
  by design: every command the fast gate allows, the full sentinel also allows -
  never the converse - so the fast path stays correct as the full classifier
  continues to change under it.

  `hooks/gate_table.json` ships as a PROVISIONAL, hand-built fixture (Task 5's
  generated decision table replaces its contents, not its shape): the floor
  holds only the host-parity read-only set named for this plan (`git
  status/log/diff/show/branch/ls-files/rev-parse/rev-list/remote -v/shortlog/
  describe/blame` plus `ls/cat/head/tail/wc/grep/rg/find/pwd/which/echo/sort/
  uniq/cut/file/stat/du/df`) - one deliberate omission from that list: `tr` is
  excluded because the full sentinel does not yet recognise a bare `tr` as
  read-only (a stream-tool gap this same plan charters a later task to close),
  so including it here would let the fast gate allow what the full hook still
  asks about. `git branch` and `git remote -v` require an exact match with no
  trailing token - both are the one shape on this floor where a bare positional
  argument, not a flag, performs a real mutation (branch create/delete/rename).

  `hooks/hooks.json`'s `PreToolUse` command now points at the fast gate
  (`godmode_gate_fast.py`, no arguments) with its timeout dropped from 10s to 3s;
  `SessionStart`/`UserPromptSubmit` are unchanged.

  Measured on this machine (`git status`, 7-spawn median, matching
  `scripts/dev/hook-probe.ps1`'s own methodology): fast path 196ms vs full hook
  542.7ms - a bare `python -c "pass"` spawn alone measures 102ms here, so
  interpreter-startup overhead dominates both numbers on Windows and the fast
  gate's own logic adds roughly 94ms of that 196ms, not the full hook's several
  hundred. The in-process verdict itself is far cheaper still: 1000 calls to
  `fast_verdict` complete in under 1 second (well over 1000/sec), and the allow
  path opens zero files (proven by an instrumented `open()` count in
  `tests/test_gate_fast.py`). The escalate path (fast gate spawns the full hook
  as a second process) measured 441.3ms median for `git push --force`, 7-spawn
  median - comfortably inside the 3s `hooks.json` timeout even with the extra
  spawn.

  **Fix round 1 (post-review):** two Critical findings, both live-reproduced
  fast-allows of a full-sentinel refusal/ask, both fixed and table-driven so
  Task 5's generator can own the values: (1) the `find` mutation-flag check
  covered only `-exec`/`-delete`, missing `-execdir`/`-ok`/`-okdir` from
  `godmode_sentinel._FIND_MUTATION`'s own five-flag set - now read from
  `gate_table.json["find_mutation_flags"]`, with a drift-guard test parsing
  `_FIND_MUTATION`'s compiled regex directly so a sixth flag added there later
  fails this suite instead of silently reopening the gap; (2) `git log/diff/show
  --output=<file>` (and the equivalent bare `-o`/`--output <file>` forms) wrote
  a file with no shell redirect involved, invisible to the fast gate's
  redirect check - now blocked by a per-phrase `gate_table.json["flag_denylist"]`
  check, while ordinary formatting flags (`--oneline`, `--stat`, a trailing
  pathspec) stay fast-allowed. **Note:** the full sentinel's own `--output=`
  gap this exposed is real and unfixed by this change (the fast gate now
  refuses to fast-allow it, but the full hook it escalates to still classifies
  it R0 today) - that gap is being closed separately in the sentinel lane, not
  by this task.
- `hooks/gate_table.json` is now generated, not hand-built: a new
  `scripts/dev/build_decision_table.py` reads `godmode_sentinel.py`'s own vocab
  tables - `DB_CLIENTS`, `_FIND_MUTATION`'s compiled flag alternation,
  `_OUTPUT_FLAGS_BY_HEAD`'s git write-flag entry - and re-verifies every floor
  phrase, read head, git-ask/git-refuse candidate, and mutation head against
  `classify_action` at generation time, so a sentinel change that moves one of
  them to a different tier breaks the build instead of shipping a table that
  silently disagrees with the classifier it was built from. `generated_from`
  is a 12-hex sha256 prefix of `godmode_sentinel.py`'s own bytes;
  `tests/test_gate_parity.py` asserts regenerating the table (`--stdout`)
  reproduces the checked-in file exactly, plus a plant test proving that
  check would actually fail on a dropped floor entry.

  The provisional table's one deliberate omission is reversed: `tr` was left
  off the floor because the sentinel did not yet classify a bare `tr` as
  read-only when that fixture was hand-built. Re-verified live against
  today's sentinel (`classify_action("tr a b")` is R0), `tr` now belongs on
  the floor and the fast gate fast-allows it like every other read head
  (`tests/test_gate_fast.py::KnownShapes::test_bare_tr_is_on_the_floor`).

  `git_ask`/`git_refuse` and `mutation_heads` are populated for the first
  time - curated candidate lists, each classified through `classify_action` at
  build time and asserted into the bucket its own verdict names, rather than
  retyped by hand disconnected from the classifier.

  Deferred-minor fix, red-first: `hooks/godmode_gate_fast.py`'s `flag_denylist`
  matching compared each trailing token to a denylisted flag by exact string
  (after stripping any `=value`), which caught `-o /tmp/x` and `-o=x` but not
  git's own glued short-flag spelling - `git log -o/tmp/x`, one token, no
  separator at all - fast-allowing a real, unrecorded write. A short
  (single-dash, single-character) denylisted flag is now prefix-matched
  against each trailing token as well as compared for equality; a long flag
  (`--output`) is never prefix-matched, since gluing a value onto it with no
  `=` is not a form git itself accepts.
- Task premise checked and found not to hold, per the plan's own "read first" step: godmode_bindings.py declares packaging/marketplace metadata only (name, version, license, author) - it has no per-host HARD/SOFT/UNAVAILABLE control concept to compare for drift. The real control logic (`host_capabilities()`) computes ONE shared table from environment facts (GODMODE_PRETOOL_GATE, GODMODE_MODEL, stdin TTY), never from the host label, and is never independently duplicated per host - so cross-host control "parity" holds by construction, not by convention that could drift, and a comparison test would have been vacuous.

  Built instead: tests locking in the actual guarantee (the control table is identical across claude/codex/grok/any host label) and the actual variance (tool_call_interception genuinely varies, but by GODMODE_PRETOOL_GATE, never by which host string is set) - plus a guard that the packaged host set stays exactly {claude, codex, grok}, so a fourth host prompts re-examining this premise rather than silently assuming it still holds.
- `godmode init --detect` writes a starter charter from what a repo already proves about itself, instead of leaving a new project staring at an empty one.

  It reads manifests (`package.json` scripts, `pyproject.toml`, `go.mod`, `Cargo.toml`), CI workflow `run:` lines, lint/format configs, `.gitignore` build markers, a migrations directory, and the default branch - all pure reads, stdlib-only, capped at 400 files with the cap always reported. Every candidate it writes is SOFT with its provenance named inline (`(detected: package.json scripts.test)`); the emitter hard-refuses to write anything else, because a wrong guess must never become a blocking gate uninspected - promotion stays a human decision made in the charter document itself.

  Tighten-only: a project with an existing authority document gets a report of detected candidates and nothing is overwritten. A repo with no signal at all still gets an honest minimal stub instead of silence.
- `godmode init --roles` scaffolds one purpose-line stub per genuinely unbound authority role (checklist, decisions, invariants, inventory, lessons, operating-guide, operator-profile, sprint-truth, state), never overwrites an existing file, and skips glob-shaped candidate patterns rather than guessing a filename.

  Fixed a pre-existing bug found while building this: `assess`'s `missing_roles` read a role's candidate patterns that failed to match as if they meant the role itself was unbound - `operating-guide` binds fine through GODMODE.md while its other three candidates (OPERATING-GUIDE.md/AGENTS.md/CLAUDE.md) all fail to match, and the old computation still listed it as missing. `missing_roles` now subtracts roles that have at least one binding; `init --roles` needed the correct set or it would have scaffolded a role that already has a home.
- `godmode guide` - a one-page, ≤60-line orientation (five day-one commands, what runs silently vs asks vs needs the password, where state lives) printed directly rather than routed through the CommandResult/JSON pipeline every data-bearing command uses, since it names nothing about any specific project. `godmode --help` now says "Start here: godmode guide" instead of opening on eighty flat subcommands with no entry point. `init`'s JSON payload gains a `next` field (inspect / resume / guide) for the ordinary case - kept inside the existing JSON contract, unlike guide, because init's output is real per-project data a caller may parse.
- `assess` reports `charter.hard_unplanted`: every HARD rule with no `plant`-proven attestation on record, archive-wide (not session-scoped, unlike `gate()`'s per-session attested_rule_ids - this is a lifetime fact about whether the guard mechanism has ever been observed catching a violation). Matches `plant_and_observe`'s real shape: an attestation with subject `guard:<name>`, status "ran" only when the green-red-green sequence proved out, `data.rule_ids` naming which HARD rules it covers. A "blocked" plant (never went red, or didn't return to green) does not clear a rule - proven with a negative-control test.

  Honest, not silently closed: this repo's own 5 HARD rules are all currently `hard_unplanted` (verified live via `godmode assess`). Closing that gap means planting each - a genuine file+command+violation per rule - which is separate, larger work than reporting the gap; left as a named follow-up rather than done hastily or hidden.
- Two formerly host-only failure scenarios are staged locally and counted (21 -> 23 caught, NEEDS_A_HOST 4 -> 2): `tool-call-interception` drives `hooks/godmode_session_hook.py` as a real subprocess with a genuine PreToolUse-shaped payload (the same entrypoint this project's own hook-latency work drove directly all session) and checks its printed decision, not an internal function's return value; `concurrent-agent-collision` races 5 threads against one archive and proves the chain stays valid (Chronicle's write_lock exists exactly for this). Neither actually needed a live host - the scenario file had just never driven the real entrypoint instead of the function it wraps.

  Both carry their own negative control: the pre-tool boundary swapped for a stub that never refuses (correctly reports not-caught), and write_lock disabled (correctly corrupts the chain and reports not-caught with "sequence is not contiguous"). The remaining 2 host-only scenarios (opaque-model-egress, cross-agent-resume) stay named rather than counted.

  Found and fixed during this work: the collision scenario's first draft conflated two different properties - chain INTEGRITY (what write_lock actually guarantees) with every writer completing within a 5s lock timeout under 10-way contention (an unrelated liveness property that legitimately degrades under real system load, and did - one CI-adjacent run genuinely saw a writer back off). Reduced to 5 threads and asserted on chain validity alone; a writer correctly backing off under contention is the lock working as designed, not a collision. The negative control (disabled lock -> real corruption) still catches the actual defect class this scenario exists for.
- scripts/dev/run-suite.ps1 shards the unittest suite across 4 parallel PowerShell jobs, each writing its own full log file (never piped through a filter, per the evidence-pipe rule). Verified against the serial baseline (939 tests, exact match, no silent drops) and negative-control proven: a planted failing test in one shard correctly produced exit 1 and VERDICT=FAILED naming the right shard, then was reverted.

### Changed

- resolve_anchor() no longer shells to git six times on every call (rev-parse --show-toplevel, rev-parse --git-common-dir, branch --show-current, rev-parse HEAD, remote, remote get-url): the result is cached keyed on the git reflog's (.git/logs/HEAD) identity (mtime_ns, size) - the file that reliably appends on both a commit AND a checkout, unlike .git/HEAD itself which measurably does NOT change across commits on the same branch (verified empirically before choosing the key). A commit, checkout, or branch switch invalidates the cache on the very next call; no TTL guessed. Falls back to .git/HEAD identity when no reflog exists (fresh repo before its first commit). Handles worktrees by following the `gitdir:` indirection file. Named ceiling: `remote_hashes` can go stale between a `git remote add` and the next commit/checkout, since remote changes don't touch the reflog - narrower and rarer than the branch/head class this cache targets.

  Measured: hook median 700.1ms -> 295-333ms (scripts/dev/hook-probe.ps1, two clean runs after discarding one 851ms outlier attributable to OS-level noise, not this change - cProfile of the same invocation shows zero resolve_anchor/git subprocess calls post-fix, versus six pre-fix). This was the dominant cost the original P1 import-deferral estimate missed entirely - found by profiling the correctly-invoked hook after the initial baseline turned out to measure an argparse error path (the hook's required positional `event` argument was omitted from every prior measurement).
- Capability tokens default to 300s (180 measured expiring under an agent's ordinary retry latency - a slow tool round-trip plus one retry could outlast it; 300 stays one short conversation, not an open-ended window). `authorize setup`/`issue` carry real help text (both `authorize --help`'s subcommand listing and their own standalone `--help`, which needed `description=` too since `help=` alone only reaches the parent listing). The irreversible-operation refusal now tells hosted-session users they can type the staging command with a leading `!` to run it from the prompt without leaving the conversation.

  A pre-existing test hardcoded the old TTL as a bare literal (180); updated to assert against `_DEFAULT_TTL_SECONDS` so a future deliberate tune can't silently desync the test from what ships.
- `godmode charter --review-advisory RULE_ID --reason "..."` records why a mechanical check cannot decide an ADVISORY rule, as a `decision` record (subject `charter-advisory-reviewed:<rule-id>`). `assess` cross-references every currently-compiled ADVISORY rule against reviewed decisions and reports `advisory_unexplained` - a rule with no enforcement is a wish; one with no enforcement AND no stated reason is a wish nobody has examined.

  Inspecting this repo's own 3 advisory rules (checkable_share 0.625) found they are sentence-fragment artifacts: GODMODE.md's descriptive prose wraps mid-sentence, and the line-based directive scanner catches half-sentences containing words like "require"/"never"/"before" that name no real directive. Manufacturing a detection shape for them would be false enforcement - the charter module's own docstring warns against exactly this. All three are now reviewed via the new command (dogfooded against the real repo, not just tested in isolation); `advisory_unexplained` is `[]` here. `checkable_share` stays 0.625 by design - reviewing names the reason, it does not fake a check.
- Archive reads are memoized in-process: `Chronicle.read_events()` caches the parsed record list keyed on a hash of every event file's (mtime_ns, size) - not just the newest file, which a tamper-evidence test caught directly (mutating an OLDER record's bytes in place left the newest file and record count unchanged, so a newest-only key would have let `verify()` pass on tampered disk content). `accepted_keys()` gets its own cache keyed on the config file's own stat, fixing a pre-existing inefficiency the events-cache work exposed: `verify()` calls `accepted_keys()` once PER RECORD, and an uncached read re-parsed the same rarely-changing config file that many times per verify pass - traced live at 384 total `_read_json` calls from one hook invocation on a 96-record archive (288 of them redundant config re-reads, only 96 real event-file reads). `watchdog()` now windows its attestation scan to the current session's own records (found via the `session` record whose hash produced the session id) instead of the last 1000 attestations across every session this archive has ever held.

  Hash-chain re-verification itself is deliberately NOT cached - `verify()` always re-checks every record's hash on every call, cache hit or miss, because that is the tamper-evidence guarantee the whole data structure exists for. The cache only removes redundant disk reads and JSON parsing, never the integrity check.

  Measured at this repo's current size (96 records), the net wall-clock effect is within noise (~295-390ms across repeated hook-probe runs, matching the anchor-cache commit's numbers). The real win scales with archive size and call repetition, both verified directly rather than assumed: at a synthetic 1000-record archive, the identity check costs 69.9ms against a 327.4ms full parse (~4.7x cheaper), and three repeated `read_events()` calls - the exact pattern one `pre-action` hook invocation performs (latest_session, watchdog's window lookup, watchdog's own scan) - cost 719ms warm versus an estimated ~1371ms cold, a ~1.9x speedup that widens as records accumulate.
- `git add`/`git commit` now ask instead of running silently. Both were left unprotected on the reasoning that a commit is local and reversible, and gating it made committing impossible in a session where the gate could only ever refuse a protected call outright - no host tool call carries a field a capability could travel in. That premise stopped being true once the host started asking rather than only refusing: asking *is* an in-session approval, and the sibling worktree operations that carry the same reversibility (`checkout --`, `restore`, `mv`, `stash`, `switch`) already asked. `add`/`commit` sitting on the allowed side of that line was never a decision, just the one git rule this classifier had not yet been given (Controller Ruling 1).

  `git checkout -b <branch>` (and `-B`) no longer asks. It matched the same pattern as `checkout --`/pathspec history-rewriting forms, which is the wrong shape for it: creating a local branch discards nothing and leaves the machine no differently than `git branch <name>` already does. Category `git-branch-create`, R1 - the same tier ordinary local computation sits at.

  Protected-path reads (`ls`/`cat`/`grep`/`head`/`tail`/`wc`/`stat`/`file`/`find` of a directory inside this gate's own runtime) were already R0 - confirmed with regression tests (`tests/test_sentinel_policy.py`) rather than left as an accident of `_SAFE_SHELL_READS` not looking at arguments at all, since a corpus of real denials had already found zero surviving instances of this failing.
- Hook hot path defers cold imports to the branches that actually use them: CapabilityBroker (secrets/getpass/hmac), the fence module (design_verdict/fence_verdict), and six event-scoped modules (charter, corpus, drift's compare, lens, requests, contribution) that `pre-action` never touches but were previously imported unconditionally on every tool call. Also moved `godmode_anchor`'s `secrets` import (which transitively pulls in `hmac`) into its once-per-device salt-creation path. PreToolUse median latency 807.5ms -> 700.1ms measured by scripts/dev/hook-probe.ps1 (7-spawn median, corrected probe — the original baseline had omitted the hook's required positional `event` argument and was timing an argparse-error path, not real hook logic).

### Fixed

- Two real gaps found by an adversarial "test the detectors on novel phrasing, not their own fixtures" pass, both fixed:

  - `evidence_pipe_advisory`'s verdict-runner regex covered `godmode verify/gates/attest/precheck` but missed `selftest/scenarios/mistakes/assess` - every one of them equally verdict-bearing and equally truncatable by the same pipe pattern (`godmode selftest | Select-Object -Last 5` sailed through unflagged). All four added; non-verdict subcommands (`capabilities`, `inspect`) confirmed to stay clean.
  - The M18/M21 absence-claim detectors' `_ABSENCE` regex covered "nothing found" but not the reversed word order - "the search turned up nothing", "the query came back empty", "the scan yielded nothing" all passed through both detectors completely undetected. Extended the pattern; verified against three realistic phrasings plus two negative controls.

  Also probed and found NOT gaps, documented as known ceilings rather than silently fixed: a DROP TABLE hidden inside a backtick command substitution (`psql -c \`echo 'DROP TABLE orders'\``) is under-classified as `unclassified-mutation` R3 instead of `database-mutation` R5, because the classifier evaluates a substitution's own behavior (echoing text) rather than simulating how its output is consumed by the outer command - it still fails closed (asks before running), it just doesn't earn the stronger tier. The same shape applies to git aliases renaming a destructive operation to an arbitrary word. Both are inherent limits of static-regex classification without executing or parsing `.git/config`, not regressions from today's work.
- Three more gaps found by an adversarial pass over detector families the previous sweep had not touched (prompt injection, secret shapes, environment classification), all fixed with negative controls and population checks:

  - **Environment classifier read a production database as development.** `\bproduction\b` does not match `production_backup` - `_` is a word character, so no boundary exists between them - and `localhost:5432/production_backup` therefore classified as *development*, the one tier where `mutation_allowed_without_capability` is True. A production database reachable on localhost was mutable without a capability, through a hostname anyone might really use. Boundaries widened to any non-alphanumeric edge; `prd` added as a real-world abbreviation. The negative that makes this safe rather than merely stricter is pinned: `my-product-catalog` must never read as production just because `product` starts with `prod`.

  - **Two secret scanners disagreed about what a secret is.** The sentinel's archive gate (blocks credential-shaped payloads from being stored) and the egress staged-file scan (names the kind, masks the value) each covered shapes the other missed - connection strings caught by one, `ghp_`/`sk-` prefixes by the other, JWTs and Slack tokens by neither. Both rule sets extended to a common set, and a new seam test pins every canonical shape against BOTH scanners so they cannot silently diverge again.

  - **Injection detection missed three real shapes**: a possessive override ("disregard *your* earlier guidance" - `earlier` was absent from the alternation entirely), a verification bypass whose object was the test suite rather than a "gate", and a decode-then-execute frame carrying its instruction as an encoded payload. All three added.

  The gate-bypass widening initially cost a false positive on this repo's own README - the row *describing* the monitor that blocks skips read as an instruction to skip - caught by a population sweep against the shipped docs (0 findings before, 1 after). Bounded the verb-to-object distance so the verb must govern the object rather than merely share a line with it; population sweep back to 0.

  Also probed and found sound, no changes needed: the capability broker refused all four attacks (replay of a spent token, tampered payload with an intact signature, a token spent on a different operation, a token minted in another project); archive integrity refused both a middle-record hash tamper and a truncated record at 400 records.
- `classify_action` no longer lets argument text convict a command. Two real false-positive shapes from a 50-session denial harvest, both a vocabulary check searching the whole line instead of the command's own words:

  - A `>`/`>>` found anywhere in the raw text was read as a shell redirect even when the only `>` on the line sat inside a quoted argument - `node -e "console.log(1 >>> 2)"` (a JS bitshift) and `node -e "const f = l=>l.trim()"` (an arrow function) both misread as an empty-target write outside the working tree, refusing an ordinary local computation. Redirect detection is now gated on a quote-aware scan first: an operator is only trusted when it survives the same quote-blanking already used for the mutation patterns.
  - A bare word inside an unquoted file path argument - `docs/RELEASE-CHECKLIST.md` read by `grep`/`tail` - matched the `release-or-external-write` vocabulary the same as if it named the verb. Vocabulary matching now runs on each segment's command-position text: the head (kept even when it is a relative path, so `./deploy.sh` is still a deploy) plus every word after it that is not itself path-shaped.

  New public interface for later gate work: `split_segments(operation) -> list[Segment]`, where `Segment` carries `head`, `subcommand`, `tokens` (quoted text excluded) and `has_redirect` per piece of a compound command - Tasks 3-4 build the remaining fixes (unknown-command vocabulary, stream-tool safe reads, git-subcommand scoping, protected-path reads) on top of this rather than re-deriving tokenization.

  Also fixed, found first and unblocking this: the docs linter's file walk did not honor `.gitignore`, so scratch orchestration reports under a gitignored directory were held to the shipped-docs standard and could fail `tests.test_docs_lint` for reasons unrelated to any shipped document.
- `classify_action` no longer refuses a command for the sole reason that it has no vocabulary entry. A 50-session denial corpus showed the fail-closed `unclassified-mutation` bucket - meant for a genuinely unknown state - catching mostly harmless, unrecognised commands (`rev`, `cp` into the tree, a `curl`/`Invoke-WebRequest` status probe, bare `sed`/`tr` in a pipeline, several PowerShell constructs) alongside the rare real gap. A segment with no recognised vocabulary and no evidence it mutates anything - no real redirect, no named write flag - now reads at R0 instead of asking or refusing for ignorance.

  "No evidence" is narrower than "unrecognised," on purpose:

  - A real redirect, or a quote left open (which blanks everything after it, including a mutation verb that was sitting there in the original text - a malformed-input case a fuzzer found), still asks - named `unknown-command`, reason names the head, never the old uninformative `unclassified-mutation`.
  - `git` and `gh` already have enumerated safe/read forms; an invocation that misses all of them stays on the ask side rather than defaulting open just because this particular subcommand went unnamed.
  - `curl`/`wget`/`Invoke-WebRequest`/`Invoke-RestMethod` can send data out, not just fetch it in, so they stay named exceptions - a narrow, explicit status-probe shape (discarded output, no method/body/output-file flags) reads; every other form still asks. `ssh`/`scp`/`rsync`/`sftp`/`ftp`/`nc`/`ncat`/`telnet` join the same family, unconditionally - a remote shell or a remote copy is not a local read of anything.
  - `export`/`unset` of a variable that changes what runs (`PATH`, `LD_PRELOAD`, ...) was already excluded from the safe-bookkeeping allowance; it now stays excluded from the open default too, rather than falling through it.
  - `bash -c`/`sh -c`/`eval` hand an interpreter a whole script as one opaque argument, and `ForEach-Object { ... }` runs whatever its block contains - both keep asking regardless of how harmless a specific instance's content looks, the same principle `find -exec`/`-delete` already uses.

  Also scoped, in the same pass: a database client's own head (`psql`, `mysql`, `sqlite3`, `redis-cli`, `mongosh`, `mariadb`, `pg_dump`, `pg_restore`) is now protected on invocation alone, not only when a migration/reset verb is visible - the verb is usually inside a quoted statement (`psql -c 'drop table users'`), which blanks it before any verb-anchored pattern runs.

  Found while widening this: `_SAFE_INSPECTION_PATTERNS`/`_GIT_LOCAL_CHANGE` matched on a command's own verb and returned before anything looked at its arguments, so a real `>` redirect past one of them was never inspected (`git log --oneline > /etc/hosts` classified as a plain read) - and the same was true of a per-command output-file flag doing the redirect's job without spelling the operator (`git log --output=/tmp/x`, `sort -o out.txt`). Both are now judged by their target the same way an ordinary redirect already is, via a small per-command flag table (`_OUTPUT_FLAGS_BY_HEAD`) rather than a one-off regex per command. `find -execdir`/`-ok`/`-okdir` were already covered by the existing `_FIND_MUTATION` pattern; pinned with tests rather than left unverified.

## [0.2.10] - 2026-08-11

### Added

- A statement about a population, made from a sample, that omits the sample.

  Third member of the family the previous two entries belong to — a value correct
  in its own frame and wrong in the reader's — and the one with the widest reach,
  because it needs no second system to go wrong in. One query with a filter and a
  limit is enough.

  Two shapes, one remedy, so one check.

  An absence. "Nothing found", "no evidence", "it is not referenced" — true of the
  search that ran, asserted about the world. Two searches that miss inside a
  document holding the answer produce exactly that sentence, and it reads as a
  conclusion rather than as the description of a search. An absence claim needs
  the search that would have disproved it, which is the standard `precheck`
  already holds itself to when it reports where it looked; nothing held the agent
  to it.

  A count. A bare total carries its query's filter and cap invisibly. A number
  from a call with a category filter and a silent limit is not the log, it is a
  slice of one, and nothing about the number says so — the reader cannot tell a
  complete count from a truncated one. Stating the denominator clears it, and so
  does naming what was examined in evidence.

  `precheck` gained the third question. It answered "was this already built" from
  the tree and "was this already refused" from decisions and removals, and had
  nothing for the case in between: a thing already FILED and still open. An
  incident, a standing obligation, an ask nobody closed — matched neither reader
  and stayed invisible, so an open item describing the same symptom as the case
  in hand could be listed twice in one session and never connected to it. Open
  items are now reported first, because they carry what is already known.

  Its own truncated list now says it is truncated. The symbol list was capped at
  ten and silent about it, which is the defect this release reports twice
  elsewhere; it does not get to commit it.

  And the guard-breadth check no longer reports a ruling that was later corrected.
  The archive is append-only, so a record cannot go back and mark itself
  superseded — the correction carries the status and the record being corrected
  never does. Reading each record's own status settled nothing, so using the
  documented lifecycle produced a permanent finding. A later settlement on the
  same subject now retires the earlier ruling; an earlier one does not pre-clear
  a ruling written after it. Found by writing a lesson, correcting it, and
  watching the original keep firing.
- An analysis that reverses every pass, and the sentence that carries it.

  The failure this answers is not being wrong once. It is being wrong
  *unstably*: a root cause is published as soon as a story fits, the next pass
  reads one more file and overturns both the root and the fix, and the reader is
  left holding a moving target with no pass safe to act on. Every reversal was
  purchasable in advance by reading code that was already there.

  Two checks, neither needing anything the agent is not already doing.

  A named root cause must cite a line of the program it indicts. A mechanism that
  explains the symptom is a hypothesis; it becomes a finding when a file says so.
  The check reads the vocabulary of attribution rather than description, because
  a claim that reports an observation is not making this mistake. Citing another
  record does not satisfy it — pointing at a prior claim is how an unexamined
  theory travels between passes, gaining standing at every hop without ever
  touching the program. Grading the claim `hypothesis` clears it, which is the
  honest alternative and the point.

  The same question answered twice, differently, with neither answer withdrawn.
  Revising an answer is ordinary; revising it silently leaves two live roots for
  one subject and no record of which was abandoned. Two live answers are
  reported, three block — one revision can be an honest correction mid-
  investigation, while a subject on its third live root is not converging, and
  another pass at the same depth will produce a fourth. The remedy is to mark the
  superseded claim, using the lifecycle the contradiction check already reads.

  That word list now has one owner rather than two. Two readers asking whether a
  record is still in force, from two copies of the same four words, is a
  disagreement waiting for a release to expose it.

  What is deliberately not built: nothing counts how many times an answer changed
  inside a single pass. That would need the agent to volunteer its own reversals,
  and an agent that reliably reported them would not be the one this exists for.
- A time quoted to a person without saying which clock it came from.

  Every store this project writes is UTC. Every surface a person reads renders in
  their own zone. Both are internally correct, which is the whole difficulty — a
  bare number copied from one into a sentence about the other is wrong by the
  reader's offset, uniformly, so it survives every consistency check the archive
  already runs and reads as plausible.

  Nothing here could catch it before. Claim binding asks whether a citation
  resolves; the citation resolved, the cited record held the right instant, and
  what went missing was the frame, dropped in transcription. The archive checked
  that a claim was supported and never that it was commensurable with the
  sentence carrying it.

  The check reads records written to be read by a person and reports a wall clock
  with no frame after it — no `UTC`, no `IST`, no offset, and not a duration.
  Blocking on a claim, which is the kind that gets published; reported without
  blocking on a lesson or a decision, because those may legitimately mention a
  schedule and a release refused over a cron expression teaches an operator to
  route around the check.

  Two things it deliberately does not do. It does not convert, because it cannot
  know the reader's zone. And it does not read code, so a bucket keyed on the
  first ten characters of a UTC timestamp is still a UTC day whatever the label
  above it says.

### Fixed

- The changelog gate refused a release for spending its own fragments.

  A fragment is a staging area. The artifact it exists to produce is a CHANGELOG
  entry, and `changelog merge` consumes every fragment to write one. So a commit
  that merges fragments and ships code in the same breath has changed code, has
  recorded the note the gate protects, and carries no fragment — because it spent
  them. The gate read that as an unnoted change and failed the release.

  It was right about the fragments and wrong about the question. What it exists to
  guarantee is that a change is written down, not that a particular staging file
  survives to be counted.

  Splitting a release into two commits avoids this, and this repository had always
  done that by habit. Habit is not a check: a gate that passes only when somebody
  remembers the customary commit order refuses a correct release the first time
  somebody does it in one, and does so in CI, after the push.

  A diff that adds entries to CHANGELOG.md now satisfies the gate. The count is of
  *net* bullets and version headings, not added ones — an edited bullet appears in
  a diff as one addition and one deletion, so counting additions alone would read a
  corrected typo in a released entry as a note for today's code, leaving the gate
  on in name and off in effect. A code change with no note anywhere is refused
  exactly as before.

  The report now names which of the two answers let it through, so a reader seeing
  `satisfied` beside an empty fragment list does not have to guess why.
- A timestamp that had lost its offset was read on two different clocks.

  Every instant this project writes carries `+00:00`. The ones that do not are
  the interesting ones: a record written by hand, or one carried over from a
  schema that stored a bare clock. Two readers disagreed about what such a value
  meant, and neither disagreed loudly.

  The health check crashed on it. `_parse_time` caught `ValueError`, so a
  malformed string returned nothing and the check carried on — but a well-formed
  string with no offset parsed cleanly into a naive instant, and subtracting that
  from an aware one raises `TypeError`, which nothing caught. One unlabelled
  timestamp anywhere in the archive took down the whole context report rather
  than ageing a single baseline wrongly.

  The staleness guard answered wrongly instead, which is worse for being quiet.
  It read the file's modification time on whatever clock the start time carried,
  so an unlabelled start time meant `tz=None` — the host's local clock — while
  the start time itself was meant as UTC. The comparison then ran between two
  different clocks and was wrong by the host's offset. Measured on a `+05:30`
  host: a process started two hours after the newest source reported `stale`, and
  the guard blocked a diagnosis that should have proceeded. West of UTC it fails
  the other way and clears a process that really is dead.

  Neither timestamp was wrong in its own frame, which is exactly why it read as
  plausible and why no self-consistency check could have found it. Both readers
  now pin to UTC, an unlabelled value is documented as UTC where it is parsed
  rather than assumed separately at each call site, and the reported modification
  time states its offset so the next reader cannot repeat the mistake by eye.
- Retiring an invariant was reported as contradicting it.

  The contradiction detector collected every invariant record ever written for a
  subject and called two values a conflict. Retiring an invariant means writing a
  new record, with a new value, carrying a retired status — so using the
  documented lifecycle produced an error by construction, and `doctor` reported
  the archive unhealthy for doing the right thing.

  Found by retiring a real invariant once a release closed the condition it
  described. The record was correct, the retirement was correct, and the health
  check called the pair a defect.

  Records whose status puts them out of force — retired, superseded, withdrawn,
  revoked — no longer take part in the comparison. A value that no longer binds
  cannot contradict one that does.

  Three things deliberately unchanged. Two live invariants that disagree are still
  an error, which is the case the check exists for. A retired record sitting
  beside a live pair does not excuse that pair. And an invariant with no status at
  all still counts as live, because records written before status was recorded
  must keep being checked — exempting them would retire the detector rather than
  the record.

## [0.2.9] - 2026-08-10

### Added

- What depended on this change, and whether anybody dealt with it.

  `atlas affected` already answered "what breaks if this changes". Nothing
  consumed that answer, so it stayed a query somebody had to think to run — and
  the moment worth running it is precisely the moment nobody is thinking about
  it. The same shape as `affected` being a good tool nobody reaches for.

  `godmode atlas closure` turns it around. Given what actually changed — read
  from the working tree by default, because requiring the caller to list what
  they just edited is how the first version ended up unused — it reports the
  files in the blast radius that were *not* themselves touched.

  Findings, never closures: the contract requests and obligations keep. A
  dependent named here is not thereby wrong. It may need updating, or it may be
  genuinely unaffected, and only a person can say which. What must not happen is
  nobody saying either, which is the case that ships broken.

  Answers are bucketed. A test covering the changed code and a module calling it
  need different work done to them, and one flat list hides which is which. The
  graph alone cannot draw that line — a test file imports what it tests like any
  other caller — so the file name corrects the bucket. That is a heuristic in a
  report and never in a refusal: wrong here it costs one mislabelled line, while
  the same guess inside a gate would be a scope that moves on its own.

  Depth 1 by default. A second hop is real but weaker, and a report naming a
  third of the repository is one nobody reads. Symbol ids collapse to file paths,
  which is both the granularity the question is asked at and what turns six
  untouched symbols in one file into one finding rather than six.
- The look of the product, which an agent may not redraw in passing.

  The scope fence is task-scoped: this change may touch these files, and the
  claim expires with the plan. A design boundary is the opposite shape. It
  outlives every plan, nobody re-declares it per task, and what it protects is
  not correctness but a decision somebody made on purpose. So it lives in
  `.godmode-boundaries.json`, and it refuses rather than asks.

  It refuses because a one-key confirmation in the middle of a long run is the
  same keystroke as every other confirmation that session, and that is not
  permission. A frozen surface moves by staged capability or not at all, and the
  refusal quotes the exact `authorize stage` command that moves it.

  **Declared globs enforce; a heuristic only proposes.** `godmode boundaries
  propose-ui` reads the tree and prints candidates for a human to accept, narrow
  or throw away — it never writes the config. Auto-detection as the enforcer
  fails three ways that matter: it freezes a `.tsx` file that is pure server-side
  data loading, it misses a UI change made in a plain route file, and its scope
  moves on its own when somebody adds an import, so yesterday's allowed edit
  becomes today's refusal with no diff to explain it. A gate whose scope moves by
  itself cannot be audited.

  Undeclared enforces nothing — every project that predates this keeps working
  untouched — and `doctor` reports `design_boundary: unconfigured` so the gap
  stays visible. Failing open is correct here; failing open *silently* is how a
  guard that governs nothing goes unnoticed.

  Known ceiling: the boundary is drawn at glob granularity, so a design change
  made inside a file nobody declared — a copy string in a constants file, a route
  table — is not caught. The alternative is semantic diff classification inside a
  gate the host kills at ten seconds.
- The brief names the build that is enforcing it.

  Every version surface here reads the tree: eight of them, the latest tag, and
  the tree a tag points at. None reads the copy that is installed and actually
  refusing tool calls, so there was no answer anywhere to the question that
  decides whether any of this work is running — which build is guarding me.

  The version being developed and the version enforcing are different facts, and
  only the first had checks. An installed plugin leaves no trace in the
  repository it guards, so any gap between the two is silent by construction and
  no warning exists to be missed.

  So the context brief now opens with the version and the filesystem root of the
  runtime that produced it. The root is there because a version cannot tell two
  installs of the same number apart, and the question is which copy this is. It
  sits outside `records`, so the degradation ladder cannot drop the one line that
  explains why every other line might be describing a different build.

  Reporting, not detection. Drift needs something to compare against, and what
  that is depends on the project; naming the number is what was missing, and
  naming it is enough to catch this.
- An ask the agent supplied, told apart from one the operator made.

  The request ledger was built for what a person typed, and quietly accepted what
  the agent decided they meant. Both are worth keeping — an inference that shaped
  the work should be reviewable — but they cannot carry the same standing, because
  waiting on a stated ask is correct behaviour and waiting on an inferred one is
  the agent blocking itself on a question nobody raised.

  Requests now carry `source`: `stated` for everything the prompt hook writes,
  `inferred` for an ask the agent records on the operator's behalf via
  `remember --kind request --source inferred`. The hook path is unchanged and can
  only ever write the truthful value.

  A detector reads the difference. `inferred-ask-blocking` fires when an inferred
  request is still open and nothing — no build, verify, plan, or attestation —
  was recorded after it. That test is deliberately not about whether the guess was
  wrong. An assumption that shapes the work is ordinary and often right; an
  assumption that *stops* the work spends the operator's turn on a question they
  never asked. So the check is whether anything happened afterwards. A checkpoint
  does not count: writing down that you are stuck is not continuing.

  It reports rather than blocks, which is the same contract the rest of the ledger
  keeps — and it is the first detector here that reads a claim about the operator
  rather than one about the repository. The failure is the same either way: an
  inference given the standing of a fact, and then acted on.
- Whether this was already built, and whether it was already refused.

  Two questions asked at the only moment the answers are worth having: before
  the work starts. Both were answered wrong in the session that added them. A
  sentinel allowlist came one command from being rebuilt after two shipped
  releases had already fixed it. A reinvention check designed in an earlier
  session was rediscovered from scratch, because nothing read the record saying
  it had been designed.

  Neither answer was missing. `removal` records why something was deleted,
  decisions record what was rejected and why, and the atlas records what exists.
  The archive held both and nothing consulted either — the same shape as
  `affected` being a good query nobody thought to run.

  `godmode precheck --about "<the task>"` matches on term overlap rather than
  wording, because a request is almost never phrased the way the thing it
  duplicates was phrased. It is a weak test deliberately: a strong one that
  reports nothing is the check that cannot fail, and the cost of over-reporting
  is a line the reader dismisses.

  It reports where it looked and how much it examined. An absence claim needs the
  search that would have disproved it, and a `nothing found` produced by a check
  that examined nothing is worse than no check, because it reads as clearance.

  Findings, never closures. Prior work is a reason to look, not grounds to
  decline: sometimes the earlier rejection was right, and sometimes the
  constraint that drove it has since gone.

  Closures now carry which of the two they were. `already-built` and `refused`
  join the closed statuses, because a plain `closed` covered both outcomes and a
  later precheck reading those records could not tell "we built this" from "we
  decided not to". Existing closures stay closed and read as `unspecified` — a
  migration that reopened old work would be a worse defect than the ambiguity.
- A skill for the answer that did not land.

  Every other surface here governs what the agent does to a repository. This one
  governs what happens when the operator says they cannot follow it — a failure
  this project had no name for, no procedure for, and no way to record.

  `godmode-repair` triggers on the operator's signal rather than the agent's own
  sense that things went well: "be clear", a question already answered asked
  again, "what do you want from me", "what is pending". The last two are named
  specifically, because they mean options were presented where a recommendation
  was owed. An operator asking what is needed from them is reporting that the ask
  was buried, not that they missed it.

  The re-pitch leads with the answer, decides the choices that were offered
  instead of re-offering them, names one next act, and drops the qualifications
  the first version carried — since length is the usual cause, and an answer
  needing a table of contents has already failed.

  The failure is then recorded as a lesson, because what did not land is almost
  never one sentence: it is a shape. Options where a decision was owed. A status
  buried under evidence. The shape is recorded and the exchange is not — the host
  already keeps the transcript, and a second copy is a second thing to leak.

  Explicitly not an apology, and not a re-argument of whether the first answer
  was right. It usually was right and unusable, which are different faults with
  different fixes; restating the reasoning at greater length is the failure
  repeating itself.
- A plan may declare the files it is allowed to edit, and edits outside them stop.

  Everything here answered the question afterwards. `atlas affected` reports a
  blast radius once a symbol is chosen, `inventory diff` reports what moved once
  it has moved, `integrity` reads a diff that already exists. All detection, and
  detection arrives after the edit.

  That is not the question an operator asks when they hand over one section of a
  codebase. They ask that nothing else move, and a report that something else
  moved is the wrong shape of answer.

  So the plan contract takes an optional `editable` field — comma- or
  newline-separated globs — and the pre-tool boundary refuses a `Write`, `Edit`
  or `NotebookEdit` whose target falls outside it. The declaration belongs to the
  change rather than the project, which is why it lives on the contract and
  expires with the plan; a design boundary outlives every plan and belongs
  elsewhere.

  Three deliberate limits. **Undeclared fences nothing**: a fence nobody wrote
  should fence nothing rather than everything, and every project predating this
  must keep working untouched. **It asks rather than refuses outright**: finding
  out that a change touches one more file than expected is ordinary, and a scope
  that could only be widened by rewriting a plan would be abandoned the first
  time it was wrong. **Only an approved plan fences**: an open plan is a
  proposal, and enforcing a proposal would let an agent fence itself in, or out,
  by writing a plan nobody agreed to.

  `src/*.py` and `src/**` stay different claims. `fnmatch` cannot draw that line —
  its `*` crosses separators, so every shallow pattern would quietly widen into
  its whole subtree, and a fence that widens on its own is not a fence.
  `PurePath.full_match` draws it but arrived in 3.13 while CI runs 3.11, so each
  segment is translated instead. Paths are judged in their project-relative form,
  so the same file cannot pass or fail depending on whether the host spelled it
  absolute, relative, or with backslashes — and a path that escapes the project
  is refused whatever the fence says, or `../` would be the way through it.

  The refusal names the exact command that widens the fence, because a refusal
  whose remedy is stale or absent teaches an agent a false model of what is
  possible, and the agent then abandons work it could have completed.
- Two questions asked of a finished change, not of a pending edit.

  `godmode fence audit` checks every changed file against what the plan said it
  would touch. The boundary gate already refuses an edit outside that set, but it
  only sees tools that announce a `file_path` — a shell command that rewrites a
  file in passing, an edit made before the plan was approved, and every change
  made in a session where the plugin was switched off all land in the tree
  unfenced. So the declaration is asked of the result too: "every changed line
  should trace directly to the request", checked against the only
  machine-readable statement of that request this project keeps.

  `godmode fence acceptance` reports completions that cite no evidence, quoting
  the acceptance the approved plan declared. A plan has always stated what done
  looks like and nothing ever compared a completion against it, so `acceptance`
  was a field that got filled in and read by nobody — the same shape as `removal`
  preserving reasons no reader consulted.

  Both are findings, never closures, and both fail quiet rather than loud: with
  no approved plan they report `no-declared-scope` and `no-acceptance-declared`
  rather than an empty result, because an empty result from a check with nothing
  to check against reads as clearance.

  Only completions are graded. Work in progress has not claimed anything yet, and
  reporting it would train the reader to skim the claims that count.

  `godmode atlas seams` adds the third: modules used by exactly one consumer.
  "One adapter means a hypothetical seam. Two adapters means a real one" — a
  single-consumer module may be right, but it is the shape a speculative
  abstraction takes and nothing looked for it. Tests do not count as consumers,
  or every module would look justified; zero consumers is left to `orphans`,
  since a finding two surfaces report is one neither gets fixed for; and
  standard-library imports are excluded, because `import base64` used once is not
  a seam anybody can delete. The deletion test that accompanies the rule — delete
  it and see whether complexity vanishes or reappears across N callers — is not
  computable from an import graph, so it is asked rather than pretended at.

### Fixed

- The gate refused where it should have asked.

  It emitted `deny` and only `deny`, for every protected operation, on the
  reasoning written into its own refusal text: no capability can be attached to a
  host tool call, so there is no in-session approval. The first clause is true.
  The conclusion does not follow, and the documentation says so in one line:

  > `"ask"`: show the permission prompt to the user as normal

  A capability cannot ride along on a tool call. The host has its own
  confirmation channel, and this gate never reached for it — through five
  releases of tightening the refusal and twice rewriting its wording.

  What that cost was reported rather than theorised. Another project running the
  plugin hit `rm probe-tmp.mjs` on a scratch file it had just written,
  `git checkout -- out/`, and `taskkill` on a dev server it had started; each was
  a hard stop, each became a command typed by hand, and that session ended up
  recommending its operator remove the guard entirely. A gate with one way to be
  careful spends the operator's patience on every false positive, and a guard
  nobody keeps switched on protects nothing.

  Protected operations now ask. R5 still refuses: the tier exists for damage no
  later command undoes — a forced push, a hard reset, a dropped table — and a
  one-key confirmation is the wrong shape for those. `authorize stage` remains
  the answer there, and a staged capability is still consumed before any of this
  is reached.

  Two decisions kept their refusal for a different reason. An exceeded ceiling
  and a run of skipped mandated steps carry no risk tier, and the first version
  of this turned both into confirmations — asking a session that has stopped
  being trustworthy to approve itself, which is the failure those signals exist
  to interrupt. They deny explicitly now, whatever the operation would otherwise
  have scored.
- Three checks that reported less than their names promised.

  **`config check` validated a schema table, not the tree.** It iterated the
  files somebody had written a contract for, so `.godmode-docslint.json` — which
  governs the docs linter in this very repository — was never checked. Replacing
  it with unparseable text left the command green: the config still named, still
  loaded by whatever reads it, and silently governing nothing. Discovery is by
  glob now, and a file with no contract must still parse and be an object.

  **Two gates declared themselves unproven and stayed that way.** `config check`
  and `atlas diagnose` both carried "no breaking mutation written yet" in the
  falsification harness — an honest note that nobody was going to act on while it
  read as a documented state rather than a debt. Both have mutations now: a
  config that no longer parses, and a source file the symbol atlas cannot read.
  Writing the second one is what surfaced the first defect above.

  **The census declared a smaller product than ships.** `database`, `obligation`,
  `session` and `request` were present in the archive and absent from the tracked
  surfaces, and the census reported them as `undeclared_kinds` for weeks. That
  field exists precisely so the report cannot quietly describe less than the
  runtime holds. It did its job; nobody read it.
- A word is not a database.

  Reported from another project running the plugin: `git restore out/` refused as
  a **database mutation**. The rule matched `drop`, `truncate`, `migrate`,
  `migration`, `rollback` and `restore` as bare words, anywhere they appeared.

  Reproducing it found worse. `cat docs/migrate-notes.md` and
  `grep -rn rollback src/` were refused the same way — a file read and a search,
  reported as schema changes. Meanwhile the genuine article escaped: the SQL in
  `psql -c 'DROP TABLE orders'` is quoted, quoted spans are blanked before these
  patterns run, and it fell through to unclassified. The rule refused prose and
  missed the statement.

  It is anchored to a database now: SQL that names what it operates on
  (`DROP TABLE`, `DELETE FROM`, `ALTER TABLE`), or a named migration tool running
  a migration. A verb on its own means nothing, because `migrate` is also a word
  in a filename.

  `git restore` discards uncommitted work and is still refused — under
  `worktree-discard`, its own category, alongside `git checkout -- .`. A refusal
  that names the wrong thing costs more than a slow one: the reader concludes the
  tool does not understand the command and starts routing around it, which is
  exactly what the reporting session proposed to its operator.
- Refusals reported by people using the plugin, each now a test.

  None was found by reading this code. The captured-corpus pass that fixed twelve
  gate defects could only find what the corpus held, and it held no `npx`, no
  heredoc script and no dev-server restart, because those are not commands this
  project runs on itself.

  **Deletes had no blast radius.** Every one scored R4 — a scratch file and
  `rm -rf /` alike. That was invisible while every protected tier refused, since
  the outcome was identical either way; the moment R4 began asking, the
  difference became one keypress. A recursive delete aimed at a filesystem root
  or a home directory now refuses outright, and an ordinary delete asks.

  **Ending a process was an `unclassified-mutation`** — the bucket for things the
  classifier does not recognise at all — so restarting a dev server the agent had
  started produced a refusal that said nothing about what would happen. `kill`,
  `pkill`, `taskkill`, `Stop-Process` and `systemctl stop` are `process-control`
  now, anchored to command position: written as "anywhere in the line" first,
  which turned `grep -rn kill src/` into a termination.

  **`npx` and `npm ci` were unknown mutations,** so a session rewrote its
  commands as `node ./node_modules/.bin/…` to get past the gate. A gate that
  teaches people to rephrase has not stopped anything.

  **Heredoc bodies were classified line by line.** A newline ends a segment, so
  `import json` inside a Python heredoc became an unknown mutation and refused
  the whole call — two sessions worked around it by writing scripts to files. The
  body is data now. A command after the delimiter is still a command, and a
  substitution inside a body is still classified, because the shell really does
  expand it.
- The request ledger put a full archive read on every prompt.

  `record_request` scanned every record to reject a repeated prompt, which meant
  each turn paid for the whole archive: measured at 1.1s against 65 events, and
  growing linearly and forever, inside a hook the host kills at its timeout. A
  neighbouring plugin's prompt hook was observed dying at 30s under archive
  contention in the same week.

  Deduplication moved to review, where `review_requests` already collapsed
  repeats. A retyped prompt now writes a second record and the reviewer shows
  one — the same answer, paid for once when somebody reads the report rather than
  on every keystroke.

  Measured attribution for the rest of that hook, which is not fixed and should
  be known: a bare interpreter costs 299ms, the runtime imports another 440ms,
  and resolving the project anchor costs 2.7s in git subprocesses. The anchor is
  the dominant cost and the pre-tool gate pays it on every tool call too. On this
  machine the cause is a virus scanner reading a large binary on each spawn, so
  the largest available improvement is an exclusion for `git.exe` rather than
  anything in this code.

  The prompt hook's timeout is raised from 10s to 30s. Recording an ask is not
  worth ending a turn over, and the hook already swallows its own failures.
- The secret scan missed a credential said the way a person says one.

  It required a `:` or `=` and eight characters — right for a machine token,
  wrong for every human phrasing. `password: 555345`, `my password 555345` and
  `the db password is hunter2` all returned no findings.

  That combination had already shipped. The request ledger records every prompt
  through this scan, so the first real credential to arrive in a conversation
  would have been written to the archive verbatim — while the module's own
  docstring said a ledger of asks is not worth a store of credentials. The claim
  was tested against `ghp_…`: the case that was imagined, not the case that
  happened.

  The eight-character floor is replaced rather than removed, because a rule that
  fires on `password manager` refuses ordinary prose, and the hook swallows a
  refusal so the operator's turn continues — every false positive would be a
  request silently not recorded, which is the failure the ledger exists to stop.
  A digit in the value, or quotes around it, separates `password 555345` from
  `password manager`, and a four-character minimum keeps `api key v2` out.

  `api key` with a space is now matched too. The old rule knew `api_key` and
  `api-key`, which is how it is written in a config file rather than a sentence.
- Two reports that were true and useless.

  **Closing a request was unreachable from the command line.** Closure matched
  `data.digest`, which the runtime writes and a person cannot: `remember --kind
  request --status closed --subject "..."` carries no field a digest could travel
  in, so the mechanism existed, the report told the reader to use it, and using it
  changed nothing. The subject is digested as a fallback now, under the same
  normalisation the request was recorded with, so retyping the line is enough.
  The same shape as obligation retirement being starved by a filtered record
  list — one module along, three weeks later.

  **`recurrences` returned a green verdict from a scan that examined nothing.**
  `{"checked": 0, "verdict": "no-recurrence"}` reads as "the same cause never
  repeated" and means "no blocked step has ever been recorded". It says
  `insufficient-data` now, and states its scope, which is what the version
  reconciler and the census each had to learn separately.
- The closure the report told you to run, made runnable.

  Every open request the ledger reported ended with the same instruction:
  `godmode remember --kind request --status closed`. The parser rejected
  `request` as an invalid choice, so the remedy the product named errored out.
  This is the exact failure the module's own digest fallback exists to fix —
  a mechanism that exists, a report that points at it, and using it changing
  nothing — recurred one layer up in the command line.

  Two more steps of the same path were dead behind it. A request written by hand
  carried no digest, so even once the parser accepted it the closure matched
  nothing by digest. And `remember` defaulted every kind to `active` while both
  the review and the detectors read only `open`, so a hand-written request landed
  in the archive and nothing ever looked at it.

  So `--kind request` is accepted, the subject is digested under the same
  normalisation the prompt hook uses — which is what makes retyping the line
  enough to close the prompt it came from — and the status default is per-kind.
  An explicit `--status` still wins, so closing stays an explicit act.
- The detector that watched for work was watching for things the archive cannot hold.

  `inferred-ask-blocking` decides whether a session stalled by asking what was
  recorded after the guess. Its watched set named `build`, `verify`, `attest` and
  `plan` — and only `plan` is a record kind. `godmode build` writes `change`;
  `verify` and `attest` write `attestation`. The other three can never appear, so
  in production the check matched almost nothing and the detector was close to
  inert.

  Every test passed throughout, because they ran against a fake ledger that
  accepts any kind at all. The census learned this exact lesson once already: a
  surface recorded under a kind the archive cannot hold is impossible, not merely
  unused. The fake was the thing that hid it.

  Fixed to the kinds that exist, and guarded two ways: one test asserts the
  watched set is a subset of `EVENT_KINDS`, so the next name typed from memory
  fails loudly, and one exercises the detector end to end through the real
  archive that validates kinds rather than through the stand-in that does not.

  The same mistake was caught in the acceptance check while it was being written,
  which selected `kind="build"` for the same reason.

## [0.2.8] - 2026-08-09

### Added

- A ledger of what the operator actually asked for.

  Everything else this runtime governs leaves an artefact: a command leaves a
  run, a fix leaves a commit, a conclusion leaves a claim that must cite one. A
  request leaves the agent's recollection and nothing else, which is the one
  substrate this product exists to distrust — so an ask made while the agent was
  already working is the thing that goes missing, and afterwards nobody can point
  at what was dropped because there was never a list.

  Recorded live, because it cannot be reconstructed. Both signals that would have
  allowed reconstruction were tested against a real 9,777-event transcript and
  both are absent: the host's "sent a new message while you were working" notice
  appears twice in the whole file, once because the agent quoted it, and zero of
  113 human inputs carry a timestamp inside a tool call's span, because the
  stored time is delivery rather than typing. After the fact an interruption is
  indistinguishable from an ordinary turn.

  So a `UserPromptSubmit` hook writes each prompt as a `request` record as it
  arrives, with whether tool calls were already in flight. `checkpoint --review`
  reports the ones nothing visibly answered, interruptions first, and closure is
  the same explicit act obligations use — findings, never closures, because an
  agent that could close its own requests would close them the way it currently
  forgets them.

  The prompt goes through the ordinary append, so the secret scan every record
  gets applies: a pasted token is refused, and the hook swallows the refusal so
  the operator's turn continues. The subject is truncated rather than stored
  whole; the host already keeps a transcript and a second copy is a second thing
  to leak.
- `version --reconcile` now reads the version out of the tree the tag points at.

  v0.2.7 was published against the commit before the version bump. Every surface
  agreed — the tag was named `v0.2.7` and every file said `0.2.7` — so the
  reconciler returned `agreed` and CI passed, while `git checkout v0.2.7` gave a
  plugin manifest reading `0.2.6`. Anyone installing the release would have got a
  plugin identifying as the previous version.

  Nothing was broken in the check. It compared the tag's name to the sources, and
  the name was never wrong; it never asked what the tagged commit says about
  itself. `plugin.json at tag <name>` is now a surface like any other, and the
  report states whether it could be read, because a shallow clone can have the
  tag without its tree and a fetch depth is not a release defect.

### Fixed

- Quick start described a CLI; the product is three hooks and five skills.

  A reader's first experience is a continuity brief loaded at session start, a
  refusal at the pre-tool boundary, and skills routing by the shape of the work.
  The section that introduces the product opened with three interpreter
  invocations and a command count, which reads as a large manual CLI and is the
  opposite of what installing it feels like. It now leads with what happens
  without being asked, and names the three ways to answer a refusal — including
  staging a capability, which is the one that had gone unmentioned everywhere.

  Two stale figures went with it, and both were inside fenced code blocks:
  `80 commands` when there are 82, and a CI snippet pinning
  `AIimagined/Godmode@v0.2.0` through seven releases.

  The count is now gone rather than corrected. Only 82 of 120 `add_parser` calls
  are top-level commands, so there is no exact local answer, and the linter's own
  guidance is to stop stating a number that changes rather than to police it —
  the same reason `hosts` has never been checked.

  The pin is checkable, because the running version is an exact answer, so
  `stale-self-pin` now reports any snippet pinning a version of this project that
  is no longer current. It reads inside fenced blocks deliberately: the figure
  check skips them, since a number in a code sample is usually an argument, which
  left every install snippet — the one thing a reader copies verbatim — in the
  only place no check looked. Release notes are exempt, because a document about
  v0.2.4 should say v0.2.4.
- The README header said "Godmode" twice and carried a blank half-screen.

  The logo image contains the wordmark, and an `<h1>Godmode</h1>` sat directly
  under it, so the name appeared twice with a gap between. The heading now wraps
  the logo, which keeps the document's one top-level heading and its accessible
  name while showing the name once.

  The gap was measurable rather than a matter of taste: 46% of the logo's height
  was transparent padding, on a 1,254-square canvas. Cropped to its content with
  a small margin — 795x727, and 1.9MB down to 818KB.

## [0.2.7] - 2026-08-09

### Added

- Ground rules about evidence are enforceable now, in two places.

  The charter grades them. Fed six real troubleshooting rules from a live
  project — never design a remedy on a root the differential has not confirmed,
  never conclude absence from a search miss, never answer why the product behaves
  this way from the code alone — the compiler graded four of them advisory,
  because they matched no known shape and the fallback blocks nothing. The gate
  that already existed would have passed a session that broke every one. They
  compile HARD now, each with a check that something can satisfy, while an
  ordinary preference stays advisory: a rule that blocks everything is switched
  off within a day.

  A root cause must cite what confirmed it. A claim asserting why something
  happened, recorded without a citation of a comparison that was actually run, is
  stored as a hypothesis whatever the author believed — and the refusal names the
  missing step rather than only refusing. A command citation still resolves only
  when an attestation records having run it, so writing the words is not enough.

  This comes from a mistake ledger that had already written the rules down and
  recorded breaking them anyway: *"the rule existed; the habit didn't"*. A rule an
  agent must remember is a rule an agent in a hurry skips, so the burden moved to
  the claim, which cannot be recorded as verified without its evidence.

  The new shapes sit below the specific development disciplines rather than above
  them. Placed first they captured a rule whose subject was citations, because a
  subordinate clause mentioned absence, and that rule lost its citation check —
  the table's own ordering contract, broken by the change meant to extend it.

  Four more shapes cover agent-behaviour rules that were falling through: a gate
  that failed without reaching its target, attribution without a positive
  identifier, a repair that is not idempotent, and a mechanism named by the event
  that preceded it rather than the one that performed the mutation. Compiled
  against a real 2,700-line operating constitution these move eleven directives
  out of advisory; the rest that stay advisory are project engineering knowledge -
  viewport sizing, poster states, a specific polling contract - which this runtime
  should not pretend to check.

  Evidence has a session now. A command citation resolved against a run from any
  session, at any distance in the past, so a claim made today could rest on a
  command executed a fortnight ago against a tree that has since changed. It must
  come from the session making the claim, and the refusal says the command ran in
  another one rather than reporting it as unresolvable - which would send a reader
  hunting for a typo that is not there.

  An absence claim resting on a single probe that found nothing is a hypothesis.
  A search miss is evidence about where it looked; a second, different probe is
  what turns it into a fact about what exists. Proportionate on purpose: a probe
  that positively enumerated something is a different act, and demanding two for
  every absence claim would be the over-gating that gets a check switched off.
- `integrity` now checks that a change arrived intact before asking what it means.

  The nine existing monitors watch what a diff does to the meaning of the tests.
  These watch something earlier and dumber: whether the write landed as written. A
  file this change touched must still parse, and must not carry control bytes no
  editor produces.

  Both come from real damage. A scripted edit reported success while the shell
  halved its backslashes, turning a word boundary into a literal backspace byte —
  so every pattern in that file silently matched nothing, and the fault was found
  by a test failing later rather than by the write. The same shell mangled two
  more edits in the same session, the same way, each time reporting success.

  Only files the diff touched are examined, because a pre-existing oddity
  elsewhere is not this pass's finding and reporting it trains the reader to skip
  the whole report. Both findings block: a file that no longer parses cannot be
  reasoned about by any monitor above it, and a corrupted write has already failed
  whether or not anyone has noticed yet.
- The last five tooling failures, each in the form that is actually checkable.

  A taxonomy of real coding-agent incidents gives the agent's own tooling its own
  section, and five of its entries describe a discipline rather than an artefact.
  Each has a narrower form a runtime can see, and the narrow form is worth more
  than a rule nothing checks.

  An anchored edit that matched nothing reports success and leaves the file as it
  was, so a file that appears in a change but differs only in whitespace is
  reported. A dependency or lockfile change means any process started before it is
  serving the old tree, so a later run is evidence about that tree rather than
  this one — reported and not blocked, because editing a lockfile is ordinary and
  a gate that stops it is a gate that gets switched off.

  A status about a system this runtime cannot see — a build that passed, a release
  that is published, a branch that was merged — is now recognised as an external
  claim, and needs a source read this session rather than a memory of one. That
  came from stating release state here from seventeen-hour-old recall while the
  API sat one call away, already used minutes earlier for something else.

  `capabilities --usage` reports corrections the runtime made that nobody wrote
  down. A downgraded claim is the one correction this runtime can see for itself:
  the author asserted something and the record refused it. If that happened and no
  lesson exists, the correction survives only in whatever was said at the time,
  which is exactly how the same mistake returns.

  Three more verifications that pass while proving less than a reader will assume.

  A check that changed the working tree while running reports on a tree that no
  longer exists — the run is real, the subject moved underneath it. That is
  recorded on the attestation rather than refused, because a check that writes is
  sometimes legitimate and refusing every one is how a gate gets switched off;
  what must not happen is the result being read later as a statement about the
  tree that produced it.

  A guard whose name promises a universal and whose body asserts one case is
  reported. The name is what a later reader trusts and the assertion is what
  holds, so either the set gets covered or the name gets narrowed. A body that
  compares a whole collection satisfies it without a loop, since demanding an
  explicit loop would report the strongest form of an assertion as the weakest.
  The quantifier is only recognised at the front of the name, where it binds the
  subject: matched anywhere it flagged four of this project's own tests for
  ordinary mid-sentence English, which is the rate at which a monitor starts
  being skipped.

  A test that writes to a path which is not temporary is reported. A mistake
  ledger records a write-endpoint smoke test aimed at a live project id, which
  returned success and destroyed the draft it was verifying.

### Fixed

- The action gate, corrected against the commands this project actually ran.

  Its allowances were written from memory, and classifying 1,419 real commands
  recovered from the project's own transcripts showed 506 refused - 74 of them
  naming no mutation at all. Twelve defects were behind that, and one ran the
  other way: `echo pwned > ~/.bashrc` was **permitted**, because `~` is not
  expanded here, so the target was joined to the project root and passed
  containment. An unexpanded path is no longer treated as a path.

  Also corrected: `git -C path <read>` and the other global options; the git read
  subcommands (`rev-list`, `ls-files`, `describe`, `blame`, `cat-file` and nine
  more); `merge-base` read as `merge` and `commit-tree` read as `commit`, the
  second of which admitted plumbing that writes; `> /dev/null` treated as a file
  write; `--help` and `--version` classified by the operation they describe;
  `gh` read subcommands, with `gh api` judged on its flags rather than its noun;
  PowerShell literal assignments; `export`/`unset` of names that do not decide
  what runs; and a segmenter that split inside an escaped quote, reporting a
  `grep` as a mutation because its pattern contained one.

  Each widened allowance ships with the mutation it must still refuse.
- The refusal message named the wrong remedy, and recommended the worst one.

  It told the operator that no capability can be attached to a host tool call, so
  there is no in-session approval — and offered disabling the plugin instead.
  Twenty lines above that sentence, in the same function, a staged capability is
  consumed and the call proceeds. `authorize stage` shipped in v0.2.6 to answer
  exactly this refusal, and the message was never revisited.

  So every refusal denied the existence of its own remedy, and the advice most
  likely to be taken was the one that removes the guard. The refusal now names
  the staged-capability path and quotes the exact operation to authorise.

## [0.2.6] - 2026-08-08

### Added

- Four additions, each closing a gap the product could describe but not detect.

  `loop` reports a file repaired by `fix:` commits across three or more releases.
  Every other detector there reads checkpoint records, and recording a failure is
  voluntary — so across this project's whole archive not one checkpoint carries a
  non-green status and the spent-hypothesis detector could never fire. Inferring
  the failure from the records was tried first and abandoned: subjects are outcome
  summaries, not problem statements, and none of them cluster. The signal is in
  history instead, which is written by committing rather than by anyone choosing
  to admit being stuck. Run against this repository it names the action gate,
  repaired across four releases while the cause was structural — one release
  before that question was finally asked.

  `godmode_usage` measures a session from the transcript the host already writes
  to disk and hands to every hook. The product's only token figure measures how
  far the archive brief compresses the records, which is routinely misread as a
  saving, and nothing supported a claim about what a session cost. Counts are read
  and counts are kept: the file is streamed rather than loaded, only numeric usage
  fields are touched, the transcript's own path is not returned, and measuring
  writes nothing. Those properties are asserted against a transcript seeded with
  distinctive strings, so the privacy contract is checked rather than promised. A
  missing transcript reports insufficient data, never zero.

  `capabilities --usage` reports which declared surfaces this project has never
  used. Establishing that four of them had zero records took a manual
  investigation; the archive knew all along. It reports and never removes, because
  a surface unused in one project may be why someone adopted it in another.

  `docs --lint` gains a stale-figure check: a number in public prose that the
  runtime can count for itself is compared against the real count. Historical
  records are exempt, since a changelog entry states what was true when written,
  and a figure with no exact local answer is left alone rather than guessed at.
  The badge that motivated the check has been corrected by removing the count
  rather than updating it — a document stating how many tests exist goes stale on
  the next commit that adds one.

  A write to the operating system's temporary directory is ordinary work.
  Containment refuses writes outside the working tree and the agent's scratch
  directory sits outside it, so both rules were right and together made the
  intended temporary location unusable. The allowance is a property of the
  machine, deliberately not a path a project can declare: a repository able to
  nominate its own writable location could nominate any of them, which is the
  disarming this gate exists to notice.

  Finishing a task records the claim. `claim` grades an assertion against
  citations that must resolve and is the first thing this product demonstrates,
  and across the whole archive it had been used zero times — because it is a
  command somebody has to decide to run, and an agent finishing a task is reaching
  for the finish rather than for a subsystem. Reporting that work is done is
  itself an assertion about project state, so `report --record-claims` puts it
  through the same grading as any other. Nothing new is asked of the agent, and
  the honest outcome is the common one: a completion carrying no resolving
  citation is stored as a hypothesis.

  `benchmarks/` holds four tasks that check whether the mechanisms fire — a
  weakened test, a drifted version surface, a spent hypothesis, and the cost of
  the bounded brief. Each binary task ships a control run with the fault absent
  that must produce the opposite result, because a task whose control also fires
  measures nothing. They need no network, no model and no keys, and the results
  are committed so that a figure published anywhere has a file behind it. The
  brief's cost is reported as a size, not a saving: establishing a saving means
  doing the same work twice, which this harness cannot do and does not claim.

  A refusal can now be answered without disabling the guard. The gate named a
  remedy that did not exist: no host tool call carries a field a capability could
  travel in, so the broker was unreachable from the hook and the only response to
  a false positive was switching the plugin off. The broker was never the missing
  part — its token is password-issued, bound to one exact operation, expiring and
  spent once. What was missing was a place the hook could read it from.
  `authorize stage` puts it in the archive's own state directory, under the git
  metadata rather than in the working tree, so a cloned repository cannot carry
  one. Every other property is inherited unchanged, and the token is never
  printed, because a capability on a terminal is a capability in a scrollback
  buffer.

  The surfaces a host feeds are enumerated, each with a test that crosses its
  real boundary or a stated reason for having none. Four gate defects reached
  released builds because the tests fed the classifier strings written by hand
  while the host sends something else; fixing the gate fixed one surface, and the
  blind spot was structural. A hook the host invokes with neither a boundary test
  nor a reason now fails the suite rather than a release.
- `checkpoint --review` reports obligations that a later handoff may have made
  moot. Recording what must not be forgotten was always here; nothing ever asked
  whether a carried obligation was still worth doing, so an item recorded validly
  and superseded by a later release was restated in every handover until a human
  asked why it was still there. Both are continuity failures and only one was
  implemented.

  Two signals, deliberately dull. An obligation restated across three or more
  handovers without changing is reported, which needs no understanding of the
  text at all. An obligation about a version, recorded again later about a higher
  version, is reported as pointing at a release nobody will install.

  Findings, never closures — the fix for carrying something too long must not
  become dropping it too early, so each finding is phrased as the question a
  reader should answer.

  The first implementation grouped obligations by exact wording and found nothing
  in twenty-two real handovers, because real obligations are compound sentences
  that drift while meaning the same thing. They are now split on the joins that
  separate them and grouped by word overlap, and the test corpus is taken from
  the archive rather than written to suit the matcher.
- `tests/probe_installed_build.py` drives the hook of the *installed* plugin
  rather than the working tree's. Every gate defect this project has had was
  found by installing a build and using it, never by the suite, and twice a live
  result was reported that had actually come from a stale cache. The working tree
  and the artifact a user receives are different things, and only one of them
  ships.

  The probe runs twenty-one cases through the newest cached build and reports
  which behave differently from the release they claim to be. It is not collected
  by the suite, because it asserts about a machine's plugin cache rather than
  about this repository.

  `git commit --amend` is now named in the protected patterns instead of being
  left to fail closed. It was refused either way, but as an unclassified
  mutation, which tells the reader nothing about why the gate stopped them.

### Fixed

- A project checked out under the system temporary directory kept its containment
  rule. Recognising the temporary directory as ordinary working space was correct
  on its own, and so was refusing writes outside the working tree — but where the
  project itself sits under temp, every path near it is also under temp, so the
  first rule swallowed the second and every write outside the tree was permitted.
  That covers CI workspaces, sandboxes and any build under `/tmp`. Where the two
  overlap, containment governs alone.

  Found while reproducing an unrelated failure in a throwaway clone that happened
  to land in the temporary directory. No test would have looked for it, because
  nobody writes a test for a project living in `/tmp`.

## [0.2.5] - 2026-08-08

### Fixed

- The gate judges what a command runs rather than what it mentions, and stops
  interrupting work that never leaves the machine.

  A command named is not a command run. The classifier searched the whole line,
  so `grep "git push" notes.md` was refused because the words appeared in an
  argument — and a session working on protected operations trips that constantly.
  Quoted text is data now: it is blanked before the mutation patterns are
  applied. That is safe only because the safe listings are a whitelist matched on
  the original, so a shell invoked on a quoted script is still unrecognised and
  still fails closed.

  Staging and committing are no longer protected. A commit is local and
  reversible and loses nothing, and gating it made committing impossible in a
  session, because no host tool call carries a field a capability could travel
  in — there was no approval to give. They are recorded at the same tier as a
  file edit. `git commit --amend`, `reset`, `clean`, `rebase`, `checkout`, branch
  deletion and every form of `push` stay protected: those either leave the
  machine or destroy work.

  Release notes moved from the repository root into `docs/releases/`. Five files
  restating what the changelog and the release pages already carry made the first
  thing a reader sees a wall of near-duplicates.
- Four more refusals of ordinary shell work, all found by using the released
  build rather than by testing it.

  An input redirect was classified as a write. `wc -l < README.md` reads a file
  and writes nothing; the two characters were grouped only because they look
  symmetrical. Reading from a file is a read.

  `2>&1` was split at the ampersand. Making a bare `&` a separator so that
  `ls & rm` could not launder was correct, but in `2>&1` the ampersand
  duplicates a file descriptor and is part of one token — the split left a bare
  `1` behind, which classified as an unknown mutation and refused the whole
  command. The separator now ignores an ampersand that follows a redirect.

  Every command substitution was refused on sight. That held the line against
  `ls $(curl …)`, and denied `echo $(ls)` along with it, which runs nothing the
  classifier could not already see. What a substitution runs is now extracted and
  classified alongside the line containing it, so the laundering is stopped just
  as firmly and nothing legitimate is lost. `${VAR}` is expansion rather than
  execution and was never this.

  An output redirect inside the working tree was refused while the declared
  `Edit` of the same path was permitted. That gated the honest form and not the
  other, which is all cost and no cover. A redirect is now judged by where it
  lands, exactly as an edit is: inside the tree it is ordinary work, and outside
  it, or into `.git/`, `.env` or a key, it is protected.

## [0.2.4] - 2026-08-08

### Fixed

- The gate is tested the way the host drives it, and three defects it had been
  hiding are fixed.

  Every file edit was refused. The allowance for ordinary working files tested
  whether a path looked absolute, which read as a reasonable proxy for "outside
  the tree" and is not one: the host sends an absolute `file_path` for every
  `Write` and `Edit`, so the allowance could never fire and no edit was ever
  permitted in a session. Containment is now measured against the project root,
  which also subsumes traversal — a path normalising outside the tree fails
  containment rather than needing its own rule — while `.git/`, `.env`, keys and
  certificates stay protected wherever they sit.

  Shell control flow was refused. `for`, `do` and `done` are not commands, so
  they matched nothing and failed closed, and an ordinary loop over a few files
  was denied. Control flow is now recognised as structure: a keyword is stripped
  and the remainder judged, exactly as an assignment prefix is, so `do rm -rf x`
  stays protected and a loop body is still classified on its own.

  The refusal message named a remedy that did not exist. It asked for a one-use
  capability, but no host tool call carries a field a capability could travel in,
  so the broker was unreachable from the hook and the operator was sent looking
  for a token they had no way to supply. It now names what actually unblocks the
  call, and says plainly that there is no in-session approval — which is also the
  reason this gate must be conservative about what it stops, since every refusal
  is total.

  All three were invisible to the suite for one reason: the tests fed the
  classifier operation strings written by hand, one layer below the boundary
  where the host's payload arrives. A real `PreToolUse` payload now goes into the
  hook process and the decision comes back out, so a case can only pass by
  working the way it will work in a session.

## [0.2.3] - 2026-08-08

### Added

- The document linter now checks both directions. Every check it shipped with was
  negative — rationale leaks, unverifiable claims, counterfactuals, internal
  notes, unfinished markers, local paths — and all six ask whether a document
  contains something it should not. None asked whether it contains something it
  must, so a document that silently omitted a required section was reported
  clean. The bias runs one way: in a one-sided
  linter every false negative makes the output look better than it is, which is
  the wrong direction for a tool whose purpose is to stop overclaiming.
  
  A project may now declare artifact contracts in `.godmode-docslint.json`,
  mapping a path pattern to the sections a document must carry. Both halves are
  checked: `missing-section` when a required heading is absent, and
  `empty-section` when one is present with nothing under it — a heading with no
  content satisfies a word-search and satisfies nobody reading it. A mistyped
  contract is reported rather than dropped, since an operator who believes their
  documents are under a check that never ran is worse off than one who declared
  nothing, and the report states which contracts were applied so it cannot be
  read as contract-checked when none was declared.
  
  Applying the first contract to this project's own release notes immediately
  found one shipped without any verification instructions.
- `godmode trust` reports what a repository's checked-in agent configuration
  would run and what it would permit. Host settings, server declarations and hook
  definitions were already being read, but only to ask whether their prose was
  shaped like an instruction — never the structural question of whether the
  configuration a repository ships *executes* anything or *disarms* anything.
  
  A cloned repository can declare a hook that runs a command the moment a tool is
  used, declare a server whose launch line is arbitrary, or pre-authorise the
  exact operations the action gate exists to interrupt. That last one made the
  omission reflexive: this product's own enforcement is a host hook, so the
  gate's off-switch lived in a file the gate never read.
  
  Blanket permission modes and fetch-and-run hooks fail the command. A declared
  server or an ordinary allowance is reported without failing, because a check
  that stopped every clone carrying one would be switched off. Nothing here
  decides whether a declaration is hostile — that is the operator's judgement
  about their own repository — and an unreadable configuration file is reported
  rather than skipped, since silence on a file that could not be parsed reads as
  approval. Absent configuration and inert configuration are reported as
  different facts.
- Each release gate is now run against a copy of the project with the property it
  defends deliberately broken, and must report failure. A gate that stays green
  under its own breaking mutation is not a check, and six times in one session a
  check reported a success it could not have withheld — twice a gate battery
  piped through a pager so the recorded exit status belonged to the pager, twice a
  probe that passed only on a machine already initialised, once a suite that
  proved refusals without asking whether ordinary work could still proceed, and
  once a contamination grep read as clean when its exit code meant the opposite.
  Knowing about the failure mode did not prevent the sixth instance, which is why
  it is asserted rather than remembered.
  
  Writing the mutation turned out to matter as much as running it. Three of the
  first mutations attempted were wrong — they broke something the gate never
  claimed to watch, and three gates were briefly and wrongly suspected of being
  blind. A breaking mutation cannot be written for a gate whose contract is not
  understood, so the harness doubles as a statement of what each gate is for.
  Gates without a proof are listed with the reason, because a harness that
  quietly covers a subset reads as covering everything.
  
  Module self-checks are now discovered rather than registered by hand. Six
  already existed and had never been wired into the suite, and the action gate —
  the classifier deciding whether a destructive command is interrupted — had no
  self-check at all while quieter modules did. It has one now, asserting both
  directions: the commands a working session issues must pass, and the
  destructive forms must not.
- A portable `plugin.json` at the repository root makes this installable by any
  client implementing the Agent Plugins specification, alongside the existing
  host manifests, which stay where their hosts look for them. The skill layout
  already conformed exactly; the field vocabulary already matched. What was
  missing was a manifest at the location every conformant client checks.
  
  The specification's schema is closed, so host-specific data moves under
  `extensions` behind a reverse-domain namespace that other clients ignore
  without validating. No `mcp.json` is shipped, because this product declares no
  MCP server and an empty one would advertise something that does not exist.
  
  The description says plainly that the portable package carries skills and that
  the action gate needs a host with hook support: hooks are outside the v1
  format, so a client without them installs the skills and none of the
  enforcement. A governance tool that does not say so is mis-sold.
  
  Conformance is asserted locally against the closed field set rather than by
  fetching anything — the schema URL in the manifest is a string, never a
  request — because a manifest validated only by other people's installers is
  exactly the shape that let the composite action stay broken for a fortnight.
  The root manifest is registered as a version surface, since adding one without
  registering it is the silent drift that command exists to catch.

### Fixed

- Changelog fragments are linted as public prose. They were treated as working
  material, so a fragment's wording was only checked once it had been merged
  verbatim into the public changelog — at which point changing it edits a
  published record rather than a draft. The linter caught its own release note
  this way, flagging a superlative in text that had already shipped into
  `CHANGELOG.md` when the same words had passed unexamined in `changelog.d/`.
- A claim about the outside world is now recognised without being declared. The
  runtime already refused to record a verified claim about an external system
  unless a primary source had been read, but that check only ran when the caller
  passed the flag — so it protected whoever remembered they were talking about a
  remote system, which is not the person who needs it. The seed case was an
  assertion that a pinned action version did not exist: stated from recall,
  wrong, and caught only because a human checked. No flag was passed, because it
  did not feel like a claim about anything remote.
  
  Detection is narrow on purpose, firing on third-party artefacts pinned at a
  version and on assertions about what a released version does. A detector that
  fired on ordinary local statements would teach the operator to route around it.
  
  Fixing the detection exposed the gate behind it as unsatisfiable. It demanded a
  `doc:` or `url:` citation and then rejected every one of them as unresolvable,
  so a claim about the outside world could never be recorded as verified whatever
  the author had actually read. A source outside the worktree now resolves as the
  operator's declaration that they read it — nothing local can confirm that, and
  confirming it over the network is not something this runtime does — and the
  record names which citations were asserted rather than checked, so a later
  reader sees the difference instead of one uniform "verified".
  
  The seeded fuzz harness caught the first version of that change accepting a
  citation of control characters and encoded traversal, which a declared source
  reference must now not look like.
- Merging a version twice no longer produces that version twice. A release is
  rarely cut in one pass — a fragment arrives after the first merge, usually
  because a gate caught something, which is the system working — and the second
  merge inserted a second heading for the same version above the first rather
  than folding into it. Entries already recorded are kept verbatim, so a re-merge
  never reformats prose that has already been published.

  One such duplicate shipped in a tagged release while 464 tests, thirteen gates,
  the changelog check and the document linter all reported green, because nothing
  had ever asked whether a version appears once. The repository's own changelog
  is now asserted to carry each version exactly once.

## [0.2.2] - 2026-08-08

### Fixed

- The injection scanner no longer reads vocabulary as instruction: an
  exfiltration verb must govern its object within a few words, so a threat model
  describing "memory leak" and "secret scan" on one line is documentation rather
  than an attack. The acceptance suite now runs every gate the CI workflow runs,
  reading the list out of the workflow file itself and checking each exit code,
  so a gate that only exists in CI can no longer regress unseen. The composite
  action resolves `python3` when a bare `python` is absent instead of failing
  with "command not found".
- The composite action loads again: an input description interpolated
  `${{ github.base_ref }}`, and expressions are evaluated in a manifest where
  that context is not bound, so the whole file failed to parse. A second defect
  made a `run:` scalar start with a quoted string and continue. Both classes are
  now asserted locally, because nothing but GitHub had ever read that file. Two
  behaviour probes were quietly machine-dependent — they called commands needing
  an initialised archive, so they passed on a developer's machine and failed on
  a fresh checkout; they now exercise the same skills without one. The anchor
  test resolves both sides before comparing, since macOS maps `/var` to
  `/private/var`.
- The pre-tool gate denied a working session: `ls`, every pipe, every compound
  command and every file edit fell through to `unclassified-mutation` and failed
  closed. Compound commands are now split and judged by their worst part, so a
  pipeline of reads is a read and a safe head cannot launder a dangerous tail;
  ordinary shell reads are recognised; editing a working file is the work rather
  than a protected action, while `.git/`, `.env`, keys and paths outside the tree
  stay protected; and running an interpreter is recorded as local compute, since
  this gate covers named protected operations and is not a sandbox. A new
  usability suite runs twenty commands taken from a real session and fails if any
  is blocked — the question no test had asked before.
- The gate denied every PowerShell command. The pre-tool hook fires on
  PowerShell calls, but the classifier knew only POSIX vocabulary, so on Windows
  each cmdlet was an unclassified mutation and the whole session failed closed —
  the same defect as the previous release, surviving its own fix because the
  usability corpus had been taken from a session that happened to run a POSIX
  shell. PowerShell's approved-verb convention now classifies it: `Get`, `Test`,
  `Measure`, `Select`, `Resolve` and their peers read, and every other verb is
  absent on purpose so `Set-Content`, `Remove-Item` and anything nobody
  enumerated still fail closed. `find`, `findstr` and `where` are recognised
  too, while `find … -delete` and `find … -exec` are named as the mutations they
  are.
  
  Granting a read allowance had also created something to hide behind. While
  `ls` still failed closed, a separator the splitter missed cost nothing; once
  `ls` was a recognised read, a newline or a bare `&` handed the rest of the line
  the tier of its first word, so `ls⏎Invoke-WebRequest …` classified as a
  listing. Both now end a segment. A command substitution cannot be split out at
  all — it never appears as a segment — so `$( )`, backticks and `${ }` withhold
  the read allowance instead of extending it over an operation the classifier
  never saw; a plain `$VAR`, `$env:` or `$_` is a value, not a command, and is
  unaffected.
  
  The usability suite now carries a Windows corpus alongside the POSIX one, and
  asserts the laundering cases directly, so neither half of the contract rests
  on which shell the last session happened to use.

## [0.2.1] - 2026-08-07

### Added

- Behaviour assertions now execute instead of being counted: an assertion in a
  skill's `godmode-evals.json` may carry a `check` (argv command plus expected
  exit code and output substring) that runs for real from the project root,
  while bare strings stay valid and are reported declared-only. Each of the
  five skills ships at least one executable probe. Two new snapshot families
  join routing: `charter-rules.json` freezes every compiled rule (id, trigger,
  enforcement, verify, text hash) so editing a prose rule shows a field-level
  diff, and `ranking.json` freezes the ordered segment selection the context
  brief makes for a fixed three-task set, so retrieval drift fails loudly.
- Chronicle depth work in three parts. Append no longer re-verifies the whole
  chain on every write: a `godmode-head.json` hint in the archive root is checked
  against the last record file only, falling back to a full verified scan (and
  rebuilding the hint) whenever the hint is missing, corrupt, or stale — full
  verification is unchanged and still catches mid-chain tampering via
  `verify()`/`doctor`. `append(..., dedupe=True)` returns the most recent
  byte-identical record of the same kind and subject (marked `"deduplicated":
  True`, never persisted) instead of growing the chain; the default is off, and
  dedupe never crosses subjects. New `Chronicle.expunge(sequence, reason)` erases
  a record's data and evidence after a secret slips the shape scanner: the record
  and every subsequent one are re-sealed so the chain still verifies, and an
  `incident` tombstone (sequence, reason, old record hash) makes the rewrite
  auditable instead of silent.
- The mandatory task-completion report (PRD 23.2) now exists as
  `godmode_report.completion_report`: twelve fields assembled from archive
  records and read-only git observation instead of composed from memory. The
  status verdict is derived, not asserted - "verified" is only reachable when no
  claim this session was downgraded and session close would pass, a blocked gate
  forces "blocked", and a session with no change records reads "no change
  required". Every field carries an uncertainty label from the 23.1 vocabulary,
  and `render_markdown` emits the TASK COMPLETION REPORT table (field, value,
  label) in a fixed order.
- A derived SQLite index (`index.db` in the archive) now persists ranked corpus
  segments, compiled rules, and archive summaries between sessions: `rebuild`
  regenerates it wholesale from the live sources, `fresh` proves the sources have
  not moved before any read, and `query` refuses a stale index outright unless
  the caller opts in and accepts a `stale: true` label. Alongside it, a read-only
  database architecture manager inventories every SQLite file via `mode=ro`,
  runs the 11-row Mandatory Schema Review (rollback text is a hard fail, never a
  question), and statically flags hazardous migration SQL such as `DELETE`
  without `WHERE`.
- `godmode fuzz` feeds seeded garbage — unicode, nulls, separators, quotes,
  comment markers, encodings, lengths — to the command classifier, path
  containment, migration review, citation binding, and every config reader, and
  asserts the properties that must hold for any input. Findings carry the seed
  and case index so a failure replays instead of being hunted. Its first run
  found four config readers that crashed with `AttributeError` on a file
  containing `null`; they now degrade to defaults, and 2,500 fuzzed cases across
  five seeds report fail-closed.
- A mid-rebase repository used to read as merely "dirty". `repo_state` now
  detects in-progress git operations (merge, rebase, cherry-pick, bisect,
  revert), detached HEAD, and stash depth straight from git's own metadata —
  worktree `.git` pointer files included — and surfaces a crisis as a
  `repo-in-progress-operation` context warning, inside `observe_git`, and as a
  named `warning` in the opening handshake, right after the dirty count it used
  to hide behind. Lessons now carry a project scope tag (`record_lesson_scoped`
  / `lessons_for`) so one project's habit cannot leak into another unless
  explicitly marked portable, and `advance_evidence` enforces the §15.2 ladder:
  confidence climbs one rung at a time, and demotions always pass but must state
  a reason.
- The parity matrix now compares eleven capability-level dimensions instead of
  file-surface counts: `capability` (public symbols via the atlas, both trees),
  `architecture`, `runtime-wiring` (orphan ratios: presence vs wiring), the six
  surface dimensions, `identity-freshness`, and `project-invariants`. Each
  dimension carries one of five verdicts (ADOPT, EXTEND, DIVERGE-DELIBERATELY,
  REJECT, ALIGNED) with a one-line reason; reference-ahead gaps name their adopt
  candidates and project-ahead gaps list local extensions, never "ignore".
  `adoption_floor` enforces E-14: an ADOPT whose paths overlap a recorded
  invariant's `file:` evidence flips to REJECT ("protected local fix; parity is
  a floor, not a ceiling"), wired into `parity_matrix` via a new optional
  `archive` parameter. `waive` records written acceptance of a gap, and the
  matrix's new `accepted` flag stays False while any open recommendation lacks
  one.
- A `PreToolUse` gate decides mutating tool calls in the host's own contract:
  protected operations without a capability, reached run ceilings, and a
  three-skip pattern all return `permissionDecision: "deny"` with the reason.
  Tool calls and elapsed time are now measured by the runtime instead of
  reported to it (tokens stay host-declared and are labelled as such), and
  `tool_call_interception` reports `HARD` only where the gate is actually
  installed.
- `godmode metrics` computes the twelve product measures from local records
  only — whether resumed sessions follow their stated next action, whether root
  causes survive scrutiny, whether finished work stays finished — each stating
  its basis and reporting `insufficient-data` rather than a flattering zero when
  there is nothing to measure. Duplicate detection stops counting test-method
  names and repeated house helpers as duplication (499 pairs to 33 on this repo)
  and is reported as leads rather than a pass/fail target.
- `session close`, `status handover`, and the session-end hook now report what
  the gates actually did — checks blocked, claims downgraded, steps skipped,
  secrets refused, scope drift, and the measured context reduction — each count
  carrying the record sequences that produced it. The summary reports activity,
  never averted disaster, because that counterfactual is unmeasurable; it stays
  silent when nothing fired and is switched off with `.godmode-report.json`
  `{"session_summary": false}`.
- The §12 lifecycle is now a stage machine read from the archive instead of a
  convention: `godmode_stages` derives each stage's entry requirement from records
  the work already produced (inventory, parity decision, approved plan, change,
  ran check, reconciled docs, undowngraded claim), `stage_gate` checks the whole
  prefix up to the target, and `advance` attests entry only when the gate passes.
  A stage may be skipped only by a recorded decision that states a reason. The
  §15.1 troubleshooting SOP ships in the same module as a fifteen-step checklist
  (T0–T14) whose completion is `sop:Tn` attestations; `sop_status` reports the
  next required step and names a root-cause claim premature while reproduction,
  staleness, and guard-observation remain unattested.
- Work items now carry the §19 schema: `status` records accept a closed item
  type (epic/story/bug/spike/chore/security/debt), Fibonacci points with a
  split-at-8 / spike-at-13 advisory finding, acceptance criteria, dependencies,
  branch, and severity. Three gates hold the schema load-bearing: verified with
  declared acceptance needs evidence, a bug cannot close without a root cause or
  an incident citation, and blocked requires naming the exact blocker. The
  rolling handover adds the §20.1 contract fields (repository anchor, approved
  objective, verified-versus-unverified split, protected invariants, changed
  files, remaining story points), and the reconciler gains a record-based
  trigger table (`record_triggers`) that reports changes without checkpoints,
  bug closes without guards, uncited decision reversals, and incidents without
  lessons.

### Changed

- The README is rewritten around what the product now does — the problem it
  addresses, how enforcement lives outside model output, per-host install,
  what is actually enforced, and the commands that prove each claim — and the
  logo ships with a transparent background so it sits on any page.

### Fixed

- First consumer dogfood of the installed plugin fixed four rough edges: the
  generic-adapter doc taught a `--name` flag `verify` does not have; `session
  open --brief` now shows the handshake's branch, dirty count, and
  sources statement instead of only the id; `verify --brief` states the check
  name and pass verdict; and a project with zero compiled rules is told its
  gates are vacuous (in `charter` and at session close) instead of reading as
  green.
- Egress hardening closed four gaps at the disclosure boundary. Path containment:
  every path a manifest or scan touches is resolved and verified inside the
  project root first; `../`, absolute, and symlink escapes are refused unread
  with a `path-escape` finding. Disclosures now carry `destination` and
  `destination_known`, stating "unknown" explicitly instead of omitting the
  receiving party. An optional `.godmode-privacy.json` lets a user declare
  `sensitive_paths` and `never_leave` globs that extend (never shrink) the
  built-in denials; a never-leave match blocks a notice exactly like a secret.
  And `redact=True` makes the "redact further and send less" choice real:
  blocking items are replaced by bare `redacted` entries - no counts, no
  excerpts - and the remaining scope is no longer blocked.
- Anti-loop fixes and scenario coverage: oscillation rollback now targets the
  last STABLE checkpoint (status green/verified, per §15.3) instead of merely the
  most recent one; a blocking `loop` verdict carries a four-part plain-language
  `notice` (what repeated, what it means, the next safe step, and no further
  mutation until the evidence changes); the repetition threshold is configurable
  via `.godmode-loop.json` `{"repeat_threshold": n}` clamped to 2..10 (default 3);
  and `transport-evidence:` attestations now count as non-model controls for
  model blame. The instruction-shaped-content scenario is relabelled from the
  mistaken E-13 to SEC-injection, and six golden scenarios are staged: false RCA
  (E-04), automated deletion preview (E-11), new-table temptation (E-15), context
  brief latency (E-19), session restart (CTX-01), and prior-fix protection
  (CTX-02) - 21 staged failures, all caught.
- The sentinel classified `git branch -d X` as read-only because the safe
  inspection prefix matched `git branch` before any protected pattern ran.
  Mutating flag forms of `git branch` now classify as `git-branch-mutation`
  ahead of every safe pattern, and the safe listings for `git branch`,
  `git tag`, `git stash`, and `git remote` are anchored so create, delete,
  rename, and remote-mutation forms fall through to protection. Every
  classification now carries a §9.2 risk tier R0-R5, with R5 (force-push,
  hard reset, `branch -D`, `clean -f`, SQL DROP) demanding a second
  confirmation. Capabilities bind to repository, worktree, and HEAD at mint
  time and refuse to be consumed elsewhere; pre-existing unscoped tokens
  still consume but say so. An optional `.godmode-authorization-policy.json`
  can tighten (never loosen) the boundary: TTL clamped to 60-900 seconds and
  `password_required` extending the protected categories.

## [0.2.0] - 2026-08-06

### Added

- `GODMODE_MODE=guided|standard|expert` changes exposure, never enforcement:
  guided appends plain-language guidance to every refusal, expert reports one
  line. `charter --bootstrap` mines candidate invariants from the project's own
  commit history for review, and `godmode operator` validates the typed operator
  profile — which has no name field on purpose and refuses profiles containing
  the OS account name.
- `godmode loop` reads the archive's own records and blocks the repetitions the
  repeating agent cannot see: identical normalised actions, reapplied patches
  (citing the prior attempt), A→B→A oscillation with a rollback point, changes to
  guarded files without re-observing the guard, and zero-output "successes";
  `loop --blame` refuses model-blame until a non-model control is attested.
- `atlas diagnose` now reports per-suffix support — a suffix whose files yield no
  symbols is "counted, not understood" and makes the atlas untrustworthy for
  structural claims — and `atlas duplicates` compares approximate symbol bodies
  as well as names, so one behaviour implemented twice under unrelated names is
  reported with `basis: body`.
- The atlas now dispatches extraction through a suffix registry — a third
  language is one `register_extractor` call, not a core edit — records
  `tested-by` and `documents` edges so `affected` can bound traversal by
  relation kind and bucket its answer into callers / tests / docs, and can be
  persisted with `save_index` / `load_index`, which reports fresh, stale, and
  missing files from content hashes with a derived confidence, never from time.
- `godmode benchmark` measures cold-start and resume brief cost against the
  declared token budgets with timings, computed and printed locally only; and
  `claim --external` downgrades a verified claim about an external API or
  library to hypothesis unless it cites a `doc:`/`url:` primary source actually
  read this session.
- `godmode changelog check` fails when a code change arrives without a
  `changelog.d/` fragment, and `godmode changelog merge --set-version X` folds the
  fragments into CHANGELOG.md at release time.
- A composite GitHub Action (`action.yml`) runs Godmode's gates — the
  test-integrity monitors and the changelog fragment gate — on a pull request with
  only a checkout of this repository; the runtime remains standard-library Python.
- `godmode config check` validates every declared `.godmode-*.json` file against
  its typed contract, failing with a `$.field` schema path instead of a stack
  trace; the extension-model split (S26-01/02) is deferred by recorded decision
  until a second consumer exists.
- `detect_context_issues` gains two staleness inputs — a `stale-lock` warning when
  an archive `*.lock` file has survived ten minutes, and `clock-or-restore-anomaly`
  when a file's mtime moved backward since the recorded baseline; new
  `capacity_checkpoint_due` returns the deterministic pre-compaction signal (due at
  80% of the context-brief token budget) for host hooks, and new `why` answers
  `context why --about X` with evidence-linked decisions, fixes, dependencies, and
  invariants actually recorded about a path or topic.
- README grows the missing front-door sections (badges, why, uninstall,
  troubleshooting, FAQ, documentation index); v0.1.0 release notes exist as an
  explicit draft with an owner checklist and no tag; and
  `scripts/godmode_docs_site.py` renders the repository's own Markdown into a
  self-contained offline HTML site with zero generator dependencies.
- The authored skill evals now execute: a deterministic routing runner scores every
  positive and near-negative prompt leave-one-out with stable tie-breaks, snapshot
  fixtures under `evals/fixtures/` turn any routing change into a field-level diff, and
  an adversarial grid attacks each control with real probes - breaches included.
- Forge output is now diffed against a checked-in golden skill tree, so a
  generator regression fails CI naming the drifted file; the learning loop's
  scanner → analyzer → writer → verifier phases each name their implementation
  in a registry.
- Gates deepen: egress `scan_staged`/`scan_paths` find secret-shaped values
  (masked, never repeated) in staged and untracked content before a commit exists;
  `loop` blocks after three non-green checkpoints under one unchanged hypothesis and
  demands a reset; scope `minimality` reports size pressure by name without blocking.
- A generic adapter reference lets any agent drive Godmode with shell, JSON, and
  exit codes alone — enforcement honestly labelled SOFT on unlisted hosts
  (S9-01); the LICENSE appendix names the copyright owner. Live install tests
  passed on both Claude Code (5 skills + hook inventoried) and Codex (installed,
  enabled, five skills discoverable).
- The scenario harness grows from 10 to 15 staged golden failures, each bound to
  its PRD acceptance ID (E-nn / CTX-nn): fix oscillation (E-03), test weakening
  (E-05), wrong environment (E-16), removal forgotten (CTX-03), and undocumented
  change (CTX-07) join the catalogue; `explain-context` now states the token
  cost of loading before anything loads.
- Instruction-file adapters for OpenCode (`AGENTS.md`), Cursor
  (`.cursor/rules/godmode.mdc`), and Gemini CLI (`GEMINI.md`) drive the CLI over
  shell, JSON, and exit codes; each host's enforcement is declared in
  `packaging/hosts.json`, `capabilities --host X [--record]` prints and records
  the negotiated table, and a test fails if an adapter document's stated levels
  drift from the declaration.
- Session open now performs the fixed model-independent handshake (identity,
  branch, dirty state, active plan, obligations, invariants, required-source
  count, and the host's enforcement table); a pair rule attested with one
  artefact blocks closure naming the missing half; `charter --decay N` surfaces
  rules no session touched; and the context brief ranks by freshness and states
  "read N of M required sources".
- `skill lifecycle`/`skill retire` give every skill a state and a recorded
  reason; `godmode lessons` runs the promote-or-retire pipeline (a lesson either
  gets its guard observed running or is retired — never appended forever); and
  `godmode experiment` executes the bounded loop declared in
  `.godmode-experiment.json`, recording every run and refusing to pass the bound.
- `godmode locale check` validates `locales/<lang>/` guidance variants against
  their English sources — heading structure must match and fenced code blocks must
  be byte-identical — and a Hindi `GODMODE.md` ships as the first variant.
- `godmode mistakes` runs the mistake-class detectors distilled from the lesson
  corpus: a status label used as evidence must trace to its assigning record, a
  regenerated-but-never-cited artefact is a box-tick, a generalized guard citing
  one surface blocks, bundled claims must split, and `--process-started` blocks
  an RCA against a process older than the code it runs.
- `netgate` differential capture proves the runtime dials nothing: each CLI
  surface runs against a throwaway project under a socket audit hook, any
  connection fails, and a detector that cannot catch a planted attempt raises
  instead of reporting clean; CI adds a `pip-audit` scan of the CI tooling
  environment (the runtime has zero dependencies) with `security`-labelled
  issue triage against THREAT-MODEL.md.
- `godmode_parity` turns comparison into decisions: `parity_matrix` scores a local
  reference across eleven named dimensions, attaching a verdict+action pair to each
  and labelling stale references; `absorption_check` rejects synced-but-unwired
  files until a reader and a ran guard both cite them; `schema_ladder` exhausts
  existing columns and tables before allowing a reviewed new table.
- `planmode specify` records the what/why before any plan states a how — a plan
  without a spec is refused; the contract gains `parity`, `steps`, and `points`
  fields; and an approved plan now survives a session handoff: a different model
  resumes it (it appears in the resume brief) instead of re-deriving it.
- `godmode method --check-method X --check-record file.json` gates an RCA on its
  method's completion contract: fault-tree cut sets are derived from the tree (not
  typed from memory), timelines need three instruments with ordered events and
  declared holes, fishbone spines are project-configurable via `.godmode-rca.json`,
  and an "unknown" root without a shipped instrument is refused for every method.
- `godmode environment --target` classifies a mutation target's blast radius
  (unknown fails closed as production, never overridable by repo text);
  `version --reconcile` diffs the version across every surface that states one;
  and `docs --reconcile` enforces the change→documentation trigger table,
  configurable per project via `.godmode-docs.json`.
- Every archive record now carries its author's fingerprint (host, model, effort,
  adapter enforcement level) at the chronicle layer, not only attestations; the
  context brief is proven byte-identical across models in the suite; and a
  handoff test proves agent B resumes agent A's approved plan and next action
  without reading any transcript.
- `godmode removal record` remembers why something was deleted — reason, location,
  replacement, references, restoration path, and authorizer are all required — and
  `godmode removal why` answers from the record instead of archaeology.
- Runtime guardrails inside the no-daemon boundary: `ceilings` checks reported
  spend against declared run limits, `watch` is a per-boundary anomaly scan that
  interrupts on a skip pattern, `rewind --to SEQ` previews a rollback to a
  verified checkpoint (checkpoints now record HEAD; execution stays with the
  operator), and `planmode arbitrate` scores every open plan instead of taking
  the first one stated.
- `status render` emits the status document read-only from the store, `status
  handover` gives one rolling handover view, every pending item is
  existence-checked before presentation (a phantom whose cited artefacts all
  vanished is closed in the same pass with evidence), and `sprint` now routes
  through the single status writer instead of appending a second truth.
- `sbom --format spdx|cyclonedx` emits the zero-dependency claim in standard
  forms, `sbom --gate` fails the build when the declarative dependency policy
  (default budget: zero) is violated, and `checksums` produces a reproducible
  SHA-256 manifest over every tracked file with `--verify` for clean-clone
  comparison; CI enforces the gate and proves the manifest reproducible.
- `godmode integrity` runs the nine test-integrity monitors (assertion-diff,
  skip/quarantine, mock expansion, coverage shape, requirement anchor,
  red-before-green, harness validity, negative control, protected-test gate) over
  the current diff and exits non-zero when a change weakens what the suite proves.
- Over-budget briefs now degrade through typed compression before dropping
  anything: each compressed view declares the fields its mask removed and the
  `seq:` handle that reconstructs the original from the archive; record
  confidence decays with the records written since (not wall time), and baseline
  staleness reports that decay instead of flipping a binary flag.
- `branches --claim` declares this agent active in the worktree and exits
  non-zero when another agent's live claim exists — the collision surfaces before
  mutation; `--release` hands it back. No merge driver ships: per-record
  append-only files make state conflicts structurally impossible (decision
  recorded).

### Fixed

- The two routing-eval positives that misrouted between the router and
  continuity skills were reworded with home vocabulary; routing is now sound at
  10/10 with regenerated snapshots, and the eval gate exits green.
- The completeness sweep's findings closed: the CI action job diffs HEAD~1 on
  push instead of passing vacuously; the verify matrix gains Windows and macOS
  legs plus the full gate battery; the command-surface reference is regenerated
  from the parser (74 commands); the acceptance doc maps every gate to its proof
  command across all three host manifests; each SKILL.md routes to the gates it
  governs; the repository's own charter now compiles 5 HARD rules (Hindi variant
  kept in step); `docs` without flags names the missing flag; and the atlas
  resolves cross-module imports — orphan noise drops from 57% to 38% and
  `diagnose` flags its own resolver when the ratio is implausible.

## [0.1.0] - 2026-08-02

### Added

- Local-first, project-bound continuity archive with atomic hash-chained records.
- Evidence-led inspection, resume, diagnosis, and context explanation commands.
- Protected-action classification, previews, and scoped single-use capabilities.
- Branch, version, plan, checklist, incident, privacy, parity, and export workflows.
- Validated on-demand project skill forging for evidenced reusable gaps.
- Five routed skills for Codex and Claude Code, a bounded Claude `SessionStart` adapter,
  acceptance tests, and release checks.
- Codex and Claude Code manifests plus a Claude plugin marketplace catalog.
- Godmode logo, social-preview artwork, and passive AIimagined project identity metadata.
- `authorize setup --password-stdin` and `authorize issue --password-stdin` for
  non-interactive hosts that pipe the password on standard input.

### Fixed

- Removed the duplicate `hooks` manifest reference that made Claude Code fail to
  load the plugin's hooks.
- `authorize setup` and `authorize issue` now fail immediately with guidance when
  no interactive console is available instead of blocking forever on the password
  prompt (including Windows `NUL` redirection, where `isatty()` reports true).

[Unreleased]: https://github.com/AIimagined/Godmode/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AIimagined/Godmode/releases/tag/v0.1.0

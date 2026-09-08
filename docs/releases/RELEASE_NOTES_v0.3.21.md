# Godmode v0.3.21

The proof release. 0.3.20 was tagged on a local suite green on one OS and
one interpreter; the CI matrix then went red on both Windows legs with the
tag already public, and no GitHub release was published for it. Two
operator findings followed the same week: features built on Claude's
events had been assumed to work on every host the plugin installs on, and
the grades godmode handed out were asserted, not executed. This release
answers all three with gates that read a record instead of prose.

## Proof before a tag

- A tag push is refused until a `ci` attestation names the tagged commit
  green (`godmode attest ci --status ran --result "<tag> <sha7> green"
  --evidence <run url>`). The refusal runs before any staged capability is
  spent, so the retry after attesting goes through. Native by design: the
  proof is a record with the run URL as evidence, not a forge API call.
- The done-bar grade is composed from executed predicates. A run-shaped
  claim (tests pass, the suite is green, a CI leg ran) citing
  `cmd:<command>` is `verified` only when an attestation for that command
  ran green on the current tree; otherwise it stays `observed`, carries the
  check that would settle it, and the done-bar names it once.
- Grounded claims: a claim citing `file:<path>` or `file:<path>#L<a>-L<b>`
  records the evidence's hash; `godmode claim --stale`, the continuity
  brief and the preflight gate name every claim whose evidence moved.
- The swallow ratchet holds at the gate: a file whose count of silent
  exception handlers rose above its committed ceiling is a mechanical
  preflight finding. This repository's 83 deliberate handlers now carry
  their reason on the line.

## Every host, stated

- A feature-reach table in code: twelve hook-borne features, nine hosts,
  every cell `yes`, `partial` or `no` with the reason. `hooks status`
  carries the host's row, `doctor --host <name>` names what cannot fire
  there, and the preflight gate raises `host-reach` for every declared
  host with no interception proof on the archive.
- Codex on Windows, proven live (Codex CLI 0.153.4, Windows 11, PowerShell
  7): `hooks wire --host codex` projects every handler with a
  `commandWindows` for the shell Codex actually uses and names the host in
  the command; SessionStart, UserPromptSubmit, PreToolUse and SessionEnd
  fired, and a forced push was refused with Codex reporting "Command
  blocked by PreToolUse hook". Codex's declared events are every event the
  shared file carries, plus `PermissionRequest` in the projection, and
  Codex can ask: an R2/R3 ask reaches it as `ask` instead of folding to
  deny.
- Host events that existed and were never wired: Cursor's
  `beforeSubmitPrompt`, `afterFileEdit`, `preCompact`, `sessionEnd` and
  `subagentStop`; Antigravity's `PreInvocation` and `PostToolUse`; Gemini's
  `AfterTool` and `AfterAgent`. Channels and proof on those hosts stay
  stated as partial until a probe inside the host chronicles them.
- Every verb has a demand path. Measured on 2026-09-08, 57 of 120 console
  verbs were named by nothing; the specialist skills now name each verb at
  the situation it answers. Measured after: 0 by nothing, 0 without a skill
  line or a nudge, and `doctor` holds both counts to a ceiling of zero.

## Less nagging, more help on a failure

- A stated ask the reply visibly answers is closed on the record at Stop;
  an obligation the turn touched is named once per session.
- An investigation-shaped prompt and a failed tool run both name the RCA
  verbs (`mistakes`, `error-pattern`, `incident --failure-class`,
  `differential`, `plant`, `verify --command`) at the moment of demand.
- Two-layer authorization policy, tightest wins: an operator-level file
  under the state home is the ceiling the project file may only tighten;
  `godmode operator --policy` names which layer decided each key.

## What the 0.3.20 matrix found

- A zero atlas budget scanned files on Windows Python 3.11: `elapsed >
  budget` read false under that interpreter's 15.6 ms clock. A budget
  already spent is spent at zero.
- A bound role document was rendered as an absolute path when the project
  path carried an 8.3 element. Both sides of `relative_to` are resolved
  now; the regression test reproduces through a symlinked project on any
  OS and through the 8.3 name on Windows, with no platform skip.

## Verifying

- `python -m unittest tests.test_tag_push_ci_gate tests.test_deterministic_grade
  tests.test_grounded_claims tests.test_swallow_ratchet_gate` - the tag
  gate, the composed grade, the stale sweep, the ratchet at the gate.
- `python -m unittest tests.test_feature_reach tests.test_verb_reach
  tests.test_host_events_wired tests.test_codex_windows_hooks` - every
  feature has a status on every host, no verb is unnamed, the new host
  events are declared, Codex's Windows command and ask dialect.
- `python -m unittest tests.test_ask_autoclose_and_rca_shape
  tests.test_policy_layers` - asks close when served, nags fire once, the
  RCA shape and failure nudge, the two-layer policy.
- `python -m unittest tests.test_atlas_registry tests.test_brief_next_actions`
  - the zero budget under a frozen clock; the aliased project path.
- CI: every leg of `godmode-verify.yml` must be green and attested as `ci`
  on the cut commit before the tag is pushed; the gate above enforces it.

Full detail per change: `CHANGELOG.md`.

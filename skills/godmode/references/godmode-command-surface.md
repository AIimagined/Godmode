# Godmode command surface

Generated from the CLI's own parser; regenerate rather than hand-edit when
commands change (`docs --reconcile` guards the drift). Global flags `--brief`
and `--json` work on every command and may appear in any position;
`GODMODE_MODE=guided|standard|expert` changes exposure, never enforcement.

| Command | Purpose |
| --- | --- |
| `absorb` | Check whether a synced file is truly absorbed (reader + guard) |
| `actions` | Read capability audit events |
| `adopt` | Relink records stranded by an identity change (e.g. git init) |
| `assess` | Grade whether this project's own rules can be complied with |
| `assurance` | Emit an assurance case generated from live probes |
| `atlas` | Map the project's symbols and their relationships |
| `attest` | Record that a mandated step ran, found nothing, or was skipped |
| `authorize` | Configure or issue local capabilities |
| `benchmark` | Measure brief budgets and timings, locally only |
| `bindings` | Generate host manifests from one source |
| `branches` | Inspect branches and worktrees |
| `brief` | Assemble a bounded, model-independent context brief |
| `build` | Record an implementation result |
| `capabilities` | Report what this host can actually enforce |
| `ceilings` | Check reported spend against declared run ceilings |
| `changelog` | Fragment-based release notes |
| `charter` | Compile prose guidance into addressable rules |
| `checklist` | Update a cumulative private check |
| `checkpoint` | Record a recoverable handoff point |
| `checksums` | SHA-256 manifest over every tracked file |
| `claim` | Record a claim; unsupported claims are downgraded, not warned about |
| `config` | Validate every .godmode-*.json config file |
| `context` | Inspect or rebuild context continuity |
| `db` | Record database governance state |
| `docs` | Record documentation obligations, or reconcile the trigger table |
| `doctor` | Verify archive and continuity health |
| `drift` | Compare step sets across sessions and agents |
| `egress` | Disclose exactly what an action would send |
| `environment` | Classify a mutation target's blast radius; unknown fails closed |
| `evals` | Execute the authored skill evals: routing accuracy plus snapshot diff |
| `experiment` | Run the declared bounded experiment loop from .godmode-experiment.json |
| `explain-context` | Explain included and excluded continuity data |
| `export` | Write a sanitized context report |
| `gate` | Check a trigger; exit non-zero when a HARD rule is unattested |
| `grid` | Attack every enforcement control; report each cell's observed result |
| `guard` | Preview and authorize an exact operation without executing it |
| `history` | Read structured local history |
| `init` | Initialize the private local archive |
| `inspect` | Capture an on-demand repository snapshot |
| `integrity` | Run the nine test-integrity monitors over the current diff |
| `inventory` | Repository inventory operations |
| `lessons` | The promote-or-retire pipeline over recorded lessons |
| `locale` | Localized guidance surfaces |
| `loop` | Detect repetition the repeating agent cannot see |
| `method` | Select an analysis method from the evidence shape |
| `mistakes` | Run the mistake-class detectors |
| `netgate` | Prove the CLI surfaces make zero network connections |
| `operator` | Validate the typed operator profile |
| `parity` | Compare neutral structure with an explicit local reference |
| `plan` | Record a private execution contract |
| `planmode` | Gate mutation behind an approved plan contract |
| `plant` | Prove a guard fails by planting a violation |
| `privacy` | Audit the local privacy boundary |
| `recurrences` | Find controls that blocked twice on the same cause |
| `reflect` | Check a claim against what the record already says |
| `remember` | Record a decision, invariant, lesson, or obligation |
| `removal` | Remember why something was deleted |
| `report` | Emit a sanitized bounded report |
| `resume` | Build a bounded continuity brief |
| `rewind` | Preview a rollback to a prior verified checkpoint |
| `roles` | Resolve authority documents by role |
| `sbom` | List what ships and what it depends on |
| `scenarios` | Stage known failures and check a control notices |
| `scope` | Enumerate the work before reasoning about it |
| `selftest` | Exercise every control and report what actually held |
| `session` | Open or close an attested session |
| `skill` | Validate or forge a project skill |
| `slice` | Read a bounded window that declares its own edges |
| `sprint` | Record private sprint state |
| `status` | Single writable status store |
| `untrusted` | Report repository text shaped like an instruction |
| `verify` | Run a declared check and attest its exit code |
| `version` | Record a version fact, or reconcile every surface |
| `watch` | Per-boundary anomaly scan over this session's attestations |

Run `python scripts/godmode.py <command> --help` for flags and sub-verbs.

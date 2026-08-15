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
    prose-quality note. Population sweep: this repo's own two negation-heavy
    HARD gates in `GODMODE.md` were rewritten to positive form (still HARD,
    same enforcement); the 3 remaining ADVISORY sentence-fragment rules are
    accepted as-is (already reviewed - see
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
    soften an existing R5 refusal to an ask.

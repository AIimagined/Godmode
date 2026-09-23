"""NS-12a + NS-12d (0.3.28 Plan 5 Task 9): the skill-impact ledger and the
strict-improvement gate.

The ablation this gate follows is the whole argument: gate a skill change
on validation score, or the loop rubber-stamps itself the same way a
checker that can never fail proves nothing (NS-4's falsification bonds, the
sibling gate this one composes with). Two record-writers -
`atlas law ratify` (`godmode_bonds.ratify`) and `skill forge`
(`godmode_forge.forge_skill` via `cmd_skill_forge`) - are the only paths
that change what a skill IS, so both write the same kind here, never a
second drifting ledger.

Kind `skill_impact` {target, diff_hash, score_before, score_after,
outcome in {accepted, rejected}, patterns: [seqs]}. Two rules, both
mechanical, neither a vibe:

1. NS-12a: a proposal whose diff hash matches a PREVIOUSLY REJECTED
   `skill_impact` is refused, naming that record's own sequence
   (`refuse_if_diff_previously_rejected`, called from
   `godmode_bonds.propose` and from `evaluate_forged_skill`, forge's own
   entry point since it has no separate propose step to hook into).
2. NS-12d: a change is `accepted` only when its `score_after` STRICTLY
   improves on the best `score_after` any earlier ACCEPTED impact for the
   same `target` ever recorded (or, with no such record, on the change's
   OWN `score_before` - the first change must still beat doing nothing).
   A tie is `rejected` - "neutral -> rejected" is the spec's own words,
   never a `>=` comparison that would call a no-op an improvement. On
   `rejected`, the target is restored to the bytes captured before the
   change was applied (or removed, for a target that did not exist
   before) - never the operator's own `git checkout`, which nothing here
   invokes.

The validation score is the eval harness's own per-skill numbers, not a
re-derivation: the mean of `godmode_evals.routing_scores`' per-skill 0..1
routing score and `godmode_evals.run_behavior_assertions`' per-skill
passed/executable ratio (a skill with zero executable assertions scores a
neutral 1.0 on that half, so a suite that is still all declared-only
cannot itself gate a proposal). Formula, per skill:

    score = (routing_score + behavior_score) / 2

where `routing_score = (positives_routed_home + near_negatives_rejected) /
(positives_total + near_negatives_total)` and `behavior_score =
passed / executable` when `executable > 0`, else `1.0`. A skill that does
not exist yet, or a project with no eval suites at all, scores `0.0` -
there is nothing to validate.

Three things the reader should know about the edges here, because none of
them is obvious from the rules above:

- `target` is proposer-supplied and reaches both rules as a free-form
  string, so every record written here keys on its CANONICAL spelling
  (`canonical_target`, and `_contained_skill_path`'s project-relative
  return value once a project is in reach). `skills\\demo\\state.py`,
  `./skills/demo/state.py`, `skills/./demo/state.py` and (on Windows)
  `skills/demo/STATE.PY` are ONE file on disk, so they are one key here
  too - otherwise a rejection is laundered by a keystroke and the
  best-so-far floor is erased by the same keystroke.
- the eval-input refusal (`_eval_harness_inputs`) is TEXTUAL: it reads the
  argv tokens of each `behavior_assertions[*].check.command`. A probe
  spelled `python -m pkg.mod`, or one that opens a data file of its own,
  names no argv path token and is therefore outside the refusal. No
  shipped suite has either shape today; a suite author who writes one is
  re-opening a self-grading path, and closing that class properly needs
  the frozen-graded-set design, not a wider text scan. Likewise, only the
  TARGET skill's own suite is consulted: a `check.command` in skill A
  naming a file under `skills/B/` is unprotected when B is the target -
  fail-closed in practice (rewriting A's grader cannot move B's score),
  noted here so it is not mistaken for coverage.
- a `<project>/skills` that is a symlink out of the project disables this
  gate entirely: every target then fails containment and is refused. That
  is the safe direction, and `_contained_skill_path` says so by name
  rather than blaming the target.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import shlex
import shutil
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError, GodmodeError
from .godmode_evals import load_suites, routing_scores, run_behavior_assertions

SKILL_IMPACT_OUTCOMES = ("accepted", "rejected")


def skill_name_from_target(target: str) -> str | None:
    """`skills/<name>/...` (or `.grok/skills/<name>/...`) -> `<name>`;
    anything with no `skills/<name>` segment -> None, meaning "not a skill
    change" - the strict-improvement gate applies only when this resolves,
    so a law or guard proposal is untouched by NS-12.
    """
    parts = Path(str(target).replace("\\", "/")).parts
    for index, part in enumerate(parts):
        if part == "skills" and index + 1 < len(parts):
            candidate = parts[index + 1]
            if candidate:
                return candidate
    return None


def canonical_target(target: str) -> str:
    """One spelling per target, computed from the string alone.

    Both NS-12 rules key on `target`, and both are defeated by a respelling
    when the key is the raw string: the filesystem effect goes through
    `_contained_skill_path`, which folds separators, `.` components,
    doubled separators and trailing separators, so four different strings
    reach the same file while carrying four different keys. A rejection
    recorded against one spelling then refuses none of the others, and the
    best-so-far floor recorded against one spelling is invisible to the
    others - the strict-improvement gate collapses back to "beat the live
    score" exactly when the live score has drifted below the recorded
    ceiling.

    This is the string-only half, for callers with no project in reach
    (`godmode_bonds.propose` holds a target but no project root). It does
    NOT fold case, because case-folding is a filesystem property, not a
    string property; `_contained_skill_path` returns the fully canonical
    form - the same `resolve()` the write uses - wherever a project root
    is available, and that one does fold Windows case.
    """
    return PurePosixPath(str(target).replace("\\", "/")).as_posix()


def canonical_skill_target(target: str, project: Path | None = None) -> str:
    """The one key both NS-12 rules use, as canonical as the caller's reach
    allows: the string-only fold always, plus the filesystem fold (which is
    what makes `skills/demo/STATE.PY` and `skills/demo/state.py` one key on
    Windows) whenever a project root is in reach and the target really does
    land under `<project>/skills/`.

    A target that cannot be contained falls back to the string-only form
    rather than raising: `propose` is a labelling verb and refusing a
    free-form target there would change what it accepts. The containment
    refusal still happens at the one place it must - the write itself.
    """
    text = canonical_target(target)
    if project is None or skill_name_from_target(text) is None:
        return text
    try:
        return _contained_skill_path(project, text)[1]
    except (GodmodeError, OSError, ValueError):
        return text


def validate_pattern_seqs(patterns: list[int] | None) -> list[int]:
    """The same shape `_skill_impact_invariants` requires of `patterns`,
    checked BEFORE anything is written to disk rather than at the append.

    `--pattern` is proposer-supplied on both writers, and `argparse`'s
    `type=int` accepts `0` and `-1` happily. Left to the invariant, such a
    value raises inside `archive.append` - i.e. AFTER the outcome has been
    decided and the filesystem already changed - which is a documented flag
    value that buys a forged skill on disk with no record of the attempt.
    Both writers call this first, so a malformed citation costs the
    proposer a refusal instead of an unrecorded change.
    """
    seqs = list(patterns or [])
    bad = [p for p in seqs if not isinstance(p, int) or isinstance(p, bool) or p <= 0]
    if bad:
        raise ArchiveError(
            "--pattern must cite positive sequence numbers (the pattern "
            f"records this change stands on); refused: {bad} - nothing was "
            "written, so re-run with real sequences from `godmode history`."
        )
    return seqs


def skill_score(project: Path, skill: str) -> float:
    """The validation score NS-12d gates on - see the module docstring for
    the exact formula. Every failure mode (no suites at all, this skill
    absent from the suites) reads as `0.0`, never a raised error: a score
    is being computed to compare against a baseline, and "nothing to
    compare" is itself informative, not a crash.
    """
    try:
        routing = routing_scores(project)
    except GodmodeError:
        return 0.0
    routing_row = routing.get(skill)
    if routing_row is None:
        return 0.0
    try:
        behavior = run_behavior_assertions(project)
    except GodmodeError:
        return 0.0
    block = behavior["skills"].get(skill)
    if block and block.get("executable", 0) > 0:
        behavior_component = block["passed"] / block["executable"]
    else:
        behavior_component = 1.0
    return round((routing_row["score"] + behavior_component) / 2.0, 4)


def scan_impacts(
    archive: Chronicle, target: str, diff_hash: str | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    """ONE pass over `read_events` answering both NS-12 questions at once:
    the highest `score_after` any ACCEPTED `skill_impact` for `target` ever
    recorded (the floor NS-12d's gate compares against, `None` when this
    target has never been accepted), and the most recent REJECTED
    `skill_impact` for `(target, diff_hash)` (NS-12a's refusal, `None` when
    `diff_hash` is `None` or nothing matches).

    Both comparisons run on `canonical_target` of BOTH sides, so a
    respelling of the same path reads the same history. Without that, the
    rejection is laundered by writing `skills\\demo\\x.py` instead of
    `skills/demo/x.py`, and the floor is erased the same way.

    The rejected match is scoped to `target` as well as the hash: the same
    diff BYTES against a different target is a different change (diff
    artifacts here are whole-file contents, and near-identical files land
    across several skills), and must not be refused as a re-proposal of one
    already tried.

    `read_events` is used directly (never `select`, which
    `godmode_bonds.py` already documents as silently clamping to the most
    recent 500 records of a kind) so a diff rejected long ago still refuses
    a re-proposal today.
    """
    wanted = canonical_target(target)
    best: float | None = None
    match: dict[str, Any] | None = None
    for record in archive.read_events(verify=False):
        if record.get("kind") != "skill_impact":
            continue
        data = record.get("data") or {}
        if canonical_target(str(data.get("target", ""))) != wanted:
            continue
        outcome = data.get("outcome")
        if outcome == "accepted":
            score = data.get("score_after")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                if best is None or score > best:
                    best = float(score)
        elif (
            outcome == "rejected"
            and diff_hash is not None
            and data.get("diff_hash") == diff_hash
        ):
            match = record
    return best, match


def best_recorded_score(archive: Chronicle, target: str) -> float | None:
    """The floor NS-12d's gate compares the next change against - see
    `scan_impacts`, which this is the one-answer spelling of."""
    return scan_impacts(archive, target)[0]


def rejected_diff(archive: Chronicle, diff_hash: str, target: str) -> dict[str, Any] | None:
    """The most recent REJECTED `skill_impact` naming this `(diff_hash,
    target)` pair, or None - see `scan_impacts`."""
    return scan_impacts(archive, target, diff_hash)[1]


def accepted_impact_for_skill(archive: Chronicle, skill: str) -> dict[str, Any] | None:
    """The first ACCEPTED `skill_impact` whose target belongs to `skill`,
    by SKILL NAME rather than by an exact target string.

    `evaluate_forged_skill`'s own guard needs this: it refuses to delete a
    directory for a name that already has accepted history, but the records
    that history leaves behind are keyed `skills/<name>/<file>` when they
    came through `atlas law ratify` (the normal case for an established
    skill) and only `skills/<name>` when they came through a prior forge.
    Matching the exact string catches the second and misses the first,
    which is the wrong half.
    """
    for record in archive.read_events(verify=False):
        if record.get("kind") != "skill_impact":
            continue
        data = record.get("data") or {}
        if data.get("outcome") != "accepted":
            continue
        if skill_name_from_target(str(data.get("target", ""))) == skill:
            return record
    return None


def refuse_if_diff_previously_rejected(archive: Chronicle, diff_hash: str, target: str) -> None:
    """NS-12a's acceptance test, verbatim: refused, naming the prior seq.

    The message names the CANONICAL target, not the spelling the caller
    happened to use, so a proposer who respelled the path is told which
    file the refusal is actually about.
    """
    _refuse_prior_rejection(diff_hash, target, rejected_diff(archive, diff_hash, target))


def _refuse_prior_rejection(
    diff_hash: str, target: str, prior: dict[str, Any] | None,
) -> None:
    """NS-12a's refusal message, shared by the standalone check above and
    by `apply_skill_diff`'s own folded scan so the two cannot drift."""
    if prior is not None:
        raise ArchiveError(
            f"diff {diff_hash[:12]}... was already tried and rejected against "
            f"{canonical_target(target)!r} at seq:{prior['sequence']} (skill_impact); propose a "
            "different change, not the same diff again - the proposer is "
            "expected to read this ledger before proposing (NS-12a)."
        )


def gate_outcome(score_before: float, score_after: float, best_so_far: float | None) -> str:
    """NS-12d: accepted only on STRICT improvement over the higher of
    `best_so_far` and `score_before` (with no `best_so_far` recorded yet,
    over `score_before` alone); a tie is `rejected` - the spec states
    "neutral -> rejected" verbatim, never a `>=` comparison.

    `best_recorded_score` keys on one canonical `target`, but the score
    it stores is skill-wide - so a DIFFERENT target for the same skill can
    hold a lower ceiling than where the skill actually stands today (an
    accepted change to a sibling file, or routing-corpus drift from a newly
    forged sibling skill). Taking the max of the two closes that gap: a
    change must beat both the best any target for this skill has ever
    recorded AND where the skill actually is right now, so neither a stale
    per-target ceiling nor an unnoticed regression can be beaten by
    accident.
    """
    baseline = max(best_so_far, score_before) if best_so_far is not None else score_before
    return "accepted" if score_after > baseline else "rejected"


def record_impact(
    archive: Chronicle,
    target: str,
    diff_hash: str,
    score_before: float,
    score_after: float,
    outcome: str,
    patterns: list[int] | None = None,
) -> dict[str, Any]:
    if outcome not in SKILL_IMPACT_OUTCOMES:
        raise ArchiveError(
            f"skill_impact outcome must be one of {SKILL_IMPACT_OUTCOMES}, not {outcome!r}"
        )
    pattern_seqs = list(patterns or [])
    data = {
        "target": target,
        "diff_hash": diff_hash,
        "score_before": float(score_before),
        "score_after": float(score_after),
        "outcome": outcome,
        "patterns": pattern_seqs,
    }
    return archive.append(
        "skill_impact", target, data,
        evidence=[f"seq:{seq}" for seq in pattern_seqs],
    )


def diff_hash_of(diff_path: str | Path) -> str:
    path = Path(diff_path)
    if not path.is_file():
        raise ArchiveError(f"--diff names a missing file: {diff_path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contained_skill_path(project: Path, target: str) -> tuple[Path, str]:
    """Resolve `project / target`, refuse anything that is not a
    project-relative path landing under `<project>/skills/` (B4), and
    return BOTH the resolved path the write uses and its project-relative
    canonical string.

    The canonical string is the key every record written here uses. It has
    to come from this function rather than from `canonical_target` alone,
    because only the `resolve()` done here folds Windows filename case -
    and `skills/demo/STATE.PY` is the same file as `skills/demo/state.py`
    on the filesystem whether or not it is the same string.

    `target` reaches here proposer-supplied and free-form (`propose` never
    validates it as a path - it stays a label right up until this task
    turns it into a filesystem write). `skill_name_from_target` only
    requires a `skills/<name>` segment to appear SOMEWHERE in the parts, so
    `../../elsewhere/skills/x/payload.py` still resolves a skill name while
    escaping the project entirely, and an absolute target replaces the
    project root outright under plain `pathlib` join semantics. Both are
    refused here explicitly (not only via the post-`resolve()` containment
    check) so the message names the actual problem instead of a generic
    "outside the project". The idiom mirrors the existing containment
    checks in `godmode_egress.py` and `godmode_console.py`.
    """
    raw = str(target).replace("\\", "/")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.anchor:
        raise ArchiveError(
            f"target must be a project-relative path, not absolute: {target!r}; "
            "use a path like skills/<name>/<file>"
        )
    if ".." in candidate.parts:
        raise ArchiveError(
            f"target must not contain '..': {target!r}; use skills/<name>/<file> "
            "directly, not a path that climbs out of the project"
        )
    project_root = project.resolve()
    skills_root = (project_root / "skills").resolve()
    # N10: without this, a project whose `skills` is a symlink out of the
    # tree reports "target escapes the project" for EVERY target, sending
    # the operator to look at the target instead of at the symlink. The
    # refusal is the same either way - a symlinked `skills` disables this
    # gate entirely, which is the fail-closed direction - but it should say
    # what is actually wrong.
    if not skills_root.is_relative_to(project_root):
        raise ArchiveError(
            "<project>/skills resolves outside the project "
            f"({skills_root}); the strict-improvement gate refuses every "
            "target until that is fixed - it only ever writes inside a "
            "skill's own directory, inside the project."
        )
    resolved = (project_root / candidate).resolve()
    if not resolved.is_relative_to(project_root):
        raise ArchiveError(f"target escapes the project: {target!r}")
    if not resolved.is_relative_to(skills_root):
        raise ArchiveError(
            f"target must be under skills/: {target!r}; the strict-improvement "
            "gate only ever writes inside a skill's own directory"
        )
    return resolved, resolved.relative_to(project_root).as_posix()


def _eval_harness_inputs(project: Path, skill: str) -> set[Path]:
    """Every filesystem path this skill's OWN pre-change eval suite reads to
    compute its score (B1): the suite file itself, and any path a
    `behavior_assertions[*].check.command` names as an argv token (a
    probe script living inside the same skill directory, exactly the
    fixture shape this branch's own tests use).

    The suite path is protected WHETHER OR NOT IT EXISTS YET, and that is
    the whole point rather than a detail. Protecting only a suite already
    on disk closes the editing case and leaves the creating case wide open:
    a target naming a suite for a skill that does not exist yet is written
    by this gate (`mkdir(parents=True)` and all), and then graded by
    `load_suites`, which globs `skills/*/godmode-evals.json` - i.e. by the
    file the proposal itself just wrote. Two positives sharing a coined
    token route home under the leave-one-out corpus (routing 1.0) and a
    suite with no executable assertions takes the neutral behaviour branch
    (1.0), so the fabricated yardstick scores a perfect 1.0 against a skill
    that has no SKILL.md and no behaviour at all. That same file also joins
    the SHARED routing corpus every other skill is scored against, so the
    creating case is a corpus-poisoning primitive on top of a self-grading
    one. `skills/*/godmode-evals.json` is exactly one filename at exactly
    one depth, so this single unconditional path closes the whole class.

    A diff whose `target` is one of these paths could move `score_after`
    by rewriting the yardstick rather than the skill: dropping the one
    failing `behavior_assertion`, or adding routing positives whose tokens
    overlap the description, both move the score without the skill's
    behaviour changing at all. `apply_skill_diff` refuses any such target
    outright (see its own docstring for why refusal, not freezing, is the
    fix taken here) rather than trying to compute a score that is honest
    despite the diff.
    """
    protected: set[Path] = set()
    eval_path = project / "skills" / skill / "godmode-evals.json"
    protected.add(eval_path.resolve())
    try:
        suites = load_suites(project)
    except GodmodeError:
        return protected
    suite = suites.get(skill)
    if suite is None:
        return protected
    for entry in suite.get("behavior_assertions", []):
        if not isinstance(entry, dict):
            continue
        check = entry.get("check")
        if not isinstance(check, dict):
            continue
        command = str(check.get("command", "")).strip()
        if not command:
            continue
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        for token in tokens:
            token_path = Path(token)
            candidate = token_path if token_path.is_absolute() else project / token_path
            try:
                protected.add(candidate.resolve())
            except OSError:
                continue
    return protected


def _is_protected(path: Path, protected: set[Path]) -> bool:
    """N5: membership is "IS one of the protected paths, or is UNDER one".

    A `check.command` argv token can name a DIRECTORY - the shipped
    skill-forge suite runs `skill validate --path skills/<name>`, so the
    protected entry is the skill directory itself and every file beneath it
    is a grading input. Exact-path membership would protect only the
    directory's own name and leave the files that actually grade the change
    writable by the change.
    """
    return any(path == entry or path.is_relative_to(entry) for entry in protected)


def _restore(path: Path, pre_bytes: bytes | None, created_dirs: list[Path]) -> None:
    """Put the target back the way it was: the captured bytes, or removal
    for a target that did not exist, plus any directory THIS call created
    and left empty (N1). Never a `git checkout` - nothing here shells out
    to git, and the operator's working tree is not this function's to
    rewrite. `created_dirs` is innermost-first, so the walk stops at the
    first directory something else has since put a file into.
    """
    if pre_bytes is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(pre_bytes)
    for directory in created_dirs:
        try:
            directory.rmdir()
        except OSError:
            break


def apply_skill_diff(
    archive: Chronicle,
    project: Path,
    target: str,
    diff_path: str | Path,
    patterns: list[int] | None = None,
) -> dict[str, Any]:
    """Apply a proposed skill change, score it, and gate it - called by
    `atlas law ratify` once NS-4's falsification-bond checks already
    passed. `target` must resolve to a `skills/<name>/...` path (checked
    by the caller via `skill_name_from_target`).

    Godmode's proposal diffs are hashed opaquely at `propose` time
    (`godmode_bonds.propose` reads `--diff <file>` only to hash it, never
    to parse it - there is no unified-diff engine in this stdlib-only
    codebase, and NS-4 never asked for one). This carries that same
    convention forward: the diff artifact IS the target file's proposed
    new full contents, written verbatim over `project / target` (contained
    to a `skills/...` path under `project` - see `_contained_skill_path`,
    B4). The bytes at that path before the write are captured first, and
    are exactly what a `rejected` outcome - or ANY exception raised once
    the write has happened - restores; never the operator's own `git
    checkout`, which this function never invokes. A target with no prior
    file is restored by removal.

    `target` is refused outright, before anything is written, when it IS
    one of the skill's own eval-harness inputs (`_eval_harness_inputs`,
    B1): the suite file itself, or a behaviour-assertion probe script the
    suite's own `check.command` names. Scoring a diff against the very
    file that grades it is not gradeable by its own grader - the fix taken
    here is refusal, not a frozen-snapshot re-score, because refusal is
    the one option that cannot itself be gamed by a diff shaped to look
    like an innocuous edit to the grading inputs; a skill's eval suite is
    edited by a separate, independently reviewed change, never through
    this gate.
    """
    skill = skill_name_from_target(target)
    if skill is None:
        raise ArchiveError(
            f"target {target!r} is not a skills/<name>/... path; the "
            "strict-improvement gate only applies to skill changes"
        )
    # R3: proposer-supplied `--pattern` values are checked BEFORE anything
    # is written, not at the append, so a documented flag value cannot buy
    # an applied change with no record of the attempt.
    pattern_seqs = validate_pattern_seqs(patterns)
    diff_path = Path(diff_path)
    diff_hash = diff_hash_of(diff_path)
    path, key = _contained_skill_path(project, target)
    protected = _eval_harness_inputs(project, skill)
    if _is_protected(path, protected):
        raise ArchiveError(
            f"target {target!r} is itself an eval-harness input for skill "
            f"{skill!r} (the suite's own godmode-evals.json - whether or not "
            "it exists yet - or a path a behavior-assertion check.command "
            "names) - a diff to the file that grades a change is not "
            "gradeable by its own grader; edit the eval suite through a "
            "separate, independently reviewed change, not through "
            "`atlas law ratify`."
        )
    # N2: a directory target makes `pre_bytes` None, then raises out of
    # `write_bytes`, then raises a SECOND time out of the restore's own
    # `unlink` - so the operator is shown the handler's error instead of
    # the real one. Refused up front, next to the eval-harness refusal.
    if path.is_dir():
        raise ArchiveError(
            f"target {target!r} is a directory; the strict-improvement gate "
            "applies a diff to ONE file - name the file inside it."
        )
    # Nit 2 + N8: `propose` already refuses a previously-rejected diff, but
    # a refused ratify writes no `improvement_verdict` (by design - the
    # proposal stays open), so the SAME proposal can be re-ratified with a
    # fresh bond. Guard here too, in defence in depth, scoped to this exact
    # target (nit 1) - and take the best-so-far floor out of the SAME pass,
    # since the archive cannot change between the two questions.
    best_so_far, prior_rejected = scan_impacts(archive, key, diff_hash)
    _refuse_prior_rejection(diff_hash, key, prior_rejected)
    pre_bytes: bytes | None = path.read_bytes() if path.is_file() else None
    # N1: `mkdir(parents=True)` below can create a whole directory tree for
    # a new-file target. A rejected proposal used to leave that tree behind
    # empty, and because `forge_skill` refuses outright when the directory
    # already exists, one rejected proposal permanently denied
    # `skill forge <that name>`. Record what did not exist beforehand,
    # innermost first, and undo it on the restore path.
    created_dirs: list[Path] = []
    probe = path.parent
    while not probe.exists() and probe.is_relative_to(project.resolve()):
        created_dirs.append(probe)
        probe = probe.parent
    score_before = skill_score(project, skill)
    outcome: str | None = None
    score_after: float | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(diff_path.read_bytes())
        score_after = skill_score(project, skill)
        outcome = gate_outcome(score_before, score_after, best_so_far)
        if outcome == "rejected":
            _restore(path, pre_bytes, created_dirs)
        record = record_impact(
            archive, key, diff_hash, score_before, score_after, outcome, pattern_seqs,
        )
    except Exception as original:
        # B2: ANY exception once the write has happened - a non-GodmodeError
        # raise out of `skill_score` (an unbalanced quote in a proposer's own
        # `check.command` failing `shlex.split`, or a non-numeric
        # `expect_exit` failing `int(...)` - see `godmode_evals.py`), or an
        # invariant failure out of `record_impact`'s own `archive.append` -
        # restores the pre-change bytes and re-raises, so nothing is ever
        # left half-applied with no record to show for it.
        try:
            _restore(path, pre_bytes, created_dirs)
        except Exception as restore_error:
            # N3: the restore can itself fail (a read-only file, a full
            # disk, a lock). Silently letting THAT exception replace the
            # original tells the operator the wrong story about a file that
            # is now sitting in the proposed state with no record of it.
            raise ArchiveError(
                f"{target!r} was changed, the change could not be scored "
                f"({original!r}), AND the restore to its pre-change bytes "
                f"failed ({restore_error!r}): the file is left in the "
                "PROPOSED state and no skill_impact was written. Restore it "
                "yourself before re-proposing."
            ) from original
        raise
    return {
        "sequence": record["sequence"],
        "target": key,
        "diff_hash": diff_hash,
        "score_before": score_before,
        "score_after": score_after,
        "best_recorded": best_so_far,
        "outcome": outcome,
        "restored": outcome == "rejected",
    }


def hash_skill_tree(skill_dir: Path) -> str:
    """A stable content hash over every file `forge_skill` just wrote - the
    "diff from nothing" a brand-new skill stands in for, since forge
    authors structured fields into a fresh tree rather than a unified
    diff against an existing file.
    """
    digest = hashlib.sha256()
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(skill_dir).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluate_forged_skill(
    archive: Chronicle,
    eval_project: Path,
    skill_dir: Path,
    patterns: list[int] | None = None,
) -> dict[str, Any]:
    """NS-12a + NS-12d for `skill forge`: the skill did not exist before
    this call, so `score_before` is fixed at `0.0` by definition. Forge has
    no separate `propose` step of its own, so NS-12a's previously-rejected
    check is applied here instead, against the hash of the tree forge just
    wrote; a match removes the just-created directory and refuses, naming
    the prior seq, exactly like a re-proposal would be refused.

    R3: this is the SECOND of the two writers, and it mutates the
    filesystem (`shutil.rmtree` on the rejected branch) before it appends.
    It carries the same write-then-restore guarantee `apply_skill_diff`
    does: an exception raised once the outcome has been decided removes the
    directory this forge created and re-raises, so there is no state where
    a forged skill sits on disk with no record of the attempt. The
    proposer-supplied `patterns` are checked first of all, before anything
    is touched, because that is the cheapest way to make the guarantee
    unnecessary.
    """
    name = skill_dir.name
    target = f"skills/{name}"
    pattern_seqs = validate_pattern_seqs(patterns)
    # Nit 3: `forge_skill` refuses an existing directory outright, and
    # `cmd_skill_forge` only ever passes the directory it JUST created, so
    # the shipped call path cannot reach this function with a pre-existing
    # skill's directory. But this function itself takes any `skill_dir` -
    # its own test in this branch calls it directly - so the safety must
    # not live only in call ordering. A skill name with a prior ACCEPTED
    # `skill_impact` record is, by definition, not a fresh forge: refuse
    # before doing anything destructive rather than trusting the caller.
    # N9: matched by SKILL NAME, not by the exact `skills/<name>` string -
    # an established skill's accepted history is keyed
    # `skills/<name>/<file>` (that is what `atlas law ratify` writes), so
    # the exact-string match protected only names with a prior FORGE accept
    # and left every ratified skill unguarded.
    prior_accept = accepted_impact_for_skill(archive, name)
    if prior_accept is not None:
        raise ArchiveError(
            f"skill {name!r} already has an accepted skill_impact record "
            f"(seq:{prior_accept['sequence']}, target "
            f"{prior_accept['data'].get('target')!r}); evaluate_forged_skill "
            "only guards a directory THIS call is responsible for creating, "
            "and a name with prior accepted history is not a fresh forge - "
            "it must never be deleted by this path."
        )
    diff_hash = hash_skill_tree(skill_dir)
    prior = rejected_diff(archive, diff_hash, target)
    if prior is not None:
        shutil.rmtree(skill_dir, ignore_errors=True)
        raise ArchiveError(
            f"This exact skill content was already tried and rejected at "
            f"seq:{prior['sequence']} (skill_impact); change the skill "
            "before forging it again."
        )
    score_before = 0.0
    # N8: the own-guard above has already proven there is no accepted
    # record for this skill, so the baseline cannot be anything but None -
    # re-walking the archive to be told that again was dead work.
    baseline: float | None = None
    try:
        score_after = skill_score(eval_project, name)
        outcome = gate_outcome(score_before, score_after, baseline)
        if outcome == "rejected":
            shutil.rmtree(skill_dir, ignore_errors=True)
        record = record_impact(
            archive, target, diff_hash, score_before, score_after, outcome, pattern_seqs,
        )
    except Exception as original:
        # R3: the outcome has been decided and the filesystem already
        # reflects it, so an exception from here on would otherwise leave a
        # forged skill on disk with no skill_impact and no decision record
        # - the exact bypass this gate exists to refuse. Undo the forge and
        # re-raise. On the rejected branch the directory is already gone,
        # and `rmtree(ignore_errors=True)` is a no-op there.
        shutil.rmtree(skill_dir, ignore_errors=True)
        raise ArchiveError(
            f"Forged skill {name!r} could not be scored and recorded "
            f"({original!r}); the directory this forge created was removed, "
            "so nothing is left on disk without a record of the attempt."
        ) from original
    return {
        "sequence": record["sequence"],
        "target": target,
        "diff_hash": diff_hash,
        "score_before": score_before,
        "score_after": score_after,
        "best_recorded": baseline,
        "outcome": outcome,
        "removed": outcome == "rejected",
    }

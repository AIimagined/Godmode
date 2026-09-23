"""I-6: closure attestation before commit.

`atlas closure <files>` (`godmode_atlas.unfollowed_dependents`) already answers
"what depends on this and was not itself touched" - a report a reader has to
think to run. `godmode retest --run` already runs and attests the tests that
pin a changed file. Neither is checked at the one moment closure actually
matters: `git commit`. `closure_survey` below is that check, read by
`godmode_githooks._evaluate_pre_commit` unconditionally - no declared-policy
gate, no capability escape, the same as that file's version-drift and
private-term checks: a stale closure claim shipped in a commit is a fact
about that commit forever, not a risk a later commit can retroactively fix.

**Scope (coordinator ruling, stated once here and on every result this
module returns).** The 0.3.28 design spec (I-6, Sec 10b)
says "every file in the staged diff".
The atlas (`godmode_atlas.build`) only ever indexes code it can parse into
symbols and edges - closure is a claim about a dependency graph, and a
graph has nothing to say about a file it never put a node on. This project's
own indexed code is Python under `scripts/`, `hooks/`, `tests/`; nothing else
here has a closure to check. A staged doc, changelog fragment, fixture, or
JSON table is exempt, not overlooked. A staged DELETION is exempt too (fix
round 1, S4): a file that no longer exists has no closure of its own to
attest, and its dependents are what `unfollowed_dependents` already answers
for the surviving staged files.

**"Citing the file."** A `retest:*` attestation (`godmode_attest.run_check`,
called from `cmd_retest`) stores the module list it ran structurally
(`data["modules"]`, fix round 1 S1) whenever its caller supplies one; the
one evidence entry, `cmd:<command line>`, is truncated at 160 characters and
is read only as a fallback for an older record with no `modules` field. The
link back to a source file is: which test files pin it
(`godmode_retest.pinning_tests`) or pin a dependent of it
(`godmode_atlas.unfollowed_dependents`, depth 1) - a retest attestation whose
module set (structural, or tokenised from the citation) intersects those
test modules AS WHOLE NAMES (fix round 1, S2 - never a substring test, which
let a retest of `tests.test_atlas` count as a retest of `tests.test_atlas_
registry`) counts as covering the file.

**Uncovered files (fix round 1, S3, coordinator ruling).** A file no test
pins at all - directly or through a dependent - cannot be cleared by
`retest --run`: there is nothing for it to run. Refusing such a file under
the "stale" remedy ("run `godmode retest --run`") is a dead end, so it is
its own category (`uncovered_staged_files`), with its own remedy ("add a
pinning test"), and is never present in `stale_staged_files`'s own list.

**"No edit record."** `edit-recorded` (`hooks/godmode_post_edit.py`) fires
only for the tool names its own `_EDIT_TOOL_NAMES` matches - a git-applied
patch or an edit made outside that tool surface leaves no such record. Ruled
here (not assumed): a staged file with no `edit-recorded` at all still needs
a retest UNLESS its staged content is provably the same content a green
retest already covered. Fix round 2 (D5): the preferred proof is a
per-path blob hash `godmode_attest.run_check` records (`blob_paths=`,
threaded from `cmd_retest`, `git hash-object` at the moment the retest ran)
- this fires even on the dirty tree the normal edit-then-retest-then-commit
flow always has. The older, coarser fallback (a green retest that ran
against a fully clean tree, so its recorded HEAD blob is exactly what it
tested) still applies to an attestation with no per-path capture at all.
Neither proof matching, or no green retest at all, lands the file in its
own `unattested` bucket - never `stale` (whose remedy, "stage the retest
result", is a no-op when there was never an edit record to begin with).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_atlas import (
    Atlas,
    build as build_atlas,
    load_index,
    rehydrate_index,
    save_index,
    unfollowed_dependents,
)
from .godmode_constants import EDIT_RECORD_SUBJECT
from .godmode_errors import GodmodeError
from .godmode_metrics import action_paths
from .godmode_retest import cited_modules, retest_module_names

# The atlas's own real coverage for this project - narrower than every
# language `godmode_atlas.build` can parse in general. Only Python under
# these three trees has symbols, edges, or a closure to check here.
_CLOSURE_ROOTS = ("scripts/", "hooks/", "tests/")
# Fix round 2 (D2i): the same three trees, as bare directory names rather
# than path-prefix strings, for `godmode_atlas.build`'s own `roots=`
# parameter - this caller never needs anything outside them, so the walk
# itself is scoped down rather than filtered down after the fact.
_CLOSURE_ROOT_DIRS = tuple(root.rstrip("/") for root in _CLOSURE_ROOTS)

# S5 (fix round 1): the conventional location a project keeps a saved atlas
# index at, so this check can use it without any wiring beyond `godmode
# atlas save --to .godmode-atlas-index.json` kept up to date. Purely a
# convention this module reads - `godmode_atlas.save_index`/`load_index`
# take an arbitrary path and know nothing about this name. Fix round 2
# (D2): also wired to write itself, via `refresh_atlas_index` below, called
# from `cmd_retest` after a successful `--run`.
_ATLAS_INDEX_FILENAME = ".godmode-atlas-index.json"

# A rebuild this check falls back to (no fresh saved index) is bounded so an
# unreadable or enormous repository fails within seconds, with a stated gap,
# never five minutes of silence (`godmode_atlas.build`'s own docstring names
# that exact failure mode). Fix round 3 (coordinator ruling, re-review 2):
# round 2's 60s comment cited a 13.07s/8.68s figure measured on a WARM
# fix-round-2 worktree; the re-review measured the same closure-scoped build
# on this repository's own MAIN WORKING CHECKOUT, cold-process each time
# (a pre-commit hook is always a fresh process): 52.10s, 56.77s (94.6% of
# the old 60s budget), 41.54s - the two checkouts differ by two files and
# 43KB, so the gap is cache/process state, not content, and a trip on a
# real cold checkout was not hypothetical. Raised to 180s - real margin
# over a cold main-checkout build, still short of the "five minutes of
# silence" `godmode_atlas.build`'s own docstring names as the failure this
# bound exists to catch, never a tight SLA. A trip still blocks the commit
# unconditionally (`_closure_inspection_failed` below); its own message
# names the remedy - `godmode retest --run` also WRITES the saved index
# (`refresh_atlas_index`, unbounded, below), so running it is a reachable
# way out of a trip, not a dead end.
_ATLAS_BUDGET_SECONDS = 180.0


def _is_closure_checked(path: str) -> bool:
    return path.endswith(".py") and any(path.startswith(root) for root in _CLOSURE_ROOTS)


def staged_name_status(project: Path) -> list[tuple[str, str]] | None:
    """`(status, path)` pairs from `git diff --cached --name-status` - the
    NEW path for a rename/copy (`R100\\told\\tnew` -> `("R100", "new")`).

    `None` on a failed inspection, never `[]` (the H2 rule `godmode_githooks.
    _staged_paths` already established for `--name-only`; this is the same
    rule for the richer `--name-status` read both that function and this
    module's own `closure_survey` now share - ONE git call, not two
    independently-timed readings of the index (fix round 1, Q2)).
    """
    raw = run_git(project, "diff", "--cached", "--name-status")
    if raw is None:
        return None
    entries: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        status = fields[0].strip()
        path = fields[-1].strip().replace("\\", "/")
        entries.append((status, path))
    return entries


def _last_edit_sequence(records: list[dict[str, Any]], path: str) -> int | None:
    """The newest `edit-recorded` action naming `path`, or `None`.

    `None` covers both "never edited" and "edited but only through a tool
    `hooks/godmode_post_edit.py` does not match (or a git-applied patch)" -
    the two are told apart by the blob comparison in `closure_survey`, never
    by this lookup alone.
    """
    last: int | None = None
    for record in records:
        if record.get("kind") != "action" or record.get("subject") != EDIT_RECORD_SUBJECT:
            continue
        if path in action_paths(record.get("data") or {}):
            last = record["sequence"]
    return last


# Fix round 1, S1: `_retest_module_names`/`_cited_modules` used to live
# here as their own definitions; both are now `godmode_retest.
# retest_module_names`/`cited_modules`, imported above - one shared home
# so `godmode_graph` and `godmode_reversals` read exactly this file->module
# bridge instead of a third and fourth independently-typed copy.


def _green_retest_info(
    records: list[dict[str, Any]], module_names: set[str],
) -> tuple[int | None, dict[str, Any] | None]:
    """The newest `check:retest:*` attestation (`status == "ran"`) whose
    covered modules (`cited_modules`) intersect `module_names` as whole
    names - its sequence and its own recorded `worktree`
    (`{"head", "dirty"}`), or `(None, None)`."""
    if not module_names:
        return None, None
    best_seq: int | None = None
    best_worktree: dict[str, Any] | None = None
    for record in records:
        if record.get("kind") != "attestation":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith("check:retest:"):
            continue
        data = record.get("data") or {}
        if data.get("status") != "ran":
            continue
        cited = cited_modules(record)
        if cited is None or not (cited & module_names):
            continue
        sequence = record["sequence"]
        if best_seq is None or sequence > best_seq:
            best_seq = sequence
            best_worktree = data.get("worktree")
    return best_seq, best_worktree


def _blob(project: Path, path: str, revision: str = "") -> str | None:
    """The git blob hash of `path` at `revision` (the index when `revision`
    is empty), or `None` when it does not resolve."""
    ref = f":{path}" if not revision else f"{revision}:{path}"
    return run_git(project, "rev-parse", ref)


def _unattested_but_unchanged(
    project: Path, path: str, green_worktree: dict[str, Any] | None,
) -> bool:
    """Whether a green retest with no `edit-recorded` for `path` still
    covers it.

    Fix round 2 (D5, re-review): in the NORMAL flow - edit outside the
    tracked-tool surface, `retest --run`, stage, commit - the tree is dirty
    at retest time BY CONSTRUCTION (the very edit being retested is still
    uncommitted), so round 1's `dirty == 0` requirement could never fire
    for the file actually being committed; that made this escape real only
    in a scenario nobody hits. Preferred proof now: `green_worktree["blobs"]`
    (fix round 2 - `godmode_attest.run_check`'s `blob_paths=`, threaded from
    `cmd_retest`, hashes each module's pinned SOURCE file via `git
    hash-object` at the moment the retest actually ran, whatever the
    tree's overall dirty count) carries a recorded hash for `path` - if the
    file's current staged blob matches THAT exact hash, this retest
    provably covered this file's exact content, dirty tree or not.
    Fallback (an older attestation with no per-path capture at all): the
    coarse, clean-tree-only proof - only trusted when `dirty == 0`, so its
    recorded HEAD blob for `path` is exactly what it tested. Fails closed
    (`False`) on any other shape: no matching blob, a dirty tree with no
    per-path capture, a missing head, or an unresolvable blob.
    """
    if not green_worktree:
        return False
    blobs = green_worktree.get("blobs") or {}
    recorded = blobs.get(path)
    if recorded is not None:
        current = _blob(project, path)
        return current is not None and current == recorded
    if green_worktree.get("dirty") != 0:
        return False
    head = green_worktree.get("head")
    if not head:
        return False
    current = _blob(project, path)
    retested = _blob(project, path, head)
    return current is not None and current == retested


def _atlas_for_closure(project: Path) -> Atlas:
    """The saved index when `load_index` reports it fully fresh, rebuilt
    (bounded by `_ATLAS_BUDGET_SECONDS`, scoped to `_CLOSURE_ROOT_DIRS`)
    otherwise.

    Fix round 2 (D1, re-review): "fully fresh" is `not report["stale"] and
    not report["missing"]` - NEVER `report["confidence"] == 1.0`, which is
    `round(len(fresh) / total, 2)` and reads 1.0 for anything at or above
    99.5% fresh. On this repository's own ~518 tracked files that rounds
    away up to 2 genuinely stale entries - exactly the files a real commit
    is staging, since staged files ARE the ones that changed since the
    index was last saved. The re-review's own repro: a 250-file project,
    one file edited, `confidence` still reads `1.0` while `stale ==
    ['scripts/m000.py']` - the rounded check rehydrated a graph that could
    not see that file's new import.

    D2i: bounded to `_CLOSURE_ROOT_DIRS` (`scripts/`, `hooks/`, `tests/`) -
    the only trees this check's own `_is_closure_checked` ever asks about -
    rather than the whole project, cutting both the walk and the risk of
    tripping the budget.

    Fix round 3 (N1, re-review 2): an index with ZERO stored files
    (`report["atlas"]["files"] == 0` - saved via `godmode atlas save` on a
    tree the atlas never walked, or a stray empty/malformed JSON) reads as
    "fully fresh" under `not stale and not missing`, since `load_index` only
    ever iterates the index's own stored files and an empty index has none
    to disagree with. Ruled: an empty index counts as MISSING, not fresh -
    it is rejected the same as a `stale`/`missing` one, forcing a real
    rebuild rather than answering from a map with nothing on it.

    A build that still hits that bound (`atlas.gap`) is never used to
    answer closure from a map that did not finish reading - raised instead,
    so the caller (`godmode_githooks._evaluate_pre_commit`) turns it into a
    refusal that BLOCKS regardless of declared policy (D2iii - this check's
    own unconditional posture, not `_inspection_failed_result`'s ordinary
    advisory-when-undeclared shape). Fix round 3: the raised message names
    the remedy directly - `godmode retest --run` both clears the ordinary
    stale/uncovered/unattested categories AND writes the saved index
    (`refresh_atlas_index`, unbounded), so it is what an operator facing a
    budget trip should run.
    """
    index_path = project / _ATLAS_INDEX_FILENAME
    if index_path.is_file():
        try:
            report = load_index(index_path, project)
        except GodmodeError:
            report = None
        if (report is not None and not report["stale"] and not report["missing"]
                and report["atlas"]["files"] > 0):
            return rehydrate_index(index_path, project)
    print(
        f"godmode: no fresh atlas index on record - building one now "
        f"(up to {_ATLAS_BUDGET_SECONDS:g}s)...",
        file=sys.stderr,
    )
    atlas = build_atlas(project, roots=_CLOSURE_ROOT_DIRS, budget_seconds=_ATLAS_BUDGET_SECONDS)
    if atlas.gap:
        scanned = int(atlas.gap.get("scanned", 0))
        unscanned = int(atlas.gap.get("unscanned", 0))
        raise GodmodeError(
            f"atlas build did not finish within {_ATLAS_BUDGET_SECONDS:g}s "
            f"({scanned} of {scanned + unscanned} files scanned); closure cannot "
            "be answered from a partial map; run `godmode retest --run` to build "
            "the index"
        )
    return atlas


def refresh_atlas_index(project: Path) -> dict[str, Any] | None:
    """Write/refresh `.godmode-atlas-index.json` from a fresh,
    closure-scoped build - `None` on any failure, never raises.

    Fix round 2 (D2): the saved-index fast path (`_atlas_for_closure`
    above) existed in round 1 with nothing that ever wrote to it - an
    "unwired fast path" the re-review named directly. Called from
    `cmd_retest` (`godmode_console.cmd_retest`) after a successful
    `--run`: the moment this project's own tests just ran green is exactly
    the moment a saved index is most trustworthy to write, and doing it
    there (a deliberate action) rather than as a side effect of every
    commit keeps `_evaluate_pre_commit` itself read-only towards this file.

    Fix round 3 (coordinator ruling): UNBOUNDED, unlike `_atlas_for_closure`'s
    commit-time build. This is the deliberate operator action that builds
    the index - `godmode retest --run` is run once, on purpose, not on
    every `git commit` - so it should always finish and leave a fresh index
    behind rather than fail under the same time pressure a commit-time
    build is bounded against. A build this large finishing slowly here is
    exactly what buys `_atlas_for_closure` its fast rehydrate path next
    time and keeps a budget trip a reachable, not hypothetical, remedy.
    """
    try:
        print("godmode: rebuilding the closure atlas index (unbounded)...",
              file=sys.stderr)
        atlas = build_atlas(project, roots=_CLOSURE_ROOT_DIRS)
        if atlas.gap:
            return None
        return save_index(atlas, project / _ATLAS_INDEX_FILENAME)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: best-effort refresh, never blocks the retest run it rides on
        return None


def closure_survey(
    project: Path,
    archive: Any,
    *,
    staged: list[str] | None = None,
    deleted: set[str] | None = None,
) -> dict[str, Any] | None:
    """One pass over the staged, atlas-checked code files, bucketed three
    ways: `stale` (`edit-recorded` exists, but no green retest is newer
    than it), `uncovered` (no test pins it, or a dependent, at all - "add a
    test" is the only honest remedy, never "run `retest --run`" again),
    and `unattested` (fix round 2, D5 - no `edit-recorded` at all, AND no
    green retest whose blob-hash or clean-tree proof covers its current
    content - "run `retest --run`, or record the edit" is the remedy;
    never the "stage the result" wording `stale` uses, which is a no-op
    when there is no edit record to begin with).

    `staged`/`deleted` let a caller that has already read `git diff --cached
    --name-status` (`godmode_githooks._evaluate_pre_commit`, fix round 1 Q2)
    pass it straight in instead of this module reading the index a second
    time. Fix round 2 (D4): `deleted` is derived independently of `staged`
    - a caller supplying `staged` alone (the signature allows it) still
    gets a real `deleted` set from a fresh read, rather than silently
    treating every staged path as a non-deletion. Left both `None`, this
    reads the index itself via `staged_name_status` and returns `None` -
    never an empty survey - on a failed inspection.
    """
    if staged is None or deleted is None:
        entries = staged_name_status(project)
        if entries is None:
            return None
        if staged is None:
            staged = [path for _status, path in entries]
        if deleted is None:
            deleted = {path for status, path in entries if status == "D"}
    checked = [path for path in staged if _is_closure_checked(path) and path not in deleted]
    if not checked:
        return {"stale": [], "uncovered": [], "unattested": []}
    records = archive.read_events()
    atlas = _atlas_for_closure(project)
    stale: list[dict[str, Any]] = []
    uncovered: list[str] = []
    unattested: list[dict[str, Any]] = []
    for path in checked:
        dependents = [
            finding["dependent"]
            for finding in unfollowed_dependents(atlas, [path])["findings"]
        ]
        module_names = retest_module_names(project, [path, *dependents])
        if not module_names:
            uncovered.append(path)
            continue
        green_seq, green_worktree = _green_retest_info(records, module_names)
        edit_seq = _last_edit_sequence(records, path)
        if edit_seq is not None:
            if green_seq is not None and green_seq > edit_seq:
                continue
            stale.append({"path": path, "last_edit_seq": edit_seq,
                          "last_green_retest_seq": green_seq})
            continue
        if green_seq is not None and _unattested_but_unchanged(project, path, green_worktree):
            continue
        unattested.append({"path": path, "last_green_retest_seq": green_seq})
    return {"stale": stale, "uncovered": uncovered, "unattested": unattested}


def stale_staged_files(
    project: Path, archive: Any, *,
    staged: list[str] | None = None, deleted: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    """The `stale` bucket of `closure_survey` - covered files with a
    recorded edit but no green retest newer than it. Never includes an
    uncovered or unattested file."""
    survey = closure_survey(project, archive, staged=staged, deleted=deleted)
    return None if survey is None else survey["stale"]


def uncovered_staged_files(
    project: Path, archive: Any, *,
    staged: list[str] | None = None, deleted: set[str] | None = None,
) -> list[str] | None:
    """The `uncovered` bucket of `closure_survey` - staged, atlas-checked
    files no test pins at all, directly or through a dependent."""
    survey = closure_survey(project, archive, staged=staged, deleted=deleted)
    return None if survey is None else survey["uncovered"]


def unattested_staged_files(
    project: Path, archive: Any, *,
    staged: list[str] | None = None, deleted: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    """The `unattested` bucket of `closure_survey` (fix round 2, D5) -
    covered, staged files with no `edit-recorded` action AND no green
    retest whose blob-hash or clean-tree proof covers their current
    content."""
    survey = closure_survey(project, archive, staged=staged, deleted=deleted)
    return None if survey is None else survey["unattested"]

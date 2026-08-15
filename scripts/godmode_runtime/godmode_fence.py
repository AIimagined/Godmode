"""What this piece of work may touch, declared before it starts.

Everything else in this runtime answers the question afterwards. `atlas
affected` reports a blast radius once a symbol is chosen; `inventory diff`
reports what moved once it has moved; `integrity` reads a diff that already
exists. All detection, and detection arrives after the edit.

That is not the question an operator asks when they hand over one section of a
codebase. They ask that nothing else move. A report that something else moved
is the wrong shape of answer to it.

So a plan may declare the paths it is allowed to edit, and an edit outside
them is refused rather than recorded. The declaration is a property of the
change, not of the project, which is why it lives on the plan contract and
expires with it - unlike the design boundary, which outlives every plan and
belongs in configuration.

**Undeclared means unenforced.** A fence nobody wrote cannot fence anything,
and deriving one from the request would be exactly the auto-detection this
project refuses everywhere a refusal is involved: a gate whose scope moves on
its own cannot be audited, and yesterday's allowed edit becomes today's
refusal with no diff to explain it. The gap is reported instead of guessed.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from .godmode_anchor import run_git
from .godmode_chronicle import Chronicle
from .godmode_constants import IGNORED_DIRECTORY_NAMES
from .godmode_errors import ArchiveError
from .godmode_plan import APPROVED
from .godmode_sentinel import POLICY_FILENAME

# Patterns are separated by commas or newlines so a contract field can be
# written either way round without the author having to know which.
_SEPARATORS = re.compile(r"[,\n]")


def declared_fence(archive: Chronicle) -> list[str] | None:
    """The patterns the approved plan may edit, or `None` when none were given.

    Only an approved plan fences. An open one is a proposal, and enforcing a
    proposal would let the agent fence itself in - or out - by writing a plan
    nobody agreed to.
    """
    for record in reversed(archive.select(kind="plan", limit=500)):
        data = record.get("data") or {}
        if data.get("state") != APPROVED:
            continue
        raw = str((data.get("contract") or {}).get("editable", "")).strip()
        if not raw:
            return None
        patterns = [part.strip() for part in _SEPARATORS.split(raw) if part.strip()]
        return patterns or None
    return None


def _relative(path: str, project_root: Path) -> str | None:
    """The path as the fence spells it, or `None` when it escapes the project.

    The host hands over whatever the agent typed, which is usually absolute and
    on Windows usually backslashed. Judging the raw string would let one file
    pass or fail depending on how it was written, and would make `../` a way
    through any fence.
    """
    candidate = Path(str(path).replace("\\", "/"))
    root = Path(project_root).resolve()
    absolute = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = absolute.resolve().relative_to(root)
    except ValueError:
        return None
    return relative.as_posix()


@lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str]:
    """`src/*.py` and `src/**` are different claims and stay different.

    `fnmatch` cannot draw that line - its `*` crosses separators, so every
    shallow pattern would quietly widen into its whole subtree, and a fence
    that widens on its own is not a fence. `PurePath.full_match` does draw it
    but arrived in 3.13, and CI runs 3.11.

    So each segment is translated: `**` spans any number of segments, a single
    `*` is confined to one, `?` to one character.
    """
    parts = pattern.split("/")
    built = ""
    for index, part in enumerate(parts):
        final = index == len(parts) - 1
        if part == "**":
            # Zero or more segments, and the separator belongs to the wildcard
            # rather than to the join: `a/**/b.py` has to match `a/b.py`, or
            # every `**` silently requires an intermediate directory that most
            # of the files it is meant to cover do not have.
            built += "(?:[^/]+/)*[^/]*" if final else "(?:[^/]+/)*"
        else:
            built += re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
            if not final:
                built += "/"
    return re.compile("^" + built + "$")


def _matches(relative: str, pattern: str) -> bool:
    return _compiled(pattern).match(relative) is not None


def audit_changes(archive: Chronicle, project_root: Path | str,
                  changed: Any) -> dict[str, Any]:
    """Every changed file, against what the plan said it would touch.

    The gate refuses an edit at the boundary, which covers the tools that
    announce a `file_path` and nothing else. A shell command that rewrites a
    file in passing, an edit made before the plan was approved, and any work
    done while the plugin was disabled all land in the tree unfenced.

    So the same declaration is asked of the result: "every changed line should
    trace directly to the request", checked against the only machine-readable
    statement of that request this project keeps.

    Findings, never closures. A file outside the set is not thereby wrong - it
    may be a dependency the plan did not foresee - but nobody having said which
    is the case that ships.
    """
    paths = [str(path).replace("\\", "/") for path in changed]
    patterns = declared_fence(archive)
    if patterns is None:
        return {
            "changes_examined": len(paths),
            "untraceable": [],
            "verdict": "no-declared-scope",
            "detail": "no approved plan declares an editable set, so nothing can be "
                      "traced against it",
        }

    untraceable = []
    for path in paths:
        verdict = fence_verdict(archive, path, project_root=project_root)
        if verdict["allowed"]:
            continue
        untraceable.append({
            "path": verdict["path"],
            "fence": patterns,
            "question": f"'{verdict['path']}' changed but the plan did not say it would "
                        "be touched - was it needed, and if so why was the scope not "
                        "widened?",
        })
    return {
        "changes_examined": len(paths),
        "untraceable": untraceable,
        "verdict": "untraceable-changes" if untraceable else "every-change-traces",
    }


def unaccepted_completions(archive: Chronicle) -> dict[str, Any]:
    """Completions that never cited the acceptance their plan declared.

    A plan states what done looks like. Nothing ever compared a completion
    against it, so `acceptance` was a field that got filled in and read by
    nobody - the same shape as `removal` recording reasons no reader consulted.

    Only completions are graded. Work in progress has not claimed anything yet,
    and reporting it would train the reader to skim the claims that count.
    """
    acceptance = ""
    for record in reversed(archive.select(kind="plan", limit=500)):
        data = record.get("data") or {}
        if data.get("state") != APPROVED:
            continue
        acceptance = str((data.get("contract") or {}).get("acceptance", "")).strip()
        break

    if not acceptance:
        return {"findings": [], "verdict": "no-acceptance-declared",
                "detail": "no approved plan declares an acceptance to grade against"}

    findings = []
    # `change`, not `build`: `godmode build` records an implementation result
    # under the `change` kind, and there is no `build` kind for the archive to
    # hold. Naming the command instead of the kind is how the sibling detector
    # in `godmode_mistakes` came to match almost nothing.
    for record in archive.select(kind="change", limit=500):
        data = record.get("data") or {}
        if str(data.get("status", "")).lower() not in {"done", "complete", "completed"}:
            continue
        if record.get("evidence"):
            continue
        findings.append({
            "subject": str(record.get("subject", ""))[:120],
            "sequence": int(record.get("sequence", 0)),
            "acceptance": acceptance,
            "question": f"this was recorded done, and the plan's acceptance was "
                        f"'{acceptance[:80]}' - what showed that it was met?",
        })
    return {
        "findings": findings,
        "acceptance": acceptance,
        "verdict": "unaccepted-completions" if findings else "completions-cite-acceptance",
    }


BOUNDARY_CONFIG = ".godmode-boundaries.json"

# What a design surface looks like, for the *proposer* only. Nothing here ever
# refuses anything: a `.tsx` file can be pure server-side data loading, a UI
# change can be a string in a plain route file, and an import added tomorrow
# would move the set without a diff to explain it. Enforcement reads declared
# globs; this reads the tree and hands a human a starting point.
_DESIGN_SUFFIXES = frozenset({
    ".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less",
})


def declared_design(project_root: Path | str) -> dict[str, list[str]] | None:
    """The design boundary this project declared, or `None` when it has none.

    An empty list is somebody who started and did not finish, and reading it as
    a boundary would freeze nothing while reporting configured - so it reads as
    absent. Malformed JSON raises rather than degrading to absent: a boundary
    that silently opens because its config failed to parse is the worst of both
    behaviours.
    """
    config = Path(project_root) / BOUNDARY_CONFIG
    if not config.exists():
        return None
    payload = json.loads(config.read_text(encoding="utf-8"))
    section = (payload or {}).get("ui") or {}
    declared = [str(p).strip() for p in (section.get("declared") or []) if str(p).strip()]
    if not declared:
        return None
    return {
        "declared": declared,
        "except": [str(p).strip() for p in (section.get("except") or []) if str(p).strip()],
    }


def design_verdict(project_root: Path | str, path: str) -> dict[str, Any]:
    """Whether this edit lands on a surface the operator froze.

    Refuses rather than asks. A one-key confirmation in the middle of a long
    run is the same keystroke as every other confirmation that session, and
    what is being protected here is not correctness but a decision somebody
    made deliberately - so it takes a deliberate act to move.
    """
    root = Path(project_root)
    declared = declared_design(root)
    relative = _relative(path, root)

    if declared is None:
        return {
            "allowed": True,
            "boundary": "unconfigured",
            "path": relative or str(path),
            "detail": f"no {BOUNDARY_CONFIG} declares a design boundary",
            "remedy": f"propose one with `godmode boundaries propose-ui`, then write "
                      f"the globs you agree with into {BOUNDARY_CONFIG}",
        }

    if relative is None:
        return {"allowed": True, "boundary": declared["declared"], "path": str(path),
                "detail": "outside the project, so no boundary of this project covers it"}

    if any(_matches(relative, pattern) for pattern in declared["except"]):
        return {"allowed": True, "boundary": declared["declared"], "path": relative,
                "detail": f"'{relative}' is an exception carved out of the boundary"}

    if not any(_matches(relative, pattern) for pattern in declared["declared"]):
        return {"allowed": True, "boundary": declared["declared"], "path": relative,
                "detail": f"'{relative}' is not a declared design surface"}

    return {
        "allowed": False,
        "boundary": declared["declared"],
        "path": relative,
        "detail": f"'{relative}' is a declared design surface; the look of this product "
                  "is a decision somebody made, not a defect to be improved in passing",
        "remedy": "have the operator authorise this exact edit: `godmode authorize stage "
                  f"--operation {json.dumps('Edit ' + relative)}` - it needs the password "
                  "from `godmode authorize setup`, is spent once, and expires",
    }


def propose_design(project_root: Path | str) -> list[str]:
    """Candidate globs for a human to read, accept, or throw away.

    It proposes and never writes. A scope that installs itself is exactly the
    auto-detection this boundary exists to refuse, and a config nobody read is
    a config nobody can be held to.
    """
    root = Path(project_root).resolve()
    directories: set[str] = set()
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() not in _DESIGN_SUFFIXES:
            continue
        relative = candidate.relative_to(root).as_posix()
        if any(part in IGNORED_DIRECTORY_NAMES for part in Path(relative).parts):
            continue
        parent = str(Path(relative).parent.as_posix())
        directories.add("**" if parent == "." else f"{parent}/**")
    return sorted(directories)


def fence_verdict(archive: Chronicle, path: str, *,
                  project_root: Path | str) -> dict[str, Any]:
    """Whether this edit is inside what the approved plan said it may touch.

    The refusal names the exact command that widens the fence. A refusal whose
    remedy is stale or absent teaches the agent a false model of what is
    possible, and the agent then hands back work it could have finished.
    """
    patterns = declared_fence(archive)
    relative = _relative(path, Path(project_root))

    if patterns is None:
        return {
            "allowed": True,
            "fence": "undeclared",
            "path": relative or str(path),
            "detail": "no approved plan declares an editable set, so nothing is fenced",
            "remedy": "declare one with `godmode planmode start --editable \"<glob>, <glob>\"`",
        }

    if relative is None:
        return {
            "allowed": False,
            "fence": patterns,
            "path": str(path),
            "detail": f"'{path}' resolves outside the project; a fence is a statement "
                      "about this project and cannot cover what escapes it",
            "remedy": "edit a path inside the project, or run the change where it belongs",
        }

    if any(_matches(relative, pattern) for pattern in patterns):
        return {"allowed": True, "fence": patterns, "path": relative,
                "detail": f"'{relative}' is inside the declared editable set"}

    return {
        "allowed": False,
        "fence": patterns,
        "path": relative,
        "detail": f"'{relative}' is outside the editable set this plan declared "
                  f"({', '.join(patterns)})",
        "remedy": "widen it deliberately with `godmode planmode start --editable "
                  "\"<glob>, <glob>\"` and have the plan re-approved, or leave the "
                  "file alone and say why it was not touched",
    }


# -----------------------------------------------------------------------
# B3-6: provenance-before-deletion gate (PARTIAL-P1, lessons sweep
# 2026-08-15).
#
# `fence_verdict` above answers "is this file one this piece of work said it
# would touch" - and an rm or an archive-move of a file inside the declared
# set, or with no fence declared at all, is something it would allow. This
# adds the mirror `removal.py` never asked: *before* that deletion lands, has
# anyone read the file's git history, run the reverse-impact traversal C-16
# already builds (`atlas.build(project).affected(path)` - reused here, not
# rebuilt), and said whether it is the sole carrier of a still-open
# obligation. Requirement-driven like B3-5: undeclared, this stays advisory;
# declared, it blocks. A pin always denies, whatever the policy says.
# -----------------------------------------------------------------------

PIN_CONFIG = ".godmode-pins.json"


def declared_pins(project_root: Path | str) -> list[str]:
    """Globs that may never be deleted, however this gate's policy reads.

    Its own small file rather than a section of BOUNDARY_CONFIG: a pin is a
    standing fact about a file, not a per-task fence or a UI surface, and
    folding it into either would make one file answer two unrelated
    questions - the drift GAP-2 names.
    """
    config = Path(project_root) / PIN_CONFIG
    if not config.exists():
        return []
    payload = json.loads(config.read_text(encoding="utf-8"))
    return [str(p).strip() for p in (payload or {}).get("pinned", []) if str(p).strip()]


def is_pinned(project_root: Path | str, path: str) -> bool:
    relative = _relative(path, Path(project_root))
    if relative is None:
        return False
    return any(_matches(relative, pattern) for pattern in declared_pins(project_root))


def _deletion_gate_declared(project_root: Path | str) -> bool:
    """Whether the operator's policy declares the deletion-provenance gate.

    Reuses sentinel's own tighten-only `POLICY_FILENAME` rather than adding a
    fourth small config file for one more operator-declared fact - the same
    choice B3-5 made for the license gate, and for the same reason.
    """
    path = Path(project_root) / POLICY_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return isinstance(raw, dict) and bool(raw.get("deletion_provenance_gate"))


def _is_tracked(project_root: Path | str, relative: str) -> bool:
    """Whether git already knows this file - a scratch file never will."""
    return run_git(Path(project_root), "ls-files", "--error-unmatch", "--", relative) is not None


def record_deletion_precheck(
    archive: Chronicle, project_root: Path | str, path: str, *,
    history_read: str, sole_carrier: str, affected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attest the pre-check this gate demands before a tracked file is deleted.

    `affected` is the caller's own `atlas.build(project).affected(path)`
    result - C-16's reverse-impact traversal, reused rather than rebuilt - so
    the record carries what traversal actually found, not a promise that
    something was checked.
    """
    relative = _relative(path, Path(project_root)) or str(path).replace("\\", "/")
    if not history_read.strip():
        raise ArchiveError(
            "a deletion pre-check needs a statement of what the file's git history showed"
        )
    if not sole_carrier.strip():
        raise ArchiveError(
            "a deletion pre-check needs a statement of whether this file is the sole "
            "carrier of a still-open obligation"
        )
    affected = affected or {}
    return archive.append(
        "action",
        f"deletion-precheck:{relative}"[:200],
        {
            "path": relative,
            "history_read": history_read.strip(),
            "sole_carrier": sole_carrier.strip(),
            "affected_count": int(affected.get("count", 0)),
            "affected_dependents": [d.get("id") for d in affected.get("dependents", [])][:20],
        },
        evidence=[],
    )


def _latest_deletion_precheck(archive: Chronicle, relative: str) -> dict[str, Any] | None:
    matches = archive.select(kind="action", subject=f"deletion-precheck:{relative}"[:200], limit=50)
    return matches[-1]["data"] if matches else None


def deletion_verdict(archive: Chronicle, path: str, *, project_root: Path | str) -> dict[str, Any]:
    """Whether a deletion the fence would otherwise allow may proceed.

    Green control: an attested pre-check passes; deleting an untracked
    scratch file is unaffected whatever the policy says, because nothing here
    has a provenance obligation to check. The pin check runs first and
    nothing below it can override its refusal - "the pin store outranks
    everything."
    """
    root = Path(project_root)
    relative = _relative(path, root)
    if relative is None:
        return {"allowed": True, "gate": "outside-project", "path": str(path),
                "detail": "outside the project; this gate is a statement about this project"}
    if is_pinned(root, relative):
        return {
            "allowed": False, "gate": "pinned", "path": relative,
            "detail": f"'{relative}' is pinned; pinned files stay denied regardless of "
                      "what any policy declares",
            "remedy": f"unpin it deliberately in {PIN_CONFIG} before deleting",
        }
    if not _is_tracked(root, relative):
        return {"allowed": True, "gate": "untracked", "path": relative,
                "detail": "untracked scratch file; deletion provenance does not apply"}
    if not _deletion_gate_declared(root):
        archive.append(
            "action", f"deletion-precheck-advisory:{relative}"[:200],
            {"path": relative,
             "detail": "no policy declares the deletion-provenance gate; recorded what a "
                       "pre-check would have covered: git-history-read, C-16's "
                       "reverse-impact traversal, and sole-carrier-of-open-obligation"},
            evidence=[],
        )
        return {"allowed": True, "gate": "advisory", "path": relative,
                "detail": "no policy declares the deletion-provenance gate"}
    attested = _latest_deletion_precheck(archive, relative)
    if attested is None:
        return {
            "allowed": False, "gate": "declared", "path": relative,
            "detail": f"policy declares the deletion-provenance gate and '{relative}' has "
                      "no recorded pre-check",
            "remedy": "record one: `godmode fence delete-precheck --path "
                      f"{relative!r} --history-read \"...\" --sole-carrier \"...\"`",
        }
    return {"allowed": True, "gate": "attested", "path": relative, "precheck": attested}

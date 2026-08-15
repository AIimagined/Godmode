"""Upstream/vendor capability-and-doctrine diff (GAP-1, task B3-1).

Before adopting, bypassing, or judging "do we already have this," diff
against the upstream/reference implementation's actual shipped behavior -
never its changelog prose, never its presence in a directory, never "we
don't currently call it." `godmode_minimality.py` (via `godmode_atlas.py`)
already finds duplication *inside* this project's own tree; nothing until
now diffed this project's own hand-rolled logic against a *named*
upstream/vendor dependency's actual shipped surface. `godmode_precheck.py`
answers "was this already built or rejected by us"; this module answers
"did the thing we depend on already solve this, better."

Two verdicts, never one, per unmatched symbol:

* an IMPORT verdict - the `disposition` field - answers "can this be reused
  as-is": `adopt` / `extend` / `diverge-deliberately` / `n/a-different-surface`.
* a BEHAVIOR verdict - the `behavior_verdict` field, separately required -
  answers "does the defect/capability this upstream symbol implies also
  exist in our own independent implementation": `confirmed-we-have-it` /
  `confirmed-we-dont` / `unverified`.

`n/a-different-surface` on the import question can NEVER stand in for the
behavior answer - a symbol ruled "different surface, not ours to adopt" can
still name a bug our own surface shares. `record_upstream_diff` refuses a
finding that carries a disposition with no behavior_verdict, and the same
refusal is enforced a second time at the archive seam
(`godmode_invariants._upstream_diff_invariants`) so a raw `Chronicle.append`
cannot bypass it either - the same defense-in-depth `_register_invariants`
and `_pin_invariants` already apply to their own kinds.

**Resolution boundary, stated rather than blurred.** Python is first-class:
`importlib.metadata` resolves the installed distribution's declared version
and its `top_level.txt`/entry-points, then the top-level module is actually
imported and its public surface enumerated - not just its README. Node is
best-effort only: `node_modules/<name>/package.json`'s `exports`/`bin` maps
are read as declared symbols, but nothing here parses the package's own
JavaScript, so a package whose real surface differs from its `exports` map
(a common case) is under-enumerated and the record says so
(`resolve_node_package`'s `note` field). An unresolvable package - not
installed, no importable top-level module, no `package.json` - never
produces a guess: it produces a `stated-gap` verdict naming the reason.

**Forked/copied repos carry the same duty (operator refinement,
2026-08-15).** The obligation is condition-triggered - "a fork or full copy
of external code exists" - not workflow-specific, so `--path
<vendored-tree>` enumerates a copied tree exactly as `--diff <package>`
enumerates an installed one, reusing `godmode_atlas.build` (the same
per-language extractor seam `godmode_minimality.py` already uses for the
project's own tree) rather than a second symbol-extraction implementation.

**Enumeration caps are loud, not silent** (the `godmode_egress.scan_project`
idiom): a resolved target's full symbol count is measured before the cap is
applied, and `truncated: true` is carried on the record whenever the cap
bit, so a capped enumeration is never read as a complete one.

**The diff itself reuses `godmode_atlas`'s duplicate-detection machinery**
(`_shingles`/`_jaccard`, the same name-shingle similarity `Atlas.duplicates`
already uses to find one capability implemented twice inside a single
project) rather than rebuilding a second symbol-matching heuristic: an
upstream symbol whose name-shingle similarity to every project symbol falls
below the threshold becomes a `finding`; at or above it, it is `matched` and
carries no finding at all - only genuinely unmatched upstream surface asks a
human for a disposition.

**The gate is requirement-driven, not always-on (operator refinement,
2026-08-15, binding).** `godmode upstream --diff <package>` runs on demand
regardless of any charter declaration - the tool always answers the
question when asked. Whether an *undispositioned* upstream-diff duty
becomes a HARD precondition on a register disposition of "already-have-it"
or "N/A" is decided by the project's own charter: `required_scope` reads a
compiled charter for a rule that names the `upstream-diff` duty and either
lists specific dependencies or declares an "any dependency / any forked or
copied repo" scope, and `gate_applies` answers whether that declared scope
covers one task. No matching charter rule means no gate - the tool stays
available, nothing blocks. A declaration can only ever ADD duty (name more
packages, widen to "any"), never remove or narrow what a prior declaration
already covered; `required_scope` has no subtractive path, by construction.

`CHARTER_RULE_TEMPLATE` below is the one emitted example of such a
declaration, phrased to compile HARD under `godmode_charter.py`'s existing
`_SHAPES` table (the `never ... without` shape, `attestation_present`,
`before_mutation`) with no edit to that table. This module never writes to
a charter file itself - the template is prose for a person to paste into an
authority document already bound by `godmode_charter.resolve_roles`, the
same way every other HARD rule in this project arrived.
"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import inspect
import json
import re
from pathlib import Path
from typing import Any

from .godmode_atlas import _jaccard, _shingles, build as build_atlas
from .godmode_errors import GodmodeError

# Full population is always counted before this cap is applied - see the
# module docstring's "loud caps" note and `godmode_egress.scan_project`,
# whose `DEFAULT_SCAN_LIMIT` this mirrors the reasoning of, not the number:
# an installed package's public surface is normally in the tens to low
# hundreds, so 512 gives real headroom while keeping a hit on the cap rare
# enough that seeing `truncated: true` remains a signal.
MAX_SYMBOLS_ENUMERATED = 512

# Name-shingle similarity floor for "this upstream symbol already exists in
# the project" - the same threshold `godmode_atlas.Atlas.duplicates` uses by
# default, kept identical rather than re-tuned so "duplicate inside our own
# tree" and "duplicate of upstream" agree about what counts as a match.
MATCH_THRESHOLD = 0.6

DISPOSITIONS = ("adopt", "extend", "diverge-deliberately", "n/a-different-surface")
BEHAVIOR_VERDICTS = ("confirmed-we-have-it", "confirmed-we-dont", "unverified")


# ---- resolution: what the upstream target actually exports ----------------

def resolve_python_package(name: str) -> dict[str, Any]:
    """First-class Python resolution: installed distribution + real import.

    Reads the declared version and `top_level.txt` from
    `importlib.metadata`, then imports the top-level module (falling back to
    the distribution name with hyphens turned to underscores when no
    `top_level.txt` is recorded) and enumerates its public surface -
    `__all__` when declared, otherwise every `dir()` name that does not
    start with `_`. An installed-but-unimportable distribution (a C
    extension that failed to build, a package requiring an optional extra)
    is reported with `module_import: False` and the import error, never
    guessed at.
    """
    name = name.strip()
    if not name:
        raise GodmodeError("resolve_python_package needs a non-empty package name")
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {
            "resolved": False, "target": name, "language": "python",
            "reason": f"no installed Python distribution named {name!r}",
        }

    version = dist.version
    top_level_text = None
    try:
        top_level_text = dist.read_text("top_level.txt")
    except Exception:  # noqa: BLE001 - a malformed dist-info degrades, never crashes
        top_level_text = None
    candidates = [line.strip() for line in (top_level_text or "").splitlines() if line.strip()]
    if not candidates:
        candidates = [name.replace("-", "_")]

    module = None
    module_name_used = None
    import_error: str | None = None
    for candidate in candidates:
        try:
            module = importlib.import_module(candidate)
            module_name_used = candidate
            break
        except Exception as exc:  # noqa: BLE001 - reported, never crashes resolution
            import_error = f"{candidate}: {exc}"

    entry_points = sorted({
        ep.name for ep in dist.entry_points
        if getattr(ep, "group", None) == "console_scripts"
    })

    if module is None:
        return {
            "resolved": True, "target": name, "language": "python", "version": version,
            "module_import": False, "import_error": import_error,
            "candidates_tried": candidates, "entry_points": entry_points,
            "symbols": [], "symbols_full_count": 0, "truncated": False,
        }

    symbols, full_count, symbol_kinds = _enumerate_module_exports(module)
    return {
        "resolved": True, "target": name, "language": "python", "version": version,
        "module_import": True, "module_name": module_name_used,
        "entry_points": entry_points,
        "symbols": symbols, "symbols_full_count": full_count,
        "truncated": full_count > MAX_SYMBOLS_ENUMERATED,
        # Round-1 review Minor #1: the module docstring's constants-never-match
        # boundary was invisible in actual output. Classifying each enumerated
        # name here (cheap - the module is already imported) lets
        # `diff_against_project` attach a per-finding note when the reason a
        # symbol is unmatched may be this known boundary rather than a genuine
        # gap, instead of leaving that only in source a JSON consumer never reads.
        "symbol_kinds": symbol_kinds,
    }


def _enumerate_module_exports(module: Any) -> tuple[list[str], int, dict[str, str]]:
    declared = getattr(module, "__all__", None)
    names = sorted(set(declared)) if declared else sorted(
        n for n in dir(module) if not n.startswith("_")
    )
    capped = names[:MAX_SYMBOLS_ENUMERATED]
    kinds: dict[str, str] = {}
    for name in capped:
        value = getattr(module, name, None)
        if inspect.isclass(value):
            kinds[name] = "class"
        elif inspect.isroutine(value):
            kinds[name] = "function"
        else:
            kinds[name] = "value"
    return capped, len(names), kinds


def resolve_node_package(name: str, project: Path) -> dict[str, Any]:
    """Best-effort Node resolution: `node_modules/<name>/package.json` only.

    Declared `exports` map keys and `bin` command names are read as the
    package's symbol surface. This is honestly incomplete - see the module
    docstring's resolution-boundary note - and the returned `note` field
    says so on every resolved record, not only in documentation a caller may
    never read.
    """
    name = name.strip()
    if not name:
        raise GodmodeError("resolve_node_package needs a non-empty package name")
    package_json = Path(project) / "node_modules" / name / "package.json"
    if not package_json.is_file():
        return {
            "resolved": False, "target": name, "language": "node",
            "reason": f"node_modules/{name}/package.json not found",
        }
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "resolved": False, "target": name, "language": "node",
            "reason": f"package.json unreadable: {exc}",
        }

    version = data.get("version")
    symbols: list[str] = []
    exports = data.get("exports")
    if isinstance(exports, dict):
        symbols.extend(str(key) for key in exports)
    elif isinstance(exports, str):
        symbols.append("exports:.")
    bin_field = data.get("bin")
    if isinstance(bin_field, dict):
        symbols.extend(f"bin:{key}" for key in bin_field)
    elif isinstance(bin_field, str):
        symbols.append(f"bin:{name}")

    names = sorted(set(symbols))
    full_count = len(names)
    return {
        "resolved": True, "target": name, "language": "node", "version": version,
        "symbols": names[:MAX_SYMBOLS_ENUMERATED], "symbols_full_count": full_count,
        "truncated": full_count > MAX_SYMBOLS_ENUMERATED,
        "note": "best-effort: package.json exports/bin declarations only, no AST "
                "parse of the package's own JavaScript - a package whose real "
                "surface differs from its declared exports map is under-enumerated",
    }


def resolve_vendored_tree(path: Path) -> dict[str, Any]:
    """Operator refinement: a forked or fully-copied external repo carries
    the same diff-against-upstream duty a lockfile dependency does. The
    copied tree at `path` IS the upstream here, so it is enumerated with the
    same `godmode_atlas.build` extractor seam this runtime already uses for
    a project's own tree - never a second symbol-extraction implementation.
    """
    path = Path(path)
    if not path.is_dir():
        return {
            "resolved": False, "target": str(path), "language": "vendored-tree",
            "reason": f"{path} is not a directory",
        }
    atlas = build_atlas(path)
    names = sorted({
        symbol.name for symbol in atlas.symbols
        if symbol.kind in ("function", "class") and not symbol.name.startswith("_")
    })
    full_count = len(names)
    return {
        "resolved": True, "target": str(path), "language": "vendored-tree", "version": None,
        "symbols": names[:MAX_SYMBOLS_ENUMERATED], "symbols_full_count": full_count,
        "truncated": full_count > MAX_SYMBOLS_ENUMERATED,
        "files_scanned": len(atlas.files), "unparsed": len(atlas.unparsed),
    }


# ---- diff: upstream surface against the project's own equivalents ---------

def diff_against_project(upstream: dict[str, Any], project: Path) -> dict[str, Any]:
    """One `finding` per upstream symbol with no name-similar match in the
    project's own atlas; everything at or above `MATCH_THRESHOLD` is
    `matched` and carries no finding. An unresolved upstream target never
    reaches a name comparison at all - it is a `stated-gap` outright, named
    by `upstream["reason"]`, not a diff against nothing that would read as
    "checked, found nothing to adopt."

    A stated boundary, not a silent gap: `godmode_atlas.Symbol` tracks
    function/class definitions only, so a config-default constant enumerated
    on the upstream side (an `__all__`-exported `DEFAULT_*`, say) can never
    match a project symbol through this comparison - it always becomes a
    `finding`, asking a human for a disposition rather than a name-match
    silently deciding "we have this" for a value nobody actually compared.
    When `upstream["symbol_kinds"]` says a finding's symbol is a non-callable
    `"value"` (only known for Python-resolved packages - see
    `_enumerate_module_exports`), the finding carries its own `note` saying
    so, rather than leaving that boundary discoverable only by reading this
    docstring.

    The converse risk runs the other way and is NOT caught by anything here:
    a project symbol with the same name as an upstream one but different
    behavior reads as `matched` by name-shingle similarity alone, and
    matching stops there - it is never diffed further, so a same-named,
    differently-behaving pair is indistinguishable from a genuine match in
    this report.
    """
    target = upstream.get("target")
    if not upstream.get("resolved"):
        return {
            "verdict": "stated-gap", "target": target,
            "reason": upstream.get("reason", "upstream target could not be resolved"),
            "upstream_symbols_enumerated": 0, "upstream_truncated": False,
            "matched": [], "findings": [],
        }

    upstream_symbols: list[str] = list(upstream.get("symbols") or [])
    symbol_kinds: dict[str, str] = upstream.get("symbol_kinds") or {}
    project_atlas = build_atlas(Path(project))
    project_names = sorted({
        symbol.name for symbol in project_atlas.symbols
        if symbol.kind in ("function", "class") and not symbol.name.startswith("_")
    })
    project_signatures = {n: _shingles(n) for n in project_names}

    matched: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for symbol in upstream_symbols:
        signature = _shingles(symbol)
        best_name: str | None = None
        best_score = 0.0
        for candidate_name, candidate_signature in project_signatures.items():
            score = _jaccard(signature, candidate_signature)
            if score > best_score:
                best_score, best_name = score, candidate_name
        if best_score >= MATCH_THRESHOLD:
            matched.append({
                "upstream_symbol": symbol, "project_symbol": best_name,
                "similarity": round(best_score, 3),
            })
        else:
            finding: dict[str, Any] = {
                "upstream_symbol": symbol,
                "closest_project_symbol": best_name,
                "closest_similarity": round(best_score, 3),
                "disposition": None,
                "behavior_verdict": None,
            }
            kind = symbol_kinds.get(symbol)
            if kind is not None:
                finding["upstream_symbol_kind"] = kind
            if kind == "value":
                # Round-1 review Minor #1: surface the constants-never-match
                # boundary on the affected finding itself, not only in the
                # module docstring - see diff_against_project's docstring.
                finding["note"] = (
                    "this upstream symbol is a non-callable value (e.g. a "
                    "constant), not a function/class; project-side matching "
                    "only compares against function/class symbols, so this "
                    "finding may already be covered by a same-purpose "
                    "constant or other non-callable equivalent this diff "
                    "cannot see"
                )
            findings.append(finding)

    return {
        "verdict": "findings-present" if findings else "fully-covered",
        "target": target, "language": upstream.get("language"),
        "version": upstream.get("version"),
        "upstream_symbols_enumerated": len(upstream_symbols),
        "upstream_truncated": bool(upstream.get("truncated")),
        "matched": matched, "findings": findings,
    }


# ---- recording: the one upstream-diff record per run ----------------------

def record_upstream_diff(
    archive: Any,
    project: Path,
    *,
    package: str | None = None,
    path: str | Path | None = None,
    language: str = "python",
    dispositions: dict[str, dict[str, str | None]] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve, diff, and write exactly one `upstream-diff` record.

    `dispositions` maps an upstream symbol name to `{"disposition":
    ..., "behavior_verdict": ...}`; a symbol absent from this mapping is
    written with both fields `None` (an open finding, same as
    `godmode_register`'s `open` state - undecided, not silently dropped).
    A supplied disposition with no paired behavior_verdict is refused here,
    before the archive is ever touched, with the same message the
    archive-seam invariant would give a raw append that tried to bypass this
    function - see the module docstring.
    """
    if bool(package) == bool(path):
        raise GodmodeError(
            "godmode upstream --diff needs exactly one of a package name or "
            "--path <vendored-tree>"
        )

    if path is not None:
        upstream = resolve_vendored_tree(Path(path))
        target = str(path)
        source_kind = "vendored-tree"
    elif language == "node":
        upstream = resolve_node_package(package, Path(project))
        target = package
        source_kind = "node-package"
    else:
        upstream = resolve_python_package(package)
        target = package
        source_kind = "python-package"

    diff = diff_against_project(upstream, Path(project))
    dispositions = dispositions or {}

    findings: list[dict[str, Any]] = []
    undispositioned: list[str] = []
    for finding in diff["findings"]:
        symbol = finding["upstream_symbol"]
        entry = dict(finding)
        supplied = dispositions.get(symbol)
        if supplied:
            disposition = supplied.get("disposition")
            behavior_verdict = supplied.get("behavior_verdict")
            if disposition is not None and disposition not in DISPOSITIONS:
                raise GodmodeError(
                    f"unknown upstream-diff disposition {disposition!r} for "
                    f"{symbol!r}; expected one of {DISPOSITIONS}"
                )
            if disposition is not None and behavior_verdict is None:
                raise GodmodeError(
                    f"upstream-diff finding for {symbol!r} supplies a "
                    f"disposition ({disposition!r}) with no behavior_verdict; "
                    "'n/a' on import can never stand in for the behavior "
                    "answer - refused"
                )
            if behavior_verdict is not None and behavior_verdict not in BEHAVIOR_VERDICTS:
                raise GodmodeError(
                    f"unknown upstream-diff behavior_verdict {behavior_verdict!r} "
                    f"for {symbol!r}; expected one of {BEHAVIOR_VERDICTS}"
                )
            entry["disposition"] = disposition
            entry["behavior_verdict"] = behavior_verdict
        if entry.get("disposition") is None:
            undispositioned.append(symbol)
        findings.append(entry)

    resolved = bool(upstream.get("resolved"))
    data: dict[str, Any] = {
        "target": target,
        "source_kind": source_kind,
        "language": upstream.get("language", language),
        "version": upstream.get("version"),
        "resolved": resolved,
        "reason": upstream.get("reason") if not resolved else None,
        "upstream_symbols_enumerated": diff.get("upstream_symbols_enumerated", 0),
        "upstream_truncated": diff.get("upstream_truncated", False),
        "matched": diff.get("matched", []),
        "findings": findings,
        "undispositioned": undispositioned,
        "verdict": "stated-gap" if not resolved else diff["verdict"],
    }
    subject = f"upstream-diff: {target}"
    record = archive.append("upstream-diff", subject, data, evidence=evidence or [])
    return {"record": record, "report": data}


# ---- charter integration: requirement-driven gate, template only ----------

# Phrased to compile HARD under godmode_charter.py's existing `_SHAPES` table
# (the `\bnever\b.*\bwithout\b` -> attestation_present/before_mutation shape)
# with no edit to that table - see the module docstring. This module never
# writes a charter file; a person pastes ONE of the two bullets below into an
# authority document godmode_charter.resolve_roles already binds.
CHARTER_RULE_TEMPLATE = """\
## Upstream-diff duty (optional; requirement-driven, tighten-only)

`godmode upstream --diff <package>` (or `--path <vendored-tree>` for a \
forked/copied repo) always runs on demand - add ONE line below only to make \
an *undispositioned* upstream-diff a HARD precondition before a register \
disposition of "already-have-it" or "N/A". No declaration below means no \
gate; a declaration can only widen what is covered, never narrow it.

Scope one or more named dependencies:
- A register disposition of "already-have-it" or "N/A" must never be \
recorded for a task naming the dependency `requests`, without an attested \
upstream-diff record for `requests` already in the archive.

Scope every dependency and every forked or copied external repo:
- A register disposition of "already-have-it" or "N/A" must never be \
recorded for a task naming a dependency, a forked repo, or a fully-copied \
external repo, without an attested upstream-diff record for it already in \
the archive.
"""

_ANY_SCOPE = re.compile(
    r"\b(?:any|all|every)\b[^.\n]{0,60}\b(?:dependenc\w*|packages?|forked|"
    r"fork\b|copied|vendored)\b",
    re.IGNORECASE,
)
_NAMED_PACKAGE = re.compile(r"[`'\"]([A-Za-z0-9_.@/-]+)[`'\"]")
_UPSTREAM_DIFF_MENTION = re.compile(r"upstream[- ]diff", re.IGNORECASE)


def required_scope(charter: dict[str, Any]) -> dict[str, Any]:
    """Read the operator's declared upstream-diff duty scope from a compiled
    charter (`godmode_charter.compile_charter`'s return shape).

    Undeclared (no rule mentions "upstream-diff" / "upstream diff") reports
    `declared: False` - the default, no-gate state the operator refinement
    requires. A rule that mentions it either names specific packages
    (quoted/backticked tokens) or declares an "any dependency" / "any
    forked or copied repo" scope; both can be present on the same or
    different rules, and the two only ever accumulate.
    """
    packages: set[str] = set()
    any_scope = False
    matching_rule_ids: list[str] = []
    for rule in charter.get("compiled", []):
        text = str(rule.get("text", ""))
        if not _UPSTREAM_DIFF_MENTION.search(text):
            continue
        matching_rule_ids.append(str(rule.get("id")))
        if _ANY_SCOPE.search(text):
            any_scope = True
        packages.update(match.lower() for match in _NAMED_PACKAGE.findall(text))

    return {
        "declared": any_scope or bool(packages),
        "any_scope": any_scope,
        "packages": sorted(packages),
        "rules": matching_rule_ids,
    }


def gate_applies(
    charter: dict[str, Any], *, task_text: str = "", package: str | None = None,
) -> dict[str, Any]:
    """Whether one task's undispositioned upstream-diff duty is a HARD gate.

    `scope["declared"] is False` (no charter rule names the duty at all)
    always answers `applies: False` - the tool remains available on demand
    regardless, per the operator refinement; this only decides whether the
    ABSENCE of an attested record blocks a register disposition.
    """
    scope = required_scope(charter)
    if not scope["declared"]:
        return {
            "applies": False, "scope": scope,
            "reason": "no upstream-diff duty declared in this project's charter",
        }

    haystack = f"{task_text} {package or ''}".lower()
    if scope["any_scope"]:
        names_a_target = bool(package) or bool(
            re.search(r"\bdepend\w*\b|\bfork\w*\b|\bvendor\w*\b|\bcopied\b|\bpackage\b", haystack)
        )
        return {
            "applies": names_a_target, "scope": scope,
            "reason": (
                "any-scope declaration; task names a dependency/fork" if names_a_target
                else "any-scope declaration, but this task names no dependency/fork"
            ),
        }

    matched_packages = [name for name in scope["packages"] if name in haystack]
    return {
        "applies": bool(matched_packages), "scope": scope,
        "matched_packages": matched_packages,
        "reason": (
            f"declared scope names {matched_packages}" if matched_packages
            else "declared scope does not name this task's dependency"
        ),
    }


def _self_check() -> None:
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        site_dir = base / "site"
        site_dir.mkdir()
        distinfo = site_dir / "selfcheckpkg-1.0.0.dist-info"
        distinfo.mkdir()
        (distinfo / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: selfcheckpkg\nVersion: 1.0.0\n", encoding="utf-8")
        (distinfo / "top_level.txt").write_text("selfcheckpkg\n", encoding="utf-8")
        (distinfo / "entry_points.txt").write_text(
            "[console_scripts]\nselfcheck-cli = selfcheckpkg:main\n", encoding="utf-8")
        (site_dir / "selfcheckpkg.py").write_text(
            "__all__ = ['rotate_widget', 'WidgetStore', 'DEFAULT_TIMEOUT']\n"
            "DEFAULT_TIMEOUT = 30\n"
            "def rotate_widget():\n    return 1\n"
            "class WidgetStore:\n    pass\n"
            "def main():\n    pass\n",
            encoding="utf-8",
        )

        sys.path.insert(0, str(site_dir))
        try:
            resolved = resolve_python_package("selfcheckpkg")
            assert resolved["resolved"] and resolved["module_import"], resolved
            assert resolved["version"] == "1.0.0", resolved
            assert "rotate_widget" in resolved["symbols"], resolved
            assert "selfcheck-cli" in resolved["entry_points"], resolved
            assert resolved["symbol_kinds"]["rotate_widget"] == "function", resolved
            assert resolved["symbol_kinds"]["WidgetStore"] == "class", resolved
            assert resolved["symbol_kinds"]["DEFAULT_TIMEOUT"] == "value", resolved

            missing = resolve_python_package("definitely-not-installed-xyz")
            assert not missing["resolved"] and missing["reason"], missing

            project = base / "project"
            project.mkdir()
            (project / "app.py").write_text(
                "def rotate_widget():\n    return 2\n", encoding="utf-8")
            diff = diff_against_project(resolved, project)
            assert diff["verdict"] == "findings-present", diff
            matched_names = {m["upstream_symbol"] for m in diff["matched"]}
            found_names = {f["upstream_symbol"] for f in diff["findings"]}
            assert "rotate_widget" in matched_names, diff
            assert "WidgetStore" in found_names, diff
            timeout_finding = next(
                f for f in diff["findings"] if f["upstream_symbol"] == "DEFAULT_TIMEOUT")
            assert timeout_finding["upstream_symbol_kind"] == "value", timeout_finding
            assert "non-callable value" in timeout_finding["note"], timeout_finding
            widget_finding = next(
                f for f in diff["findings"] if f["upstream_symbol"] == "WidgetStore")
            assert "note" not in widget_finding, widget_finding

            gap_diff = diff_against_project(missing, project)
            assert gap_diff["verdict"] == "stated-gap", gap_diff

            vendored = resolve_vendored_tree(project)
            assert vendored["resolved"] and "rotate_widget" in vendored["symbols"], vendored
            not_a_dir = resolve_vendored_tree(base / "does-not-exist")
            assert not not_a_dir["resolved"], not_a_dir

            node_project = base / "node-project"
            node_pkg = node_project / "node_modules" / "leftpad"
            node_pkg.mkdir(parents=True)
            (node_pkg / "package.json").write_text(
                json.dumps({"version": "2.0.0", "exports": {".": "./index.js"},
                            "bin": {"leftpad": "./cli.js"}}),
                encoding="utf-8",
            )
            node_resolved = resolve_node_package("leftpad", node_project)
            assert node_resolved["resolved"] and node_resolved["version"] == "2.0.0", node_resolved
            assert "bin:leftpad" in node_resolved["symbols"], node_resolved
            assert "note" in node_resolved, node_resolved
            node_missing = resolve_node_package("nope", node_project)
            assert not node_missing["resolved"], node_missing

            class _FakeArchive:
                def __init__(self) -> None:
                    self.calls: list[dict[str, Any]] = []

                def append(self, kind, subject, data, evidence=None):
                    self.calls.append({"kind": kind, "subject": subject, "data": data})
                    return {"kind": kind, "subject": subject, "data": data, "sequence": 1}

            fake = _FakeArchive()
            try:
                record_upstream_diff(
                    fake, project, package="selfcheckpkg",
                    dispositions={"WidgetStore": {"disposition": "adopt", "behavior_verdict": None}},
                )
                raise AssertionError("a disposition with no behavior_verdict must be refused")
            except GodmodeError:
                pass
            assert not fake.calls, "the refused write must never reach the archive"

            outcome = record_upstream_diff(
                fake, project, package="selfcheckpkg",
                dispositions={
                    "WidgetStore": {"disposition": "adopt", "behavior_verdict": "unverified"},
                    "DEFAULT_TIMEOUT": {"disposition": "n/a-different-surface",
                                        "behavior_verdict": "unverified"},
                },
            )
            assert outcome["report"]["verdict"] == "findings-present", outcome
            written = next(f for f in outcome["report"]["findings"]
                           if f["upstream_symbol"] == "WidgetStore")
            assert written["disposition"] == "adopt" and written["behavior_verdict"] == "unverified", written
            assert outcome["report"]["undispositioned"] == [], outcome

            # required_scope / gate_applies: undeclared charter -> no gate.
            empty_charter = {"compiled": []}
            assert required_scope(empty_charter)["declared"] is False
            assert gate_applies(empty_charter, package="selfcheckpkg")["applies"] is False

            named_charter = {"compiled": [
                {"id": "R-1", "text": "A register disposition must never be "
                                      "recorded for a task naming the "
                                      "dependency `selfcheckpkg`, without an "
                                      "attested upstream-diff record for "
                                      "`selfcheckpkg` already in the archive."},
            ]}
            scope = required_scope(named_charter)
            assert scope["declared"] and "selfcheckpkg" in scope["packages"], scope
            hit = gate_applies(named_charter, package="selfcheckpkg")
            assert hit["applies"], hit
            miss = gate_applies(named_charter, package="unrelated-package")
            assert not miss["applies"], miss

            any_charter = {"compiled": [
                {"id": "R-2", "text": "A register disposition must never be "
                                      "recorded for any task naming a "
                                      "dependency or a forked repo, without "
                                      "an attested upstream-diff record for "
                                      "it already in the archive."},
            ]}
            any_scope = required_scope(any_charter)
            assert any_scope["declared"] and any_scope["any_scope"], any_scope
            assert gate_applies(any_charter, task_text="add the widget dependency")["applies"]
            assert not gate_applies(any_charter, task_text="fix a typo in the README")["applies"]

            assert "upstream-diff" in CHARTER_RULE_TEMPLATE
        finally:
            sys.path.remove(str(site_dir))
            for name in ("selfcheckpkg",):
                sys.modules.pop(name, None)

    print("godmode_upstream self-check OK")


if __name__ == "__main__":
    _self_check()

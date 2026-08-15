"""Silent/swallowed-error scanner: catch/except shapes that discard failure.

A catch block, a dropped `error` field, a log call that only fires on the
success branch - each collapses two different facts ("nothing happened" and
"the check could not run") into one observable, and the observable is
always the more comfortable one. Nothing in the runtime's claim/evidence
family catches this, because it is a code-shape defect, not a claim-shape
one: `godmode_docslint.py` reads prose, `godmode_mistakes.py` reads claims
and diffs, and neither opens a source file to ask whether its own error
handling discards the failure it just caught.

Fidelity boundary, stated once here rather than implied:

* **Python** is scanned with the standard library's `ast` module - a real
  parse, not a pattern match. Three shapes: `empty-except` (a block that is
  only `pass`, a bare string, or `...` - the residue Python leaves when a
  comment is the entire body), `unused-exception-name` (`except X as e:`
  where `e` is bound and never referenced, and the block does not re-raise),
  and `success-only-log` (the `try` body logs or prints; none of the
  `except` handlers log, and none of them re-raise, so a failure here leaves
  no signal anywhere).
* **JavaScript/TypeScript** is best-effort: regex-shape matching over raw
  text plus a hand-rolled brace counter, not an AST. It catches exactly
  three shapes - `empty-catch`, `unused-catch-binding`
  (`catch (e) { ... }` where `e` is never referenced), and
  `unused-error-destructure` (`const { data, error } = ...` where `error`
  is never read in the following lines) - and nothing else. A brace or
  string delimiter inside an unusual construct (a regex literal containing
  `{`, a tagged template) can confuse the counter; this is the honest
  tradeoff of scanning a language without a stdlib parser, not a hidden
  claim of AST-grade precision. No other language is scanned.

A re-raising handler is never flagged: `except Exception as e: raise` (or
`raise SomeError(...) from e`) does not swallow anything - the failure still
propagates - and flagging it would teach a reader to delete the honest
re-raise and add a comment instead.

Ratchet, not block. Too many legitimate non-fatal catches exist (this
runtime's own `godmode_session_log.py` wraps state writes exactly this way,
so a caller never loses its result over a write failure) for a hard block
on every hit to be usable. Each finding carries `severity: "advisory"`
instead. What DOES fail loudly is the ratchet: a `.godmode-swallow-baseline.json`
file at the project root stores a per-file count of un-exempted findings,
and that ceiling may only shrink. A file whose count grows past its stored
baseline is a `regression` - the one hard signal this scanner produces -
independent of how many advisory findings exist elsewhere. `--update-baseline`
tightens the file to the current counts but can never raise a stored
ceiling: a file whose count grew keeps its old (lower) entry, so a real
regression cannot be baselined away by re-running the command that is
supposed to accept fixes.

Legitimate suppression gets an explicit escape, never a silent one: a
`# godmode: swallow-ok <reason>` (Python) or `// godmode: swallow-ok
<reason>` (JS/TS) comment anywhere inside the flagged span exempts that one
site from the count - but the reason is surfaced in the report's
`exemptions` list either way, so an exemption is never invisible to a
reader. An annotation with no reason text does not exempt anything; the
site stays in `findings`, marked `annotation_without_reason`.

Population sweep, per the caps discipline `godmode_egress.py` already
established: candidates are counted in full before the scan limit is
applied, and exceeding it sets `truncated: true` rather than quietly
reporting a partial sweep as clean.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .godmode_constants import IGNORED_DIRECTORY_NAMES, RUNTIME_VERSION

BASELINE_FILENAME = ".godmode-swallow-baseline.json"

# Same headroom reasoning as `godmode_egress.DEFAULT_SCAN_LIMIT`: large enough
# that an ordinary project never hits it, small enough that a scan of an
# adversarial tree still terminates. Hitting it is loud (`truncated: true`),
# never silent.
DEFAULT_SCAN_LIMIT = 2048

JS_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

_LOG_ATTR_NAMES = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)

_PY_ANNOTATION = re.compile(r"#\s*godmode:\s*swallow-ok\b(.*)")
_JS_ANNOTATION = re.compile(r"//\s*godmode:\s*swallow-ok\b(.*)")


def _annotation(lines: list[str], start_line: int, end_line: int) -> tuple[bool, str | None, bool]:
    """Whether a swallow-ok marker sits anywhere in `[start_line, end_line]`
    (1-indexed, inclusive), and its reason text if one was given."""
    lo = max(start_line, 1)
    hi = min(end_line, len(lines))
    for lineno in range(lo, hi + 1):
        line = lines[lineno - 1]
        for pattern in (_PY_ANNOTATION, _JS_ANNOTATION):
            match = pattern.search(line)
            if match:
                reason = match.group(1).strip(" \t-:")
                return True, (reason or None), bool(reason)
    return False, None, False


# --- Python: a real parse -----------------------------------------------


def _walk_all(stmts: list[ast.stmt]):
    for stmt in stmts:
        yield from ast.walk(stmt)


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "print"
    if isinstance(func, ast.Attribute):
        return func.attr in _LOG_ATTR_NAMES
    return False


def _contains_log_call(stmts: list[ast.stmt]) -> bool:
    return any(isinstance(n, ast.Call) and _is_log_call(n) for n in _walk_all(stmts))


def _contains_raise(stmts: list[ast.stmt]) -> bool:
    return any(isinstance(n, ast.Raise) for n in _walk_all(stmts))


def _references_name(stmts: list[ast.stmt], name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name for n in _walk_all(stmts))


def _is_swallowing_body(stmts: list[ast.stmt]) -> bool:
    """True when every statement is `pass`, a bare string (the shape a
    stripped comment or docstring leaves), or `...` - the only ways an
    `except` body can be non-empty and still do nothing."""
    if not stmts:
        return True
    for stmt in stmts:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            value = stmt.value.value
            if isinstance(value, str) or value is Ellipsis:
                continue
        return False
    return True


def _python_findings(relative: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [], f"syntax error line {exc.lineno}"

    lines = text.splitlines()
    findings: list[dict[str, Any]] = []
    exemptions: list[dict[str, Any]] = []

    def emit(check: str, line: int, end_line: int, why: str, remedy: str) -> None:
        excerpt = lines[line - 1].strip()[:160] if 0 <= line - 1 < len(lines) else ""
        found, reason, has_reason = _annotation(lines, line, end_line)
        if found and has_reason:
            exemptions.append({"path": relative, "line": line, "check": check, "reason": reason})
            return
        entry: dict[str, Any] = {
            "path": relative, "line": line, "check": check, "severity": "advisory",
            "why": why, "remedy": remedy, "excerpt": excerpt,
        }
        if found and not has_reason:
            entry["annotation_without_reason"] = True
        findings.append(entry)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        try_has_log = _contains_log_call(node.body)
        any_handler_log = False
        any_handler_raise = False
        for handler in node.handlers:
            end = getattr(handler, "end_lineno", handler.lineno) or handler.lineno
            if _is_swallowing_body(handler.body):
                emit(
                    "empty-except", handler.lineno, end,
                    "except block is empty, pass-only, or comment-only - the "
                    "failure is discarded silently",
                    "handle it, re-raise it, or log why it is safe to ignore",
                )
            elif (
                handler.name
                and not _contains_raise(handler.body)
                and not _references_name(handler.body, handler.name)
            ):
                emit(
                    "unused-exception-name", handler.lineno, end,
                    f"`{handler.name}` is bound and never referenced in the block",
                    f"use `{handler.name}` in the handler, or drop the binding "
                    "(`except ...:` without `as`)",
                )
            if _contains_log_call(handler.body):
                any_handler_log = True
            if _contains_raise(handler.body):
                any_handler_raise = True
        if node.handlers and try_has_log and not any_handler_log and not any_handler_raise:
            last_end = getattr(node.handlers[-1], "end_lineno", node.handlers[-1].lineno) or node.handlers[-1].lineno
            emit(
                "success-only-log", node.lineno, last_end,
                "the try branch logs; none of its except branches do, and none "
                "re-raise - a failure here leaves no signal",
                "log (or otherwise signal) the failure path too, not only the "
                "success path",
            )

    return findings, exemptions, None


# --- JavaScript/TypeScript: best-effort regex-shape ----------------------

# The parameter group is captured loosely (anything up to the closing
# paren) so a destructured (`catch ({ message }) {`) or typed
# (`catch (e: unknown) {`) parameter still matches the catch block itself;
# a plain identifier is then pulled out of that text below, and the
# unused-binding check only runs when one was found - a destructured
# parameter has no single name to check for use.
_CATCH_RE = re.compile(r"\bcatch\s*(\(\s*([^)]*)\))?\s*\{")
_SIMPLE_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
_DESTRUCTURE_ERROR_RE = re.compile(
    r"\b(?:const|let|var)\s*\{\s*(?:data\s*,\s*error|error\s*,\s*data)\s*\}\s*="
)


def _match_brace(text: str, open_index: int) -> int | None:
    """Index of the `{` at `open_index`'s matching `}`, tracking string,
    template-literal, and comment state so a brace inside one is not
    counted. A tokenizer this is not - it is the smallest state machine
    that handles the ordinary case without a dependency."""
    depth = 0
    i = open_index
    n = len(text)
    state: str | None = None  # None | '"' | "'" | '`' | 'line' | 'block'
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "line":
            if ch == "\n":
                state = None
        elif state == "block":
            if ch == "*" and nxt == "/":
                state = None
                i += 1
        elif state in ('"', "'", "`"):
            if ch == "\\":
                i += 1
            elif ch == state:
                state = None
        else:
            if ch == "/" and nxt == "/":
                state = "line"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block"
                i += 1
            elif ch in ('"', "'", "`"):
                state = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def _strip_js_comments(block: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    return re.sub(r"//[^\n]*", "", without_block)


def _js_findings(relative: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []
    exemptions: list[dict[str, Any]] = []

    def emit(check: str, line: int, end_line: int, why: str, remedy: str) -> None:
        excerpt = lines[line - 1].strip()[:160] if 0 <= line - 1 < len(lines) else ""
        found, reason, has_reason = _annotation(lines, line, end_line)
        if found and has_reason:
            exemptions.append({"path": relative, "line": line, "check": check, "reason": reason})
            return
        entry: dict[str, Any] = {
            "path": relative, "line": line, "check": check, "severity": "advisory",
            "why": why, "remedy": remedy, "excerpt": excerpt,
        }
        if found and not has_reason:
            entry["annotation_without_reason"] = True
        findings.append(entry)

    for match in _CATCH_RE.finditer(text):
        open_index = match.end() - 1
        close_index = _match_brace(text, open_index)
        if close_index is None:
            continue
        block = text[open_index + 1:close_index]
        line_no = text.count("\n", 0, match.start()) + 1
        end_line = text.count("\n", 0, close_index) + 1
        stripped = _strip_js_comments(block).strip()
        if not stripped:
            emit(
                "empty-catch", line_no, end_line,
                "catch block is empty or comment-only - the failure is "
                "discarded silently",
                "handle it, rethrow it, or log why it is safe to ignore",
            )
            continue
        raw_param = (match.group(2) or "").strip()
        identifier = _SIMPLE_IDENTIFIER.match(raw_param) if raw_param else None
        binding = identifier.group(0) if identifier else None
        if binding and not re.search(r"\b" + re.escape(binding) + r"\b", stripped):
            emit(
                "unused-catch-binding", line_no, end_line,
                f"`{binding}` is bound and never referenced in the catch block",
                f"use `{binding}` in the block, or drop the binding (`catch {{}}`)",
            )

    for match in _DESTRUCTURE_ERROR_RE.finditer(text):
        line_no = text.count("\n", 0, match.start()) + 1
        window_end = min(len(lines), line_no + 40)
        # The window excludes the destructure line itself: the destructure
        # spells `error` in the pattern, which is not a use of it.
        window = "\n".join(lines[line_no:window_end])
        if not re.search(r"\berror\b", window):
            emit(
                "unused-error-destructure", line_no, window_end,
                "`error` is destructured from the result and never referenced "
                "afterward",
                "check `error` before using `data`, or drop it from the "
                "destructure",
            )

    return findings, exemptions


# --- Ratchet: baseline load/store -----------------------------------------


def _load_baseline(project: Path) -> tuple[dict[str, int] | None, str | None]:
    path = Path(project) / BASELINE_FILENAME
    if not path.is_file():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"baseline file unreadable: {exc}"
    counts = payload.get("counts") if isinstance(payload, dict) else None
    if not isinstance(counts, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in counts.items()
    ):
        return None, "baseline file malformed: expected {'counts': {path: int}}"
    return counts, None


def update_baseline(project: Path, current_counts: dict[str, int]) -> dict[str, int]:
    """Write a tightened baseline: a file's stored ceiling only ever shrinks
    or holds. A file whose count grew keeps its OLD (lower) entry, so a real
    regression cannot be baselined away by re-running this command - only by
    fixing the site or annotating it."""
    existing, _ = _load_baseline(project)
    existing = existing or {}
    merged: dict[str, int] = {}
    for relative, count in current_counts.items():
        if count <= 0:
            continue
        merged[relative] = min(count, existing[relative]) if relative in existing else count
    payload = {"counts": merged, "runtime_version": RUNTIME_VERSION}
    (Path(project) / BASELINE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return merged


def scan_project(project: Path, limit: int = DEFAULT_SCAN_LIMIT) -> dict[str, Any]:
    """Sweep Python and JS/TS source for silent-failure shapes, and ratchet
    the result against the stored baseline.

    Candidates are counted in full before the cap is applied, matching
    `godmode_egress.scan_project`'s discipline: a scan that truncates
    without saying so would let a clean read over part of the tree stand in
    for a claim about all of it.
    """
    project = Path(project)
    candidates: list[Path] = []
    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix != ".py" and suffix not in JS_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        candidates.append(path)

    truncated = len(candidates) > limit
    findings: list[dict[str, Any]] = []
    exemptions: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    scanned = 0
    for path in candidates[:limit]:
        scanned += 1
        relative = path.relative_to(project).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            unparsed.append({"path": relative, "reason": str(exc)[:120]})
            continue
        if path.suffix.lower() == ".py":
            file_findings, file_exemptions, reason = _python_findings(relative, text)
            if reason:
                unparsed.append({"path": relative, "reason": reason})
        else:
            file_findings, file_exemptions = _js_findings(relative, text)
        findings.extend(file_findings)
        exemptions.extend(file_exemptions)
        if file_findings:
            counts[relative] = len(file_findings)

    baseline, baseline_error = _load_baseline(project)
    baseline_exists = baseline is not None
    baseline_map = baseline or {}
    regressions: list[dict[str, Any]] = []
    if baseline_exists:
        for relative, count in counts.items():
            ceiling = baseline_map.get(relative, 0)
            if count > ceiling:
                regressions.append({"path": relative, "current": count, "baseline": ceiling})
        regressions.sort(key=lambda r: r["path"])

    if regressions:
        verdict = "regression"
    elif truncated:
        verdict = "truncated"
    elif findings:
        verdict = "findings"
    else:
        verdict = "clean"

    return {
        "scanned": scanned,
        "candidates": len(candidates),
        "truncated": truncated,
        "unparsed": unparsed,
        "findings": findings,
        "exemptions": exemptions,
        "counts": counts,
        "baseline_exists": baseline_exists,
        "baseline": baseline_map,
        "baseline_error": baseline_error,
        "regressions": regressions,
        "verdict": verdict,
    }

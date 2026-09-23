"""Bad/fixed wording pairs for gate refusals and Stop-boundary messages.

`lint_text` checks one already-assembled string against the table.
`lint_hook_strings` walks the shipped source files with `ast` and
assembles every WHOLE message a reader could actually see - flattening
an f-string (`JoinedStr`) and a `"a" + "b"` concatenation (`BinOp` of
`+`, including a conditional clause like `(f"..." if x else "")`) into
one string, with a `{<source>}` placeholder standing in for each
interpolated expression (e.g. `{tier}`, `{preview['category']}`) - then
lints each assembled message once. Fix round 1: the first version only
inspected bare `ast.Constant` nodes in isolation, so a wording problem
spread across an f-string's own literal fragments (nearly every shipped
refusal) was invisible to it - it saw the fragment `"refused: "` and
nothing past the first `{...}`.

Function, class and module docstrings are excluded from the scan: they
are read by a contributor working on the source, never shown to an
operator, so their prose is not held to this table.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

# Each entry: (regex, why it trips a reader, a fixed example for that class).
PATTERNS: tuple[tuple[str, str, str], ...] = (
    # A tier code alone ("R5"), or a placeholder that renders one
    # (`{preview.get('tier', 'R?')}`), names nothing to a reader outside
    # the project; the class must ride beside it, e.g. "R5 (history or
    # remote)". The lookahead accepts "R5 (" / "R5 -" / "R5:" - or the
    # same right after a `{...tier...}` placeholder - followed by a word
    # as already-named; anything else (bare, or immediately closed by a
    # bare ")") is flagged.
    (r"(?:\bR[0-5]\b|\{[^}]*[Tt]ier[^}]*\})(?!\s*[-(:]\s*[A-Za-z])",
     "bare tier code with no class name", "R5 (history or remote)"),
    # "not un<word>" (e.g. "not unreachable") makes a reader negate a
    # negation to find the meaning; say the positive form instead.
    (r"\bnot un\w+", "double negative", "say the positive form"),
    # A remedy that tells the operator to act ("stage it", "retry") but
    # never gives the exact command leaves them guessing what to type.
    (r"(?i)\b(stage it|retry)\b(?![^.]*`)", "remedy names no command",
     "stage it with `godmode authorize stage --from-last-refusal`"),
    # Internal record vocabulary, read as an instruction rather than as
    # the implementation detail it is - a reader outside the project has
    # no way to know what a "walrus", a "seq:N only" filter, or a "hash-
    # chained" record means, and none of the three tells them what to do.
    (r"\b(walrus|seq:\d+ only|hash-chained)\b", "internal record vocabulary as instruction",
     "name the operator-facing effect instead"),
)
# A sentence ends at ".", "!" or "?" only when that punctuation is itself
# followed by whitespace or the end of the string - splitting on every
# "." also cut a path or filename apart (`godmode.cmd`, `.claude`),
# measuring one long sentence as a run of short, harmless-looking pieces
# instead of the whole thing a reader has to hold in their head at once.
_SENTENCE = re.compile(r"[^\n]+?(?:[.!?](?=\s|$)|\Z)")
MAX_SENTENCE = 240
_MARKERS = ("refused", "deliberate block", "SCOPE STILL OPEN", "DONE BAR", "stop", "godmode gate")
_FILES = (
    "hooks/godmode_session_hook.py",
    "hooks/godmode_gate_fast.py",
    "scripts/godmode_runtime/godmode_hostevent.py",
    "scripts/godmode_runtime/godmode_sentinel.py",
)


def lint_text(text: str) -> list[str]:
    """Every wording finding in `text`, as `"<why>: <matched text>"`."""
    findings = []
    for pattern, why, _fixed in PATTERNS:
        for match in re.finditer(pattern, text):
            findings.append(f"{why}: {match.group(0)!r}")
    for sentence in _SENTENCE.findall(text):
        if len(sentence.strip()) > MAX_SENTENCE:
            findings.append(f"sentence over {MAX_SENTENCE} chars: {sentence.strip()[:60]!r}…")
    return findings


def _operator_facing(literal: str) -> bool:
    return any(marker.lower() in literal.lower() for marker in _MARKERS)


def _placeholder(expr: ast.expr) -> str:
    """A brace-wrapped stand-in for an interpolated expression, carrying
    the expression's own source text (`{tier}`, `{preview['category']}`)
    so a reader of the finding can tell what it renders without running
    the code, and so the tier-code pattern can still recognise it."""
    try:
        return "{" + ast.unparse(expr) + "}"
    except Exception:  # pragma: no cover - defensive: unparse never fails on parsed AST
        return "{...}"


def _render(node: ast.expr) -> str | None:
    """The whole message `node` builds, or `None` if `node` is not built
    purely from string constants, f-strings, `+` concatenation of those,
    and `x if cond else y` branches of those - i.e. it bottoms out in a
    bare name/call/attribute that isn't itself one of these shapes, which
    is left for its own literal parts to be found on their own rather than
    guessed at.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append(_placeholder(value.value))
            else:  # pragma: no cover - JoinedStr.values is only ever these two
                return None
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _render(node.left)
        right = _render(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.IfExp):
        body = _render(node.body)
        orelse = _render(node.orelse)
        if body is None or orelse is None:
            return None
        # Representative text: every shipped instance's "no" branch is ""
        # (nothing to lint), so the branch that actually says something is
        # the one worth checking.
        return body or orelse
    return None


def _collect_messages(tree: ast.AST) -> list[tuple[int, str]]:
    """Every assembled message in `tree`, as `(lineno, text)`, each
    counted once even when it spans several literal fragments - and
    never counting a fragment twice by also visiting it as part of its
    parent `JoinedStr`/`BinOp`. Module, class and function docstrings are
    skipped entirely."""
    docstring_ids = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
        and ast.get_docstring(node, clean=False) is not None
    }
    messages: list[tuple[int, str]] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str) and id(node) not in docstring_ids:
                messages.append((node.lineno, node.value))

        def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
            text = _render(node)
            if text is None:  # pragma: no cover - defensive, see _render
                self.generic_visit(node)
                return
            messages.append((node.lineno, text))

        def visit_BinOp(self, node: ast.BinOp) -> None:
            text = _render(node)
            if text is None:
                # Not a pure string chain (e.g. `"..." + some_name`) - let
                # each side be found on its own instead of guessing at the
                # dynamic operand.
                self.generic_visit(node)
                return
            messages.append((node.lineno, text))

    _Visitor().visit(tree)
    return messages


def lint_hook_strings(hooks_dir: Path) -> dict[str, Any]:
    """Lint every operator-facing message assembled from the shipped
    source: `hooks/godmode_session_hook.py`, `hooks/godmode_gate_fast.py`,
    `scripts/godmode_runtime/godmode_hostevent.py` (`render_decision`),
    and `scripts/godmode_runtime/godmode_sentinel.py` (`stage_hint`, the
    remedy text every refusal above routes through). `hooks_dir` locates
    the project root as its parent, so a caller passes the project's own
    `hooks/` directory.

    `scanned` is the number of assembled, operator-facing messages held
    to the wording table (one per marker-carrying literal/f-string/`+`
    chain, not per fragment), across every file that exists - a project
    shape missing all of them scans zero, and `passed` requires
    `scanned > 0` so an empty scan cannot read as a clean one.
    """
    root = Path(hooks_dir).parent
    findings: list[dict[str, Any]] = []
    scanned = 0
    for rel in _FILES:
        path = root / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, text in _collect_messages(tree):
            if not _operator_facing(text):
                continue
            scanned += 1
            for finding in lint_text(text):
                findings.append({"file": rel, "line": lineno, "finding": finding})
    return {"passed": scanned > 0 and not findings, "findings": findings, "scanned": scanned}

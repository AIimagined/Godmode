"""A docstring that promises a field is set, filtered, selected or skipped
names a symbol the function body never touches - the phantom
cross-layer contract (absorbed 2026-09-11 from a multi-agent workspace's
incident-derived review rules: "if a comment says another layer sets
this, grep that the layer actually sets it"; a description read by a
model is API surface it cannot check).

Structural on purpose: the property is that a promise and a body agree,
which execution cannot show. Scope is narrow so it stays decidable: a
promise is a backticked identifier after a promise verb inside a
function's own docstring, and the check is that the identifier's last
segment appears in that function's body.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "scripts" / "godmode_runtime", ROOT / "hooks"]
_PROMISE = re.compile(
    r"(?i)\b(?:sets|assigns|writes|filters(?: on| by)?|selects|excludes|skips|reads|returns)\s+`([A-Za-z_][\w.]*)`")


def phantom_promises(source: str, filename: str = "<module>") -> list[str]:
    tree = ast.parse(source, filename)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        if not doc:
            continue
        body = ast.get_source_segment(source, node) or ""
        body = body[len(doc):] if body else body  # the docstring itself must not satisfy its own promise
        for match in _PROMISE.finditer(doc):
            name = match.group(1).split(".")[-1]
            if len(name) < 3:
                continue
            if not re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", body.replace(doc, "", 1)):
                found.append(f"{node.name}: promises `{match.group(1)}` (line {node.lineno})")
    return found


class DocstringPromiseTests(unittest.TestCase):
    def test_the_checker_names_a_promise_the_body_does_not_keep(self) -> None:
        broken = ('def f(row):\n    """Filters on `joinPolicy` before returning."""\n    return row\n'
                  'def g(row):\n    """Filters on `joinPolicy` before returning."""\n    return row if row.joinPolicy else None\n')
        found = phantom_promises(broken)
        self.assertEqual([f.split(":")[0] for f in found], ["f"], found)

    def test_no_godmode_function_promises_what_its_body_never_names(self) -> None:
        offenders: dict[str, list[str]] = {}
        for base in SCANNED:
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                found = phantom_promises(path.read_text(encoding="utf-8", errors="replace"), str(path))
                if found:
                    offenders[str(path.relative_to(ROOT))] = found
        self.assertEqual(offenders, {}, offenders)


if __name__ == "__main__":
    unittest.main()

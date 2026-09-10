"""A name that no scope defines is a NameError waiting for its first call.

The required-sources gate went dark for a whole cycle: its body referenced
`transcript_path`, which was never a parameter, and the best-effort
`except Exception: return None` around the call turned the NameError into a
gate that never asked. The suite pinned the ask and caught it, one gate
round late. This check catches the class before any test runs: every name a
function reads from module scope is defined somewhere in that module, an
import, a builtin, or a `global` declaration - resolved with the standard
library's symtable, no third-party linter.
"""
from __future__ import annotations

import builtins
import os
import symtable
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "hooks", ROOT / "scripts", ROOT / "tests"]
_KNOWN = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__spec__", "__loader__", "__package__",
    "__builtins__", "__path__", "__annotations__", "__debug__", "__class__",
    "__qualname__", "__module__", "__dict__", "__cached__",
}


def undefined_names(source: str, filename: str = "<module>") -> list[str]:
    """`name@line-scope` for every module-scope read that nothing defines."""
    top = symtable.symtable(source, filename, "exec")
    defined = set(_KNOWN)
    for symbol in top.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter():
            defined.add(symbol.get_name())

    def declared_globals(table: symtable.SymbolTable) -> None:
        for symbol in table.get_symbols():
            if symbol.is_declared_global() and symbol.is_assigned():
                defined.add(symbol.get_name())
        for child in table.get_children():
            declared_globals(child)

    declared_globals(top)
    found: list[str] = []

    def walk(table: symtable.SymbolTable) -> None:
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if name in defined or (name.startswith("__") and name.endswith("__")):
                # dunder names at any scope are the interpreter's own
                # (`__conditional_annotations__` on 3.14, `__class__` in methods)
                continue
            if table is top:
                unresolved = symbol.is_referenced() and not symbol.is_assigned()
            else:
                unresolved = symbol.is_global() and symbol.is_referenced()
            if unresolved:
                found.append(f"{name}@{table.get_name()}:{table.get_lineno()}")
        for child in table.get_children():
            walk(child)

    walk(top)
    return found


def _python_files() -> list[Path]:
    out: list[Path] = []
    for base in SCANNED:
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts or ".godmode-preflight" in str(path):
                continue
            out.append(path)
    return out


class UndefinedNameTests(unittest.TestCase):
    def test_the_checker_names_a_read_nothing_defines(self) -> None:
        broken = "import os\n\ndef f(x):\n    return g(x) + os.sep + y\n"
        found = undefined_names(broken)
        self.assertEqual(sorted(n.split("@")[0] for n in found), ["g", "y"], found)

    def test_the_checker_accepts_globals_imports_and_free_variables(self) -> None:
        fine = (
            "import os\nfrom pathlib import Path\nCOUNT = 0\n\n"
            "def bump():\n    global COUNT\n    COUNT += 1\n    return os.sep\n\n"
            "def outer(a):\n    def inner():\n        return a + COUNT\n    return inner\n\n"
            "class K:\n    LIMIT = 3\n    def m(self):\n        return super().m() + self.LIMIT\n\n"
            "try:\n    import tomllib\nexcept ImportError:\n    tomllib = None\n"
            "print(len([p for p in Path('.').iterdir()]))\n"
        )
        self.assertEqual(undefined_names(fine), [])

    def test_no_godmode_source_reads_an_undefined_name(self) -> None:
        offenders: dict[str, list[str]] = {}
        for path in _python_files():
            source = path.read_text(encoding="utf-8", errors="replace")
            try:
                found = undefined_names(source, str(path))
            except SyntaxError as error:
                self.fail(f"{path}: {error}")
            if found:
                offenders[str(path.relative_to(ROOT))] = found
        self.assertEqual(offenders, {}, offenders)


if __name__ == "__main__":
    unittest.main()

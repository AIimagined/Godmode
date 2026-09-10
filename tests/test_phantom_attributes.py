"""A `module.name` the module does not define is an AttributeError waiting
for its first call - the class the symtable check (`test_undefined_names`)
cannot see, since the name resolves; the member does not (absorbed from a
static analyser's cross-module member check, 2026-09-10).

Every `from godmode_runtime.X import a` and every `X.attr` read on an
imported godmode module, anywhere in hooks, scripts and tests, is checked
against the module's real namespace by importing it. Standard-library and
third-party modules are out of scope: their surfaces vary by version, and
godmode owns none of them.
"""
from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "tests", ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

SCANNED = [ROOT / "hooks", ROOT / "scripts", ROOT / "tests"]
PACKAGE = "godmode_runtime"


def _own_module(name: str, current: str | None) -> str | None:
    """The absolute godmode module a dotted import names, or None."""
    if name.startswith(PACKAGE):
        return name
    if current and name.startswith(".") and current.startswith(PACKAGE):
        base = current.rsplit(".", 1)[0]
        return base + name if name != "." else base
    return None


def phantom_members(source: str, filename: str, current: str | None = None) -> list[str]:
    tree = ast.parse(source, filename)
    aliases: dict[str, str] = {}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = _own_module(alias.name, current)
                if module:
                    aliases[alias.asname or alias.name.split(".")[-1]] = module
        elif isinstance(node, ast.ImportFrom) and node.module is not None or (
                isinstance(node, ast.ImportFrom) and node.level):
            dotted = ("." * node.level) + (node.module or "")
            module = _own_module(dotted, current)
            if not module:
                continue
            try:
                loaded = importlib.import_module(module)
            except Exception as error:  # noqa: BLE001 - an unimportable module is itself the finding
                found.append(f"{module}: {type(error).__name__} at line {node.lineno}")
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if hasattr(loaded, alias.name):
                    if isinstance(getattr(loaded, alias.name), type(sys)):
                        aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
                    continue
                # A submodule reached through its package.
                try:
                    importlib.import_module(f"{module}.{alias.name}")
                    aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
                except Exception:  # noqa: BLE001
                    found.append(f"{module}.{alias.name} at line {node.lineno}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            module = aliases[node.value.id]
            try:
                loaded = importlib.import_module(module)
            except Exception:  # noqa: BLE001
                continue
            if not hasattr(loaded, node.attr):
                found.append(f"{module}.{node.attr} at line {node.lineno}")
    return found


def _python_files() -> list[Path]:
    out: list[Path] = []
    for base in SCANNED:
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts or ".godmode-preflight" in str(path):
                continue
            out.append(path)
    return out


def _module_name(path: Path) -> str | None:
    try:
        relative = path.relative_to(ROOT / "scripts")
    except ValueError:
        return None
    return ".".join(relative.with_suffix("").parts)


class PhantomAttributeTests(unittest.TestCase):
    def test_the_checker_names_a_member_the_module_lacks(self) -> None:
        broken = ("from godmode_runtime import godmode_constants\n"
                  "from godmode_runtime.godmode_constants import EVENT_KINDS, NO_SUCH_NAME\n"
                  "print(godmode_constants.ALSO_MISSING, EVENT_KINDS)\n")
        found = phantom_members(broken, "<t>")
        self.assertEqual(sorted(f.split(" at ")[0] for f in found),
                         ["godmode_runtime.godmode_constants.ALSO_MISSING",
                          "godmode_runtime.godmode_constants.NO_SUCH_NAME"], found)

    def test_no_godmode_source_reads_a_phantom_member(self) -> None:
        offenders: dict[str, list[str]] = {}
        for path in _python_files():
            source = path.read_text(encoding="utf-8", errors="replace")
            found = phantom_members(source, str(path), _module_name(path))
            if found:
                offenders[str(path.relative_to(ROOT))] = found
        self.assertEqual(offenders, {}, offenders)


if __name__ == "__main__":
    unittest.main()

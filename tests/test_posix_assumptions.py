"""A test written on Windows must not carry a Windows-only assumption to
the Linux and macOS runners: a backslash parent path (`..\\elsewhere`),
`$env:NAME`, or a drive-letter path in a literal that no `os.name` guard or
skip covers. Two 0.3.33 pull-request failures were exactly this; this check
runs on the changed test modules before a push, on every platform."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TESTS = PLUGIN_ROOT / "tests"

# The two shapes whose meaning depends on the platform the test runs on: a
# backslash parent path (a path on Windows, a filename on POSIX) and the
# temp directory through a PowerShell variable (unset on a POSIX runner).
# A `$env:NAME` that is only classified as text needs no guard.
_WINDOWS_ONLY = re.compile(r"\.\.\\|\$env:(?:TEMP|TMP)\b")
_GUARD = re.compile(r"os\.name|sys\.platform|platform\.system|skipUnless|skipIf")


def windows_only_literals(source: str) -> list[tuple[int, str]]:
    """(line, literal) for every string literal with a Windows-only shape
    whose enclosing function carries no platform guard in its own source,
    and whose enclosing class carries none on its decorators. A literal at
    module level has no guard to carry, so it is always named. Docstrings
    are prose, not commands, and are skipped."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    findings: list[tuple[int, str]] = []

    def decorators_text(node: ast.AST) -> str:
        return "\n".join(ast.get_source_segment(source, d) or "" for d in getattr(node, "decorator_list", []))

    def scan(node: ast.AST, guarded: bool) -> None:
        body = getattr(node, "body", None)
        docstring = body[0] if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                                and isinstance(getattr(body[0], "value", None), ast.Constant)) else None
        for child in ast.iter_child_nodes(node):
            if child is docstring:
                continue
            if isinstance(child, ast.ClassDef):
                scan(child, guarded or bool(_GUARD.search(decorators_text(child))))
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                segment = "\n".join(lines[child.lineno - 1:child.end_lineno])
                scan(child, guarded or bool(_GUARD.search(segment)))
                continue
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if not guarded and _WINDOWS_ONLY.search(child.value):
                    findings.append((child.lineno, child.value[:80]))
            scan(child, guarded)

    scan(tree, False)
    return findings


def changed_test_modules() -> list[Path]:
    """Test modules changed against origin/main, plus untracked ones; empty
    when git cannot answer (a shallow CI checkout with no such ref)."""
    def git(*args: str) -> list[str]:
        done = subprocess.run(["git", *args], cwd=PLUGIN_ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        return done.stdout.splitlines() if done.returncode == 0 else []

    names = set(git("diff", "--name-only", "origin/main", "--", "tests"))
    names |= set(git("ls-files", "--others", "--exclude-standard", "--", "tests"))
    return sorted(PLUGIN_ROOT / n for n in names
                  if n.startswith("tests/test_") and n.endswith(".py") and (PLUGIN_ROOT / n).is_file()
                  and n != "tests/test_posix_assumptions.py")


class PosixAssumptionTests(unittest.TestCase):
    def test_the_detector_names_the_two_shapes_that_failed(self) -> None:
        source = (
            'WINDOWS_STILL_PROTECTED = ("New-Item -ItemType Directory ..\\\\elsewhere\\\\build",)\n'
            "class T:\n"
            "    def test_a(self):\n"
            "        run('Remove-Item -Recurse -Force \"$env:TEMP\\\\x\"')\n"
            "    def test_guarded(self):\n"
            "        if os.name == 'nt':\n"
            "            run('Remove-Item \"$env:TEMP\\\\y\"')\n"
            "    def test_posix_shape(self):\n"
            "        run('New-Item -ItemType Directory ../elsewhere')\n"
        )
        found = windows_only_literals(source)
        self.assertEqual([line for line, _ in found], [1, 4], found)

    def test_a_class_level_skip_guards_every_method(self) -> None:
        source = (
            "@unittest.skipUnless(os.name == 'nt', 'windows')\n"
            "class T:\n"
            "    def test_a(self):\n"
            "        run('dir C:\\\\x')\n"
        )
        self.assertEqual(windows_only_literals(source), [])

    def test_changed_test_modules_carry_no_unguarded_windows_shape(self) -> None:
        findings = []
        for path in changed_test_modules():
            for line, literal in windows_only_literals(path.read_text(encoding="utf-8", errors="replace")):
                findings.append(f"{path.relative_to(PLUGIN_ROOT).as_posix()}:{line}: {literal!r}")
        self.assertEqual(findings, [], "Windows-only literal in a changed test with no os.name or skip guard "
                                       "(use a forward-slash path, or guard it):\n" + "\n".join(findings))


if __name__ == "__main__":
    unittest.main()

"""Repo-wide privacy floor: no banned term anywhere in the shipped tree.

The coverage-map test (test_capability_register) guards one file; this
guards every git-tracked file. Same external-list design, for the same
reason: the term list IS the vocabulary the privacy rule protects, so it
lives outside the repository (see `_banned_terms_path`) and a fresh
clone/CI skips the check while the structural tests still run.

Failure messages never name the matched term - a red test's own output
must not become the second place a term leaks. They name the file and
the count only; the operator diffs against the private list locally.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _banned_terms_path() -> Path | None:
    """Same resolver as test_capability_register: env override, then an
    upward walk for the private ledger's sibling location."""
    override = os.environ.get("GODMODE_COVERAGE_TERMS")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    candidate = PLUGIN_ROOT
    for _ in range(8):
        found = candidate / ".godmode-private" / "coverage-banned-terms.txt"
        if found.is_file():
            return found
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return None


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PLUGIN_ROOT, capture_output=True, check=True,
    ).stdout
    return [PLUGIN_ROOT / p for p in out.decode("utf-8").split("\0") if p]


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


class RepoWidePrivacy(unittest.TestCase):
    def test_no_banned_term_in_any_tracked_file(self) -> None:
        path = _banned_terms_path()
        if path is None:
            self.skipTest(
                "no private banned-term list found (GODMODE_COVERAGE_TERMS unset, and no "
                ".godmode-private/coverage-banned-terms.txt found above the repo root) - "
                "expected on a fresh clone/CI")
        terms = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith("#")]
        self.assertTrue(terms, f"{path} exists but named zero terms")
        patterns = [re.compile(r"\b" + re.escape(t.lower()) + r"\b") for t in terms]
        leaks: dict[str, int] = {}
        for file in _tracked_files():
            if not file.is_file():  # deleted-in-worktree entries
                continue
            data = file.read_bytes()
            if _is_binary(data):
                continue
            text = data.decode("utf-8", errors="replace").lower()
            hits = sum(1 for p in patterns if p.search(text))
            if hits:
                leaks[str(file.relative_to(PLUGIN_ROOT))] = hits
        self.assertFalse(
            leaks,
            "banned terms from the private list leaked into tracked files "
            f"(file -> distinct-term count, terms deliberately unnamed): {leaks}")


if __name__ == "__main__":
    unittest.main()

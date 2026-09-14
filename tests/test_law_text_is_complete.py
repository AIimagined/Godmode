"""Task 7 (D-6): `godmode law compile` must never truncate Guard text.

Observed in the live GODMODE-CODE-OF-LAW.md: Law 3's Guard line ends
"...a criterion precedes every sprint-size..." and Law 4's ends "...until
then...": a guard is the whole rule a session is meant to follow, and a
partial guard silently read as a smaller rule is actually a wrong one.

Resolution: Guard text is always emitted complete - no length cap, no
ellipsis, on the compiled file, on `top_laws()` (the brief's source), and
on `fresh_laws()` (the pre-action overlay). Why/provenance text may still
be shortened for the brief's budget, but only at a word boundary, ending
in "…" - never mid-word.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime import godmode_law  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    LAW_FILENAME, compile_laws, fresh_laws, top_laws,
)


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-law-complete-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


def _lesson(archive, subject, value, guard):
    return archive.append(
        "lesson", subject,
        {"status": "active", "value": value, "generalized_guard": guard},
        evidence=[])


# Deliberately longer than the old 200-char GUARD_CHARS cap, as one
# run-on sentence so no earlier truncation point was ever safe.
LONG_GUARD = (
    "Every long-form guard sentence in this fixture stays inside a single "
    "run-on rule so that no word boundary lands anywhere near the old two "
    "hundred character cap, proving the compiler keeps the whole thing "
    "instead of stopping partway through the instruction it exists to state."
)


class GuardIsCompleteTests(unittest.TestCase):
    def test_compiled_guard_is_never_truncated(self) -> None:
        with _project() as (root, archive):
            self.assertGreater(len(LONG_GUARD), 200)
            _lesson(archive, "long-guard", "value", LONG_GUARD)
            compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        guard_line = next(
            line for line in text.splitlines() if line.startswith("Guard:"))
        self.assertEqual(guard_line, f"Guard: {LONG_GUARD}")
        self.assertNotIn("…", guard_line)

    def test_top_laws_guard_is_never_truncated(self) -> None:
        with _project() as (_root, archive):
            _lesson(archive, "long-guard", "value", LONG_GUARD)
            top = top_laws(archive, 1)
        self.assertEqual(top[0]["guard"], LONG_GUARD)
        self.assertNotIn("…", top[0]["guard"])

    def test_fresh_laws_guard_is_never_truncated(self) -> None:
        with _project() as (root, archive):
            _lesson(archive, "long-guard", "value", LONG_GUARD)
            fresh = fresh_laws(archive, root)
        self.assertEqual(fresh[0]["guard"], LONG_GUARD)
        self.assertNotIn("…", fresh[0]["guard"])


class WhyBreaksOnWordBoundaryTests(unittest.TestCase):
    def test_ellipsize_never_cuts_mid_word(self) -> None:
        # 11-char tokens ("abcdefghij ") never put a space exactly on the
        # limit boundary, so a naive hard slice at WHY_CHARS lands mid-word.
        why = ("abcdefghij " * 40).strip()
        result = godmode_law._ellipsize(why, godmode_law.WHY_CHARS)
        self.assertTrue(result.endswith("…"), result)
        kept = result[:-1]
        self.assertTrue(why.startswith(kept))
        self.assertLess(len(kept), len(why))
        # Word boundary: the next original character right after what was
        # kept is a space - the cut never lands inside a token.
        self.assertEqual(why[len(kept)], " ")

    def test_short_why_is_left_complete(self) -> None:
        why = "a short reason"
        self.assertEqual(
            godmode_law._ellipsize(why, godmode_law.WHY_CHARS), why)

    def test_why_at_exactly_the_limit_is_left_complete(self) -> None:
        why = "y" * godmode_law.WHY_CHARS
        self.assertEqual(
            godmode_law._ellipsize(why, godmode_law.WHY_CHARS), why)

    def test_compiled_why_line_never_ends_mid_word(self) -> None:
        why = ("supercalifragilisticexpialidocious " * 10).strip()
        with _project() as (root, archive):
            _lesson(archive, "long-why", why, "a guard")
            compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        why_line = next(
            line for line in text.splitlines() if line.startswith("Why:"))
        self.assertTrue(why_line.endswith("…"), why_line)
        kept = why_line[len("Why: "):-1]
        self.assertTrue(why.startswith(kept))
        self.assertEqual(why[len(kept)], " ")


if __name__ == "__main__":
    unittest.main()

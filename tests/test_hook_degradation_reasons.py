"""G-6: `record_hook_degradation` reasons are total.

`record_hook_degradation` (`scripts/godmode_runtime/godmode_hookproof.py`)
raises `ValueError` for any reason outside `DEGRADE_REASONS`. Three real
call sites in `hooks/godmode_session_hook.py`
(`interrupted-intent-capture-failed`, `inline-scan-record-failed`,
`ask-only-record-failed`) passed reasons that were never added to that
enum, so the very degradation-recording call meant to survive a failure
instead raised one itself.

This module has two independent guards, so a future call site with a new
literal reason string cannot silently reopen the gap:

- `test_every_literal_reason_is_recordable` statically collects every
  string-literal argument passed to `record_hook_degradation` anywhere
  under `hooks/` and `scripts/`, and asserts each one is a member of
  `DEGRADE_REASONS`.
- `TestThreeReasonsRecordWithoutRaising` calls the real function with each
  of the three previously-unrecordable reasons against a real archive and
  asserts none of them raises.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_hookproof import (  # noqa: E402
    DEGRADE_REASONS,
    SUBJECT_HOOK_DEGRADED,
    record_hook_degradation,
)
from test_godmode_runtime import isolated_project  # noqa: E402

SCANNED_DIRS = [ROOT / "hooks", ROOT / "scripts"]

# The three call sites this defect names (task G-6), pinned verbatim so a
# rename of any one without updating `DEGRADE_REASONS` fails loudly here
# too, independent of the static scan below.
NAMED_CALL_SITE_REASONS = (
    "interrupted-intent-capture-failed",
    "inline-scan-record-failed",
    "ask-only-record-failed",
)


def _literal_reasons_passed_to(source: str, filename: str) -> list[tuple[str, int]]:
    """Every string-literal `reason` argument passed to a call named
    `record_hook_degradation` in `source` - as `(reason, lineno)` pairs.

    Matches both a bare-name call (`record_hook_degradation(...)`, the
    only form this codebase uses today) and a dotted call
    (`module.record_hook_degradation(...)`), so a future call site
    reached through an import alias is still caught. Only literal string
    arguments are collected - a call site that instead passes a named
    `DEGRADE_REASON_*` constant is already pinned by `DEGRADE_REASONS`
    membership at the constant's own definition, not by this scan.
    """
    tree = ast.parse(source, filename)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None)
        if name != "record_hook_degradation":
            continue
        reason_node = None
        if len(node.args) >= 3:
            reason_node = node.args[2]
        else:
            for keyword in node.keywords:
                if keyword.arg == "reason":
                    reason_node = keyword.value
        if isinstance(reason_node, ast.Constant) and isinstance(reason_node.value, str):
            found.append((reason_node.value, node.lineno))
    return found


class TestEveryLiteralReasonIsRecordable(unittest.TestCase):
    def test_every_literal_reason_is_recordable(self) -> None:
        collected: list[tuple[str, str, int]] = []
        for directory in SCANNED_DIRS:
            for path in sorted(directory.rglob("*.py")):
                source = path.read_text(encoding="utf-8")
                for reason, lineno in _literal_reasons_passed_to(source, str(path)):
                    collected.append((str(path.relative_to(ROOT)), reason, lineno))
        # The scan itself must find real call sites - an empty result would
        # let this test pass vacuously if the scan ever stopped matching.
        self.assertGreaterEqual(len(collected), len(NAMED_CALL_SITE_REASONS))
        found_reasons = {reason for _, reason, _ in collected}
        for expected in NAMED_CALL_SITE_REASONS:
            self.assertIn(expected, found_reasons)
        for relative_path, reason, lineno in collected:
            self.assertIn(
                reason, DEGRADE_REASONS,
                f"{relative_path}:{lineno} passes unrecordable reason {reason!r} "
                "to record_hook_degradation - add it to DEGRADE_REASONS",
            )


class TestThreeReasonsRecordWithoutRaising(unittest.TestCase):
    def test_each_named_reason_records_without_raising(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for reason in NAMED_CALL_SITE_REASONS:
                with self.subTest(reason=reason):
                    record_hook_degradation(archive, "claude", reason)
            degradations = archive.select(
                kind="action", subject=SUBJECT_HOOK_DEGRADED, limit=10)
            recorded_reasons = [entry["data"]["reason"] for entry in degradations]
            self.assertEqual(recorded_reasons, list(NAMED_CALL_SITE_REASONS))

    def test_acceptance_repro_no_longer_raises_valueerror_for_known_reason(self) -> None:
        # Acceptance line from the task: `record_hook_degradation(None,
        # 'claude', 'ask-only-record-failed')` must no longer raise
        # `ValueError` for an unknown reason. `archive=None` still fails
        # (there is no chronicle to append to) but that failure must never
        # be the reason-validation `ValueError` this task closes.
        try:
            record_hook_degradation(None, "claude", "ask-only-record-failed")
        except ValueError:
            self.fail(
                "record_hook_degradation raised ValueError for a reason "
                "that must now be recordable")
        except AttributeError:
            pass  # expected: None has no .append - a different, known failure


if __name__ == "__main__":
    unittest.main()

"""NS-8n: obligations name their blockers.

`remember --kind obligation --blocked-by <obligation-id>` (repeatable) stores
the edge; a phantom or circular blocker is refused with the same walker
`record_item`'s `depends_on` already used
(`godmode_status._check_dependencies`, extracted so both paths share one
check). `status remaining` lists a blocked obligation under its blocker
instead of standing alone, and `open_scope` treats it as listed - not
nagged - until the blocker closes.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_iteration as it  # noqa: E402
from godmode_runtime.godmode_console import main  # noqa: E402
from godmode_runtime.godmode_status import _check_dependencies, remaining  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _remember(project: Path, *extra: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(["--project", str(project), "--json", "remember",
                     "--kind", "obligation", *extra])
    text = out.getvalue().strip()
    payload = json.loads(text) if text else {}
    return code, payload


class SharedWalkerTests(unittest.TestCase):
    """`_check_dependencies` is the one walker both `record_item`'s
    `depends_on` and the obligation `blocked_by` path use."""

    def test_a_phantom_dependency_is_refused(self) -> None:
        with self.assertRaises(Exception):
            _check_dependencies({}, "b", ["never-recorded"])

    def test_self_dependency_is_refused(self) -> None:
        with self.assertRaises(Exception):
            _check_dependencies({"a": []}, "a", ["a"])

    def test_a_cycle_is_refused(self) -> None:
        existing = {"a": [], "b": ["a"]}
        with self.assertRaises(Exception):
            # 'a' -> 'b' would close the loop b -> a -> b.
            _check_dependencies(existing, "a", ["b"])

    def test_a_known_acyclic_dependency_is_accepted(self) -> None:
        existing = {"a": []}
        _check_dependencies(existing, "b", ["a"])  # must not raise


class RememberBlockedByTests(unittest.TestCase):
    def test_a_phantom_blocker_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload = _remember(
                project, "--subject", "b-duty", "--value", "second duty",
                "--blocked-by", "never-recorded")
            self.assertEqual(code, 2, payload)
            self.assertEqual(payload.get("error"), "ArchiveError", payload)

    def test_a_self_blocker_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload = _remember(
                project, "--subject", "a-duty", "--value", "first duty",
                "--blocked-by", "a-duty")
            self.assertEqual(code, 2, payload)

    def test_a_circular_blocker_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, _ = _remember(project, "--subject", "a-duty", "--value", "first")
            self.assertEqual(code, 0)
            code, _ = _remember(project, "--subject", "b-duty", "--value", "second",
                                "--blocked-by", "a-duty")
            self.assertEqual(code, 0)
            # Re-recording a-duty blocked-by b-duty would close a-duty -> b-duty -> a-duty.
            code, payload = _remember(project, "--subject", "a-duty", "--value", "first",
                                      "--blocked-by", "b-duty")
            self.assertEqual(code, 2, payload)

    def test_a_known_blocker_is_stored(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, _ = _remember(project, "--subject", "a-duty", "--value", "first duty")
            self.assertEqual(code, 0)
            code, payload = _remember(project, "--subject", "b-duty", "--value", "second duty",
                                      "--blocked-by", "a-duty")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["data"]["blocked_by"], ["a-duty"])


class RemainingRendersBlockedObligationsTests(unittest.TestCase):
    def test_a_blocked_obligation_is_listed_under_its_blocker(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("obligation", "a-duty", {"value": "first duty", "status": "open"}, evidence=[])
            archive.append("obligation", "b-duty",
                           {"value": "second duty", "status": "open", "blocked_by": ["a-duty"]},
                           evidence=[])
            view = remaining(archive, project)
            blocked = {e["id"]: e["blocked_by"] for e in view["blocked"]}
            self.assertIn("b-duty", blocked)
            self.assertIn("a-duty", blocked["b-duty"])
            # It is never lost either way - it still shows up in the flat list.
            self.assertIn("b-duty", {e["id"] for e in view["remaining"] if e["source"] == "obligation"})

    def test_closing_the_blocker_drops_it_from_blocked(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("obligation", "a-duty", {"value": "first duty", "status": "open"}, evidence=[])
            archive.append("obligation", "b-duty",
                           {"value": "second duty", "status": "open", "blocked_by": ["a-duty"]},
                           evidence=[])
            archive.append("obligation", "a-duty", {"value": "first duty", "status": "closed"}, evidence=[])
            view = remaining(archive, project)
            self.assertEqual(view["blocked"], [])


class ObligationExistenceCheckIsUncappedTests(unittest.TestCase):
    """The existence/cycle map `remember --blocked-by` checks against used
    to come from `archive.select(kind="obligation", limit=500)`, which
    hard-caps at 500 and keeps only the newest that many. Past that cap, a
    real, still-open obligation reads as phantom (the blocker check
    refuses a legitimate write) - fixed by building the map from
    `read_events()` filtered to `kind == "obligation"` instead, which is
    uncapped."""

    def test_a_real_blocker_beyond_the_500_cap_is_not_read_as_phantom(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with archive.write_lock():
                count, tail_hash = archive._chain_tail()
                record = archive._write_record(
                    "obligation", "old-duty", {"value": "first duty", "status": "open"}, [],
                    sequence=count + 1, previous_hash=tail_hash)
                count += 1
                tail_hash = record["record_hash"]
                for i in range(600):
                    record = archive._write_record(
                        "obligation", f"filler-{i}", {"value": "filler", "status": "open"}, [],
                        sequence=count + 1, previous_hash=tail_hash)
                    count += 1
                    tail_hash = record["record_hash"]
            # Beyond the old 500-cap window - the last 500 obligation
            # records no longer include "old-duty".
            code, payload = _remember(
                project, "--subject", "new-duty", "--value", "depends on old",
                "--blocked-by", "old-duty")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["data"]["blocked_by"], ["old-duty"])


class OpenScopeListsNotNagsTests(unittest.TestCase):
    def test_a_blocked_obligation_is_listed_but_not_scoped(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("obligation", "a-duty", {"value": "first duty", "status": "open"}, evidence=[])
            archive.append("obligation", "b-duty",
                           {"value": "second duty", "status": "open", "blocked_by": ["a-duty"]},
                           evidence=[])
            scope = it.open_scope(archive, None)
            self.assertTrue(any("b-duty" in entry for entry in scope["blocked_obligations"]))
            self.assertEqual(it.scope_items(scope), [])

    def test_once_unblocked_it_is_no_longer_reported_as_blocked(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("obligation", "a-duty", {"value": "first duty", "status": "closed"}, evidence=[])
            archive.append("obligation", "b-duty",
                           {"value": "second duty", "status": "open", "blocked_by": ["a-duty"]},
                           evidence=[])
            scope = it.open_scope(archive, None)
            self.assertEqual(scope["blocked_obligations"], [])


if __name__ == "__main__":
    unittest.main()

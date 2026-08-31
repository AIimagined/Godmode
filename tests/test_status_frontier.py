"""The ready set is derived, not hand-picked.

`remaining` splits status items into ready (nothing blocking) and
blocked (each with its named blocker): an item is blocked by its
`blocked_on` note, or by any `depends_on` target that is not yet
terminal. Dependencies are existence-checked at write time - a phantom
blocker is refused with the known items named - and a dependency chain
that loops back on itself is refused outright, because a cycle makes
every member unstartable forever.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_status import (  # noqa: E402
    record_item,
    remaining,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class DependencyWriteTests(unittest.TestCase):
    def test_a_phantom_dependency_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_item(archive, "b", "needs a ghost", "proposed",
                            depends_on=["never-recorded"])

    def test_a_cycle_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "a", "first", "proposed")
            record_item(archive, "b", "second", "proposed", depends_on=["a"])
            with self.assertRaises(ArchiveError):
                record_item(archive, "a", "first", "proposed", depends_on=["b"])

    def test_self_dependency_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "a", "first", "proposed")
            with self.assertRaises(ArchiveError):
                record_item(archive, "a", "first", "proposed", depends_on=["a"])


class FrontierTests(unittest.TestCase):
    def test_remaining_splits_ready_from_blocked(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "free", "no blockers", "proposed")
            record_item(archive, "gated", "waits on free", "proposed",
                        depends_on=["free"])
            record_item(archive, "operator-gated", "needs a human", "blocked",
                        blocked_on="operator decision on rollout")
            view = remaining(archive, project)
            ready = {e["id"] for e in view["ready"]}
            blocked = {e["id"]: e["blocked_by"] for e in view["blocked"]}
            self.assertIn("free", ready)
            self.assertNotIn("gated", ready)
            self.assertIn("free", blocked["gated"])
            self.assertIn("operator decision", blocked["operator-gated"])

    def test_resolving_a_blocker_moves_dependents_to_ready(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "free", "no blockers", "proposed")
            record_item(archive, "gated", "waits on free", "proposed",
                        depends_on=["free"])
            record_item(archive, "free", "no blockers", "verified",
                        evidence=["cmd:true"])
            view = remaining(archive, project)
            self.assertIn("gated", {e["id"] for e in view["ready"]})
            self.assertEqual(view["blocked"], [])


if __name__ == "__main__":
    unittest.main()

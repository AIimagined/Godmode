"""A copied archive keeps reading its own records.

The archive's config records the project key it was created under. A checkout
copied with its `.git` (the falsifiability harness, a moved clone) resolves a
different key for the same records; those records are the archive's own, not
a foreign project's, so they verify. A key that is neither the current
anchor's, the archive's birth key, nor an adopted key stays refused.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            yield project, anchor, Chronicle(anchor)


class CopiedArchiveIdentityTests(unittest.TestCase):
    def test_records_written_under_the_birth_key_read_from_a_new_key(self) -> None:
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            for index in range(3):
                archive.append("decision", f"subject-{index}", {"value": index}, evidence=[])
            moved = dataclasses.replace(anchor, project_key="0" * 24)
            copy = Chronicle(moved)
            self.assertIn(anchor.project_key, copy.accepted_keys())
            self.assertEqual(len(copy.read_events()), 3)
            self.assertTrue(copy.verify()["valid"])

    def test_a_foreign_key_is_still_refused(self) -> None:
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            archive.append("decision", "subject", {"value": 1}, evidence=[])
            self.assertNotIn("f" * 24, archive.accepted_keys())
            self.assertEqual(archive.accepted_keys(), {anchor.project_key})


if __name__ == "__main__":
    unittest.main()

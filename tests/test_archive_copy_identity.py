"""A copied archive keeps reading its own records.

The archive's config records the project key it was created under. A checkout
copied with its `.git` (the falsifiability harness, a moved clone) resolves a
different key for the same records; those records are the archive's own, not
a foreign project's, so they verify. A key that is neither the current
anchor's, the archive's birth key, nor an adopted key stays refused.
"""
from __future__ import annotations

import dataclasses
import json
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
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


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


class TrustedPrefixIdentityTests(unittest.TestCase):
    """Row 12 (limits-0.3.29.md #13): a record inside `verify()`'s trusted
    prefix (the fast path an on-disk read index, or a registered
    checkpoint, accelerates past re-hashing) must be checked for identity
    exactly like a record in the untrusted tail - unchanged file-stat
    identity proves the BYTES are what the index recorded, never which
    PROJECT wrote them. Exercised directly against `verify(trusted_prefix=
    ...)` rather than growing an archive past `_INDEX_TAIL_LIMIT` (200) to
    force a real on-disk index - the loop this covers is the same either
    way."""

    def test_a_foreign_record_inside_the_trusted_prefix_is_caught(self) -> None:
        with isolated_project() as (_project, _anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            archive.append("decision", "subject-1", {"value": 1}, evidence=[])
            records = archive.read_events()
            self.assertEqual(len(records), 2)
            tampered = list(records)
            tampered[0] = {**tampered[0], "project_key": "f" * 24}
            outcome = archive.verify(tampered, trusted_prefix=2)
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("project identity mismatch", outcome["message"])
            self.assertEqual(outcome["first_broken_sequence"], 1)

    def test_the_same_break_in_the_untrusted_tail_is_also_caught(self) -> None:
        """Positive control: the tail's own check, unaffected by this fix."""
        with isolated_project() as (_project, _anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            records = archive.read_events()
            tampered = [{**records[0], "project_key": "f" * 24}]
            outcome = archive.verify(tampered, trusted_prefix=0)
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("project identity mismatch", outcome["message"])

    def test_a_born_key_record_inside_the_trusted_prefix_still_verifies(self) -> None:
        """Positive control: a record legitimately within accepted_keys()
        (the ordinary case, every record here) must not become a false
        positive in the trusted prefix."""
        with isolated_project() as (_project, _anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            archive.append("decision", "subject-1", {"value": 1}, evidence=[])
            records = archive.read_events()
            outcome = archive.verify(records, trusted_prefix=2)
            self.assertTrue(outcome["ok"], outcome)


class AppendAcceptsTheBornIdentityTests(unittest.TestCase):
    """Row 12: a moved/copied checkout could read its archive -
    `accepted_keys()` already covers the born identity - but could not
    append to it: `initialize()` checked only the raw current key for an
    exact match, against a bare message naming neither key. The check
    stays exactly as strict (fail-closed, row 12's own security note) - a
    first-time drift still refuses, by design, since there is no
    automatic way to tell a moved checkout apart from a foreign archive
    that happens to share a location. What changed is the message (both
    keys named, a real next step) and that an identity `adopt()` already
    explicitly recorded is recognized, not just the exact current one."""

    def test_a_first_time_moved_checkout_still_refuses_to_append(self) -> None:
        """No prior `adopt()` ever ran for this identity, so there is
        nothing to distinguish "moved" from "foreign" - stays refused."""
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            moved = dataclasses.replace(anchor, project_key="0" * 24)
            copy = Chronicle(moved)
            self.assertTrue(copy.read_events(), "a moved checkout must still read its history")
            with self.assertRaises(ArchiveError) as ctx:
                copy.append("decision", "subject-1", {"value": 1}, evidence=[])
            message = str(ctx.exception)
            self.assertIn(anchor.project_key, message, "the recorded key must be named")
            self.assertIn("0" * 24, message, "the resolved key must be named")

    def test_an_identity_adopt_already_recorded_can_append(self) -> None:
        """The explicit, existing remedy this now names: once `adopt()`
        has recorded a new identity in `adopted_keys` (its own established
        job), a write under that identity is no longer a mismatch."""
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            moved = dataclasses.replace(anchor, project_key="0" * 24)
            copy = Chronicle(moved)
            config = json.loads(copy.config.read_text(encoding="utf-8"))
            config["adopted_keys"] = ["0" * 24]
            copy.config.write_text(json.dumps(config), encoding="utf-8")

            record = copy.append("decision", "subject-1", {"value": 1}, evidence=[])
            self.assertEqual(record["subject"], "subject-1")
            self.assertTrue(copy.verify()["valid"])

    def test_a_genuinely_foreign_identity_still_refuses_to_append(self) -> None:
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            foreign = dataclasses.replace(anchor, project_key="f" * 24)
            other = Chronicle(foreign)
            with self.assertRaises(ArchiveError) as ctx:
                other.append("decision", "subject-1", {"value": 1}, evidence=[])
            message = str(ctx.exception)
            self.assertIn(anchor.project_key, message)
            self.assertIn("f" * 24, message)


if __name__ == "__main__":
    unittest.main()

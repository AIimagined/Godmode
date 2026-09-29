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



class MovedCheckoutSelfAdoptTests(unittest.TestCase):
    """Row 12 residual: a moved or copied checkout could not relink its own
    archive - `adopt()` refuses a destination that holds records, and the
    console called `initialize()` (which refuses the drifted key) before
    it. `godmode adopt --confirm` now relinks in place: operator-confirmed,
    chronicled, the old key kept in `adopted_keys`. Nothing else about the
    append identity check moves."""

    def test_the_moved_archive_relinks_in_place_and_appends_again(self) -> None:
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            for index in range(3):
                archive.append("decision", f"subject-{index}", {"value": index}, evidence=[])
            moved = Chronicle(dataclasses.replace(anchor, project_key="0" * 24))
            drift = moved.identity_drift()
            self.assertEqual(drift["recorded_key"], anchor.project_key)
            self.assertEqual(drift["current_key"], "0" * 24)
            result = moved.adopt_moved_identity()
            self.assertEqual(result["previous_key"], anchor.project_key)
            self.assertTrue(result["chain"]["ok"], result["chain"])
            config = json.loads(moved.config.read_text(encoding="utf-8"))
            self.assertEqual(config["project_key"], "0" * 24)
            self.assertIn(anchor.project_key, config["adopted_keys"])
            records = moved.read_events()
            self.assertEqual(records[-1]["subject"], "archive-identity-adopted")
            self.assertEqual(records[-1]["data"]["previous_key"], anchor.project_key)
            moved.append("decision", "after", {"value": 9}, evidence=[])
            self.assertTrue(moved.verify()["ok"])
            self.assertIsNone(moved.identity_drift())
            with self.assertRaises(ArchiveError):
                moved.adopt_moved_identity()

    def test_a_broken_chain_is_not_adopted(self) -> None:
        with isolated_project() as (_project, anchor, archive):
            archive.initialize()
            archive.append("decision", "subject-0", {"value": 0}, evidence=[])
            archive.append("decision", "subject-1", {"value": 1}, evidence=[])
            first = archive.event_paths()[0]
            record = json.loads(first.read_text(encoding="utf-8"))
            record["data"] = {"value": "edited"}
            first.write_text(json.dumps(record), encoding="utf-8")
            moved = Chronicle(dataclasses.replace(anchor, project_key="0" * 24))
            before = moved.config.read_text(encoding="utf-8")
            with self.assertRaises(ArchiveError):
                moved.adopt_moved_identity()
            self.assertEqual(moved.config.read_text(encoding="utf-8"), before)

    def test_adopt_confirm_relinks_a_moved_git_checkout_end_to_end(self) -> None:
        import io
        import shutil
        import subprocess
        from godmode_runtime import godmode_console as console

        def run(project: Path, *args: str, stdin: str = "") -> tuple[int, dict]:
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out),                     mock.patch.object(sys, "stderr", io.StringIO()):
                with mock.patch.object(sys, "stdin", io.StringIO(stdin)):
                    code = console.main(["--project", str(project), *args])
            return code, json.loads(out.getvalue())

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            original = base / "original"
            original.mkdir()
            subprocess.run(["git", "init", "-q", str(original)], check=True)
            # No state-home override here: with one set, a git project's
            # archive lives under the home keyed by its git directory, so a
            # moved checkout simply resolves a fresh archive and there is
            # no identity to drift. The shipped default keeps the archive
            # under `.git`, where it travels with the checkout - the case
            # `adopt` exists for. The application home is still pointed at
            # the temp dir so the anchor cache never touches the real one.
            environment = {k: v for k, v in os.environ.items() if k != "GODMODE_STATE_HOME"}
            environment["LOCALAPPDATA"] = str(base / "local")
            environment["XDG_STATE_HOME"] = str(base / "local")
            with mock.patch.dict(os.environ, environment, clear=True):
                archive = Chronicle(resolve_anchor(original))
                archive.initialize()
                archive.append("decision", "before-move", {"value": 1}, evidence=[])
                moved = base / "moved"
                shutil.move(str(original), str(moved))
                moved_archive = Chronicle(resolve_anchor(moved))
                self.assertIsNotNone(moved_archive.identity_drift())
                with self.assertRaises(ArchiveError):
                    moved_archive.append("decision", "refused", {"value": 2}, evidence=[])

                code, preview = run(moved, "adopt")
                self.assertEqual(code, 1, preview)
                self.assertEqual(preview["confirm_with"], "--confirm --as-operator")
                # An operator decision: not run as the operator, it is refused
                # and nothing is relinked.
                code, refused = run(moved, "adopt", "--confirm")
                self.assertEqual(code, 1, refused)
                self.assertIn("--as-operator", refused["reason"])
                self.assertIsNotNone(Chronicle(resolve_anchor(moved)).identity_drift())
                # No password set: a terminal answering "y" is not the
                # operator (a pseudo-terminal answers as readily), so it is
                # refused with the setup remedy and nothing is relinked.
                class _Terminal(io.StringIO):
                    def isatty(self) -> bool:
                        return True

                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out), \
                        mock.patch.object(sys, "stderr", io.StringIO()), \
                        mock.patch.object(sys, "stdin", _Terminal("y\n")):
                    code = console.main(["--project", str(moved), "adopt", "--confirm",
                                         "--as-operator"])
                unset = json.loads(out.getvalue())
                self.assertEqual(code, 1, unset)
                self.assertIn("godmode authorize setup", unset["reason"])
                self.assertEqual(unset["remedy"], "godmode authorize setup")
                self.assertIsNotNone(Chronicle(resolve_anchor(moved)).identity_drift())
                from godmode_runtime.godmode_sentinel import CapabilityBroker

                CapabilityBroker(moved_archive).configure("relink operator")
                code, adopted = run(moved, "adopt", "--confirm", "--as-operator",
                                    "--password-stdin", stdin="relink operator\n")
                self.assertEqual(code, 0, adopted)
                self.assertEqual(adopted["adopted"], "moved-checkout")

                after = Chronicle(resolve_anchor(moved))
                after.append("decision", "after-move", {"value": 3}, evidence=[])
                subjects = [r["subject"] for r in after.read_events()]
                self.assertEqual(subjects, ["before-move", "archive-identity-adopted",
                                            "after-move"])
                self.assertTrue(after.verify()["ok"])


if __name__ == "__main__":
    unittest.main()

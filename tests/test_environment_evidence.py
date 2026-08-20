"""A run under a different environment is not evidence about this one.

The taxonomy this comes from names it plainly: reproduce under the relevant
runtime when behaviour diverges. This project learned it twice in one day —
a detector that reported nothing on a shallow checkout was called broken by a
test written where history existed, and a suite green on one machine went red
on six CI jobs for a reason that had nothing to do with the code.

An attestation already records who wrote it: host, model, effort, enforcement.
It did not record *where*, so a claim could cite a command that ran on another
operating system or interpreter and nothing in the record would say so.

Recorded, not refused. Cross-platform work is ordinary and blocking it would be
absurd; what must not happen is a result being read as a statement about this
environment when it was produced in a different one.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_chronicle import writer_fingerprint  # noqa: E402
from godmode_runtime.godmode_attest import evidence_from_elsewhere  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class FingerprintTests(unittest.TestCase):
    def test_the_writer_records_where_it_ran(self) -> None:
        print_ = writer_fingerprint()
        for field in ("platform", "python"):
            self.assertIn(field, print_)
            self.assertTrue(print_[field])

    def test_the_writer_records_which_agent_wrote_it(self) -> None:
        """Host and model are not an identity when two agents share a host.

        Without this, records from two concurrent lanes interleave into one
        indistinguishable stream and the fleet layer can name a lease
        holder it cannot then find in the archive.
        """
        from godmode_runtime.godmode_fleet import agent_id

        print_ = writer_fingerprint()
        self.assertIn("agent_id", print_)
        self.assertEqual(print_["agent_id"], agent_id())

    def test_the_fingerprint_carries_no_machine_identity(self) -> None:
        """A hostname or a user path names a person, and this is written to a
        record that travels."""
        joined = " ".join(writer_fingerprint().values()).lower()
        for leak in (os.path.expanduser("~").lower(), "users\\", "/home/"):
            if leak:
                self.assertNotIn(leak, joined)


class MismatchTests(unittest.TestCase):
    def _attest(self, archive, session: str, citation: str, platform: str) -> None:
        from godmode_runtime.godmode_attest import record_step

        with mock.patch.dict(os.environ, {"GODMODE_PLATFORM_OVERRIDE": platform}):
            record_step(archive, session, "ran it", "ran",
                        result="ok", evidence=[citation])

    def test_a_run_from_another_platform_is_named(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            self._attest(archive, "s1", "cmd:pytest -q", "some-other-os")
            elsewhere = evidence_from_elsewhere(archive, ["cmd:pytest -q"])
        self.assertTrue(elsewhere)
        self.assertIn("some-other-os", elsewhere[0]["ran_on"])

    def test_a_run_from_this_platform_is_not(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            from godmode_runtime.godmode_attest import record_step

            record_step(archive, "s1", "ran it", "ran",
                        result="ok", evidence=["cmd:pytest -q"])
            self.assertEqual(evidence_from_elsewhere(archive, ["cmd:pytest -q"]), [])

    def test_a_citation_with_no_run_reports_nothing(self) -> None:
        """Absent is not mismatched; the citation simply does not resolve, and
        that is a different finding with a different remedy."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(evidence_from_elsewhere(archive, ["cmd:never-ran"]), [])


if __name__ == "__main__":
    unittest.main()

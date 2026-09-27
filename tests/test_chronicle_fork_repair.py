"""`godmode doctor --repair-fork`: undo a same-sequence fork at the tip.

Field shape: two writers sealed records at the same sequence with the same
previous hash, and every later write refused with "chain broken ... not
contiguous". The repair keeps the sibling the chain anchor names (the
earliest when no anchor names one), moves the others - never deletes them -
into a quarantine folder beside the events directory, records the repair
as its own record, and re-verifies. Any other shape is refused unchanged.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
import uuid
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_chronicle import _record_hash  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


PASSWORD = "fork repair operator"


def _doctor(project: Path, *args: str, stdin: str = "") -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()), \
            mock.patch.object(sys, "stdin", io.StringIO(stdin)):
        code = console.main(["--project", str(project), "doctor", *args])
    return code, json.loads(out.getvalue())


def _as_operator(project: Path, archive) -> tuple[int, dict]:
    """`doctor --repair-fork` run by the operator: password verified."""
    from godmode_runtime.godmode_sentinel import CapabilityBroker

    CapabilityBroker(archive).configure(PASSWORD)
    return _doctor(project, "--repair-fork", "--as-operator", "--password-stdin",
                   stdin=PASSWORD + "\n")


def _sibling(archive, of: dict, *, recorded_at: str, anchor: str,
             previous_hash: str | None = "same") -> tuple[Path, dict]:
    """Seal a second record at `of`'s sequence, the way a racing writer did."""
    record = {key: value for key, value in of.items() if key != "record_hash"}
    record["record_id"] = uuid.uuid4().hex
    record["recorded_at"] = recorded_at
    record["data"] = {**record["data"], "anchor": anchor}
    if previous_hash != "same":
        record["previous_hash"] = previous_hash
    record["record_hash"] = _record_hash(record)
    path = archive.events / f"{record['sequence']:012d}-{record['record_id']}.godmode.json"
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path, record


def _names(archive) -> list[str]:
    return [path.name for path in archive.event_paths()]


class ForkRepairTests(unittest.TestCase):
    def _forked(self, archive) -> tuple[dict, Path, dict]:
        archive.initialize()
        archive.append("claim", "one", {"text": "x"})
        archive.append("claim", "two", {"text": "y"})
        earlier = archive.append("action", "cooldown", {"anchor": "first"})
        later_path, later = _sibling(archive, earlier, recorded_at="2999-01-01T00:00:00+00:00",
                                     anchor="second")
        return earlier, later_path, later

    def test_the_sibling_the_anchor_names_is_kept_and_the_other_quarantined(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            earlier, _later_path, later = self._forked(archive)
            # The later writer's anchor landed last, as in the field.
            archive._write_chain_anchor(3, later["record_hash"])
            self.assertFalse(archive.verify(
                [archive._read_json(p) for p in archive.event_paths()])["ok"])
            code, report = _as_operator(project, archive)
            repair = report["fork_repair"]
            self.assertTrue(repair["repaired"], report)
            self.assertEqual(repair["kept_by"], "anchor")
            self.assertIn(later["record_id"], repair["kept"])
            self.assertEqual(len(repair["quarantined"]), 1)
            self.assertIn(earlier["record_id"], repair["quarantined"][0])
            quarantined = Path(repair["quarantine"]) / repair["quarantined"][0]
            self.assertTrue(quarantined.is_file(), "the other sibling was deleted, not moved")
            self.assertEqual(Path(repair["quarantine"]).parent.parent, archive.root)
            self.assertTrue(report["archive"]["ok"], report["archive"])
            records = archive.read_events()
            self.assertEqual([r["sequence"] for r in records], [1, 2, 3, 4])
            self.assertEqual(records[2]["record_hash"], later["record_hash"])
            self.assertEqual(records[3]["subject"], "chain-fork-repaired")
            self.assertEqual(records[3]["data"]["sequence"], 3)
            # Writes work again.
            archive.append("claim", "after", {"text": "z"})
            self.assertTrue(archive.verify()["ok"])

    def test_a_repair_not_run_as_the_operator_is_refused_and_leaves_the_fork(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            self._forked(archive)
            before = _names(archive)
            code, report = _doctor(project, "--repair-fork")
            self.assertEqual(code, 1)
            self.assertFalse(report["fork_repair"]["repaired"])
            self.assertIn("--as-operator", report["fork_repair"]["reason"])
            self.assertEqual(_names(archive), before)
            from godmode_runtime.godmode_sentinel import CapabilityBroker

            CapabilityBroker(archive).configure(PASSWORD)
            code, report = _doctor(project, "--repair-fork", "--as-operator",
                                   "--password-stdin", stdin="wrong\n")
            self.assertEqual(code, 1)
            self.assertIn("did not verify", report["fork_repair"]["reason"])
            self.assertEqual(_names(archive), before)

    def test_without_a_password_a_terminal_yes_is_not_the_operator(self) -> None:
        """A pseudo-terminal answers a y/N prompt as readily as a person, so
        with no password set the repair is refused with the setup remedy."""
        class _Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        with isolated_project() as (project, _state, _anchor, archive):
            self._forked(archive)
            before = _names(archive)
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()), \
                    mock.patch.object(sys, "stdin", _Terminal("y\n")):
                code = console.main(["--project", str(project), "doctor", "--repair-fork",
                                     "--as-operator"])
            report = json.loads(out.getvalue())
            self.assertEqual(code, 1, report)
            self.assertFalse(report["fork_repair"]["repaired"])
            self.assertIn("godmode authorize setup", report["fork_repair"]["reason"])
            self.assertEqual(report["fork_repair"]["remedy"], "godmode authorize setup")
            self.assertEqual(_names(archive), before)

    def test_without_an_anchor_at_the_fork_the_earliest_is_kept(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            earlier, _later_path, _later = self._forked(archive)
            archive.chain_anchor.unlink()
            repair = archive.repair_fork()
            self.assertEqual(repair["kept_by"], "earliest")
            self.assertIn(earlier["record_id"], repair["kept"])
            self.assertTrue(repair["chain"]["ok"], repair["chain"])

    def test_no_fork_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"})
            code, report = _as_operator(project, archive)
            self.assertEqual(code, 1)
            self.assertFalse(report["fork_repair"]["repaired"])
            self.assertIn("No fork", report["fork_repair"]["reason"])

    def test_other_shapes_are_refused_and_left_untouched(self) -> None:
        cases = {
            "different predecessor": lambda archive, tip, second: _sibling(
                archive, tip, recorded_at="2999", anchor="x", previous_hash="0" * 64),
            "not at the tip": lambda archive, tip, second: _sibling(
                archive, second, recorded_at="2999", anchor="x"),
            "tampered sibling": lambda archive, tip, second: self._tampered(archive, tip),
        }
        for name, make in cases.items():
            with self.subTest(name), isolated_project() as (_p, _s, _a, archive):
                archive.initialize()
                archive.append("claim", "one", {"text": "x"})
                second = archive.append("claim", "two", {"text": "y"})
                tip = archive.append("claim", "three", {"text": "z"})
                make(archive, tip, second)
                before = _names(archive)
                with self.assertRaises(ArchiveError) as ctx:
                    archive.repair_fork()
                self.assertIn("Refusing to repair", str(ctx.exception))
                self.assertEqual(_names(archive), before)
                self.assertFalse((archive.root / "godmode-quarantine").exists())

    @staticmethod
    def _tampered(archive, tip: dict) -> None:
        path, record = _sibling(archive, tip, recorded_at="2999", anchor="x")
        record["data"]["anchor"] = "edited after sealing"
        path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

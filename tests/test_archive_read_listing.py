"""A fresh read of a large archive lists the events directory once and
opens only the records the read index does not already hold.

Field report 2026-09-23: on an archive of about 20,000 records, a hook's
first read stat-ed every record file one at a time to check the read index
(about 4.4 s of a 7.5 s read, measured), after `_events_identity` had
already listed the directory with the same (name, mtime, size) for every
file. That walk ran on every hook call in every initialized project, and
it grew with the archive.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
import uuid

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _path in (PLUGIN_ROOT / "scripts", Path(__file__).parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from godmode_runtime import godmode_chronicle as chronicle  # noqa: E402
from godmode_runtime.godmode_anchor import anchor_fingerprint  # noqa: E402
from godmode_runtime.godmode_chronicle import (  # noqa: E402
    TRUST_ORDER, Chronicle, _record_hash, writer_fingerprint)
from godmode_runtime.godmode_constants import SCHEMA_VERSION  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

COUNT = 260  # past the read index's 200-record tail, so a read writes one


def _fabricate(archive: Chronicle, count: int) -> None:
    """Chain-valid records written straight to disk (the same shortcut the
    memory-contract load test takes: no fsync per record)."""
    sequence, tail = archive._chain_tail()
    now = datetime.now(timezone.utc).isoformat()
    for index in range(count):
        seq = sequence + 1 + index
        record_id = uuid.uuid4().hex
        record = {
            "schema_version": SCHEMA_VERSION, "project_key": archive.anchor.project_key,
            "sequence": seq, "record_id": record_id, "recorded_at": now,
            "anchor_fingerprint": anchor_fingerprint(archive.anchor),
            "agent": writer_fingerprint(), "writer": "agent", "trust": TRUST_ORDER["agent"],
            "kind": "decision", "subject": f"fixture-{index}",
            "data": {"value": index}, "evidence": [], "previous_hash": tail,
        }
        record["record_hash"] = _record_hash(record)
        tail = record["record_hash"]
        (archive.events / f"{seq:012d}-{record_id}.godmode.json").write_text(
            json.dumps(record), encoding="utf-8")
    archive._write_chain_anchor(sequence + count, tail)
    archive._write_head(sequence + count, tail)
    archive._drop_events_cache(rewrite=True)


class FreshReadListsOnceTests(unittest.TestCase):
    def test_an_indexed_read_stats_no_record_file_and_parses_only_the_tail(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            _fabricate(archive, COUNT)
            total = len(archive.read_events())  # verifies the chain, writes the index
            self.assertTrue((archive.root / Chronicle._INDEX_NAME).is_file())
            archive.append("decision", "after-the-index", {}, evidence=[])

            fresh = Chronicle(anchor)
            fresh.pin_identity()  # what every hook does first
            real_stat = Path.stat
            stats: list[str] = []

            def counting_stat(path: Path, *args, **kwargs):
                if path.name.endswith(".godmode.json"):
                    stats.append(path.name)
                return real_stat(path, *args, **kwargs)

            with mock.patch.object(Path, "stat", counting_stat), \
                    mock.patch.object(Chronicle, "_read_json",
                                      side_effect=Chronicle._read_json) as parsed:
                records = fresh.read_events()
            self.assertEqual(len(records), total + 1)
            self.assertEqual(stats, [], "the read stat-ed record files one by one")
            record_reads = [c.args[0] for c in parsed.call_args_list
                            if Path(c.args[0]).name.endswith(".godmode.json")]
            self.assertEqual(len(record_reads), 1, f"only the record after the index is parsed: {record_reads}")

    def test_a_record_rewritten_in_place_is_still_caught(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            _fabricate(archive, COUNT)
            archive.read_events()
            target = archive.event_paths()[5]
            record = json.loads(target.read_text(encoding="utf-8"))
            record["data"] = {"value": "tampered"}
            target.write_text(json.dumps(record), encoding="utf-8")
            fresh = Chronicle(anchor)
            fresh.pin_identity()
            with self.assertRaises(ArchiveError):
                fresh.read_events()

    def test_a_stray_upper_case_record_copy_is_seen_by_every_listing(self) -> None:
        """Review 2026-09-23 (H2): the directory glob matched a stray
        `.GODMODE.JSON` copy case-insensitively on Windows and macOS while
        the identity scan's suffix test did not, so the listing-based read
        quietly skipped a file the old read broke the chain on. Both now
        use one predicate, and the stray copy breaks the chain again."""
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            _fabricate(archive, COUNT)
            archive.read_events()
            original = archive.event_paths()[10]
            # A different record id: on a case-insensitive filesystem the
            # same name in upper case would simply be the same file.
            stray = original.with_name(original.name[:13] + "e" * 32 + ".GODMODE.JSON")
            stray.write_bytes(original.read_bytes())
            fresh = Chronicle(anchor)
            identity = fresh._events_identity()
            self.assertEqual(sorted(fresh._listing_for(identity)),
                             [p.name for p in fresh.event_paths()])
            fresh.pin_identity()
            with self.assertRaises(ArchiveError):
                fresh.read_events()

    def test_the_prefix_identity_is_the_same_from_a_listing_or_from_stat(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _fabricate(archive, 5)
            identity = archive._events_identity()
            listing = archive._listing_for(identity)
            self.assertIsNotNone(listing)
            paths = archive.event_paths()
            listed = chronicle._ListedPaths(archive.events, sorted(listing))
            self.assertEqual(Chronicle._prefix_identity(listed, listing),
                             Chronicle._prefix_identity(paths))
            self.assertEqual([str(p) for p in listed], [str(p) for p in paths])


if __name__ == "__main__":
    unittest.main()

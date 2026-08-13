"""The archive parse is memoized on file identity, not on hope.

read_events() re-parsed every record file on every call - 384 individual
JSON reads costing ~64ms in one profiled hook run, with read_events called
twice directly plus more through latest_session/watchdog inside a single
invocation. The cache key is (count, newest-file-name, mtime_ns, size):
events live in MANY files, not one, so the identity reuses _tail_entry()'s
existing count+newest scan rather than assuming a single events path.

expunge() mutates records returned from read_events() in place (rewriting
data/evidence/hash on the record it expunges and every one after it) - a
real aliasing hazard once the cache shares one list of dict objects across
calls. Pinned here as a correctness test, not just a speed one.
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

from test_godmode_runtime import isolated_project  # noqa: E402


class ChronicleCacheTests(unittest.TestCase):
    def test_second_read_returns_identical_records(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"}, evidence=[])
            first = archive.read_events()
            second = archive.read_events()
        self.assertEqual(first, second)

    def test_second_read_is_a_cache_hit(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"}, evidence=[])
            first = archive.read_events()
            second = archive.read_events()
        # Identity, not equality: the cached list object comes back, so a
        # caller mutating one copy cannot silently diverge from another.
        self.assertIs(first, second)

    def test_append_invalidates(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"}, evidence=[])
            before = archive.read_events()
            archive.append("claim", "two", {"text": "y"}, evidence=[])
            after = archive.read_events()
        self.assertEqual(len(after), len(before) + 1)
        self.assertIsNot(before, after)

    def test_external_write_is_seen(self) -> None:
        # A second Chronicle instance writing the same archive must be
        # visible on the next read: the key is file identity, not a
        # cross-process invalidation protocol.
        with isolated_project() as (_p, _s, anchor, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"}, evidence=[])
            stale = archive.read_events()
            from godmode_runtime.godmode_chronicle import Chronicle
            other = Chronicle(anchor)
            other.append("claim", "two", {"text": "y"}, evidence=[])
            fresh = archive.read_events()
        self.assertEqual(len(fresh), len(stale) + 1)

    def test_accepted_keys_does_not_reread_config_per_call(self) -> None:
        # verify() calls accepted_keys() once PER RECORD - found by tracing
        # a real hook invocation where events-cache hits still cost 384
        # _read_json calls on a 96-record archive: 3 read_events(verify=True)
        # calls x 96 accepted_keys() config re-reads each, plus one real
        # event-file parse (288 + 96 = 384). Pre-existing, not introduced by
        # the events cache - just newly dominant once the bigger cost was
        # fixed. accepted_keys() must not re-read the config file from disk
        # on every call once nothing about it has changed.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            import unittest.mock as mock
            from pathlib import Path
            real_read_text = Path.read_text
            calls = []
            def counting_read_text(self, *a, **k):
                if self.name == "godmode-archive.json":
                    calls.append(1)
                return real_read_text(self, *a, **k)
            with mock.patch.object(Path, "read_text", counting_read_text):
                archive.accepted_keys()
                archive.accepted_keys()
                archive.accepted_keys()
            self.assertEqual(len(calls), 1,
                             "accepted_keys() re-read the config file on a "
                             "call where nothing about it had changed")

    def test_tampering_an_older_record_still_fails_verify(self) -> None:
        # The class this whole cache design nearly shipped broken: mutating
        # a record OTHER than the newest (no file added, no count change)
        # must still invalidate the cache, or verify() would pass on
        # tampered disk content because it re-checked stale, pre-tamper
        # in-memory data. Caught live by test_godmode_runtime's own
        # tamper-evidence test; pinned here as this module's own guard.
        from godmode_runtime.godmode_errors import ArchiveError
        import json
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            archive.append("lesson", "guard", {"value": "verify"}, evidence=[])
            archive.read_events()  # warm the cache
            first = archive.event_paths()[0]
            payload = json.loads(first.read_text(encoding="utf-8"))
            payload["data"]["value"] = "altered"
            first.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArchiveError):
                archive.verify()

    def test_verify_false_still_uses_the_cache(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "x"}, evidence=[])
            verified = archive.read_events(verify=True)
            unverified = archive.read_events(verify=False)
        self.assertIs(verified, unverified)

    def test_expunge_does_not_corrupt_the_cache(self) -> None:
        # The real aliasing hazard: expunge() mutates records it read from
        # read_events() in place. If the cache shares those dict objects,
        # a later read_events() call would return already-expunged content
        # from BEFORE expunge wrote anything to disk, or a torn hybrid.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("claim", "one", {"text": "secret-shaped"}, evidence=[])
            archive.append("claim", "two", {"text": "y"}, evidence=[])
            archive.read_events()  # warm the cache before expunging
            archive.expunge(1, "leaked secret shape")
            after = archive.read_events()
        self.assertEqual(after[0]["data"], {"expunged": True,
                                            "reason": "leaked secret shape"})
        # The chain must still verify: expunge re-seals every record after
        # the expunged one, and a corrupted cache would desync that reseal
        # from what actually landed on disk.
        result = archive.verify()
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()

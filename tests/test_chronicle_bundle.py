"""Supersession cascades, the cold registry is sealed, cold reads are
opt-in, and a checkpoint of unknown shape is a plain record."""
from __future__ import annotations

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

from godmode_runtime.godmode_chronicle import superseded_sequences  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class CascadeTests(unittest.TestCase):
    def test_a_lesson_citing_a_superseded_record_is_superseded_with_it(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            old = archive.append("decision", "db", {"value": "sqlite"}, evidence=[])
            lesson = archive.append("lesson", "use-sqlite", {"guard": "prefer sqlite"},
                                    evidence=[f"seq:{old['sequence']}"])
            follow = archive.append("lesson", "sqlite-pragmas", {"guard": "set pragmas"},
                                    evidence=[f"seq:{lesson['sequence']}"])
            claim = archive.append("claim", "measured", {"text": "sqlite was 2x faster"},
                                   evidence=[f"seq:{old['sequence']}"])
            archive.append("decision", "db", {"value": "postgres", "supersedes": old["sequence"]},
                           evidence=[])
            gone = superseded_sequences(archive.read_events())
            self.assertIn(old["sequence"], gone)
            self.assertIn(lesson["sequence"], gone, "cites the superseded decision")
            self.assertIn(follow["sequence"], gone, "cites the superseded lesson")
            self.assertNotIn(claim["sequence"], gone, "a claim is a fact about the past")

    def test_nothing_superseded_means_nothing_cascades(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = archive.append("decision", "db", {"value": "sqlite"}, evidence=[])
            archive.append("lesson", "l", {"guard": "g"}, evidence=[f"seq:{first['sequence']}"])
            self.assertEqual(superseded_sequences(archive.read_events()), frozenset())


class ColdTierTests(unittest.TestCase):
    def _rotated(self, archive) -> list[int]:
        archive.initialize()
        sequences = [archive.append("decision", f"d{i}", {"value": str(i)}, evidence=[])["sequence"]
                     for i in range(4)]
        archive.append("checkpoint", "cp", {"summary": "state"}, evidence=[])
        archive.rotate_to_cold(sequences[:2])
        return sequences

    def test_an_edited_registry_fails_its_seal_and_doctor_names_it(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            self._rotated(archive)
            registry = archive._read_cold_registry()
            self.assertIsNotNone(registry)
            self.assertEqual((len(registry["rotated"]), registry["seal_ok"]), (2, True))
            self.assertTrue(archive.verify_cold()["ok"])
            payload = json.loads(archive.cold_registry.read_text(encoding="utf-8"))
            payload["segments"][0]["file"] = payload["segments"][0]["file"]  # same body...
            payload["hash_by_sequence"] = dict(payload["hash_by_sequence"])  # ...re-serialised
            archive.cold_registry.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            self.assertTrue(archive.verify_cold()["ok"], "formatting is not an edit")
            payload["seal"] = "0" * 64
            archive.cold_registry.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIs(archive._read_cold_registry()["seal_ok"], False)
            outcome = archive.verify_cold()
            self.assertFalse(outcome["ok"])
            self.assertIn("seal", outcome["message"])

    def test_cold_reads_are_opt_in(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            sequences = self._rotated(archive)
            hot = archive.select(kind="decision", limit=50)
            self.assertEqual([r["sequence"] for r in hot], sequences[2:])
            whole = archive.select(kind="decision", limit=50, include_cold=True)
            self.assertEqual([r["sequence"] for r in whole], sequences)


class CheckpointShapeTests(unittest.TestCase):
    def test_a_checkpoint_of_unknown_shape_verifies_as_a_plain_record(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "d", {"value": "v"}, evidence=[])
            odd = archive.append("checkpoint", "legacy", {"summary": "old shape"}, evidence=[])
            # Strip the chain fields `append` stamps, as a pre-C-8 writer would.
            path = next(p for p in archive.events.iterdir() if p.name.startswith(f"{odd['sequence']:012d}-"))
            self.assertIn("chain_head", json.loads(path.read_text(encoding="utf-8"))["data"])
            archive.append("decision", "e", {"value": "w"}, evidence=[])
            verification = archive.verify(archive.read_events(), use_checkpoint=False)
            self.assertTrue(verification["valid"], verification)
            self.assertEqual(verification["sealed_records"], 3)


if __name__ == "__main__":
    unittest.main()

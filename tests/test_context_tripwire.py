"""The context tripwire says "compact" - and, since 2026-09-11, also
says when compaction cannot help. Two field reports: a measured 313,385
against a declared 200,000 window (the declaration was stale, the model
had a larger window; advising a compact was wrong), and a session where
compaction had already run and the recent window alone filled the
budget (the WeKnora compactor's ErrNothingToCompact, in ledger terms).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_iteration import context_advice, context_size  # noqa: E402


def _transcript(lines: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for entry in lines:
        handle.write(json.dumps(entry) + "\n")
    handle.close()
    return Path(handle.name)


def _assistant(tokens: int) -> dict:
    return {"type": "assistant", "message": {"usage": {"input_tokens": tokens}}}


def _boundary(post: int) -> dict:
    return {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"postTokens": post}}


class ContextSizeTests(unittest.TestCase):
    def test_compaction_markers_are_counted_with_the_post_size(self) -> None:
        path = _transcript([_assistant(150_000), _boundary(120_000), _assistant(160_000)])
        size = context_size(path)
        self.assertEqual(size["tokens"], 160_000)
        self.assertEqual(size["compactions"], 1)
        self.assertEqual(size["last_compaction_post_tokens"], 120_000)


class ContextAdviceTests(unittest.TestCase):
    def test_below_the_line_says_nothing(self) -> None:
        self.assertIsNone(context_advice({"tokens": 100_000, "source": "measured", "compactions": 0}, 200_000))

    def test_over_the_line_advises_a_steered_compact(self) -> None:
        text = context_advice({"tokens": 150_000, "source": "measured", "compactions": 0}, 200_000)
        self.assertIn("steered compact", text)

    def test_a_measurement_past_the_declared_window_names_a_stale_declaration(self) -> None:
        text = context_advice({"tokens": 313_385, "source": "measured", "compactions": 0}, 200_000)
        self.assertIn("declared window", text)
        self.assertIn("context_window", text)
        self.assertNotIn("steered compact", text)

    def test_a_compaction_that_freed_little_stops_advising_another(self) -> None:
        size = {"tokens": 150_000, "source": "measured", "compactions": 1,
                "last_compaction_post_tokens": 120_000}
        text = context_advice(size, 200_000)
        self.assertIn("already ran", text)
        self.assertNotIn("steered compact", text)


if __name__ == "__main__":
    unittest.main()

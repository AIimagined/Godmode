"""Measure the session from the host's own log, and keep only numbers.

The one figure this product could never support is what it cost to run. Its
token metric measures how far the archive brief compresses the records, which is
routinely misread as a saving, and its own `counterfactual-claim` check is high
severity precisely to stop anyone writing the sentence that would.

The host already writes a full session transcript to disk and passes its path to
every hook. Nothing here read it. Comparable local-only projects measure
themselves exactly this way and transmit nothing; the privacy boundary was never
what stopped this one.

**The privacy contract is the point of this file.** A transcript contains
prompts, source, and file paths. The declared limit `raw_prompts_stored: false`
does not bend for a metric, so the tests below assert that no fragment of a
transcript's content survives measurement — not that a comment promises it.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_usage import measure_session  # noqa: E402


# Distinctive strings that must never reach the result.
SECRET_PROMPT = "REFACTOR-THE-PAYROLL-EXPORT-FOR-ACME"
SECRET_PATH = "/home/someone/private/salaries.csv"
SECRET_CODE = "api_key = 'zzzz-not-a-real-key-zzzz'"


def _transcript(*, turns: int = 3) -> tempfile.TemporaryDirectory:
    holder = tempfile.TemporaryDirectory(prefix="godmode-usage-")
    path = Path(holder.name) / "session.jsonl"
    lines = []
    for index in range(turns):
        lines.append(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": f"{SECRET_PROMPT} step {index}"},
        }))
        lines.append(json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"editing {SECRET_PATH}"},
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": SECRET_PATH, "new_string": SECRET_CODE}},
                ],
                "usage": {
                    "input_tokens": 100, "output_tokens": 20,
                    "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3,
                },
            },
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    holder._path = path  # type: ignore[attr-defined]
    return holder


class MeasurementTests(unittest.TestCase):
    def test_usage_is_summed_across_the_session(self) -> None:
        holder = _transcript(turns=3)
        with holder:
            result = measure_session(holder._path)  # type: ignore[attr-defined]
        self.assertEqual(result["input_tokens"], 300)
        self.assertEqual(result["output_tokens"], 60)
        self.assertEqual(result["cache_read_tokens"], 15)
        self.assertEqual(result["assistant_turns"], 3)
        self.assertEqual(result["tool_calls"], 3)

    def test_an_absent_transcript_is_insufficient_data_not_zero(self) -> None:
        """Zero is a measurement. Absent is not, and reporting one as the other
        is how a dashboard starts lying quietly."""
        result = measure_session(Path("does-not-exist.jsonl"))
        self.assertEqual(result["confidence"], "insufficient-data")
        self.assertIsNone(result["input_tokens"])

    def test_a_malformed_line_does_not_abandon_the_rest(self) -> None:
        holder = _transcript(turns=2)
        path = holder._path  # type: ignore[attr-defined]
        with holder:
            path.write_text("{not json\n" + path.read_text(encoding="utf-8"),
                            encoding="utf-8")
            result = measure_session(path)
        self.assertEqual(result["input_tokens"], 200)
        self.assertEqual(result["unreadable_lines"], 1)


class PrivacyContractTests(unittest.TestCase):
    """The tests that decide whether this feature may exist at all."""

    def test_no_prompt_path_or_code_survives_measurement(self) -> None:
        holder = _transcript(turns=2)
        with holder:
            result = measure_session(holder._path)  # type: ignore[attr-defined]
        serialised = json.dumps(result)
        for secret in (SECRET_PROMPT, SECRET_PATH, SECRET_CODE):
            self.assertNotIn(secret, serialised, "transcript content escaped into the result")

    def test_the_result_contains_only_numbers_and_declared_labels(self) -> None:
        """A free-text field is where content leaks next, so the shape is
        asserted rather than the current contents of it."""
        holder = _transcript(turns=1)
        with holder:
            result = measure_session(holder._path)  # type: ignore[attr-defined]
        allowed_text = {"confidence", "source"}
        for key, value in result.items():
            if key in allowed_text:
                self.assertIn(value, {"measured", "insufficient-data", "session-transcript"})
                continue
            self.assertIsInstance(value, (int, type(None)), f"{key} is not a count")

    def test_the_transcript_path_itself_is_not_recorded(self) -> None:
        """The path names a project and often a person."""
        holder = _transcript(turns=1)
        with holder:
            result = measure_session(holder._path)  # type: ignore[attr-defined]
            self.assertNotIn(str(holder._path), json.dumps(result))  # type: ignore[attr-defined]

    def test_nothing_is_written_anywhere_by_measuring(self) -> None:
        """Measurement reads; recording is the caller's decision."""
        holder = _transcript(turns=1)
        with holder:
            root = Path(holder.name)
            before = {p.name for p in root.iterdir()}
            measure_session(holder._path)  # type: ignore[attr-defined]
            self.assertEqual({p.name for p in root.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()

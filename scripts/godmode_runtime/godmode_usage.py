"""What the session cost, measured from the host's own log, kept as numbers.

The one figure this product could never support is what it cost to run. Its
token metric measures how far the archive brief compresses the records - a
compression ratio routinely misread as a saving - and the
`counterfactual-claim` check exists at high severity precisely to stop anyone
writing the sentence that would paper over the gap.

The host already writes a full session transcript to disk and hands its path to
every hook. Nothing here read it. Comparable local-only projects measure
themselves exactly this way and transmit nothing, so the privacy boundary was
never what stopped this one; the input was simply left on the floor.

**Privacy contract.** A transcript holds prompts, source and file paths. The
declared limit `raw_prompts_stored: false` does not bend for a metric:

* the file is streamed, never loaded whole and never copied;
* only numeric usage fields are read - no message text, no tool arguments;
* the return value carries counts, two fixed labels, and nothing else;
* the transcript's own path is not returned, because a path names a project and
  frequently a person;
* measuring writes nothing anywhere. Recording is the caller's decision.

Those properties are asserted in `tests/test_usage.py` against a transcript
seeded with distinctive strings, so the contract is checked rather than
promised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Fields the host records per assistant message. Anything not named here is not
# read, so a future transcript gaining a `prompt_text` field cannot silently
# start flowing through this function.
_INPUT = "input_tokens"
_OUTPUT = "output_tokens"
_CACHE_READ = "cache_read_input_tokens"
_CACHE_WRITE = "cache_creation_input_tokens"


def _absent() -> dict[str, Any]:
    """Absent is not zero. Reporting one as the other is how a dashboard starts
    lying quietly, and this product reports `insufficient-data` instead."""
    return {
        "confidence": "insufficient-data",
        "source": "session-transcript",
        "input_tokens": None,
        "output_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "assistant_turns": None,
        "tool_calls": None,
        "unreadable_lines": None,
    }


def measure_session(transcript: Path | str) -> dict[str, Any]:
    """Sum the usage the host recorded for one session.

    `transcript` is the path the host passes to its hooks. A missing or
    unreadable file reports insufficient data rather than a zero.
    """
    path = Path(transcript)
    if not path.is_file():
        return _absent()

    totals = {_INPUT: 0, _OUTPUT: 0, _CACHE_READ: 0, _CACHE_WRITE: 0}
    turns = 0
    tool_calls = 0
    unreadable = 0

    try:
        # Streamed a line at a time: a real session transcript runs to tens of
        # megabytes, and holding one in memory is both wasteful and a larger
        # window in which content could be mishandled.
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    unreadable += 1
                    continue
                message = record.get("message")
                if not isinstance(message, dict):
                    continue
                usage = message.get("usage")
                if isinstance(usage, dict):
                    turns += 1
                    for field in totals:
                        value = usage.get(field)
                        if isinstance(value, int):
                            totals[field] += value
                content = message.get("content")
                if isinstance(content, list):
                    # Counted by type only; the block's arguments are never read.
                    tool_calls += sum(
                        1 for block in content
                        if isinstance(block, dict) and block.get("type") == "tool_use")
    except OSError:
        return _absent()

    if not turns:
        return _absent()

    return {
        "confidence": "measured",
        "source": "session-transcript",
        "input_tokens": totals[_INPUT],
        "output_tokens": totals[_OUTPUT],
        "cache_read_tokens": totals[_CACHE_READ],
        "cache_write_tokens": totals[_CACHE_WRITE],
        "assistant_turns": turns,
        "tool_calls": tool_calls,
        "unreadable_lines": unreadable,
    }


def _self_check() -> None:
    import tempfile

    secret = "DO-NOT-LEAK-THIS-PROMPT"
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "session.jsonl"
        path.write_text("\n".join([
            json.dumps({"type": "user", "message": {"content": secret}}),
            json.dumps({"type": "assistant", "message": {
                "content": [{"type": "tool_use", "name": "Edit",
                             "input": {"file_path": secret}}],
                "usage": {_INPUT: 10, _OUTPUT: 4, _CACHE_READ: 1, _CACHE_WRITE: 2}}}),
            "{ not json",
        ]) + "\n", encoding="utf-8")

        result = measure_session(path)
        assert result["input_tokens"] == 10, result
        assert result["output_tokens"] == 4, result
        assert result["tool_calls"] == 1, result
        assert result["unreadable_lines"] == 1, result
        assert secret not in json.dumps(result), "transcript content escaped"
        assert str(path) not in json.dumps(result), "transcript path escaped"

        missing = measure_session(Path(raw) / "absent.jsonl")
        assert missing["confidence"] == "insufficient-data", missing
        assert missing["input_tokens"] is None, missing

    print("godmode_usage self-check OK")

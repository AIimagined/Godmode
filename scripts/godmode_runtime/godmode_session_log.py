"""Counts-only measurement, read from the host's own transcript.

Godmode measures its own value and the session's shape from the transcript the
host already writes locally, storing COUNTS ONLY, never content. `measure`
streams a session's JSONL transcript and tallies tool calls, commands, test
runs, and token usage; `record_measurement` writes those tallies as a
`metric` record, or - when the transcript is missing or unreadable - a stated
gap. Either way the checkpoint the caller is trying to record must not be
lost, so the hook wraps this whole thing in `try`/`except` (see
`hooks/godmode_session_hook.py`, session-end branch).

**The transcript shape, pinned from a real file, not guessed.** Read
read-only on 2026-08-15 from a local Claude Code session transcript
(`~/.claude/projects/<project>/<session>.jsonl` on this machine - the
specific session identifier is not recorded here; it carries no
verification value a reader could check and is not this module's to keep).
Transcript content is untrusted and none of it is reproduced below or
anywhere in this module or its fixtures - only the field NAMES observed:

* One JSON object per line. Top level: `{"type": "assistant"|"user"|
  "attachment"|"queue-operation"|"ai-title"|"last-prompt", "message": {...},
  "sessionId": ..., "uuid": ..., "timestamp": ..., ...}`.
* An assistant turn's `message`: `{"role": "assistant", "content": [...],
  "usage": {...}, "model": ..., ...}`.
* `message.content` is a list of blocks. Observed block `type` values:
  `"thinking"`, `"tool_use"`, `"text"`; a user-role message carries
  `"tool_result"` blocks instead.
* A `tool_use` block: `{"type": "tool_use", "id": ..., "name": ...,
  "input": {...}, "caller": {...}}`. A `Bash` tool_use's `input` carries
  `{"command": ..., "description": ...}`.
* `message.usage`: `{"input_tokens": int, "cache_creation_input_tokens": int,
  "cache_read_input_tokens": int, "output_tokens": int, "server_tool_use":
  {...}, "cache_creation": {...}, "service_tier": ..., "inference_geo": ...,
  "iterations": [...], "speed": ...}`.

Only `message.role`, `message.usage.{input,output,cache_*}_tokens`,
`content[].type`, and a `tool_use` block's `name`/`input.command` are ever
read. Every other field, and every string value anywhere in the transcript,
is looked at only long enough to classify it (a shell command matched
against a fixed test-runner pattern, a tool name matched against a fixed
enum) and then discarded - never copied into a stored record.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Tool names this module will name individually. Anything else tallies under
# `_OTHER_TOOL` instead. Two reasons this enum is closed rather than "whatever
# `tool_use.name` says": an MCP server can register a tool under any name it
# likes, and a name is exactly where a would-be content leak would try to
# ride along; and the acceptance contract requires every stored string to be
# drawn from a closed enum, not merely short.
_KNOWN_TOOLS = frozenset({
    "Bash", "PowerShell", "Read", "Write", "Edit", "NotebookEdit",
    "Grep", "Glob", "WebFetch", "WebSearch", "TodoWrite", "Task",
    "ExitPlanMode", "SlashCommand", "KillShell", "BashOutput",
    "AskUserQuestion", "StructuredOutput", "Artifact",
})
_OTHER_TOOL = "other"

# The tools whose `input.command` is a shell command worth classifying as a
# test run. Their content is read only to match this pattern - never stored.
_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

_TEST_RUN_PATTERN = re.compile(
    r"\b(pytest|unittest|npm\s+(run\s+)?test|yarn\s+test|go\s+test|"
    r"cargo\s+test|jest|mocha|rspec|phpunit|dotnet\s+test|mvn\s+test|"
    r"ctest|gradle\s+test)\b",
    re.IGNORECASE,
)

# Reasons `record_measurement` can state for not measuring. Closed and short,
# same discipline as the tool-name enum above: the caller passes whatever
# `transcript_path` the host handed it, and this module never turns an
# arbitrary path or OS error message into a stored string.
REASON_NO_PATH = "no-transcript-path-supplied"
REASON_NOT_FOUND = "transcript-file-not-found"
REASON_UNREADABLE = "transcript-file-unreadable"

_SUBJECT = "session measurement"


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _tool_name(raw: Any) -> str:
    name = str(raw) if raw is not None else ""
    return name if name in _KNOWN_TOOLS else _OTHER_TOOL


def measure(transcript_path: Path) -> dict[str, Any]:
    """Tally one session's transcript. Counts only - see the module docstring.

    Streams the file line by line (`for line in handle`) rather than reading
    it whole: a transcript can run to megabytes, and this must not load the
    entire thing into memory to count a handful of integers. Raises
    `OSError` (subclasses include `FileNotFoundError`, `IsADirectoryError`,
    `PermissionError`) or `ValueError` (an unusable path, e.g. an embedded
    null byte) when the path cannot be opened at all; the caller decides what
    a missing transcript means. A line that fails to parse as JSON is
    skipped, not fatal - the host may still be writing the tail line when
    session-end fires.
    """
    turns = 0
    tool_calls: dict[str, int] = {}
    commands = 0
    test_runs = 0
    tokens_in = 0
    tokens_out = 0

    with Path(transcript_path).open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue

            if message.get("role") == "assistant":
                turns += 1
                usage = message.get("usage")
                if isinstance(usage, dict):
                    tokens_in += (
                        _int(usage.get("input_tokens"))
                        + _int(usage.get("cache_creation_input_tokens"))
                        + _int(usage.get("cache_read_input_tokens"))
                    )
                    tokens_out += _int(usage.get("output_tokens"))

            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = _tool_name(block.get("name"))
                tool_calls[name] = tool_calls.get(name, 0) + 1
                if name in _SHELL_TOOLS:
                    commands += 1
                    block_input = block.get("input")
                    command_text = ""
                    if isinstance(block_input, dict):
                        command_text = str(block_input.get("command", ""))
                    if _TEST_RUN_PATTERN.search(command_text):
                        test_runs += 1

    return {
        "turns": turns,
        "tool_calls": tool_calls,
        "commands": commands,
        "test_runs": test_runs,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "content_free": True,
    }


def _gap(archive: Any, session: str | None, reason: str) -> dict[str, Any]:
    return archive.append(
        "metric", _SUBJECT,
        {
            "measured": False,
            "reason": reason,
            "session": str(session)[:80] if session else None,
            "content_free": True,
        },
        evidence=[],
    )


def record_measurement(
    archive: Any, transcript_path: Any, *, session: str | None = None
) -> dict[str, Any]:
    """Write one `metric` record for the transcript at `transcript_path`.

    A missing or unreadable transcript is not an error here - it is a stated
    gap, recorded and returned like any other measurement, so a caller never
    has to guard this call beyond the try/except it already needs for its own
    reasons (the archive can refuse to write, same as any other record).
    """
    path_text = str(transcript_path).strip() if transcript_path else ""
    if not path_text:
        return _gap(archive, session, REASON_NO_PATH)
    try:
        counts = measure(Path(path_text))
    except FileNotFoundError:
        return _gap(archive, session, REASON_NOT_FOUND)
    except (OSError, ValueError):
        # ValueError covers a path Python cannot even open (an embedded
        # null byte, for instance) - not a Python-level bug, just another
        # shape of "this transcript cannot be read".
        return _gap(archive, session, REASON_UNREADABLE)

    data = dict(counts)
    data["measured"] = True
    data["session"] = str(session)[:80] if session else None
    return archive.append("metric", _SUBJECT, data, evidence=[])

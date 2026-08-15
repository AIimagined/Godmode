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

**The red/green choice, recorded (U-T2).** `command_timeline` additionally
reads a `tool_result` block's `is_error` and `tool_use_id` fields, to pair a
shell command with its outcome. The same real, read-only 2026-08-15 read
that pinned the shape above was checked specifically for a structured exit
code on these blocks: there is none. A `tool_result` block is
`{"type": "tool_result", "tool_use_id": ..., "content": <str>, "is_error":
<bool, sometimes absent>}` - `content` is always a plain string (never a
structured payload carrying a numeric code), and `is_error` is the one
boolean signal, present on some blocks and absent from others (absent reads
as not-an-error, same as the host's own rendering). So red/green here is
derived from `is_error`, not parsed from a POSIX exit status: a synthesised
`exit_code` of `1` when `is_error` is `true`, `0` otherwise. `content` is
never read for this purpose - a real exit code embedded in prose output
would require reading command output, which this module does not do.
"""

from __future__ import annotations

import hashlib
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


# Tools that change project files, for the red-before-green mutation anchor
# (U-T2): a fix-vocabulary claim is checked against a test run seen failing
# before the last of these and passing after. `NotebookEdit` is included
# alongside `Edit`/`Write` for the same reason it is tracked separately in
# `_KNOWN_TOOLS` above - it mutates project content just as they do.
_MUTATING_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def command_digest(command_text: str) -> str:
    """A stable digest of a shell command's text - never the text itself.

    Both sides of a temporal check must derive the same digest from the same
    normalisation, or a real match reads as a miss: this is called here
    while scanning the transcript, and again in `godmode_attest` on a
    claim's `cmd:` citation. Normalisation is deliberately minimal - strip
    only - because a citation is expected to quote the command verbatim.
    """
    normalized = str(command_text).strip()
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _scan_timeline(transcript_path: Path) -> tuple[dict[str, list[tuple[int, int]]], list[int]]:
    """One streaming pass producing both the command timeline and mutation turns.

    Shares `measure`'s turn-counting rule (increment on each assistant-role
    message) so a `(turn, exit_code)` pair here lines up with a mutation
    turn recorded from the same scan. A shell `tool_use` is paired with its
    outcome by `tool_use_id` -> the matching `tool_result` block's
    `is_error`; a command whose result never arrives (a torn tail, a
    still-running call) is simply absent from the timeline rather than
    guessed at.
    """
    commands: dict[str, list[tuple[int, int]]] = {}
    mutations: list[int] = []
    pending: dict[str, tuple[str, int]] = {}
    turn = 0

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
            content = message.get("content")
            if not isinstance(content, list):
                continue
            role = message.get("role")

            if role == "assistant":
                turn += 1
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = str(block.get("name") or "")
                    if name in _MUTATING_TOOLS:
                        mutations.append(turn)
                    if name in _SHELL_TOOLS:
                        block_input = block.get("input")
                        command_text = ""
                        if isinstance(block_input, dict):
                            command_text = str(block_input.get("command", ""))
                        tool_id = block.get("id")
                        if tool_id is not None and command_text.strip():
                            pending[str(tool_id)] = (command_digest(command_text), turn)
            elif role == "user":
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool_id = block.get("tool_use_id")
                    match = pending.pop(str(tool_id), None) if tool_id is not None else None
                    if match is None:
                        continue
                    digest, observed_turn = match
                    exit_code = 1 if block.get("is_error") is True else 0
                    commands.setdefault(digest, []).append((observed_turn, exit_code))

    return commands, mutations


def command_timeline(transcript_path: Path) -> dict[str, list[tuple[int, int]]]:
    """Per-command outcome timeline: `{cmd_digest: [(turn, exit_code)]}`.

    Digests only, never the command text - see `command_digest`. `exit_code`
    is a synthesised binary outcome derived from `is_error` (see the module
    docstring's U-T2 note), not a parsed POSIX exit status: treat any
    nonzero value as "failed", not as a specific code. Raises the same
    `OSError`/`ValueError` as `measure` for a path that cannot be opened -
    the caller decides what a missing transcript means.
    """
    commands, _mutations = _scan_timeline(Path(transcript_path))
    return commands


def mutation_turns(transcript_path: Path) -> list[int]:
    """Turns (1-based assistant-message index) carrying an Edit/Write/NotebookEdit."""
    _commands, mutations = _scan_timeline(Path(transcript_path))
    return mutations


def session_timeline(transcript_path: Path) -> dict[str, Any]:
    """The combined shape `record_claim`/`record_criterion` consume as `timeline`.

    `{"commands": {cmd_digest: [(turn, exit_code)]}, "mutation_turns": [...]}`,
    built from one scan rather than two separate calls to `command_timeline`
    and `mutation_turns`. A caller (hook or CLI) that has a transcript path
    computes this once and passes it through; a caller with no transcript
    passes `None`, which both consumers treat as a stated gap, never a
    penalty.
    """
    commands, mutations = _scan_timeline(Path(transcript_path))
    return {"commands": commands, "mutation_turns": mutations}


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

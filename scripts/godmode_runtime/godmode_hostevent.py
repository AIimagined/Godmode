"""CX-2: the canonical host-event adapter.

Every host that can call this plugin's pre-tool boundary speaks its own
dialect: field names in two casings, tool names that mean the same thing
under three different spellings, event names in four different
capitalisation schemes, and a response contract with different keys for
"deny". `classify_action`, the capability broker, the fences, and the
archive should not have to know any of that - they consume ONE shape,
`HostEvent`, and this module is the only place host dialects are read or
written.

**What is BINDING here, and where it comes from** (see
`docs/superpowers/plans/2026-08-16-codex-compat.md`'s "Plan amendments"
1-4 and `docs/superpowers/specs/2026-08-16-codex-compat-design.md`'s CX-2
unit + Addenda 2/6 - every literal spelling below is copied from one of
those, never guessed):

- Dual-casing field normalization: `hookEventName`/`hook_event_name`,
  `toolName`/`tool_name`, `toolInput`/`tool_input`, `sessionId`/
  `session_id`, `workspaceRoot`/`cwd` - both casings, always (`field()`).
- Host detection chain: `GODMODE_HOST` || `GROK_AGENT` ||
  `CLAUDE_CODE_ENTRYPOINT` || payload-shape || `"unknown"`. No env var here
  ever decides an INTERCEPTION claim - that stays `godmode_hookproof.py`'s
  chronicled-proof job exclusively; this chain only picks which dialect to
  speak for one payload.
- Claude tool map: unchanged from the pre-CX-2 hook, byte-for-byte
  (`Bash`/`PowerShell` -> command text, `Write`/`Edit`/`NotebookEdit` ->
  `file_path`, `Read`/`Glob`/`Grep` -> read operation).
- Codex tool map: `shell_command` -> `tool_input.command` (PowerShell/cmd/
  POSIX text, read the same way Claude's `Bash` is); `apply_patch` -> every
  `*** Add File:`/`*** Update File:`/`*** Delete File:`/`*** Move to:`
  target in the patch body, each carrying its own add/update/delete/rename
  INTENT (Plan amendment 3); `functions.exec` is Codex's orchestration
  wrapper - unwrapped to the nested tool call it names, or failed closed
  when the nested shape does not match any documented pattern (Plan
  amendment 2, CX-2 additions).
- Grok tool map (Addendum 6, verbatim): `run_terminal_command` ->
  `toolInput.command`, `write` -> `toolInput.file_path`, `search_replace`
  -> `toolInput.file_path`.
- Unknown tool name NEVER degrades silently: `HostEvent(tool="<raw-name>")`
  with `tool_kind="unrecognized"`, and the caller (the hook) classifies it
  fail-closed as `protected=True, category="unrecognized-tool"`,
  chronicled with counts only (`record_unrecognized_tool`).
- Gate-exactly-once (Plan amendment 2): `parse_host_payload(raw, seen=...)`
  takes an OPTIONAL, caller-owned `seen` set of request ids. This is
  documented honestly as an IN-PROCESS guard only - each real host tool
  call spawns a fresh hook subprocess with its own empty set, so this
  catches a payload that would otherwise reach the gate twice WITHIN one
  parse (an orchestration wrapper whose unwrap logic double-dispatches),
  never a host that resends the same request id across two separate
  process invocations. That cross-invocation boundary is not this
  module's to close; it is named here so nobody mistakes the guard for
  more than it is.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from typing import Any

SCHEMA = 1

# ---------------------------------------------------------------------------
# Dual-casing field lookup. One table, one function - every adapter below
# reads a payload field through this, never through a bare `raw.get(...)`,
# so a host that ships camelCase or snake_case is never a special case.
# ---------------------------------------------------------------------------

_ALIASES: dict[str, tuple[str, ...]] = {
    "hook_event_name": ("hookEventName", "hook_event_name"),
    "tool_name": ("toolName", "tool_name"),
    "tool_input": ("toolInput", "tool_input"),
    "session_id": ("sessionId", "session_id"),
    "cwd": ("workspaceRoot", "workspace_root", "cwd"),
    "request_id": ("requestId", "request_id", "toolUseId", "tool_use_id"),
    "actor": ("agentId", "agent_id", "subagentType", "subagent_type"),
}


def field(raw: Any, name: str) -> Any:
    """`raw[<any known casing of name>]`, or `None`. Never raises on a
    non-dict `raw` - a malformed payload reads as "field absent", the same
    fail-closed-by-absence shape every adapter below already relies on.
    """
    if not isinstance(raw, dict):
        return None
    for key in _ALIASES.get(name, (name,)):
        if key in raw:
            return raw[key]
    return None


# ---------------------------------------------------------------------------
# HostEvent - the ONE shape every downstream consumer reads.
# ---------------------------------------------------------------------------

# `tool_kind` values. Not an exhaustive taxonomy of every tool a host might
# ever send - just enough for the hook to route without re-deriving it:
# a read costs nothing, a fenced mutation walks `targets` through the scope
# fence, a shell command is classified as text, `unrecognized` fails closed,
# `duplicate` marks a gate-exactly-once hit, and `other` is "known tool,
# none of the above" (e.g. Claude's TodoWrite).
TOOL_KIND_READ = "read"
TOOL_KIND_FENCED = "fenced"
TOOL_KIND_SHELL = "shell"
TOOL_KIND_UNRECOGNIZED = "unrecognized"
TOOL_KIND_DUPLICATE = "duplicate"
TOOL_KIND_OTHER = "other"


@dataclass
class HostEvent:
    schema: int
    event: str
    host: str
    tool: str
    operation: str
    targets: list[str]
    cwd: str
    request_id: str
    tool_kind: str | None = None
    approval_context: dict[str, Any] | None = None
    actor: str | None = None


# ---------------------------------------------------------------------------
# Host detection.
# ---------------------------------------------------------------------------

# Claude's own tool vocabulary - the exact set the pre-CX-2 hook recognised,
# copied here (not re-derived) so detection-by-shape can never disagree with
# the adapter that actually classifies these names.
_CLAUDE_TOOLS = frozenset({
    "Bash", "PowerShell", "Write", "Edit", "NotebookEdit",
    "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
})
_CODEX_TOOLS = frozenset({"shell_command", "apply_patch", "functions.exec"})
# Grok tool map, Addendum 6 verbatim: run_terminal_command/write/search_replace.
_GROK_TOOLS = frozenset({"run_terminal_command", "write", "search_replace"})
# Addendum 5: Cursor's pre-tool events, camelCase, a fourth dialect.
_CURSOR_EVENTS = frozenset({"preToolUse", "beforeShellExecution"})
# Addendum 4a: Gemini CLI's pre-tool event is BeforeTool, not PreToolUse.
_GEMINI_EVENTS = frozenset({"BeforeTool"})


def detect_host(raw: Any) -> str:
    """`GODMODE_HOST || GROK_AGENT || CLAUDE_CODE_ENTRYPOINT || payload-shape
    || "unknown"` (Addendum 6's binding chain). Env vars decide the DIALECT
    to speak, never the interception claim - `godmode_hookproof.py` owns
    that exclusively, from chronicled proof records only.
    """
    if os.environ.get("GODMODE_HOST"):
        return os.environ["GODMODE_HOST"]
    if os.environ.get("GROK_AGENT"):
        return "grok"
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    return _detect_from_shape(raw) or "unknown"


def _detect_from_shape(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    event_name = field(raw, "hook_event_name")
    tool = field(raw, "tool_name")
    if event_name in _CURSOR_EVENTS or "beforeShellExecution" in raw:
        return "cursor"
    if event_name in _GEMINI_EVENTS:
        return "gemini"
    if isinstance(tool, str) and tool:
        if tool in _CODEX_TOOLS:
            return "codex"
        if tool in _GROK_TOOLS:
            return "grok"
        if tool in _CLAUDE_TOOLS:
            return "claude"
    return None


# Every pre-tool event name spelling across the four documented dialects:
# Claude/Codex PascalCase, Grok's snake_case stdin value, Cursor's
# camelCase, Gemini's BeforeTool. `is_pretool_event` widens the hook's old
# `hook_event_name == "PreToolUse"` literal check to all of them without
# changing what it matches for Claude.
_PRETOOL_EVENT_NAMES = frozenset({
    "PreToolUse", "pre_tool_use", "preToolUse", "BeforeTool",
})


def is_pretool_event(raw: Any) -> bool:
    name = field(raw, "hook_event_name")
    return isinstance(name, str) and name in _PRETOOL_EVENT_NAMES


# ---------------------------------------------------------------------------
# Unrecognized tool: the fail-closed replacement for the deleted
# generic-invocation degradation path (`godmode_guardrails.tool_operation`
# used to return `f"{tool} tool invocation"` for anything it didn't know;
# that string carried no target/command information forward and classified
# through `classify_action`'s own catch-all - correct by accident, and
# undiagnosable when it happened). An unrecognized tool now stays visible:
# its own category, its own chronicle record, never a guess at what it
# might have meant.
# ---------------------------------------------------------------------------


def unrecognized_tool_preview(tool: str) -> dict[str, Any]:
    """The `classify_action`-shaped preview for a tool no adapter maps.

    R3/ask - the same fail-closed tier `unclassified-mutation` already uses
    for command text the classifier cannot parse. A tool this repo has no
    map for is exactly as unknown as a command it cannot read, and gets the
    same honest answer: recoverable by staging or by the operator's own
    approval, never a silent guess and never an outright unrecoverable
    refusal for something that might turn out to be harmless.
    """
    name = tool or "(unnamed)"
    return {
        "protected": True,
        "category": "unrecognized-tool",
        "operation_digest": hashlib.sha256(name.encode("utf-8")).hexdigest(),
        "impact": [f"tool {name!r} is not in any host adapter's known map"],
        "tier": "R3",
        "second_confirmation_required": False,
        "external_repo_ref": None,
    }


def record_unrecognized_tool(archive: Any, host: str, tool: str) -> None:
    """Counts-only miss record: which host and tool name reached the gate
    with no adapter mapping - never the command/target text that came with
    it. Best-effort: a chronicle failure must never change the fail-closed
    answer, which is already decided before this is ever called.
    """
    try:
        archive.append(
            "refusal", "unrecognized-tool",
            {"host": host[:60], "tool": (tool or "")[:120],
             "category": "unrecognized-tool", "tier": "R3"},
            evidence=[],
        )
    except Exception:  # noqa: BLE001
        pass


def _unrecognized(host: str, tool: str, raw: Any) -> HostEvent:
    return HostEvent(
        schema=SCHEMA,
        event=str(field(raw, "hook_event_name") or ""),
        host=host,
        tool=tool or "",
        operation="",
        targets=[],
        cwd=str(field(raw, "cwd") or ""),
        request_id=str(field(raw, "request_id") or ""),
        tool_kind=TOOL_KIND_UNRECOGNIZED,
    )


# ---------------------------------------------------------------------------
# Claude adapter - byte-identical to the pre-CX-2 hook. Tool map is imported
# from `godmode_guardrails.tool_operation` rather than re-copied, so the two
# can never quietly drift apart; that function itself lost its old generic
# fallback (it now returns `None` for a name it does not know, which routes
# here to `_unrecognized` instead of a flattened "<tool> tool invocation"
# string).
# ---------------------------------------------------------------------------

_CLAUDE_READ_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"})
_CLAUDE_FENCED_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})
_CLAUDE_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})


def _adapt_claude(raw: Any) -> HostEvent:
    from .godmode_guardrails import tool_operation

    tool = str(field(raw, "tool_name") or "").strip()
    tool_input = field(raw, "tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool not in _CLAUDE_TOOLS:
        return _unrecognized("claude", tool, raw)
    operation = tool_operation(tool, tool_input) or ""
    target = str(tool_input.get("file_path", "")).strip()
    targets = [target] if tool in _CLAUDE_FENCED_TOOLS and target else []
    if tool in _CLAUDE_READ_TOOLS:
        kind = TOOL_KIND_READ
    elif tool in _CLAUDE_FENCED_TOOLS:
        kind = TOOL_KIND_FENCED
    elif tool in _CLAUDE_SHELL_TOOLS:
        kind = TOOL_KIND_SHELL
    else:
        kind = TOOL_KIND_OTHER
    return HostEvent(
        schema=SCHEMA,
        event=str(field(raw, "hook_event_name") or ""),
        host="claude",
        tool=tool,
        operation=operation,
        targets=targets,
        cwd=str(field(raw, "cwd") or ""),
        request_id=str(field(raw, "request_id") or ""),
        tool_kind=kind,
    )


# ---------------------------------------------------------------------------
# Codex adapter.
# ---------------------------------------------------------------------------

# The documented OpenAI/Codex `apply_patch` V4A patch format: a single text
# block naming every touched file under one of four directives. This is the
# public patch grammar the tool itself defines (not a guess at Codex's
# hook-payload wrapper, which stays undocumented and is read generically
# below) - `*** Update File:` immediately followed by `*** Move to:` is a
# rename-with-content-change; every other directive stands alone.
_APPLY_PATCH_ADD = re.compile(r"^\*\*\* Add File: (.+)$")
_APPLY_PATCH_DELETE = re.compile(r"^\*\*\* Delete File: (.+)$")
_APPLY_PATCH_UPDATE = re.compile(r"^\*\*\* Update File: (.+)$")
_APPLY_PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$")

# Field names tried, in order, for the patch body and the shell command
# text. Codex's exact hook-payload field names are not published (spec's
# own CONFIRMED/ACCEPTED findings say so); "command"/"input" match the
# convention every documented dialect (Claude's Bash, the apply_patch tool
# schema's own "input" parameter) already uses, tried first and alone
# unless absent - never a value silently invented when both are missing.
_SHELL_COMMAND_FIELDS = ("command",)
_PATCH_BODY_FIELDS = ("input", "patch", "content")


def _first_field(payload: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def apply_patch_targets(patch_text: str) -> list[tuple[str, str]]:
    """`[(path, intent)]`, intent in `add`/`update`/`delete`/`rename` - Plan
    amendment 3's "detects add/update/delete/rename/move INTENT per target,
    not just paths". A `*** Move to:` line immediately following an
    `*** Update File:` is a rename: both the old and the new path are
    returned (as `update` and `rename` respectively) so the scope fence
    sees both ends of the move.
    """
    targets: list[tuple[str, str]] = []
    pending_update = False
    for line in patch_text.splitlines():
        match = _APPLY_PATCH_ADD.match(line)
        if match:
            targets.append((match.group(1).strip(), "add"))
            pending_update = False
            continue
        match = _APPLY_PATCH_DELETE.match(line)
        if match:
            targets.append((match.group(1).strip(), "delete"))
            pending_update = False
            continue
        match = _APPLY_PATCH_UPDATE.match(line)
        if match:
            targets.append((match.group(1).strip(), "update"))
            pending_update = True
            continue
        match = _APPLY_PATCH_MOVE.match(line)
        if match and pending_update:
            targets.append((match.group(1).strip(), "rename"))
            pending_update = False
            continue
    return targets


def _target_operation_text(path: str, intent: str) -> str:
    """One `classify_action`-readable segment per target, reusing its
    EXISTING vocabulary (`write file <path>` already routes through
    `_TOOL_FILE_EDIT` - pinned-evaluator/sensitive-path/containment checks;
    `rm <path>` already routes through the general filesystem-mutation
    pattern) rather than inventing a new category for apply_patch. A
    `rename` target is the destination path, treated as a write - the
    source path (recorded separately as its own `update` target) is what
    carries the `rm`-shaped removal-of-the-old-name risk.
    """
    if intent == "delete":
        return f"rm {path}"
    return f"write file {path}"


def _adapt_codex(raw: Any, tool: str | None = None, tool_input: Any = None,
                 *, _orchestrated: bool = False) -> HostEvent:
    if tool is None:
        tool = str(field(raw, "tool_name") or "").strip()
    if tool_input is None:
        tool_input = field(raw, "tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool == "functions.exec" and not _orchestrated:
        unwrapped = _codex_unwrap(tool_input)
        if unwrapped is None:
            return _unrecognized("codex", tool, raw)
        inner_tool, inner_input = unwrapped
        return _adapt_codex(raw, inner_tool, inner_input, _orchestrated=True)

    event_name = str(field(raw, "hook_event_name") or "")
    cwd = str(field(raw, "cwd") or "")
    request_id = str(field(raw, "request_id") or "")

    if tool == "shell_command":
        command = _first_field(tool_input, _SHELL_COMMAND_FIELDS) or ""
        return HostEvent(
            schema=SCHEMA, event=event_name, host="codex", tool=tool,
            operation=command.strip(), targets=[], cwd=cwd,
            request_id=request_id, tool_kind=TOOL_KIND_SHELL,
        )

    if tool == "apply_patch":
        patch_text = _first_field(tool_input, _PATCH_BODY_FIELDS) or ""
        touched = apply_patch_targets(patch_text)
        if not touched:
            return _unrecognized("codex", tool, raw)
        operation = "; ".join(
            _target_operation_text(path, intent) for path, intent in touched
        )
        targets = [path for path, _intent in touched]
        return HostEvent(
            schema=SCHEMA, event=event_name, host="codex", tool=tool,
            operation=operation, targets=targets, cwd=cwd,
            request_id=request_id, tool_kind=TOOL_KIND_FENCED,
        )

    return _unrecognized("codex", tool, raw)


def _codex_unwrap(wrapper: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Best-effort unwrap of Codex's orchestration wrapper
    (`functions.exec`) into `(inner_tool_name, inner_tool_input)`. Tries
    every documented nested-call shape in order; `None` when none match -
    the caller fails closed (`unrecognized-tool`) rather than guessing at
    an undocumented wrapper shape (Plan amendment 2: "unwrap to nested
    operations or fail closed").
    """
    name = wrapper.get("name")
    arguments = wrapper.get("arguments")
    if isinstance(name, str) and isinstance(arguments, dict):
        return name, arguments
    inner_tool = wrapper.get("tool")
    inner_input = wrapper.get("input")
    if isinstance(inner_tool, str) and isinstance(inner_input, dict):
        return inner_tool, inner_input
    function = wrapper.get("function")
    if isinstance(function, dict):
        fname = function.get("name")
        fargs = function.get("arguments")
        if isinstance(fname, str) and isinstance(fargs, dict):
            return fname, fargs
    return None


# ---------------------------------------------------------------------------
# Grok adapter. Field spellings and tool map are Addendum 6, verbatim.
# ---------------------------------------------------------------------------


def _adapt_grok(raw: Any) -> HostEvent:
    tool = str(field(raw, "tool_name") or "").strip()
    tool_input = field(raw, "tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    event_name = str(field(raw, "hook_event_name") or "")
    cwd = str(field(raw, "cwd") or "")
    request_id = str(field(raw, "request_id") or "")

    if tool == "run_terminal_command":
        command = str(tool_input.get("command", "")).strip()
        return HostEvent(
            schema=SCHEMA, event=event_name, host="grok", tool=tool,
            operation=command, targets=[], cwd=cwd, request_id=request_id,
            tool_kind=TOOL_KIND_SHELL,
        )
    if tool in ("write", "search_replace"):
        target = str(tool_input.get("file_path", "")).strip()
        if not target:
            return _unrecognized("grok", tool, raw)
        verb = "write" if tool == "write" else "edit"
        return HostEvent(
            schema=SCHEMA, event=event_name, host="grok", tool=tool,
            operation=f"{verb} file {target}", targets=[target], cwd=cwd,
            request_id=request_id, tool_kind=TOOL_KIND_FENCED,
        )
    return _unrecognized("grok", tool, raw)


# ---------------------------------------------------------------------------
# Gemini CLI / Cursor adapters. Addenda 4a/5 document event names and I/O
# discipline but not a verbatim tool-name vocabulary distinct from Claude's;
# both hosts describe themselves as running "the same kind of PreToolUse
# payload" in shape (Cursor: matchers "by tool type... stdin carries...
# hook_event_name"; Gemini: "stdin JSON payload"). Rather than invent tool
# names neither addendum states, both adapters try the CLAUDE-shaped
# tool/tool_input pair through the same dual-casing lookup and fail closed
# to `unrecognized-tool` (never a silent read-vs-mutation guess, per the
# plan's RULING) when the payload does not carry one.
# ---------------------------------------------------------------------------


def _adapt_generic(raw: Any, host: str) -> HostEvent:
    from .godmode_guardrails import tool_operation

    tool = str(field(raw, "tool_name") or "").strip()
    tool_input = field(raw, "tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if not tool:
        return _unrecognized(host, tool, raw)
    operation = tool_operation(tool, tool_input)
    if operation is None:
        return _unrecognized(host, tool, raw)
    target = str(tool_input.get("file_path", "")).strip()
    targets = [target] if tool in _CLAUDE_FENCED_TOOLS and target else []
    if tool in _CLAUDE_READ_TOOLS:
        kind = TOOL_KIND_READ
    elif tool in _CLAUDE_FENCED_TOOLS:
        kind = TOOL_KIND_FENCED
    elif tool in _CLAUDE_SHELL_TOOLS:
        kind = TOOL_KIND_SHELL
    else:
        kind = TOOL_KIND_OTHER
    return HostEvent(
        schema=SCHEMA,
        event=str(field(raw, "hook_event_name") or ""),
        host=host, tool=tool, operation=operation, targets=targets,
        cwd=str(field(raw, "cwd") or ""),
        request_id=str(field(raw, "request_id") or ""),
        tool_kind=kind,
    )


# ---------------------------------------------------------------------------
# The bare, host-neutral shape: `{"operation": "..."}`, no `tool_name` at
# all. This is CX-1's probe path (`godmode-probe:<nonce>`), the CLI/test
# harness convention that predates every host adapter, and stays supported
# unchanged - a caller with no tool payload to translate is not a host this
# module has anything to adapt.
# ---------------------------------------------------------------------------


def _adapt_bare(raw: Any, host: str) -> HostEvent:
    return HostEvent(
        schema=SCHEMA,
        event=str(field(raw, "hook_event_name") or ""),
        host=host, tool="",
        operation=str(raw.get("operation", "")).strip() if isinstance(raw, dict) else "",
        targets=[], cwd=str(field(raw, "cwd") or ""),
        request_id=str(field(raw, "request_id") or ""),
        tool_kind=None,
    )


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

_ADAPTERS = {
    "claude": _adapt_claude,
    "codex": _adapt_codex,
    "grok": _adapt_grok,
}


def parse_host_payload(raw: Any, *, seen: set[str] | None = None) -> HostEvent:
    """Detect the host, translate its payload into one canonical `HostEvent`.

    `seen`, when passed, is a caller-owned set of request ids scoped to ONE
    hook process invocation (gate-exactly-once, in-process only - see the
    module docstring). A request id already in it comes back as a minimal
    `HostEvent` with `tool_kind="duplicate"`; the caller's job is to treat
    that as "already decided this run", never to re-run classification.
    """
    if not isinstance(raw, dict):
        raw = {}
    host = detect_host(raw)
    request_id = str(field(raw, "request_id") or "")
    if seen is not None and request_id and request_id in seen:
        return HostEvent(
            schema=SCHEMA, event=str(field(raw, "hook_event_name") or ""),
            host=host, tool=str(field(raw, "tool_name") or ""), operation="",
            targets=[], cwd=str(field(raw, "cwd") or ""),
            request_id=request_id, tool_kind=TOOL_KIND_DUPLICATE,
        )

    tool_name = field(raw, "tool_name")
    if not tool_name:
        event = _adapt_bare(raw, host)
    elif host in _ADAPTERS:
        event = _ADAPTERS[host](raw)
    elif host in ("gemini", "cursor"):
        event = _adapt_generic(raw, host)
    else:
        # A tool name is present but the host is unrecognised - still fail
        # closed rather than guessing which dialect to speak.
        event = _unrecognized("unknown", str(tool_name), raw)

    actor = field(raw, "actor")
    if actor is not None:
        event.actor = str(actor)
    if seen is not None and request_id:
        seen.add(request_id)
    return event


# ---------------------------------------------------------------------------
# Payload-capture probe (Plan amendments 2). Counts-only, structural facts
# ONLY - never a command, a path, a prompt, or any other value a tool
# actually carried. Gated by the caller (the hook checks
# GODMODE_CAPTURE_HOST_PAYLOADS / --capture-payload before calling this);
# this function itself has no on/off logic of its own, so a caller cannot
# forget to gate it and get silent unconditional capture instead.
# ---------------------------------------------------------------------------


def capture_payload_probe(archive: Any, raw: Any, event: HostEvent) -> None:
    """Record event name, tool name, sorted input FIELD NAMES, a hash of
    the request id, and a hash of cwd - never a value. Meant for an
    unrecognised host shape: capturing what shape it had, not what it said,
    so a future fixture can be built from the field names alone. Best
    effort: a capture failure must never affect the gate's own decision,
    which has already been made before this is ever called.
    """
    tool_input = field(raw, "tool_input") if isinstance(raw, dict) else None
    field_names = sorted(tool_input.keys()) if isinstance(tool_input, dict) else []

    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""

    try:
        archive.append(
            "action", "host-payload-capture",
            {
                "host": event.host[:40],
                "event": (event.event or "")[:80],
                "tool": (event.tool or "")[:80],
                "field_names": field_names[:40],
                "request_id_hash": _hash(event.request_id),
                "cwd_hash": _hash(event.cwd),
            },
            evidence=[],
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Response emission - ONE JSON object carrying every host's key for the same
# decision, so a host that ignores the keys it does not read is unaffected
# and detection does not have to be perfect to be safe (Plan amendments 1's
# "DUAL-OUTPUT" requirement, generalised to every documented dialect rather
# than only Grok+Claude). `base_decision` is host-neutral: "allow"/"ask"/
# "deny". Exit code is always 0 for a decided response - Claude's own
# tested contract (exit 0, JSON signals deny) already required this, Grok's
# own docs accept exit 0 with JSON as an alternative to exit 2, and EXIT 3
# NEVER APPEARS HERE AT ALL (the Grok probe proved it fail-opens on any
# host whose contract does not name it).
# ---------------------------------------------------------------------------

# Hosts whose own documented contract includes an `ask`/third decision.
# Everyone else has only allow/deny (Addendum 6: "Grok has no ask decision";
# Addenda 4a/2 document no ask for Gemini/Codex either) - `render_decision`
# folds `ask` down to `deny` for those, with a remedy that names the staged-
# capability escape hatch by its exact command.
HOSTS_WITH_ASK = frozenset({"claude", "cursor"})


def render_decision(host: str, event_name: str, base_decision: str,
                    reason: str) -> tuple[dict[str, Any], int]:
    """`(body, exit_code)` for one decision. `allow` is silent (`{}`, 0) -
    every documented dialect treats silence/exit-0-with-no-body as proceed,
    matching the pre-CX-2 Claude contract exactly.
    """
    if base_decision == "allow":
        return {}, 0
    effective = base_decision if (base_decision != "ask" or host in HOSTS_WITH_ASK) else "deny"
    grok_decision = "deny" if base_decision == "ask" else base_decision
    body = {
        "hookSpecificOutput": {
            "hookEventName": event_name or "PreToolUse",
            "permissionDecision": effective,
            "permissionDecisionReason": reason,
        },
        "decision": grok_decision,
        "reason": reason,
        "permission": base_decision,
        "user_message": reason,
        "agent_message": reason,
    }
    return body, 0

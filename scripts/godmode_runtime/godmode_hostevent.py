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
  **First-alias-wins is a deliberate security property, not incidental
  dict-ordering** (fix round 1, I3): when a payload carries BOTH casings
  of a field with conflicting values, the alias listed FIRST in
  `_ALIASES` (always the camelCase spelling) wins, consistently, at
  every call site that reads a payload field this way -
  `godmode_hostevent.field()` itself, the fast gate's independent local
  duplicate (`hooks/godmode_gate_fast.py`'s
  `payload.get("toolName", payload.get("tool_name"))`), and the hook's
  read-only shortcut (`hooks/godmode_session_hook.py`'s `host_field`
  call) all agree on the same winner for the same payload. The
  alternative - "last write wins" from an unordered merge, or each call
  site picking independently - would let a payload that names the SAME
  field under both casings mean two different things to two different
  checks reading it, which is exactly the kind of disagreement a gate is
  supposed to make impossible.
- Host detection chain: `GODMODE_HOST` || `GROK_AGENT` ||
  `CLAUDE_CODE_ENTRYPOINT` || payload-shape || `"unknown"`. The first
  three steps are Addendum 6's binding chain, verbatim
  (`GODMODE_HOST || GROK_AGENT || CLAUDE_CODE_ENTRYPOINT || unknown`);
  the payload-shape step is NOT addendum text - it is this module's own
  synthesis with the Plan's ORIGINAL (pre-amendment) CX-2 interface line
  ("`parse_host_payload(raw) -> HostEvent` - detects host by payload
  shape"), needed because a real hook subprocess frequently runs with
  none of the three env vars set at all (fix round 1, I2 - corrects a
  misattribution in the prior revision of this docstring that cited the
  whole chain, including the shape step, as addendum text). No env var
  here ever decides an INTERCEPTION claim - that stays
  `godmode_hookproof.py`'s chronicled-proof job exclusively; this chain
  only picks which dialect to speak for one payload.
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
  amendment 2, CX-2 additions). **STRICT whole-patch parsing** (fix
  round 1, C1): if ANY line in the patch body looks directive-like (the
  `***` marker plus an Add/Update/Delete File or Move to keyword, in any
  indentation or spacing variant) but does not match the exact grammar
  above, the ENTIRE `apply_patch` call fails closed - a patch mixing one
  well-formed target with one malformed one used to silently drop the
  malformed one instead of failing the whole call; partial recognition
  may never shrink the target set the fence sees.
- Grok tool map (Addendum 6, verbatim): `run_terminal_command` ->
  `toolInput.command`, `write` -> `toolInput.file_path`, `search_replace`
  -> `toolInput.file_path`.
- Unknown tool name NEVER degrades silently: `HostEvent(tool="<raw-name>")`
  with `tool_kind="unrecognized"`, and the caller (the hook) classifies it
  fail-closed as `protected=True, category="unrecognized-tool"`,
  chronicled with counts only (`record_unrecognized_tool`), exactly ONCE
  per miss (fix round 1, M1 - the classifier's own generic refusal-write
  used to fire a second time for the same miss; the hook now checks
  `preview["_chronicled_miss"]` before its own write). A `tool_name` field
  that is PRESENT but empty/whitespace-only is also unrecognized-tool
  (fix round 1, M2), distinct from a payload that carries no `tool_name`
  field at all (the bare `{"operation": ...}` shape below).
- Gate-exactly-once dedup was REMOVED in fix round 1 (C2/I1): the prior
  revision keyed a `seen` set on `request_id` alone, so a SECOND, DIFFERENT
  operation replaying an already-seen id was silently allowed with zero
  scrutiny - a live bypass guarding a double-dispatch path
  (`_adapt_codex`'s `functions.exec` unwrap recurses via a direct Python
  call, never through `parse_host_payload`) that does not exist anywhere
  in this tree. `request_id` stays on `HostEvent` (recorded, and hashed
  into the payload-capture probe's record) but nothing deduplicates on it
  today. If a future unit's live orchestration probe proves a real
  double-dispatch path exists, its dedup key must be
  `(request_id, operation-or-tool-fingerprint)` - never `request_id`
  alone - so a genuinely repeated parse dedupes while a differing one
  under a reused id still classifies fully.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from typing import Any
import unicodedata

SCHEMA = 1

# ---------------------------------------------------------------------------
# Dual-casing field lookup. One table, one function - every adapter below
# reads a payload field through this, never through a bare `raw.get(...)`,
# so a host that ships camelCase or snake_case is never a special case.
#
# Alias ORDER is load-bearing (fix round 1, I3): each tuple lists camelCase
# before snake_case, and `field()` returns the FIRST key present - so when a
# payload carries both casings with conflicting values, camelCase always
# wins, deterministically, everywhere this table (or a duplicate of it, like
# the fast gate's local lookup) is consulted. This is a security property,
# not an accident of dict-literal ordering: see `test_hostevent.py`'s
# `FirstAliasWinsTests` for the cross-call-site pin.
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


def field_present(raw: Any, name: str) -> bool:
    """Whether `raw` carries ANY known casing of `name`'s key, regardless of
    its value - distinct from `field()` returning a falsy value. Fix round
    1, M2: a payload with `"tool_name": ""` (explicitly present, empty) must
    be told apart from one with no `tool_name` field at all - the first is
    an unrecognized tool, the second is the host-neutral bare-operation
    shape.
    """
    if not isinstance(raw, dict):
        return False
    return any(key in raw for key in _ALIASES.get(name, (name,)))


# ---------------------------------------------------------------------------
# HostEvent - the ONE shape every downstream consumer reads.
# ---------------------------------------------------------------------------

# `tool_kind` values. Not an exhaustive taxonomy of every tool a host might
# ever send - just enough for the hook to route without re-deriving it:
# a read costs nothing, a fenced mutation walks `targets` through the scope
# fence, a shell command is classified as text, `unrecognized` fails closed
# (an unmapped tool name, OR an empty/whitespace `tool_name` that was
# explicitly present - fix round 1, M2), `malformed` fails closed the same
# way for a structurally-invalid `apply_patch` body (fix round 1, C1 - kept
# distinct from `unrecognized` so the chronicle record and the operator-
# facing reason both name the real cause), and `other` is "known tool, none
# of the above" (e.g. Claude's TodoWrite).
TOOL_KIND_READ = "read"
TOOL_KIND_FENCED = "fenced"
TOOL_KIND_SHELL = "shell"
TOOL_KIND_UNRECOGNIZED = "unrecognized"
TOOL_KIND_MALFORMED = "malformed"
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
    || "unknown"`. The first three steps are Addendum 6's binding chain,
    verbatim; the payload-shape step is this module's own addition, needed
    because a real subprocess invocation frequently carries none of the
    three env vars (fix round 1, I2 - the prior docstring wrongly cited the
    whole chain as addendum text; see the module docstring's host-detection
    bullet for the full correction). Env vars decide the DIALECT to speak,
    never the interception claim - `godmode_hookproof.py` owns that
    exclusively, from chronicled proof records only.
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

    `_chronicled_miss: True` (fix round 1, M1) tells the hook this preview
    already has its own dedicated chronicle record
    (`record_unrecognized_tool`, called alongside this) - the classifier's
    OWN generic refusal-write, downstream, must not write a second record
    for the same miss.
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
        "_chronicled_miss": True,
    }


def record_unrecognized_tool(archive: Any, host: str, tool: str) -> None:
    """Counts-only miss record: which host and tool name reached the gate
    with no adapter mapping - never the command/target text that came with
    it. Best-effort: a chronicle failure must never change the fail-closed
    answer, which is already decided before this is ever called. Called
    exactly ONCE per miss (fix round 1, M1) - the hook checks
    `preview["_chronicled_miss"]` before its own generic refusal-write, so
    this is never followed by a second record for the same call.
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


def malformed_apply_patch_preview(tool: str) -> dict[str, Any]:
    """The `classify_action`-shaped preview for an `apply_patch` call whose
    patch body contains a directive-looking line that does not match the
    strict grammar (fix round 1, C1). Distinct category from
    `unrecognized-tool`: the TOOL is known (`apply_patch` is mapped) - what
    failed is the patch BODY's own structure, and the operator-facing
    reason should say that, not "this tool is unmapped".
    """
    return {
        "protected": True,
        "category": "apply-patch-malformed-directive",
        "operation_digest": hashlib.sha256((tool or "apply_patch").encode("utf-8")).hexdigest(),
        "impact": [
            "the patch body contains a line that looks like a directive "
            "(the *** marker plus an Add/Update/Delete File or Move to "
            "keyword) but does not match the exact grammar required - "
            "failing the whole call closed rather than trusting only the "
            "targets that did parse"],
        "tier": "R3",
        "second_confirmation_required": False,
        "external_repo_ref": None,
        "_chronicled_miss": True,
    }


def record_malformed_apply_patch(archive: Any, host: str, tool: str) -> None:
    """Counts-only miss record for `malformed_apply_patch_preview` - host and
    tool name only, never the patch body. Best-effort, same discipline as
    `record_unrecognized_tool`.
    """
    try:
        archive.append(
            "refusal", "apply-patch-malformed-directive",
            {"host": host[:60], "tool": (tool or "")[:120],
             "category": "apply-patch-malformed-directive", "tier": "R3"},
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


def _malformed(host: str, tool: str, raw: Any) -> HostEvent:
    return HostEvent(
        schema=SCHEMA,
        event=str(field(raw, "hook_event_name") or ""),
        host=host,
        tool=tool or "",
        operation="",
        targets=[],
        cwd=str(field(raw, "cwd") or ""),
        request_id=str(field(raw, "request_id") or ""),
        tool_kind=TOOL_KIND_MALFORMED,
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
_APPLY_PATCH_STRICT = (_APPLY_PATCH_ADD, _APPLY_PATCH_DELETE,
                       _APPLY_PATCH_UPDATE, _APPLY_PATCH_MOVE)

# Fix round 1, C1 (review Critical): a LOOSE detector, deliberately not
# anchored and deliberately case-insensitive - the strict regexes above
# require column-0, single-space, exact-case text; this one exists purely
# to catch a line that LOOKS like a directive but does not match them.
# Reviewer's live repro: "*** Add File: harmless.txt" alongside
# "  *** Add File: /etc/passwd" (two-space indent) used to silently keep
# only the first - `has_malformed_directive` below is what makes the whole
# call fail closed instead.
#
# Fix round 2 (re-review adversarial extension): round 1's version matched
# literal `***` + keyword + colon, which two smuggling vectors defeated -
# a Unicode zero-width character breaking the literal `***` run (`**<ZWSP>*
# Add File: /etc/passwd`), and a directive keyword with no trailing colon
# (`*** Add File /etc/passwd`). Both used to read as ordinary content (no
# lookalike match => not malformed => not a recognised target either =>
# silently dropped, call proceeds on whatever DID parse). Fixed two ways:
#
# 1. `_normalize_for_lookalike` strips every Unicode category-Cf character
#    (zero-width space/joiner/non-joiner, BOM anywhere in the line, LRM/
#    RLM, and any other "format" character Unicode ever defines - looked
#    up by `unicodedata.category`, never a hardcoded partial list of code
#    points) and folds whitespace runs, BEFORE lookalike matching only.
#    The STRICT grammar above still parses the ORIGINAL, un-normalized
#    line - this normalization exists purely to make the loose detector at
#    least as permissive as any plausible host parser, never to change
#    what counts as a valid directive.
# 2. The colon requirement is dropped: `_looks_directive_like` now asks
#    only "does a run of 2+ asterisks appear, followed somewhere later in
#    the (normalized) line by a directive keyword" - `Add|Update|Delete|
#    Rename` + `File`, or `Move` + `to`/`File`. `Rename` is included even
#    though this repo's own strict grammar only ever emits `rename` via a
#    `Move to` pairing - the detector's job is to be broader than what we
#    parse, not equal to it.
#
# The detector's job is to OVER-TRIGGER, not to precision-match Codex's
# grammar: a false positive here costs one fail-closed `apply_patch` call
# (recoverable - ask/deny, staged capability, or the operator running it
# themselves); a false negative is a silently-dropped scope-fence bypass.
# If the real Codex parser turns out to be stricter than this detector on
# any axis, over-triggering here is harmless - the call simply fails closed
# on text the real tool would have rejected anyway.
_STAR_RUN = re.compile(r"\*{2,}")
_DIRECTIVE_KEYWORD = re.compile(
    r"(?:Add|Update|Delete|Rename)\s*File\b|Move\s*(?:to|File)\b", re.IGNORECASE)


def _normalize_for_lookalike(line: str) -> str:
    """Detection-only normalization - never applied to the line the STRICT
    grammar parses. Strips Unicode category-Cf ("format") characters by
    category lookup (not a hardcoded list: BOM/ZWSP/ZWJ/ZWNJ/LRM/RLM and
    anything else Unicode ever classifies as Cf), then folds every run of
    whitespace (including whatever whitespace a stripped format character
    left behind) down to a single space.
    """
    without_format_chars = "".join(
        ch for ch in line if unicodedata.category(ch) != "Cf")
    return re.sub(r"\s+", " ", without_format_chars)


def _looks_directive_like(normalized_line: str) -> bool:
    """`True` iff a run of 2+ asterisks appears, followed somewhere later
    in the line by a directive keyword - colon optional, spacing
    irrelevant (already folded by `_normalize_for_lookalike`).
    """
    star = _STAR_RUN.search(normalized_line)
    if star is None:
        return False
    return _DIRECTIVE_KEYWORD.search(normalized_line, star.end()) is not None

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


def has_malformed_directive(patch_text: str) -> bool:
    """Fix round 1, C1 (widened in fix round 2): `True` iff any line in
    `patch_text` LOOKS like a patch directive - after Unicode-format-
    character stripping and whitespace folding (`_normalize_for_lookalike`,
    fix round 2), a 2+-asterisk run followed by a directive keyword,
    colon optional (`_looks_directive_like`) - but the ORIGINAL,
    un-normalized line does not match one of the four STRICT grammars
    `apply_patch_targets` requires. The caller's job is to fail the WHOLE
    call closed when this is `True` - never to trust `apply_patch_targets`'s
    output as "the complete picture" once any line in the body looked
    directive-shaped and failed to parse. Ordinary patch content (`+`/`-`
    diff lines, `*** Begin Patch`/`*** End Patch`, a markdown `**bold**`
    line with no directive keyword after the asterisks) never matches the
    lookalike pattern at all, so a normal, fully well-formed patch never
    trips this.
    """
    for line in patch_text.splitlines():
        if not _looks_directive_like(_normalize_for_lookalike(line)):
            continue
        if any(pattern.match(line) for pattern in _APPLY_PATCH_STRICT):
            continue
        return True
    return False


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
        # Fix round 1, C1 (review Critical): checked BEFORE trusting
        # apply_patch_targets's output - a patch with one well-formed and
        # one malformed directive must never proceed on the well-formed
        # target alone.
        if has_malformed_directive(patch_text):
            return _malformed("codex", tool, raw)
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


def parse_host_payload(raw: Any) -> HostEvent:
    """Detect the host, translate its payload into one canonical `HostEvent`.

    Every call classifies fully - fix round 1 (C2/I1) removed the prior
    revision's `seen`-set dedup entirely; see the module docstring's
    "Gate-exactly-once dedup was REMOVED" bullet for why. `request_id`
    still travels on the returned `HostEvent` (and is hashed, never stored
    raw, by `capture_payload_probe`) - nothing in this function deduplicates
    on it.
    """
    if not isinstance(raw, dict):
        raw = {}
    host = detect_host(raw)

    # Fix round 1, M2: a `tool_name` field that is PRESENT but empty or
    # whitespace-only is a host explicitly saying "no tool" - that is not
    # the same signal as a payload that carries no `tool_name` field at
    # all (the bare `{"operation": ...}` shape), and must not be routed
    # there. `field_present` answers "was the key there", independent of
    # what `field` reads back as its value.
    tool_name = field(raw, "tool_name")
    tool_name_given = isinstance(tool_name, str) and tool_name.strip()
    if not field_present(raw, "tool_name"):
        event = _adapt_bare(raw, host)
    elif not tool_name_given:
        event = _unrecognized(host, str(tool_name) if tool_name is not None else "", raw)
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


# ---------------------------------------------------------------------------
# CX-3: public aliases of this module's own tool/event vocabularies, for
# `godmode_host_manifests.py` (the packaging layer) to build host hook
# manifests FROM. A manifest generator must never re-type a tool or event
# name by hand - every matcher/allowlist it emits is built from one of these
# constants, so a manifest can never declare a tool this adapter would not
# also recognise (or vice versa). Same objects as the private names above,
# just re-exported without the leading underscore for cross-module use.
# ---------------------------------------------------------------------------
CODEX_TOOLS = _CODEX_TOOLS
GROK_TOOLS = _GROK_TOOLS
CLAUDE_TOOLS = _CLAUDE_TOOLS
CURSOR_EVENTS = _CURSOR_EVENTS
GEMINI_EVENTS = _GEMINI_EVENTS
PRETOOL_EVENT_NAMES = _PRETOOL_EVENT_NAMES

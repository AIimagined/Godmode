"""R-5 + NS-10a: `hooks wire` as one function, run in two modes.

`wire()` is the single code path behind both `hooks wire --all` and its
`--dry-run` preview: the same rendering, the same comparisons, and the
same [CREATE]/[UPDATE]/[OK]/[CONFLICT]/[INVALID] classification either way - only
whether the result is actually written to disk differs. A preview and its
matching apply can therefore never disagree with each other, because
nothing about the plan changes between the two calls, only `dry_run`.

NS-10a (idempotent marker-delimited host-config merge): every host writer
below owns exactly one region of a file it may have to share with other,
foreign content - a JSON object gets a `"godmode"` owned key (Antigravity's
`.agents/hooks.json`), a JSON array gets entries carrying `"_godmode":
true` (Codex's `.codex/hooks.json` event blocks). Foreign top-level keys
and array entries survive a merge, but both JSON strategies re-serialize
the WHOLE document to write their own region back out: key order and
foreign content are preserved, exact byte formatting (indent width,
inline-array compaction, a missing trailing newline) is not - only the
strategy below (`merge_text_block()`) is byte-for-byte. A whole-file
artifact with nothing to share (OpenCode's generated shim) carries its own
one-line digest header instead of a begin/end pair, for the same reason:
telling "we rendered this before, unedited" from "someone hand-edited our
own output" apart without a second state file. `merge_text_block()` below
is the literal `<!-- godmode:begin -->` / `<!-- godmode:end -->` primitive
the plan and spec name for a plain text/TOML shared config, exercised
directly by `tests/test_hooks_wire.py` and, since NS-6, by the real Copilot
instructions block (`.github/copilot-instructions.md`) - the first target
this primitive actually ships against, and Markdown, not TOML: the shell/
TOML-style `# --- godmode:begin ---` line this primitive originally used
would render as a stray H1 heading inside `copilot-instructions.md` (a `#
`-led line is a Markdown heading), noise in the very file a human reads
alongside the model. An HTML comment renders as nothing in Markdown; the
day a real TOML host needs this primitive, TOML has no comment syntax an
HTML comment satisfies either (only `#`), so that caller will need its own
marker/digest-prefix pair - a follow-up scoped to whichever task adds that
host, not a regression introduced here (no TOML host exists today).

Every strategy answers the same question the same way: is the on-disk
Godmode-owned region *exactly* what the last successful write of it left
behind? A digest recorded alongside that region at write time makes the
answer honest - if the region we can see now does not hash to the digest
we see now, something changed it since Godmode last touched it, and that
is a `conflict`, not a silent overwrite.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Sequence

from .godmode_errors import GodmodeError
from .godmode_paths import contained_or_refuse

# Hosts `hooks wire` can write a project-level artifact for today - the
# same set `cmd_hooks`'s own "hooks wire knows codex ... opencode ...
# antigravity ... copilot ... kiro" error message already names. `hooks
# wire --all` and `hooks status`'s `wire_state` column both walk this one
# tuple.
WIRE_HOSTS: tuple[str, ...] = ("codex", "antigravity", "opencode", "copilot", "kiro")

ANTIGRAVITY_OWNED_KEY = "godmode"
ANTIGRAVITY_DIGEST_FIELD = "_godmode_digest"
CODEX_TAG_KEY = "_godmode"
CODEX_DIGEST_FIELD = "_godmode_digest"
OPENCODE_DIGEST_PREFIX = "// godmode:digest:"

BEGIN_MARKER = "<!-- godmode:begin -->"
END_MARKER = "<!-- godmode:end -->"
DIGEST_COMMENT_PREFIX = "<!-- godmode:digest:"
DIGEST_COMMENT_SUFFIX = " -->"

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _digest(payload: Any) -> str:
    """One short, stable fingerprint for a Godmode-owned region - a string
    body hashed as-is, anything else canonicalized through JSON first so
    key order never changes the digest."""
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def _rel(project: Path, target: Path) -> str:
    """The target as the report names it: project-relative, always.

    `target` comes back from `contained_or_refuse` RESOLVED (symlinks and
    8.3 short names expanded, `..` collapsed) while `project` is whatever
    the caller passed. When the two spell the same directory differently -
    a temp directory reached through an alias, a `..` in the argument -
    a plain `relative_to` raises and the report used to print the absolute
    resolved path in the alias case and the relative one otherwise. The
    same file must be named the same way whichever spelling the project
    arrived under, so the comparison is retried on the resolved pair.
    """
    try:
        return str(target.relative_to(project))
    except ValueError:  # godmode: swallow-ok: falls through to the retry on the resolved pair below
        pass
    try:
        return str(target.resolve().relative_to(Path(project).resolve()))
    except (ValueError, OSError):
        return str(target)


def _read_raw(path: Path) -> str:
    """Read a target file's text with its own line endings intact -
    `newline=""` turns off `Path.read_text()`'s universal-newline
    translation, so a CRLF file reads back as CRLF, not silently as LF."""
    # open(), not read_text(newline=...): that keyword arrived in Python 3.13
    # and this runs on 3.11 (first 3.11 CI run, 2026-09-24).
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _majority_newline(raw: str) -> str:
    """n6: the dominant line-ending style already present in `raw`, by
    count rather than by mere presence - CRLF pairs against bare (non-CRLF)
    LFs. A file is not always purely one style or the other (a hand-edit,
    a tool that writes one line differently, an old commit merged across
    checkouts with different `core.autocrlf`); counting means one outlier
    line does not flip the whole file's write style. Empty content, or a
    tie, keeps LF."""
    crlf = raw.count("\r\n")
    bare_lf = raw.count("\n") - crlf
    return "\r\n" if crlf > bare_lf else "\n"


def _newline_of(raw: str, exists: bool) -> str:
    """The line ending a write should match: a brand-new file always gets
    LF; an existing file keeps its own majority style (`_majority_newline`,
    n6). Never flips a file's dominant style to the other - that turns
    every wire of a CRLF-committed config into a whole-file diff."""
    if not exists:
        return "\n"
    return _majority_newline(raw)


def _write_matching(path: Path, text: str, newline: str) -> None:
    """Write `text` (built with plain "\\n") using the newline style
    `_newline_of` detected, with `newline=""` so `Path.write_text()` does
    not re-translate it back to the platform default underneath us."""
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")


def _write_raw(path: Path, text: str) -> None:
    """Write `text` byte-for-byte, no newline translation at all - for
    output that has ALREADY chosen its own line endings (`merge_text_block`
    stamps its own newline style internally), where a second
    `_write_matching`-style replace would double-convert an existing CRLF
    file's untouched prefix/suffix."""
    path.write_text(text, encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Antigravity: JSON object, one owned top-level key ("godmode").
# ---------------------------------------------------------------------------


def _plan_antigravity(plugin_root: Path, project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    root = Path(plugin_root)
    fragment = host_manifests.build_antigravity_fragment()
    payload = json.loads(json.dumps(fragment["godmode"]).replace(
        host_manifests.ANTIGRAVITY_ROOT_TOKEN + "/", root.as_posix() + "/"))
    target = contained_or_refuse(project / ".agents" / "hooks.json",
                                  [project], "antigravity hooks path")
    exists = target.is_file()
    raw = _read_raw(target) if exists else ""
    newline = _newline_of(raw, exists)
    existing: dict[str, Any] = {}
    invalid = False
    if exists:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
            invalid = True
        if not invalid and isinstance(parsed, dict):
            existing = parsed
        elif not invalid:
            invalid = True

    state: str
    reason = ""
    if not exists:
        state = "create"
    elif invalid:
        # B3: unparseable (or non-object) JSON is refused, never forced -
        # the legacy per-host writers already say so; `wire()` must agree
        # and `--force` must not be able to clear this state.
        state = "invalid"
        reason = "exists but is not valid JSON, or not the expected shape; fix or remove it first"
    else:
        prior = existing.get(ANTIGRAVITY_OWNED_KEY)
        if prior is None:
            state = "update"  # file exists, our key does not yet
        elif not isinstance(prior, dict):
            state = "conflict"
        else:
            prior_digest = prior.get(ANTIGRAVITY_DIGEST_FIELD)
            prior_payload = {k: v for k, v in prior.items() if k != ANTIGRAVITY_DIGEST_FIELD}
            if prior_digest is None:
                # B4: no digest was ever recorded - a legacy install from
                # before this field existed. If the content on disk is
                # exactly what today's renderer would produce, that is
                # evidence we authored it, not evidence of tampering.
                state = "update" if prior_payload == payload else "conflict"
            elif prior_digest != _digest(prior_payload):
                state = "conflict"
            else:
                state = "ok" if prior_payload == payload else "update"

    def writer() -> None:
        merged = dict(existing)
        merged[ANTIGRAVITY_OWNED_KEY] = {**payload, ANTIGRAVITY_DIGEST_FIELD: _digest(payload)}
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_matching(target, json.dumps(merged, indent=2) + "\n", newline)
        host_manifests._record_installed(project, "antigravity-hooks", target)

    return {"host": "antigravity", "target": target, "rel": _rel(project, target),
            "state": state, "reason": reason, "writer": writer}


# ---------------------------------------------------------------------------
# Codex: JSON, per-event arrays; Godmode's own entries carry "_godmode": true.
# ---------------------------------------------------------------------------


def _tag_codex_doc(doc: dict[str, Any]) -> dict[str, list]:
    hooks: dict[str, list] = {}
    for event, blocks in doc.get("hooks", {}).items():
        hooks[event] = [dict(block, **{CODEX_TAG_KEY: True}) for block in blocks]
    return {"hooks": hooks}


def _plan_codex(plugin_root: Path, project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    rendered = host_manifests.codex_project_hooks(Path(plugin_root))
    tagged = _tag_codex_doc(rendered)
    target = contained_or_refuse(project / ".codex" / "hooks.json",
                                  [project], "codex hooks path")
    exists = target.is_file()
    raw = _read_raw(target) if exists else ""
    newline = _newline_of(raw, exists)
    existing: dict[str, Any] = {"hooks": {}}
    invalid = False
    if exists:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
            invalid = True
        if not invalid and isinstance(parsed, dict):
            existing = parsed
        elif not invalid:
            invalid = True

    # B5: a file that parses as JSON and is an object, but whose "hooks"
    # region is not the shape every operation below assumes - not a dict,
    # an event's value not a list, or a block entry not a dict - must not
    # be silently iterated and rewritten (the old `else {}` fallback below
    # discarded exactly this shape and wrote a fresh "hooks" over it,
    # dropping whatever was actually there). Same "invalid, unforceable"
    # treatment B3 gives unparseable JSON: the remedy is identical (fix or
    # remove the file), so it carries the same reason text.
    existing_hooks: dict[str, Any] = {}
    if not invalid and exists:
        raw_hooks = existing.get("hooks", {})
        if not isinstance(raw_hooks, dict):
            invalid = True
        elif not all(isinstance(blocks, list)
                     and all(isinstance(block, dict) for block in blocks)
                     for blocks in raw_hooks.values()):
            invalid = True
        else:
            existing_hooks = raw_hooks

    # B1: a block written by the legacy `hooks wire --host codex` (or
    # `write_codex_project_hooks` directly, which every earlier release's
    # README pointed operators at) carries none of our tagging - no
    # `_godmode` key, no digest - but its content is byte-identical to what
    # the CURRENT renderer would produce for that same event, modulo that
    # missing tag. Recognise that shape and adopt it instead of treating it
    # as foreign, or every hook fires twice once `wire()` "merges" it in.
    legacy_matched: dict[str, list[int]] = {}
    for event, fresh_blocks in rendered["hooks"].items():
        pool = list(fresh_blocks)
        matched_indices: list[int] = []
        for idx, block in enumerate(existing_hooks.get(event, [])):
            if isinstance(block, dict) and block.get(CODEX_TAG_KEY) is True:
                continue
            if block in pool:
                pool.remove(block)
                matched_indices.append(idx)
        legacy_matched[event] = matched_indices

    def _combined_prior_tagged() -> dict[str, list]:
        """What the file's Godmode-owned content looks like once explicitly
        tagged blocks and adopted legacy blocks are both counted as ours -
        the shape `prior_digest` was (or should have been) computed over.

        B6: built from the events actually present in `existing_hooks` (the
        file as it is on disk), not from `tagged["hooks"]`'s key set (today's
        render). Iterating today's event set meant a renderer that adds an
        event invented an empty-list key the stored digest never covered,
        and one that drops an event silently lost a key the stored digest
        did cover - either way a pure version bump that changes nothing on
        disk read back as a hand-edit. Verifying the region as stored,
        independent of what the renderer emits now, is the same approach
        the antigravity and opencode strategies above already use.
        """
        combined: dict[str, list] = {}
        for event, blocks in existing_hooks.items():
            legacy_idx = set(legacy_matched.get(event, []))
            out = []
            for idx, block in enumerate(blocks):
                if isinstance(block, dict) and block.get(CODEX_TAG_KEY) is True:
                    out.append(block)
                elif idx in legacy_idx:
                    out.append(dict(block, **{CODEX_TAG_KEY: True}))
            if out:
                combined[event] = out
        return {"hooks": combined}

    prior_digest = existing.get(CODEX_DIGEST_FIELD)
    combined_prior = _combined_prior_tagged()
    has_prior_tag = any(combined_prior["hooks"].values())

    state: str
    reason = ""
    if not exists:
        state = "create"
    elif invalid:
        # B3: unparseable (or non-object) JSON is refused, never forced.
        state = "invalid"
        reason = "exists but is not valid JSON, or not the expected shape; fix or remove it first"
    elif prior_digest is not None:
        if prior_digest != _digest(combined_prior):
            state = "conflict"
        else:
            state = "ok" if combined_prior == tagged else "update"
    elif has_prior_tag:
        # B4: tagged and/or legacy-matched content with no recorded digest
        # (a legacy install predates the digest field entirely). Adopt it
        # if it is structurally exactly today's render; otherwise there is
        # nothing to prove we authored it, so it stays a conflict.
        state = "update" if combined_prior == tagged else "conflict"
    else:
        # A hand-authored file with nothing of ours in it yet (and nothing
        # legacy-shaped either): adding our block is a legitimate update,
        # not a conflict - there is no prior Godmode content to drift from.
        state = "update"

    def writer() -> None:
        merged_hooks: dict[str, list] = {}
        # N1: sorted, not set-iteration order, so two machines wiring the
        # same repo (or two runs under hash randomization) write the same
        # bytes instead of a gratuitous key-order diff.
        for event in sorted(set(existing_hooks) | set(tagged["hooks"])):
            legacy_idx = set(legacy_matched.get(event, []))
            foreign = [block for idx, block in enumerate(existing_hooks.get(event, []))
                       if idx not in legacy_idx
                       and not (isinstance(block, dict) and block.get(CODEX_TAG_KEY) is True)]
            fresh = tagged["hooks"].get(event, [])
            if foreign or fresh:
                merged_hooks[event] = foreign + fresh
        # B2: every top-level key besides "hooks" (e.g. "version", "notify")
        # is foreign to us and must survive - only "hooks" and our own
        # digest field are ours to overwrite.
        merged_doc = {**existing, "hooks": merged_hooks, CODEX_DIGEST_FIELD: _digest(tagged)}
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_matching(target, json.dumps(merged_doc, indent=2) + "\n", newline)
        host_manifests._record_installed(project, "codex-hooks", target)

    return {"host": "codex", "target": target, "rel": _rel(project, target),
            "state": state, "reason": reason, "writer": writer}


# ---------------------------------------------------------------------------
# OpenCode: a whole dedicated file - a one-line digest header is the marker.
# ---------------------------------------------------------------------------


def _plan_opencode(plugin_root: Path, project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    root = Path(plugin_root)
    source = root / "adapters" / "opencode" / "godmode.opencode.js"
    body = source.read_text(encoding="utf-8")
    digest = _digest(body)
    rendered = f"{OPENCODE_DIGEST_PREFIX}{digest}\n{body}"
    target = contained_or_refuse(project / ".opencode" / "plugins" / "godmode.js",
                                  [project], "opencode shim path")
    exists = target.is_file()
    raw = _read_raw(target) if exists else ""
    newline = _newline_of(raw, exists)
    # Compare on content, not on line ending - a CRLF-written shim from a
    # prior wire is still `ok`/`update` on its own terms, never a false
    # conflict just because the file happens to carry CRLF.
    normalized = raw.replace("\r\n", "\n")

    state: str
    if not exists:
        state = "create"
    else:
        if normalized == rendered:
            state = "ok"
        else:
            first_line, sep, rest = normalized.partition("\n")
            if sep and first_line.startswith(OPENCODE_DIGEST_PREFIX):
                prior_digest = first_line[len(OPENCODE_DIGEST_PREFIX):]
                state = "update" if prior_digest == _digest(rest) else "conflict"
            elif normalized == body:
                # B4: predates the digest header entirely (a legacy
                # `hooks wire --host opencode` / `write_opencode_project_
                # shim` install), but the content is exactly what today's
                # renderer would produce - adopt it (add the header) rather
                # than flag a false hand-edit on every legacy install.
                state = "update"
            else:
                # Predates this scheme with different content, or is not
                # ours at all - unknown provenance is refused, never
                # silently claimed as ours.
                state = "conflict"

    def writer() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_matching(target, rendered, newline)
        host_manifests._record_installed(project, "opencode-shim", target)

    return {"host": "opencode", "target": target, "rel": _rel(project, target),
            "state": state, "reason": "", "writer": writer}


# ---------------------------------------------------------------------------
# NS-6: Copilot - JSON owned-key strategy for `.github/hooks/godmode.json`
# (the whole "hooks" region is godmode's own, foreign top-level keys survive
# a merge the same way antigravity's "godmode" key does), plus the literal
# `merge_text_block()` text-marker primitive for the advisory block in
# `.github/copilot-instructions.md`. One host, two files, one combined
# [CREATE]/[UPDATE]/[OK]/[CONFLICT]/[INVALID] state - `wire()` itself only
# ever sees one plan per host name.
# ---------------------------------------------------------------------------

COPILOT_HOOKS_OWNED_KEY = "hooks"
COPILOT_HOOKS_DIGEST_FIELD = "_godmode_digest"


def _plan_copilot_hooks_file(plugin_root: Path, project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    root = Path(plugin_root)
    payload = json.loads(json.dumps(host_manifests.build_copilot_hooks()).replace(
        host_manifests.COPILOT_ROOT_TOKEN + "/", root.as_posix() + "/"))[
        COPILOT_HOOKS_OWNED_KEY]
    target = contained_or_refuse(project / ".github" / "hooks" / "godmode.json",
                                  [project], "copilot hooks path")
    exists = target.is_file()
    raw = _read_raw(target) if exists else ""
    newline = _newline_of(raw, exists)
    existing: dict[str, Any] = {}
    invalid = False
    if exists:
        try:
            parsed = json.loads(raw)
        except ValueError:
            invalid = True
        else:
            if isinstance(parsed, dict):
                existing = parsed
            else:
                invalid = True

    state: str
    reason = ""
    if not exists:
        state = "create"
    elif invalid:
        state = "invalid"
        reason = "exists but is not valid JSON, or not the expected shape; fix or remove it first"
    else:
        prior = existing.get(COPILOT_HOOKS_OWNED_KEY)
        if prior is None:
            state = "update"
        elif not isinstance(prior, dict):
            # N5: parity with antigravity's owned-key planner (`:175-176`
            # there), which marks a non-dict prior `conflict` explicitly
            # rather than reaching it only incidentally via a digest
            # mismatch - same outcome today (a non-dict `prior` can never
            # equal `_digest(prior)`'s dict-shaped input, so it always fell
            # through to `conflict` anyway), but the intent is now
            # readable at the branch that actually decides it.
            state = "conflict"
        else:
            prior_digest = existing.get(COPILOT_HOOKS_DIGEST_FIELD)
            if prior_digest is None:
                state = "update" if prior == payload else "conflict"
            elif prior_digest != _digest(prior):
                state = "conflict"
            else:
                state = "ok" if prior == payload else "update"

    def writer() -> None:
        merged = dict(existing)
        merged[COPILOT_HOOKS_OWNED_KEY] = payload
        merged[COPILOT_HOOKS_DIGEST_FIELD] = _digest(payload)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_matching(target, json.dumps(merged, indent=2) + "\n", newline)
        host_manifests._record_installed(project, "copilot-hooks", target)

    return {"target": target, "rel": _rel(project, target), "state": state,
            "reason": reason, "writer": writer}


def _plan_copilot_instructions(project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    body = host_manifests.copilot_instructions_block()
    target = contained_or_refuse(project / ".github" / "copilot-instructions.md",
                                  [project], "copilot instructions path")
    raw = _read_raw(target) if target.is_file() else ""
    _, state = merge_text_block(raw, body)
    reason = ("the godmode block was hand-edited; fix or remove it first"
              if state == "conflict" else "")

    def writer() -> None:
        # B1 fix round 1: `merge_text_block` is a CLASSIFIER - on
        # `conflict` it returns `existing_text` unchanged (the whole point
        # is that a preview must never silently overwrite a hand-edit). But
        # `writer()` is only ever invoked by `wire()` once the caller has
        # already decided to apply: a clean create/update, or a `conflict`
        # explicitly cleared by `--force`. By the time we are here the
        # block is always meant to be replaced, so recompute the
        # replacement unconditionally via `_replace_text_block` rather than
        # reusing whatever `merge_text_block` returned at plan time - the
        # same way every JSON planner's writer above always re-renders its
        # owned region from scratch regardless of the state that got it
        # here, instead of writing back a value computed under the
        # assumption that a conflict blocks the write.
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_raw(target, _replace_text_block(raw, body))
        host_manifests._record_installed(project, "copilot-instructions", target)

    return {"target": target, "rel": _rel(project, target), "state": state,
            "reason": reason, "writer": writer}


# Precedence for combining the two Copilot sub-plans into the one plan
# `wire()` sees for the "copilot" host: a real problem (invalid/conflict)
# always wins; otherwise the more consequential of create/update/ok wins,
# except a lone "create" downgrades to "update" the moment the OTHER file
# is not also brand new (a project that already has one of the two files -
# an unusual but real starting state - is having an existing tree touched,
# not created from nothing).
_COPILOT_STATE_RANK = {"invalid": 4, "conflict": 3, "update": 2, "create": 1, "ok": 0}


def _plan_copilot(plugin_root: Path, project: Path) -> dict[str, Any]:
    hooks_plan = _plan_copilot_hooks_file(plugin_root, project)
    instructions_plan = _plan_copilot_instructions(project)
    states = {hooks_plan["state"], instructions_plan["state"]}
    combined = max(states, key=lambda state: _COPILOT_STATE_RANK[state])
    if combined == "create" and states != {"create"}:
        combined = "update"
    reason = hooks_plan["reason"] or instructions_plan["reason"]

    def writer() -> None:
        hooks_plan["writer"]()
        instructions_plan["writer"]()

    rel = f"{hooks_plan['rel']} + {instructions_plan['rel']}"
    return {"host": "copilot", "target": hooks_plan["target"], "rel": rel,
            "state": combined, "reason": reason, "writer": writer}


# ---------------------------------------------------------------------------
# NS-6: Kiro - array-tag strategy for `.kiro/hooks.json`, mirroring the
# Codex merge above (Godmode's own rule blocks per event carry `"_godmode":
# true`; a legacy, untagged block that is byte-identical to today's render
# is adopted rather than duplicated). Deliberately a separate, self-
# contained function rather than a shared helper factored out of
# `_plan_codex`: the two hosts' merge rules are identical in SHAPE today,
# but Codex's is exercised by a large, already-passing fix-round test suite
# this task must not risk regressing by refactoring it mid-flight.
# ---------------------------------------------------------------------------

KIRO_TAG_KEY = "_godmode"
KIRO_DIGEST_FIELD = "_godmode_digest"


def _tag_kiro_doc(doc: dict[str, Any]) -> dict[str, list]:
    hooks: dict[str, list] = {}
    for event, blocks in doc.get("hooks", {}).items():
        hooks[event] = [dict(block, **{KIRO_TAG_KEY: True}) for block in blocks]
    return {"hooks": hooks}


def _plan_kiro(plugin_root: Path, project: Path) -> dict[str, Any]:
    from . import godmode_host_manifests as host_manifests

    root = Path(plugin_root)
    rendered = json.loads(json.dumps(host_manifests.build_kiro_hooks()).replace(
        host_manifests.KIRO_ROOT_TOKEN + "/", root.as_posix() + "/"))
    tagged = _tag_kiro_doc(rendered)
    target = contained_or_refuse(project / ".kiro" / "hooks.json",
                                  [project], "kiro hooks path")
    exists = target.is_file()
    raw = _read_raw(target) if exists else ""
    newline = _newline_of(raw, exists)
    existing: dict[str, Any] = {"hooks": {}}
    invalid = False
    if exists:
        try:
            parsed = json.loads(raw)
        except ValueError:
            invalid = True
        else:
            if isinstance(parsed, dict):
                existing = parsed
            else:
                invalid = True

    existing_hooks: dict[str, Any] = {}
    if not invalid and exists:
        raw_hooks = existing.get("hooks", {})
        if not isinstance(raw_hooks, dict):
            invalid = True
        elif not all(isinstance(blocks, list)
                     and all(isinstance(block, dict) for block in blocks)
                     for blocks in raw_hooks.values()):
            invalid = True
        else:
            existing_hooks = raw_hooks

    legacy_matched: dict[str, list[int]] = {}
    for event, fresh_blocks in rendered["hooks"].items():
        pool = list(fresh_blocks)
        matched_indices: list[int] = []
        for idx, block in enumerate(existing_hooks.get(event, [])):
            if isinstance(block, dict) and block.get(KIRO_TAG_KEY) is True:
                continue
            if block in pool:
                pool.remove(block)
                matched_indices.append(idx)
        legacy_matched[event] = matched_indices

    def _combined_prior_tagged() -> dict[str, list]:
        combined: dict[str, list] = {}
        for event, blocks in existing_hooks.items():
            legacy_idx = set(legacy_matched.get(event, []))
            out = []
            for idx, block in enumerate(blocks):
                if isinstance(block, dict) and block.get(KIRO_TAG_KEY) is True:
                    out.append(block)
                elif idx in legacy_idx:
                    out.append(dict(block, **{KIRO_TAG_KEY: True}))
            if out:
                combined[event] = out
        return {"hooks": combined}

    prior_digest = existing.get(KIRO_DIGEST_FIELD)
    combined_prior = _combined_prior_tagged()
    has_prior_tag = any(combined_prior["hooks"].values())

    state: str
    reason = ""
    if not exists:
        state = "create"
    elif invalid:
        state = "invalid"
        reason = "exists but is not valid JSON, or not the expected shape; fix or remove it first"
    elif prior_digest is not None:
        if prior_digest != _digest(combined_prior):
            state = "conflict"
        else:
            state = "ok" if combined_prior == tagged else "update"
    elif has_prior_tag:
        state = "update" if combined_prior == tagged else "conflict"
    else:
        state = "update"

    def writer() -> None:
        merged_hooks: dict[str, list] = {}
        for event in sorted(set(existing_hooks) | set(tagged["hooks"])):
            legacy_idx = set(legacy_matched.get(event, []))
            foreign = [block for idx, block in enumerate(existing_hooks.get(event, []))
                       if idx not in legacy_idx
                       and not (isinstance(block, dict) and block.get(KIRO_TAG_KEY) is True)]
            fresh = tagged["hooks"].get(event, [])
            if foreign or fresh:
                merged_hooks[event] = foreign + fresh
        merged_doc = {**existing, "hooks": merged_hooks, KIRO_DIGEST_FIELD: _digest(tagged)}
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_matching(target, json.dumps(merged_doc, indent=2) + "\n", newline)
        host_manifests._record_installed(project, "kiro-hooks", target)

    return {"host": "kiro", "target": target, "rel": _rel(project, target),
            "state": state, "reason": reason, "writer": writer}


_PLANNERS: dict[str, Callable[[Path, Path], dict[str, Any]]] = {
    "codex": _plan_codex,
    "antigravity": _plan_antigravity,
    "opencode": _plan_opencode,
    "copilot": _plan_copilot,
    "kiro": _plan_kiro,
}


def _plan_host(plugin_root: Path, project: Path, host: str) -> dict[str, Any]:
    planner = _PLANNERS.get(host)
    if planner is None:
        raise GodmodeError(f"godmode_wire does not know host {host!r}; known: "
                            f"{', '.join(WIRE_HOSTS)}")
    return planner(plugin_root, project)


def wire(project, hosts: Sequence[str], *, dry_run: bool, force: bool) -> dict[str, Any]:
    """One wiring path, two modes. `dry_run` suppresses writes only - the
    plan (rendering, comparisons, [CREATE]/[UPDATE]/[OK]/[CONFLICT]/[INVALID]
    classification) is identical either way, so a preview and the apply
    that follows it can never disagree.

    A `conflict` anywhere in the batch blocks the WHOLE batch (unless
    `force`): nothing is written for any host, not just the conflicted
    one, so a caller never ends up with half the hosts freshly wired and
    one silently left on stale content because it happened to sort last.

    `invalid` (B3: a host's target exists but failed to parse) blocks the
    WHOLE batch unconditionally - `force` clears a `conflict` (a hand-edit
    we can see and choose to overwrite) but never an `invalid` file, since
    there is no content there to have made an informed choice about.
    """
    project = Path(project)
    plans: list[dict[str, Any]] = []
    for host in hosts:
        try:
            plans.append(_plan_host(_PLUGIN_ROOT, project, host))
        except OSError as exc:
            # N4: `wire_status` already refuses to let a missing/unreadable
            # source artifact (e.g. the OpenCode shim template under a
            # damaged plugin install) raise past it; `wire()` must agree
            # instead of taking `hooks wire --all` down with an exception.
            plans.append({
                "host": host, "target": None,
                "rel": f"<{host}: source unreadable>",
                "state": "invalid",
                "reason": f"could not read the source for {host}: {exc}",
                "writer": lambda: None,
            })
    has_invalid = any(plan["state"] == "invalid" for plan in plans)
    has_conflict = any(plan["state"] == "conflict" for plan in plans)
    safe = not has_invalid and (force or not has_conflict)

    # n1: `invalid` gets its own label. It used to render as `[CONFLICT]`,
    # which is the state `--force` clears - the one state it cannot clear
    # then looked exactly like the one state it can, and an operator who
    # reads `[CONFLICT]` reaches for `--force` first. `[INVALID]` puts the
    # distinction in the token the eye lands on; the parenthetical reason
    # still carries the remedy.
    labels = {"create": "CREATE", "update": "UPDATE", "ok": "OK",
              "conflict": "CONFLICT", "invalid": "INVALID"}
    lines: list[str] = []
    changed: list[str] = []
    for plan in plans:
        state = plan["state"]
        forced_over_conflict = state == "conflict" and force
        effective = "update" if forced_over_conflict else state
        # N8: a forced conflict is recorded as such, never silently relabeled
        # as a plain [UPDATE] the operator has no way to tell apart from an
        # ordinary clean apply.
        note = ""
        if forced_over_conflict:
            note = " (forced over conflict)"
        elif state == "invalid" and plan.get("reason"):
            note = f" ({plan['reason']})"
        lines.append(f"[{labels[effective]}] {plan['host']}: {plan['rel']}{note}")
        if safe and not dry_run and effective in ("create", "update"):
            plan["writer"]()
            changed.append(plan["host"])

    summary = "safe to apply" if safe else "blocked; no changes made"
    return {"lines": lines, "summary": summary, "changed": changed}


def wire_status(project, hosts: Sequence[str] = WIRE_HOSTS) -> dict[str, str]:
    """`hooks status`'s `wire_state` column: `absent`/`in-sync`/`drifted`
    per host, computed by the exact same rendering and comparisons `wire()`
    itself uses (`_plan_host`), so status can never claim a state `hooks
    wire --all` would disagree with."""
    project = Path(project)
    result: dict[str, str] = {}
    for host in hosts:
        try:
            plan = _plan_host(_PLUGIN_ROOT, project, host)
        except OSError:
            # A source artifact this host's plan needs to read (e.g. the
            # OpenCode shim template under the plugin install) is itself
            # missing or unreadable. This column has no fourth value for
            # "cannot even tell" distinct from "never wired", so it reports
            # the same thing a project that was never wired would: `absent`.
            result[host] = "absent"
            continue
        state = plan["state"]
        if state == "create":
            result[host] = "absent"
        elif state == "ok":
            result[host] = "in-sync"
        else:  # update, conflict, or invalid (n2: this column has no
               # fourth value for "cannot even parse/understand it";
               # invalid also reads as drifted)
            result[host] = "drifted"
    return result


# ---------------------------------------------------------------------------
# NS-10a's literal text/TOML primitive. Copilot's `.github/copilot-
# instructions.md` (NS-6) is the first host to actually wire it - a
# Markdown, not TOML, target, which is why the marker pair is an HTML
# comment rather than the `#`-line shell/TOML comment style this primitive
# used before (see the module docstring above). It stays exercised
# directly by tests/test_hooks_wire.py too, ahead of whatever future host
# needs it next (a TOML-based host, or a text fragment appended to another
# host's shell profile).
# ---------------------------------------------------------------------------


def _replace_text_block(existing_text: str, body: str) -> str:
    """Unconditionally drop any existing marker-delimited block and stamp
    the fresh one in its place (or append it, if no markers are present),
    preserving everything outside the block byte-for-byte. This is the
    replacement half of `merge_text_block`'s create/update behaviour,
    factored out so a caller that has already decided to overwrite - a
    clean create/update, or a `conflict` `--force` has cleared - can
    perform the replacement without re-running `merge_text_block`'s own
    conflict *detection* (which returns the text unchanged on conflict,
    exactly because it must never make that decision on its own).
    """
    newline = _majority_newline(existing_text) if existing_text else "\n"
    digest = _digest(body)
    block_lines = [BEGIN_MARKER, f"{DIGEST_COMMENT_PREFIX}{digest}{DIGEST_COMMENT_SUFFIX}",
                   *body.splitlines(), END_MARKER, ""]
    stamped = "\n".join(block_lines)
    if newline == "\r\n":
        stamped = stamped.replace("\n", "\r\n")

    start = existing_text.find(BEGIN_MARKER)
    end = existing_text.find(END_MARKER)
    if start == -1 or end == -1:
        prefix = existing_text
        if prefix and not prefix.endswith("\n"):
            prefix += newline
        return prefix + stamped

    end_of_end_line = existing_text.find("\n", end)
    end_of_end_line = end_of_end_line + 1 if end_of_end_line != -1 else len(existing_text)
    before = existing_text[:start]
    after = existing_text[end_of_end_line:]
    return before + stamped + after


def merge_text_block(existing_text: str, body: str) -> tuple[str, str]:
    """Marker-delimited merge for a text/TOML shared config: everything
    outside `BEGIN_MARKER`/`END_MARKER` is preserved byte-for-byte - unlike
    the JSON strategies above, which re-serialize the whole document, this
    is a raw text slice, so no re-serialization ever touches foreign
    content's formatting. The block between the markers is Godmode's own,
    self-describing (a digest comment on the line right after the marker)
    so a hand-edit inside it is detectable on the next call, exactly as the
    JSON strategies above are.

    Returns `(merged_text, state)` with `state` in the same vocabulary
    `_plan_host` uses (`create`/`update`/`ok`/`conflict`). On `conflict`
    `merged_text` is `existing_text`, UNCHANGED - this function only
    classifies; a caller that means to overwrite a conflict anyway (a
    writer invoked under `--force`) calls `_replace_text_block` directly
    instead of trusting this return value, so a preview can never silently
    have already applied the overwrite it is only supposed to report on.

    n7: the stamped block is written in `existing_text`'s own majority
    newline style (`_majority_newline`) - a brand-new/empty file gets LF,
    an existing CRLF file's block is stamped in CRLF too, so a merge never
    leaves the block itself mixed-ending against the byte-for-byte-
    preserved text around it.
    """
    start = existing_text.find(BEGIN_MARKER)
    end = existing_text.find(END_MARKER)
    if start == -1 or end == -1:
        return (_replace_text_block(existing_text, body),
                ("create" if not existing_text else "update"))

    end_of_end_line = existing_text.find("\n", end)
    end_of_end_line = end_of_end_line + 1 if end_of_end_line != -1 else len(existing_text)
    block_text = existing_text[start:end_of_end_line]
    lines = block_text.splitlines()

    prior_digest = None
    body_lines = lines[1:-1]  # strip BEGIN_MARKER and END_MARKER
    if (body_lines and body_lines[0].startswith(DIGEST_COMMENT_PREFIX)
            and body_lines[0].endswith(DIGEST_COMMENT_SUFFIX)):
        prior_digest = body_lines[0][len(DIGEST_COMMENT_PREFIX):-len(DIGEST_COMMENT_SUFFIX)]
        body_lines = body_lines[1:]
    prior_body = "\n".join(body_lines)

    if prior_digest is None or prior_digest != _digest(prior_body):
        return existing_text, "conflict"
    if prior_body == body:
        return existing_text, "ok"
    return _replace_text_block(existing_text, body), "update"

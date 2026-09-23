"""Read a hook's stdin payload without waiting for EOF.

Sweep 2026-09-07 (a hook-bearing plugin in the research ledger fixed the same
class in three of its own issues): under the Windows pipe implementation a
host's close of the hook's stdin can lag arbitrarily,
so a hook that reads to EOF sits with its work done until the host's own
timeout kills it. A hook payload is one JSON object, so the read resolves
the moment that object is complete; EOF and a size cap are the other two
ends. Standard library only, imported by every hook, so it must stay small
and import nothing beyond what a hook already loads.
"""
from __future__ import annotations

import json
import os
import sys

# `typing` is not imported (about 6-10 ms): `Any` below appears only in an
# annotation, which `from __future__ import annotations` never evaluates.

CAP_BYTES = 2 * 1024 * 1024
_CHUNK = 65536

# The exact prefix `read_first_json`'s own completion check strips before
# looking for the opening `{` - a UTF-8 BOM plus ordinary JSON whitespace.
# `parse_first_json` below strips the same set before decoding, so a shape
# the reader already resolves on (BOM-prefixed, CRLF, trailing data) is
# never re-rejected one step later by a stricter decode.
_LSTRIP_PREFIX = "﻿ \t\r\n"


# Bytes an earlier stage of the same process already read from stdin
# (`godmode_session_entry.py` reads the payload to decide whether the full
# hook runs at all); the next `read_first_json` call returns them once.
_preloaded: bytes | None = None


def preload(raw: bytes) -> None:
    """Hand bytes already read from stdin to the next `read_first_json`."""
    global _preloaded
    _preloaded = raw


def read_first_json(cap: int = CAP_BYTES) -> bytes:
    """The bytes of the first complete JSON object on stdin, or whatever
    arrived before EOF or the cap. A terminal stdin yields nothing: a hook
    run by hand must not sit waiting for a payload nobody is typing."""
    global _preloaded
    if _preloaded is not None:
        raw, _preloaded = _preloaded, None
        return raw
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return b""
    except (AttributeError, ValueError, OSError):
        return b""
    try:
        fd = sys.stdin.fileno()
    except (AttributeError, ValueError, OSError):
        # No descriptor (a test's StringIO, a host that hands a text stream):
        # nothing to poll, so the plain read is the only read.
        try:
            text = sys.stdin.read()
        except Exception:  # noqa: BLE001
            return b""
        return text.encode("utf-8", "replace") if isinstance(text, str) else bytes(text or b"")
    buffer = bytearray()
    decoder = json.JSONDecoder()
    while len(buffer) < cap:
        try:
            chunk = os.read(fd, _CHUNK)
        except OSError:
            break
        if not chunk:
            break
        buffer += chunk
        # Only a closing brace can complete an object; only then is a parse
        # attempt worth its cost.
        if b"}" not in chunk:
            continue
        text = buffer.decode("utf-8", "replace").lstrip(_LSTRIP_PREFIX)
        if not text.startswith("{"):
            continue
        try:
            decoder.raw_decode(text)
        except ValueError:
            continue
        return bytes(buffer)
    return bytes(buffer)


def parse_first_json(raw: bytes) -> tuple[dict[str, Any], bool]:
    """`(payload, malformed)` for the bytes `read_first_json` returned.

    G-8: the reader already resolves on the first complete JSON object and
    tolerates a leading UTF-8 BOM, CRLF, and anything after that object
    (trailing whitespace, trailing data, a second concatenated object) -
    but every call site used to hand the raw bytes straight to `json.loads`,
    which raises on a leading BOM (`Unexpected UTF-8 BOM`) and on any
    non-whitespace content after the first value (`Extra data`). That
    turned a payload shape the reader already accepted into a parse
    failure one step later, in each call site's own way, drifting out of
    step with the fast gate's tolerance for the same bytes. This is the one
    decode both stages now share: the same `_LSTRIP_PREFIX` the reader
    strips before its own completion check, then `raw_decode` for the
    FIRST value only - never a merge of a second object, never a rejection
    because one followed.

    `malformed` is True only for input that is genuinely not a JSON object:
    unparsable, or a JSON value that parsed but was not an object (a bare
    list or string). Empty or whitespace-only input is not a failure - a
    TTY or genuinely empty stdin - and returns `({}, False)`; that "truly
    empty" test is the exact one `_input()` used before this function
    existed (`str.strip()` on the fully decoded text, which treats a BOM
    character as content, not whitespace - `"﻿".strip()` is truthy) so
    a bare BOM, or a BOM plus nothing else meaningful, is never mistaken
    for empty stdin. Fix round 1: `_LSTRIP_PREFIX` treats a BOM as
    whitespace for the READER's own "is the object complete yet" check,
    which is a different question from "was anything real sent at all" -
    conflating the two here made a bare BOM (or BOM+CRLF) decode to an
    empty string and return `({}, False)`, silently indistinguishable from
    a TTY, so G-4(a)'s no-project-evidence guard (a payload that fails to
    parse and carries no session id must not resolve a project from cwd)
    never fired for its own textbook example - a governed project's
    archive still opened and metered a bare-BOM pre-action call.
    """
    if not raw:
        return {}, False
    full_text = raw.decode("utf-8", "replace")
    if not full_text.strip():
        return {}, False
    text = full_text.lstrip(_LSTRIP_PREFIX)
    if not text:
        # Non-empty, and not mere whitespace by the check above either - a
        # BOM (or other `_LSTRIP_PREFIX` content) with no JSON value behind
        # it. Not a JSON object, no different from any other unparsable
        # payload.
        return {}, True
    try:
        value, _end = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return {}, True
    if not isinstance(value, dict):
        return {}, True
    return value, False

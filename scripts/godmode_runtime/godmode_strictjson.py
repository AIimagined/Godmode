"""Strict JSON for CLI payload files: no duplicate keys, no unknown fields, no trailing data.

Hook stdin (`hooks/godmode_stdin.py`) stays on plain `json.loads` - a host's
own JSON emitter is not something Godmode gets to reject mid-session. This
module is for the other input path: a `--payload <file.json>` a human or a
script hands the CLI directly, where a duplicate key silently overwriting an
earlier one, an unrecognised field silently ignored, or trailing garbage
after the object all fail the same way - quietly, with the wrong value
recorded. Refusing all three turns a payload mistake into an error message
instead of a wrong verdict.
"""
from __future__ import annotations

import json
from typing import Any

from .godmode_errors import ArchiveError

_STRIP_CHARS = "﻿ \t\r\n"


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ArchiveError(f"payload has a duplicate key: {key}")
        out[key] = value
    return out


def strict_loads(text: str, allowed_keys: frozenset[str]) -> dict[str, Any]:
    """Decode `text` as one JSON object whose keys are all in `allowed_keys`.

    Raises `ArchiveError` (never a raw `json.JSONDecodeError`) on a
    duplicate key, an unknown top-level key, trailing data after the first
    object, or a top-level value that is not an object at all.
    """
    decoder = json.JSONDecoder(object_pairs_hook=_pairs)
    stripped = text.lstrip(_STRIP_CHARS)
    try:
        value, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"payload is not JSON: {exc.msg} at {exc.pos}") from exc
    if stripped[end:].strip():
        raise ArchiveError("payload has trailing data after the first object")
    if not isinstance(value, dict):
        raise ArchiveError("payload must be a JSON object")
    unknown = sorted(set(value) - set(allowed_keys))
    if unknown:
        raise ArchiveError(f"payload has unknown field(s): {', '.join(unknown)}")
    return value

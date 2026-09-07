"""Read a hook's stdin payload without waiting for EOF.

Sweep 2026-09-07 (a hook-bearing plugin in the research ledger 9ed2c39, their #729/#833/#949): under the Windows
pipe implementation a host's close of the hook's stdin can lag arbitrarily,
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

CAP_BYTES = 2 * 1024 * 1024
_CHUNK = 65536


def read_first_json(cap: int = CAP_BYTES) -> bytes:
    """The bytes of the first complete JSON object on stdin, or whatever
    arrived before EOF or the cap. A terminal stdin yields nothing: a hook
    run by hand must not sit waiting for a payload nobody is typing."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return b""
        fd = sys.stdin.fileno()
    except (AttributeError, ValueError, OSError):
        return b""
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
        text = buffer.decode("utf-8", "replace").lstrip("﻿ \t\r\n")
        if not text.startswith("{"):
            continue
        try:
            decoder.raw_decode(text)
        except ValueError:
            continue
        return bytes(buffer)
    return bytes(buffer)

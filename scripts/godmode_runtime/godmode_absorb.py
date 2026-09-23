"""Shape rules for an upstream absorb decision.

Two verdicts, always. An import verdict of adopt or extend funds code, so
it must cite a source file that was opened - never a README, a doc, or a
release note. A surface read may only park, skip, diverge or say unread.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

# Fix round 1 (coordinator ruling): this project's own reader,
# `godmode_parity._IMPORT_VERDICTS`, and skills/godmode-governance/SKILL.md
# already used `n-a` for "confirmed not applicable" where this module used
# none. The vocabulary is the union of both sets - `n-a` joins here exactly
# as `exists` and `unread` join the reader's set in godmode_parity.py.
IMPORT_VERDICTS = ("adopt", "extend", "diverge", "skip", "exists", "unread", "n-a")
BEHAVIOUR_VERDICTS = ("confirmed-have", "confirmed-dont", "unverified")
_SURFACE = re.compile(r"(^|/)(readme[^/]*|changelog[^/]*|release[-_ ]?notes[^/]*)$|(^|/)docs/", re.I)


def _verdict(value: str, key: str, allowed: Sequence[str]) -> str | None:
    # `\b` before the key: without it, `re.search` matches `import_verdict`
    # as a substring of `no_import_verdict`, since `_` and `i` are both word
    # characters and neither end of that pair is a boundary on its own - a
    # negated key would have silently satisfied the gate.
    match = re.search(r"\b" + key + r"\s*:\s*([a-z-]+)", value, re.I)
    if not match:
        return None
    found = match.group(1).lower()
    return found if found in allowed else f"bad:{found}"


def is_source_cite(evidence: str, archive: Any = None) -> bool:
    """`file:<path>` is a source cite when the path is not surface. I-2 adds
    a second form: `receipt:<source>:<path>` cites what `godmode read`
    actually opened - a source cite only when that receipt exists in
    `archive` and its path is not surface either. `archive` is optional and
    dependency-free (typed `Any`, no `godmode_chronicle` import) so this
    module keeps importing nothing about the archive itself; omitting it
    keeps the pre-I-2 behaviour, where a `receipt:` cite settles nothing."""
    if evidence.startswith("file:"):
        path = evidence[5:].split("#", 1)[0].strip().replace("\\", "/")
        return bool(path) and not _SURFACE.search(path)
    if evidence.startswith("receipt:") and archive is not None:
        target_subject = evidence[len("receipt:"):].strip().replace("\\", "/")
        if not target_subject or ":" not in target_subject:
            return False
        for record in reversed(archive.select(kind="receipt", limit=500)):
            subject = str(record.get("subject", "")).replace("\\", "/")
            if subject != target_subject:
                continue
            path = str((record.get("data") or {}).get("path") or "").replace("\\", "/")
            return bool(path) and not _SURFACE.search(path)
        return False
    return False


def parse_verdicts(value: str) -> tuple[str | None, str | None]:
    """The two verdicts as written, clean of any `bad:` marker - what
    `cmd_remember` persists onto the record's data once a write passes
    `validate_absorb`, so `godmode_parity.upstream_verdicts` reads a
    CLI-recorded absorb decision the same way it reads one written by direct
    archive access."""
    imp = _verdict(value, "import_verdict", IMPORT_VERDICTS)
    beh = _verdict(value, "behaviour_verdict", BEHAVIOUR_VERDICTS)
    return (imp if imp in IMPORT_VERDICTS else None,
            beh if beh in BEHAVIOUR_VERDICTS else None)


def validate_absorb(value: str, evidence: Sequence[str], archive: Any = None) -> list[str]:
    gaps: list[str] = []
    raw_imp = _verdict(value, "import_verdict", IMPORT_VERDICTS)
    raw_beh = _verdict(value, "behaviour_verdict", BEHAVIOUR_VERDICTS)
    if raw_imp is None:
        gaps.append("missing:import_verdict")
    elif raw_imp.startswith("bad:"):
        gaps.append(f"unknown_import_verdict:{raw_imp[4:]}")
    if raw_beh is None:
        gaps.append("missing:behaviour_verdict")
    elif raw_beh.startswith("bad:"):
        gaps.append(f"unknown_behaviour_verdict:{raw_beh[4:]}")
    imp, _beh = parse_verdicts(value)
    if imp in ("adopt", "extend") and not any(is_source_cite(e, archive) for e in evidence):
        # I-2: a decision that cited only `receipt:` evidence and none of it
        # named a source read is refused by its own name - `surface-only` -
        # distinct from citing no receipt or file at all, which is the older
        # and plainer `adopt_or_extend_needs_source_cite`.
        if archive is not None and any(str(e).startswith("receipt:") for e in evidence):
            gaps.append("surface-only")
        else:
            gaps.append("adopt_or_extend_needs_source_cite")
    return gaps

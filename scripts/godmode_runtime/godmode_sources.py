"""Required-source accounting, doc adoption, and guard-pin lookup (S5).

Obligation 4094: the attest counter's read/unread view, extended with
on-the-record exemptions, shared by the handshake and the pre-tool gate.
Obligation 4097: `adopt --from-docs` seeds a late install from the bound
authority documents - counts and digests only, never prose.
Obligation 4166: a state-is-a-gap claim is checked against the tests that
name its surface and the lessons ledger before it may grade verified.
"""
from __future__ import annotations

import json
import os
import re

import hashlib
from pathlib import Path
from typing import Any

EXEMPTION_PREFIX = "sources-exemption:"
ADOPTED_PREFIX = "adopted-doc:"
_MAX_DOC_BYTES = 1_000_000
_MAX_TEST_FILES = 250


def _norm(path: Any) -> str:
    text = str(path).replace("\\", "/").lstrip("./")
    # Grok field report 2026-09-10: `Agents.md` and `AGENTS.md` are one file
    # on Windows and read as two here; the comparison folds case there.
    return text.lower() if os.name == "nt" else text


def transcript_reads(transcript_path: str | Path | None, project: Path) -> set[str]:
    """Project-relative paths a host transcript shows being read this
    session: Read/Edit/Grep tool inputs, and shell or interpreter commands
    that name a file under the project (the reader the handshake trusts
    beside `file:` citations)."""
    if not transcript_path:
        return set()
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    root = str(Path(project).resolve()).replace("\\", "/")
    out: set[str] = set()
    token = re.compile(r"(?<![\w])((?:[A-Za-z]:)?(?:[\w.-]+[/\\])*[\w.-]+\.[A-Za-z0-9]{1,6})(?![\w])")
    for raw in lines[-8000:]:
        if '"tool_use"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        for part in ((entry.get("message") or {}).get("content") or []):
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            payload = part.get("input") or {}
            candidates = [str(payload.get(k) or "") for k in ("file_path", "path", "notebook_path")]
            candidates += token.findall(str(payload.get("command") or ""))
            for candidate in candidates:
                if not candidate:
                    continue
                text = candidate.replace("\\", "/")
                if text.lower().startswith(root.lower()):
                    text = text[len(root):].lstrip("/")
                elif Path(candidate).is_absolute():
                    continue
                if (Path(project) / text).is_file():
                    out.add(_norm(text))
    return out


def _required_paths(project: Path) -> list[str]:
    try:
        from .godmode_corpus import resolve_roles

        resolution = resolve_roles(Path(project))
        return sorted({
            _norm(binding.path.relative_to(resolution.project).as_posix())
            if binding.path.is_absolute() else _norm(binding.path.as_posix())
            for binding in resolution.bindings
        })
    except Exception:
        return []


def required_sources_view(project: Path, archive: Any,
                          transcript_path: str | Path | None = None) -> dict[str, Any]:
    """documents/read/unread/exempted for the bound authority roles.

    A source counts as read when any record cites it (`file:<path>`) - the
    same evidence class every other check trusts. An exemption is a decision
    record `sources-exemption:<path>` whose latest status is not retired or
    closed: the operator's stated "proceeding without this one, and why",
    on the record instead of silently.
    """
    required = _required_paths(project)
    cited: set[str] = set()
    exempt: dict[str, bool] = {}
    try:
        for record in archive.read_events():
            for reference in record.get("evidence") or []:
                text = str(reference)
                if text.startswith("file:"):
                    cited.add(_norm(text[len("file:"):]))
            if record.get("kind") == "decision":
                subject = str(record.get("subject") or "")
                if subject.startswith(EXEMPTION_PREFIX):
                    status = str((record.get("data") or {}).get("status") or "active")
                    exempt[_norm(subject[len(EXEMPTION_PREFIX):])] = (
                        status not in ("retired", "closed"))
    except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
        pass
    cited |= transcript_reads(transcript_path, Path(project))
    exempted = [p for p in required if exempt.get(p)]
    unread = [p for p in required if p not in cited and not exempt.get(p)]
    return {
        "documents": len(required),
        "required": required,
        "read": len(required) - len(unread),
        "unread": unread,
        "exempted": exempted,
    }


def adopt_from_docs(archive: Any, project: Path) -> dict[str, Any]:
    """Seed a late install (obligation 4097): one counts-only decision record
    per bound authority document - headings, bullets, lines, a content digest,
    `file:` evidence - so the brief, the ranking, and the required-sources
    counter start populated on day one instead of blank. Idempotent: an
    unchanged digest writes nothing; a changed document writes a fresh record.
    Never stores the document's prose - the file stays the source of truth.
    """
    project = Path(project)
    existing: dict[str, str] = {}
    try:
        for record in archive.read_events():
            if record.get("kind") != "decision":
                continue
            subject = str(record.get("subject") or "")
            if subject.startswith(ADOPTED_PREFIX):
                existing[subject[len(ADOPTED_PREFIX):]] = str(
                    (record.get("data") or {}).get("digest") or "")
    except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
        pass
    adopted: list[str] = []
    unchanged: list[str] = []
    missing: list[str] = []
    for rel in _required_paths(project):
        target = project / rel
        if not target.is_file():
            missing.append(rel)
            continue
        try:
            raw = target.read_bytes()[:_MAX_DOC_BYTES]
        except OSError:
            missing.append(rel)
            continue
        digest = hashlib.sha256(raw).hexdigest()[:12]
        if existing.get(rel) == digest:
            unchanged.append(rel)
            continue
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        archive.append(
            "decision",
            f"{ADOPTED_PREFIX}{rel}",
            {
                "status": "active",
                "value": "adopted at install: counts only; the document itself "
                         "stays the single source of truth",
                "lines": len(lines),
                "headings": sum(1 for line in lines if line.lstrip().startswith("#")),
                "bullets": sum(1 for line in lines if line.lstrip()[:2] in ("- ", "* ")),
                "digest": digest,
            },
            evidence=[f"file:{rel}"],
        )
        adopted.append(rel)
    return {
        "adopted": adopted,
        "unchanged": unchanged,
        "missing": missing,
        "note": "counts and digests only; re-run after a document changes",
    }


def _salient_words(text: str) -> set[str]:
    words = set()
    for token in str(text).split():
        stripped = token.strip(".,;:'\"()[]`").lower()
        if len(stripped) >= 5:
            words.add(stripped)
    return words


def guard_pin_reason(project: Path, archive: Any, text: str,
                     citations: list[str]) -> str:
    """Obligation 4166: before a gap claim grades verified, look for the pin.

    A test that names the cited surface but is not itself cited, or an active
    lesson whose subject/guard shares the claim's vocabulary, means the "gap"
    may be a deliberate decision with a guard standing on it - the answer is
    that pin's provenance, not a fix. Returns the downgrade reason, or ""
    when no pin is found. Bounded: first matching test file wins, lessons
    scanned via the archive's own bounded select.
    """
    cited_norm = {_norm(str(c)[len("file:"):]) for c in citations
                  if str(c).startswith("file:")}
    surfaces: list[str] = []
    for path in cited_norm:
        name = path.rsplit("/", 1)[-1]
        if not (name.startswith("test_") or name.endswith("_test.py")
                or ".test." in name or "/tests/" in f"/{path}"):
            surfaces.append(name)
    pins: list[str] = []
    tests_dir = Path(project) / "tests"
    if surfaces and tests_dir.is_dir():
        for count, test_file in enumerate(sorted(tests_dir.rglob("*.py"))):
            if count >= _MAX_TEST_FILES:
                break
            rel = _norm(test_file.relative_to(project).as_posix())
            if rel in cited_norm:
                continue
            try:
                body = test_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hit = next((s for s in surfaces if s in body), None)
            if hit:
                pins.append(f"tests: {rel} names {hit}")
                break
    claim_words = _salient_words(text)
    if claim_words:
        try:
            for record in archive.select(kind="lesson", limit=200):
                data = record.get("data") or {}
                if str(data.get("status", "active")) in ("retired", "candidate"):
                    continue
                lesson_words = _salient_words(
                    f"{record.get('subject', '')} {data.get('generalized_guard', '')}")
                if len(claim_words & lesson_words) >= 3:
                    pins.append(
                        f"lesson seq:{record.get('sequence')} "
                        f"({str(record.get('subject', ''))[:60]})")
                    break
        except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
            pass
    if not pins:
        return ""
    return ("a pin already names this surface (" + "; ".join(pins[:2]) +
            ") - answer its provenance (is the gap deliberate?) before "
            "grading a gap verified; cite the pin or retire it first")

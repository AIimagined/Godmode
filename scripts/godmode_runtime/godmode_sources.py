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
    return str(path).replace("\\", "/").lstrip("./")


def _fold(path: Any) -> str:
    """The comparison key. Grok field report 2026-09-10: `Agents.md` and
    `AGENTS.md` are one file on Windows and read as two here; the key folds
    case there while every displayed path keeps the file's own spelling."""
    text = _norm(path)
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
    root = os.path.realpath(str(project)).replace("\\", "/")
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
                # CI 2026-09-11 (Windows and macOS runners): the transcript
                # spells the project through its short name (RUNNER~1) or
                # its symlinked temp root (/var -> /private/var), the
                # resolved root does not, and every read went uncredited.
                # Absolute candidates are resolved the same way the root is.
                if Path(candidate).is_absolute():
                    try:
                        candidate = os.path.realpath(candidate)
                    except (OSError, ValueError):  # godmode: swallow-ok: an unresolvable path keeps its own spelling
                        pass
                text = candidate.replace("\\", "/")
                if text.lower().startswith(root.lower()):
                    text = text[len(root):].lstrip("/")
                elif Path(candidate).is_absolute():
                    continue
                if (Path(project) / text).is_file():
                    out.add(_fold(text))
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
                    cited.add(_fold(text[len("file:"):]))
            if record.get("kind") == "decision":
                subject = str(record.get("subject") or "")
                if subject.startswith(EXEMPTION_PREFIX):
                    status = str((record.get("data") or {}).get("status") or "active")
                    exempt[_fold(subject[len(EXEMPTION_PREFIX):])] = (
                        status not in ("retired", "closed"))
    except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
        pass
    cited |= transcript_reads(transcript_path, Path(project))
    exempted = [p for p in required if exempt.get(_fold(p))]
    unread = [p for p in required if _fold(p) not in cited and not exempt.get(_fold(p))]
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


#: A lesson in any of these states is not a standing pin. The settled set is
#: the archive's own, imported rather than re-spelled so the two cannot drift;
#: `candidate` joins it because a lesson not yet promoted is not a ruling.
from .godmode_constants import SETTLED_STATUSES  # noqa: E402

_SETTLED_OR_CANDIDATE = frozenset(SETTLED_STATUSES) | {"candidate"}


def _salient_words(text: str) -> set[str]:
    words = set()
    for token in str(text).split():
        stripped = token.strip(".,;:'\"()[]`").lower()
        if len(stripped) >= 5:
            words.add(stripped)
    return words


#: Fix round 1 on H5: a bare word-length filter turned every ordinary word
#: in a `cmd:`/prose citation into a "stem" - `cmd:python -m unittest
#: tests.x` yielded {python, tests, unittest}, capping on lessons that
#: shared nothing but generic vocabulary. These names never identify a
#: particular surface even when they carry path structure elsewhere in a
#: token (`origin/main`, `tests/`), so they are dropped after extraction
#: rather than trusted to mean anything on their own.
_STOP_STEMS = frozenset({
    "git", "python", "python3", "tests", "test", "main", "master",
    "origin", "scripts", "src", "docs", "run", "cmd", "sh", "exec",
})


def _path_stems(path: str) -> set[str]:
    """A `file:` citation's own basename (without extension) and its
    immediate parent directory only - every ancestor above that is
    dropped, so `scripts/godmode_runtime/godmode_sentinel.py` ->
    {'godmode_sentinel', 'godmode_runtime'}, not 'scripts'."""
    parts = [p for p in str(path).replace("\\", "/").split("/") if p]
    stems: set[str] = set()
    if parts:
        basename = parts[-1].split(".")[0].strip("-")
        if len(basename) >= 3:
            stems.add(basename.lower())
        if len(parts) >= 2:
            parent = parts[-2].split(".")[0].strip("-")
            if len(parent) >= 3:
                stems.add(parent.lower())
    return stems - _STOP_STEMS


def _structural_stems(text: str) -> set[str]:
    """Tokens that carry path or identifier structure - contain `/`, `.`,
    `_`, or `-` - kept whole with any extension stripped; a plain word
    carries no such structure and is never a stem. That is what keeps a
    claim and a lesson that merely share vocabulary (both mention "tests",
    both mention "main") from reading as the same surface. Used for a
    lesson's own subject/guard text, for every `cmd:` citation token after
    the command name, and for any citation kind this module does not
    otherwise special-case."""
    stems: set[str] = set()
    for raw in str(text).split():
        token = raw.strip(".,;:'\"()[]`")
        if not token or not any(ch in token for ch in "/._-"):
            continue
        candidate = token.split(".")[0].strip("-")
        if len(candidate) >= 3:
            stems.add(candidate.lower())
    return stems - _STOP_STEMS


def _cmd_stems(text: str) -> set[str]:
    """A `cmd:` citation's command name plus every later token that
    carries path or identifier structure, kept whole (not path-split):
    `git rev-parse origin/main` -> {'rev-parse', 'origin/main'} - 'git' is
    too generic to survive the stop-set, and 'origin/main' stays one
    compound stem rather than splitting into 'origin' and 'main', both of
    which are themselves too generic to mean anything alone."""
    tokens = str(text).split()
    stems: set[str] = set()
    if tokens:
        first = tokens[0].split(".")[0].strip("-")
        if len(first) >= 3:
            stems.add(first.lower())
    stems |= _structural_stems(" ".join(tokens[1:]))
    return stems - _STOP_STEMS


def _citation_stems(citation: str) -> set[str]:
    """Dispatches one raw citation to the tokenizer that matches its
    kind: a `file:` citation to its own path shape (`_path_stems`), a
    `cmd:` citation to its command shape (`_cmd_stems`), and any other
    kind to the same structural-token rule the lesson side uses."""
    text = str(citation)
    if text.startswith("file:"):
        return _path_stems(text[len("file:"):])
    if text.startswith("cmd:"):
        return _cmd_stems(text[len("cmd:"):])
    return _structural_stems(text.split(":", 1)[-1])


#: The prefix that marks a `guard_pin_reason` result as informational only:
#: a shared-vocabulary lesson was found, but it names no cited path or
#: command stem, so it must never downgrade a grade. Exported so
#: `godmode_attest.py` checks the same literal string rather than a second
#: copy that could quietly drift out of sync with a rewording here.
PIN_ADVISORY_PREFIX = "advisory:"


def guard_pin_reason(project: Path, archive: Any, text: str,
                     citations: list[str]) -> str:
    """Obligation 4166 / H5: before a gap claim grades verified, look for
    the pin.

    A test that names the cited surface but is not itself cited caps the
    claim outright, same as before. For a lesson, relevance is a shared
    cited path or command stem (`_citation_stems` vs. `_structural_stems`
    on the lesson's own subject/guard) - vocabulary alone no longer caps.
    Three returns are possible: "" when no pin is found; the downgrade
    reason (starts with "a pin already names this surface") when a test or
    a stem-relevant lesson pins the surface, which the caller must treat
    as a hard cap; or a `PIN_ADVISORY_PREFIX`-prefixed string when an
    active lesson merely shares the claim's vocabulary with no cited stem
    in common - this is informational only and the caller must NOT
    downgrade on it (it may still be worth surfacing as a note). Bounded:
    first matching test file wins, lessons scanned via the archive's own
    bounded select.
    """
    cited_norm = {_fold(str(c)[len("file:"):]) for c in citations
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
            rel = _fold(test_file.relative_to(project).as_posix())
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
    advisories: list[str] = []
    claim_words = _salient_words(text)
    if claim_words or citations:
        try:
            cite_stems = (set().union(*(_citation_stems(c) for c in citations))
                          if citations else set())
            records = list(archive.select(kind="lesson", limit=200))
            # The newest record for a subject decides its status, the same
            # supersession every other kind in this archive relies on. Reading
            # each record's own status made retirement unreachable: records are
            # append-only, so a later record marking a lesson retired left the
            # original active and still pinning, and the refusal's own
            # instruction - "retire it first" - named an action with no
            # implementation. Any surface a lesson ever touched could then
            # never be graded verified again.
            newest_status: dict[str, tuple[int, str]] = {}
            for record in records:
                subject = str(record.get("subject", ""))
                sequence = int(record.get("sequence") or 0)
                status = str((record.get("data") or {}).get("status", "active"))
                if subject not in newest_status or sequence >= newest_status[subject][0]:
                    newest_status[subject] = (sequence, status)

            for record in records:
                data = record.get("data") or {}
                subject = str(record.get("subject", ""))
                status = newest_status.get(subject, (0, "active"))[1]
                # `candidate` joins the settled set here: a lesson not yet
                # promoted is not a standing pin either.
                if status in _SETTLED_OR_CANDIDATE:
                    continue
                lesson_text = f"{record.get('subject', '')} {data.get('generalized_guard', '')}"
                lesson_words = _salient_words(lesson_text)
                lesson_stems = _structural_stems(lesson_text)
                if cite_stems & lesson_stems:
                    pins.append(
                        f"lesson seq:{record.get('sequence')} "
                        f"({str(record.get('subject', ''))[:60]})")
                    break
                if len(claim_words & lesson_words) >= 3:
                    advisories.append(
                        f"lesson seq:{record.get('sequence')} "
                        f"({str(record.get('subject', ''))[:60]})")
        except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
            pass
    if pins:
        return ("a pin already names this surface (" + "; ".join(pins[:2]) +
                ") - answer its provenance (is the gap deliberate?) before "
                "grading a gap verified; cite the pin or retire it first")
    if advisories:
        return (f"{PIN_ADVISORY_PREFIX} related lessons by vocabulary only (" +
                "; ".join(advisories[:2]) +
                ") - not a cap; read them if the surface is the same")
    return ""

"""A derived, disposable SQLite index that refuses to answer for a stale world.

The archive's record files and the project's authority documents are the truth;
re-reading and re-ranking all of them on every lookup is the cost. This index
pays that cost once per rebuild and answers from `index.db` afterwards - but a
cache that silently outlives its sources is worse than no cache, because a later
session will trust it. So every read first proves the sources have not moved
(record count plus a content hash over the corpus) and raises `IndexStale`
otherwise: the caller either rebuilds or opts into staleness explicitly and is
handed `"stale": True` alongside the results. Deleting `index.db` loses nothing;
`rebuild()` regenerates it byte-for-byte from the live sources.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from .godmode_charter import compile_charter
from .godmode_chronicle import Chronicle
from .godmode_corpus import fts5_available, resolve_roles, segment_document
from .godmode_errors import GodmodeError


def _uri_escape(text: str) -> str:
    """Percent-escape for a sqlite file: URI without importing urllib.

    The privacy guard forbids network-client imports in the runtime, and
    urllib.parse trips it even though only string escaping is wanted. The URI
    grammar needs %, ?, and # escaped; everything else passes through.
    """
    return text.replace("%", "%25").replace("?", "%3F").replace("#", "%23")

INDEX_FILENAME = "index.db"
INDEX_SCHEMA_VERSION = 1

# The archive caps select() at 500; the index mirrors that ceiling rather than
# inventing a larger window the underlying reader cannot serve.
_RECORD_LIMIT = 500


class IndexStale(GodmodeError):
    """A read consulted an index older than the sources it summarises."""


def _index_path(archive: Chronicle) -> Path:
    return archive.root / INDEX_FILENAME


def _configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")


def _connect_rw(archive: Chronicle) -> sqlite3.Connection:
    archive.root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(_index_path(archive)))
    _configure(connection)
    return connection


def _connect_ro(archive: Chronicle) -> sqlite3.Connection:
    # mode=ro is load-bearing: a query must not be able to heal or mutate the
    # index as a side effect, or staleness checks would race their own reads.
    uri = f"file:{_uri_escape(_index_path(archive).as_posix())}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _source_generation(archive: Chronicle, project: Path) -> dict[str, Any]:
    """Fingerprint of everything the index is derived from.

    Two components, deliberately cheap: the archive is append-only so its record
    count only ever moves forward, and the corpus is a handful of documents whose
    content hash changes on any edit, rename or rebind. Together they cover every
    input rebuild() reads.
    """
    parts: list[str] = []
    for binding in resolve_roles(project).bindings:
        try:
            digest = hashlib.sha256(binding.path.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        parts.append(f"{binding.role}\x00{binding.path.as_posix()}\x00{digest}")
    corpus = hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()
    return {"records": len(archive.event_paths()), "corpus": corpus}


_SCHEMA = (
    "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE segments("
    "  id INTEGER PRIMARY KEY,"
    "  role TEXT NOT NULL,"
    "  path TEXT NOT NULL,"
    "  start_line INTEGER NOT NULL,"
    "  end_line INTEGER NOT NULL,"
    "  weight REAL NOT NULL,"
    "  body TEXT NOT NULL)",
    "CREATE TABLE rules("
    "  id TEXT PRIMARY KEY,"
    "  role TEXT NOT NULL,"
    "  path TEXT NOT NULL,"
    "  line INTEGER NOT NULL,"
    "  text TEXT NOT NULL,"
    "  trigger TEXT NOT NULL,"
    "  enforcement TEXT NOT NULL,"
    "  verify TEXT NOT NULL)",
    "CREATE TABLE attestations("
    "  sequence INTEGER PRIMARY KEY,"
    "  session TEXT NOT NULL,"
    "  subject TEXT NOT NULL,"
    "  status TEXT NOT NULL)",
    "CREATE TABLE claims("
    "  sequence INTEGER PRIMARY KEY,"
    "  session TEXT NOT NULL,"
    "  grade TEXT NOT NULL,"
    "  downgraded INTEGER NOT NULL)",
    "CREATE TABLE sessions("
    "  id TEXT PRIMARY KEY,"
    "  label TEXT NOT NULL,"
    "  opened_at TEXT NOT NULL)",
)

_DROPS = (
    "DROP TABLE IF EXISTS seg_fts",
    "DROP TABLE IF EXISTS segments",
    "DROP TABLE IF EXISTS rules",
    "DROP TABLE IF EXISTS attestations",
    "DROP TABLE IF EXISTS claims",
    "DROP TABLE IF EXISTS sessions",
    "DROP TABLE IF EXISTS meta",
)


def rebuild(archive: Chronicle, project: Path) -> dict[str, Any]:
    """Drop everything and repopulate from the live sources.

    Wholesale replacement instead of incremental patching: the index has no
    authority of its own, so the only defensible content is a fresh projection.
    An incremental path would need its own correctness argument and would still
    have to be distrusted by fresh().
    """
    generation = _source_generation(archive, project)
    resolution = resolve_roles(project)
    charter = compile_charter(project)

    connection = _connect_rw(archive)
    try:
        with connection:
            for statement in _DROPS:
                connection.execute(statement)
            for statement in _SCHEMA:
                connection.execute(statement)

            scorer = "fts5-bm25" if fts5_available() else "like-fallback"
            if scorer == "fts5-bm25":
                # External-content: bodies live once, in segments; FTS holds
                # only the inverted index over them.
                connection.execute(
                    "CREATE VIRTUAL TABLE seg_fts USING fts5("
                    "body, content='segments', content_rowid='id',"
                    " tokenize='unicode61')"
                )

            segment_count = 0
            for binding in resolution.bindings:
                for segment in segment_document(binding, resolution.project):
                    segment_count += 1
                    connection.execute(
                        "INSERT INTO segments"
                        "(id, role, path, start_line, end_line, weight, body)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            segment_count,
                            segment.role,
                            segment.path,
                            segment.start_line,
                            segment.end_line,
                            segment.weight,
                            segment.body,
                        ),
                    )
                    if scorer == "fts5-bm25":
                        connection.execute(
                            "INSERT INTO seg_fts(rowid, body) VALUES (?, ?)",
                            (segment_count, segment.body),
                        )

            for rule in charter["compiled"]:
                path, _, line = rule["source"].rpartition(":")
                connection.execute(
                    "INSERT OR REPLACE INTO rules"
                    "(id, role, path, line, text, trigger, enforcement, verify)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rule["id"], rule["role"], path, int(line or 0),
                        rule["text"], rule["trigger"], rule["enforcement"],
                        rule["verify"],
                    ),
                )

            attestation_count = 0
            for record in archive.select(kind="attestation", limit=_RECORD_LIMIT):
                attestation_count += 1
                connection.execute(
                    "INSERT INTO attestations(sequence, session, subject, status)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        record["sequence"],
                        str(record["data"].get("session", "")),
                        record["subject"],
                        str(record["data"].get("status", "")),
                    ),
                )

            claim_count = 0
            for record in archive.select(kind="claim", limit=_RECORD_LIMIT):
                claim_count += 1
                connection.execute(
                    "INSERT INTO claims(sequence, session, grade, downgraded)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        record["sequence"],
                        str(record["data"].get("session", "")),
                        str(record["data"].get("grade", "unknown")),
                        1 if record["data"].get("downgraded") else 0,
                    ),
                )

            session_count = 0
            for record in archive.select(kind="session", limit=_RECORD_LIMIT):
                session_count += 1
                connection.execute(
                    "INSERT OR REPLACE INTO sessions(id, label, opened_at)"
                    " VALUES (?, ?, ?)",
                    (
                        f"S-{record['record_hash'][:12]}",
                        record["subject"],
                        str(record.get("recorded_at", "")),
                    ),
                )

            connection.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", str(INDEX_SCHEMA_VERSION)),
            )
            connection.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("source_generation", json.dumps(generation, sort_keys=True)),
            )
            connection.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)", ("scorer", scorer)
            )
    finally:
        connection.close()

    return {
        "path": str(_index_path(archive)),
        "scorer": scorer,
        "segments": segment_count,
        "rules": len(charter["compiled"]),
        "attestations": attestation_count,
        "claims": claim_count,
        "sessions": session_count,
        "source_generation": generation,
    }


def _stored_meta(archive: Chronicle) -> dict[str, str] | None:
    if not _index_path(archive).is_file():
        return None
    try:
        connection = _connect_ro(archive)
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute("SELECT key, value FROM meta").fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return {str(key): str(value) for key, value in rows}


def fresh(archive: Chronicle, project: Path) -> dict[str, Any]:
    """The mandatory pre-read check: is the index still describing this project?

    The comparison names which input moved, because "stale" alone teaches
    nothing: a grown archive and an edited operating guide call for the same
    rebuild but explain very different worlds.
    """
    meta = _stored_meta(archive)
    if meta is None:
        return {"fresh": False, "reason": "index has never been built"}
    if meta.get("schema_version") != str(INDEX_SCHEMA_VERSION):
        return {"fresh": False, "reason": "index schema is from another runtime"}
    try:
        stored = json.loads(meta.get("source_generation", "{}"))
    except json.JSONDecodeError:
        return {"fresh": False, "reason": "index generation record is unreadable"}
    live = _source_generation(archive, project)
    if stored.get("records") != live["records"]:
        delta = live["records"] - int(stored.get("records") or 0)
        return {
            "fresh": False,
            "reason": f"archive moved by {delta} record(s) since the last rebuild",
        }
    if stored.get("corpus") != live["corpus"]:
        return {
            "fresh": False,
            "reason": "an authority document changed since the last rebuild",
        }
    return {"fresh": True, "reason": "index matches the live sources"}


def _fts_rows(
    connection: sqlite3.Connection, terms: list[str]
) -> dict[int, float]:
    match = " OR ".join(f'"{term}"' for term in terms)
    rows = connection.execute(
        "SELECT rowid, bm25(seg_fts) FROM seg_fts WHERE seg_fts MATCH ?",
        (match,),
    ).fetchall()
    # bm25() is negative, lower is better; flip so higher is better.
    return {int(rowid): -float(score) for rowid, score in rows}


def _like_rows(
    connection: sqlite3.Connection, terms: list[str]
) -> dict[int, float]:
    """Hand-rolled fallback for SQLite builds without FTS5: term hits as score."""
    hits: dict[int, float] = {}
    for term in terms:
        pattern = f"%{term}%"
        for (rowid,) in connection.execute(
            "SELECT id FROM segments WHERE body LIKE ? ESCAPE '\\'",
            (pattern,),
        ):
            hits[int(rowid)] = hits.get(int(rowid), 0.0) + 1.0
    return hits


def _terms(task: str) -> list[str]:
    import re

    seen: dict[str, None] = {}
    for match in re.findall(r"[A-Za-z0-9_]{2,}", task.lower()):
        seen.setdefault(match, None)
    return list(seen)


def query(
    archive: Chronicle,
    project: Path,
    task: str,
    limit: int = 10,
    *,
    allow_stale: bool = False,
) -> dict[str, Any]:
    """Ranked segment lookup from the persisted index.

    The persistent counterpart of corpus.rank: the same weight-times-relevance
    shape, answered from disk instead of a fresh scan. Refuses on a stale index
    unless the caller opts in, and then labels every answer as stale rather than
    letting borrowed confidence travel.
    """
    state = fresh(archive, project)
    if not state["fresh"] and not allow_stale:
        raise IndexStale(
            f"Index is stale ({state['reason']}); run rebuild or pass allow_stale=True"
        )

    terms = _terms(task)
    connection = _connect_ro(archive)
    try:
        scorer = dict(
            connection.execute("SELECT key, value FROM meta").fetchall()
        ).get("scorer", "like-fallback")
        relevance: dict[int, float] = {}
        if terms:
            relevance = (
                _fts_rows(connection, terms)
                if scorer == "fts5-bm25"
                else _like_rows(connection, terms)
            )
        top = max(relevance.values(), default=0.0) or 1.0

        rule_counts = {
            str(path): int(count)
            for path, count in connection.execute(
                "SELECT path, COUNT(*) FROM rules GROUP BY path"
            )
        }

        scored: list[dict[str, Any]] = []
        for row in connection.execute(
            "SELECT id, role, path, start_line, end_line, weight, body"
            " FROM segments"
        ):
            identifier, role, path, start, end, weight, body = row
            # A segment matching nothing still ranks by role weight, mirroring
            # corpus.rank: authority is never invisible to a badly worded task.
            score = round(
                float(weight) * (1.0 + relevance.get(int(identifier), 0.0) / top),
                6,
            )
            scored.append(
                {
                    "role": role,
                    "path": path,
                    "lines": [int(start), int(end)],
                    "score": score,
                    "rules": rule_counts.get(str(path), 0),
                    "body": body,
                }
            )
    finally:
        connection.close()

    scored.sort(key=lambda row: (-row["score"], row["path"], row["lines"][0]))
    return {
        "task": task,
        "scorer": scorer,
        "stale": not state["fresh"],
        "results": scored[: max(1, limit)],
    }


def _self_check() -> None:
    """Smallest check that fails if staleness detection breaks."""
    import os
    import tempfile
    from unittest import mock

    from .godmode_anchor import resolve_anchor

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        (project / "GODMODE.md").write_text(
            "# Tokens\nRefresh token rotation must happen exactly once.\n",
            encoding="utf-8",
        )
        with mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
        ):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()

            counts = rebuild(archive, project)
            assert counts["segments"] >= 1, counts
            assert fresh(archive, project)["fresh"]

            found = query(archive, project, "token rotation")
            assert found["results"], found
            assert not found["stale"]

            archive.append("lesson", "something new", {"detail": "x"})
            assert not fresh(archive, project)["fresh"]
            try:
                query(archive, project, "token rotation")
            except IndexStale:
                pass
            else:  # pragma: no cover - guard for the guard
                raise AssertionError("stale query must refuse without allow_stale")
            assert query(archive, project, "token rotation", allow_stale=True)["stale"]

    print("godmode_index self-check OK")


if __name__ == "__main__":  # pragma: no cover
    _self_check()

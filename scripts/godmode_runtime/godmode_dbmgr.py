"""Read-only database architecture manager: inventory, review, never mutate.

Schema mistakes are the expensive kind of mistake - a dropped column has no
undo and a second source of truth never converges back into one. So this module
holds the pen the wrong way on purpose: it opens every database with mode=ro,
its schema review is a fixed 11-row interrogation that cannot be talked past
("approved" requires zero failures and zero unanswered rows), and its migration
review only reads SQL text and names hazards. Anything that would change a
database happens elsewhere, deliberately, after this module has said its piece.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

from .godmode_constants import DATABASE_SUFFIXES, IGNORED_DIRECTORY_NAMES


def _uri_escape(text: str) -> str:
    """Percent-escape for a sqlite file: URI without importing urllib.

    The privacy guard forbids network-client imports in the runtime, and
    urllib.parse trips it even though only string escaping is wanted. The URI
    grammar needs %, ?, and # escaped; everything else passes through.
    """
    return text.replace("%", "%25").replace("?", "%3F").replace("#", "%23")

_SUFFIXES = frozenset(DATABASE_SUFFIXES | {".sqlite3"})

PASS = "pass"
FAIL = "fail"
NEEDS_INPUT = "needs-input"


def _candidate_files(project: Path) -> list[Path]:
    found: list[Path] = []
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue
        relative = path.relative_to(project)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts[:-1]):
            continue
        found.append(path)
    # Sorted by relative posix path so the inventory is identical across hosts.
    return sorted(found, key=lambda p: p.relative_to(project).as_posix())


def _introspect(path: Path) -> dict[str, Any]:
    # mode=ro is the design, not a convenience: an inventory that could write
    # would turn a survey into a mutation vector on every database it visits.
    uri = f"file:{_uri_escape(path.as_posix())}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables: list[dict[str, Any]] = []
        for name in names:
            columns = [
                {
                    "name": str(row[1]),
                    "type": str(row[2]),
                    "notnull": int(row[3]),
                    "pk": int(row[5]),
                }
                for row in connection.execute(f"PRAGMA table_info({name!r})")
            ]
            indexes = sorted(
                str(row[1])
                for row in connection.execute(f"PRAGMA index_list({name!r})")
            )
            try:
                rows = int(
                    connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                )
            except sqlite3.Error:
                # A virtual table or a corrupt page must not sink the survey.
                rows = -1
            tables.append(
                {"name": name, "columns": columns, "indexes": indexes, "rows": rows}
            )
        return {"status": "ok", "tables": tables}
    except sqlite3.DatabaseError:
        # A .sql script or any non-SQLite bytes land here: reported, not raised,
        # because the finding "this is not a database" is itself inventory.
        return {"status": "not-a-sqlite-database", "tables": []}
    finally:
        connection.close()


def schema_inventory(project: Path) -> dict[str, Any]:
    """Every database-shaped file in the project, introspected without touching it."""
    databases: list[dict[str, Any]] = []
    for path in _candidate_files(project):
        entry: dict[str, Any] = {"path": path.relative_to(project).as_posix()}
        try:
            entry.update(_introspect(path))
        except sqlite3.Error as exc:
            entry.update({"status": f"unreadable: {exc}", "tables": []})
        databases.append(entry)
    return {"databases": databases, "scanned": len(databases)}


def _existing_tables(inventory: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for database in inventory.get("databases", []):
        for table in database.get("tables", []):
            names.add(str(table["name"]))
    return sorted(names)


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def schema_review(inventory: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    """The Mandatory Schema Review: eleven named rows, none skippable.

    Three outcomes per row because two would lie: a proposal that never mentions
    rollback has not failed rollback, it has not answered - except where silence
    is itself the hazard (rollback text), which fails outright. "approved" means
    every row passed; anything less names exactly what is owed.
    """
    checks: list[dict[str, str]] = []
    migration = proposal.get("migration") or {}

    tables = _existing_tables(inventory)
    insufficiency = proposal.get("insufficiency")
    if insufficiency is None:
        checks.append(_check(
            "existing-schema-insufficiency", NEEDS_INPUT,
            "state why each existing table cannot hold this data: "
            + (", ".join(tables) or "(no existing tables found)"),
        ))
    else:
        unexplained = [t for t in tables if not str(insufficiency.get(t, "")).strip()]
        checks.append(
            _check("existing-schema-insufficiency", FAIL,
                   "no insufficiency stated for: " + ", ".join(unexplained))
            if unexplained
            else _check("existing-schema-insufficiency", PASS,
                        "every existing table has a stated reason it cannot serve")
        )

    owner = str(proposal.get("owner", "")).strip()
    checks.append(
        _check("single-source-of-truth", PASS, f"owner: {owner}")
        if owner
        else _check("single-source-of-truth", NEEDS_INPUT,
                    "name the single writer that owns this data")
    )

    consumers = proposal.get("consumers") or []
    checks.append(
        _check("read-before-write-consumers", PASS,
               "consumers: " + ", ".join(str(c) for c in consumers))
        if consumers
        else _check("read-before-write-consumers", NEEDS_INPUT,
                    "list every consumer that reads this data before writes land")
    )

    additive = proposal.get("additive")
    if additive is None:
        checks.append(_check("additive-nullable-compatibility", NEEDS_INPUT,
                             "declare additive: true/false for this change"))
    elif additive:
        checks.append(_check("additive-nullable-compatibility", PASS,
                             "change is declared additive/nullable"))
    else:
        checks.append(_check("additive-nullable-compatibility", FAIL,
                             "non-additive change breaks existing readers"))

    lag = str(proposal.get("lag_tolerance", "")).strip()
    checks.append(
        _check("schema-lag-tolerance", PASS, lag)
        if lag
        else _check("schema-lag-tolerance", NEEDS_INPUT,
                    "state how long old readers may lag behind the new schema")
    )

    idempotent = migration.get("idempotent")
    if idempotent is None:
        checks.append(_check("migration-idempotency", NEEDS_INPUT,
                             "declare whether the migration can run twice safely"))
    elif idempotent:
        checks.append(_check("migration-idempotency", PASS,
                             "migration declared idempotent"))
    else:
        checks.append(_check("migration-idempotency", FAIL,
                             "a migration that cannot re-run safely will, one day, half-run"))

    precheck = str(migration.get("precheck", "")).strip()
    checks.append(
        _check("migration-precheck", PASS, precheck)
        if precheck
        else _check("migration-precheck", NEEDS_INPUT,
                    "declare the check that runs before the migration mutates anything")
    )

    # Rollback is the one row where absence is failure, not a question: by the
    # time rollback text is needed, it is too late to start writing it.
    rollback = str(migration.get("rollback", "")).strip()
    checks.append(
        _check("rollback-present", PASS, "down-migration text present")
        if rollback
        else _check("rollback-present", FAIL,
                    "no rollback/down-migration text; this is mandatory")
    )

    retention = str(proposal.get("retention", "")).strip()
    checks.append(
        _check("retention-privacy", PASS, retention)
        if retention
        else _check("retention-privacy", NEEDS_INPUT,
                    "declare retention and privacy posture for every new column")
    )

    permissions = str(proposal.get("permissions", "")).strip()
    checks.append(
        _check("narrowest-role-permissions", PASS, permissions)
        if permissions
        else _check("narrowest-role-permissions", NEEDS_INPUT,
                    "state the narrowest role that can read and the one that can write")
    )

    impact = str(proposal.get("index_impact", "")).strip()
    checks.append(
        _check("index-hot-table-impact", PASS, impact)
        if impact
        else _check("index-hot-table-impact", NEEDS_INPUT,
                    "state the impact on indexes and hot tables")
    )

    failed = sum(1 for check in checks if check["status"] == FAIL)
    open_rows = sum(1 for check in checks if check["status"] == NEEDS_INPUT)
    verdict = "approved" if not failed and not open_rows else (
        "blocked" if failed else "needs-input"
    )
    return {
        "verdict": verdict,
        "failed": failed,
        "needs_input": open_rows,
        "checks": checks,
    }


_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _statements(sql_text: str) -> list[str]:
    stripped = _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql_text))
    return [
        " ".join(part.split())
        for part in stripped.split(";")
        if part.strip()
    ]


def _finding(check: str, statement: str, detail: str, blocking: bool) -> dict[str, Any]:
    return {
        "check": check,
        "statement": statement[:120],
        "detail": detail,
        "blocking": blocking,
    }


def migration_review(sql_text: str) -> dict[str, Any]:
    """Static hazard scan over migration SQL - names risks, changes nothing.

    Text-level checks only, and honestly so: this is a tripwire for the four
    ways migrations usually hurt (irreversible drops, reader-breaking ALTERs,
    non-idempotent CREATEs, unbounded writes), not a SQL parser. A migration
    passing this review is unremarkable; one failing it should not run.
    """
    has_rollback_comment = re.search(r"--\s*rollback:", sql_text, re.IGNORECASE)
    findings: list[dict[str, Any]] = []

    for statement in _statements(sql_text):
        upper = statement.upper()

        if re.match(r"DROP\s+TABLE\b", upper) or re.search(
            r"\bDROP\s+COLUMN\b", upper
        ):
            if not has_rollback_comment:
                findings.append(_finding(
                    "drop-without-rollback", statement,
                    "a DROP with no paired '-- rollback:' comment is a one-way door",
                    True,
                ))

        if re.match(r"ALTER\s+TABLE\b", upper) and re.search(
            r"\b(DROP|RENAME)\b", upper
        ):
            findings.append(_finding(
                "non-additive-alter", statement,
                "ALTER that drops or renames breaks readers still on the old shape",
                True,
            ))

        if re.match(r"CREATE\s+(TABLE|INDEX|UNIQUE\s+INDEX|VIEW)\b", upper) and \
                "IF NOT EXISTS" not in upper:
            findings.append(_finding(
                "create-not-idempotent", statement,
                "CREATE without IF NOT EXISTS fails on re-run instead of converging",
                False,
            ))

        if re.match(r"DELETE\s+FROM\b", upper) and " WHERE " not in f" {upper} ":
            findings.append(_finding(
                "delete-without-where", statement,
                "DELETE with no WHERE clause empties the table",
                True,
            ))

        if re.match(r"UPDATE\b", upper) and " WHERE " not in f" {upper} ":
            findings.append(_finding(
                "update-without-where", statement,
                "UPDATE with no WHERE clause rewrites every row",
                True,
            ))

    return {
        "findings": findings,
        "blocking": any(finding["blocking"] for finding in findings),
        "statements": len(_statements(sql_text)),
    }


def _self_check() -> None:
    """Smallest check that fails if read-only introspection or review breaks."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        connection = sqlite3.connect(str(project / "app.db"))
        connection.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
        connection.execute("INSERT INTO t(v) VALUES ('x')")
        connection.commit()
        connection.close()
        (project / "schema.sql").write_text("CREATE TABLE t(id);", encoding="utf-8")

        inventory = schema_inventory(project)
        statuses = {d["path"]: d["status"] for d in inventory["databases"]}
        assert statuses == {"app.db": "ok", "schema.sql": "not-a-sqlite-database"}, statuses
        table = inventory["databases"][0]["tables"][0]
        assert table["rows"] == 1 and table["columns"][1]["notnull"] == 1, table

        review = schema_review(inventory, {"additive": True})
        assert review["verdict"] != "approved", review
        rollback = [c for c in review["checks"] if c["name"] == "rollback-present"][0]
        assert rollback["status"] == FAIL, rollback

        hazards = migration_review("DELETE FROM t;\nDROP TABLE t;")
        assert hazards["blocking"], hazards
        assert {f["check"] for f in hazards["findings"]} == {
            "delete-without-where", "drop-without-rollback",
        }, hazards

    print("godmode_dbmgr self-check OK")


if __name__ == "__main__":  # pragma: no cover
    _self_check()

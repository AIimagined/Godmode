"""Guards for the derived SQLite index and the read-only database manager.

The index is a disposable cache over the immutable archive and the live corpus;
the property under test is honesty, not speed: a stale index must refuse to
answer rather than serve yesterday's project, and the database manager must
never open anything writable while it inventories or reviews a schema.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import (  # noqa: E402
    open_session,
    record_claim,
    record_step,
)
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_dbmgr import (  # noqa: E402
    migration_review,
    schema_inventory,
    schema_review,
)
from godmode_runtime.godmode_index import (  # noqa: E402
    IndexStale,
    fresh,
    query,
    rebuild,
)


@contextmanager
def isolated_project():
    """A temp project with a bound corpus and a private archive, like production."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        (project / "docs").mkdir(parents=True)
        (project / "GODMODE.md").write_text(
            "# Gates\n"
            "Never commit without an explicit ask.\n\n"
            "# Tokens\n"
            "Refresh token rotation must happen exactly once.\n",
            encoding="utf-8",
        )
        (project / "docs" / "LESSONS.md").write_text(
            "# L-001\nA status label is not evidence.\n", encoding="utf-8"
        )
        with mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False
        ):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


class IndexTests(unittest.TestCase):
    def test_rebuild_populates_and_query_returns_ranked_rows(self) -> None:
        with isolated_project() as (project, archive):
            session = open_session(archive, "index-test")
            record_step(archive, session, "registry-scan", "ran", result="clean")
            record_claim(
                archive, project, session, "the registry is clean", "verified"
            )

            counts = rebuild(archive, project)
            self.assertGreater(counts["segments"], 0)
            self.assertGreater(counts["rules"], 0)
            self.assertEqual(counts["sessions"], 1)
            self.assertEqual(counts["attestations"], 1)
            self.assertEqual(counts["claims"], 1)
            self.assertTrue((archive.root / "index.db").is_file())

            state = fresh(archive, project)
            self.assertTrue(state["fresh"], state)

            result = query(archive, project, "refresh token rotation")
            self.assertFalse(result["stale"])
            self.assertTrue(result["results"], result)
            top = result["results"][0]
            # The token segment must outrank the unrelated gates segment.
            self.assertIn("token", top["body"].lower())
            self.assertEqual(top["path"], "GODMODE.md")
            # Every row is joined with the rule count of its source document.
            self.assertGreaterEqual(top["rules"], 1)
            scores = [row["score"] for row in result["results"]]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_rebuild_is_idempotent_and_deterministic(self) -> None:
        with isolated_project() as (project, archive):
            first = rebuild(archive, project)
            second = rebuild(archive, project)
            self.assertEqual(first["segments"], second["segments"])
            once = query(archive, project, "refresh token rotation")
            again = query(archive, project, "refresh token rotation")
            self.assertEqual(once["results"], again["results"])

    def test_stale_index_refuses_reads_unless_explicitly_allowed(self) -> None:
        with isolated_project() as (project, archive):
            rebuild(archive, project)
            self.assertTrue(fresh(archive, project)["fresh"])

            # A new archive record makes the index a summary of a past project.
            archive.append("lesson", "post-rebuild lesson", {"detail": "late"})

            state = fresh(archive, project)
            self.assertFalse(state["fresh"])
            self.assertIn("record", state["reason"])

            with self.assertRaises(IndexStale):
                query(archive, project, "refresh token rotation")

            tolerated = query(
                archive, project, "refresh token rotation", allow_stale=True
            )
            self.assertTrue(tolerated["stale"])
            self.assertTrue(tolerated["results"])

    def test_corpus_edit_also_invalidates_the_index(self) -> None:
        with isolated_project() as (project, archive):
            rebuild(archive, project)
            (project / "GODMODE.md").write_text(
                "# Tokens\nRotation policy changed entirely.\n", encoding="utf-8"
            )
            state = fresh(archive, project)
            self.assertFalse(state["fresh"])
            self.assertIn("document", state["reason"])

    def test_never_built_index_reports_unfresh_not_crash(self) -> None:
        with isolated_project() as (project, archive):
            state = fresh(archive, project)
            self.assertFalse(state["fresh"])
            with self.assertRaises(IndexStale):
                query(archive, project, "anything")


class DbmgrInventoryTests(unittest.TestCase):
    def test_inventory_introspects_sqlite_read_only_and_reports_impostors(self) -> None:
        with isolated_project() as (project, _archive):
            db_path = project / "app.db"
            connection = sqlite3.connect(str(db_path))
            try:
                connection.execute(
                    "CREATE TABLE users("
                    "id INTEGER PRIMARY KEY, email TEXT NOT NULL)"
                )
                connection.execute("CREATE INDEX idx_users_email ON users(email)")
                connection.executemany(
                    "INSERT INTO users(email) VALUES (?)",
                    [("a@example.test",), ("b@example.test",)],
                )
                connection.commit()
            finally:
                connection.close()
            (project / "notes.sql").write_text(
                "CREATE TABLE scratch(id INTEGER);\n", encoding="utf-8"
            )

            inventory = schema_inventory(project)
            by_path = {entry["path"]: entry for entry in inventory["databases"]}
            self.assertIn("app.db", by_path)
            self.assertIn("notes.sql", by_path)
            self.assertEqual(by_path["notes.sql"]["status"], "not-a-sqlite-database")

            app = by_path["app.db"]
            self.assertEqual(app["status"], "ok")
            users = {table["name"]: table for table in app["tables"]}["users"]
            self.assertEqual(users["rows"], 2)
            columns = {column["name"]: column for column in users["columns"]}
            self.assertEqual(columns["email"]["notnull"], 1)
            self.assertEqual(columns["id"]["pk"], 1)
            self.assertIn("idx_users_email", users["indexes"])

            # Deterministic ordering is part of the contract.
            paths = [entry["path"] for entry in inventory["databases"]]
            self.assertEqual(paths, sorted(paths))


class DbmgrReviewTests(unittest.TestCase):
    def _proposal(self) -> dict:
        return {
            "insufficiency": {"users": "users has no audit trail column"},
            "owner": "godmode_index.rebuild",
            "consumers": ["godmode_index.query"],
            "additive": True,
            "lag_tolerance": "readers tolerate one rebuild cycle of lag",
            "migration": {
                "idempotent": True,
                "precheck": "SELECT COUNT(*) FROM users",
                "rollback": "DROP TABLE audit_log; -- restores prior schema",
            },
            "retention": "audit rows kept 90 days, no personal data",
            "permissions": "read-only for consumers, writer owns DDL",
            "index_impact": "new table, no hot-table index touched",
        }

    def _inventory(self) -> dict:
        return {
            "databases": [
                {
                    "path": "app.db",
                    "status": "ok",
                    "tables": [{"name": "users", "columns": [], "indexes": [], "rows": 0}],
                }
            ]
        }

    def test_complete_proposal_is_approved(self) -> None:
        review = schema_review(self._inventory(), self._proposal())
        self.assertEqual(review["verdict"], "approved")
        self.assertEqual(len(review["checks"]), 11)
        self.assertTrue(all(c["status"] == "pass" for c in review["checks"]))

    def test_missing_rollback_is_a_hard_fail_not_a_question(self) -> None:
        proposal = self._proposal()
        del proposal["migration"]["rollback"]
        review = schema_review(self._inventory(), proposal)
        self.assertNotEqual(review["verdict"], "approved")
        rollback = {c["name"]: c for c in review["checks"]}["rollback-present"]
        self.assertEqual(rollback["status"], "fail")

    def test_unstated_insufficiency_needs_input_rather_than_guessing(self) -> None:
        proposal = self._proposal()
        del proposal["insufficiency"]
        review = schema_review(self._inventory(), proposal)
        self.assertEqual(review["verdict"], "needs-input")
        check = {c["name"]: c for c in review["checks"]}[
            "existing-schema-insufficiency"
        ]
        self.assertEqual(check["status"], "needs-input")


class MigrationReviewTests(unittest.TestCase):
    def test_delete_without_where_blocks(self) -> None:
        review = migration_review("DELETE FROM users;")
        self.assertTrue(review["blocking"])
        self.assertTrue(
            any("WHERE" in finding["detail"] for finding in review["findings"])
        )

    def test_drop_without_rollback_comment_blocks(self) -> None:
        review = migration_review("DROP TABLE users;")
        self.assertTrue(review["blocking"])
        paired = migration_review(
            "-- rollback: CREATE TABLE users(id INTEGER PRIMARY KEY);\n"
            "DROP TABLE users;"
        )
        self.assertFalse(
            any(f["check"] == "drop-without-rollback" for f in paired["findings"])
        )

    def test_create_without_if_not_exists_is_flagged_not_blocking(self) -> None:
        review = migration_review("CREATE TABLE audit(id INTEGER);")
        names = {finding["check"] for finding in review["findings"]}
        self.assertIn("create-not-idempotent", names)
        self.assertFalse(review["blocking"])

    def test_additive_idempotent_migration_is_clean(self) -> None:
        review = migration_review(
            "CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY);\n"
            "ALTER TABLE users ADD COLUMN note TEXT;\n"
            "UPDATE users SET note = '' WHERE note IS NULL;"
        )
        self.assertEqual(review["findings"], [])
        self.assertFalse(review["blocking"])


if __name__ == "__main__":
    unittest.main()

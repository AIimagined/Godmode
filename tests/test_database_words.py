"""A word is not a database.

Reported from another project using the plugin: `git restore out/` refused as a
**database mutation**. The rule matched `drop`, `truncate`, `migrate`,
`migration`, `rollback` and `restore` as bare words, anywhere they appeared.

Reproducing it found worse than was reported. `cat docs/migrate-notes.md` and
`grep -rn rollback src/` were also refused as database mutations — a file read
and a search, reported as schema changes. And the genuine article escaped:
the SQL in `psql -c 'DROP TABLE orders'` is quoted, quoted spans are blanked
before these patterns run, so it fell through to unclassified. The rule refused
prose and missed the statement.

A refusal that names the wrong thing costs more than a slow one. The reader
learns the tool does not understand the command, and starts routing around it —
which is what that session did, and what it proposed to the operator as the
remedy.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


class Case(unittest.TestCase):
    def verdict(self, command: str) -> dict:
        return classify_action(command, project_root=PLUGIN_ROOT)

    def allowed(self, command: str) -> None:
        verdict = self.verdict(command)
        self.assertFalse(verdict["protected"],
                         f"refused a read: {command} -> {verdict['category']}")

    def refused(self, command: str, category: str | None = None) -> None:
        verdict = self.verdict(command)
        self.assertTrue(verdict["protected"], f"permitted: {command}")
        if category:
            self.assertEqual(verdict["category"], category, command)


class EnglishIsNotSchemaTests(Case):
    """The words that were matched anywhere they appeared."""

    def test_reading_a_file_whose_name_contains_migrate(self) -> None:
        self.allowed("cat docs/migrate-notes.md")

    def test_searching_for_the_word_rollback(self) -> None:
        self.allowed("grep -rn rollback src/")

    def test_listing_a_migrations_directory(self) -> None:
        self.allowed("ls db/migrations")

    def test_reading_a_file_about_restoring(self) -> None:
        self.allowed("cat RESTORE.md")

    def test_a_branch_named_for_a_migration(self) -> None:
        self.allowed("git log --oneline feature/migrate-users")


class RealDatabaseWorkTests(Case):
    """What the category is actually for."""

    def test_sql_that_names_what_it_drops(self) -> None:
        for command in ("DROP TABLE orders", "drop database analytics",
                        "TRUNCATE TABLE events", "DELETE FROM users",
                        "ALTER TABLE orders ADD COLUMN x int"):
            with self.subTest(command=command):
                self.refused(command, "database-mutation")

    def test_a_migration_tool_running_a_migration(self) -> None:
        for command in ("alembic upgrade head",
                        "alembic downgrade -1",
                        "prisma migrate deploy",
                        "flyway migrate",
                        "knex migrate:latest",
                        "python manage.py migrate",
                        "rails db:migrate"):
            with self.subTest(command=command):
                self.refused(command, "database-mutation")

    def test_a_drop_still_escalates(self) -> None:
        self.assertEqual(self.verdict("DROP TABLE orders")["tier"], "R5")

    def test_a_bare_verb_with_no_database_in_sight_is_not_a_schema_change(self) -> None:
        """`migrate` alone is a word. Requiring the tool to be named is what
        stopped a filename from being a schema change."""
        verdict = self.verdict("cat notes-about-migrate.txt")
        self.assertNotEqual(verdict["category"], "database-mutation")


class WorktreeDiscardTests(Case):
    """`git restore` throws away uncommitted work. Worth stopping — under its
    own name, not the database's."""

    def test_git_restore_is_protected(self) -> None:
        self.refused("git restore out/", "worktree-discard")
        self.refused("git restore .", "worktree-discard")

    def test_git_restore_staged_is_protected(self) -> None:
        self.refused("git restore --staged src/app.py", "worktree-discard")

    def test_the_impact_names_the_work_at_risk(self) -> None:
        impact = " ".join(self.verdict("git restore .")["impact"])
        self.assertIn("uncommitted", impact)

    def test_discarding_through_checkout_is_still_protected(self) -> None:
        """The neighbouring form, unchanged by this."""
        self.refused("git checkout -- .")


class ReportedSessionTests(Case):
    """The commands that session said worked, kept so a later tightening has
    to argue with a test."""

    def test_a_loop_over_directories_is_a_read(self) -> None:
        self.allowed("for d in specs/*/; do echo $d; done")
        self.allowed("for d in specs/*/; do cat $d/spec.md; done")

    def test_the_commands_it_fell_back_to_still_pass(self) -> None:
        self.allowed("npm test")
        self.allowed("node frames.js")


if __name__ == "__main__":
    unittest.main()

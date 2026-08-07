"""Stable Godmode runtime constants."""

from __future__ import annotations

PRODUCT = "Godmode"
RUNTIME_VERSION = "0.2.3"
SCHEMA_VERSION = 1
ARCHIVE_DIRNAME = "godmode-state"
MAX_HASH_BYTES = 5 * 1024 * 1024
DEFAULT_CONTEXT_BUDGET = 1_200
DEFAULT_RECORD_LIMIT = 24

EVENT_KINDS = frozenset(
    {
        "action", "attestation", "branch", "change", "checklist", "checkpoint",
        "claim", "database", "decision", "documentation", "incident", "invariant",
        "inventory", "lesson", "obligation", "plan", "session", "sprint", "version",
    }
)

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git", ".hg", ".svn", ".godmode", ".godmode-private",
        ".godmode-state", ".research", ".planning", ".sprints",
        ".checkpoints", ".handovers", ".evidence", ".decisions", ".lessons",
        "node_modules", "coverage", "dist", "build", "target", "__pycache__",
        ".venv", "venv",
    }
)

MANIFEST_NAMES = frozenset(
    {
        "package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "composer.json", "gemfile",
    }
)
DOCUMENT_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt", ".adoc"})
DATABASE_SUFFIXES = frozenset({".sql", ".sqlite", ".sqlite3", ".db"})
CODE_SUFFIXES = frozenset(
    {
        ".c", ".cc", ".cpp", ".cs", ".go", ".java", ".js", ".jsx",
        ".kt", ".php", ".py", ".rb", ".rs", ".swift", ".ts", ".tsx",
    }
)

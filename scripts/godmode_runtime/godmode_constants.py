"""Stable Godmode runtime constants."""

from __future__ import annotations

import hashlib
import os

# Tools that read and cannot write. Named rather than inferred: a tool
# absent from this set is treated as capable of mutation and pays the full
# check.
#
# One owner because two had the same six names as separate literals - the
# gate hook deciding what skips the full check, and the Claude adapter
# deciding what an event reports as a read. They agreed by coincidence, and
# a disagreement about what can mutate is not the kind of drift worth
# discovering from behaviour.
READ_ONLY_TOOLS = frozenset({
    "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
})

# U-V2 disposition register vocabulary. It lives here rather than in
# `godmode_register` because two modules need it and neither may import the
# other: `godmode_invariants` is deliberately dependency-free so
# `godmode_chronicle` can import it without a cycle, while `godmode_register`
# imports `godmode_chronicle` - so invariants -> register would close exactly
# the loop that dependency-freedom exists to prevent.
#
# The previous arrangement kept two copies in step by hand with a test
# asserting they still agreed. This module has no runtime imports at all, so
# both sides can read one definition and the drift becomes unrepresentable
# rather than merely detected.
REGISTER_STATES = (
    "established", "superseded", "refuted", "worse-than-baseline",
    "matched-baseline", "rejected-precedent", "open",
)
REGISTER_EVIDENCE_PREFIXES = ("witness:", "verdict:", "file:")

AGENT_ENV = "GODMODE_AGENT_ID"


def agent_id() -> str:
    """Which agent is writing: declared if the host set one, else derived.

    Lives here, in the module with no runtime dependencies, because both
    the chronicle (which stamps it on every record) and the fleet layer
    (which coordinates between agents) need it. Putting it in either one
    makes the other import it and closes an import cycle - deferring that
    import inside a function hides the cycle from the interpreter but not
    from the atlas, which reads imports statically and enforces the
    no-cycle invariant.

    **Only the host can truly separate concurrent agents, and this does not
    pretend otherwise.** Two undeclared agents on one project share this
    id; separating them requires `GODMODE_AGENT_ID`, and one honest
    identity per project beats a fabricated per-agent one.

    Derived from the state home rather than the process, because the gate
    runs as a fresh subprocess per tool call - anything process-scoped
    would give ONE agent a different id per record. Hashed and truncated
    because the id travels inside records that may be shared, and a raw
    path is local detail that should not leave the machine.
    """
    declared = os.environ.get(AGENT_ENV, "").strip()
    if declared:
        return declared
    seed = os.environ.get("GODMODE_STATE_HOME") or os.getcwd()
    return "agent-" + hashlib.sha256(
        seed.encode("utf-8", "replace")).hexdigest()[:12]


PRODUCT = "Godmode"
RUNTIME_VERSION = "0.3.1"
SCHEMA_VERSION = 1
ARCHIVE_DIRNAME = "godmode-state"
MAX_HASH_BYTES = 5 * 1024 * 1024
DEFAULT_CONTEXT_BUDGET = 1_200
DEFAULT_RECORD_LIMIT = 24

EVENT_KINDS = frozenset(
    {
        "action", "assumption", "attestation", "branch", "change", "checklist", "checkpoint",
        "claim", "criterion", "database", "decision", "differential", "documentation",
        "incident", "invariant", "inventory", "lesson", "metric", "obligation", "pin",
        "plan", "refusal", "request",
        "session", "sprint", "upstream-diff", "verdict", "version",
    }
)

# Statuses that put a record out of force. Read by the contradiction check
# (a value that no longer binds cannot contradict one that does) and by the
# reversal check (an answer that was withdrawn is not a competing answer).
# One owner, because two readers asking "is this still in force?" with two
# different word lists is a disagreement waiting for a release to expose it.
SETTLED_STATUSES = frozenset({"retired", "superseded", "withdrawn", "revoked"})

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git", ".hg", ".svn", ".godmode", ".godmode-private",
        ".godmode-state", ".research", ".planning", ".sprints",
        ".checkpoints", ".handovers", ".evidence", ".decisions", ".lessons",
        "node_modules", "coverage", "dist", "build", "target", "__pycache__",
        ".venv", "venv",
        # Tool caches. These lived only in `godmode_structure`'s private
        # copy of this list, so every other walk - the atlas, the database
        # inventory, the scope fence - descended into them.
        ".tox", ".mypy_cache", ".pytest_cache",
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

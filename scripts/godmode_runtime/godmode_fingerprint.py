"""Working-tree fingerprint for claims and verdicts; the `seq:` referential check they share.

A claim or a verdict rests on the tree as it stood at cite time. `tree_fingerprint`
captures that instant - HEAD, the working-tree status, and the unstaged plus staged
diff - into one digest, so a later sweep can tell that the ground moved even when no
single cited file's hash did (a rename, a sibling file, an index change). It is
recorded verbatim (`godmode_attest.record_claim`'s `data["tree_fingerprint"]`,
`godmode_verdict`'s `data["witness_version"]` for a `file:` witness) and compared
against the tree as it is now (`godmode_attest.stale_claims`'s `tree-changed` and
`witness-changed` reasons) - never re-derived from history, so a stale check never
has to trust that nothing else touched the tree in between.

Two failure classes are kept apart on purpose (review finding S5/S6): a project git
cannot see AT ALL (no `.git`, no `git` binary) reads as `NO_GIT_DIGEST` - stable,
comparable, safe to treat as "clean" on both sides of a comparison. A project that
IS a git repo but could not be READ this one time (a 5-second timeout, index-lock
contention, an unborn branch with no HEAD commit yet) reads as `UNKNOWN_DIGEST`
instead - a transient failure must never freeze into a permanent false
`tree-changed` against a real digest recorded earlier, nor must it silently forge a
digest that looks like a real, clean tree.

`require_seq_cite` is the one referential check `record_claim` and
`record_verdict`'s `seq:` witness both need: a `seq:<n>` citation naming a
record sequence that was never appended is not a hypothesis to be graded
softer, it is a mistake in the citation itself - the record it claims to
rest on does not exist, so it is refused outright rather than downgraded.
A malformed `seq:` remainder (non-ASCII, non-decimal, or otherwise not a
plain base-10 integer `int()` can parse) is refused the same way, by the
same rule, never as an uncaught `ValueError` escaping past this check.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .godmode_anchor import run_git
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# The sentinel `digest` for a project git cannot see at all (no `.git`, no
# `git` binary at all) - visibly different from any real fingerprint's hex
# digest, never silently equal to one, and stable enough to compare on
# both sides (a project that is genuinely outside git stays outside git).
NO_GIT_DIGEST = "no-git"
# The sentinel for a real git repository this one call could not read (a
# timeout, index-lock contention, an unborn branch with no HEAD commit
# yet) - kept distinct from `NO_GIT_DIGEST` so `stale_claims` can skip the
# comparison entirely rather than either freezing a false mismatch or
# folding a read failure into a fake "clean" digest.
UNKNOWN_DIGEST = "unknown"


def tree_fingerprint(project: Path) -> dict[str, str]:
    """The working tree's current shape, as `{"head", "status_digest", "diff_digest", "digest"}`.

    `head` is `git rev-parse HEAD`; `status_digest` hashes the raw bytes of
    `git status --porcelain=v1 -z` (every path git considers modified,
    added, deleted, or untracked); `diff_digest` hashes the raw bytes of
    the unstaged diff plus the staged diff (`git diff --no-color` + `git
    diff --cached --no-color`), so an edit that is only staged, or only
    working-tree, still moves the digest. `digest` folds all three
    together - the one value callers compare.

    Not a git repository at all (or `git` itself cannot be run): every
    field empty, `digest` reads `NO_GIT_DIGEST`. A real repository this
    call could not fully read - `rev-parse HEAD` fails (no commit yet,
    or a transient error) or either of the two `git diff`/`status` reads
    times out or hits lock contention: `digest` reads `UNKNOWN_DIGEST`
    instead, distinct from both a real digest and `NO_GIT_DIGEST`, so a
    caller comparing against it treats "could not read" as "cannot say",
    never as "unchanged" or "outside git".

    Cost: exactly 4 git subprocess calls in the common case (a repo with a
    HEAD commit, all three payload reads succeed) - `rev-parse HEAD`,
    `status`, `diff`, `diff --cached`. The disambiguating `rev-parse
    --git-dir` probe below only runs when `rev-parse HEAD` already failed,
    so it never taxes the case every real caller hits.
    """
    head = run_git(project, "rev-parse", "HEAD")
    if head is None:
        # `rev-parse HEAD` alone cannot tell "not a git repo" from "is a
        # repo, but has no HEAD commit yet (or hit a transient error)" -
        # the probe below costs one extra call, spent only here, never on
        # the common path where HEAD already resolved.
        if run_git(project, "rev-parse", "--git-dir") is None:
            return {"head": "", "status_digest": "", "diff_digest": "", "digest": NO_GIT_DIGEST}
        return {"head": "", "status_digest": "", "diff_digest": "", "digest": UNKNOWN_DIGEST}
    status = run_git(project, "status", "--porcelain=v1", "-z", text=False)
    diff_unstaged = run_git(project, "diff", "--no-color", text=False)
    diff_staged = run_git(project, "diff", "--cached", "--no-color", text=False)
    if status is None or diff_unstaged is None or diff_staged is None:
        return {"head": head, "status_digest": "", "diff_digest": "", "digest": UNKNOWN_DIGEST}
    status_digest = hashlib.sha256(status).hexdigest()
    diff_digest = hashlib.sha256(diff_unstaged + diff_staged).hexdigest()
    digest = hashlib.sha256(f"{head}{status_digest}{diff_digest}".encode("utf-8")).hexdigest()
    return {
        "head": head,
        "status_digest": status_digest,
        "diff_digest": diff_digest,
        "digest": digest,
    }


def existing_sequences(archive: Chronicle) -> set[int]:
    """Every record sequence currently in `archive` - one full, unbounded read.

    R3 (review): the one scan a caller with MORE THAN ONE `seq:` cite to
    check in a single run (`record_claim` citing several, or a future
    caller of `seq_cite_resolves` in a loop) should take once and reuse,
    rather than one `archive.read_events()` per citation. Callers with a
    single `seq:` cite have no reason to precompute this - `seq_cite_resolves`
    scans on its own when nothing is passed in.
    """
    return {record["sequence"] for record in archive.read_events()}


def seq_cite_resolves(
    archive: Chronicle, sequence: int, *, existing: set[int] | None = None
) -> bool:
    """Whether a record at exactly this sequence exists in `archive`.

    Existence is the whole test: sequences are assigned once, in order, at
    append time, so a sequence that exists is by construction no later than
    the current head - there is no separate "exists but is from the
    future" case this needs to guard against.

    Cost, not correctness: a cite naming a sequence past the current head
    is refused from the cheap head cache alone, with no archive read at
    all - the common case for a fabricated or typo'd `seq:`. Anything
    within range still needs the actual scan, and that scan is UNBOUNDED
    (`archive.read_events()`, not `archive.select(...)`) - review finding
    N1: `Chronicle.select` clamps its `limit` to the last 500 records
    (`selected[-max(1, min(limit, 500)):]`) regardless of what is asked
    for, so bounding this existence check by any `select(limit=...)` call
    silently narrows it to the newest 500 records - a real, older cite on
    an archive past that size would be refused outright with a message
    that is false. A `seq:` cite is a referential-integrity question about
    the WHOLE archive, never a recency window.

    `existing` (R3 above) lets a caller checking several `seq:` cites in
    one run pass in `existing_sequences(archive)` once and skip the scan
    here entirely; `None` (every caller before R3, and any caller with
    only one cite to check) scans fresh, unchanged from before.
    """
    head = archive._read_head()
    if head is not None and sequence > head["sequence"]:
        return False
    if existing is not None:
        return sequence in existing
    return any(record["sequence"] == sequence for record in archive.read_events())


def require_seq_cite(
    archive: Chronicle, citation: str, *, existing: set[int] | None = None
) -> None:
    """Raise when `citation` is `seq:`-prefixed and does not resolve.

    A well-formed `seq:<n>` (`n` a plain ASCII decimal integer) that names
    an existing record passes silently; anything else `seq:`-prefixed -
    a sequence nothing was ever appended at, or a remainder that is not a
    plain ASCII decimal integer at all (non-digit text, or a digit-shaped
    Unicode character `int()` cannot parse the way it looks, such as a
    superscript or a full-width numeral) - raises the same `ArchiveError`.
    `rest.isascii() and rest.isdecimal()` is checked before `int(rest)`
    ever runs, so the parse itself can never raise past this function: a
    malformed cite is refused by the same rule as a dangling one, never by
    an uncaught `ValueError`. `existing` (R3) is passed straight through
    to `seq_cite_resolves`.
    """
    if not citation.startswith("seq:"):
        return
    rest = citation[len("seq:"):]
    if (rest.isascii() and rest.isdecimal()
            and seq_cite_resolves(archive, int(rest), existing=existing)):
        return
    raise ArchiveError(f"cite {citation} does not exist")

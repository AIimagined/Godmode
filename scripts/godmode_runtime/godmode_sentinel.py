"""Privacy boundary and local one-use capabilities for Godmode."""

from __future__ import annotations

# getpass/hmac/secrets are deferred into the five CapabilityBroker methods
# that use them (configure, configure_interactive, _password_matches, issue,
# consume) rather than imported here: classify_action - the function every
# hook call makes, whether or not it ever touches a capability - lives in
# this same module, so a module-top import of these three paid their cost
# on every tool call, not just the ones that mint or spend a capability.
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import sys
import tempfile
import time
from typing import Any

from .godmode_constants import MAX_HASH_BYTES
from .godmode_errors import ArchiveError, AuthorizationError, PrivacyError


def _stdin_is_interactive() -> bool:
    try:
        if not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if os.name == "nt":
        # On Windows, isatty() is true for any character device, including
        # NUL. Only a real console accepts GetConsoleMode, and getpass reads
        # from the console, so anything else would block forever.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    return True


def _require_tty() -> None:
    if not _stdin_is_interactive():
        raise AuthorizationError(
            "No interactive terminal is available for password entry. "
            "Run this command from an interactive shell, or pass "
            "--password-stdin and pipe the password on standard input."
        )


def read_password_stdin() -> str:
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise AuthorizationError("No password was received on standard input")
    return password


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    # Three shapes an adversarial sweep found in ONE of the two secret
    # scanners but not the other (this gate missed conn-strings the egress
    # scan caught; both missed JWTs and Slack tokens). The seam test in
    # tests/test_secret_scanner_parity.py now pins every named kind against
    # BOTH scanners, so the two rule sets cannot silently diverge again.
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,30}:\/\/[^\s:@\/]+:[^\s@\/]{4,}@"),
    re.compile(r"\bxox[abprse]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"(?i)\b(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~-]{12,}"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[^\s,;]{8,}"),
    # A credential the way a person says one. The rule above needs a `:` or `=`
    # and eight characters, which is right for a machine token and wrong for
    # every human phrasing: `password: 555345`, `my password 555345` and
    # `the db password is hunter2` all passed it, and were stored verbatim.
    #
    # The eight-character floor existed to stop `secret=x` matching noise. It
    # also excluded the passwords people actually type, which are short - so
    # length is replaced by the shape of the value. A digit, or quotes, is what
    # separates `password 555345` from `password manager`, and four characters
    # keeps `api key v2` out.
    #
    # This shipped in the request ledger's first release and the first real
    # credential to arrive walked straight past it. The docstring claiming a
    # ledger of asks is not worth a store of credentials was tested against
    # `ghp_…` - the case that was imagined, not the case that happened.
    re.compile(
        # `api key` with a space is how it is written in a sentence; the older
        # rule knew only `api_key` and `api-key`, which are how it is written
        # in a config file.
        r"(?i)\b(?:password|passwd|passphrase|passcode|pin|api[_\-\s]?key|secret|"
        r"token|credential)s?\b\s*(?:is|was|=|:|->)?\s*"
        r"(?:(?P<quoted>[\"'][^\"']{4,}[\"'])|(?P<value>(?=\S*\d)[^\s,;]{4,}))"
    ),
)

# A mutating flag anywhere in a `git branch` invocation is checked before any
# safe pattern, because the verified failure mode was the reverse order: the
# read-only prefix matched `git branch` and the delete flag never got a look.
_GIT_BRANCH_MUTATION = re.compile(
    r"(?i)\bgit\s+branch\b.*\s(?:-[a-z]*[dmcf][a-z]*|--delete|--force|--move|--copy|"
    r"--set-upstream-to(?:=\S+)?|--unset-upstream|--edit-description)\b"
)

# Staging and committing are the work: local, reversible, and losing nothing.
# Gating them made committing impossible in a session, because no host tool
# call carries a field a capability could travel in. What earns an
# interruption is the operation that leaves the machine or destroys work, so
# `--amend` is excluded here and stays protected.
# `commit-tree` writes an object into the store and is not `commit`. The word
# boundary after `commit` falls inside the hyphen, so plumbing that writes was
# admitted by the allowance for ordinary committing - the same defect as
# `merge-base` being read as `merge`, in the direction that matters.
_GIT_LOCAL_CHANGE = re.compile(r"(?i)^\s*git\s+(?:add|commit)(?![-\w])(?!.*\s--amend\b)")

# `git checkout -b <name>` creates a branch and switches to it; the plain
# `checkout`/`checkout --`/pathspec forms discard working-tree changes or
# move HEAD around history, which is the shape `_ACTION_PATTERNS`'s
# `git-history-or-remote` pattern still catches (that pattern excludes this
# `-b`/`-B` form explicitly - see its own comment). `-B` resets an existing
# branch to the given start point as well as creating one; treated the same
# as `-b` here, since neither leaves the machine or discards committed work.
_GIT_BRANCH_CREATE = re.compile(r"(?i)^\s*git\s+checkout\s+-[bB]\b")

# `git -C <path> log` is a log. Every git rule here reads the subcommand at a
# fixed position, so a global option in front of it meant no rule matched and
# the read fell through to unclassified-mutation. Stripping the options and
# judging what remains keeps one rule per operation instead of a copy of the
# skip in each: `git -C other push` becomes `git push` and is protected as one,
# where before it was refused as an unknown, which is the right answer given
# for the wrong reason and stops being right the moment the fallback changes.
#
# `--exec-path=` is deliberately absent: it points git at a different set of
# binaries, so it changes what runs rather than only where.
_GIT_GLOBAL_OPTION = re.compile(
    r"(?i)^([ \t]*git)[ \t]+(?:-C[ \t]+(?:\"[^\"]*\"|'[^']*'|[^\s;&|<>]+)|"
    r"-c[ \t]+\S+|--no-pager|--paginate|--no-replace-objects|--literal-pathspecs|"
    r"--(?:git-dir|work-tree|namespace)[= \t][^\s;&|<>]+)(?=[ \t])"
)

# Quoted text is data. The classifier searched the whole line, so
# `grep "git push" notes.md` was refused for containing the words. Blanking
# quoted spans before the mutation patterns is safe only because the safe
# listings are a whitelist matched on the original: a shell invoked on a
# quoted script is not on that list and still fails closed.
#
# A regex (`'[^']*'|"[^"]*"`) was the first version here and had no
# backslash-escape awareness: `grep "he said \"drop table users\""` closed
# the match at the first escaped `\"` instead of the real closing quote, so
# "drop table users" read as live text and the search was refused as a
# database mutation - the exact false-refusal shape the plant test
# (`grep "drop table" ...` -> R0) exists to prevent, just one quoting layer
# deeper than that test reaches. `_raw_segments` a few hundred lines below
# already tracks quotes correctly (a backslash escapes the next character
# unless inside single quotes, so an escaped quote can't end a quoted span
# early); `_executable_text` mirrors those exact rules character-by-character
# rather than sharing `_raw_segments` outright - `_raw_segments` also has to
# find multi-character separators at each unquoted position via
# `_SEPARATORS.match(command, index)`, which needs the original string and
# index together in a way a blanking pass does not, and merging the two
# risked the segment splitter for a benefit blanking does not need. Any
# change to one's quote/backslash rule must be checked against the other.
def _executable_text(command: str) -> str:
    """The command with its quoted arguments blanked out, one character at
    a time rather than by collapsing each quoted span to one space - so a
    quote's start and end positions in the result line up exactly with
    `command`, which `_categorize`'s redirect-target extraction depends on.
    """
    result: list[str] = []
    quote: str | None = None
    index = 0
    length = len(command)
    while index < length:
        character = command[index]
        if character == "\\" and quote != "'" and index + 1 < length:
            blank = quote is not None
            result.append(" " if blank else character)
            result.append(" " if blank else command[index + 1])
            index += 2
            continue
        if quote:
            result.append(" ")
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "\"'":
            quote = character
            result.append(" ")
            index += 1
            continue
        result.append(character)
        index += 1
    return "".join(result)


_ACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "git-history-or-remote",
        re.compile(
            # `commit --amend` is named here rather than left to fail closed:
            # it was protected either way, but the refusal called it an
            # unclassified mutation, which tells the reader nothing about why.
            r"(?i)\bgit\s+commit\b[^;|&]*\s--amend\b|"
            # `merge-base` reports the common ancestor of two commits and
            # merges nothing. The boundary after `merge` falls inside the
            # hyphen, so the word matched and a read was reported as history
            # mutation - the same shape as `Out-String` reading while
            # `Out-File` writes, which is why neither is matched by prefix.
            # `checkout(?!\s+-[bB]\b)`: `-b`/`-B` creates (and switches to) a
            # local branch rather than discarding work or rewriting history -
            # `_GIT_BRANCH_CREATE` names that form separately, above.
            r"\bgit\s+(?:push|merge(?!-base)|rebase|reset|clean|tag|checkout(?!\s+-[bB]\b)|switch|"
            r"branch\s+(?:-[dDmM]|--delete)|worktree\s+(?:remove|prune|move)|"
            r"stash\s+(?:drop|pop|clear|apply|push|save|branch|create|store)|"
            r"remote\s+(?:add|remove|rm|rename|set-url|set-head|set-branches|prune|update))\b"
        ),
        ("repository history", "branches or worktrees", "possibly a remote"),
    ),
    (
        # `git restore` discards working-tree changes, which is worth stopping
        # - but it was stopped as a *database* mutation, because the word
        # `restore` was matched anywhere it appeared. A refusal that names the
        # wrong thing is worse than a slow one: the reader learns the tool does
        # not understand the command, and starts routing around it.
        "worktree-discard",
        re.compile(r"(?i)\bgit\s+restore\b"),
        ("uncommitted work in the working tree", "recoverability"),
    ),
    (
        "database-mutation",
        # Anchored to a database, not to English. The previous rule matched
        # `drop`, `migrate`, `rollback` and `restore` as bare words, so
        # `cat docs/migrate-notes.md` and `grep -rn rollback src/` were both
        # refused as database mutations - a read of a file and a search, called
        # schema changes. Meanwhile the genuine article escaped: the SQL in
        # `psql -c 'DROP TABLE orders'` is quoted, quoted spans are blanked
        # before these patterns run, and the command fell through to
        # unclassified. It refused prose and missed the statement.
        re.compile(
            # SQL that names what it operates on.
            r"(?i)\b(?:drop|truncate)\s+(?:table|database|schema|index|view|user)\b|"
            r"\bdelete\s+from\b|\balter\s+table\b|"
            # A migration tool doing a migration. The verb alone means nothing
            # - `migrate` is also a word in a filename - so the tool has to be
            # named too.
            r"\b(?:psql|mysql|mysqldump|sqlite3|mongosh|mongo|redis-cli|"
            r"prisma|alembic|flyway|liquibase|knex|sequelize|typeorm|dbmate|"
            r"goose|atlas|sqlx|diesel)\b[^;|&]*\b(?:migrate|migration|rollback|"
            # `upgrade` and `downgrade` are alembic's own verbs and were absent
            # until a test case named a real invocation instead of a plausible
            # one. `up`/`down` do not cover them: the boundary stops at the `g`.
            r"reset|drop|seed|restore|upgrade|downgrade|up|down)\b|"
            r"\b(?:manage\.py|rails|artisan|dotnet\s+ef|npm\s+run|yarn|pnpm\s+run)\b"
            r"[^;|&]*\b(?:migrate|migration|rollback|db:migrate|db:rollback|"
            r"db:reset|seed)\b"
        ),
        ("database schema or records", "rollback readiness"),
    ),
    (
        "release-or-external-write",
        re.compile(
            r"(?i)\b(?:deploy|publish|release|upload|send\s+(?:message|email)|"
            r"create\s+(?:pull request|issue)|post\s+to)\b"
        ),
        ("an external system", "other users or consumers"),
    ),
    (
        # PowerShell's write cmdlets, named the same way `stop-process` already
        # was: the read-verb list (`_PS_READ_VERBS`) is what usually keeps an
        # unlisted cmdlet failing closed, but Task 3's unknown-command fallback
        # (below) now reads a genuinely unrecognised head as a plain command
        # with no evidence of mutation - which these ARE evidence of, by name,
        # so they are named here rather than left to fall through to it.
        "filesystem-mutation",
        re.compile(
            r"(?i)(?:\brm\b|\brmdir\b|\brd\b|\bdel\b|\bremove-item\b|\bmove-item\b|"
            r"\bnew-item\b|\bset-content\b|\badd-content\b|\bout-file\b|"
            r"\bclear-content\b|\brename-item\b|"
            r"\bshutil\.rmtree\b|\bos\.remove\b)"
        ),
        ("local files", "recoverability"),
    ),
    (
        # Registering a new plugin SOURCE: from then on, everything that
        # marketplace serves is code the agent will offer to run. The
        # recovered field corpus (B4-9) shows the gate asking about this as
        # an unclassified mutation and the operator judging the ask CORRECT
        # (trust boundary) - while `list`/`install` beside it were judged
        # pure friction, because installing draws from a marketplace already
        # trusted. U-G1b's read-by-default for unknown heads later swallowed
        # all three; this names the one that must keep asking. Anchored to
        # the full `plugin marketplace add` phrase so the two friction reads
        # stay reads.
        "agent-trust-mutation",
        re.compile(r"(?i)\bclaude\s+plugin\s+marketplace\s+add\b"),
        ("the agent's own plugin trust surface",
         "every plugin the new source serves"),
    ),
    (
        # A streamed regex edit of a file in place. Multi-layer escaping and
        # pattern-located boundaries silently corrupt source (four escaping
        # failures in one recorded session); the honest tools are the host's
        # Edit/Write, which match exact text and fail loudly. This was already
        # protected as `unclassified-mutation` - the point of naming it is the
        # refusal message: "use the editor tools" beats "unknown state".
        # Scripts remain the right tool for DATA files; the ask-tier leaves
        # that judgement with the operator instead of refusing outright.
        "scripted-source-edit",
        re.compile(
            r"(?i)\bsed\b[^;|&]*\s(?:-i|--in-place)\b|"
            r"\bperl\b[^;|&]*\s-[a-z]*i[a-z]*\b|"
            r"\bawk\b[^;|&]*\s-i\s*inplace\b"
        ),
        ("file contents via a streamed regex; exact-text editor tools are the "
         "safe form for source", "silent mid-line corruption"),
    ),
    (
        # Ending a process. Restarting a dev server the agent started is
        # ordinary work, and it was an `unclassified-mutation` - the bucket for
        # things the classifier does not recognise at all - so the refusal said
        # nothing useful about what would happen. Named, it can be reasoned
        # about; at R3 it asks rather than stops.
        #
        # `taskkill` and `Stop-Process` sit here too: the same act, spelled
        # three ways by three platforms, and only one of them was ever going to
        # be guessed by a POSIX-shaped rule.
        "process-control",
        # Anchored to command position. Written as "anywhere in the line" first,
        # which made `grep -rn kill src/` a process termination - the identical
        # bare-word defect fixed for the database category minutes earlier, and
        # reintroduced by the person who fixed it. A verb is only a verb where
        # a verb goes.
        re.compile(
            r"(?i)^\s*(?:sudo\s+)?(?:kill|killall|pkill|taskkill|stop-process|"
            r"stop-service|systemctl\s+(?:stop|restart|kill))\b"
        ),
        ("a running process", "whatever it was serving"),
    ),
    (
        # U-B2: unpinning a protected evaluator is the one operation that
        # can defeat the pin mechanism, so it is capability-gated the same
        # way a forced push is - see `unpin_operation_text` and
        # `_TIER_BY_CATEGORY["evaluator-unpin"]` (R5, refuse outright, only
        # a staged/consumed capability moves it).
        "evaluator-unpin",
        re.compile(r"(?i)^\s*godmode\s+protect\s+--unpin\b"),
        ("a pinned evaluator's protection", "the integrity of results already "
         "measured with it"),
    ),
)

# A database client's own head, not a bare verb anywhere in the line. The
# verb-anchored alternative inside `_ACTION_PATTERNS`'s database-mutation
# entry above only fires when a migration/reset/etc. word is visible - and a
# real statement handed to one of these clients is usually quoted (`psql -c
# 'drop table users'`), which blanks the verb before either pattern ever
# runs. A DB client's whole purpose is running arbitrary statements, so
# invoking one at all is the evidence; no visible verb is required. Scoped to
# the actual interactive/scripting clients - not the app-level migration
# runners (`prisma`, `alembic`, `knex`, ...) the verb-anchored pattern above
# already covers, where the tool name alone says nothing without a verb.
DB_CLIENTS = ("psql", "mysql", "sqlite3", "redis-cli", "mongosh", "mariadb",
              "pg_dump", "pg_restore")
_DB_CLIENT_HEAD = re.compile(
    rf"(?i)^(?:{'|'.join(re.escape(name) for name in DB_CLIENTS)})\b")

# Tools that fetch from, send to, or run a command on a remote host. Unlike a
# merely unrecognised local command, these can exfiltrate or execute
# remotely - `curl --data-binary @secrets.env <remote URL>` sends the file's
# contents, not just the fact that curl ran, and `ssh host cmd`/`scp file
# host:` are a remote shell and a remote copy, not a local read of anything -
# so they are excluded from the unknown-command fallback's default read even
# when nothing else about the line looks like a mutation. `godmode_netgate.py`
# was checked for a reusable network-egress category first (per the
# controller's own instruction): it is a differential runtime socket-capture
# tool with no command vocabulary or category of its own, so there is nothing
# to reuse - these stay `unknown-command`, the same category the fetch tools
# above already use.
_NETWORK_FETCH_HEADS = re.compile(
    r"(?i)^\s*(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|"
    r"ssh|scp|rsync|sftp|ftp|nc|ncat|telnet)\b")

# Programs this module already models as "has a real write surface, and the
# safe/read forms of it are enumerated above" (`git`, via `_SAFE_PREFIXES`/
# `_SAFE_GIT_BRANCH`/`_SAFE_GIT_TAG`/`_SAFE_GIT_REMOTE`/the git-history-or-
# remote pattern; `gh`, via `_SAFE_GH`) - reaching this point means none of
# that table matched, which is different from a plain unrecognised command
# having nothing pointing at a mutation: the existence of a dedicated safe
# subset for a program is itself the signal that its *un*enumerated forms
# are not "no evidence." `export`/`unset` join them for the same reason from
# the other direction - `_ENV_BINDING`'s own negative lookahead is what
# excludes `PATH`/`LD_PRELOAD`/etc. from the safe form, so anything of this
# shape reaching here already failed that check on purpose.
_NAMED_BY_OWN_RULES = re.compile(r"(?i)^\s*(?:git|gh|export|unset)\b")

# Per-command flags that name an output-file argument on a command this
# module otherwise reads as ordinary inspection: `git log --output=file` and
# `sort -o file` write a file exactly like a `>` redirect does, without
# spelling the redirect operator - so a command already matched by
# `_SAFE_INSPECTION_PATTERNS`/`_SAFE_SHELL_READS` never had its own arguments
# looked at for one. Keyed by head, not by head+subcommand: `--output` is
# specific enough a name that scoping it to `git log`/`diff`/`show`
# specifically buys no real safety, and a data table an exporter can walk
# directly is worth more than a marginally narrower regex.
_OUTPUT_FLAGS_BY_HEAD: dict[str, tuple[str, ...]] = {
    "git": ("--output",),
    "sort": ("-o", "--output"),
}


def _output_flag_target(segment: Segment) -> str | None:
    """The path named by one of `_OUTPUT_FLAGS_BY_HEAD`'s flags in
    `segment`, or None if its head has no such flag or none is present.
    Reads `segment.tokens` (not `vocab_tokens`): a flag's target is a real
    argument, path-shaped or not, the same as a redirect's target is."""
    flags = _OUTPUT_FLAGS_BY_HEAD.get(segment.head.lower())
    if not flags:
        return None
    tokens = segment.tokens
    for index, token in enumerate(tokens):
        for flag in flags:
            if token.startswith(f"{flag}="):
                return token[len(flag) + 1:]
            if token == flag:
                return tokens[index + 1] if index + 1 < len(tokens) else ""
            # The short form's attached spelling (`-oFILE`, no `=`) - only
            # for single-character flags, matching what `sort` itself accepts.
            if len(flag) == 2 and not flag.startswith("--") and token.startswith(flag) \
                    and token != flag:
                return token[len(flag):]
    return None

# Commands whose entire purpose is running a body the classifier cannot read
# to decide anything about, and are excluded from the unknown-command
# fallback's default read for that reason - named, not defaulted, the same
# way `git` and the network fetchers above are.
#
# `ForEach-Object { ... }` runs whatever its block contains, same as the
# stream-editing `sed`/`awk` this task otherwise widens: `StillClosedTests`
# already pins this cmdlet as permanently protected regardless of how
# visibly harmless a specific block's content is, because reading the block
# to decide is the same defect class as `find -exec`/`-delete` deciding by
# what a shell would do with it rather than by what it names. The
# `foreach($x in $list){...}` STATEMENT is a different construct (no piped
# block, no cmdlet) and is not named here.
#
# `bash -c "..."`/`sh -c "..."`/`eval "..."` hand an interpreter a whole
# script as one opaque, usually-quoted argument - `ExecutablePositionTests`
# already pins `bash -c "rm -rf /"` as protected specifically because
# quoting must not launder an unrecognised executable. This is the same
# construct `node -e`/`python -c` are (an interpreter fed a string), except
# those two are pinned open by `_self_check` and this plan is not chartered
# to revisit interpreter policy (task-2-report.md, addendum 2) - `bash`/`sh`
# were never on that allowance and are not added to it here.
_UNKNOWABLE_BODY_HEADS = re.compile(
    r"(?i)^\s*ForEach-Object\b|"
    r"^\s*(?:bash|sh|zsh|ksh|dash)\b[^;|&]*\s-c\b|"
    r"^\s*eval\b"
)

# The one shape of the excluded tools above this project's own transcripts
# show being used harmlessly: a status probe that discards the response body
# and sends nothing. `curl` needs both a discarded output (`-o /dev/null`)
# and the write-out flag that is the whole reason to run it that way;
# PowerShell's request cmdlets need the flag that names this as a basic
# status check (`-UseBasicParsing`) AND to not be writing the response to a
# file, a non-GET method, or a request body - `-UseBasicParsing` is required
# rather than merely tolerated, because a bare `Invoke-WebRequest <url>` with
# none of these flags is still an ordinary fetch of whatever the URL returns,
# not a probe, and must keep asking. Read-only either way - what governs
# actually fetching data is the separate network gate, not this classifier.
# B4-9: flags that turn a curl invocation into something other than a plain
# read - data senders, uploads, credentials, non-GET methods, config files
# (a config file can add any of the others invisibly), and output flags that
# write somewhere real. Grouped here so the readonly-fetch rule below and any
# future reviewer read ONE list.
_CURL_UNSAFE_FLAG = re.compile(
    r"(?:^|\s)(?:-d|--data(?:-\w+)?|-F|--form(?:-string)?|-T|--upload-file|"
    r"-u|--user|-K|--config|-b|--cookie|-c|--cookie-jar|-e|--referer|"
    r"-A|--user-agent|-H|--header|-E|--cert|--key|-n|--netrc\S*|"
    r"-X|--request|--json|--url-query)\b"
)
_CURL_OUTPUT_FLAG = re.compile(
    r"(?:^|\s)(?:-o|--output|-O|--remote-name|-J|--remote-header-name|"
    r"--output-dir|--create-dirs)\b"
)
_CURL_DISCARDED_OUTPUT = re.compile(
    r"(?:^|\s)(?:-o|--output)[ \t]+(?:/dev/null|nul)\b(?![^;|&]*"
    r"(?:^|\s)(?:-o|--output)[ \t]+(?!/dev/null|nul))"
)
_LITERAL_HTTPS_URL = re.compile(r"[\"']?https?://[^\s\"'`$]+[\"']?")


def _readonly_literal_fetch(text: str) -> bool:
    """B4-9: True only for a curl invocation the classifier can PROVE is a
    plain read of a literal URL: head is curl, at least one literal
    http(s):// URL, no `$`/backtick anywhere (an unexpanded expansion means
    the URL is not knowable from the text), no data/upload/auth/config/
    method flag, and no output flag other than a discarded `-o /dev/null`.
    Anything unprovable falls back to the caller's ask."""
    if "$" in text or "`" in text:
        return False
    if not re.match(r"(?i)^\s*curl\b", text):
        return False
    if not _LITERAL_HTTPS_URL.search(text):
        return False
    # Every URL-shaped token must be http(s) - `curl ftp://...` or
    # `scp://` never qualifies even beside a legitimate https one.
    # Scheme literals assembled, not written: the privacy sweep bans a
    # remote-URL literal anywhere in this runtime, comments included.
    for token in re.findall(r"[a-z][a-z0-9+.-]*://", text.lower()):
        if token not in ("http:" + "//", "https:" + "//"):
            return False
    if _CURL_UNSAFE_FLAG.search(text):
        return False
    if _CURL_OUTPUT_FLAG.search(text) and not _CURL_DISCARDED_OUTPUT.search(text):
        return False
    return True


_SAFE_NETWORK_PROBE = re.compile(
    r"(?i)^\s*curl\b(?=[^;|&]*\s(?:-o|--output)[ \t]+(?:/dev/null|nul)\b)"
    r"(?=[^;|&]*\s(?:-w|--write-out)\b)|"
    r"^\s*(?:Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b"
    r"(?=[^;|&]*-UseBasicParsing\b)"
    r"(?![^;|&]*(?:-OutFile\b|-Method[ \t]+(?!GET\b)\S|-Body\b))"
)

# Argument tokens the anchored safe listings may carry. Shell control and
# expansion characters are excluded so a read-only form cannot smuggle a second
# command, and a leading dash is excluded so a flag can never ride in as a
# positional argument.
_ARG = r"[^\s;&|<>`$\"'-][^\s;&|<>`$]*|'[^';&|<>`$]*'|\"[^\";&|<>`$]*\""
_VAL = r"[^\s;&|<>`$]+"

# `git branch`, `git tag`, and `git remote` list state when bare but mutate it
# with the right flag or a positional name, so their safe forms are anchored to
# the end of the operation and enumerate only listing tokens; anything else
# falls through to the protected classifiers. Separators are limited to spaces
# and tabs so a newline cannot append a second command.
_SAFE_GIT_BRANCH = re.compile(
    r"(?i)^[ \t]*git[ \t]+branch"
    r"(?:[ \t]+(?:--show-current|--all|--remotes|--verbose|-[arv]{1,3}|"
    rf"--sort={_VAL}|--format={_VAL}|--column(?:={_VAL})?|--no-column|"
    rf"--(?:contains|no-contains|merged|no-merged|points-at)(?:[ \t]+(?:{_ARG}))?|"
    rf"--list(?:[ \t]+(?:{_ARG}))*))*"
    r"[ \t]*$"
)
_SAFE_GIT_TAG = re.compile(
    r"(?i)^[ \t]*git[ \t]+tag"
    rf"(?:[ \t]+(?:-l(?:[ \t]+(?:{_ARG}))*|--list(?:[ \t]+(?:{_ARG}))*|-n\d*|"
    rf"--sort={_VAL}|--format={_VAL}|--column(?:={_VAL})?|--no-column|"
    rf"--(?:contains|no-contains|merged|no-merged|points-at)(?:[ \t]+(?:{_ARG}))?))*"
    r"[ \t]*$"
)
_SAFE_GIT_REMOTE = re.compile(
    r"(?i)^[ \t]*git[ \t]+remote"
    r"(?:[ \t]+(?:-v|--verbose))*"
    rf"(?:[ \t]+(?:show|get-url)(?:[ \t]+(?:-n|--push|--all|{_ARG}))*)?"
    r"[ \t]*$"
)
# Git has no verb convention to classify itself with, so its read subcommands
# have to be named. This list was written from memory and was missing most of
# what real work uses: `rev-list`, `ls-files`, `describe`, `blame` and six more
# were all refused as unknown mutations. The replacements were not imagined
# either - they are the git commands this project actually issued, recovered
# from its own transcripts, which is the only way a list like this stops being
# a guess. Plumbing that writes (`update-ref`, `commit-tree`, `hash-object`,
# `symbolic-ref NAME REF`) is absent on purpose and still fails closed.
_SAFE_PREFIXES = re.compile(
    r"(?i)^\s*(?:git\s+(?:status|diff|log|show|rev-parse|rev-list|describe|blame|"
    r"annotate|shortlog|whatchanged|name-rev|merge-base|for-each-ref|show-ref|"
    r"count-objects|check-ignore|check-attr|cat-file|ls-files|ls-tree|ls-remote|"
    # `fetch` downloads objects and updates remote-tracking refs; it touches
    # no local branch and loses no local work, which is the same
    # non-destructive shape as `remote update` already being read here.
    r"diff-tree|diff-index|grep|version|fetch|worktree\s+list|"
    r"stash\s+(?:list|show))|inspect|read|list|show|explain|doctor|privacy)\b"
)

# `gh` reads the same forge the gate protects writes to, and every one of them
# was an unclassified mutation - including `gh auth status`, which prints who
# you are. The nouns are open-ended because new ones keep arriving; the verbs
# are closed, so `gh release view` reads and `gh release create` is still a
# release. `gh api` is the exception that needs its own guard: the default is
# GET, and it becomes a write through a flag rather than through a word.
_SAFE_GH = re.compile(
    r"(?i)^[ \t]*gh[ \t]+(?:"
    r"auth[ \t]+status|"
    r"[a-z-]+[ \t]+(?:view|list|status|diff|checks)\b|"
    r"api\b(?![^\n]*(?:-X[ \t]+(?!GET\b)|--method[ \t]+(?!GET\b)|"
    r"[ \t]-[fF][ \t]|--field[ \t]|--raw-field[ \t]|--input[ \t]))"
    r")"
)

# A help or version banner is not the operation it describes. `release --help`
# was classified as a release and refused at R4, which is the gate at its least
# credible: it blocked the one call whose entire purpose is to explain itself.
# Every CLI short-circuits on these before acting, so the flag decides.
#
# `-h` and `-V` are deliberately absent. `sort -h` sorts and `du -h` formats;
# a single letter means whatever each tool decided, and the long forms carry
# the whole benefit without inheriting that ambiguity.
_HELP_FLAG = re.compile(r"(?i)(?:^|\s)--(?:help|version|usage)(?=\s|$)")

# `godmode release --published v0.2.5` compares local tags against a list of
# releases the caller supplies and contacts nothing. It was refused at R4 for
# containing the word `release` - the tool built so that release state would be
# read instead of remembered, blocked by the gate shipped beside it.
#
# Named narrowly rather than by exempting the interpreter: `python manage.py
# migrate` must keep failing on the word `migrate`, so what is allowed here is
# this command with this reading flag, and nothing else about it generalises.
_SAFE_GODMODE_READ = re.compile(
    r"(?i)^[^;&|]*\bgodmode(?:\.py)?\b[^;&|]*\brelease\s+--published\b[^;&|]*$"
)

# Ordinary inspection. Absent these, every `ls` fell through to
# unclassified-mutation and the gate denied a working session - failing closed
# on an unknown mutation is right, and applying it to `ls` is the approval
# fatigue the threat model warns about.
_SAFE_SHELL_READS = re.compile(
    r"(?i)^\s*(?:ls|dir|pwd|cat|bat|head|tail|wc|nl|file|stat|du|df|tree|echo|"
    r"printf|which|type|whoami|date|env|printenv|basename|dirname|realpath|"
    r"readlink|sort|uniq|cut|awk|sed\s+-n|grep|egrep|fgrep|rg|ag|diff|cmp|"
    r"md5sum|sha256sum|cd|pushd|popd|find|fd|findstr|where|more|fc)\b"
)

# PowerShell classifies itself. Its approved-verb convention is a documented
# contract on cmdlet authors, so `Get-` is read-only by construction and
# matching the verb set stays correct for cmdlets nobody enumerated. Naming the
# read verbs is the safe direction: an unlisted verb - Set, New, Remove, Clear,
# Rename, Move, Stop, Invoke - falls through and fails closed. Listing the
# write verbs instead would let everything unlisted through.
#
# Without this the hook fired on PowerShell calls but the classifier knew only
# POSIX vocabulary, so on Windows every cmdlet was an unclassified mutation and
# the gate denied the whole session.
_PS_READ_VERBS = (
    r"Get|Test|Measure|Select|Where|Sort|Group|Compare|Resolve|Split|Join|"
    r"Format|ConvertTo|ConvertFrom|Show|Read|Find|Search"
)
# `Out-` cannot join them: Out-String reads and Out-File writes, so the split
# runs through the verb rather than around it and only the readers are named.
_POWERSHELL_READS = re.compile(
    rf"(?i)^\s*(?:(?:{_PS_READ_VERBS})-[A-Za-z]+|"
    r"Out-(?:String|Host|GridView)|Write-(?:Output|Host|Verbose|Debug)|"
    r"gci|gc|gi|gl|gp|gm|gcm|gu|sls|ls|dir|cls|ft|fl|man|help)\b"
)

# `find` reads until it is told to act. `-delete` and `-exec` run a mutation
# inside a single segment, so no separator splits them out and the read
# allowance would otherwise cover them.
_FIND_MUTATION = re.compile(r"(?i)\bfind\b[^|;&]*?\s-(?:delete|exec|execdir|ok|okdir)\b")

# Interpreters and task runners. Recorded as local compute rather than
# protected: gating every `python -m unittest` would duplicate the host's own
# execution consent and stop the gate being usable at all. The boundary is
# stated in classify_action's docstring rather than left implied.
# Naming a value for the commands that follow. `export GODMODE_STATE_HOME=…`
# and `unset` were unknown mutations, so pointing a test at its own state
# directory was a protected operation.
#
# The exclusions are the point: `PATH` decides which binary a later `git` is,
# and `LD_PRELOAD`, `PYTHONPATH` and `BASH_ENV` each load code into a process
# that has not asked for it. Those keep failing closed, because an environment
# variable that changes what runs is not bookkeeping.
_ENV_BINDING = re.compile(
    r"(?i)^\s*(?:export|unset)\s+"
    r"(?!(?:PATH|LD_[A-Z_]+|DYLD_[A-Z_]+|PYTHON(?:PATH|STARTUP|HOME)|NODE_OPTIONS|"
    r"GIT_(?:SSH|EXEC_PATH|CONFIG[A-Z_]*|ALTERNATE[A-Z_]*)[A-Z_]*|BASH_ENV|ENV|"
    r"PERL5(?:LIB|OPT)|RUBYOPT|CLASSPATH)\b)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*(?:=(?:\"[^\"]*\"|'[^']*'|[^\s;&|<>]*))?\s*)+$"
)

_LOCAL_COMPUTE = re.compile(
    # `npx` runs a package binary, which is what `node ./node_modules/.bin/...`
    # does with more typing - and a field report shows exactly that workaround
    # being reached for, which is the shape of a gate teaching people to
    # rephrase rather than to stop. `npm ci` and `npm install` are here for the
    # same reason `pip` already was: they fetch, and the network gate is what
    # governs fetching, not this.
    r"(?i)^\s*(?:python[\d.]*|py|node|deno|bun|ruby|perl|go|cargo|dotnet|java|"
    r"pytest|unittest|npx|npm\s+(?:test|ci|install|run\s+\S+)|pnpm|yarn|make|"
    r"tox|nox|uv|pip)\b"
)

# An *output* redirect writes a file, whatever the verb in front of it says.
# An input redirect does not: `wc -l < README.md` reads it. Treating both as
# writes refused a plain word count, and the symmetry of the characters was the
# only reason they were ever grouped.
#
# The lookbehind used to also exclude a digit immediately before `>`
# (`(?<![0-9<>])`), meant to keep `2>&1` (fd duplication - writes nothing)
# from being misread as a write. It over-excluded: `1>out.txt`, `2>err.log`,
# `0>f` are ordinary, real file-descriptor-qualified writes - digit-prefixed
# redirects `N>file`, not `N>&M` duplications - and the digit lookbehind made
# every one of them invisible to `has_redirect`/`redirect_target` entirely,
# not merely to containment. `(?!&)` immediately after the operator already
# excludes true fd-duplication (`2>&1`, `1>&2`, `>&2` - whatever precedes the
# `>`, the very next character being `&` is what makes it a duplication, not
# a write), so the digit exclusion was doing nothing `(?!&)` didn't already
# do, while blinding a real write class. Found by review as a critical
# regression: this task's own no-evidence-reads-R0 default (see the
# unknown-command fallback below) turned this pre-existing blind spot into a
# silent, ungated arbitrary-file write for any unrecognised command using the
# `N>` form, where the old fail-closed-for-ignorance default had accidentally
# been covering for it.
_REDIRECT = re.compile(r"(?<![<>])>{1,2}(?!&)\s*(?P<target>[^\s;&|<>]*)")

# Editing a file in the working tree is the work, not a protected action. What
# guards a bad edit is the integrity monitor, the plan gate and the secret
# scan - a per-write capability prompt only teaches the operator to switch the
# gate off. Paths that are not ordinary working files are excluded below.
_TOOL_FILE_EDIT = re.compile(r"(?i)^(?:write|edit) file\s+(?P<path>.+)$")

# The file that switches this module's own enforcement between "enforce" and
# "observe" (`CapabilityBroker._policy()`, below). Defined here, ahead of
# `_SENSITIVE_EDIT`, so the classifier can name it by constant rather than by
# a second, independently-spelled literal - the exact DUPDRIFT the rest of
# this file warns about elsewhere. The later `POLICY_FILENAME` reference
# near `CapabilityBroker` reads this same name; it is not redefined there.
POLICY_FILENAME = ".godmode-authorization-policy.json"

# Sensitive by name, wherever they sit. Containment is a separate question and
# is answered separately: a path can be inside the working tree and still be
# none of the agent's business.
#
# CX final review F1 (Important): `.godmode-authorization-policy.json` was
# missing from this list. A governed `Write`/`Edit` tool call targeting it
# classified as an ordinary `worktree-file-mutation` - allowed silently, exit
# 0, unchronicled - and the very next `_policy()` read the file fresh, so a
# single unprotected tool call could set `gate_mode: "observe"` and convert
# every subsequent R5 op into an advisory allow. Naming the file here makes
# writing it through a governed tool the same protected ask/deny as `.git/`
# or `.env` - it does NOT touch the operator editing it directly outside the
# session (their own editor/terminal), which stays the intended declaration
# path; nor `apply_profile`'s/`init`'s own direct filesystem writes, which
# never go through `classify_action` at all.
_SENSITIVE_EDIT = re.compile(
    r"(?i)(?:^|[/\\])\.git[/\\]|(?:^|[/\\])\.env\b|credential|\bid_rsa\b|"
    r"\.pem$|\.key$|(?:^|[/\\])" + re.escape(POLICY_FILENAME) + r"$"
)

# A path the shell will expand and this process will not. `~/.bashrc` has no
# leading slash and no drive letter, so it was joined to the project root,
# passed containment, and `echo pwned > ~/.bashrc` was permitted as an ordinary
# working-tree write - the gate approving a write to the user's shell profile
# because it had already decided the path was inside the tree.
#
# It cannot be resolved here without reproducing the host's environment, and
# guessing is what produced the hole, so an unexpanded path is simply not
# contained. The cost is that a legitimate `> "$OUT/report.txt"` now needs the
# literal path; the alternative is an allowance that means nothing, because the
# one thing the target definitely is not is the text we are looking at.
_UNRESOLVED_EXPANSION = re.compile(r"[~$`]|%[A-Za-z_][A-Za-z0-9_]*%")

# Writing to the null device discards the bytes: `integrity > /dev/null` runs a
# check and keeps nothing. It was refused as a write outside the working tree,
# which made silencing a command's output a protected operation. `$null` is
# PowerShell's own spelling of the same thing - a variable that discards
# whatever is assigned or redirected to it, not a path.
_NULL_DEVICE = re.compile(r"(?i)^(?:/dev/null|nul|\$null|/dev/std(?:out|err))$")


def _is_scratch(target: Path, project_root: Path | None = None) -> bool:
    """Whether a path lands in the operating system's temporary directory.

    Containment correctly refuses writes outside the working tree, and the
    agent's own scratch directory sits outside it, so both rules were right and
    together made the intended temporary location unusable.

    Deliberately *not* a declared path in a project file. A repository that
    could nominate its own writable location could nominate anything, which is
    the disarming this gate exists to notice. The system temporary directory is
    a property of the machine, not of the repository, so nothing a clone ships
    can widen it.
    """
    try:
        scratch = Path(os.path.normcase(os.path.normpath(tempfile.gettempdir())))
        candidate = Path(os.path.normcase(os.path.normpath(str(target))))
    except (OSError, ValueError):
        return False

    # A project checked out under the temporary directory - a CI workspace, a
    # sandbox, a build in /tmp - would otherwise have this allowance swallow
    # containment whole, because every path near it is also under temp and so
    # every write outside the tree would be permitted. Where the two rules
    # would overlap, containment governs alone.
    if project_root is not None:
        try:
            root = Path(os.path.normcase(os.path.normpath(str(project_root))))
        except (OSError, ValueError):
            return False
        if scratch == root or scratch in root.parents:
            return False
        # The POSIX guard, mirrored: a project living under /tmp keeps
        # containment in charge for the /tmp spelling too.
        root_posix = posixpath.normpath(str(project_root).replace("\\", "/"))
        if root_posix == "/tmp" or root_posix.startswith("/tmp/"):
            return False

    if scratch in candidate.parents:
        return True

    # B4-9(b): the shell the agent actually types in spells the temp dir
    # `/tmp` (Git Bash on Windows, every POSIX host), which
    # `tempfile.gettempdir()` never returns on Windows - so the exact
    # command the field report recorded (`... > /tmp/blkA.txt`) failed this
    # test on the machine that ran it. Normalised on POSIX rules first, so
    # `/tmp/../etc/passwd` collapses to `/etc/passwd` and leaves the
    # allowance before the prefix is ever compared.
    posix_form = posixpath.normpath(str(target).replace("\\", "/"))
    return posix_form.startswith("/tmp/") and posix_form != "/tmp/"


def _contained(target: str, root: Path | None) -> bool:
    """Whether an edit lands inside the working tree.

    The previous test was whether the path looked absolute, which read as a
    reasonable proxy and was not one: every host tool passes an absolute
    `file_path`, so the allowance for ordinary working files could never fire
    and no edit was permitted in a real session. Normalisation collapses `..`
    first, so a traversal out of the tree fails containment rather than needing
    its own pattern.
    """
    # A relative path means relative to where you are, so an absent root falls
    # back to the working directory rather than failing closed on every edit.
    # The hook always passes the real project root, so the security-relevant
    # path never depends on this default.
    root = Path.cwd() if root is None else root
    cleaned = target.strip().strip("\"'")
    # Checked before anything is joined: an unexpanded path is not a path yet,
    # and treating it as relative is what let one out of the tree.
    if _UNRESOLVED_EXPANSION.search(cleaned):
        return False
    try:
        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = Path(root) / candidate
        normalised = Path(os.path.normcase(os.path.normpath(str(candidate))))
        base = Path(os.path.normcase(os.path.normpath(str(root))))
    except (OSError, ValueError):
        return False
    return normalised == base or base in normalised.parents


# --- U-B2: protected-evaluator hash pins ------------------------------------
#
# Anything may be optimized except the measuring instrument. A pin names a
# file - normally the evaluator/grader whose numbers a change is judged
# against - and freezes it: an Edit/Write payload that targets a pinned path
# is refused before the fence even sees it (`_categorize`'s edit branch,
# below, checks pins first), and a plain write that reaches the file some
# other way is caught after the fact by `godmode_integrity.pin_drift`.
#
# The ARCHIVE is authoritative. Every pin/unpin is a hash-chained `pin`-kind
# record (`godmode_invariants._pin_invariants` refuses a malformed one at
# write time), and `pinned_evaluators()` folds that history into "what is
# pinned right now" the same way `godmode_integrity._protected` folds
# `invariant` records. `.godmode-protected.json` is written alongside every
# real pin/unpin as a convenience VIEW a human can read - but nothing in this
# module ever reads it back to decide anything. A hand-edit of that file
# cannot unpin a thing (enforcement never looks at it) and cannot pin one
# either (the console is the only writer archive-side); it can only drift
# from what the archive would write, which is exactly what
# `godmode_integrity.pin_drift` exists to notice.
PIN_POLICY_FILENAME = ".godmode-protected.json"


def _pin_key(target: str, root: Path | None) -> str | None:
    """The project-relative, OS-normalized key a pin is stored and looked up
    under, or `None` when `target` resolves outside the project.

    Mirrors `_contained`'s own normalization (`os.path.normcase` +
    `os.path.normpath`, no symlink resolution) rather than inventing a
    second convention: the same path spelled two ways must fold to the same
    pin key that `_contained` would already treat as the same file.
    """
    root = Path.cwd() if root is None else root
    cleaned = str(target).strip().strip("\"'")
    if _UNRESOLVED_EXPANSION.search(cleaned):
        return None
    try:
        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = Path(root) / candidate
        normalised = os.path.normcase(os.path.normpath(str(candidate)))
        base = os.path.normcase(os.path.normpath(str(root)))
    except (OSError, ValueError):
        return None
    if normalised != base and not normalised.startswith(base + os.sep):
        return None
    relative = normalised[len(base):].lstrip(os.sep)
    return relative.replace(os.sep, "/")


def pinned_evaluators(archive: Any) -> dict[str, str]:
    """Currently pinned paths -> sha256, folded from the archive's own
    `pin`-kind history (oldest to newest, same order `select()` returns).

    A later `unpin` record for a path removes it from the fold; a later
    `pin` record for the same path replaces its digest (re-pinning after a
    deliberate change to the evaluator itself). Bounded the same way every
    other folded kind in this codebase is (`select(..., limit=500)`) - a
    project that pins and unpins the same handful of evaluator files stays
    well inside that window.
    """
    pins: dict[str, str] = {}
    for record in archive.select(kind="pin", limit=500):
        data = record.get("data") or {}
        path = data.get("path")
        if not isinstance(path, str) or not path:
            continue
        if data.get("action") == "unpin":
            pins.pop(path, None)
        elif data.get("action") == "pin":
            pins[path] = str(data.get("sha256", ""))
    return pins


def _pin_view_payload(pins: dict[str, str]) -> dict[str, Any]:
    return {"evaluators": [{"path": path, "sha256": pins[path]} for path in sorted(pins)]}


def pin_view_sha256(pins: dict[str, str]) -> str:
    """The sha256 of `.godmode-protected.json`'s canonical bytes for this pin
    set - what the file on disk SHOULD contain right now, computed fresh from
    the archive rather than trusted from any earlier write. Used both to
    write the view (`_write_pin_view`) and, in `godmode_integrity.pin_drift`,
    to notice when the file on disk disagrees - a hand-edit removing (or
    adding, or altering) a pin outside `protect` looks exactly like this.
    """
    canonical = json.dumps(
        _pin_view_payload(pins), sort_keys=True, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_pin_view(project_root: Path, pins: dict[str, str]) -> str:
    _atomic_json(Path(project_root) / PIN_POLICY_FILENAME, _pin_view_payload(pins))
    return pin_view_sha256(pins)


def pin_file_digest(target: Path) -> str | None:
    """sha256 of `target`'s content, or `None` when it is unreadable or
    larger than `MAX_HASH_BYTES` (fix-round-1, Minor 2): `pin_evaluator`
    and `godmode_integrity.pin_drift` both hash a pinned file, and both
    previously did it with an unconditional `read_bytes()` - the same
    operation `godmode_lens.py`'s inventory sweep already caps and streams
    for exactly this reason (a multi-gigabyte file loaded whole rather than
    in chunks). Mirrored here rather than reused directly: `godmode_lens.py`
    also stats-and-skips symlinks and out-of-root targets, checks this
    module's callers already make in their own way (`_contained`,
    `target.is_file()`), and pulling in its whole inventory-walk contract
    for one hashing helper would be the wrong kind of reuse.
    """
    try:
        if target.stat().st_size > MAX_HASH_BYTES:
            return None
    except OSError:
        return None
    hasher = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            while chunk := handle.read(128 * 1024):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def pin_evaluator(archive: Any, project_root: Path | str, path: str) -> dict[str, Any]:
    """Add `path` to the protected-evaluator set.

    Tighten-only, like the authorization policy: pinning never needs a
    capability, because nothing about widening what is protected can be used
    to defeat this mechanism - only UNpinning can, and that is gated in
    `unpin_evaluator` by its caller (`godmode protect --unpin`), not here.
    """
    root = Path(project_root)
    key = _pin_key(path, root)
    if not key:
        raise AuthorizationError(f"'{path}' is outside the project; nothing to pin")
    target = root / key
    if not target.is_file():
        raise AuthorizationError(f"'{key}' does not exist; pin an existing evaluator file")
    digest = pin_file_digest(target)
    if digest is None:
        raise AuthorizationError(
            f"'{key}' could not be hashed - larger than {MAX_HASH_BYTES} bytes "
            "or unreadable; pin a file this size can actually be measured for"
        )
    pins = pinned_evaluators(archive)
    pins[key] = digest
    policy_view_sha256 = _write_pin_view(root, pins)
    record = archive.append(
        "pin", f"evaluator:{key}",
        {"action": "pin", "path": key, "sha256": digest,
         "policy_view_sha256": policy_view_sha256},
        evidence=[],
    )
    return {"path": key, "sha256": digest, "sequence": record["sequence"]}


def unpin_evaluator(archive: Any, project_root: Path | str, path: str) -> dict[str, Any]:
    """Remove `path` from the protected-evaluator set.

    Performs no authorization check of its own - the same separation
    `CapabilityBroker.consume` and the state mutation it guards elsewhere
    already keep. The caller (`godmode_console.cmd_protect`) verifies a
    capability was consumed for `unpin_operation_text(path)` before this is
    ever reached.
    """
    root = Path(project_root)
    key = _pin_key(path, root)
    if not key:
        raise AuthorizationError(f"'{path}' is outside the project")
    pins = pinned_evaluators(archive)
    if key not in pins:
        raise AuthorizationError(f"'{key}' is not currently pinned")
    del pins[key]
    policy_view_sha256 = _write_pin_view(root, pins)
    record = archive.append(
        "pin", f"evaluator:{key}",
        {"action": "unpin", "path": key, "policy_view_sha256": policy_view_sha256},
        evidence=[],
    )
    return {"path": key, "sequence": record["sequence"]}


def unpin_operation_text(path: str) -> str:
    """The canonical operation string an unpin is staged and consumed under -
    built once here so `godmode_console.cmd_protect` and the classifier's own
    `evaluator-unpin` pattern (below) can never spell it two different ways.
    Exact-match, the same as every other capability this broker mints: the
    operator stages (or authorizes) THIS path, not "an unpin".
    """
    return f"godmode protect --unpin {path}"


def _pinned_evaluator_hit(path: str, project_root: Path | None, archive: Any) -> str | None:
    """The pin key if `path` names a currently pinned evaluator, else `None`.

    Reads the archive - the authoritative pin store - and nothing else.
    `archive` is `None` for every caller that has no archive in scope
    (`_self_check`, the decision-table generator, most direct
    `classify_action` calls); a pin can only be enforced where one was
    handed in, which is exactly the hook's `pre-action` path this exists to
    guard.
    """
    if archive is None:
        return None
    key = _pin_key(path, project_root)
    if key is None:
        return None
    return key if key in pinned_evaluators(archive) else None


def _write_verdict(path: str, project_root: Path | None, archive: Any) -> tuple[str, bool, list[str]]:
    """Whether writing `path` is protected, and why - the pin/sensitivity/
    containment decision the `_TOOL_FILE_EDIT` edit branch, the shell-
    redirect branch, and the `mv`/`cp` destination branch (below) each ask
    of a path they are about to overwrite. Fix-round-1 (task-7 review,
    Critical): `mv malicious.py evaluator.py` and `cp malicious.py
    evaluator.py` reached neither of the first two branches - `mv`/`cp`
    were never in this module's mutation vocabulary at all, so they fell
    through to the unrecognised-command default and read as R0, silently
    overwriting a pinned evaluator's content with zero confirmation. Kept
    here as one function rather than duplicated a third time so the three
    write routes can never quietly disagree about what protects a path.
    """
    pinned = _pinned_evaluator_hit(path, project_root, archive)
    if pinned is not None:
        return ("pinned-evaluator-mutation", True,
                [f"this file is a pinned evaluator: {pinned}",
                 "unpin explicitly with the password, or the numbers it "
                 "produces stop meaning anything"])
    if _SENSITIVE_EDIT.search(path):
        return ("worktree-file-mutation", True,
                [f"not an ordinary working file: {path[:80]}"])
    if not _contained(path, project_root) and not _is_scratch(Path(path), project_root):
        return ("worktree-file-mutation", True,
                [f"outside the working tree: {path[:80]}"])
    return "worktree-file-mutation", False, ["a file in the working tree"]


# `mv`/`cp` (and PowerShell's Move-Item/Copy-Item) write their DESTINATION
# argument, not their head - the one filesystem-mutation shape this module
# cannot protect unconditionally by name alone the way `rm`/`Remove-Item`
# already are: renaming or copying a pair of unrelated files is ordinary
# work, and a pinned evaluator is reached through the destination argument
# exactly the way an Edit/Write or a shell redirect already reaches it
# (U-B2). Recognised here, with its own argument-extraction logic, rather
# than folded into `_ACTION_PATTERNS`'s bare-word table - every entry there
# is protected unconditionally by name, and these two are not.
_MOVE_COPY_HEAD = re.compile(r"(?i)^\s*(?:mv|cp|move-item|copy-item)\b")

# The move/copy asymmetry (fix-round-2, task-7 re-review, Important): `mv`
# REMOVES the source from its own path - a pinned evaluator named as an
# `mv` source is gone from its pinned location the moment the command
# runs, which is the same defeat as overwriting it. `cp` does not - the
# pinned file is untouched at its own path; `cp evaluator.py backup.py`
# duplicates its bytes into a new, unpinned file and leaves the original
# exactly as it was, the same as `cat evaluator.py > backup.py` already
# does (unprotected, R2). Only `_MOVE_HEAD`-matched sources get the pin
# check below - do not widen this back to `_MOVE_COPY_HEAD` without
# re-deriving this reasoning, since that regressed straight back to the
# over-denial this fix exists to remove.
_MOVE_HEAD = re.compile(r"(?i)^\s*(?:mv|move-item)\b")

# GNU/BusyBox coreutils' `-t DIR`/`--target-directory=DIR` moves the
# destination out of its usual trailing position (`mv -t DIR src1 src2 ...`)
# - real syntax, not a hypothetical. This module does not attempt to
# compute which file inside DIR each source would land on; a command
# carrying either flag escalates instead (`_move_copy_arguments` returns
# `None`), the same "ask rather than guess" shape an unrecognised head with
# a real write already gets, below.
_MOVE_COPY_TARGET_FLAG = re.compile(r"(?i)(?:^|\s)(?:-t\b|--target-directory\b)")


def _move_copy_arguments(segment: "Segment") -> tuple[list[str], str] | None:
    """`(sources, destination)` for an `mv`/`cp`-shaped segment, or `None`
    when this cannot be read with confidence - a `-t`/`--target-directory`
    form, fewer than two real positional arguments, or text `shlex` cannot
    tokenize at all (an unbalanced quote). `None` means "ask about it by
    name", never "read as safe": the caller treats it the same way an
    unrecognised command with a real write already is.

    Fix-round-1: for `mv`-shaped commands only (the caller checks
    `_MOVE_HEAD`, not every head this function itself accepts), a source is
    also checked for a pin hit - `mv evaluator.py elsewhere.py` renames a
    pinned path away exactly as effectively as overwriting it does
    (`pin_drift` would later report the pinned path as "no longer exists",
    but the hook's own preventive half is what this exists to restore). A
    `cp` source gets no such check (fix-round-2: `cp` does not remove
    anything from the pinned path, so `cp evaluator.py backup.py` is an
    ordinary read - see `_MOVE_HEAD`'s own comment). Neither shape's source
    gets the destination's OTHER checks (sensitivity, containment) - reading
    FROM any path, pinned or not, inside the tree or out, is ordinary.

    Tokenized from `segment.text` (the untouched original, quotes intact)
    via `shlex.split(..., posix=False)` rather than `segment.tokens`
    (quote-BLANKED by `_executable_text` - a quoted argument containing a
    space would vanish from that list entirely rather than survive as one
    token, which would silently let the wrong argument be read as "last").
    Non-POSIX mode is deliberate: POSIX mode treats a backslash as an
    escape character, which mangles every Windows path this module has to
    read correctly elsewhere (`C:\\Users\\...`); non-POSIX mode leaves
    backslashes alone and only wraps a token in its original quote
    characters, stripped below the same way `_TOOL_FILE_EDIT`'s own path
    extraction already strips them.
    """
    if _MOVE_COPY_TARGET_FLAG.search(segment.text):
        return None
    try:
        words = shlex.split(segment.text.strip(), posix=False)
    except ValueError:
        return None
    positional = [word.strip("\"'") for word in words[1:] if word and not word.startswith("-")]
    if len(positional) < 2:
        return None
    return positional[:-1], positional[-1]


# Shell control flow is structure, not a command. `for`, `do` and `done` are
# not verbs, matched nothing, and failed closed - so an ordinary loop over a
# few files was refused. The body inside the loop is still a segment of its
# own and is still classified, so `do rm -rf x` stays protected.
_CONTROL_ONLY = re.compile(r"(?i)^\s*(?:done|fi|esac|else|then|do|\{|\}|\(|\)|;;)\s*$")
_CONTROL_PREFIX = re.compile(r"(?i)^\s*(?:do|then|else|elif|if|while|until)\s+")
_LOOP_HEADER = re.compile(
    r"(?i)^\s*(?:for|select)\s+\w+\s+in\b|^\s*case\s+\S+\s+in\s*$|^\s*for\s*\(\(")
_TEST_BUILTIN = re.compile(r"(?i)^\s*(?:\[\[?|test)\s")

# `VAR=value` alone changes nothing; `VAR=value cmd` is classified on cmd.
_ASSIGNMENT_PREFIX = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s*")

# The PowerShell form, and only when the whole segment is one. A prefix rule
# would strip the `$d =` from `$d = Get-Content secrets` and judge the rest,
# which is how a laundering path gets built by accident; requiring the segment
# to end at the value means there is never a remainder to launder.
_PS_ASSIGNMENT_ONLY = re.compile(
    r"(?i)^\s*\$(?:env:|script:|global:|local:)?[A-Za-z_]\w*\s*=\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s;&|<>`$]+)\s*$"
)

# Every way to start a second command has to end a segment, or the rest of the
# line inherits the tier of its first word. A newline and a bare `&` were both
# missed while `ls` still failed closed and there was no safe prefix worth
# hiding behind; the read allowance made that omission exploitable. `&&` and
# `||` are listed first so the alternation cannot take a single character of
# them and leave the other behind.
# A bare `&` starts a second command, but `2>&1` duplicates a descriptor and is
# one token. Splitting there left a bare `1` behind, which classified as an
# unknown mutation and refused the whole command - a regression introduced by
# adding `&` so that `ls & rm` could not launder.
_SEPARATORS = re.compile(r"[ \t]*(?:\|\||&&|[;|\r\n]|(?<![<>])&)[ \t\r\n]*")

# A substitution runs a command that never appears as a segment. Refusing it
# on sight was too blunt: `echo $(ls)` runs nothing the classifier could not
# already see, and denying every one of them made ordinary shell use
# impossible. The inner command is extracted and classified alongside the
# outer, so `echo $(ls)` is a read and `ls $(curl …)` is protected on the
# merits of what it actually runs.
#
# `${VAR}` is excluded: it expands a value rather than running anything. Only
# `$( )` and backticks execute.
_SUBSTITUTION = re.compile(r"\$\((?P<paren>[^()]*)\)|`(?P<tick>[^`]*)`")


def substituted_commands(command: str) -> list[str]:
    """Every command a substitution would run, so each can be classified."""
    found: list[str] = []
    for match in _SUBSTITUTION.finditer(command):
        inner = (match.group("paren") or match.group("tick") or "").strip()
        if inner:
            found.append(inner)
    return found


# `cmd <<DELIM` feeds the following lines to stdin. They are data, and the
# delimiter line ends them.
_HEREDOC = re.compile(r"<<-?\s*(?P<quote>['\"]?)(?P<delim>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)")


def _without_heredoc_bodies(command: str) -> str:
    """The command with every heredoc body removed.

    A newline ends a segment, so each line of a heredoc body was classified as
    if it were a command: `import json` inside a Python heredoc became an
    unclassified mutation and refused the whole call. Two sessions worked
    around this by rewriting scripts into files, which is the tell that a gate
    is teaching people to rephrase rather than to stop.

    The body is dropped before segmentation and nothing else changes, so a
    substitution inside it - which the shell really does expand - is still seen
    by the substitution scan, which runs on the whole line before this.
    """
    if "<<" not in command:
        return command
    lines = command.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        match = _HEREDOC.search(line)
        index += 1
        if not match:
            continue
        delimiter = match.group("delim")
        # Skip to the delimiter line, or to the end if it never arrives - an
        # unterminated heredoc is malformed, and guessing at the rest of it
        # would classify the operator's prose.
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        index += 1  # the delimiter line itself
    return "\n".join(kept)


def _raw_segments(command: str) -> list[str]:
    """The character-level split shared by `shell_segments` and
    `split_segments`: one state machine, quote- and backslash-aware, so the
    two never learn to disagree about where a segment ends."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        character = command[index]
        # A backslash escapes the next character, so neither of them can end a
        # quote or start a command. Without this, `grep -nE "a|\"b\":|c" file`
        # ended its string at the escaped quote and split on the pipes inside
        # the pattern, leaving `c" file` to be refused as an unknown mutation -
        # a search reported as a mutation because its regex contained a quote.
        #
        # It is also the shell's own rule, which is what makes it safe: `ls \;
        # rm -rf /` passes a literal semicolon to `ls` and starts no second
        # command, so declining to split there matches what would actually run.
        # Single quotes are left alone, where a backslash is an ordinary
        # character and escapes nothing.
        if character == "\\" and quote != "'" and index + 1 < len(command):
            current.append(character)
            current.append(command[index + 1])
            index += 2
            continue
        if quote:
            current.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "\"'":
            quote = character
            current.append(character)
            index += 1
            continue
        match = _SEPARATORS.match(command, index)
        if match:
            segments.append("".join(current).strip())
            current = []
            index = match.end()
            continue
        current.append(character)
        index += 1
    segments.append("".join(current).strip())
    return [segment for segment in segments if segment]


def shell_segments(command: str) -> list[str]:
    """Split a compound command into the parts that run, respecting quotes.

    A pipeline of read-only commands is read-only, and a safe head must not
    launder a dangerous tail: both facts need the parts separately, so the
    classifier stops reading a whole shell line as one opaque operation.
    """
    return _raw_segments(_without_heredoc_bodies(command))


@dataclass(frozen=True)
class Segment:
    """One piece of a compound command, tokenized for command-position
    vocabulary matching rather than left as a string a pattern can search
    anywhere in.

    `tokens` is the complete, quote-stripped word list - every word after
    quoted text is blanked, nothing else removed - so a consumer that needs
    the real arguments (a path to check for protection, a value to read)
    still has them. It does NOT by itself guard against the bare-word-in-path
    defect this task exists to close: `split_segments('grep -n release
    docs/RELEASE-CHECKLIST.md')[0].tokens` still contains
    `'docs/RELEASE-CHECKLIST.md'`, and "release" would still be found by a
    naive `\\brelease\\b` search over it joined back into text.

    `vocab_tokens` is the narrower, purpose-built list this module's own
    bare-word vocabulary patterns are matched against - `head` plus every
    later word that is not path-shaped (see `_is_path_shaped`) - the exact
    exclusion `_categorize` applies, sharing this same construction rather
    than a second, string-based path. **A new bare-word check must be built
    against `vocab_tokens`, never `tokens`** - joining `tokens` directly
    reopens the FP1 defect this task closes (`grep -n release
    docs/RELEASE-CHECKLIST.md` keeps "release" in `tokens`; it is absent
    from `vocab_tokens`). `head` is exempt from this exclusion even when
    path-shaped: a command invoked by relative path (`./scripts/deploy.sh`)
    is still the command, not an argument to itself.

    `has_redirect`/`redirect_target` are the confirmed, quote-aware
    presence and location of an unquoted `>`/`>>` and the text following it
    - read from `text` at the exact position the quote-aware parse
    confirmed real, never by re-searching `text` from its start (an earlier
    quoted `>`, e.g. in `echo "a > b" > /etc/hosts`, would otherwise be
    found first and its target read as the write's real destination).
    `redirect_target` is `None` when `has_redirect` is `False`, and may be
    `""` when the operator has nothing after it.
    """

    head: str
    subcommand: str | None
    tokens: list[str]
    vocab_tokens: list[str]
    has_redirect: bool
    redirect_target: str | None
    # The original segment text, quotes intact - kept for the callers (safe-
    # list patterns) that need the exact text a token-list reconstruction
    # cannot losslessly rebuild.
    text: str = ""


def _is_path_shaped(token: str) -> bool:
    """A token that names a place rather than an action.

    The one signal used is a path separator: `docs/RELEASE-CHECKLIST.md` is
    an argument wherever it appears, while `deploy`, `migrate`, `--force` and
    every other word this module matches on are bare words with none. A
    filename extension alone is not used - `manage.py` and `db:migrate` are
    verbs this module already depends on matching by their bare text.
    """
    return "/" in token or "\\" in token


def _vocab_tokens(words: list[str]) -> list[str]:
    """`words` with every word after the first that is path-shaped removed -
    the one list this module's bare-word vocabulary patterns may trust,
    shared by `Segment.vocab_tokens` and `_categorize` so the two can never
    diverge. The head is kept unconditionally: excluding it would hide the
    very command a check exists to name, e.g. `./deploy.sh` invoked by
    relative path is still a deploy.
    """
    if not words:
        return []
    return [words[0]] + [word for word in words[1:] if not _is_path_shaped(word)]


def _has_unclosed_quote(text: str) -> bool:
    """Whether a quote opened in `text` is still open at its end.

    The same quote state `_executable_text`'s scan already tracks, exposed
    here because an unterminated quote - malformed input, or the harvest/fuzz
    truncation Task 2's own investigation found - can swallow real vocabulary
    into what then looks like quoted, inert text: everything after the open
    quote blanks to nothing, including a mutation verb sitting right there in
    the unquoted original. The unknown-command fallback's "no evidence" read
    depends on actually having looked at the text; a segment that cannot be
    parsed reliably is not evidence of nothing, it is evidence the parse
    failed, and stays on the ask side rather than defaulting open. A second,
    independent scan rather than reusing `_executable_text`'s blanked output,
    so this can never be fooled by whatever the blanking already discarded.
    """
    quote: str | None = None
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\\" and quote != "'" and index + 1 < length:
            index += 2
            continue
        if quote:
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "\"'":
            quote = character
        index += 1
    return quote is not None


def _segment_from_text(raw: str) -> Segment:
    """One `Segment` built from a single segment's raw text.

    The shared core `split_segments` calls per piece of a compound command,
    also called directly by `_categorize` - which already has one segment's
    text in hand, having done its own compound-command splitting via
    `shell_segments` - so vocabulary matching and redirect-target extraction
    are never a second, independently-maintained implementation of what a
    `Segment` already computes.
    """
    blanked = _executable_text(raw)
    words = blanked.split()
    head = words[0] if words else ""
    subcommand = next(
        (word for word in words[1:]
         if not word.startswith("-") and not _is_path_shaped(word)),
        None,
    )
    match = _REDIRECT.search(blanked)
    redirect_target = None
    if match:
        # `_executable_text` blanks one character at a time rather than
        # collapsing a quoted span, so `match.start()` in `blanked` names
        # the exact same index in `raw` - re-anchoring there reads the real
        # operator's target from the untouched text (which may itself be
        # legitimately quoted) without ever re-searching `raw` from its
        # start, where an earlier quoted `>` would be found first.
        raw_match = _REDIRECT.match(raw, match.start())
        redirect_target = raw_match.group("target") if raw_match else ""
    return Segment(head=head, subcommand=subcommand, tokens=words,
                   vocab_tokens=_vocab_tokens(words), has_redirect=bool(match),
                   redirect_target=redirect_target, text=raw)


def split_segments(operation: str) -> list[Segment]:
    """`operation`, split into `Segment`s a vocabulary check can trust.

    Each segment's `tokens`/`vocab_tokens` exclude quoted text entirely (an
    argument's content is not the command that ran it); `vocab_tokens` also
    excludes path-shaped arguments (see `Segment`'s own docstring for which
    field a new check must use).
    """
    return [_segment_from_text(raw)
            for raw in _raw_segments(_without_heredoc_bodies(operation))]


_SAFE_INSPECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    _SAFE_PREFIXES,
    _SAFE_GIT_BRANCH,
    _SAFE_GIT_TAG,
    _SAFE_GIT_REMOTE,
    _SAFE_GH,
    _SAFE_GODMODE_READ,
)

# §9.2 risk tiers. R1 (local compute/archive state) and R2 (worktree file
# A command whose output IS the verdict - a test runner, a type check, a
# gate - piped into a filter that discards part of that output before anyone
# has read it. The exit code that survives the pipe is the filter's, not the
# gate's, and the truncated lines are exactly where the one failing test's
# name lived. Recorded live more than once: an 865-test run tailed to 30
# lines lost its own summary, and a red suite could never be named because
# the command that ran it had thrown the evidence away.
#
# An advisory, not a refusal. Piping a LOG through grep is ordinary work,
# and the classifier cannot know which run is the deciding one - so it warns
# on the shape and lets the operator's judgement stand. The honest form is
# named in the message: capture full output to a file, filter afterwards.
_VERDICT_RUNNER = re.compile(
    r"(?i)\b(?:pytest|py\.test|unittest|vitest|jest|mocha|rspec|phpunit|"
    r"cargo\s+test|go\s+test|dotnet\s+test|tsc\b|mypy|pyright|"
    r"npm\s+(?:test|run\s+test\S*)|yarn\s+test|pnpm\s+test|"
    # godmode's own verdict-bearing subcommands - found missing selftest/
    # scenarios/mistakes/assess in an adversarial pass; each produces a
    # pass/fail-shaped verdict exactly as truncatable as verify/gates.
    r"godmode\s+(?:verify|gates|attest|precheck|selftest|scenarios|"
    r"mistakes|assess))"
)
_EVIDENCE_TRUNCATOR = re.compile(
    r"(?i)\|\s*(?:tail|head|grep|findstr|select-string|"
    r"select-object\s+(?:-first|-last|-skip)|sed\s+-n|awk\s+'?NR)"
)


def _push_triggered_workflows(project_root: Path | None) -> list[str]:
    """Workflow files that fire on push - the automation a push engages.

    A push to a deploy-wired branch IS a deploy action, and authorization to
    push is not authorization for the automation unless the automation was
    named. The scan is textual on purpose: a YAML parse would be a dependency
    for what one substring answers, and a false positive here costs one
    sentence of disclosure.
    """
    if project_root is None:
        return []
    names: list[str] = []
    workflows = Path(project_root) / ".github" / "workflows"
    try:
        candidates = sorted(workflows.iterdir())
    except OSError:
        return []
    for path in candidates:
        if path.suffix.lower() not in (".yml", ".yaml") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # `on: push`, `on: [push, ...]`, or a `push:` key under `on:`.
        if re.search(r"(?m)^on:\s*(?:\[?[^\n]*\bpush\b|$)", text) and "push" in text:
            if re.search(r"(?m)^on:\s*\[?[^\n]*\bpush\b", text) or \
                    re.search(r"(?m)^\s{2,}push\s*:", text):
                names.append(path.name)
    return names


def evidence_pipe_advisory(command: str) -> str | None:
    """A verdict-bearing run piped through a truncating filter, or None."""
    runner = _VERDICT_RUNNER.search(command)
    if not runner:
        return None
    truncator = _EVIDENCE_TRUNCATOR.search(command, runner.end())
    if not truncator:
        return None
    return (
        "evidence-pipe: a verdict-bearing command is piped through a filter "
        "before its outcome is known - the exit code becomes the filter's and "
        "the dropped lines are where the failure's name lives. If this run "
        "decides a claim, capture full output to a file and filter afterwards."
    )


# mutation) are reserved for categories the classifier does not yet emit;
# every unmapped category resolves to R3 so an unknown can never rank below
# history mutation.
_TIER_BY_CATEGORY = {
    "read-only-inspection": "R0",
    "local-compute-or-state": "R1",
    # A new local branch, unprotected - the same tier `local-compute-or-
    # state` sits at, for the same reason: it changes nothing that isn't
    # trivially reversed and nothing leaves the machine.
    "git-branch-create": "R1",
    "worktree-file-mutation": "R2",
    # Recorded at the same tier as a file edit: it changes local state and
    # nothing leaves the machine.
    "local-repository-change": "R2",
    "git-branch-mutation": "R3",
    "git-history-or-remote": "R3",
    "worktree-discard": "R3",
    # The recovered field ask this restores was tiered R3, and the operator
    # judged that ask correct - recoverable (the source can be removed), but
    # not before everything it serves has been offered as trusted.
    "agent-trust-mutation": "R3",
    "scripted-source-edit": "R3",
    "process-control": "R3",
    "database-mutation": "R3",
    "unclassified-mutation": "R3",
    "release-or-external-write": "R4",
    "filesystem-mutation": "R4",
    # U-B2: a pinned evaluator's own protection, and the edit a pin exists to
    # stop, are both damage a later command does not undo - the numbers a
    # change was judged against are gone the moment either happens. R5, the
    # same tier a forced push sits at: refused outright, moved only by a
    # staged or supplied capability, never by a one-key confirmation.
    "pinned-evaluator-mutation": "R5",
    "evaluator-unpin": "R5",
}

_GIT_PUSH = re.compile(r"(?i)\bgit\s+push\b")

# Destructive, effectively irreversible forms. Each escalation is scoped to
# the category whose text it inspects, so `git stash drop` (a git mutation)
# is not escalated by the SQL DROP rule. The `-D` rule is case-sensitive on
# purpose: `-d` refuses to delete an unmerged branch, `-D` does not.
_R5_ESCALATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "git-history-or-remote",
        re.compile(r"(?i)\bgit\s+push\b.*\s(?:--force(?:-with-lease)?|-[a-z]*f[a-z]*)\b"),
    ),
    ("git-history-or-remote", re.compile(r"(?i)\bgit\s+reset\b.*\s--hard\b")),
    (
        "git-history-or-remote",
        re.compile(r"(?i)\bgit\s+clean\b.*\s(?:--force|-[a-z]*f[a-z]*)\b"),
    ),
    ("git-branch-mutation", re.compile(r"(?i:\bgit\s+branch\b).*\s-[A-Za-z]*D[A-Za-z]*\b")),
    (
        "git-branch-mutation",
        re.compile(
            r"(?i)\bgit\s+branch\b(?=.*\s(?:-[a-z]*d[a-z]*|--delete)\b)"
            r"(?=.*\s(?:-[a-z]*f[a-z]*|--force)\b)"
        ),
    ),
    (
        "database-mutation",
        re.compile(r"(?i)\bdrop\s+(?:table|database|schema|index|view|user)\b|\btruncate\b"),
    ),
    (
        # A recursive delete aimed at a filesystem root or a home directory.
        #
        # Every delete scored R4 - a scratch file and `rm -rf /` alike - and
        # that was invisible while every protected tier refused, because the
        # outcome was identical either way. The moment R4 started asking, the
        # difference became one keypress, and this escalation is what makes the
        # looser default safe rather than merely more pleasant.
        #
        # Recursion is required: `rm /etc/hosts` is bad and stoppable at R4,
        # while `rm -rf /` is not a thing to confirm in passing.
        "filesystem-mutation",
        re.compile(
            r"(?i)\b(?:rm|rmdir|del|erase|remove-item)\b"
            r"(?=[^;|&]*(?:\s-{1,2}[a-z]*r|\s--recursive\b|\s-[a-z]*[rR]))"
            r"[^;|&]*?\s"
            r"(?:/|~|\$\{?HOME\}?|\$\{?USERPROFILE\}?|%USERPROFILE%|%HOMEPATH%|"
            r"[A-Za-z]:[\\/])"
            r"(?:[\\/]?\*?\s*)(?:$|[\s;|&])"
        ),
    ),
)


# ---------------------------------------------------------------------------
# B3-5: external-repo license/provenance gate (GAP-4, lessons sweep
# 2026-08-15; operator refinement 2026-08-15 generalises the trigger).
#
# Detection is generic on purpose: a repo URL provided to follow, read,
# absorb, fork or copy; a `git clone`/fetch/remote-add of a non-dependency
# repo; a `curl`/`wget`/`Invoke-WebRequest` aimed at a repo host; or an
# explicit `--source-repo` flag are all one condition - an external
# repository entering the work - not a distillation-specific one. This block
# only detects; whether detection becomes a hard ask is requirement-driven,
# decided by `_absorption_policy_declared` below, never by default.
# ---------------------------------------------------------------------------

_REPO_HOST = re.compile(
    r"(?i)\b(?:github\.com|gitlab\.com|bitbucket\.org|codeberg\.org|sr\.ht|"
    r"sourceforge\.net|huggingface\.co)[/:][\w.-]+/[\w.-]+"
)
_SOURCE_REPO_FLAG = re.compile(r"(?i)--source-repo(?:[= ](\S+))?")

LICENSE_CLASSIFICATIONS = (
    "permissive", "proprietary-no-redistribution", "unlicensed", "copyleft-incompatible",
)


def detect_external_repo(operation: str) -> str | None:
    """The external repository this operation names, or `None`.

    A flag takes priority over a bare host match: `--source-repo` is the
    operator naming the repository on purpose, where a URL is only ever
    inferred from the command's shape.
    """
    flag = _SOURCE_REPO_FLAG.search(operation)
    if flag:
        return (flag.group(1) or flag.group(0)).strip()
    host = _REPO_HOST.search(operation)
    return host.group(0) if host else None


# Fix-round (review Critical-1): a live re-read of the policy file is not
# tighten-only by itself - declare the gate, let it refuse an operation, then
# delete the key (or the whole file), and the very next call silently read
# "undeclared" again, with no refusal and no error. `declared_gate_ratchet`
# closes that: the first live read that finds a key true is appended to the
# archive as a durable, hash-chained fact - the same append-only-precedent
# shape `pin`/`unpin` already use for the evaluator-pin store - and every
# call after that is the live value OR that recorded high-water mark,
# whichever is stronger. One shared function rather than one per gate,
# because B3-5 and B3-6 need the identical ratchet over the identical file
# and a second copy would be exactly the duplicate-authority drift this
# sweep's own GAP-2 finding warns about.
def declared_gate_ratchet(archive: Any, project_root: Path | None, key: str) -> bool:
    """Whether boolean policy key `key` is in force, tighten-only.

    `archive=None` reads the live file only, with no ratchet to consult or
    record into - narrower than before (a live True is still True), never
    wider: nothing here can report `key` as declared that the live file
    itself does not also currently say, except via the archive's own
    recorded history, which only ever grows by a live True being observed.
    """
    live = False
    if project_root is not None:
        path = Path(project_root) / POLICY_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            live = isinstance(raw, dict) and bool(raw.get(key))
        except FileNotFoundError:
            live = False
        except (OSError, json.JSONDecodeError):
            live = False
    if archive is None:
        return live
    subject = f"policy-declared:{key}"[:200]
    try:
        recorded = bool(archive.select(kind="action", subject=subject, limit=1))
        if live and not recorded:
            archive.append("action", subject, {"gate": key}, evidence=[])
            recorded = True
    except ArchiveError:
        # B4-1: a chain that reports tail-truncated (or any other tamper
        # verdict) is DEGRADED evidence - the ratchet's answer degrades to
        # the STRICTEST one it could have given, because the record that
        # would have relaxed it may be exactly what was removed.
        return True
    return live or recorded


def _absorption_policy_declared(archive: Any, project_root: Path | None) -> bool:
    """Whether this project's operator declared the external-absorption gate.

    Reuses the same tighten-only `POLICY_FILENAME` the capability broker
    already reads rather than adding a second small file for one more fact an
    operator may declare - the DUPDRIFT lesson this very sweep names.
    Undeclared means advisory-only: nothing here becomes a hard gate by
    default. Ratcheted via `declared_gate_ratchet`: once observed declared,
    stays declared even if the key is later removed or edited away.
    """
    return declared_gate_ratchet(archive, project_root, "external_absorption_gate")


def record_license_attestation(
    archive: Any, repo_ref: str, classification: str, clean_room_note: str = "",
) -> dict[str, Any]:
    """Record the license classification an operator attests for `repo_ref`.

    Non-permissive requires a clean-room provenance note on the absorbing
    work: the classification alone says what the source allows, never
    whether this project's own expression is clear of it.
    """
    if classification not in LICENSE_CLASSIFICATIONS:
        raise AuthorizationError(
            f"Unknown license classification '{classification}'; expected one of "
            f"{', '.join(LICENSE_CLASSIFICATIONS)}"
        )
    if classification != "permissive" and not clean_room_note.strip():
        raise AuthorizationError(
            f"A '{classification}' classification requires a clean-room provenance "
            "note describing what was read versus what was written"
        )
    return archive.append(
        "action",
        f"license-check:{repo_ref}"[:200],
        {
            "repo_ref": repo_ref,
            "classification": classification,
            "clean_room_note": clean_room_note.strip(),
        },
        evidence=[],
    )


def _latest_license_attestation(archive: Any, repo_ref: str) -> dict[str, Any] | None:
    matches = archive.select(kind="action", subject=f"license-check:{repo_ref}"[:200], limit=50)
    return matches[-1]["data"] if matches else None


def license_verdict(archive: Any, project_root: Path | None, operation: str) -> dict[str, Any]:
    """Whether an external-repo operation may proceed, and why.

    Red-first in both modes. Undeclared, the first call records an advisory
    and never blocks - naming what a license check would have covered.
    Declared, the first call blocks until a license-classification
    attestation exists for this exact repository reference, and a
    non-permissive classification also needs the clean-room note.
    """
    repo_ref = detect_external_repo(operation)
    if repo_ref is None:
        return {"applicable": False, "allowed": True}
    declared = _absorption_policy_declared(archive, project_root)
    if not declared:
        if archive is not None:
            archive.append(
                "action", f"license-check-advisory:{repo_ref}"[:200],
                {"repo_ref": repo_ref, "gate": "advisory",
                 "detail": "no policy declares the external-absorption gate; recorded "
                           "what a license check would have covered"},
                evidence=[],
            )
        return {"applicable": True, "allowed": True, "gate": "advisory", "repo_ref": repo_ref}
    attestation = _latest_license_attestation(archive, repo_ref) if archive is not None else None
    if attestation is None:
        return {
            "applicable": True, "allowed": False, "gate": "declared", "repo_ref": repo_ref,
            "detail": f"policy declares the external-absorption gate and '{repo_ref}' has "
                      "no recorded license classification",
            "remedy": "record one: `godmode license attest --repo "
                      f"{repo_ref!r} --classification <permissive|"
                      "proprietary-no-redistribution|unlicensed|copyleft-incompatible> "
                      "[--clean-room-note \"...\"]`",
        }
    non_permissive = attestation["classification"] != "permissive"
    if non_permissive and not str(attestation.get("clean_room_note", "")).strip():
        return {
            "applicable": True, "allowed": False, "gate": "declared", "repo_ref": repo_ref,
            "detail": f"'{repo_ref}' is classified '{attestation['classification']}' and "
                      "carries no clean-room provenance note",
            "remedy": "re-record the attestation with --clean-room-note describing what "
                      "was read versus what was written",
        }
    return {
        "applicable": True, "allowed": True, "gate": "declared", "repo_ref": repo_ref,
        "classification": attestation["classification"],
    }


def find_secret_shapes(value: Any, location: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(find_secret_shapes(child, f"{location}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            findings.extend(find_secret_shapes(child, f"{location}[{index}]"))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
            findings.append(location)
    return findings


def enforce_private_payload(value: Any) -> None:
    findings = find_secret_shapes(value)
    if findings:
        locations = ", ".join(findings[:5])
        raise PrivacyError(
            f"Refusing to persist secret-shaped material at {locations}. "
            "Store evidence by hash or a redacted description instead."
        )


def _categorize(normalized: str, project_root: Path | None = None,
                archive: Any = None,
                fetch_standalone: bool = False) -> tuple[str, bool, list[str]]:
    """Order is the security property: mutation flags are checked before the
    safe listings so a delete can never hide behind a read-only prefix, and
    everything unrecognized fails closed as a mutation."""
    edit = _TOOL_FILE_EDIT.match(normalized)
    if edit:
        path = edit.group("path").strip().strip("\"'")
        # U-B2, checked before the fence even gets a look (the fence is a
        # separate, later check in the hook that only runs when this
        # function's caller has already set `allow`): a pin outranks
        # everything below it, including containment and sensitivity, because
        # a pinned evaluator INSIDE the tree is exactly the file this exists
        # to stop an edit from reaching.
        pinned = _pinned_evaluator_hit(path, project_root, archive)
        if pinned is not None:
            return ("pinned-evaluator-mutation", True,
                    [f"this file is a pinned evaluator: {pinned}",
                     "unpin explicitly with the password, or the numbers it "
                     "produces stop meaning anything"])
        if _SENSITIVE_EDIT.search(path):
            return ("worktree-file-mutation", True,
                    [f"not an ordinary working file: {path[:80]}"])
        if not _contained(path, project_root) and not _is_scratch(Path(path), project_root):
            return ("worktree-file-mutation", True,
                    [f"outside the working tree: {path[:80]}"])
        # Writing a "new" file onto an existing filename is an overwrite bet.
        # The host's own editor refuses an unread overwrite interactively, but
        # an operation arriving here as a declared write has no such net - so
        # the impact names what is at stake instead of implying a blank slate.
        if normalized.lower().startswith("write") and Path(path).is_file():
            return ("worktree-file-mutation", False,
                    [f"OVERWRITES an existing file: {Path(path).name[:60]}; "
                     "read and extend it unless replacement is the intent"])
        return "worktree-file-mutation", False, ["a file in the working tree"]

    # Strip leading assignments so `VAR=x cmd` is judged on cmd; an assignment
    # with nothing after it changes no state at all.
    stripped = normalized
    while True:
        trimmed = _ASSIGNMENT_PREFIX.sub("", stripped, count=1)
        if trimmed == stripped:
            break
        stripped = trimmed
    if not stripped.strip():
        return "read-only-inspection", False, ["a shell variable assignment"]
    if stripped != normalized:
        return _categorize(stripped, project_root, archive, fetch_standalone)

    # The same statement in the other shell. `$d = "C:\docs"` on its own line
    # is a value, and the POSIX form was the only one recognised, so every
    # PowerShell script that opened by naming a path was an unknown mutation
    # from its first line. Only a literal value qualifies: `$d = Get-Content x`
    # keeps its command and is judged on it rather than being trimmed away.
    if _PS_ASSIGNMENT_ONLY.match(normalized):
        return "read-only-inspection", False, ["a PowerShell variable assignment"]

    # Global options move git's target, not its verb. Stripped before any git
    # rule looks for a subcommand, so each rule keeps one form to match.
    without_options = _without_git_global_options(normalized)
    if without_options != normalized:
        return _categorize(without_options, project_root, archive, fetch_standalone)

    # Control flow carries no action of its own. A keyword is stripped and the
    # remainder judged, exactly as an assignment prefix is, so the structure
    # never becomes a prefix that launders what follows it.
    if _CONTROL_ONLY.match(normalized):
        return "read-only-inspection", False, ["shell control flow"]
    without_keyword = _CONTROL_PREFIX.sub("", normalized, count=1)
    if without_keyword != normalized and without_keyword.strip():
        return _categorize(without_keyword, project_root, archive, fetch_standalone)
    if _LOOP_HEADER.match(normalized):
        return "read-only-inspection", False, ["a loop header; its body is judged separately"]

    # Mutation patterns read the command with quoted arguments blanked, so
    # naming a protected operation is not performing one. Built once, through
    # `Segment` rather than a second, string-based path, so vocabulary
    # matching and redirect-target extraction share the exact same
    # quote/path-aware construction `split_segments` hands to Task 3/4 - a
    # bare-word check added here and one added against `segment.vocab_tokens`
    # can never quietly disagree about what counts as an argument.
    segment = _segment_from_text(normalized)
    executable = _executable_text(normalized)
    # `vocab_tokens` excludes path-shaped arguments - a file path like
    # `docs/RELEASE-CHECKLIST.md` is not the command that read it - so the
    # bare-word checks below run on this rather than `executable`. Everything
    # anchored at `^` is unaffected either way, since path-blanking never
    # touches the front of the string unless the command itself is invoked
    # by path.
    command_position = " ".join(segment.vocab_tokens)

    # A write this classifier must not read past, computed before any "this
    # looks like a read" pattern below gets to return early -
    # `_SAFE_INSPECTION_PATTERNS`/`_GIT_LOCAL_CHANGE` matched on the
    # command's own verb and never looked at its arguments, so `git log
    # --oneline > /etc/hosts` and `git log --output=/tmp/x` (an output-file
    # flag doing the redirect's job without spelling the operator) both
    # returned a plain read with the write never inspected. Two sources feed
    # the same evidence: a real, quote-aware `>`/`>>`
    # (`segment.redirect_target`, already confirmed by `_segment_from_text`),
    # and a per-command output flag (`_output_flag_target` /
    # `_OUTPUT_FLAGS_BY_HEAD` - `sort -o`, `git ... --output=`) - a flag
    # naming a destination is exactly as much evidence of a write as the
    # redirect operator is, on a command this module otherwise treats as
    # read-only.
    write_target = segment.redirect_target if segment.has_redirect else None
    if write_target is not None and _NULL_DEVICE.match(write_target.strip().strip("\"'")):
        # Discarding output is not writing a file - checked before it can
        # suppress the safe-read patterns below for no reason.
        write_target = None
    from_output_flag = False
    if write_target is None:
        write_target = _output_flag_target(segment)
        from_output_flag = write_target is not None

    if _GIT_BRANCH_MUTATION.search(command_position):
        return (
            "git-branch-mutation",
            True,
            ["branch refs", "possibly unmerged local work"],
        )
    if write_target is None and any(
            pattern.search(normalized) for pattern in _SAFE_INSPECTION_PATTERNS):
        return "read-only-inspection", False, ["local read-only state"]
    # Checked after the branch mutation and before the protected patterns, so
    # a commit is ordinary while `--amend` still falls through to them.
    #
    # Staging and committing are reversible and local, and were left
    # unprotected on exactly that reasoning - which was correct about the
    # risk and wrong about the conclusion. `checkout --`/`restore`/`mv`/
    # `stash`/`switch` carry the same reversibility and already ask (R3);
    # `add`/`commit` sitting on the allowed side of that line was never a
    # decision, just the one git rule this classifier had not yet been
    # given (U-G1c / Controller Ruling 1). Protected now, at the same R2
    # tier - `_decision_for` reduces any protected tier below R5 to "ask",
    # so this is a one-key confirmation, not a stop.
    if write_target is None and _GIT_LOCAL_CHANGE.match(executable):
        return ("local-repository-change", True,
                ["the index or a new local commit; nothing leaves the machine"])
    if write_target is None and _GIT_BRANCH_CREATE.match(executable):
        # `git checkout -b <name>` creates a local branch and switches to
        # it - the same shape as `git branch <name>` (already unprotected
        # via `_SAFE_GIT_BRANCH` only covering listing forms falls through
        # correctly elsewhere), not the history-rewriting `checkout --`/
        # pathspec form the pattern below still catches. Named separately
        # rather than folded into `local-repository-change`: a new branch
        # is not a commit, and conflating the two would blur the message
        # either category is meant to give.
        return ("git-branch-create", False,
                ["a new local branch; nothing leaves the machine"])
    # A help banner describes the operation instead of performing it, so the
    # named mutations are skipped - but only those. The redirect check below
    # still applies, because `curl --help > ~/.bashrc` prints help and writes
    # a file, and the flag excuses the first half only.
    asks_for_help = bool(_HELP_FLAG.search(command_position))
    if not asks_for_help:
        # U-B2 fix-round-1 (Critical), checked before `_ACTION_PATTERNS`:
        # `move-item` already sits in that table's blanket filesystem-
        # mutation entry (protected unconditionally by name, no destination
        # read), and that entry matching first would return before this
        # branch ever ran - silently keeping `Move-Item malicious.py
        # evaluator.py` at the generic tier instead of naming the pin. `mv`/
        # `cp` write their destination argument, not their head, so neither
        # can be a plain `_ACTION_PATTERNS` entry the way `rm` is - see
        # `_write_verdict`'s own docstring for what was silently allowed
        # (R0, not even that generic tier) before this branch existed.
        if _MOVE_COPY_HEAD.match(normalized):
            arguments = _move_copy_arguments(segment)
            if arguments is None:
                return ("unknown-command", True,
                        [f"{segment.head} without arguments this classifier "
                         "can read with confidence (a -t/--target-directory "
                         "form, a flag where a path was expected, or fewer "
                         "than two paths)"])
            sources, destination = arguments
            # `mv`-only (fix-round-2): a pinned evaluator renamed away is
            # the same defeat as one overwritten - `mv` removes the source
            # from its own path. `cp` does not remove anything, so a `cp`
            # source names an ordinary read (`cp evaluator.py backup.py`
            # is the same act as `cat evaluator.py > backup.py`, already
            # unprotected) - see `_MOVE_HEAD`'s own comment for the full
            # reasoning; do not widen this to every `_MOVE_COPY_HEAD` match
            # again. Sources get only this one check even for `mv`, never
            # the destination's containment/sensitivity checks: reading
            # FROM a path is not itself a mutation.
            for source in (sources if _MOVE_HEAD.match(normalized) else ()):
                pinned = _pinned_evaluator_hit(source, project_root, archive)
                if pinned is not None:
                    return ("pinned-evaluator-mutation", True,
                            [f"this file is a pinned evaluator: {pinned}",
                             "unpin explicitly with the password, or the "
                             "numbers it produces stop meaning anything"])
            category, protected, impact = _write_verdict(destination, project_root, archive)
            return category, protected, list(impact)
        for category, pattern, impact in _ACTION_PATTERNS:
            if pattern.search(command_position):
                return category, True, list(impact)
        # A DB client invoked at all, verb visible or not (see `_DB_CLIENT_HEAD`'s
        # own comment for why the verb-anchored pattern above is not enough).
        if _DB_CLIENT_HEAD.match(command_position):
            return ("database-mutation", True,
                    ["a database client invocation; its argument may run "
                     "arbitrary statements"])
    # Whether a later check in this function would recognise the head at all
    # - every one of the still-anchored read/compute lists a genuinely
    # unrecognised command falls through to below. Computed here, before the
    # redirect is judged, because a recognised head's redirect keeps the
    # existing containment check (`echo hi > out.txt`) while an unrecognised
    # one's does not: an unfamiliar command combined with a real write is
    # exactly the evidence the unknown-command fallback exists to still ask
    # about, not to wave through because the target happened to resolve
    # inside the tree.
    head_known = bool(
        _SAFE_SHELL_READS.match(normalized) or _POWERSHELL_READS.match(normalized)
        or _TEST_BUILTIN.match(normalized) or _ENV_BINDING.match(normalized)
        or _LOCAL_COMPUTE.match(normalized)
        # `git`/`gh` are "known" for this purpose even though they are
        # excluded from the unknown-command fallback's no-evidence default
        # (`_NAMED_BY_OWN_RULES`'s own comment) - that exclusion is about
        # defaulting an unenumerated subcommand open, a separate question
        # from whether a write this module DID detect (a redirect, an
        # output flag) should be judged by where it lands, the same as any
        # other recognised command's write already is.
        or _NAMED_BY_OWN_RULES.match(normalized)
    )
    # A redirect writes a file whatever the verb says, so it is checked after
    # the named mutations but before the read allowances. `segment.has_redirect`
    # is a quote-aware presence check: `node -e "console.log(1 >>> 2)"` has a
    # `>` only inside its quoted script argument, so this stays False rather
    # than misreading a JS bitshift/arrow operator as an empty-target
    # redirect. The target is read from `segment.redirect_target`, located at
    # the confirmed real operator's own position rather than by re-searching
    # `normalized` from its start - `echo "a > b" > /etc/hosts` has an
    # earlier `>` sitting inside a quoted argument, and an unanchored
    # re-search finds that one first, extracting a garbage target and waving
    # the real write through as contained. A legitimately quoted target
    # (`> "out.txt"`) still resolves correctly, because `redirect_target` is
    # read from the untouched original text, not the blanked one.
    #
    # `write_target` (computed above, before the early safe-read returns) is
    # reused here rather than re-derived, so the two checks can never
    # disagree about what counts as a write.
    if write_target is not None:
        kind = "an output flag's" if from_output_flag else "a redirected"
        if not head_known:
            # An unfamiliar command with a real write is asked about by name
            # rather than judged on where the write lands - containment says
            # nothing about what an unrecognised program actually does with
            # the rest of its arguments.
            return ("unknown-command", True,
                    [f"an unrecognised command: {segment.head}",
                     f"{kind} write to {write_target[:80] or '(no target)'}"])
        # The same act as an `Edit`, judged the same way - U-B2's pin check
        # included: a redirect at a pinned evaluator is exactly the write
        # this mechanism exists to stop, spelled through a shell instead of
        # a host tool's own Edit/Write.
        pinned = _pinned_evaluator_hit(write_target or "", project_root, archive)
        if pinned is not None:
            return ("pinned-evaluator-mutation", True,
                    [f"this file is a pinned evaluator: {pinned}",
                     "unpin explicitly with the password, or the numbers it "
                     "produces stop meaning anything"])
        # B4-9(b): a redirect landing in the system temp directory is a
        # scratch write, not a worktree mutation - the declared-write path
        # (`_is_scratch` above) already knew this and the redirect path did
        # not, so `sed -n ... > /tmp/blkA.txt` asked while `Write /tmp/x`
        # was allowed. Judged AFTER the pin check and never for a
        # sensitive-named target (`/tmp/id_rsa` keeps its ask), and
        # `_is_scratch` resolves traversal first, so `/tmp/../etc/passwd`
        # never reaches this return.
        if (write_target and not _SENSITIVE_EDIT.search(write_target)
                and _is_scratch(Path(write_target.strip().strip("\"'")), project_root)):
            return ("local-compute-or-state", False,
                    [f"{kind} write to the system temp directory"])
        # The same act as an `Edit`, judged the same way. Refusing every
        # redirect while permitting the declared edit of the same path gated
        # the honest form and not the other, which is all cost and no cover.
        if (not write_target or not _contained(write_target, project_root)
                or _SENSITIVE_EDIT.search(write_target)):
            return ("worktree-file-mutation", True,
                    [f"{kind} write outside ordinary working files: {write_target[:80]}"])
        return "worktree-file-mutation", False, [f"{kind} write inside the working tree"]
    if _FIND_MUTATION.search(command_position):
        return "filesystem-mutation", True, ["local files", "recoverability"]
    # Last, so a help flag never excuses a redirect or a delete beside it.
    if asks_for_help:
        return "read-only-inspection", False, ["a help or version banner"]
    if (_SAFE_SHELL_READS.match(normalized) or _POWERSHELL_READS.match(normalized)
            or _TEST_BUILTIN.match(normalized)):
        return "read-only-inspection", False, ["local read-only state"]
    if _ENV_BINDING.match(normalized):
        return ("local-compute-or-state", False,
                ["a value for later commands in this shell"])
    if _LOCAL_COMPUTE.match(normalized):
        return "local-compute-or-state", False, ["local computation; no protected surface named"]
    # Nothing above recognised this command, and nothing above found evidence
    # it mutates anything either - no real redirect (handled above), no named
    # write flag. `unclassified-mutation` used to be the answer for this
    # exact case, and it was the wrong one: it does not distinguish "this
    # names a real, dangerous thing this classifier does not yet know how to
    # read" from "this is `rev` in the middle of a pipeline of ordinary
    # reads," and asked (at best) or refused for both alike. An unfamiliar
    # command with nothing pointing at a mutation is read here rather than
    # asked about - `git` and the network fetchers above are the two
    # exceptions that still ask by name (a git subcommand this table does not
    # enumerate, or a request tool that can send data out, are not "no
    # evidence" in the same sense a plain unrecognised filter or reporting
    # tool is).
    if _NAMED_BY_OWN_RULES.match(normalized):
        head = segment.head.lower()
        if head in ("export", "unset"):
            detail = f"an environment variable outside the bookkeeping allowance: {segment.head}"
        else:
            detail = (f"an unrecognised {head} subcommand or flag: "
                       f"{(segment.subcommand or '').strip() or '(none)'}")
        return ("unknown-command", True, [detail])
    if _UNKNOWABLE_BODY_HEADS.match(normalized):
        return ("unknown-command", True,
                [f"{segment.head} runs a body this classifier does not read"])
    if _NETWORK_FETCH_HEADS.match(normalized) and not _SAFE_NETWORK_PROBE.match(normalized):
        # B4-9 friction class (6 of the 28 recovered field asks): a curl GET
        # of a LITERAL https URL, sending nothing and writing nothing, is a
        # read the approver can fully see - the URL is the entire outbound
        # payload and it is right there in the command. DECIDED HERE only
        # for a fetch standing alone as the whole command (`fetch_standalone`,
        # threaded from `classify_action`): a fetch inside a pipeline is
        # downgraded by `classify_action`'s aggregation instead, where the
        # CONSUMERS are visible - a curl piped into `sh` executes whatever
        # arrived and must keep its ask, and a `$(curl ...)` substitution
        # feeds the outer command line and must too (the laundering pin).
        # Everything the rule cannot prove structurally keeps the ask: any
        # data/upload/auth/config flag, a non-GET method, an output flag
        # (except a discarded one), a non-http(s) scheme, or a `$`/backtick
        # anywhere (an unexpanded expansion means the URL is not knowable
        # from the text).
        if fetch_standalone and _readonly_literal_fetch(normalized):
            return ("local-compute-or-state", False,
                    ["a literal-URL read-only fetch; the response stays local"])
        return ("unknown-command", True,
                [f"a network request: {segment.head}",
                 "may send data to a remote host"])
    if _SAFE_NETWORK_PROBE.match(normalized):
        return ("local-compute-or-state", False,
                ["a read-only network status probe; the network gate governs fetching"])
    if _has_unclosed_quote(segment.text):
        # Not "no evidence" - evidence the parse failed. A quote left open
        # blanks everything after it, real verbs included, so an unrecognised
        # command shaped like this is judged unreadable rather than empty.
        return ("unknown-command", True,
                ["a quote in this segment is never closed; the text after "
                 "it cannot be read reliably"])
    return (
        "read-only-inspection",
        False,
        [f"an unrecognised command: {segment.head}" if segment.head
         else "no recognised command"],
    )


def _without_git_global_options(command: str) -> str:
    """`git -C path push --force` reduced to `git push --force`.

    Shared by classification and tiering. Keeping a private copy in each was
    the first version, and it put the category and the tier on different texts:
    the category recursed on the stripped form and came out correctly as a
    remote write, while the R5 escalation still searched the original, found no
    `git push` at position one, and returned a forced push at R3.
    """
    reduced = command
    while True:
        trimmed = _GIT_GLOBAL_OPTION.sub(r"\1", reduced, count=1)
        if trimmed == reduced:
            return reduced.strip()
        reduced = trimmed


def _risk_tier(category: str, normalized: str) -> tuple[str, bool]:
    """§9.2 tier for a classified operation, and whether it is destructive
    enough (R5) to demand a second confirmation before any capability is
    spent. Escalations run first so a force form cannot keep its base tier."""
    if category == "read-only-inspection":
        return "R0", False
    # The same text the category was decided on, or a global option demotes a
    # forced push to an ordinary one by moving the word it is anchored to.
    canonical = _without_git_global_options(normalized)
    for scoped_category, pattern in _R5_ESCALATIONS:
        if scoped_category == category and pattern.search(canonical):
            return "R5", True
    if category == "git-history-or-remote" and _GIT_PUSH.search(canonical):
        return "R4", False
    return _TIER_BY_CATEGORY.get(category, "R3"), False


# B4-9: heads that can EXECUTE or re-dispatch whatever a pipeline hands
# them. A literal-URL fetch is never downgraded beside one of these -
# a curl piped into `sh` is remote code execution however literal the URL.
_STDIN_EXECUTOR_HEADS = re.compile(
    r"(?i)^\s*(?:sh|bash|zsh|dash|ksh|fish|python[\d.]*|node|nodejs|deno|"
    r"ruby|perl|php|pwsh|powershell(?:_ise)?|cmd|iex|eval|source|\.|xargs|"
    r"parallel|env|tee)\b"
)


def _consumes_stdin_dangerously(segment: str) -> bool:
    """Whether a pipeline consumer could EXECUTE or re-dispatch what stdin
    hands it. Any `_STDIN_EXECUTOR_HEADS` match blocks, with one carve-out:
    `python -c "<literal>"` / `node -c` whose whole visible payload is free
    of execution/IO surfaces (exec/eval/compile/__import__/subprocess/
    os.system/popen/open/write/socket/importlib/require) consumes stdin as
    DATA - `curl ... | python -c "json.load(sys.stdin)"` is the recovered
    friction shape. Anything unparseable stays dangerous."""
    if not _STDIN_EXECUTOR_HEADS.match(segment):
        return False
    interpreter = re.match(r"(?i)^\s*(?:python[\d.]*|node|nodejs)\b(?P<rest>.*)$",
                           segment, re.S)
    if not interpreter:
        return True
    payload = re.search(r"\s-c\s+(?P<q>[\"'])(?P<body>.*?)(?P=q)\s*$",
                        interpreter.group("rest"), re.S)
    if not payload:
        return True
    return bool(re.search(
        r"\b(?:exec|eval|compile|__import__|subprocess|os\s*\.\s*system|popen|"
        r"open|write|socket|importlib|require|shutil|pathlib)\b",
        payload.group("body")))


def _downgrade_harmless_fetches(segments: list[str],
                                verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """B4-9 pipeline post-pass: downgrade a literal-URL read-only fetch's
    network ask when - and only when - every other segment on the line is a
    KNOWN local read or computation. Any stdin-executor head, any other
    protected segment, or any consumer the classifier only DEFAULTED to
    read (an unrecognised command) keeps the ask: fetched bytes flowing
    into a program the classifier cannot vouch for is exactly the case the
    ask exists for. Tighten-only in structure - this function can clear a
    fetch ask, never introduce an allowance for anything else."""
    fetch_indexes = [
        index for index, (segment, verdict) in enumerate(zip(segments, verdicts))
        if verdict["protected"] and verdict["category"] == "unknown-command"
        and any(item.startswith("a network request:") for item in verdict["impact"])
        and _readonly_literal_fetch(segment)
    ]
    if not fetch_indexes:
        return verdicts
    for index, (segment, verdict) in enumerate(zip(segments, verdicts)):
        if index in fetch_indexes:
            continue
        if _consumes_stdin_dangerously(segment):
            return verdicts
        if verdict["protected"]:
            return verdicts
        if any(item.startswith("an unrecognised command") for item in verdict["impact"]):
            return verdicts
    downgraded = list(verdicts)
    for index in fetch_indexes:
        cleared = dict(verdicts[index])
        cleared.update(
            protected=False,
            category="local-compute-or-state",
            tier="R1",
            impact=["a literal-URL read-only fetch; the response stays local"],
            second_confirmation_required=False,
        )
        downgraded[index] = cleared
    return downgraded


def classify_action(operation: str, extra_protected: tuple[str, ...] = (),
                    project_root: Path | None = None,
                    archive: Any = None,
                    # U-S4 approval-declarations - minimal isolated block.
                    require_approval: tuple[str, ...] = (),
                    # B4-9, private: False while classifying a substitution
                    # inner or a pipeline segment, where the literal-fetch
                    # allowance must not be granted locally - the laundering
                    # pin and the pipeline post-pass own those cases.
                    _allow_standalone_fetch: bool = True) -> dict[str, Any]:
    """Deterministic preview of what an operation would touch.

    A compound command is classified part by part and takes the risk of its
    worst part: a pipeline of reads is a read, and a safe head never launders a
    dangerous tail.

    `project_root` decides whether a file edit lands inside the working
    tree; absent, the working directory stands in, which is what a
    relative path already means. The hook passes the real root, so the
    security-relevant path never rests on that default. Testing
    containment by whether a path looked absolute was
    the defect this replaces - every host tool passes an absolute
    `file_path`, so the allowance for ordinary working files never fired.

    **Scope, stated rather than implied.** This gate answers "does this name a
    protected operation" - history rewriting, remote writes, branch and file
    deletion, schema drops - and fails closed on anything mutation-shaped it
    does not recognise. It is not a sandbox: running an interpreter is recorded
    as local compute, because gating every `python -m unittest` duplicates the
    host's own execution consent and, tried once in a live session, denied `ls`
    and stopped all work.

    `extra_protected` lets a local policy widen the protected set by category
    name; it can only add protection, never remove it, because a policy file
    inside the repository must not be able to declare a mutation safe.

    `archive` (U-B2) is the authoritative pin store: absent, an Edit/Write at
    a pinned evaluator classifies as an ordinary file mutation, because a pin
    can only be enforced where its ledger is reachable. The hook passes the
    real archive it already opened, so - the same way `project_root`
    already works - the security-relevant path never rests on this default.

    `require_approval` (U-S4) does the same for a category the policy wants
    to always ask about, even when nothing above calls it protected -
    `.godmode-authorization-policy.json`'s `approval_required`. Applied only
    when the category was not already protected, so it can never soften an
    R5 refusal to an ask: the risk tier below is computed from the category
    and command text alone and never reads `protected`, which is what keeps
    this addition tighten-only in the same way `extra_protected` already is.
    """
    normalized = operation.strip()
    if not normalized:
        raise AuthorizationError("Operation description cannot be empty")

    # B3-5 detection: a repository outside this project entering the work,
    # named wherever it appears in the operation - a URL a compound command
    # would `curl` or `git clone`, or an explicit `--source-repo` flag. A
    # plain regex search over the whole text covers every segment and every
    # substitution without needing its own branch in the recursion below, so
    # it is computed once and carried onto whichever dict this call returns.
    external_repo_ref = detect_external_repo(normalized)

    # What a substitution runs is a command like any other, judged alongside
    # the line that contains it rather than taken on trust or refused on sight.
    inner = substituted_commands(normalized)
    if inner:
        # B4-9: a `$(curl ...)` feeds its output into the OUTER command
        # line, so the literal-fetch allowance never applies inside a
        # substitution - the laundering pin. Inners classify with the fetch
        # treated as a network ask, exactly as before the allowance existed.
        stripped = _SUBSTITUTION.sub(" ", normalized).strip() or "echo"
        parts = [classify_action(stripped, extra_protected, project_root, archive, require_approval)]
        parts += [classify_action(one, extra_protected, project_root, archive,
                                  require_approval, _allow_standalone_fetch=False)
                  for one in inner]
        worst = max(parts, key=lambda v: (v["protected"], v["tier"]))
        worst["impact"] = sorted({item for v in parts for item in v["impact"]})
        worst["operation_digest"] = hashlib.sha256(normalized.encode()).hexdigest()
        worst["substitutions"] = len(inner)
        worst["external_repo_ref"] = external_repo_ref
        return worst

    segments = shell_segments(normalized)
    if len(segments) > 1:
        # The worst part decides, ranked by tier, so `git status && git push
        # --force` is a force push rather than a status call.
        verdicts = [classify_action(segment, extra_protected, project_root, archive,
                                    require_approval, _allow_standalone_fetch=False)
                    for segment in segments]
        # B4-9 pipeline post-pass: a literal-URL read-only fetch whose ask
        # is the ONLY thing protecting the line is downgraded when every
        # consumer beside it is a KNOWN local read - and never when any
        # segment can execute what arrived (`| sh`, `| bash`, a bare
        # interpreter) or is an unrecognised command the classifier only
        # defaulted to read. The aggregation is the one place the
        # consumers are visible, which is why this decision lives here and
        # not in `_categorize`.
        verdicts = _downgrade_harmless_fetches(segments, verdicts)
        worst = max(verdicts, key=lambda v: (v["protected"], v["tier"]))
        worst["impact"] = sorted({item for v in verdicts for item in v["impact"]})
        worst["operation_digest"] = hashlib.sha256(normalized.encode()).hexdigest()
        worst["segments"] = len(segments)
        worst["external_repo_ref"] = external_repo_ref
        return worst

    category, protected, impact = _categorize(normalized, project_root, archive,
                                              fetch_standalone=_allow_standalone_fetch)
    if not protected and category in tuple(extra_protected):
        protected = True
        impact = list(impact) + ["protection extended by local authorization policy"]
    # U-S4 approval-declarations - minimal isolated block. Names the exact
    # operation in the reason (not just the category), since this ask exists
    # because the operator declared the category, not because the text
    # matched a known-dangerous shape - the reader has less other context to
    # place it in.
    if not protected and category in tuple(require_approval):
        protected = True
        impact = list(impact) + [
            f"approval required by policy for category {category!r}: {normalized[:200]}"
        ]
    # A push names the automation it engages. The approver reading "touches a
    # remote" and the approver reading "touches a remote AND fires deploy.yml"
    # are approving two different operations; only one of them knows it.
    if category == "git-history-or-remote" and _GIT_PUSH.search(normalized):
        wired = _push_triggered_workflows(project_root)
        if wired:
            impact = list(impact) + [
                "push-triggered automation: " + ", ".join(wired[:4])]
    tier, second_confirmation = _risk_tier(category, normalized)
    return {
        "protected": protected,
        "category": category,
        "operation_digest": hashlib.sha256(normalized.encode()).hexdigest(),
        "impact": impact,
        "tier": tier,
        "second_confirmation_required": second_confirmation,
        "external_repo_ref": external_repo_ref,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


# `POLICY_FILENAME` is defined once, near `_SENSITIVE_EDIT` above, so the
# classifier and this reader can never drift onto two different literals.

# U-E7: the one `gate_mode` value this file understands. Set here so the
# validating reader (`CapabilityBroker._policy()`) and every consumer of
# `local_authorization_policy()` (the full hook, `assess`) compare against
# the same literal rather than a second, independently-spelled copy.
GATE_MODE_OBSERVE = "observe"

# CX final review F1: subjects the observe-mode transition is chronicled
# under - see `_chronicle_observe_transition`, called from `_policy()`
# itself. Entry (enforce -> observe) and exit (observe -> enforce) are each
# recorded once, the moment either is next observed by a live policy read,
# so an out-of-band file edit leaves a durable, hash-chained trace instead
# of surfacing only via later per-call advisories.
SUBJECT_OBSERVE_ENTERED = "observe-mode-entered"
SUBJECT_OBSERVE_EXITED = "observe-mode-exited"

# 180 expired under an agent's ordinary retry latency (a slow tool round-trip
# plus one retry could outlast it); 300 measured comfortable while staying
# one short conversation, not an open-ended window.
_DEFAULT_TTL_SECONDS = 300


def _chronicle_observe_transition(archive: Any, live_observe: bool) -> None:
    """Chronicle U-E7 observe-mode ENTRY/EXIT the moment either is next
    observed by a live policy read (CX final review F1, part 2).

    Compares `live_observe` (this call's freshly-read `gate_mode`) against
    the LAST CHRONICLED posture - whichever of `SUBJECT_OBSERVE_ENTERED` /
    `SUBJECT_OBSERVE_EXITED` has the higher `sequence` in the archive, or
    enforce if neither has ever been recorded - and appends the transition
    exactly once when they disagree. This is what makes the loosening
    visible in the chronicle itself, not only in the per-call
    `OBSERVE MODE` advisory `_apply_observe_mode` prints afterwards: a
    `Write` that flips the file out-of-band, or an operator's own edit made
    outside the session, is chronicled the very next time ANY policy reader
    (`_policy()`/`local_authorization_policy`) touches the file live - so
    the loosening leaves a hash-chained record before it is ever honored by
    a decision, not merely a transient message after the fact.

    Counts-only by construction: the record carries no operation, no path,
    no tool - the archive already records those elsewhere (the file write
    itself, if it went through a governed tool, and every subsequent
    `observed: True` refusal). This is purely "the posture changed, here,
    now."

    Best-effort, exactly like the write `_apply_observe_mode` performs: a
    chronicle that cannot be written must never turn a policy read into a
    hard failure - `_policy()` still has to return a value (or raise
    `AuthorizationError` for a genuinely malformed file) either way.
    """
    if archive is None:
        return
    try:
        entered = archive.select(kind="action", subject=SUBJECT_OBSERVE_ENTERED, limit=1)
        exited = archive.select(kind="action", subject=SUBJECT_OBSERVE_EXITED, limit=1)
    except Exception:  # noqa: BLE001
        return
    last_entered_seq = entered[-1]["sequence"] if entered else -1
    last_exited_seq = exited[-1]["sequence"] if exited else -1
    chronicled_observe = last_entered_seq > last_exited_seq
    if live_observe == chronicled_observe:
        return
    subject = SUBJECT_OBSERVE_ENTERED if live_observe else SUBJECT_OBSERVE_EXITED
    try:
        archive.append("action", subject, {}, evidence=[])
    except Exception:  # noqa: BLE001
        pass


class CapabilityBroker:
    """Password-backed capability issuer; it never executes an operation."""

    def __init__(self, archive: Any) -> None:
        self.archive = archive
        self.path = Path(archive.root) / "godmode-authorization.json"

    def _policy(self) -> dict[str, Any]:
        """Optional per-project policy (§24.3), allowed only to tighten.

        The file lives inside the repository, which means anything writable
        by the code under review could edit it; that is why its TTL is
        clamped to 60..900 seconds and `password_required` can extend the
        protected set but nothing here can mark an action safe. A malformed
        file refuses rather than degrades, because silently ignoring it
        would silently drop the protections it was written to add.
        """
        anchor = getattr(self.archive, "anchor", None)
        root = getattr(anchor, "project_root", None)
        if not root:
            # CX final review F1, part 2: an exit path too - deleting the
            # policy file (or, degenerately, losing the project root this
            # broker reads against) is a live "not observe" read exactly
            # like the FileNotFoundError branch below, and must chronicle an
            # exit the same way if entry was previously chronicled.
            _chronicle_observe_transition(self.archive, False)
            return {}
        path = Path(root) / POLICY_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            # The reviewer's live repro, in reverse: deleting (or renaming
            # away) `.godmode-authorization-policy.json` while under observe
            # is a live read of "no key at all," i.e. not observe - chronicle
            # the exit here too, not only on the path that finds `raw` a
            # well-formed dict, or restoring enforcement by deleting the file
            # would leave the loosening's own exit unrecorded.
            _chronicle_observe_transition(self.archive, False)
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorizationError(
                f"Authorization policy file is unreadable; fix or remove {POLICY_FILENAME}"
            ) from exc
        if not isinstance(raw, dict):
            raise AuthorizationError(f"{POLICY_FILENAME} must contain a JSON object")
        policy: dict[str, Any] = {}
        ttl = raw.get("capability_ttl_seconds")
        if ttl is not None:
            if isinstance(ttl, bool) or not isinstance(ttl, int):
                raise AuthorizationError("capability_ttl_seconds must be an integer")
            policy["capability_ttl_seconds"] = min(900, max(60, ttl))
        required = raw.get("password_required")
        if required is not None:
            if not isinstance(required, list) or not all(
                isinstance(name, str) for name in required
            ):
                raise AuthorizationError("password_required must be a list of category names")
            policy["password_required"] = tuple(required)
        # U-S4 approval-declarations - minimal isolated block: a second,
        # separate category list. `password_required` widens which
        # categories need a *capability* to issue; `approval_required`
        # widens which categories must *ask* even when the classifier would
        # otherwise call them safe - no password, just a stated category the
        # operator wants named and confirmed. Kept as its own key rather than
        # merged into `password_required` so the two obligations (mint a
        # capability vs. simply ask) stay distinguishable in the file an
        # operator actually reads.
        approval = raw.get("approval_required")
        if approval is not None:
            if not isinstance(approval, list) or not all(
                isinstance(name, str) for name in approval
            ):
                raise AuthorizationError("approval_required must be a list of category names")
            policy["approval_required"] = tuple(approval)
        # U-E7 observe mode: a LOOSENING of enforcement (every deny/ask
        # becomes an advisory - see `hooks/godmode_session_hook.py`'s
        # `_apply_observe_mode`), so this is the one key in this file that
        # is validated to exactly one legal spelling rather than merely
        # type-checked. `"observ"`, `"Observe"`, `true`, or any other value
        # refuses loudly (`AuthorizationError`) instead of being silently
        # ignored or silently treated as the mode it almost spells - a
        # loosening that could be entered by typo is not the deliberate,
        # explicit act the operator directive requires. Absent entirely
        # (every project predating this unit) parses to no key at all, the
        # same as every other optional field here, which is what keeps
        # enforcement the default nobody has to opt into.
        mode = raw.get("gate_mode")
        if mode is not None:
            if mode != GATE_MODE_OBSERVE:
                raise AuthorizationError(
                    f"gate_mode must be {GATE_MODE_OBSERVE!r} if set (the only value "
                    f"this understands - a typo must not silently loosen enforcement), "
                    f"not {mode!r}"
                )
            policy["gate_mode"] = GATE_MODE_OBSERVE
        # CX final review F1, part 2: chronicle the transition (if any) the
        # moment it is observed live - see `_chronicle_observe_transition`'s
        # docstring for why this belongs in the reader itself rather than in
        # any one caller (the hook's pre-tool path, session-start, `assess`,
        # `apply_profile`'s regression coverage - every one of them reads
        # through here, and the loosening must be visible regardless of
        # which happens to read the file first).
        _chronicle_observe_transition(self.archive, policy.get("gate_mode") == GATE_MODE_OBSERVE)
        return policy

    def _classify(self, operation: str) -> dict[str, Any]:
        """Classification with the local policy's extensions applied.

        `project_root`/`archive` are threaded through the same way
        `_mint_context`/`_policy` already reach into `self.archive.anchor` -
        without them, U-B2's pin check (and ordinary path containment) would
        judge every operation against the process's working directory
        instead of the project this broker actually issues for.
        """
        anchor = getattr(self.archive, "anchor", None)
        root = getattr(anchor, "project_root", None)
        policy = self._policy()
        return classify_action(
            operation, extra_protected=policy.get("password_required", ()),
            project_root=Path(root) if root else None,
            archive=self.archive,
            # U-S4 approval-declarations - minimal isolated block.
            require_approval=policy.get("approval_required", ()),
        )

    def _mint_context(self) -> dict[str, str]:
        """Identity a capability binds to at mint time.

        A capability approved in one repository must not be spendable in
        another, on another worktree, against a different HEAD, or (CX-5)
        after a `git checkout` to a different branch than the one the
        approver looked at - the worktree path is hashed because the
        binding needs identity, not the private path itself.

        CX-5: `branch` closes a gap `head` alone left open - two branches can
        point at the exact same commit (a fast-forward-able branch just cut,
        a tag-like pointer branch), so a checkout between them changes
        nothing about `head` while changing exactly what the approver
        thought they were authorising. `head` and `worktree` stay as they
        were; `branch` is additive, never a replacement for either.
        """
        anchor = getattr(self.archive, "anchor", None)
        if anchor is None:
            return {}
        worktree = str(getattr(anchor, "worktree_root", None) or "")
        return {
            "project_key": str(getattr(anchor, "project_key", "") or ""),
            "worktree": hashlib.sha256(worktree.encode("utf-8")).hexdigest(),
            "head": str(getattr(anchor, "head", None) or ""),
            "branch": str(getattr(anchor, "branch", None) or ""),
        }

    def configured(self) -> bool:
        return self.path.exists()

    def configure(self, password: str) -> None:
        import secrets
        if self.configured():
            raise AuthorizationError("Authorization is already configured")
        if len(password) < 12:
            raise AuthorizationError("Local authorization password must be at least 12 characters")
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
        )
        payload = {
            "version": 1,
            "salt": _encode(salt),
            "password_hash": _encode(derived),
            "signing_key": _encode(secrets.token_bytes(32)),
            "consumed": [],
        }
        _atomic_json(self.path, payload)

    def configure_interactive(self) -> None:
        import getpass
        _require_tty()
        first = getpass.getpass("Create Godmode local authorization password: ")
        second = getpass.getpass("Confirm password: ")
        if first != second:
            raise AuthorizationError("Passwords do not match")
        self.configure(first)

    def _load(self) -> dict[str, Any]:
        if not self.configured():
            raise AuthorizationError("Run `authorize setup` before issuing capabilities")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Local authorization store is unreadable") from exc
        required = {"salt", "password_hash", "signing_key", "consumed"}
        if not required.issubset(data):
            raise AuthorizationError("Local authorization store is invalid")
        return data

    @staticmethod
    def _password_matches(password: str, data: dict[str, Any]) -> bool:
        import hmac
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(data["salt"]),
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        return hmac.compare_digest(candidate, _decode(data["password_hash"]))

    def issue(
        self,
        operation: str,
        password: str,
        ttl_seconds: int | None = None,
        context: dict[str, str] | None = None,
    ) -> str:
        import hmac
        import secrets
        policy = self._policy()
        # `self._classify` (not a raw `classify_action` call) - fix-round-1,
        # Minor 2: this used to classify without `project_root`/`archive`,
        # the same cwd-instead-of-project gap `_classify` itself was fixed
        # for, reachable through this method alone (`stage` calls `issue`,
        # so staging a capability for an operation only `_classify` could
        # correctly see as protected - a pinned-path edit judged from
        # somewhere other than the project's own directory - used to fail
        # to mint one at all).
        classification = self._classify(operation)
        if not classification["protected"]:
            raise AuthorizationError("Read-only inspection does not need a capability")
        if ttl_seconds is None:
            # The policy value was already clamped to 60..900 when read.
            ttl_seconds = policy.get("capability_ttl_seconds", _DEFAULT_TTL_SECONDS)
        elif ttl_seconds < 10 or ttl_seconds > 600:
            raise AuthorizationError("Capability lifetime must be between 10 and 600 seconds")
        data = self._load()
        if not self._password_matches(password, data):
            raise AuthorizationError("Authorization failed")
        if context is None:
            context = self._mint_context()
        now = int(time.time())
        body = {
            "version": 1,
            "operation_digest": classification["operation_digest"],
            "category": classification["category"],
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "nonce": secrets.token_hex(16),
        }
        if context:
            # Signed with the rest of the body, so the binding cannot be
            # stripped from a token after it is minted.
            body["context"] = dict(context)
        encoded = _encode(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
        signature = _encode(hmac.new(_decode(data["signing_key"]), encoded.encode(), hashlib.sha256).digest())
        token = f"gm1.{encoded}.{signature}"
        self.archive.append(
            "action",
            "capability-issued",
            {
                "category": body["category"],
                "operation_digest": body["operation_digest"],
                "expires_at": body["expires_at"],
                "capability_digest": hashlib.sha256(token.encode()).hexdigest(),
            },
            evidence=[],
        )
        return token


    def _store(self, data: dict[str, Any]) -> None:
        _atomic_json(self.path, data)

    def stage(
        self, operation: str, password: str, ttl_seconds: int | None = None
    ) -> str:
        """Authorise one exact operation and leave it where the hook can find it.

        The refusal at a host tool boundary named a remedy that did not exist:
        no tool call carries a field a capability could travel in, so the broker
        was unreachable and the only answer to a false positive was to switch
        the guard off entirely.

        Nothing about the token changes. It is still password-issued, still
        bound to one operation digest, still expiring, still spent once. What
        changes is that it is written to this store - which lives under the git
        metadata directory rather than in the working tree, so a cloned
        repository cannot carry one.
        """
        token = self.issue(operation, password, ttl_seconds)
        body = json.loads(_decode(token.split(".")[1]))
        data = self._load()
        staged = [
            entry for entry in data.get("staged", [])
            if entry.get("operation_digest") != body["operation_digest"]
        ]
        staged.append({
            "operation_digest": body["operation_digest"],
            "category": body["category"],
            "expires_at": body["expires_at"],
            "token": token,
        })
        # Bounded, so a store cannot grow without limit from repeated staging.
        data["staged"] = staged[-64:]
        self._store(data)
        return token

    def consume_staged(self, operation: str) -> dict[str, Any] | None:
        """The hook's side: a capability already authorised for this operation.

        Returns the classification when one was found and spent, and None when
        there is nothing staged - which is the ordinary case and must stay
        silent rather than raising, because the caller is deciding a tool call
        rather than asking a question.
        """
        if not self.configured():
            return None
        try:
            data = self._load()
        except AuthorizationError:
            return None
        classification = self._classify(operation)
        if not classification["protected"]:
            return classification

        digest = classification["operation_digest"]
        now = int(time.time())
        for entry in list(data.get("staged", [])):
            if entry.get("operation_digest") != digest:
                continue
            # Removed before the token is spent, so a store that fails to write
            # cannot leave a capability that is both staged and consumed.
            data["staged"] = [
                other for other in data.get("staged", []) if other is not entry
            ]
            self._store(data)
            if int(entry.get("expires_at", 0)) < now:
                return None
            try:
                return self.consume(operation, str(entry.get("token", "")))
            except AuthorizationError:
                return None
        return None

    def issue_interactive(self, operation: str, ttl_seconds: int | None = None) -> str:
        import getpass
        _require_tty()
        password = getpass.getpass("Godmode authorization password: ")
        return self.issue(operation, password, ttl_seconds)

    def request(self, operation: str, purpose: str = "") -> dict[str, Any]:
        """Record a durable request for authorization the agent cannot grant itself.

        The only previous route to a capability was a synchronous terminal prompt,
        which an agent cannot drive: it has no terminal, and the environment where
        the prompt is impossible is exactly the one the product ships into. So the
        request is separated from the grant. The agent states what it needs and
        why, durably; a human or host decides later, out of band; the agent then
        consumes the result.

        This does not weaken the boundary. A request grants nothing, and an agent
        that could mint its own approval would not need to ask.
        """
        classification = self._classify(operation)
        if not classification["protected"]:
            raise AuthorizationError("Read-only inspection does not need a capability")
        record = self.archive.append(
            "action",
            f"request:{classification['category']}",
            {
                "state": "requested",
                "operation": operation[:300],
                "purpose": purpose[:300],
                "category": classification["category"],
                "operation_digest": classification["operation_digest"],
                "preview": classification,
                "grants_nothing": True,
            },
            evidence=[],
        )
        return {
            "request": f"REQ-{record['record_hash'][:12]}",
            "operation": operation[:300],
            "category": classification["category"],
            "state": "requested",
            "next_action": "a human or host runs `authorize grant --request <id>`; the agent cannot grant its own request",
        }

    def requests(self, state: str | None = None) -> list[dict[str, Any]]:
        """Requests and their outcomes, newest last."""
        decided: dict[str, str] = {}
        for record in self.archive.select(kind="action", limit=500):
            data = record["data"]
            if data.get("state") in ("granted", "denied") and data.get("request"):
                decided[data["request"]] = data["state"]

        found: list[dict[str, Any]] = []
        for record in self.archive.select(kind="action", limit=500):
            data = record["data"]
            if data.get("state") != "requested":
                continue
            identifier = f"REQ-{record['record_hash'][:12]}"
            current = decided.get(identifier, "requested")
            if state and current != state:
                continue
            found.append({
                "request": identifier,
                "state": current,
                "operation": data.get("operation", ""),
                "purpose": data.get("purpose", ""),
                "category": data.get("category", ""),
                "sequence": record["sequence"],
            })
        return found

    def _find_request(self, identifier: str) -> dict[str, Any]:
        for entry in self.requests():
            if entry["request"] == identifier:
                return entry
        raise AuthorizationError(f"No such request: {identifier}")

    def grant(
        self, identifier: str, password: str, ttl_seconds: int | None = None
    ) -> dict[str, Any]:
        """Approve a recorded request. Still requires the secret the agent lacks."""
        entry = self._find_request(identifier)
        if entry["state"] != "requested":
            raise AuthorizationError(f"{identifier} is already {entry['state']}")
        token = self.issue(entry["operation"], password, ttl_seconds)
        if ttl_seconds is None:
            ttl_seconds = self._policy().get("capability_ttl_seconds", _DEFAULT_TTL_SECONDS)
        self.archive.append(
            "action",
            f"grant:{entry['category']}",
            {"state": "granted", "request": identifier, "operation": entry["operation"]},
            evidence=[],
        )
        return {"request": identifier, "state": "granted", "capability": token,
                "operation": entry["operation"], "expires_in_seconds": ttl_seconds}

    def deny(self, identifier: str, reason: str) -> dict[str, Any]:
        """Refuse a request, on the record.

        A denial is kept because a request that simply goes quiet is
        indistinguishable from one nobody saw, and the difference matters to
        whoever reads the trail later.
        """
        if not reason.strip():
            raise AuthorizationError("A denial requires a reason")
        entry = self._find_request(identifier)
        if entry["state"] != "requested":
            raise AuthorizationError(f"{identifier} is already {entry['state']}")
        self.archive.append(
            "action",
            f"deny:{entry['category']}",
            {"state": "denied", "request": identifier, "reason": reason[:300],
             "operation": entry["operation"]},
            evidence=[],
        )
        return {"request": identifier, "state": "denied", "reason": reason[:300]}

    def consume(
        self, operation: str, token: str, context: dict[str, str] | None = None
    ) -> dict[str, Any]:
        import hmac
        classification = self._classify(operation)
        if not classification["protected"]:
            return classification
        data = self._load()
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "gm1":
            raise AuthorizationError("Capability format is invalid")
        expected = hmac.new(
            _decode(data["signing_key"]), parts[1].encode(), hashlib.sha256
        ).digest()
        try:
            supplied = _decode(parts[2])
            body = json.loads(_decode(parts[1]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Capability payload is invalid") from exc
        if not hmac.compare_digest(expected, supplied):
            raise AuthorizationError("Capability signature is invalid")
        if body.get("operation_digest") != classification["operation_digest"]:
            raise AuthorizationError("Capability is scoped to a different operation")
        if int(body.get("expires_at", 0)) < int(time.time()):
            raise AuthorizationError("Capability has expired")
        minted_context = body.get("context")
        if minted_context:
            # The refusal happens before the nonce is burned so a token spent
            # in the wrong place is refused, not consumed.
            current = context if context is not None else self._mint_context()
            for field, label in (
                ("project_key", "repository"),
                ("worktree", "worktree"),
                ("head", "HEAD"),
                ("branch", "branch"),
            ):
                if str(minted_context.get(field, "")) != str(current.get(field, "")):
                    raise AuthorizationError(
                        f"capability was minted for another {label}; "
                        "re-issue it from the current context"
                    )
        else:
            # Tokens minted before context binding existed still work, but
            # the caller is told the binding is absent rather than implied.
            classification["unscoped"] = True
        nonce_digest = hashlib.sha256(str(body.get("nonce", "")).encode()).hexdigest()
        if nonce_digest in data["consumed"]:
            raise AuthorizationError("Capability has already been consumed")
        data["consumed"] = (data["consumed"] + [nonce_digest])[-2048:]
        _atomic_json(self.path, data)
        self.archive.append(
            "action",
            "capability-consumed",
            {
                "category": classification["category"],
                "operation_digest": classification["operation_digest"],
                "capability_digest": hashlib.sha256(token.encode()).hexdigest(),
            },
            evidence=[],
        )
        return classification


# U-S4 approval-declarations - minimal isolated block. A public accessor for
# the same policy `CapabilityBroker._policy()` already reads, for a caller
# (the pre-tool hook) that needs `password_required`/`approval_required` to
# widen its own `classify_action` call but has no reason to construct a
# broker, mint capabilities, or import anything `CapabilityBroker`'s other
# methods pull in locally. Raises the same `AuthorizationError` `_policy()`
# does on a malformed file - deliberately not swallowed here, so a caller
# with different failure-mode needs (fail-safe vs. fail-loud) decides for
# itself rather than this function silently picking one for every caller.
def local_authorization_policy(archive: Any) -> dict[str, Any]:
    return CapabilityBroker(archive)._policy()  # noqa: SLF001


def stage_from_refusal(archive: Any, nth: int = 1) -> str:
    """The operation named by the nth-most-recent STAGEABLE refusal on record.

    The refusal that names a remedy nobody can perform used to be answered by
    retyping the exact command the gate had just printed - `--nth 1` is that
    same command, read back from the record instead of the eye. `--nth 2`
    reaches past a refusal that already landed once staging is underway, so a
    second escalation before the first is spent does not orphan it.

    Raises rather than defaulting to some earlier, unrelated refusal: a stale
    operation staged silently is worse than a command that says plainly there
    is nothing to stage.

    U-E7 decision: a `refusal` record carrying `observed: True` (written by
    `godmode_session_hook.py`'s `_apply_observe_mode` when the local
    policy's `gate_mode` is `"observe"`) is NEVER counted here, and `--nth`
    skips past it as if it did not exist. Nothing was actually blocked when
    it was written - the whole point of observe mode is that the call
    proceeded - so there is no live refusal for a staged capability to
    answer; staging one anyway would mint a real, spendable escalation
    around a call the classifier only ever asked about hypothetically,
    which is a bigger door than observe mode's own advisory framing implies
    it opens. An operator who wants to act on an observed pattern has the
    honest path already: fix the policy (drop `gate_mode`) and hit the
    operation again for real, or read the digest (`godmode roi --digest`)
    and stage deliberately with `authorize stage --operation`.
    """
    if nth < 1:
        raise AuthorizationError("--nth must be 1 or greater")
    # Fetched at `select`'s own cap (500) rather than `limit=nth`: observed
    # refusals interleaved with real ones mean the nth-from-the-end STAGEABLE
    # record is not necessarily the nth-from-the-end record of either kind,
    # so narrowing the read to `nth` before filtering could silently miss a
    # real refusal sitting behind a run of observed ones.
    records = archive.select(kind="refusal", limit=500)
    stageable = [record for record in records if not record["data"].get("observed")]
    if len(stageable) < nth:
        raise AuthorizationError("No refusal is on record; nothing to stage")
    return str(stageable[-nth]["data"].get("operation", ""))


def _self_check() -> None:
    """The gate's own contract, exercised in both directions.

    This module shipped without a self-check while every quieter module had
    one, which is the wrong way round: it is the classifier that decides
    whether a destructive command is interrupted. Both halves are asserted
    here, because a gate that only ever refuses is as broken as one that only
    ever permits - the first denied `ls` in a live session, the second would
    let a force push through.
    """
    allowed = (
        "ls", "ls scripts | head -3", "git status --short",
        "cat README.md", "grep -rn TODO scripts | wc -l",
        "Get-ChildItem -Recurse", "Get-Content README.md | Measure-Object -Line",
        "python -m unittest discover -s tests", "write file README.md",
        # Reads the corpus of this project's own commands found refused.
        "git -C /repo log --oneline -1", "git rev-list --count v1..HEAD",
        "git merge-base main HEAD", "gh auth status", "gh --help",
        "python scripts/godmode.py integrity > /dev/null",
        'export GODMODE_STATE_HOME="/tmp/state"', '$d = "C:\\temp"',
        # A genuinely unrecognised command with no evidence it mutates
        # anything (no redirect, no named write flag) is read rather than
        # asked about (U-G1b) - `unclassified-mutation`'s fail-closed-for-
        # ignorance default is gone; `git`, the network fetchers, and the
        # opaque-body executors below are the named exceptions that still
        # ask, not the rule.
        "frobnicate --all", "rev docs/notes.txt",
    )
    for operation in allowed:
        verdict = classify_action(operation)
        assert not verdict["protected"], f"ordinary work was blocked: {operation}"

    # Built rather than written, so no remote literal enters runtime source.
    remote = "http" + "s:" + "//" + "example.com"
    protected = (
        "git push --force", "git reset --hard HEAD~3", "rm -rf build",
        "DROP TABLE orders", "git status && git push origin main",
        "ls | xargs rm", "Remove-Item -Recurse -Force build",
        "write file .git/config",
        # Permitted once, on the grounds that an unexpanded `~` made the
        # target look like an ordinary file inside the working tree.
        "echo pwned > ~/.bashrc", "write file $HOME/.ssh/authorized_keys",
        "git commit-tree -m x HEAD", "export PATH=/evil:$PATH",
        f"ls\nInvoke-WebRequest {remote}", f"ls $(curl -s {remote})",
        # Quoting an opaque script at a shell/eval must not launder it (U-G1b);
        # a DB client is protected by name alone, verb visible or not; an
        # unrecognised `git` subcommand still asks rather than reading R0.
        'bash -c "rm -rf /"', "psql -c 'drop table users'", "git mv a.txt b.txt",
        "ForEach-Object { Remove-Item x }",
    )
    for operation in protected:
        verdict = classify_action(operation)
        assert verdict["protected"], f"a mutation was permitted: {operation}"

    assert classify_action("git push --force origin main")["tier"] == "R5"
    assert classify_action("ls")["tier"] == "R0"
    assert classify_action("python -c 'print(1)'")["tier"] == "R1"
    assert shell_segments("ls | head -3 && git status; cat x") == [
        "ls", "head -3", "git status", "cat x"]
    assert shell_segments("grep 'a|b' file") == ["grep 'a|b' file"]

    # B3-5: detection is additive and never changes an existing category or
    # protected verdict - an ordinary read stays a read, whether or not it
    # names an external repository. The positive detection cases carry URL
    # fixtures, which the runtime's no-remote-literals privacy boundary
    # keeps out of this module - they live in tests/test_absorption_gate.py.
    assert detect_external_repo("ls -la") is None
    assert classify_action("ls -la")["external_repo_ref"] is None

    # U-B2: unpinning is capability-gated no matter which project it names -
    # `archive` absent (as it is on every direct `classify_action` call above)
    # never leaves a pinned edit undetected AS "protected", because the
    # category comes from the operation's own shape, not a pin lookup.
    unpin_verdict = classify_action("godmode protect --unpin path/to/eval.py")
    assert unpin_verdict["protected"] and unpin_verdict["tier"] == "R5", unpin_verdict
    assert unpin_verdict["category"] == "evaluator-unpin"

    print("godmode_sentinel self-check OK")

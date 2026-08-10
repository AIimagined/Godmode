"""Privacy boundary and local one-use capabilities for Godmode."""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
from typing import Any

from .godmode_errors import AuthorizationError, PrivacyError


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
_QUOTED_SPAN = re.compile(r"'[^']*'|\"[^\"]*\"")


def _executable_text(command: str) -> str:
    """The command with its quoted arguments blanked out."""
    return _QUOTED_SPAN.sub(" ", command)


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
            r"\bgit\s+(?:push|merge(?!-base)|rebase|reset|clean|tag|checkout|switch|"
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
        "filesystem-mutation",
        re.compile(
            r"(?i)(?:\brm\b|\brmdir\b|\bdel\b|\bremove-item\b|\bmove-item\b|"
            r"\bshutil\.rmtree\b|\bos\.remove\b)"
        ),
        ("local files", "recoverability"),
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
    r"diff-tree|diff-index|grep|version|worktree\s+list|"
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
_REDIRECT = re.compile(r"(?<![0-9<>])>{1,2}(?!&)\s*(?P<target>[^\s;&|<>]*)")

# Editing a file in the working tree is the work, not a protected action. What
# guards a bad edit is the integrity monitor, the plan gate and the secret
# scan - a per-write capability prompt only teaches the operator to switch the
# gate off. Paths that are not ordinary working files are excluded below.
_TOOL_FILE_EDIT = re.compile(r"(?i)^(?:write|edit) file\s+(?P<path>.+)$")

# Sensitive by name, wherever they sit. Containment is a separate question and
# is answered separately: a path can be inside the working tree and still be
# none of the agent's business.
_SENSITIVE_EDIT = re.compile(
    r"(?i)(?:^|[/\\])\.git[/\\]|(?:^|[/\\])\.env\b|credential|\bid_rsa\b|"
    r"\.pem$|\.key$"
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
# which made silencing a command's output a protected operation.
_NULL_DEVICE = re.compile(r"(?i)^(?:/dev/null|nul|/dev/std(?:out|err))$")


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

    return scratch in candidate.parents


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


def shell_segments(command: str) -> list[str]:
    """Split a compound command into the parts that run, respecting quotes.

    A pipeline of read-only commands is read-only, and a safe head must not
    launder a dangerous tail: both facts need the parts separately, so the
    classifier stops reading a whole shell line as one opaque operation.
    """
    command = _without_heredoc_bodies(command)
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
_SAFE_INSPECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    _SAFE_PREFIXES,
    _SAFE_GIT_BRANCH,
    _SAFE_GIT_TAG,
    _SAFE_GIT_REMOTE,
    _SAFE_GH,
    _SAFE_GODMODE_READ,
)

# §9.2 risk tiers. R1 (local compute/archive state) and R2 (worktree file
# mutation) are reserved for categories the classifier does not yet emit;
# every unmapped category resolves to R3 so an unknown can never rank below
# history mutation.
_TIER_BY_CATEGORY = {
    "read-only-inspection": "R0",
    "local-compute-or-state": "R1",
    "worktree-file-mutation": "R2",
    # Recorded at the same tier as a file edit: it changes local state and
    # nothing leaves the machine.
    "local-repository-change": "R2",
    "git-branch-mutation": "R3",
    "git-history-or-remote": "R3",
    "worktree-discard": "R3",
    "process-control": "R3",
    "database-mutation": "R3",
    "unclassified-mutation": "R3",
    "release-or-external-write": "R4",
    "filesystem-mutation": "R4",
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


def _categorize(normalized: str, project_root: Path | None = None) -> tuple[str, bool, list[str]]:
    """Order is the security property: mutation flags are checked before the
    safe listings so a delete can never hide behind a read-only prefix, and
    everything unrecognized fails closed as a mutation."""
    edit = _TOOL_FILE_EDIT.match(normalized)
    if edit:
        path = edit.group("path").strip().strip("\"'")
        if _SENSITIVE_EDIT.search(path):
            return ("worktree-file-mutation", True,
                    [f"not an ordinary working file: {path[:80]}"])
        if not _contained(path, project_root) and not _is_scratch(Path(path), project_root):
            return ("worktree-file-mutation", True,
                    [f"outside the working tree: {path[:80]}"])
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
        return _categorize(stripped, project_root)

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
        return _categorize(without_options, project_root)

    # Control flow carries no action of its own. A keyword is stripped and the
    # remainder judged, exactly as an assignment prefix is, so the structure
    # never becomes a prefix that launders what follows it.
    if _CONTROL_ONLY.match(normalized):
        return "read-only-inspection", False, ["shell control flow"]
    without_keyword = _CONTROL_PREFIX.sub("", normalized, count=1)
    if without_keyword != normalized and without_keyword.strip():
        return _categorize(without_keyword, project_root)
    if _LOOP_HEADER.match(normalized):
        return "read-only-inspection", False, ["a loop header; its body is judged separately"]

    # Mutation patterns read the command with quoted arguments blanked, so
    # naming a protected operation is not performing one.
    executable = _executable_text(normalized)

    if _GIT_BRANCH_MUTATION.search(executable):
        return (
            "git-branch-mutation",
            True,
            ["branch refs", "possibly unmerged local work"],
        )
    if any(pattern.search(normalized) for pattern in _SAFE_INSPECTION_PATTERNS):
        return "read-only-inspection", False, ["local read-only state"]
    # Checked after the branch mutation and before the protected patterns, so
    # a commit is ordinary while `--amend` still falls through to them.
    if _GIT_LOCAL_CHANGE.match(executable):
        return ("local-repository-change", False,
                ["the index or a new local commit; nothing leaves the machine"])
    # A help banner describes the operation instead of performing it, so the
    # named mutations are skipped - but only those. The redirect check below
    # still applies, because `curl --help > ~/.bashrc` prints help and writes
    # a file, and the flag excuses the first half only.
    asks_for_help = bool(_HELP_FLAG.search(executable))
    if not asks_for_help:
        for category, pattern, impact in _ACTION_PATTERNS:
            if pattern.search(executable):
                return category, True, list(impact)
    # A redirect writes a file whatever the verb says, so it is checked after
    # the named mutations but before the read allowances.
    redirect = _REDIRECT.search(normalized)
    if redirect and _NULL_DEVICE.match(redirect.group("target").strip().strip("\"'")):
        # Discarding output is not writing a file. Checked before containment,
        # because the null device is outside every working tree and so was
        # refused as a write to somewhere it does not belong.
        redirect = None
    if redirect:
        # The same act as an `Edit`, judged the same way. Refusing every
        # redirect while permitting the declared edit of the same path gated
        # the honest form and not the other, which is all cost and no cover.
        target = redirect.group("target")
        if not target or not _contained(target, project_root) or _SENSITIVE_EDIT.search(target):
            return ("worktree-file-mutation", True,
                    [f"a redirected write outside ordinary working files: {target[:80]}"])
        return "worktree-file-mutation", False, ["a redirected write inside the working tree"]
    if _FIND_MUTATION.search(normalized):
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
    return (
        "unclassified-mutation",
        True,
        ["unknown state; fail closed until explicitly scoped"],
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


def classify_action(operation: str, extra_protected: tuple[str, ...] = (),
                    project_root: Path | None = None) -> dict[str, Any]:
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
    """
    normalized = operation.strip()
    if not normalized:
        raise AuthorizationError("Operation description cannot be empty")

    # What a substitution runs is a command like any other, judged alongside
    # the line that contains it rather than taken on trust or refused on sight.
    inner = substituted_commands(normalized)
    if inner:
        stripped = _SUBSTITUTION.sub(" ", normalized).strip() or "echo"
        parts = [classify_action(stripped, extra_protected, project_root)]
        parts += [classify_action(one, extra_protected, project_root) for one in inner]
        worst = max(parts, key=lambda v: (v["protected"], v["tier"]))
        worst["impact"] = sorted({item for v in parts for item in v["impact"]})
        worst["operation_digest"] = hashlib.sha256(normalized.encode()).hexdigest()
        worst["substitutions"] = len(inner)
        return worst

    segments = shell_segments(normalized)
    if len(segments) > 1:
        # The worst part decides, ranked by tier, so `git status && git push
        # --force` is a force push rather than a status call.
        verdicts = [classify_action(segment, extra_protected, project_root)
                    for segment in segments]
        worst = max(verdicts, key=lambda v: (v["protected"], v["tier"]))
        worst["impact"] = sorted({item for v in verdicts for item in v["impact"]})
        worst["operation_digest"] = hashlib.sha256(normalized.encode()).hexdigest()
        worst["segments"] = len(segments)
        return worst

    category, protected, impact = _categorize(normalized, project_root)
    if not protected and category in tuple(extra_protected):
        protected = True
        impact = list(impact) + ["protection extended by local authorization policy"]
    tier, second_confirmation = _risk_tier(category, normalized)
    return {
        "protected": protected,
        "category": category,
        "operation_digest": hashlib.sha256(normalized.encode()).hexdigest(),
        "impact": impact,
        "tier": tier,
        "second_confirmation_required": second_confirmation,
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


POLICY_FILENAME = ".godmode-authorization-policy.json"

_DEFAULT_TTL_SECONDS = 180


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
            return {}
        path = Path(root) / POLICY_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
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
        return policy

    def _classify(self, operation: str) -> dict[str, Any]:
        """Classification with the local policy's extensions applied."""
        return classify_action(
            operation, extra_protected=self._policy().get("password_required", ())
        )

    def _mint_context(self) -> dict[str, str]:
        """Identity a capability binds to at mint time.

        A capability approved in one repository must not be spendable in
        another, on another worktree, or against a different HEAD than the
        one the approver looked at. The worktree path is hashed because the
        binding needs identity, not the private path itself.
        """
        anchor = getattr(self.archive, "anchor", None)
        if anchor is None:
            return {}
        worktree = str(getattr(anchor, "worktree_root", None) or "")
        return {
            "project_key": str(getattr(anchor, "project_key", "") or ""),
            "worktree": hashlib.sha256(worktree.encode("utf-8")).hexdigest(),
            "head": str(getattr(anchor, "head", None) or ""),
        }

    def configured(self) -> bool:
        return self.path.exists()

    def configure(self, password: str) -> None:
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
        policy = self._policy()
        classification = classify_action(
            operation, extra_protected=policy.get("password_required", ())
        )
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
        "write file .git/config", "frobnicate --all",
        # Permitted once, on the grounds that an unexpanded `~` made the
        # target look like an ordinary file inside the working tree.
        "echo pwned > ~/.bashrc", "write file $HOME/.ssh/authorized_keys",
        "git commit-tree -m x HEAD", "export PATH=/evil:$PATH",
        f"ls\nInvoke-WebRequest {remote}", f"ls $(curl -s {remote})",
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

    print("godmode_sentinel self-check OK")

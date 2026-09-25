"""One parse of a shell command under the semantics of the shell that runs it.

The gate's classifier reads command text with Bash's lexical rules: a
backslash escapes the next character, a backtick opens a substitution, a
single quote opens a literal string. PowerShell and cmd.exe disagree on each
of those, and the disagreement is not cosmetic. Under PowerShell a backslash
is an ordinary character, so

    Get-Content "C:\\dir\\"; git push --force origin main

closes its string at the second quote and then force-pushes; read with Bash's
rules the `\\"` escapes that quote, the string never closes, and the whole
line looked like one harmless read. The reverse also happened: PowerShell's
escape character is the backtick, so `Write-Host "a`tb"` was refused as an
unclosed command substitution.

`parse(command, dialect)` lexes `command` once, under its own dialect's rules,
and lowers it to text with the same meaning under Bash's rules - the one
language the classifier reads. Every dialect then goes through the same
segment walk and the same classifier (one code path); nothing downstream
branches on the dialect. For Bash the lowering is the identity, so a Bash
command is classified exactly as it was before this module existed.

`dialect_for_tool` picks the dialect from the host's tool name. A shell tool
whose shell is not declared (a Codex, Grok or Antigravity shell tool) on
Windows may be running PowerShell or cmd, so it is read all three ways and
the stricter reading wins (`DIALECT_EITHER`).

Standard library only; no import from the rest of the runtime at module
level, so the classifier can import this without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
import sys
from typing import Iterator

BASH = "bash"
POWERSHELL = "powershell"
CMD = "cmd"
DIALECTS = (BASH, POWERSHELL, CMD)
# Not a dialect of its own: "read this as Bash, as PowerShell and as cmd,
# keep the stricter answer". Used for a shell tool whose shell is not
# declared, on Windows, where any of the three may be the one that runs it.
# The value keeps its first name so a recorded dialect still reads.
DIALECT_EITHER = "bash-or-powershell"

# The shell segment walk, shared with the classifier (godmode_sentinel),
# which imports these names from here.
_SEPARATORS = re.compile(r"[ \t]*(?:\|\||&&|[;|\r\n]|(?<![<>])&)[ \t\r\n]*")

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


def _blank_quoted_heredoc_bodies(command: str) -> str:
    """`command` with every *quoted* heredoc body blanked, length preserved.

    Incident 12459: a documentation write was refused as a filesystem mutation
    because the prose it carried described cleanup code and contained a
    backticked command name. `_without_heredoc_bodies` was not at fault - it
    strips correctly. The substitution scan was, and its sibling docstring says
    why it was built that way: a substitution inside a heredoc body "really
    does expand".

    That is true of `<<EOF` and false of `<<'EOF'`. A quoted delimiter
    suppresses **all** expansion - backticks, `$( )` and `$VAR` are literal
    text handed to the consumer untouched - so scanning a quoted body for
    substitutions reads the operator's prose as shell.

    Unquoted bodies are deliberately left intact: those do expand, and R5
    requires interpreter-fed bodies to stay scanned. A change that neutralised
    both would break the gate rather than repair it.

    Blanked in place rather than removed because the caller reuses the scan's
    `(start, end)` spans against the original string; deleting characters would
    silently shift every later offset.
    """
    if "<<" not in command:
        return command
    lines = command.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        match = _HEREDOC.search(line)
        index += 1
        if not match or not match.group("quote"):
            # No heredoc here, or an unquoted one whose body really expands.
            continue
        delimiter = match.group("delim")
        while index < len(lines) and lines[index].strip() != delimiter:
            body = lines[index]
            out.append("".join(" " if ch != "\n" else "\n" for ch in body))
            index += 1
        if index < len(lines):
            out.append(lines[index])  # the delimiter line, kept verbatim
            index += 1
    return "".join(out)


# The characters after which a `#` starts a new word, and so a comment.
_COMMENT_WORD_START = frozenset(" \t<>()")


def _walk_segments(command: str) -> Iterator[tuple[str, str | None]]:
    """The character-level split shared by `_raw_segments`, `shell_segments`,
    `split_segments` and `_component_boundaries`: one state machine, quote-
    and backslash-aware, so none of them can learn to disagree about where a
    segment ends. Yields `(text, operator)` pairs - `operator` is the
    separator that introduced `text`, `None` for the first - so a caller
    that needs to know which `&&`/`||`/`;`/`|`/`&`/newline preceded a
    component (NS-8a's component-scoped deny-by-default) reads it from the
    same single scan `_raw_segments` already trusted, rather than a second,
    hand-copied instance of this machine that could quietly drift from it."""
    current: list[str] = []
    quote: str | None = None
    index = 0
    operator: str | None = None
    # Whether the last thing consumed was an escaped pair: an escaped space
    # is part of the word, so a `#` after it is not a comment.
    escaped = False
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
            escaped = True
            index += 2
            continue
        was_escaped, escaped = escaped, False
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
        # A `#` that starts a word opens a comment that runs to the end of
        # the line: the shell reads nothing in it, so a quote character
        # there opens no string. Before this, `ls # don't` + newline +
        # `git push --force` read the apostrophe as an open quote that
        # swallowed the next line, and the push was never seen (review H1).
        # The comment text stays in the segment; only the quote tracking and
        # the separators inside it are skipped. The newline still ends it.
        if character == "#" and (not current or (current[-1] in _COMMENT_WORD_START
                                                  and not was_escaped)):
            end = index
            while end < len(command) and command[end] not in "\r\n":
                end += 1
            current.append(command[index:end])
            index = end
            continue
        match = _SEPARATORS.match(command, index)
        if match:
            text = "".join(current).strip()
            if text:
                yield text, operator
            operator = match.group(0).strip()
            current = []
            index = match.end()
            continue
        current.append(character)
        index += 1
    text = "".join(current).strip()
    if text:
        yield text, operator


# Every host shell tool this gate knows by name, and the shell that runs it.
# `None` means the host does not say which shell it uses.
SHELL_TOOL_DIALECTS: dict[str, str | None] = {
    "Bash": BASH,
    "PowerShell": POWERSHELL,
    # Codex
    "shell_command": None,
    "functions.exec": None,
    # Grok
    "run_terminal_command": None,
    # Gemini CLI
    "run_shell_command": None,
    # Antigravity
    "run_command": None,
    # Cursor
    "Shell": None,
    # The hook's own generic label.
    "shell": None,
}

# Characters that change meaning under Bash's lexer. A character one of the
# other dialects means literally is re-emitted with a backslash in front of
# it when it is one of these, so Bash reads it literally too.
_BASH_SPECIAL = frozenset("\\'\"`$;&|<>()# \t\r\n*?[]{}~!")
# Inside Bash double quotes a backslash escapes only these.
_BASH_DQ_SPECIAL = frozenset("\\\"`$\n")

# PowerShell reads the typographic quotes and dashes as their ASCII forms.
_PWSH_SINGLE_QUOTES = "\u2018\u2019\u201a\u201b"
_PWSH_DOUBLE_QUOTES = "\u201c\u201d\u201e"
_PWSH_DASHES = "\u2013\u2014\u2015"
_PWSH_TRANSLATE = str.maketrans(
    {**{ch: "'" for ch in _PWSH_SINGLE_QUOTES},
     **{ch: '"' for ch in _PWSH_DOUBLE_QUOTES},
     **{ch: "-" for ch in _PWSH_DASHES}})


def dialect_for_tool(tool: str | None, platform: str | None = None) -> str:
    """The dialect a command carried by `tool` is written in.

    `Bash` is Bash and `PowerShell` is PowerShell on every platform. A tool
    named `cmd`, or ending in `.cmd`, is cmd.exe. A known shell tool whose
    host does not declare its shell is Bash off Windows and
    `DIALECT_EITHER` on Windows. No tool name at all (a CLI preview, the
    corpus) is Bash, which is what every such caller meant before dialects
    existed.
    """
    if not tool:
        return BASH
    if tool.lower() == "cmd" or tool.lower().endswith(".cmd"):
        return CMD
    if tool in SHELL_TOOL_DIALECTS:
        declared = SHELL_TOOL_DIALECTS[tool]
        if declared is not None:
            return declared
        return DIALECT_EITHER if (platform or sys.platform) == "win32" else BASH
    return BASH


def dialects_to_read(dialect: str) -> tuple[str, ...]:
    """The concrete dialects a command in `dialect` is classified under."""
    if dialect == DIALECT_EITHER:
        return (BASH, POWERSHELL, CMD)
    if dialect not in DIALECTS:
        raise ValueError(f"unknown shell dialect: {dialect!r}")
    return (dialect,)


def _bash_literal(ch: str) -> str:
    """`ch` spelled so Bash reads it as that literal character."""
    return "\\" + ch if ch in _BASH_SPECIAL else ch


def _bash_backslash(next_ch: str | None, special: frozenset[str]) -> str:
    """A literal backslash, spelled for Bash. Before a character Bash would
    let it escape (or at the end of the text) it is doubled; before an
    ordinary character it is left single, which is how the classifier has
    always read Windows paths such as `C:\\Users\\me`."""
    if next_ch is None or next_ch in special:
        return "\\\\"
    return "\\"


def _single_quoted(content: str) -> str:
    return "'" + content.replace("'", "'\\''") + "'"


class _PowerShellLowering:
    """PowerShell text -> the same command spelled for Bash's lexer.

    Handled: the backtick escape (and backtick-newline continuation), the
    literal backslash, single-quoted strings with `''`, double-quoted strings
    with backtick escapes, `""` and live `$( )` subexpressions, both
    here-string forms, and the quote characters inside a `#` or `<# #>`
    comment. Everything else - separators, redirects, `$`, `&`, groupings -
    is passed through, so Bash's reading of it stays at least as strict as
    PowerShell's.
    """

    def __init__(self, text: str) -> None:
        self.text = text.translate(_PWSH_TRANSLATE)
        self.length = len(self.text)

    def lower(self) -> str:
        out, _, _ = self._code(0, closer=None)
        return out

    def _peek(self, index: int) -> str | None:
        return self.text[index] if index < self.length else None

    def _code(self, index: int, closer: str | None) -> tuple[str, int, bool]:
        """Lower code from `index` until an unmatched `closer` (or the end).
        Returns the lowered text, the index just past the closer, and
        whether the closer was found at all."""
        text = self.text
        out: list[str] = []
        depth = 0
        at_token_start = True
        while index < self.length:
            ch = text[index]
            if closer is not None and ch == closer and depth == 0:
                return "".join(out), index + 1, True
            if ch == "`":
                nxt = self._peek(index + 1)
                if nxt is None:
                    index += 1
                    continue
                if nxt == "\r" and self._peek(index + 2) == "\n":
                    out.append(" ")
                    index += 3
                    continue
                if nxt == "\n":
                    out.append(" ")
                    index += 2
                    continue
                out.append(_bash_literal(nxt))
                index += 2
                at_token_start = False
                continue
            if ch == "\\":
                out.append(_bash_backslash(self._peek(index + 1), _BASH_SPECIAL))
                index += 1
                at_token_start = False
                continue
            # A here-string opens only at the start of a token: `x@'` is
            # the bare word `x@` followed by an ordinary quoted string.
            if ch == "@" and at_token_start and self._peek(index + 1) in ("'", '"'):
                here = self._here_string(index)
                if here is not None:
                    lowered, index = here
                    out.append(lowered)
                    at_token_start = False
                    continue
            if ch == "'":
                lowered, index = self._single(index + 1)
                out.append(lowered)
                at_token_start = False
                continue
            if ch == '"':
                lowered, index = self._double(index + 1, terminator='"')
                out.append(lowered)
                at_token_start = False
                continue
            if ch == "<" and self._peek(index + 1) == "#":
                end = text.find("#>", index + 2)
                end = self.length if end == -1 else end + 2
                out.append(self._inert_comment(text[index:end]))
                index = end
                continue
            if ch == "#" and at_token_start:
                end = text.find("\n", index)
                end = self.length if end == -1 else end
                out.append(self._inert_comment(text[index:end]))
                index = end
                continue
            if ch == "$" and self._peek(index + 1) == "(":
                out.append(self._subexpression(index))
                index = self._subexpression_end
                at_token_start = False
                continue
            if closer is not None:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            out.append(ch)
            # `=` and `,` too: `$x=@'` and `1,@'` open a here-string.
            at_token_start = ch in " \t\r\n;|&({=,"
            index += 1
        return "".join(out), index, False

    def _subexpression(self, index: int) -> str:
        """`$( ... )` at `index`, its inside lowered as PowerShell code. An
        unclosed one stays unclosed, so the classifier's unparsed-
        substitution rule still refuses it."""
        inner, end, closed = self._code(index + 2, closer=")")
        self._subexpression_end = end
        return "$(" + inner + (")" if closed else "")

    @staticmethod
    def _inert_comment(comment: str) -> str:
        """A comment, with its quote characters made literal for Bash.

        Only the quotes are neutralised: a quote inside a comment must not
        open a string that swallows the lines after it. Separators and
        substitutions inside it are left live, so a comment this lexer
        misjudged can only make the reading stricter, never hide a command.
        """
        return "".join("\\" + ch if ch in "'\"`" else ch for ch in comment)

    def _single(self, index: int) -> tuple[str, int]:
        """A single-quoted string starting after its opening quote. `''`
        is an escaped quote. Unterminated stays unterminated for Bash too,
        so the classifier's unclosed-quote rule still fails it closed."""
        text = self.text
        content: list[str] = []
        while index < self.length:
            ch = text[index]
            if ch == "'":
                if self._peek(index + 1) == "'":
                    content.append("'")
                    index += 2
                    continue
                return _single_quoted("".join(content)), index + 1
            content.append(ch)
            index += 1
        return "'" + "".join(content).replace("'", "'\\''"), index

    def _double(self, index: int, terminator: str | None) -> tuple[str, int]:
        """A double-quoted string (or a double here-string body when
        `terminator` is None and the caller cut the body out). Backtick
        escapes, `""`, and a live `$( )` whose inside is PowerShell code."""
        text = self.text
        out: list[str] = ['"']
        while index < self.length:
            ch = text[index]
            if terminator is not None and ch == terminator:
                if self._peek(index + 1) == terminator:
                    out.append('\\"')
                    index += 2
                    continue
                out.append('"')
                return "".join(out), index + 1
            if ch == "`":
                nxt = self._peek(index + 1)
                if nxt is None:
                    index += 1
                    continue
                if nxt in _BASH_DQ_SPECIAL:
                    out.append("\\" + nxt)
                elif nxt.isalpha() or nxt == "0":
                    # `n, `t, `r, `0 ... - a control character. Its exact
                    # value never matters to the classifier.
                    out.append(" ")
                else:
                    out.append(nxt)
                index += 2
                continue
            if ch == "\\":
                out.append(_bash_backslash(self._peek(index + 1), _BASH_DQ_SPECIAL | {'"'}))
                index += 1
                continue
            if ch == "$" and self._peek(index + 1) == "(":
                out.append(self._subexpression(index))
                index = self._subexpression_end
                continue
            if ch == '"':
                # Only inside a here-string body: a literal quote.
                out.append('\\"')
                index += 1
                continue
            out.append(ch)
            index += 1
        if terminator is None:
            out.append('"')
        return "".join(out), index

    def _here_string(self, index: int) -> tuple[str, int] | None:
        """`@'...'@` or `@"..."@`: the opener must end its line, and the
        body ends at a line that starts with the matching closer. Returns
        None when the opener is not a real here-string header."""
        text = self.text
        quote = text[index + 1]
        cursor = index + 2
        while cursor < self.length and text[cursor] in " \t":
            cursor += 1
        if text.startswith("\r\n", cursor):
            body_start = cursor + 2
        elif text.startswith("\n", cursor):
            body_start = cursor + 1
        else:
            return None
        closer = quote + "@"
        search = body_start
        while True:
            line_end = text.find("\n", search)
            line = text[search:] if line_end == -1 else text[search:line_end]
            if line.startswith(closer):
                body = text[body_start:max(body_start, search - 1)].rstrip("\r")
                end = search + len(closer)
                break
            if line_end == -1:
                # Never closed: keep it unterminated for Bash as well.
                body = text[body_start:]
                end = self.length
                if quote == "'":
                    return "'" + body.replace("'", "'\\''"), end
                lowered, _ = _PowerShellLowering(body)._double(0, terminator=None)
                return lowered[:-1], end
            search = line_end + 1
        if quote == "'":
            return _single_quoted(body), end
        lowered, _ = _PowerShellLowering(body)._double(0, terminator=None)
        return lowered, end


def _lower_cmd(text: str) -> str:
    """cmd.exe text -> the same command spelled for Bash's lexer.

    `^` escapes the next character (and `^` before a newline continues the
    line); a double-quoted string has no escapes and ends at the next quote
    or the end of the line; a single quote, a backtick and `$` are ordinary
    characters; a backslash is literal. `%VAR%` is left as written, which the
    classifier already treats as an unresolved expansion. Separators pass
    through - `;` included, which cmd does not treat as one, so Bash's
    reading can only be stricter.
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        nxt = text[index + 1] if index + 1 < length else None
        if ch == "^":
            if nxt is None:
                index += 1
            elif nxt == "\n":
                out.append(" ")
                index += 2
            elif nxt == "\r" and index + 2 < length and text[index + 2] == "\n":
                out.append(" ")
                index += 3
            else:
                out.append(_bash_literal(nxt))
                index += 2
            continue
        if ch == '"':
            end = index + 1
            content: list[str] = []
            while end < length and text[end] not in '"\n':
                inner = text[end]
                if inner == "\\":
                    following = text[end + 1] if end + 1 < length else None
                    content.append(_bash_backslash(following, _BASH_DQ_SPECIAL | {'"'}))
                elif inner in "\"`$":
                    content.append("\\" + inner)
                else:
                    content.append(inner)
                end += 1
            out.append('"' + "".join(content) + '"')
            index = end + 1 if end < length and text[end] == '"' else end
            continue
        if ch in "'`$":
            out.append("\\" + ch)
            index += 1
            continue
        if ch == "\\":
            out.append(_bash_backslash(nxt, _BASH_SPECIAL))
            index += 1
            continue
        out.append(ch)
        index += 1
    return "".join(out)


def lower(command: str, dialect: str) -> str:
    """`command`, written in `dialect`, spelled with the same meaning for
    Bash's lexer. The identity for Bash."""
    if dialect == BASH:
        return command
    if dialect == POWERSHELL:
        return _PowerShellLowering(command).lower()
    if dialect == CMD:
        return _lower_cmd(command)
    raise ValueError(f"unknown shell dialect: {dialect!r}")


# A command name a shell would look up: no expansion, space or operator.
_PLAIN_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./+-]*$")
_WORD_END = frozenset(" \t\r\n;&|<>()")


def _first_word(segment: str) -> tuple[bool, str, str, str] | None:
    """`(call, raw, name, rest)` for the command word of `segment` (Bash
    spelling): whether a leading `&` call operator preceded it, the word as
    written, the word with its quoting resolved, and the text after it.
    None when a quote in the word never closes."""
    text = segment.lstrip()
    # PowerShell's call operator: `& 'git' push` runs git. The segment walk
    # leaves a leading `&` in place when nothing precedes it.
    call = text.startswith("&")
    if call:
        text = text[1:].lstrip()
    quote: str | None = None
    resolved: list[str] = []
    index = 0
    while index < len(text):
        ch = text[index]
        if quote == "'":
            if ch == "'":
                quote = None
            else:
                resolved.append(ch)
        elif quote == '"':
            if ch == "\\" and index + 1 < len(text) and text[index + 1] in '"\\$`':
                resolved.append(text[index + 1])
                index += 1
            elif ch == '"':
                quote = None
            else:
                resolved.append(ch)
        elif ch == "\\" and index + 1 < len(text):
            resolved.append(text[index + 1])
            index += 1
        elif ch in "'\"":
            quote = ch
        elif ch in _WORD_END:
            break
        else:
            resolved.append(ch)
        index += 1
    if quote is not None:
        return None
    return call, text[:index], "".join(resolved), text[index:]


def resolved_head(segment: str) -> str | None:
    """`segment` (Bash spelling) with its command word written plainly, when
    that word was quoted or escaped - `'git' push`, `"git" push`, `g\\it
    push` all run `git`. None when the head is already plain, cannot be
    resolved (an unclosed quote), or resolves to anything but a plain
    command name. The classifier's head patterns read the resolved name, so
    quoting the name no longer hides the command (review H2-parse)."""
    word = _first_word(segment)
    if word is None:
        return None
    call, raw, name, rest = word
    if (name == raw and not call) or not _PLAIN_NAME.match(name):
        return None
    return name + rest


_EXECUTABLE_SUFFIX = re.compile(r"(?i)\.(?:exe|cmd|bat|com)$")


def head_readings(segment: str) -> list[str]:
    """Other spellings of `segment` naming the program its command word
    runs, for the classifier to judge alongside the text itself. The
    stricter reading wins, so none of these can make a command pass:

    - the head with its quoting resolved (`'git' push` -> `git push`);
    - a head that is a path, quoted or not, read by its program name
      (`'/usr/bin/git' push`, `& "C:/Program Files/git.exe" push` ->
      `git push`; review round 2, F3). The base name is cut from the word
      as written, so a Windows path's backslashes still separate.
    """
    readings: list[str] = []
    plain = resolved_head(segment)
    if plain is not None:
        readings.append(plain)
    word = _first_word(segment)
    if word is not None:
        _call, raw, _name, rest = word
        written = raw.replace("'", "").replace('"', "")
        base = _EXECUTABLE_SUFFIX.sub("", re.split(r"[\\/]", written)[-1])
        if (base != written and base and not base.startswith(".")
                and _PLAIN_NAME.match(base)):
            reading = base + rest
            if reading not in readings:
                readings.append(reading)
    return readings


# ---------------------------------------------------------------------------
# Command words that are not written as a plain name.
#
# `head_readings` above resolves quoting and paths. The forms below name the
# program some other way - an expansion, PowerShell's call and dot-source
# operators, `Start-Process`, a pseudo-terminal wrapper - and each one was
# read as an unrecognised command, which the classifier's no-evidence
# default allows. Each form is either normalised to the command it runs
# (an extra reading; the stricter reading still wins, so a reading can only
# raise a verdict) or, where the program is not knowable from the text,
# reported as opaque.
# ---------------------------------------------------------------------------

# A PowerShell operator in the second word: `$x -eq 1` compares, it runs
# nothing.
_PWSH_OPERATOR = re.compile(
    r"(?i)^-(?:[ci]?(?:eq|ne|gt|ge|lt|le|like|notlike|match|notmatch|contains|"
    r"notcontains|in|notin|replace|split)|join|is|isnot|as|band|bor|bxor|bnot|"
    r"shl|shr|and|or|xor|not|f)$")
# `$x = ...`, `$env:X += ...`, `$x.Name = ...`, `$x[0] = ...`: an assignment,
# the one PowerShell statement shape that starts with a variable and runs
# nothing of its own. Its value, when it is a command, is judged elsewhere.
_VARIABLE_ASSIGNMENT = re.compile(
    r"^\$(?:\{[^}]*\}|[\w:]+)(?:\[[^\]]*\]|\.\w+)*\s*[-+*/%]?=(?!=)")
_VARIABLE_WORD = re.compile(r"^\$(?:\{[^}]*\}|[A-Za-z_][\w:]*|[0-9@*#?$!-])$")
_EXPANSION_DEFAULT = re.compile(r"^\$\{[A-Za-z_]\w*:?[-=+?](?P<word>[^}]*)\}$")
_ANSI_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
                 "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v",
                 "\\": "\\", "'": "'", '"': '"', "?": "?"}
_GET_COMMAND = re.compile(
    r"(?i)^\(\s*(?:Get-Command|gcm)\s+(?:-Name\s+)?(?P<q>['\"]?)(?P<name>[A-Za-z0-9_.\\/:+-]+)"
    r"(?P=q)(?:\s+-\w+(?:\s+[\w-]+)?)*\s*\)\s*(?:\.(?:Source|Path|Definition|Name))?$")
_START_PROCESS = frozenset({"start-process", "start", "saps"})
# `Start-Process` parameters that take a value, by full name. PowerShell
# accepts any unambiguous prefix, so a written parameter is matched as one.
_START_PROCESS_VALUED = ("filepath", "argumentlist", "args", "workingdirectory", "verb",
                         "windowstyle", "redirectstandardoutput", "redirectstandarderror",
                         "redirectstandardinput", "credential", "environment")
# Wrappers that run a command under a pseudo-terminal. A terminal is what
# an operator-only prompt checks for, so running one of those verbs under a
# wrapper is not the operator at a keyboard.
_PTY_WRAPPERS = frozenset({"script", "winpty", "unbuffer", "expect", "pty", "ptyrun"})


def _call_operator(segment: str) -> tuple[str | None, str]:
    """`(operator, text)`: PowerShell's call operator `&` or the dot-source
    `.` (Bash's `source`) in front of the command word, and the text after
    it. `(None, segment)` when neither is there."""
    text = segment.lstrip()
    if text.startswith("&") and not text.startswith("&&"):
        return "&", text[1:].lstrip()
    if len(text) > 1 and text[0] == "." and text[1] in " \t":
        return ".", text[1:].lstrip()
    return None, text


def _leading_word(text: str) -> tuple[str, str]:
    """The first word of `text` as written (quotes and `${...}` braces kept
    whole) and the text after it."""
    index = 0
    quote: str | None = None
    depth = 0
    while index < len(text):
        ch = text[index]
        if quote:
            if ch == "\\" and quote != "'" and index + 1 < len(text):
                index += 2
                continue
            if ch == quote:
                quote = None
        elif ch == "\\" and index + 1 < len(text):
            index += 2
            continue
        elif ch in "'\"":
            quote = ch
        elif ch in "({":
            depth += 1
        elif ch in ")}":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in _WORD_END:
            break
        index += 1
    return text[:index], text[index:]


def _unwrapped_double_quotes(word: str) -> str:
    """`word` without one pair of enclosing double quotes."""
    if len(word) > 1 and word[0] == '"' and word[-1] == '"' and '"' not in word[1:-1]:
        return word[1:-1]
    return word


def _ansi_c(body: str) -> str:
    """The value of a Bash `$'...'` string's body."""
    out: list[str] = []
    index = 0
    while index < len(body):
        ch = body[index]
        if ch != "\\" or index + 1 >= len(body):
            out.append(ch)
            index += 1
            continue
        nxt = body[index + 1]
        if nxt in _ANSI_ESCAPES:
            out.append(_ANSI_ESCAPES[nxt])
            index += 2
        elif nxt == "x":
            digits = re.match(r"[0-9A-Fa-f]{1,2}", body[index + 2:])
            if digits:
                out.append(chr(int(digits.group(0), 16)))
                index += 2 + len(digits.group(0))
            else:
                out.append("\\x")
                index += 2
        elif nxt in "uU":
            digits = re.match(r"[0-9A-Fa-f]{1,8}" if nxt == "U" else r"[0-9A-Fa-f]{1,4}",
                              body[index + 2:])
            if digits:
                out.append(chr(int(digits.group(0), 16)))
                index += 2 + len(digits.group(0))
            else:
                out.append("\\" + nxt)
                index += 2
        elif nxt in "01234567":
            digits = re.match(r"[0-7]{1,3}", body[index + 1:])
            out.append(chr(int(digits.group(0), 8)))
            index += 1 + len(digits.group(0))
        else:
            out.append("\\" + nxt)
            index += 2
    return "".join(out)


def _written_word_value(word: str) -> str | None:
    """The value of one command word written with Bash quoting - `'a'`,
    `"a"`, `a\\b`, `$'a'` and `$"a"` parts, concatenated - or None when any
    part expands (`$x`, `${x}`, a substitution) or a quote never closes."""
    out: list[str] = []
    index = 0
    while index < len(word):
        ch = word[index]
        if word.startswith("$'", index):
            end = index + 2
            while end < len(word) and word[end] != "'":
                end += 2 if word[end] == "\\" else 1
            if end >= len(word):
                return None
            out.append(_ansi_c(word[index + 2:end]))
            index = end + 1
        elif word.startswith('$"', index):
            index += 1
            continue
        elif ch == "'":
            end = word.find("'", index + 1)
            if end == -1:
                return None
            out.append(word[index + 1:end])
            index = end + 1
        elif ch == '"':
            end = index + 1
            part: list[str] = []
            while end < len(word) and word[end] != '"':
                if word[end] in "$`":
                    return None
                if word[end] == "\\" and end + 1 < len(word) and word[end + 1] in '"\\$`':
                    part.append(word[end + 1])
                    end += 2
                    continue
                part.append(word[end])
                end += 1
            if end >= len(word):
                return None
            out.append("".join(part))
            index = end + 1
        elif ch == "\\" and index + 1 < len(word):
            out.append(word[index + 1])
            index += 2
        elif ch in "$`":
            return None
        else:
            out.append(ch)
            index += 1
    return "".join(out)


def _program_name(value: str) -> str:
    """The program a command word names: its base name, any Windows
    executable suffix dropped."""
    return _EXECUTABLE_SUFFIX.sub("", re.split(r"[\\/]", value)[-1])


def lookalike_head(segment: str) -> str | None:
    """The command name of `segment` when it is not plain ASCII - a Cyrillic
    `і` in `gіt` names a different program that reads, to a person, as git.
    None for an ASCII name. Only the program's own name counts, so a
    non-ASCII directory on the way to an ordinary tool does not."""
    _operator, text = _call_operator(segment)
    word, _rest = _leading_word(text)
    value = _written_word_value(word)
    if value is None or not value or any(ch.isspace() for ch in value):
        # An expansion, or a quoted phrase: not a name a person reads as a
        # known command.
        return None
    name = _program_name(value)
    return None if name.isascii() else name


def _start_process_reading(rest: str) -> tuple[str | None, bool]:
    """`(reading, opaque)` for `Start-Process <rest>`: the command it
    launches as a command line, and whether the program is an expansion
    this text cannot name."""
    try:
        tokens = shlex.split(rest, posix=True)
    except ValueError:
        return None, True
    program: str | None = None
    arguments: list[str] = []
    redirects: list[str] = []
    positional: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("-") and len(token) > 1:
            name = token[1:].split(":", 1)[0].lower()
            valued = [full for full in _START_PROCESS_VALUED if full.startswith(name)]
            if valued and index + 1 < len(tokens):
                value = tokens[index + 1]
                if valued[0] == "filepath":
                    program = value
                elif valued[0] in ("argumentlist", "args"):
                    arguments.append(value)
                elif valued[0] in ("redirectstandardoutput", "redirectstandarderror"):
                    redirects.append(value)
                index += 2
                continue
            index += 1
            continue
        positional.append(token)
        index += 1
    if program is None and positional:
        program = positional.pop(0)
    if not arguments and positional:
        arguments.append(positional.pop(0))
    if not program:
        return None, False
    if program.startswith(("$", "(")):
        return None, True
    words = [program] + [argument.replace(",", " ") for argument in arguments]
    reading = " ".join(words) + "".join(f" > {shlex.quote(target)}" for target in redirects)
    return reading, False


def _script_command(tokens: list[str]) -> str | None:
    """The command `script` runs: util-linux `-c CMD`/`--command CMD`
    (short flags may be bundled, `-qc CMD`), or the BSD form's words after
    the typescript file."""
    positional: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--command"):
            if "=" in token:
                return token.split("=", 1)[1]
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if token.startswith("-") and not token.startswith("--") and len(token) > 1:
            flags = token[1:]
            if "c" in flags:
                after = flags[flags.index("c") + 1:]
                if after:
                    return after
                return tokens[index + 1] if index + 1 < len(tokens) else None
            # Options that take a value (util-linux and BSD).
            if flags[-1] in "BEIOTFmt" and index + 1 < len(tokens):
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--"):
            index += 1
            continue
        positional.append(token)
        index += 1
    if len(positional) >= 2:
        return shlex.join(positional[1:])
    return None


def pty_wrapped(segment: str) -> str | None:
    """The command a pseudo-terminal wrapper at the head of `segment` runs,
    or None. `winpty git status` runs `git status`; `script -qc "..."
    /dev/null` runs its `-c` string; `expect -c '...'` runs its script."""
    _operator, text = _call_operator(segment)
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    wrapper = _program_name(tokens[0]).lower()
    if wrapper not in _PTY_WRAPPERS:
        return None
    rest = tokens[1:]
    if wrapper == "script":
        return _script_command(rest)
    if wrapper == "expect":
        for index, token in enumerate(rest):
            if token == "-c" and index + 1 < len(rest):
                return rest[index + 1]
        return shlex.join(rest) if rest else None
    # The wrapped command as written, cut after the wrapper's own options,
    # so its words keep their own quoting (`winpty $'git' push`).
    _word, remaining = _leading_word(text)
    while True:
        stripped = remaining.lstrip()
        word, after = _leading_word(stripped)
        if not word or not word.startswith("-"):
            return stripped or None
        remaining = after


# Heads whose next positional word selects what they do, so quoting that
# word hides the operation from a head-and-subcommand rule.
_SUBCOMMAND_HEADS = frozenset({
    "git", "gh", "godmode", "npm", "pnpm", "yarn", "cargo", "docker", "podman",
    "kubectl", "helm", "terraform", "claude", "twine", "gcloud", "az", "aws",
    "dotnet", "pip", "pip3", "uv", "poetry",
})
# Plain enough that quoting it changes nothing the shell does.
_PLAIN_WORD = re.compile(r"^[A-Za-z0-9_./:=@%+,-]+$")


def _unquoted_flags(segment: str) -> str | None:
    """`segment` with its quoted flags, and a subcommand head's quoted
    subcommand words, written bare: `git "push" "--force"` runs exactly
    what `git push --force` runs. Quoted data (a message, a search
    pattern) keeps its quotes, so the words inside it stay data. None when
    nothing changes."""
    _operator, text = _call_operator(segment)
    words: list[str] = []
    changed = False
    remaining = text
    position = 0
    head: str | None = None
    subcommand_words = 0
    previous_valued = False
    # A subcommand comes before the options that configure it; once one
    # is seen, a later bare word may be a flag's value (a message), which
    # is data.
    seen_flag = False
    while remaining.strip():
        stripped = remaining.lstrip()
        spacing = remaining[:len(remaining) - len(stripped)]
        if stripped[0] in "|;&<>":
            words.append(spacing + stripped)
            break
        word, remaining = _leading_word(stripped)
        if not word:
            words.append(spacing + stripped)
            break
        value = _written_word_value(word)
        written = word
        if position == 0:
            head = _program_name(value if value is not None else word).lower()
        elif value is not None and value != word and _PLAIN_WORD.match(value):
            if value.startswith("-"):
                written = value
            elif (head in _SUBCOMMAND_HEADS and subcommand_words < 2
                  and not previous_valued and not seen_flag):
                written = value
        current = value or word
        if position > 0 and current[:1] != "-":
            if not previous_valued:
                subcommand_words += 1
        # git's `-C <path>` / `-c <key=value>` take the next word and come
        # before the subcommand; every other flag ends the subcommand words.
        previous_valued = head == "git" and current in ("-C", "-c")
        if position > 0 and current[:1] == "-" and not previous_valued:
            seen_flag = True
        changed = changed or written != word
        words.append(spacing + written)
        position += 1
    if not changed:
        return None
    return "".join(words)


def command_readings(segment: str) -> list[str]:
    """Readings of `segment` with its command word normalised to the
    program it runs, beyond what `head_readings` resolves: a `$'...'` or
    `$"..."` name, a `${x:-name}` default, `& (Get-Command name)`, a
    dot-sourced script run as a script, `Start-Process`, a pseudo-terminal
    wrapper, and quoted flags or subcommand words written bare. Each is an
    extra reading; the classifier keeps the stricter verdict."""
    readings: list[str] = []
    operator, text = _call_operator(segment)
    word, rest = _leading_word(text)
    if word.startswith(("$'", '$"')):
        value = _written_word_value(word)
        if value and _PLAIN_NAME.match(_program_name(value)):
            readings.append(value + rest)
    default = _EXPANSION_DEFAULT.match(_unwrapped_double_quotes(word))
    if default:
        value = _written_word_value(default.group("word"))
        if value and _PLAIN_NAME.match(_program_name(value)):
            readings.append(value + rest)
    command = _GET_COMMAND.match(word)
    if command and operator is not None:
        readings.append(command.group("name") + rest)
    if operator == "." and word and not word.startswith(("$", "(", "{")):
        value = _written_word_value(word)
        if value:
            runner = "pwsh" if value.lower().endswith(".ps1") else "bash"
            readings.append(f"{runner} {shlex.quote(value)}{rest}")
    value = _written_word_value(word)
    if value is not None and _program_name(value).lower() in _START_PROCESS:
        reading, _opaque = _start_process_reading(rest)
        if reading:
            readings.append(reading)
    wrapped = pty_wrapped(segment)
    if wrapped:
        readings.append(wrapped)
    unquoted = _unquoted_flags(segment)
    if unquoted:
        readings.append(unquoted)
    return [reading for index, reading in enumerate(readings)
            if reading.strip() and reading not in readings[:index]]


def opaque_head(segment: str, strict: bool) -> str | None:
    """Why the program `segment` runs cannot be read from its text, or
    None. An expansion in the command word (`$cmd`, `${x:-git}`,
    PowerShell's `& $cmd`, `& (expression)`, `Start-Process $exe`) names
    whatever the variable holds when it runs.

    `strict` is True when the text is certainly Bash, where a variable
    standing alone as the command word is run. A variable with more after
    it (`$x.Name`, `$x[0]`) is read as PowerShell member access and left
    alone: Bash would run `${x}.Name`, a named residual. Otherwise the text may be
    PowerShell, which runs a variable only through the call or dot-source
    operator, or when words follow it; a bare `$x`, `$x | ...` or an
    assignment there is a value, not a command."""
    operator, text = _call_operator(segment)
    word, rest = _leading_word(text)
    if not word:
        return None
    # `"$cmd"` runs what `$cmd` runs; the quotes only stop word splitting.
    word = _unwrapped_double_quotes(word)
    if word.startswith("$") and not word.startswith(("$'", '$"', "$(")):
        if operator is None and _VARIABLE_ASSIGNMENT.match(text):
            return None
        if _EXPANSION_DEFAULT.match(word):
            return "the command word is a parameter expansion; the program depends on a variable"
        if operator is not None or (strict and _VARIABLE_WORD.match(word)):
            return "the command word is a variable; the program it names is not in the text"
        following = rest.split()
        if (_VARIABLE_WORD.match(word) and following
                and following[0][:1] not in "|;&)=<>" and not _PWSH_OPERATOR.match(following[0])):
            return "the command word is a variable; the program it names is not in the text"
        return None
    if operator is not None and word.startswith("(") and not _GET_COMMAND.match(word):
        return "the command word is an expression; the program it names is not in the text"
    value = _written_word_value(word)
    if value is not None and _program_name(value).lower() in _START_PROCESS:
        _reading, opaque = _start_process_reading(rest)
        if opaque:
            return "Start-Process names its program through an expansion"
    return None


@dataclass(frozen=True)
class ParsedSegment:
    """One command of a compound line.

    `text` is the segment as the classifier reads it (Bash spelling);
    `operator` is the separator that introduced it (`None` for the first);
    `argv` is its words with quoting resolved, or `None` when they cannot be
    resolved (an unclosed quote) - never a guess.
    """

    text: str
    operator: str | None
    argv: tuple[str, ...] | None

    @property
    def head(self) -> str:
        return self.argv[0] if self.argv else ""


@dataclass(frozen=True)
class ParseView:
    """`source` read once under `dialect`: `text` is the Bash spelling the
    classifier reads, `segments` its commands in order."""

    dialect: str
    source: str
    text: str
    segments: tuple[ParsedSegment, ...]

    @property
    def heads(self) -> tuple[str, ...]:
        return tuple(segment.head for segment in self.segments)


def _argv(segment: str) -> tuple[str, ...] | None:
    try:
        return tuple(shlex.split(segment, comments=False, posix=True))
    except ValueError:
        return None


def parse(command: str, dialect: str = BASH) -> ParseView:
    """`command` parsed under `dialect` (`bash`, `powershell` or `cmd`).

    The segments come from the classifier's own segment walk over the
    lowered text - the one splitter the gate uses - so this view and the
    verdict can never disagree about where a command ends.
    """
    if dialect not in DIALECTS:
        raise ValueError(f"unknown shell dialect: {dialect!r}")
    text = lower(command, dialect)
    segments = tuple(
        ParsedSegment(text=segment, operator=operator, argv=_argv(segment))
        for segment, operator in _walk_segments(_without_heredoc_bodies(text)))
    return ParseView(dialect=dialect, source=command, text=text, segments=segments)

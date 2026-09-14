"""Oracle-tamper rules: three advisory checks over one change set.

A change set is a git diff range (`base..head`) or the working tree against
HEAD. The rules read the unified diff plus the before/after text of the files it
touches; nothing runs, nothing is written, and every finding is advisory
(`blocking: False`). A static reading of a diff cannot prove a test still means
what it meant - it can only name the shapes below, so read each finding as a
question for the reviewer, not a verdict.

Rules
-----
`test-weakened-with-code`
    A test file loses an assertion, loosens one (`assertEqual` to
    `assertIn`/`assertTrue`/`assertRegex`, `==` to a truthiness check, a
    lower bound or count reduced), gains a skip / expectedFailure / xfail
    marker, or loses a test function - and the same change set modifies a
    non-test file whose module name the test file imports or names.
`ci-node-dropped`
    A GitHub workflow loses a job, a matrix entry, or a `run:` command that
    invokes tests or checks (a job whose body reappears under a new name is a
    rename, and a command that reappears in another job is a move).
`checker-neutered`
    A file under `quality/checks/`, or a script a workflow's `run:` names, is
    deleted; or its exit is forced to success (`|| true` added, `exit 0` /
    `sys.exit(0)` replacing a computed exit, an unconditional `exit 0` placed
    before more code in the same block); or a workflow gains
    `continue-on-error: true`.

Blind spots
-----------
- A renamed test whose assertion keeps its method but loses its meaning (for
  example `assertEqual(total(x), 5)` rewritten as
  `assertEqual(total(x), total(x))`) is read as a rename plus a same-strength
  rewrite and is not reported.
- The test-to-code link is by name. A test that reaches the changed code only
  through another module (it imports `app.api`, which calls the changed
  `app/billing.py`) is not linked, so its weakening is not reported.
- Conditional skips (`skipIf`, `skipUnless`, `pytest.mark.skipif`, a
  `skipTest` directly under an `if`) are not reported, so a skip gated on a
  condition that is always true passes unread.
- Weakening that leaves assertion text alone - a mock replacing the unit,
  changed fixture data, an early `return` in a test - is not read.
- Only GitHub workflow files are parsed, line by line rather than as full
  YAML (anchors and flow mappings are not resolved). A checker reached through
  a Makefile target or package script is not known to be CI-invoked.
- A weakening split across two change sets is invisible when each is read on
  its own; read the whole range.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .godmode_anchor import run_git
from .godmode_oracle import _TEST_PATH

RULE_TEST_WEAKENED = "test-weakened-with-code"
RULE_CI_NODE_DROPPED = "ci-node-dropped"
RULE_CHECKER_NEUTERED = "checker-neutered"
RULES = (RULE_TEST_WEAKENED, RULE_CI_NODE_DROPPED, RULE_CHECKER_NEUTERED)

REMEDIES = {
    RULE_TEST_WEAKENED: (
        "Restore the removed or loosened check, or move the test change into its own change set "
        "and state in its description why the old expectation was wrong."),
    RULE_CI_NODE_DROPPED: (
        "Restore the dropped job, matrix entry or command, or state in the change description "
        "which check replaces it and add that check in the same change."),
    RULE_CHECKER_NEUTERED: (
        "Remove the forced success so the checker's own exit code reaches CI again, or restore "
        "the deleted checker; if it is retired on purpose, state what replaces it."),
}

Source = Callable[[str], "str | None"]

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_WORKFLOW = re.compile(r"(^|/)\.github/workflows/[^/]+\.ya?ml$")
_ASSERT = re.compile(r"^\s*(?:assert\b|self\.assert[A-Z]\w*\s*\(|expect\s*\()")
_METHOD = re.compile(r"\b(assert[A-Z]\w*)\s*\(")
_EXACT = {"assertEqual", "assertEquals", "assertIs", "assertListEqual", "assertDictEqual",
          "assertTupleEqual", "assertSetEqual", "assertCountEqual", "assertMultiLineEqual",
          "assertSequenceEqual", "assertAlmostEqual", "assertRaises", "assertRaisesRegex"}
_LOWER_BOUND = {"assertGreater", "assertGreaterEqual"}
_UPPER_BOUND = {"assertLess", "assertLessEqual"}
# Unconditional markers only: `skipIf`/`skipUnless`/`skipif` gate on the
# environment (a platform, an installed tool) and were most of the noise when
# this rule was run over this repository's own history.
_SKIP = re.compile(
    r"@unittest\.skip(?![A-Za-z])|@unittest\.expectedFailure|@expectedFailure\b|pytest\.mark\.skip(?!if)|"
    r"pytest\.mark\.xfail|\bpytest\.(?:skip|xfail)\(|\bself\.skipTest\(|\b(?:it|test|describe)\.skip\(|"
    r"\bx(?:it|describe)\(")
_SKIP_CALL = re.compile(r"^\s*(?:self\.skipTest|pytest\.(?:skip|xfail))\(")
_BRANCH = re.compile(r"^\s*(?:if|elif|else|except|try|with|for|while)\b.*:\s*(?:#.*)?$")
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_CHECK_COMMAND = re.compile(
    r"(?i)\b(?:pytest|unittest|tox|nox|tests?|checks?|lint|verify|ruff|mypy|flake8|pylint|eslint|"
    r"jest|vitest|mocha|go\s+vet|cargo\s+(?:test|clippy))\b")
_SCRIPT_TOKEN = re.compile(r"[\w./\\-]+\.(?:py|sh|bash|ps1|js|mjs|cjs|ts|rb)\b")
_OR_TRUE = re.compile(r"\|\|\s*(?:true|:)(?:\s|$|;)")
_EXIT_ZERO = re.compile(r"^\s*(?:exit\s+0\b|sys\.exit\(\s*0?\s*\)|raise\s+SystemExit\(\s*0?\s*\)|os\._exit\(\s*0\s*\))")
_EXIT_COMPUTED = re.compile(r"\b(?:exit\s+(?!0\b)\S+|sys\.exit\(\s*(?!0?\s*\))|SystemExit\(\s*(?!0?\s*\)))")
_CONTINUE_ON_ERROR = re.compile(r"^\s*continue-on-error:\s*(?:true|'true'|\"true\")\s*(?:#.*)?$")


# --- diff parsing -------------------------------------------------------------

def _strip_prefix(raw: str) -> str | None:
    path = raw.strip().split("\t", 1)[0].strip('"')
    if path == "/dev/null":
        return None
    return path[2:] if path[:2] in ("a/", "b/") else path


def parse_diff(text: str) -> list[dict[str, Any]]:
    """Files in a unified diff: old/new path and hunks of
    (kind, old line, new line, text) with kind one of ' ', '-', '+'."""
    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    hunk: list | None = None
    old_no = new_no = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = line[len("diff --git "):].split(" b/", 1)
            current = {"old": _strip_prefix(parts[0]), "new": parts[1] if len(parts) > 1 else None, "hunks": []}
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue  # only git-shaped diffs: every file starts with `diff --git`
        if hunk is None:
            if line.startswith("--- "):
                current["old"] = _strip_prefix(line[4:])
            elif line.startswith("+++ "):
                current["new"] = _strip_prefix(line[4:])
            elif line.startswith("deleted file mode"):
                current["deleted"] = True
            elif line.startswith("new file mode"):
                current["added"] = True
            elif line.startswith("rename from "):
                current["old"] = line[len("rename from "):]
            elif line.startswith("rename to "):
                current["new"] = line[len("rename to "):]
        match = _HUNK.match(line)
        if match:
            old_no, new_no = int(match.group(1)), int(match.group(2))
            hunk = []
            current["hunks"].append(hunk)
            continue
        if hunk is None or line.startswith("\\"):
            continue
        kind, body = (line[:1], line[1:]) if line[:1] in "+-" else (" ", line[1:])
        if kind == "-":
            hunk.append(("-", old_no, None, body))
            old_no += 1
        elif kind == "+":
            hunk.append(("+", None, new_no, body))
            new_no += 1
        else:
            hunk.append((" ", old_no, new_no, body))
            old_no += 1
            new_no += 1
    for entry in files:
        if entry.get("deleted"):
            entry["new"] = None
        if entry.get("added"):
            entry["old"] = None
        entry["path"] = entry["new"] or entry["old"] or ""
        entry["status"] = ("A" if entry["old"] is None else "D" if entry["new"] is None
                           else "R" if entry["old"] != entry["new"] else "M")
    return files


def _added(entry: dict[str, Any]) -> list[tuple[int, str, list]]:
    return [(n, t, h) for h in entry["hunks"] for k, _o, n, t in h if k == "+"]


def _removed(entry: dict[str, Any]) -> list[tuple[int, str, list]]:
    return [(o, t, h) for h in entry["hunks"] for k, o, _n, t in h if k == "-"]


def _excerpt(hunk: list | None, line: int, side: str, fallback: str = "") -> str:
    if not hunk:
        return fallback
    column, changed = (1, "-") if side == "old" else (2, "+")
    matches = [i for i, row in enumerate(hunk) if row[column] == line]
    index = next((i for i in matches if hunk[i][0] == changed), matches[0] if matches else 0)
    rows = hunk[max(0, index - 2):index + 4]
    return "\n".join(f"{kind}{text}"[:120] for kind, _o, _n, text in rows)


def _finding(rule: str, path: str, line: int, detail: str, evidence: str) -> dict[str, Any]:
    line = max(1, int(line or 1))
    return {"rule": rule, "path": path, "line": line, "location": f"{path}:{line}",
            "detail": detail, "evidence": evidence, "remedy": REMEDIES[rule], "blocking": False}


def _in_string(line: str, position: int) -> bool:
    return line.count('"', 0, position) % 2 == 1 or line.count("'", 0, position) % 2 == 1


# --- rule 1: test weakened with the code it tests ---------------------------

def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text)]


def _shape(text: str) -> str:
    return re.sub(r"(?<![\w.])\d+(?:\.\d+)?", "_", text.strip())


def _method(text: str) -> str:
    match = _METHOD.search(text)
    if match:
        return match.group(1)
    return "assert" if re.match(r"^\s*assert\b", text) else "expect"


def _loosening(old: str, new: str) -> str | None:
    """Why `new` checks less than `old`, or None for a same-strength rewrite."""
    old_method, new_method = _method(old), _method(new)
    old_exact = old_method in _EXACT or (old_method == "assert" and "==" in old)
    new_exact = new_method in _EXACT or (new_method == "assert" and "==" in new)
    if old_exact and not new_exact:
        return f"exact check loosened: {old.strip()} -> {new.strip()}"
    if _shape(old) == _shape(new):
        before, after = _numbers(old), _numbers(new)
        for b, a in zip(before, after):
            if b == a:
                continue
            lower = old_method in _LOWER_BOUND or ">" in old or "len(" in old or "count" in old.lower()
            upper = old_method in _UPPER_BOUND or re.search(r"<(?!<)", old)
            if (lower and a < b) or (upper and not lower and a > b):
                return f"bound or count reduced: {old.strip()} -> {new.strip()}"
            break
    return None


def _code_stem(path: str) -> str:
    p = Path(path)
    stem = p.stem
    if stem in ("__init__", "index", "mod", "main", "lib") and p.parent.name:
        stem = p.parent.name
    return stem


def _test_signals(entry: dict[str, Any], added_anywhere: set[str], defs_added_anywhere: set[str]) -> list:
    signals: list[tuple[str, int, str, list]] = []  # (side, line, text, hunk)
    removed_text = {t.strip() for _l, t, _h in _removed(entry)}
    for hunk in entry["hunks"]:
        gone = [(o, t) for k, o, _n, t in hunk if k == "-" and _ASSERT.match(t) and t.strip() not in added_anywhere]
        new = [t for k, _o, _n, t in hunk if k == "+" and _ASSERT.match(t)]
        new = [t for t in new if t.strip() not in removed_text]
        unused = list(new)
        for old_line, text in gone:
            # Pair with a replacement of the same method first, then by order.
            partner = next((a for a in unused if _method(a) == _method(text)), unused[0] if unused else None)
            if partner is not None:
                unused.remove(partner)
                why = _loosening(text, partner)
                if why:
                    signals.append(("old", old_line, why, hunk))
            else:
                signals.append(("old", old_line, f"assertion removed: {text.strip()}", hunk))
        previous = ""
        for kind, _o, new_line, text in hunk:
            if kind == "-":
                continue
            match = _SKIP.search(text) if kind == "+" else None
            conditional = bool(_SKIP_CALL.match(text)) and bool(_BRANCH.match(previous)) \
                and _indent(previous) < _indent(text)
            if match and not conditional and not _in_string(text, match.start()) \
                    and text.strip() not in removed_text:
                signals.append(("new", new_line, f"skip marker added: {text.strip()}", hunk))
            if text.strip():
                previous = text
    removed_defs = [(o, _TEST_DEF.match(t).group(1), h) for o, t, h in _removed(entry) if _TEST_DEF.match(t)]
    added_defs = [_TEST_DEF.match(t).group(1) for _n, t, _h in _added(entry) if _TEST_DEF.match(t)]
    unmatched_removed = [d for d in removed_defs if d[1] not in defs_added_anywhere]
    unmatched_added = [name for name in added_defs if name not in {d[1] for d in removed_defs}]
    for old_line, name, hunk in unmatched_removed[len(unmatched_added):]:
        signals.append(("old", old_line, f"test function deleted: {name}", hunk))
    return signals


def _rule_test_weakened(files: list[dict[str, Any]], old: Source, new: Source) -> list[dict[str, Any]]:
    tests = [f for f in files if _TEST_PATH.search(f["path"])]
    code = [f["path"] for f in files if not _TEST_PATH.search(f["path"]) and not _WORKFLOW.search(f["path"])]
    if not tests or not code:
        return []
    added_anywhere = {t.strip() for f in files for _n, t, _h in _added(f)}
    defs_added_anywhere = {_TEST_DEF.match(t).group(1) for f in files for _n, t, _h in _added(f) if _TEST_DEF.match(t)}
    findings: list[dict[str, Any]] = []
    for entry in tests:
        signals = _test_signals(entry, added_anywhere, defs_added_anywhere)
        if not signals:
            continue
        source = (new(entry["new"]) if entry["new"] else None) or (old(entry["old"]) if entry["old"] else None) or ""
        source += "\n" + "\n".join(t for h in entry["hunks"] for _k, _o, _n, t in h)
        linked = [p for p in code
                  if len(_code_stem(p)) >= 3 and re.search(rf"(?<![\w-]){re.escape(_code_stem(p))}(?![\w-])", source)]
        if not linked:
            continue
        side, line, _why, hunk = signals[0]
        findings.append(_finding(
            RULE_TEST_WEAKENED, entry["path"], line,
            f"{entry['path']} checks less in the same change set that modifies {', '.join(linked[:3])}: "
            + "; ".join(s[2][:100] for s in signals[:3])
            + (f" (+{len(signals) - 3} more)" if len(signals) > 3 else "")
            + (" (line number before the change)" if side == "old" else ""),
            _excerpt(hunk, line, side)))
    return findings


# --- workflow reading (line-based, not full YAML) ----------------------------

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def workflow_jobs(text: str) -> dict[str, dict[str, Any]]:
    """Job name -> {line, body (list of lines), commands, matrix}."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", l)), None)
    if start is None:
        return {}
    jobs: dict[str, dict[str, Any]] = {}
    key_indent = None
    current = None
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not _meaningful(line):
            if current:
                current["body"].append(line)
            continue
        if _indent(line) == 0:
            break
        if key_indent is None:
            key_indent = _indent(line)
        match = re.match(r"^\s*([\w.-]+|\"[^\"]+\"|'[^']+'):\s*(#.*)?$", line)
        if _indent(line) == key_indent and match:
            current = {"line": i + 1, "body": []}
            jobs[match.group(1).strip("'\"")] = current
        elif current is not None:
            current["body"].append(line)
    for job in jobs.values():
        job["commands"] = _run_commands(job["body"])
        job["matrix"] = _matrix_entries(job["body"])
    return jobs


def _run_commands(body: list[str]) -> list[str]:
    commands: list[str] = []
    i = 0
    while i < len(body):
        match = re.match(r"^(\s*(?:-\s+)?)run:\s*(.*)$", body[i])
        if not match:
            i += 1
            continue
        column = len(match.group(1))
        value = match.group(2).strip()
        i += 1
        if value in ("", "|", ">", "|-", ">-", "|+", ">+"):
            while i < len(body) and (not body[i].strip() or _indent(body[i]) > column):
                if _meaningful(body[i]):
                    commands.append(" ".join(body[i].split()))
                i += 1
        else:
            commands.append(" ".join(value.strip("'\"").split()))
    return commands


def _matrix_entries(body: list[str]) -> list[str]:
    entries: list[str] = []
    start = next((i for i, l in enumerate(body) if re.match(r"^\s*matrix:\s*(#.*)?$", l)), None)
    if start is None:
        return entries
    base = _indent(body[start])
    key = ""
    for line in body[start + 1:]:
        if not _meaningful(line):
            continue
        if _indent(line) <= base:
            break
        stripped = line.strip()
        pair = re.match(r"^([\w.-]+):\s*(.*)$", stripped)
        if stripped.startswith("- "):
            if key != "exclude":
                entries.append(f"{key}={stripped[2:].strip()}")
        elif pair:
            name, value = pair.group(1), pair.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                entries.extend(f"{name}={v.strip()}" for v in value[1:-1].split(",") if v.strip())
            elif not value:
                key = name
    return entries


def _old_hunk_for(entry: dict[str, Any], line: int) -> list | None:
    for hunk in entry["hunks"]:
        if any(row[1] == line and row[0] == "-" for row in hunk):
            return hunk
    for hunk in entry["hunks"]:
        if any(row[1] == line for row in hunk):
            return hunk
    return entry["hunks"][0] if entry["hunks"] else None


def _find_line(text: str, needle: str, after: int = 0) -> int:
    for number, line in enumerate(text.splitlines(), 1):
        if number > after and needle in " ".join(line.split()):
            return number
    return after or 1


def _rule_ci_node_dropped(files: list[dict[str, Any]], old: Source, new: Source) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in files:
        if not entry["old"] or not _WORKFLOW.search(entry["old"]):
            continue
        before_text = old(entry["old"]) or ""
        after_text = (new(entry["new"]) if entry["new"] else None) or ""
        before, after = workflow_jobs(before_text), workflow_jobs(after_text)
        if not before:
            continue
        new_bodies = {name: [l.strip() for l in job["body"] if l.strip()] for name, job in after.items() if name not in before}
        all_new_commands = {c for job in after.values() for c in job["commands"]}
        for name, job in before.items():
            if name in after:
                continue
            body = [l.strip() for l in job["body"] if l.strip()]
            renamed = next((n for n, b in new_bodies.items() if b == body), None)
            if renamed:
                new_bodies.pop(renamed)
                continue
            hunk = _old_hunk_for(entry, job["line"])
            findings.append(_finding(
                RULE_CI_NODE_DROPPED, entry["path"], job["line"],
                f"job `{name}` removed from {entry['path']} (line number before the change)",
                _excerpt(hunk, job["line"], "old", f"-  {name}:")))
        for name, job in before.items():
            if name not in after:
                continue
            for value in job["matrix"]:
                if value in after[name]["matrix"]:
                    continue
                shown = value.split("=", 1)[1]
                line = _find_line(before_text, shown, job["line"])
                findings.append(_finding(
                    RULE_CI_NODE_DROPPED, entry["path"], line,
                    f"matrix entry `{value}` removed from job `{name}` (line number before the change)",
                    _excerpt(_old_hunk_for(entry, line), line, "old", f"-{shown}")))
            for command in job["commands"]:
                if command in all_new_commands or not _CHECK_COMMAND.search(command):
                    continue
                line = _find_line(before_text, command, job["line"])
                findings.append(_finding(
                    RULE_CI_NODE_DROPPED, entry["path"], line,
                    f"command `{command[:80]}` removed from job `{name}` (line number before the change)",
                    _excerpt(_old_hunk_for(entry, line), line, "old", f"-{command}")))
    return findings


# --- rule 3: checker neutered --------------------------------------------------

def ci_invoked_scripts(workflow_texts: Iterable[str]) -> set[str]:
    """Repository paths that a workflow `run:` command names."""
    scripts: set[str] = set()
    for text in workflow_texts:
        for job in workflow_jobs(text).values():
            for command in job["commands"]:
                for token in _SCRIPT_TOKEN.findall(command):
                    token = token.replace("\\", "/")
                    scripts.add(token[2:] if token.startswith("./") else token)
    return scripts


def _rule_checker_neutered(files: list[dict[str, Any]], old: Source, new: Source,
                           ci_scripts: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    scripts = set(ci_scripts)
    scripts |= ci_invoked_scripts(old(f["old"]) or "" for f in files if f["old"] and _WORKFLOW.search(f["old"]))
    for entry in files:
        path = entry["old"] or entry["new"] or ""
        is_workflow = bool(_WORKFLOW.search(path))
        is_checker = path.startswith("quality/checks/") or path in scripts
        if entry["status"] == "D" and is_checker:
            hunk = entry["hunks"][0] if entry["hunks"] else None
            findings.append(_finding(
                RULE_CHECKER_NEUTERED, path, 1, f"checker {path} deleted",
                _excerpt(hunk, 1, "old", f"-{path}")))
            continue
        if entry["status"] == "D" or not (is_checker or is_workflow):
            continue
        after_lines = ((new(entry["new"]) if entry["new"] else None) or "").splitlines()
        for hunk in entry["hunks"]:
            removed = [t for k, _o, _n, t in hunk if k == "-"]
            removed_stripped = {t.strip() for t in removed}
            for kind, _o, new_line, text in hunk:
                if kind != "+" or text.strip() in removed_stripped:
                    continue
                why = None
                if is_workflow:
                    if _CONTINUE_ON_ERROR.match(text):
                        why = "`continue-on-error: true` added - a failing step no longer fails the job"
                    elif _OR_TRUE.search(text):
                        why = f"`|| true` added to a workflow command: {text.strip()[:80]}"
                elif _OR_TRUE.search(text):
                    why = f"`|| true` added: {text.strip()[:80]}"
                elif _EXIT_ZERO.match(text):
                    if any(_EXIT_COMPUTED.search(r) for r in removed):
                        why = f"exit forced to success, replacing a computed exit: {text.strip()}"
                    elif _dead_code_follows(after_lines, new_line):
                        why = f"unconditional success exit placed before more code: {text.strip()}"
                if why:
                    findings.append(_finding(RULE_CHECKER_NEUTERED, entry["path"], new_line,
                                             f"{entry['path']}: {why}", _excerpt(hunk, new_line, "new")))
    return findings


def _dead_code_follows(lines: list[str], line: int) -> bool:
    if not 0 < line <= len(lines):
        return False
    column = _indent(lines[line - 1])
    for later in lines[line:]:
        if not _meaningful(later):
            continue
        return _indent(later) == column
    return False


# --- entry points ---------------------------------------------------------------

def _as_source(source: "Source | Mapping[str, str] | None") -> Source:
    if source is None:
        return lambda _path: None
    if isinstance(source, Mapping):
        return source.get
    return source


def tamper_findings(diff_text: str, old_source: "Source | Mapping[str, str] | None" = None,
                    new_source: "Source | Mapping[str, str] | None" = None,
                    ci_scripts: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Every rule over one unified diff. `old_source`/`new_source` return a
    file's text before/after the change (or None); `ci_scripts` names scripts
    CI invokes beyond those the diff's own workflows show."""
    files = parse_diff(diff_text)
    old, new = _as_source(old_source), _as_source(new_source)
    return (_rule_test_weakened(files, old, new)
            + _rule_ci_node_dropped(files, old, new)
            + _rule_checker_neutered(files, old, new, set(ci_scripts)))


def change_set_findings(project: Path, base: str = "HEAD", head: str | None = None) -> list[dict[str, Any]]:
    """The rules over `base..head`, or over the working tree against `base`
    when no head is given. `base` may itself be written `A..B`. Read-only git."""
    project = Path(project)
    if head is None and ".." in base:
        base, head = base.split("..", 1)
        base, head = base or "HEAD", head or None
    arguments = ["diff", "--no-color", "--no-ext-diff", "-M", "--unified=3", base] + ([head] if head else [])
    diff = run_git(project, *arguments)
    if not diff:
        return []

    def old(path: str) -> str | None:
        return run_git(project, "show", f"{base}:{path}")

    def new(path: str) -> str | None:
        if head:
            return run_git(project, "show", f"{head}:{path}")
        try:
            return (project / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    listed = run_git(project, "ls-tree", "-r", "--name-only", base, "--", ".github/workflows") or ""
    workflows = [old(p) or "" for p in listed.splitlines() if _WORKFLOW.search(p)]
    return tamper_findings(diff, old, new, ci_scripts=ci_invoked_scripts(workflows))

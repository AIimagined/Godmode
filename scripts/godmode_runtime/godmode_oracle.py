"""The oracle contract: the checker is independent of the author (PRD F5,
F10; research brief Slice A, ExecCritic).

A wrong patch can pass a wrong test when one trajectory wrote both and
decided when to stop. Everything here is a pure function over the diff,
the archive, and the host transcript; nothing calls a model. Findings
start as observe-mode records (`would-have-rejected-oracle-tamper`) and
the strict profile may refuse on them later (Phase 2).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git

_TEST_PATH = re.compile(r"(?i)(^|/)(tests?|spec|__tests__|specs)(/|$)|(^|/)(test_[^/]+|[^/]+[._-](test|spec))\.[a-z]+$")
_CI_PATH = re.compile(r"(?i)(^|/)(\.github/workflows/|\.gitlab-ci\.yml|\.circleci/|jest\.config|vitest\.config|"
                      r"pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml|package\.json|karma\.conf|playwright\.config|"
                      r"Makefile|justfile|\.pre-commit-config\.yaml|codecov\.yml|\.mocharc)")
_SUCCESS_INJECTION = re.compile(
    r"sys\.exit\(\s*0\s*\)|process\.exit\(\s*0\s*\)|\bexit 0\b|@pytest\.mark\.skip|@unittest\.skip|"
    r"\b(?:it|test|describe)\.skip\(|\bx(?:it|test|describe)\(|\bpytest\.skip\(|\|\|\s*true\b|"
    r"^\s*(?:pass|return)\s*(?:#.*)?$|assert\s+True\b|expect\(true\)\.toBe\(true\)")
_NODE_DROP = re.compile(
    r"(?i)--ignore(?:-glob)?[= ]|testPathIgnorePatterns|\bexclude\s*[:=]|--deselect|-k\s+[\"']?not\b|"
    r"continue-on-error:\s*true|allow_failure:\s*true|\|\|\s*true\b|\bomit\b|\bskip[-_]?(?:ci|tests?)\b")
_ASSERTION = re.compile(r"^\s*(?:assert\b|self\.assert|expect\s*\(|\.should\b|assert_eq!|ASSERT_|EXPECT_|t\.(?:Errorf|Fatal))")
_OPERATIONAL_ERROR = re.compile(
    r"(?im)\b(?:ModuleNotFoundError|ImportError|Cannot find module|command not found|No such file or directory|"
    r"ENOENT|SyntaxError|is not recognized as an internal or external command|Permission denied|"
    r"No module named)\b")


def _changed_files(project: Path, base: str) -> dict[str, str]:
    raw = run_git(project, "diff", "--name-status", "--no-renames", base) or ""
    files: dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files[parts[-1].replace("\\", "/")] = parts[0][:1]
    for line in (run_git(project, "status", "--porcelain") or "").splitlines():
        if line.startswith("??"):
            files[line[3:].strip().replace("\\", "/")] = "A"
    # Field report file 2026-09-10, Part 3: a NEW test file is untracked
    # until it is added, and a diff against HEAD cannot see it - so the
    # coverage pairing called three tested routes untested. Untracked
    # files count as added.
    untracked = run_git(project, "ls-files", "--others", "--exclude-standard")
    for line in (untracked or "").splitlines():
        path = line.strip()
        if path and path not in files:
            files[path] = "A"
    return files


def _diff_lines(project: Path, base: str, path: str) -> tuple[list[str], list[str]]:
    raw = run_git(project, "diff", "--unified=0", "--no-color", base, "--", path) or ""
    if not raw and (project / path).is_file():
        try:  # an untracked file is all added lines
            return [], (project / path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return [], []
    removed = [l[1:] for l in raw.splitlines() if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in raw.splitlines() if l.startswith("+") and not l.startswith("+++")]
    return removed, added


def split_assertion_changes(removed: list[str], added: list[str], pattern: Any = None) -> dict[str, list[str]]:
    """Removed assertions minus the ones that merely changed a number or a
    literal (a widened margin is a change to name, not a removal to block).
    Field report file 2026-09-10, finding 6."""
    strip = lambda s: re.sub(r"[\d.]+|['\"][^'\"]*['\"]", "_", s.strip())
    match = (pattern or _ASSERTION).match
    lost = [l.strip() for l in removed if match(l)]
    kept = [l.strip() for l in added if match(l)]
    kept_shapes = [strip(k) for k in kept]
    gone: list[str] = []
    changed: list[str] = []
    for line in lost:
        if line in kept:
            continue
        if strip(line) in kept_shapes:
            changed.append(line)
        else:
            gone.append(line)
    return {"removed": gone, "changed": changed, "added": [k for k in kept if k not in lost]}


def oracle_tamper_findings(project: Path, base: str = "HEAD",
                           red_observed: set[str] | None = None) -> list[dict[str, Any]]:
    """The five ExecCritic shapes that a diff alone can show (the
    transcript-borne ones live in `checker_authored` and
    `operational_error_in`):

    1. a test weakened in the same diff as a source edit;
    2. a CI or harness file edited to drop or skip a node;
    4. a new test file that was never observed failing (Base gate).

    `red_observed` is the set of test paths seen failing (from guard
    attestations or the transcript); None means nothing is known.
    """
    files = _changed_files(project, base)
    tests = [p for p, s in files.items() if _TEST_PATH.search(p) and s != "D"]
    production = [p for p, s in files.items() if not _TEST_PATH.search(p) and not _CI_PATH.search(p)
                  and s != "D" and Path(p).suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".mjs", ".cjs"}]
    ci = [p for p, s in files.items() if _CI_PATH.search(p) and s != "D"]
    findings: list[dict[str, Any]] = []
    for path in tests:
        removed, added = _diff_lines(project, base, path)
        split = split_assertion_changes(removed, added)
        injected = [l.strip() for l in added if _SUCCESS_INJECTION.search(l)]
        if production and (split["removed"] or injected):
            findings.append({
                "shape": "test-weakened-with-source-edit", "path": path, "blocking": True,
                "detail": (f"{len(split['removed'])} assertion(s) removed and {len(injected)} unconditional-success "
                           f"line(s) added in {path} in the same diff as {len(production)} source file(s) "
                           f"({', '.join(production[:3])}) - the oracle and the patch moved together"),
            })
        if split["changed"]:
            findings.append({
                "shape": "assertion-changed", "path": path, "blocking": False,
                "detail": f"{len(split['changed'])} assertion(s) in {path} changed a literal or bound, not removed: "
                          + "; ".join(split["changed"][:2]),
            })
        if files.get(path) == "A" and red_observed is not None and path not in red_observed:
            findings.append({
                "shape": "new-test-never-red", "path": path, "blocking": False,
                "detail": f"{path} is new and was never observed failing on the tree before the source edit "
                          "(Base gate) - a test that passes on HEAD proves nothing about the patch",
            })
    for path in ci:
        removed, added = _diff_lines(project, base, path)
        dropped = [l.strip() for l in added if _NODE_DROP.search(l)]
        if dropped:
            findings.append({
                "shape": "harness-node-dropped", "path": path, "blocking": True,
                "detail": f"{path} gained {len(dropped)} line(s) that skip, ignore, or tolerate a failing node: "
                          + "; ".join(d[:80] for d in dropped[:2]),
            })
    return findings


def edited_paths_from_transcript(transcript_path: str | Path | None) -> list[str]:
    """Every file_path an Edit/Write/NotebookEdit call named this session,
    slash-normalised and lower-cased."""
    if not transcript_path:
        return []
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    edited: list[str] = []
    for line in lines[-8000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        for part in (entry.get("message") or {}).get("content") or []:
            if isinstance(part, dict) and part.get("type") == "tool_use" \
                    and part.get("name") in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
                path = str((part.get("input") or {}).get("file_path", "")).replace("\\", "/").lower()
                if path:
                    edited.append(path)
    return edited


def checker_authored(command: str, edited: list[str]) -> str | None:
    """The file this session wrote that the cited checker command names, or
    None. A checker the same trajectory authored is not independent
    (ExecCritic: shared-trajectory tests acquit shared-trajectory patches)."""
    lowered = " ".join(str(command).split()).lower()
    tokens = set(re.split(r"[\s'\"=,;:|()]+", lowered))
    for path in edited:
        name = path.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if not stem or len(stem) < 3:
            continue
        module = path.replace("/", ".").rsplit(".", 1)[0]
        if name in tokens or path in lowered or any(t.endswith("/" + name) or t == name for t in tokens) \
                or any(t.endswith(module.split(".", 1)[-1]) for t in tokens if "." in t and len(t) > 6):
            return path
    return None


def operational_error_in(text: str) -> str | None:
    """The operational error (missing module, missing file, command not
    found) in a tool result, or None. An operational error is not a
    behavioural verdict: the checker could not judge."""
    match = _OPERATIONAL_ERROR.search(text or "")
    return match.group(0) if match else None


def last_result_for(transcript_path: str | Path | None, command: str) -> str | None:
    """The text of the newest tool_result for this exact command, or None."""
    if not transcript_path:
        return None
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    wanted = " ".join(str(command).split())
    pending: dict[str, bool] = {}
    latest: str | None = None
    for line in lines[-8000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use" and part.get("name") in ("Bash", "PowerShell"):
                pending[str(part.get("id"))] = " ".join(str((part.get("input") or {}).get("command", "")).split()) == wanted
            elif part.get("type") == "tool_result" and pending.pop(str(part.get("tool_use_id")), False):
                body = part.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                latest = str(body or "")
    return latest


_TRUNCATED_OUTPUT = re.compile(r"Output too large \([^)]*\)\. Full output saved to: (?P<path>[^\r\n\"\\]+(?:\\\\[^\r\n\"\\]+)*)")


def unread_truncated_outputs(transcript_path: str | Path | None) -> list[dict[str, Any]]:
    """Field roundup 2026-09-10: a failure sat on line 1,400 of test output
    the host truncated to a file the agent never opened, and the reply said
    green. Every truncation marker in the transcript whose saved path never
    appears in a later tool call (a Read, a Bash grep, anything naming it)."""
    if not transcript_path:
        return []
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    pending: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for turn, raw in enumerate(lines):
        if not raw.strip():
            continue
        for match in _TRUNCATED_OUTPUT.finditer(raw):
            path = match.group("path").replace("\\\\", "\\").strip()
            pending.append({"path": path, "turn": turn})
            continue
        if not pending:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        parts = message.get("content") if isinstance(message, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            payload = json.dumps(part.get("input") or {}).replace("\\\\", "\\")
            pending = [item for item in pending
                       if item["turn"] >= turn or Path(item["path"]).name not in payload]
    out.extend(pending)
    return out


def created_uncited(transcript_path: str | Path | None, archive: Any, project: Path) -> list[str]:
    """Field report file 2026-09-10, Part 3: two throwaway specs sat in the
    tree until the agent happened to delete them. Every path a Write tool
    call created this session that still exists and that no claim
    citation, change record, or checkpoint evidence names."""
    if not transcript_path:
        return []
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    written: list[str] = []
    for raw in lines:
        if '"Write"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        parts = message.get("content") if isinstance(message, dict) else None
        for part in parts or []:
            if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("name") == "Write":
                path = str((part.get("input") or {}).get("file_path") or "")
                if path and path not in written:
                    written.append(path)
    if not written:
        return []
    named: list[str] = []
    try:
        for record in archive.select(limit=600):
            if record.get("kind") in ("claim", "change", "checkpoint", "build", "attestation"):
                named.append(" ".join(str(e) for e in (record.get("evidence") or [])))
                named.append(str(record.get("subject", "")))
                # Part 6: a checkpoint carries file NAMES in its text, not paths.
                named.append(json.dumps(record.get("data") or {}))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable archive names nothing; every written file is then listed
        named = []
    haystack = " ".join(named).replace("\\", "/")
    out: list[str] = []
    for path in written:
        try:
            resolved = Path(path)
            if not resolved.is_absolute():
                resolved = Path(project) / path
            if not resolved.is_file():
                continue
            relative = str(resolved.resolve().relative_to(Path(project).resolve())).replace("\\", "/")
        except (OSError, ValueError):
            continue
        if relative not in haystack and resolved.name not in haystack:
            out.append(relative)
    return out


def _tool_calls(transcript_path: str | Path | None) -> list[tuple[int, str, dict[str, Any], str | None]]:
    """(turn, tool name, input, result text or None) in transcript order;
    the result is the tool_result that answered the call, when one did."""
    if not transcript_path:
        return []
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    calls: list[tuple[int, str, dict[str, Any], str | None]] = []
    index_by_id: dict[str, int] = {}
    for turn, raw in enumerate(lines):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        parts = message.get("content") if isinstance(message, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                index_by_id[str(part.get("id"))] = len(calls)
                calls.append((turn, str(part.get("name") or ""), dict(part.get("input") or {}), None))
            elif part.get("type") == "tool_result":
                position = index_by_id.get(str(part.get("tool_use_id")))
                if position is None:
                    continue
                content = part.get("content")
                if isinstance(content, list):
                    content = " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
                turn_, name, payload, _ = calls[position]
                calls[position] = (turn_, name, payload, str(content or "")[:4000])
    return calls


_SHELL_TOOLS = ("Bash", "PowerShell", "shell", "run_command")
_STOP_PROCESS = re.compile(r"(?i)\b(?:Stop-Process|taskkill|pkill|killall|kill\s+(?:-\d+\s+)?\d+)\b")
_DEV_SERVER = re.compile(r"(?i)\b(?:npm\s+run\s+dev|pnpm\s+dev|yarn\s+dev|next\s+dev|vite(?:\s|$)|flask\s+run|uvicorn|rails\s+s(?:erver)?)\b")
_SERVE_PORT = re.compile(r"(?i)\b(?:next\s+start|npm\s+(?:run\s+)?start|node\s+\S+|python\s+-m\s+http\.server|serve)\b[^|;&]*?(?:-p|--port)[= ]?(\d{2,5})")
_SQL_UPDATE = re.compile(r"(?i)\bUPDATE\s+([A-Za-z_][\w.\"]*)\s+SET\b")
_STASH = re.compile(r"(?i)\bgit\s+stash\b(?!\s+(?:pop|apply|list|show|drop))")
_STASH_BACK = re.compile(r"(?i)\bgit\s+stash\s+(?:pop|apply)\b")
_PERSISTENT_ENV = re.compile(r"(?i)\bsetx\s+\w+|\[Environment\]::SetEnvironmentVariable")


def unrestored_temporaries(transcript_path: str | Path | None) -> list[dict[str, str]]:
    """Field reports Part 3, Part 4 and the RCA pass (2026-09-10): a dev
    server stopped, a production server started on a port, a role bumped
    with an UPDATE, a stash never popped - restored from memory, or not.
    Every shape below is a temporary state this session created and no
    later call in the same transcript reversed. Heuristic and bounded:
    it names what it saw, and the restore may have happened outside the
    transcript; the reader decides."""
    calls = _tool_calls(transcript_path)
    commands = [(turn, str(payload.get("command") or "")) for turn, name, payload, _ in calls
                if name in _SHELL_TOOLS and payload.get("command")]
    out: list[dict[str, str]] = []
    stops = [turn for turn, c in commands if _STOP_PROCESS.search(c)]
    restarts = [turn for turn, c in commands if _DEV_SERVER.search(c)]
    if stops and not any(r > stops[-1] for r in restarts):
        out.append({"kind": "process", "detail": "a process was stopped and no dev-server start followed"})
    for turn, c in commands:
        for port in _SERVE_PORT.findall(c):
            later_stop = any(t > turn and (_STOP_PROCESS.search(cc) or port in cc and "kill" in cc.lower())
                             for t, cc in commands)
            if not later_stop:
                out.append({"kind": "process", "detail": f"a server was started on port {port} and no stop followed"})
    seen_tables: dict[str, list[int]] = {}
    for turn, c in commands:
        for table in _SQL_UPDATE.findall(c):
            seen_tables.setdefault(table.strip('"'), []).append(turn)
    for table, turns in seen_tables.items():
        if len(turns) == 1:
            out.append({"kind": "data", "detail": f"table {table} was updated once and no reverting update followed"})
    stash_turns = [turn for turn, c in commands if _STASH.search(c)]
    if stash_turns and not any(t > stash_turns[-1] for t, c in commands if _STASH_BACK.search(c)):
        out.append({"kind": "worktree", "detail": "git stash was created and never popped or applied"})
    if any(_PERSISTENT_ENV.search(c) for _, c in commands):
        out.append({"kind": "environment", "detail": "a persistent environment variable was set (setx / SetEnvironmentVariable)"})
    unique: list[dict[str, str]] = []
    for item in out:
        if item not in unique:
            unique.append(item)
    return unique[:6]


_RED = re.compile(r"(?i)\b(?:FAILED|FAIL:|ERROR:|Error:|Traceback|assert(?:ion)?(?:Error)?|\d+ failed)\b")


def unattributed_flips(transcript_path: str | Path | None, threshold: int = 3) -> list[dict[str, Any]]:
    """The one-variable rule as data: two consecutive runs of the same
    verdict-bearing command that flipped red to green with `threshold` or
    more distinct files edited in between. Whatever flipped it is not
    attributed to any one change; the reader decides whether that matters
    (it does in an investigation, it may not in a fix)."""
    calls = _tool_calls(transcript_path)
    last_red: dict[str, tuple[int, int]] = {}  # command -> (turn, call index)
    out: list[dict[str, Any]] = []
    for position, (turn, name, payload, result) in enumerate(calls):
        if name not in _SHELL_TOOLS or not payload.get("command") or result is None:
            continue
        command = " ".join(str(payload["command"]).split())
        red = bool(_RED.search(result))
        previous = last_red.get(command)
        if red:
            last_red[command] = (turn, position)
            continue
        if previous is None:
            continue
        edited: list[str] = []
        for _t, n, p, _r in calls[previous[1] + 1:position]:
            if n in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
                path = str(p.get("file_path") or p.get("path") or "")
                if path and path not in edited:
                    edited.append(path)
        if len(edited) >= threshold:
            out.append({"command": command[:80], "files": [Path(p).name for p in edited][:8],
                        "detail": f"`{command[:60]}` flipped red to green with {len(edited)} files edited between "
                                  f"the two runs ({', '.join(Path(p).name for p in edited[:4])}); the flip is not "
                                  "attributed to any one change - revert all but one, or record which one and why"})
        last_red.pop(command, None)
    return out[:3]


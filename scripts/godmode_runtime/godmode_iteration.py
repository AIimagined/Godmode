"""Iteration controls computed from records and the host transcript.

Field report file 2026-09-10 and the operator's own observation: an agent
declares everything complete, then after the deployment work names one
more item "for the next release" that was asked for in this one; and the
iteration trap (spectator loops, local minima, runaway spend) is watched
by advisories that cannot stop anything. Every function here returns
data: what is open, what was measured, how long the streak is. The hook
turns that data into a block or an ask; nothing here names a verb to run.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_SCORE = re.compile(r"(?i)\bscore\s*[:=]\s*(-?\d+(?:\.\d+)?)")
_DONE_STATUSES = frozenset({"done", "complete", "completed", "closed", "skipped", "dropped"})


def open_scope(archive: Any, session_id: str | None) -> dict[str, list[str]]:
    """What the record still holds open for this session's work: the
    operator's own asks stated in this host session, the active plan's
    pending steps, criteria no claim has cited, and a hypothesis that has
    failed three checkpoints. Each entry is a sentence a reader can act
    on, with the closing command where one exists."""
    from .godmode_requests import open_stated_requests

    out: dict[str, list[str]] = {"asks": [], "steps": [], "criteria": [], "hypotheses": [], "temporaries": []}
    records = archive.select(limit=600)
    latest_obligation: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("kind") == "obligation":
            latest_obligation[str(record.get("subject", ""))] = record
    for subject, record in latest_obligation.items():
        data = record.get("data") or {}
        if subject.startswith("temporary:") and str(data.get("status", "open")).lower() not in ("closed", "done", "retired", "waived"):
            out["temporaries"].append(
                f"{subject} still on record - restore it, then `godmode remember --kind obligation "
                f"--subject \"{subject}\" --status closed`")
    # The request-only window, the same one the closure command reads
    # (2026-09-11): a window over every kind stopped short of the closure
    # in a busy session, and the gate named an ask the closure had already
    # answered.
    requests = archive.select(kind="request", limit=600)
    for record in open_stated_requests(requests):
        data = record.get("data") or {}
        if session_id and str(data.get("session") or "") != str(session_id):
            continue
        words = " ".join(str(w) for w in (data.get("keywords") or [])[:7])
        out["asks"].append(f"ask {record.get('subject')} '{words}' - `godmode remember --kind request "
                           f"--subject \"{record.get('subject')}\" --status closed`")
    plans = [r for r in records if r.get("kind") == "plan"]
    if plans:
        latest = plans[-1]
        for step in (latest.get("data") or {}).get("steps") or []:
            if str(step.get("status", "pending")).lower() not in _DONE_STATUSES:
                out["steps"].append(f"plan step '{str(step.get('text', ''))[:80]}' still {step.get('status', 'pending')}")
    cited = " ".join(
        " ".join(str(e) for e in (r.get("evidence") or []))
        for r in records if r.get("kind") == "claim")
    for record in records:
        if record.get("kind") != "criterion":
            continue
        task = str((record.get("data") or {}).get("task") or "")
        if task and f"criterion:{task}" not in cited:
            out["criteria"].append(f"criterion:{task} has no claim citing it - `godmode claim \"<what held>\" "
                                   f"--cite criterion:{task} --cite cmd:<the check>`")
    try:
        from .godmode_loop import hypothesis_reset_required
        for finding in hypothesis_reset_required(records):
            out["hypotheses"].append(str(finding.get("detail", ""))[:160])
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a detector that cannot run adds nothing; the other three lists still answer
        pass
    return out


def scope_items(scope: dict[str, list[str]]) -> list[str]:
    return (scope["asks"] + scope["steps"] + scope["criteria"] + scope["hypotheses"]
            + scope.get("temporaries", []))


def measured_spend(transcript_path: str | Path | None) -> dict[str, int]:
    """Token spend the host itself wrote into the transcript, summed over
    every assistant message: input, output, cache creation and cache read,
    plus the assistant message count. Zero everywhere when there is no
    transcript; `source` says whether the numbers were measured."""
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0, "messages": 0}
    if not transcript_path:
        return {**totals, "tokens": 0, "source": "unavailable"}
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {**totals, "tokens": 0, "source": "unavailable"}
    for line in lines:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        usage = (entry.get("message") or {}).get("usage") or {}
        if not usage:
            continue
        totals["messages"] += 1
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            try:
                totals[key] += int(usage.get(key) or 0)
            except (TypeError, ValueError):
                totals[key] += 0  # a non-numeric usage field counts as nothing, stated
    tokens = totals["input_tokens"] + totals["output_tokens"] + totals["cache_creation_input_tokens"]
    return {**totals, "tokens": tokens, "source": "measured" if totals["messages"] else "unavailable"}


def context_size(transcript_path: str | Path | None) -> dict[str, Any]:
    """The window as it stands: the LAST assistant message's input, cache
    creation and cache read tokens summed - what the host sent the model
    on the most recent turn. Compaction playbook (2026-09-10): the danger
    line is ~70 percent, not the auto-compact trigger; a steered compact at
    a phase boundary keeps what a bare one drops."""
    out: dict[str, Any] = {"tokens": 0, "source": "unavailable", "turn": None}
    if not transcript_path:
        return out
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for index, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        usage = (entry.get("message") or {}).get("usage") or {}
        if not usage:
            continue
        total = 0
        for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            try:
                total += int(usage.get(key) or 0)
            except (TypeError, ValueError):
                total += 0  # a non-numeric usage field counts as nothing, stated
        out = {"tokens": total, "source": "measured", "turn": index}
    return out


def _digest(command: str) -> str:
    return hashlib.sha256(" ".join(str(command).split()).encode("utf-8")).hexdigest()[:16]


def repeat_failures(transcript_path: str | Path | None, command: str) -> dict[str, Any]:
    """How many times this exact command has already failed in the session
    with no tracked-file mutation (Edit/Write/NotebookEdit) after the last
    failure. A fourth identical run against an unchanged tree is the
    iteration trap in one number."""
    out = {"failures": 0, "mutated_since_last_failure": True, "digest": _digest(command)}
    if not transcript_path:
        return out
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    pending: dict[str, str] = {}
    failures = 0
    mutated_since = True
    for line in lines[-8000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "assistant" and isinstance(content, list):
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                name = part.get("name")
                if name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
                    mutated_since = True
                elif name in ("Bash", "PowerShell"):
                    pending[str(part.get("id"))] = _digest(str((part.get("input") or {}).get("command", "")))
        elif entry.get("type") == "user" and isinstance(content, list):
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_result":
                    continue
                digest = pending.pop(str(part.get("tool_use_id")), None)
                if digest != out["digest"]:
                    continue
                body = part.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                text = str(body or "")
                failed = bool(part.get("is_error")) or bool(
                    re.search(r"(?im)\bexit(?:ed)?(?: code)?\s+[1-9]\d*\b|^Traceback|\bFAILED\b|\bError\b:|\bfatal:", text))
                if failed:
                    failures += 1
                    mutated_since = False
                else:
                    failures = 0
    out["failures"] = failures
    out["mutated_since_last_failure"] = mutated_since
    return out


def commit_score_plateau(project: Path, window: int = 12, streak: int = 4) -> dict[str, Any] | None:
    """The local-minimum signal from the evidence carrier a search loop
    already leaves: `score = <n>` in commit subjects on the current branch.
    `streak` consecutive newest commits whose score did not beat the best
    before them is a plateau; the report carries the numbers."""
    try:
        done = subprocess.run(["git", "log", f"-{window}", "--format=%h %s"], cwd=str(project),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    scored: list[tuple[str, float]] = []
    for line in done.stdout.splitlines():
        match = _SCORE.search(line)
        if match:
            scored.append((line.split()[0], float(match.group(1))))
    if len(scored) < streak + 1:
        return None
    newest = scored[:streak]
    older_best = max(score for _sha, score in scored[streak:])
    if any(score > older_best for _sha, score in newest):
        return None
    return {
        "check": "score-plateau",
        "streak": streak,
        "best_before": older_best,
        "newest": [{"commit": sha, "score": score} for sha, score in newest],
        "detail": (f"the newest {streak} scored commits ({', '.join(f'{sha}={score:g}' for sha, score in newest)}) "
                   f"did not beat the best before them ({older_best:g}); the branch is on a plateau"),
    }

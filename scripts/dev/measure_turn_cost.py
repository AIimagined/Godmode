#!/usr/bin/env python3
"""Measure what Godmode's hooks cost one ordinary turn: the text they inject
and the time they take.

Drives the shipped hooks the way a host does - a JSON payload on stdin, one
interpreter per event - against a throwaway governed project whose archive
lives under a throwaway state home. Nothing on this machine's real archives
is read or written.

The turn is: a prompt, a floor read (`git log`), a script run
(`python script.py`), two edits of one tracked file, the post-edit hook for
each, and a Stop whose reply makes an unbacked claim; then the next prompt,
which is where parked notices come back. The session brief is measured
separately (once per session, not per turn).

Tokens are estimated as characters / 4 over every text field a hook prints
(`additionalContext`, `systemMessage`, `reason`), split into what reaches the
model and what reaches only the operator.

Usage:
    python scripts/dev/measure_turn_cost.py [--runs 5] [--json] [--compare-bytecode]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "hooks"
SESSION = "measure-session"

# Host markers the measuring shell may carry; a hook must see a plain
# Claude Code call, not whatever session launched this script.
_SCRUB = ("GROK_AGENT", "GROK_PLUGIN_ROOT", "GROK_HOOK_EVENT", "ANTIGRAVITY_AGENT",
          "ANTIGRAVITY_CONVERSATION_ID", "CURSOR_TRACE_ID", "GEMINI_CLI", "PLUGIN_ROOT",
          "CLAUDE_PLUGIN_ROOT", "CI", "GODMODE_HOST", "PYTHONPATH")


def _env(state: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    env["GODMODE_STATE_HOME"] = str(state)
    env["GODMODE_ATTENDED"] = "1"
    env["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    return env


def _project(base: Path, env: dict[str, str]) -> Path:
    project = base / "project"
    project.mkdir(parents=True)
    (project / "app.py").write_text(
        "def parse(text):\n    try:\n        return int(text)\n    except Exception:\n"
        "        pass\n", encoding="utf-8")
    (project / "script.py").write_text("print('ok')\n", encoding="utf-8")
    (project / "README.md").write_text("# fixture\n", encoding="utf-8")
    for command in (["init", "-q"], ["config", "user.email", "m@example.invalid"],
                    ["config", "user.name", "m"], ["add", "-A"], ["commit", "-qm", "seed"]):
        subprocess.run(["git", *command], cwd=project, check=True, capture_output=True)
    # Initialized through the runtime itself, under the throwaway state home.
    subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from godmode_runtime.godmode_anchor import resolve_anchor;"
         "from godmode_runtime.godmode_chronicle import Chronicle;"
         "Chronicle(resolve_anchor(sys.argv[2])).initialize()",
         str(REPO / "scripts"), str(project)],
        check=True, env=env, capture_output=True)
    return project


def _transcript(base: Path, reply: str) -> Path:
    path = base / "transcript.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": "fix the parser"}},
        {"type": "assistant", "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": reply}]}},
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def _texts(stdout: str) -> tuple[str, str]:
    """(model text, operator text) out of one hook's stdout."""
    model: list[str] = []
    operator: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            body = json.loads(line)
        except ValueError:
            continue
        if not isinstance(body, dict):
            continue
        specific = body.get("hookSpecificOutput") or {}
        context = specific.get("additionalContext") or body.get("additionalContext")
        if context:
            model.append(str(context))
        if body.get("decision") in ("block", "continue") and body.get("reason"):
            model.append(str(body["reason"]))
        reason = specific.get("permissionDecisionReason")
        if reason:
            model.append(str(reason))
        if body.get("systemMessage"):
            operator.append(str(body["systemMessage"]))
    return "\n".join(model), "\n".join(operator)


def _run(hook: str, args: list[str], payload: dict, env: dict[str, str],
         flags: list[str]) -> tuple[float, str]:
    # The launcher sends session events through the small front door.
    if hook == "godmode_session_hook.py":
        hook = "godmode_session_entry.py"
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, *flags, str(HOOKS / hook), *args],
        input=json.dumps(payload).encode("utf-8"), capture_output=True, env=env,
        timeout=120)
    return time.perf_counter() - started, result.stdout.decode("utf-8", "replace")


def _tokens(text: str) -> int:
    return (len(text) + 3) // 4


def _steps(project: Path, transcript: Path) -> list[tuple[str, str, list[str], dict]]:
    common = {"session_id": SESSION, "cwd": str(project), "transcript_path": str(transcript)}
    edit = {**common, "hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": str(project / "app.py"),
                           "old_string": "pass", "new_string": "return None"}}
    post = {**edit, "hook_event_name": "PostToolUse"}

    def bash(command: str) -> dict:
        return {**common, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command}}

    return [
        ("session-start", "godmode_session_hook.py", ["session-start"],
         {**common, "hook_event_name": "SessionStart", "source": "startup"}),
        ("user-prompt", "godmode_session_hook.py", ["user-prompt"],
         {**common, "hook_event_name": "UserPromptSubmit", "prompt": "fix the parser in app.py"}),
        ("pre-tool git log", "godmode_gate_fast.py", [], bash("git log --oneline -5")),
        ("pre-tool cd && git status", "godmode_gate_fast.py", [], bash("cd . && git status")),
        ("pre-tool python script.py", "godmode_gate_fast.py", [], bash("python script.py")),
        ("pre-tool Edit (1st)", "godmode_gate_fast.py", [], edit),
        ("post-edit (1st)", "godmode_post_edit.py", [], post),
        ("pre-tool Edit (2nd)", "godmode_gate_fast.py", [], edit),
        ("post-edit (2nd)", "godmode_post_edit.py", [], post),
        ("pre-tool Edit (3rd)", "godmode_gate_fast.py", [], edit),
        ("post-edit (3rd)", "godmode_post_edit.py", [], post),
        ("stop", "godmode_session_hook.py", ["stop"],
         {**common, "hook_event_name": "Stop", "stop_hook_active": False}),
        ("next user-prompt", "godmode_session_hook.py", ["user-prompt"],
         {**common, "hook_event_name": "UserPromptSubmit", "prompt": "thanks, continue"}),
    ]


def _plugin_copy(base: Path) -> None:
    """Run the hooks from a copy of the plugin with no byte-code beside it,
    the way an installed plugin runs (its cache directory never holds any):
    a working tree's own `__pycache__` would otherwise serve `-B` runs."""
    global HOOKS
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "hooks", base / "plugin" / "hooks", ignore=ignore)
    shutil.copytree(REPO / "scripts", base / "plugin" / "scripts", ignore=ignore)
    HOOKS = base / "plugin" / "hooks"


def measure(runs: int, flagsets: list[list[str]]) -> list[dict]:
    """One report per flag set; runs are interleaved across the sets so
    machine load falls on each of them alike. One unmeasured warm-up pass
    per set fills any byte-code cache first."""
    base = Path(tempfile.mkdtemp(prefix="godmode-turncost-"))
    env = _env(base / "state")
    try:
        _plugin_copy(base)
        project = _project(base, env)
        transcript = _transcript(
            base, "I fixed the parser in app.py. All tests pass and the change is complete.")
        steps = _steps(project, transcript)
        # Opt the fixture into post-edit quality so that hook has findings to show.
        (project / ".godmode-authorization-policy.json").write_text(
            json.dumps({"post_edit_quality": True}), encoding="utf-8")
        timings = [{name: [] for name, *_ in steps} for _ in flagsets]
        texts: list[dict[str, tuple[str, str]]] = [{} for _ in flagsets]
        for flags in flagsets:
            for _name, hook, args, payload in steps:
                _run(hook, args, {**payload, "session_id": f"{SESSION}-warm"}, env, flags)
        for index in range(runs):
            for which, flags in enumerate(flagsets):
                # Every run is a new session so once-per-session lines count every time.
                session = f"{SESSION}-{index}-{which}"
                for name, hook, args, payload in steps:
                    payload = {**payload, "session_id": session}
                    elapsed, stdout = _run(hook, args, payload, env, flags)
                    timings[which][name].append(elapsed)
                    if index == 0:
                        texts[which][name] = _texts(stdout)
        reports = []
        for which, flags in enumerate(flagsets):
            rows = []
            for name, *_ in steps:
                model, operator = texts[which].get(name, ("", ""))
                rows.append({"step": name,
                             "median_s": round(statistics.median(timings[which][name]), 3),
                             "max_s": round(max(timings[which][name]), 3),
                             "model_tokens": _tokens(model), "operator_tokens": _tokens(operator),
                             "model_text": model[:300]})
            turn = [r for r in rows if r["step"] != "session-start"]
            reports.append({
                "flags": flags,
                "rows": rows,
                "brief_tokens": rows[0]["model_tokens"],
                "turn_model_tokens": sum(r["model_tokens"] for r in turn),
                "turn_operator_tokens": sum(r["operator_tokens"] for r in turn),
                "turn_hook_seconds": round(sum(r["median_s"] for r in turn), 3),
            })
        return reports
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compare-bytecode", action="store_true",
                        help="interleave -B with a private byte-code cache and report both")
    args = parser.parse_args()
    cache = Path(tempfile.mkdtemp(prefix="godmode-measure-pycache-"))
    flagsets = [["-I", f"-Xpycache_prefix={cache}"]]
    if args.compare_bytecode:
        flagsets.insert(0, ["-I", "-B"])
    try:
        reports = measure(args.runs, flagsets)
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    if args.json:
        print(json.dumps(reports, indent=2))
        return 0
    for report in reports:
        print(f"flags: {' '.join(report['flags'])}")
        print(f"{'step':28} {'median s':>9} {'max s':>7} {'model tok':>10} {'oper tok':>9}")
        for row in report["rows"]:
            print(f"{row['step']:28} {row['median_s']:>9.3f} {row['max_s']:>7.3f} "
                  f"{row['model_tokens']:>10} {row['operator_tokens']:>9}")
        print(f"session brief (model tokens, once per session): {report['brief_tokens']}")
        print(f"ordinary turn: model tokens {report['turn_model_tokens']}, operator tokens "
              f"{report['turn_operator_tokens']}, hook seconds {report['turn_hook_seconds']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

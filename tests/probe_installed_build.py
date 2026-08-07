"""Drive the *installed* plugin's hook, not the working tree's.

Every gate defect this session was found by installing a build and using it,
never by the suite — and twice I reported a live result that turned out to come
from a stale cache. The working tree and the artifact a user actually receives
are different things, and only one of them is what ships.

Run directly; not collected by the suite, because it asserts about a machine's
plugin cache rather than about this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

CACHE = Path.home() / ".claude" / "plugins" / "cache" / "aiimagined" / "godmode"

MUST_ALLOW = (
    ("plain listing", "Bash", {"command": "ls"}),
    ("piped compound read", "Bash", {"command": "ls scripts | head -3 && git status --short"}),
    ("shell loop", "Bash", {"command": "for f in *.md; do wc -l $f; done"}),
    ("input redirect", "Bash", {"command": "wc -l < README.md"}),
    ("descriptor duplication", "Bash", {"command": "python -m unittest discover -s tests 2>&1"}),
    ("substitution over a read", "Bash", {"command": "echo $(git rev-parse HEAD)"}),
    ("naming a command in an argument", "Bash", {"command": 'grep "git push" CHANGELOG.md'}),
    ("powershell read", "PowerShell", {"command": "Get-ChildItem | Select-Object Name"}),
    ("stage", "Bash", {"command": "git add -A"}),
    ("commit", "Bash", {"command": "git commit -m 'a message'"}),
    ("edit a project file", "Edit", {"file_path": "<PROJECT>/tests/test_gate_usability.py"}),
    ("write a project file", "Write", {"file_path": "<PROJECT>/notes.md"}),
    ("redirect inside the tree", "Bash", {"command": "echo hello > scratch.txt"}),
)

MUST_DENY = (
    ("force push", "Bash", {"command": "git push --force origin main"}),
    ("recursive delete", "Bash", {"command": "rm -rf build"}),
    ("amend", "Bash", {"command": "git commit --amend"}),
    ("quoted script", "Bash", {"command": 'bash -c "rm -rf /"'}),
    ("destructive substitution", "Bash", {"command": "echo $(rm -rf build)"}),
    ("edit inside .git", "Edit", {"file_path": "<PROJECT>/.git/config"}),
    ("write outside the tree", "Write", {"file_path": "<PARENT>/outside.txt"}),
    ("safe head, dangerous tail", "Bash", {"command": "git status && git push origin main"}),
)


def newest_installed() -> Path:
    versions = sorted(
        (p for p in CACHE.iterdir() if p.is_dir()),
        key=lambda p: tuple(int(x) for x in p.name.split(".") if x.isdigit()))
    return versions[-1]


def decide(hook: Path, project: Path, tool: str, tool_input: dict) -> tuple[str, str]:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(hook), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project))
    body = (done.stdout or "").strip()
    if not body:
        return "allow", ""
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return (str(specific.get("permissionDecision", "?")),
            str(specific.get("permissionDecisionReason", "")))


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    installed = newest_installed()
    hook = installed / "hooks" / "godmode_session_hook.py"
    print(f"installed build: {installed.name}   ({hook})\n")

    def resolve(payload: dict) -> dict:
        return {k: str(v).replace("<PROJECT>", str(project))
                            .replace("<PARENT>", str(project.parent))
                for k, v in payload.items()}

    wrong = []
    for expected, cases in (("allow", MUST_ALLOW), ("deny", MUST_DENY)):
        for label, tool, payload in cases:
            decision, reason = decide(hook, project, tool, resolve(payload))
            mark = "OK " if decision == expected else "!! "
            if decision != expected:
                wrong.append(f"{label}: expected {expected}, got {decision}")
            print(f"{mark}{label:34} {tool:11} -> {decision:6} {reason.split('.')[0][:46]}")
        print()

    if wrong:
        print(f"MISMATCHES ({len(wrong)}):")
        for line in wrong:
            print("  " + line)
        return 1
    print(f"the installed {installed.name} build behaves as released.")
    print("Run it against a live session too: the probe proves the artifact is "
          "right, only a session proves the integration is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

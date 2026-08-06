"""Differential network capture: prove the runtime made zero connections.

"No network at runtime" is easy to claim and easy to silently break - one
imported convenience library phoning home would never show up in a code review
of our own files. So the claim is not asserted, it is measured: every named CLI
surface runs in a child process whose interpreter carries an audit hook on the
socket layer, and the diff against an expected-empty capture is the evidence.
An empty capture is only evidence if the detector demonstrably works, so the
gate first plants a deliberate connection attempt and must see it; a detector
that cannot see the plant raises instead of reporting clean. Fail closed,
never a false "clean".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from .godmode_errors import GodmodeError

# The CLI surfaces the PRD names as the runtime's user-facing perimeter.
SURFACES = ("init", "inspect", "resume", "doctor", "report")

# Substituted in command argv with the throwaway project differential creates,
# so callers can name the surfaces without knowing the temp path in advance.
PROJECT_TOKEN = "{project}"

_CHILD_TIMEOUT = 120

# Installed in the child via a sitecustomize.py on a prepended PYTHONPATH: the
# site module imports it before user code runs, so the hook observes the whole
# process lifetime. Audit hooks cannot be removed once added, which is exactly
# the property a gate wants. Appends one JSON line per socket-shaped event to
# the file named by GODMODE_NET_AUDIT; anything else it stays out of.
_AUDITOR = """\
import json
import os
import sys

_GODMODE_AUDIT_PATH = os.environ.get("GODMODE_NET_AUDIT")
_GODMODE_EVENTS = ("socket.connect", "socket.getaddrinfo", "socket.create_connection")

if _GODMODE_AUDIT_PATH:
    def _godmode_net_hook(event, args):
        if event in _GODMODE_EVENTS:
            try:
                with open(_GODMODE_AUDIT_PATH, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(
                        {"event": event, "args": [repr(item) for item in args]}
                    ) + "\\n")
            except OSError:
                pass
    sys.addaudithook(_godmode_net_hook)
"""


class NetgateError(GodmodeError):
    """The detector could not prove it detects; results are not trustworthy."""


def capture(command: list[str], project: Path) -> dict[str, Any]:
    """Run a command with a socket-auditing bootstrap and report what it dialled.

    The audit hook lives in the child, not here: a parent cannot observe another
    process's sockets with the standard library alone, so the child's own
    interpreter is enlisted via sitecustomize and reports through a file.
    """
    with tempfile.TemporaryDirectory() as temporary:
        bootstrap = Path(temporary) / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "sitecustomize.py").write_text(_AUDITOR, encoding="utf-8")
        audit_file = Path(temporary) / "net-audit.jsonl"

        # Copy-and-modify, never replace: on Windows a bare environment loses
        # SYSTEMROOT and friends and the child fails for unrelated reasons.
        env = os.environ.copy()
        env["GODMODE_NET_AUDIT"] = str(audit_file)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(bootstrap) + (os.pathsep + existing if existing else "")
        )

        completed = subprocess.run(
            command,
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=_CHILD_TIMEOUT,
        )

        connections: list[dict[str, Any]] = []
        if audit_file.exists():
            for line in audit_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    connections.append(json.loads(line))

    return {
        "command": list(command),
        "exit_code": completed.returncode,
        "connections": connections,
        "clean": len(connections) == 0,
    }


def _plant_detected(project: Path) -> bool:
    """Run a deliberate resolver call in a child and ask whether it was seen."""
    planted = capture(
        [
            sys.executable,
            "-c",
            "import socket\n"
            "try:\n"
            "    socket.getaddrinfo('localhost', 80)\n"
            "except OSError:\n"
            "    pass\n",
        ],
        project,
    )
    return not planted["clean"]


def _require_working_detector(project: Path) -> None:
    """Fail closed: an empty capture from a blind detector is not evidence.

    sitecustomize only imports when the child's site module runs (isolated mode
    or -S would skip it), so the mechanism is proven per invocation with a plant
    rather than assumed from documentation.
    """
    if not _plant_detected(project):
        raise NetgateError(
            "netgate cannot detect a planted connection attempt on this "
            "interpreter (sitecustomize did not install the audit hook); "
            "refusing to report clean"
        )


def _default_commands(project: Path) -> list[list[str]]:
    script = str(Path(project) / "scripts" / "godmode.py")
    return [
        [sys.executable, script, "--project", PROJECT_TOKEN, surface]
        for surface in SURFACES
    ]


def differential(
    project: Path, commands: list[list[str]] | None = None
) -> dict[str, Any]:
    """Run each CLI surface against a throwaway project; any connection fails.

    The throwaway project and a redirected GODMODE_STATE_HOME keep the sweep
    from touching real state: the gate must be able to run anywhere, including
    CI, without leaving a mark. The expected capture is empty, so the diff
    degenerates to "list everything observed" - and the empty diff, produced by
    a detector that just proved it can see, IS the evidence for the claim.
    """
    _require_working_detector(project)
    if commands is None:
        commands = _default_commands(project)

    commands_run: list[list[str]] = []
    violations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temporary:
        throwaway = Path(temporary) / "project"
        throwaway.mkdir()
        state = Path(temporary) / "state"
        original_state = os.environ.get("GODMODE_STATE_HOME")
        os.environ["GODMODE_STATE_HOME"] = str(state)
        try:
            for command in commands:
                resolved = [
                    argument.replace(PROJECT_TOKEN, str(throwaway))
                    for argument in command
                ]
                report = capture(resolved, project)
                commands_run.append(resolved)
                if not report["clean"]:
                    violations.append({
                        "command": resolved,
                        "endpoints": report["connections"],
                    })
        finally:
            if original_state is None:
                os.environ.pop("GODMODE_STATE_HOME", None)
            else:
                os.environ["GODMODE_STATE_HOME"] = original_state

    return {
        "commands_run": commands_run,
        "violations": violations,
        "clean": len(violations) == 0,
    }


def _self_check() -> None:
    project = Path(__file__).resolve().parents[2]

    # The real gate, expected clean: no surface may open a connection.
    sweep = differential(project)
    assert sweep["clean"], sweep["violations"]
    assert len(sweep["commands_run"]) == len(SURFACES), sweep

    # Plant-and-observe: the same machinery must catch a deliberate attempt,
    # otherwise the clean sweep above proved nothing.
    planted = capture(
        [sys.executable, "-c",
         "import socket\n"
         "try:\n"
         "    socket.getaddrinfo('localhost', 80)\n"
         "except OSError:\n"
         "    pass\n"],
        project,
    )
    assert not planted["clean"], "planted connection attempt went undetected"
    assert any(
        entry["event"] == "socket.getaddrinfo" for entry in planted["connections"]
    ), planted

    print("godmode_netgate self-check OK")


if __name__ == "__main__":
    _self_check()

"""CX-6: the end-to-end harness.

Every earlier CX unit tested one layer: the classifier against hand-written
operation strings, the adapter against a payload dict, the git backstop
against a real git subprocess. None of them proves the thing an operator
actually cares about — that a real host, sending a real payload, through the
real hook subprocess, produces a decision that changes what the filesystem
and the git remote actually look like afterward.

This module is a HOST SIMULATOR, not a mock. It never imports the hook's own
decision logic and never patches anything in-process: every scenario spawns
the real `hooks/godmode_session_hook.py` (or the real fast gate) as a
subprocess, exactly the way `tests/test_hook_end_to_end.py` and
`tests/test_grok_host_contract.py` already do, and reads its stdout/exit code
back cold.

**The four-plane checklist** (Plan amendments 4), enforced by
`four_plane_check` on every scenario below:

1. **Hook process exit code** — the real subprocess's own return code.
2. **Decision envelope** — the JSON object printed on stdout (or the
   empty-body silent-allow case).
3. **Host interpretation** — what a REAL host would read from (1)+(2),
   simulated per that host's own documented contract (`HOST_INTERPRETERS`
   below) — never godmode's own internal `preview["allow"]`, which no host
   ever sees.
4. **Real-world side effect** — the actual file/git state after this
   harness, ACTING AS THE HOST, honors interpretation (3): it performs the
   underlying operation only on `allow`/consumed-`ask`, and refrains
   otherwise. An `allow` verdict is only correct when the state changed in
   the SPECIFIC way expected (positive evidence); a `deny`/`ask` verdict is
   only correct when the state matches its OWN recorded baseline, not merely
   "nothing observably happened" — silence is never allow, and an unchecked
   absence is never proof of a deny either.

A scenario passes `four_plane_check` only when all four planes agree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
FAST_GATE = PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py"

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

# ---------------------------------------------------------------------------
# Git plumbing — same discipline as tests/test_githooks.py: real git
# subprocesses, never mocked, because a mocked git is exactly the kind of
# "empty stdout read as allow" shortcut this whole suite exists to refuse.
# ---------------------------------------------------------------------------


def git(*args: str, cwd: Path, env: dict[str, str] | None = None,
        timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True,
        timeout=timeout, env=env,
    )


def init_repo(project: Path) -> None:
    project.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "e2e@godmode.invalid"],
        ["config", "user.name", "godmode-e2e"],
        # Pinned rather than left to `git init`'s machine-local default -
        # every push/remote scenario below assumes `main`.
        ["checkout", "-q", "-b", "main"],
    ):
        result = git(*args, cwd=project)
        assert result.returncode == 0, result.stderr


def commit_file(project: Path, name: str, content: str, env: dict[str, str] | None = None) -> str:
    target = project / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git("add", name, cwd=project, env=env)
    committed = git("commit", "-q", "-m", f"e2e: {name}", cwd=project, env=env)
    assert committed.returncode == 0, committed.stderr
    return git("rev-parse", "HEAD", cwd=project, env=env).stdout.strip()


def head_of(project: Path, ref: str = "HEAD") -> str:
    return git("rev-parse", ref, cwd=project).stdout.strip()


def remote_ref(remote: Path, ref: str = "main") -> str | None:
    result = git("rev-parse", f"refs/heads/{ref}", cwd=remote)
    return result.stdout.strip() if result.returncode == 0 else None


# ---------------------------------------------------------------------------
# The temp-repo builder.
# ---------------------------------------------------------------------------


@dataclass
class E2ERepo:
    """A real, throwaway git work repo (and optionally a bare remote), with
    its own isolated godmode state directory so no scenario ever touches
    this real checkout's own archive."""

    project: Path
    state: Path
    remote: Path | None = None
    archive: Chronicle | None = None

    def env(self, *, host: str | None = None, extra: dict[str, str] | None = None
           ) -> dict[str, str]:
        """The environment a real host subprocess would run this hook
        under. `GODMODE_HOST`/`GROK_AGENT`/`CLAUDE_CODE_ENTRYPOINT` are
        always cleared first (mirroring `test_grok_host_contract.py`'s
        `_run`) so no scenario accidentally inherits this OWN process's
        identity - the payload's own shape, or an explicit `host=`, is what
        decides detection, exactly as a real subprocess would see it.
        """
        environment = os.environ.copy()
        environment["GODMODE_STATE_HOME"] = str(self.state)
        for stale in ("GODMODE_HOST", "GROK_AGENT", "CLAUDE_CODE_ENTRYPOINT"):
            environment.pop(stale, None)
        if host:
            environment["GODMODE_HOST"] = host
        if extra:
            environment.update(extra)
        return environment


@contextmanager
def e2e_repo(*, with_remote: bool = False, seed: bool = True):
    """Yield an `E2ERepo`: a real git work tree, isolated godmode state, and
    (when `with_remote`) a real bare remote already tracking `main`."""
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        state = base / "state"
        init_repo(project)
        repo = E2ERepo(project=project, state=state)
        if seed:
            commit_file(project, "README.md", "seed\n", env=repo.env())
        if with_remote:
            remote = base / "remote.git"
            git("init", "-q", "--bare", str(remote), cwd=base)
            git("remote", "add", "origin", str(remote), cwd=project, env=repo.env())
            pushed = git("push", "-q", "-u", "origin", "main", cwd=project, env=repo.env())
            assert pushed.returncode == 0, pushed.stderr
            repo.remote = remote
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
        repo.archive = archive
        yield repo


def reopen_archive(repo: E2ERepo) -> Chronicle:
    """Re-open the SAME on-disk archive a subprocess just wrote to - so a
    test reads what actually landed, never what stdout merely claimed."""
    with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(repo.state)}, clear=False):
        return Chronicle(resolve_anchor(repo.project))


# ---------------------------------------------------------------------------
# Per-host payload dialects. Field spellings and event names are copied from
# the same sources CX-2/CX-6's own binding docstrings cite - never re-guessed
# here: `godmode_hostevent.py`'s module docstring (Claude/Codex/Grok tool
# maps) and `tests/test_grok_host_contract.py` (Grok's exact camelCase wire
# shape, drawn from the operator's live probe).
# ---------------------------------------------------------------------------


def claude_shell(command: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": cwd}


def claude_edit(file_path: str, cwd: str, tool: str = "Edit") -> dict[str, Any]:
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": file_path}, "cwd": cwd}


def claude_read(file_path: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "PreToolUse", "tool_name": "Read",
            "tool_input": {"file_path": file_path}, "cwd": cwd}


def codex_shell(command: str, cwd: str) -> dict[str, Any]:
    # `pre_tool_use`: CX-3's own instruction is "verify exact names against
    # the host's documented config before coding; if unverifiable, the
    # manifest omits it" - the SNAKE_CASE spelling is this harness's
    # replay-time convention (matching `godmode_hostevent.is_pretool_event`'s
    # own recognised set), not a confirmed Codex fact; see this file's
    # module docstring in `test_host_e2e.py` for the honesty note this
    # carries forward.
    return {"hookEventName": "pre_tool_use", "toolName": "shell_command",
            "toolInput": {"command": command}, "cwd": cwd}


def codex_apply_patch(patch_body: str, cwd: str) -> dict[str, Any]:
    return {"hookEventName": "pre_tool_use", "toolName": "apply_patch",
            "toolInput": {"input": patch_body}, "cwd": cwd}


def codex_orchestrated_shell(command: str, cwd: str, *, request_id: str) -> dict[str, Any]:
    """Codex's `functions.exec` orchestration wrapper around a shell call -
    Plan amendments 2's "leaf tool, orchestration tool, or normalized alias"
    shape, unwrapped by `godmode_hostevent._codex_unwrap`'s `name`+`arguments`
    branch."""
    return {"hookEventName": "pre_tool_use", "toolName": "functions.exec",
            "toolInput": {"name": "shell_command", "arguments": {"command": command}},
            "cwd": cwd, "requestId": request_id}


def grok_shell(command: str, cwd: str) -> dict[str, Any]:
    return {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
            "toolInput": {"command": command}, "cwd": cwd}


def grok_write(file_path: str, cwd: str) -> dict[str, Any]:
    return {"hookEventName": "pre_tool_use", "toolName": "write",
            "toolInput": {"file_path": file_path}, "cwd": cwd}


def cursor_shell(command: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "beforeShellExecution", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": cwd}


def cursor_edit(file_path: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "preToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": file_path}, "cwd": cwd}


def gemini_shell(command: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "BeforeTool", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": cwd}


def gemini_edit(file_path: str, cwd: str) -> dict[str, Any]:
    return {"hook_event_name": "BeforeTool", "tool_name": "Edit",
            "tool_input": {"file_path": file_path}, "cwd": cwd}


HOST_SHELL_BUILDERS: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "claude": claude_shell, "codex": codex_shell, "grok": grok_shell,
    "cursor": cursor_shell, "gemini": gemini_shell,
}
HOST_EDIT_BUILDERS: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "claude": claude_edit, "grok": grok_write, "cursor": cursor_edit,
    "gemini": gemini_edit,
}


# ---------------------------------------------------------------------------
# Running the real hook subprocess.
# ---------------------------------------------------------------------------


@dataclass
class HookResult:
    returncode: int
    stdout: str
    stderr: str
    envelope: dict[str, Any]
    latency_seconds: float


def run_hook(payload: dict[str, Any], repo: E2ERepo, *, host: str | None = None,
             event: str = "pre-action", extra_env: dict[str, str] | None = None,
             fast: bool = False, timeout: int = 60) -> HookResult:
    """Spawn the real hook (or fast gate) exactly as a host would, and parse
    whatever it printed. Never raises on unparsable stdout - a malformed
    response is itself a scenario this harness has to be able to observe,
    not something it hides behind an exception."""
    script = FAST_GATE if fast else HOOK
    args = [sys.executable, str(script)]
    if not fast:
        args += [event, "--project", str(repo.project)]
    started = time.perf_counter()
    completed = subprocess.run(
        args, input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        cwd=str(repo.project), env=repo.env(host=host, extra=extra_env),
    )
    elapsed = time.perf_counter() - started
    body = (completed.stdout or "").strip()
    envelope: dict[str, Any] = {}
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                envelope = parsed
        except json.JSONDecodeError:
            envelope = {}
    return HookResult(completed.returncode, completed.stdout, completed.stderr,
                      envelope, elapsed)


# ---------------------------------------------------------------------------
# Host interpretation — simulating what a REAL host reads back, never
# godmode's own internal preview. Three documented key families (Plan
# amendments 4's own phrasing): exit-code-primary, a `decision` key, and a
# `permission` key - plus Claude's own `hookSpecificOutput.permissionDecision`
# as the reference dialect every other key is layered onto
# (`godmode_hostevent.render_decision` always emits all of them at once, so
# a host reading only the one key it understands is always safe).
#
# Codex's own JSON schema is UNDOCUMENTED (CX-5's own concern #1 names this
# directly) - the exit-code interpreter is this harness's deliberately
# conservative stand-in: it trusts ONLY the process exit code (0 => proceed,
# 2 => refused), the one signal every sandboxed-CLI convention this project
# could find documentation for agrees on, and never leans on a JSON key this
# harness cannot independently confirm Codex reads. Gemini is bucketed with
# Grok (both fold `ask` to `deny` and have no host-native "ask" of their
# own - `HOSTS_WITH_ASK` in `godmode_hostevent.py`), so the same `decision`
# key interpretation applies to both.
# ---------------------------------------------------------------------------


def _from_exit_code(result: HookResult) -> str:
    if result.returncode == 2:
        return "deny"
    if result.returncode == 0:
        return "allow" if not result.envelope else "deny"
    return "fail-closed-unrecognized-exit"


def _claude_interpretation(result: HookResult) -> str:
    # Deliberately does NOT short-circuit on an empty envelope before
    # checking the exit code: silence is only a legitimate allow when
    # PAIRED with exit 0 (the real Claude contract) - an empty envelope
    # alongside a garbage exit code (an unparsable/unexpected response) must
    # fall through to `_from_exit_code`'s own fail-closed sentinel, never
    # read as permission just because nothing else was printed.
    specific = result.envelope.get("hookSpecificOutput") if result.envelope else None
    if isinstance(specific, dict) and "permissionDecision" in specific:
        return str(specific["permissionDecision"])
    return _from_exit_code(result)


def _cursor_interpretation(result: HookResult) -> str:
    if result.envelope and "permission" in result.envelope:
        return str(result.envelope["permission"])
    return _from_exit_code(result)


def _decision_key_interpretation(result: HookResult) -> str:
    """Grok/Gemini: a `decision` key, deny/allow only (no `ask`). A real
    Grok host FAILS OPEN on any exit code other than 0/2 (Addendum 6's
    probe finding, the reason `render_decision` never emits exit 3
    anywhere) - simulated here rather than asserted away, so a scenario
    that somehow produced an unrecognised exit is caught as an ALLOW, the
    same (dangerous) way the real host would read it, rather than silently
    passing this harness's own check.
    """
    if result.returncode not in (0, 2):
        return "allow"  # fail-open, matching the real host's own documented behavior
    if not result.envelope:
        return "allow"
    if "decision" in result.envelope:
        return str(result.envelope["decision"])
    return _from_exit_code(result)


def _codex_interpretation(result: HookResult) -> str:
    return _from_exit_code(result)


HOST_INTERPRETERS: dict[str, Callable[[HookResult], str]] = {
    "claude": _claude_interpretation,
    "cursor": _cursor_interpretation,
    "grok": _decision_key_interpretation,
    "gemini": _decision_key_interpretation,
    "codex": _codex_interpretation,
}


def interpret(host: str, result: HookResult) -> str:
    interpreter = HOST_INTERPRETERS.get(host)
    if interpreter is None:
        raise AssertionError(f"no host interpreter registered for {host!r}")
    return interpreter(result)


# ---------------------------------------------------------------------------
# The four-plane assertion.
# ---------------------------------------------------------------------------


class FourPlaneFailure(AssertionError):
    pass


@dataclass
class FourPlaneReport:
    scenario: str
    host: str
    exit_code: int
    envelope: dict[str, Any]
    host_decision: str
    expected_decision: str
    side_effect_verified: bool
    latency_seconds: float


def four_plane_check(
    scenario: str, host: str, result: HookResult, *,
    expect: str,
    on_allow: Callable[[], None] | None = None,
    verify_side_effect: Callable[[str], bool],
) -> FourPlaneReport:
    """Run all four planes for one scenario and raise `FourPlaneFailure`
    naming exactly which plane disagreed.

    `expect` is the host-neutral verdict this scenario is built to prove:
    `"allow"` or `"blocked"` (covers both `ask` and `deny` - a host tool
    call has no field a capability can travel in, so a protected operation
    is never SUPPOSED to reach `allow` this way; see
    `hooks/godmode_session_hook.py`'s own `_decision_for` docstring).

    Plane 4 (`verify_side_effect`) is called AFTER this function decides
    whether to run `on_allow` (which performs the real operation) - so the
    callback always sees the state the decision actually produced, and
    receives `expect` so it can assert POSITIVE evidence for whichever
    branch actually ran, never "nothing happened, so it must be fine."
    """
    # Plane 1: exit code. The real hook's own contract (CX-2): 0 for a
    # decided pretool response (Claude/Cursor keep 0 for ask/deny too, via
    # the JSON envelope; Grok/Codex/Gemini's own "exit 2 is also legal"
    # alternative is a real accepted shape, not a bug) - 2 is legal on any
    # host, 3 must never appear.
    if result.returncode not in (0, 2):
        raise FourPlaneFailure(
            f"{scenario}/{host}: plane 1 (exit code) - got {result.returncode}, "
            "expected 0 or 2; exit 3 was removed everywhere in CX-2 because at "
            "least one host (Grok) fail-opens on any code it does not recognise")

    # Plane 2: decision envelope. Silence is a legitimate allow envelope
    # (`{}`) - but ONLY when plane 3 below also reads it as allow; an empty
    # envelope paired with a blocked expectation is a real bug, not noise.
    envelope = result.envelope

    # Plane 3: host interpretation, from ONLY planes 1+2 - never from
    # anything godmode's own process computed internally.
    host_decision = interpret(host, result)
    if host_decision == "fail-closed-unrecognized-exit":
        # This harness's own honesty rule (module docstring): an exit code
        # neither host contract recognises must never be read as an
        # implicit allow BY THIS TEST, even for hosts whose real-world
        # behavior (Grok) would fail open on it - that fail-open path is
        # itself asserted, deliberately, by `_decision_key_interpretation`;
        # reaching this branch means a host with NO documented fail-open
        # convention (Claude/Cursor/Codex) returned a code none of their
        # contracts define, which is a hook defect to surface, never a
        # decision to guess at.
        raise FourPlaneFailure(
            f"{scenario}/{host}: plane 3 (host interpretation) - exit code "
            f"{result.returncode} has no meaning in {host}'s documented contract")
    normalized = "allow" if host_decision == "allow" else "blocked"
    if normalized != expect:
        raise FourPlaneFailure(
            f"{scenario}/{host}: plane 3 (host interpretation) - expected "
            f"{expect!r}, host would read {host_decision!r} "
            f"(exit={result.returncode}, envelope={envelope!r})")

    if normalized == "allow" and on_allow is not None:
        on_allow()

    # Plane 4: the real filesystem/git side effect, checked AFTER the
    # harness (acting as an honest host) has honored planes 1-3.
    if not verify_side_effect(normalized):
        raise FourPlaneFailure(
            f"{scenario}/{host}: plane 4 (real-world side effect) - state did "
            f"not match what a {normalized!r} verdict requires")

    return FourPlaneReport(
        scenario=scenario, host=host, exit_code=result.returncode,
        envelope=envelope, host_decision=host_decision, expected_decision=expect,
        side_effect_verified=True, latency_seconds=result.latency_seconds,
    )


# ---------------------------------------------------------------------------
# Perf stage timing (contract point: "publish median AND p95 per stage").
# ---------------------------------------------------------------------------


def timed(fn: Callable[[], Any], *, repeats: int = 11) -> list[float]:
    """Run `fn` `repeats` times, discarding nothing, returning raw seconds.
    The first call (interpreter/module warm-up) is intentionally INCLUDED -
    `median`/`p95` below are resistant to one slow outlier, and hiding the
    cold-start cost would make the published baseline describe a call
    pattern (already-warm process) this harness never actually uses,
    since every stage here re-spawns a fresh `python` subprocess.
    """
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - started)
    return samples


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]

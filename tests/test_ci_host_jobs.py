"""NS-8e: the dispatch workflow's per-host CI jobs cannot silently drift
from `scripts/dev/gen_host_ci_jobs.py`, and each generated job's own shell
logic is proven locally rather than trusted: once with the real launcher
(exit 0, a deny observed) and once with a launcher deliberately corrupted
so it cannot deny anything (non-zero) - the same "a broken launcher turns
the job red" acceptance line the plan states for this task.

The corrupted-launcher half never touches the committed `hooks/run-hook.sh`
- a throwaway copy stands in for it - because every generated job shares
that one script, and a test that broke the real file would make every
other test in this run (and the actual hook the harness runs on Claude
itself) fail alongside it.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
DEV_SCRIPTS = PLUGIN_ROOT / "scripts" / "dev"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import gen_host_ci_jobs as gen  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

WORKFLOW_PATH = PLUGIN_ROOT / ".github" / "workflows" / "godmode-verify.yml"


class WorkflowDriftTests(unittest.TestCase):
    def test_committed_workflow_matches_the_generator(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        generated = gen.generate_workflow(committed)
        self.assertEqual(
            generated, committed,
            f"{WORKFLOW_PATH} is stale - regenerate with "
            "`python scripts/dev/gen_host_ci_jobs.py`",
        )

    def test_the_workflow_carries_the_marker_pair(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(gen.BEGIN_MARKER, committed)
        self.assertIn(gen.END_MARKER, committed)
        self.assertLess(committed.index(gen.BEGIN_MARKER), committed.index(gen.END_MARKER))

    def test_generator_raises_without_a_marker_pair(self) -> None:
        with self.assertRaises(ValueError):
            gen.generate_workflow("jobs:\n  required:\n    needs: [verify]\n")

    def test_generator_is_idempotent(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        once = gen.generate_workflow(committed)
        twice = gen.generate_workflow(once)
        self.assertEqual(once, twice)

    def test_a_hand_edited_block_is_detected_as_drift(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        tampered = committed.replace("host-claude:", "host-claude-hand-edited:", 1)
        generated = gen.generate_workflow(tampered)
        self.assertNotEqual(generated, tampered)

    def test_the_workflow_stays_dispatch_only(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", committed)
        self.assertNotIn("\npush:\n", committed)
        self.assertNotIn("\npull_request:\n", committed)


class EveryHostGetsAJobTests(unittest.TestCase):
    def test_every_union_host_has_a_generated_job(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        hosts = gen._union_hosts()
        self.assertGreaterEqual(len(hosts), 8, hosts)
        for host in hosts:
            with self.subTest(host=host):
                self.assertIn(f"  host-{host}:", committed)

    def test_every_generated_job_is_in_the_required_needs_list(self) -> None:
        committed = WORKFLOW_PATH.read_text(encoding="utf-8")
        needs_line = next(
            line for line in committed.splitlines() if line.strip().startswith("needs: [")
        )
        for host in gen._union_hosts():
            with self.subTest(host=host):
                self.assertIn(f"host-{host}", needs_line)

    def test_claude_is_covered_even_though_it_has_no_wire_route_or_builder(self) -> None:
        from godmode_runtime import godmode_host_manifests as host_manifests
        from godmode_runtime import godmode_wire

        self.assertNotIn("claude", host_manifests.HOOK_ARTIFACTS)
        self.assertNotIn("claude", godmode_wire.WIRE_HOSTS)
        self.assertIn("claude", gen._union_hosts())


def _sh() -> str | None:
    found = shutil.which("bash") or shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parent.parent / "usr" / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _run(sh: str, script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sh, "-c", script], cwd=PLUGIN_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, env=env, stdin=subprocess.DEVNULL,
    )


def _install(sh: str, host: str, project: Path) -> subprocess.CompletedProcess:
    script = "set -e\n" + "\n".join(
        [f'project="{project.as_posix()}"'] + gen.install_body_lines(host)
    )
    return _run(sh, script, scrubbed_env())


def _fire(sh: str, project: Path, state: Path, launcher: Path) -> subprocess.CompletedProcess:
    script = "set -e\n" + "\n".join(
        [f'project="{project.as_posix()}"', f'launcher="{launcher.as_posix()}"']
        + list(gen.FIRE_BODY_LINES)
    )
    return _run(sh, script, scrubbed_env(GODMODE_STATE_HOME=str(state)))


class HostJobLocalRedTests(unittest.TestCase):
    """One host per test method (bounded, readable failures): install into
    a fresh temp project, fire through the real launcher (exit 0, a deny
    observed), then fire the identical logic again through a corrupted
    copy of the launcher (non-zero) - the local proof of NS-8e's own
    acceptance line, "a broken launcher turns the job red"."""

    def _check_host(self, host: str) -> None:
        sh = _sh()
        if not sh:
            self.skipTest("no POSIX shell (bash/sh) on this machine")
        real_launcher = PLUGIN_ROOT / "hooks" / "run-hook.sh"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            state = base / "state"
            project.mkdir()
            state.mkdir()

            installed = _install(sh, host, project)
            self.assertEqual(installed.returncode, 0,
                              f"{host} install step: {installed.stdout}\n{installed.stderr}")

            denied = _fire(sh, project, state, real_launcher)
            self.assertEqual(denied.returncode, 0,
                              f"{host} fire step (real launcher): "
                              f"{denied.stdout}\n{denied.stderr}")
            self.assertIn("ok", denied.stdout)

            corrupted = base / "corrupted-run-hook.sh"
            corrupted.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            broken = _fire(sh, project, state, corrupted)
            self.assertNotEqual(
                broken.returncode, 0,
                f"{host}: a corrupted launcher must turn this job red, "
                f"got exit 0: {broken.stdout}\n{broken.stderr}",
            )


def _make_host_test(host: str):
    def test(self: HostJobLocalRedTests) -> None:
        self._check_host(host)
    test.__name__ = f"test_install_and_fire_{host}"
    return test


for _host in gen._union_hosts():
    setattr(HostJobLocalRedTests, f"test_install_and_fire_{_host}", _make_host_test(_host))
del _host


if __name__ == "__main__":
    unittest.main()

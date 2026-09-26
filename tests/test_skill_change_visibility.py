"""Skill changes are visible by default and locked only by a declared boundary.

A project skill is ordinary work in every session. With nobody presumed
watching, each change - a hook Edit/Write, `skill forge`, `skill retire`,
`skill restore` - is recorded, reported once per session and skill, and
listed by `godmode status`. A skill the operator lists in
`.godmode-boundaries.json` is refused to every one of those writers, in
every session, unless the operator runs it with a verified password.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
for entry in (SCRIPTS, Path(__file__).parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

PASSWORD = "correct horse battery staple"
LINE = "skills/demo changed ({how}) in an unattended session - review the diff"
_HOST_ENV = None


def setUpModule() -> None:
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()


@contextlib.contextmanager
def _attended(flag: bool):
    with mock.patch.dict(os.environ, {"GODMODE_ATTENDED": "1" if flag else "0"}, clear=False):
        os.environ.pop("CI", None)
        yield


def _run(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, dict, str]:
    out, err = io.StringIO(), io.StringIO()
    stdin_ctx = (mock.patch.object(sys, "stdin", io.StringIO(stdin))
                 if stdin is not None else contextlib.nullcontext())
    with stdin_ctx, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {}), err.getvalue()


def _hook(project: Path, tool: str, tool_input: dict,
          extra_env: dict | None = None) -> tuple[str, str]:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, **(extra_env or {})})
    body = (done.stdout or "").strip()
    if not body:
        return "allow", ""
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return str(specific.get("permissionDecision") or "allow"), body


def _skill(project: Path, name: str = "demo") -> Path:
    evals = project / "skills" / name / "godmode-evals.json"
    evals.parent.mkdir(parents=True, exist_ok=True)
    evals.write_text('{"lifecycle": "active"}\n', encoding="utf-8")
    (evals.parent / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    return evals


def _lock(project: Path, glob: str = "skills/demo/**") -> None:
    (project / ".godmode-boundaries.json").write_text(
        json.dumps({"ui": {"declared": [glob]}}), encoding="utf-8")


def _forge_argv(archive, name: str = "demo") -> list[str]:
    cites = [f"seq:{archive.append('action', f'forge-success-{i}', {'gate': 'allow'})['sequence']}"
             for i in range(3)]
    return ["skill", "forge", "--name", name,
            "--purpose", "Calibrate the demo widget subsystem before shipping it",
            "--gap-evidence", "Observed the same manual calibration step done by hand three times",
            "--repeated-uses", "3",
            "--success-evidence", cites[0], "--success-evidence", cites[1],
            "--success-evidence", cites[2],
            "--positive", "calibrate the widget before shipping",
            "--positive", "run the widget calibration routine",
            "--negative", "order lunch for the team",
            "--negative", "schedule a meeting for tomorrow",
            "--assertion", "reports the calibration outcome"]


class UnattendedHookEditTests(unittest.TestCase):
    def test_an_unattended_skill_write_passes_and_reports_once(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("session", "open", {"status": "open"})
            target = _skill(project).parent / "SKILL.md"
            with _attended(False):
                first = _hook(project, "Write", {"file_path": str(target), "content": "# a\n"})
                second = _hook(project, "Edit", {"file_path": str(target),
                                                 "old_string": "# demo", "new_string": "# b"})
                code, status, _err = _run(project, "status")
        self.assertEqual(first[0], "allow", first)
        self.assertIn(LINE.format(how="write"), first[1])
        self.assertEqual(second[0], "allow", second)
        self.assertNotIn("unattended session", second[1])
        self.assertEqual(code, 0, status)
        self.assertEqual(status["skills_changed_unattended"],
                         [LINE.format(how="write, edit")])

    def test_an_attended_skill_edit_is_not_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _skill(project).parent / "SKILL.md"
            with _attended(True):
                decision, body = _hook(project, "Write", {"file_path": str(target),
                                                          "content": "# a\n"})
        self.assertEqual(decision, "allow", body)
        self.assertNotIn("unattended session", body)

    def test_a_boundary_listed_skill_is_refused_to_the_hook_in_every_session(self) -> None:
        for flag in (True, False):
            with self.subTest(attended=flag), isolated_project() as (project, _s, _a, archive):
                archive.initialize()
                target = _skill(project).parent / "SKILL.md"
                _lock(project)
                with _attended(flag):
                    decision, body = _hook(project, "Write", {"file_path": str(target),
                                                              "content": "# a\n"})
                self.assertEqual(decision, "deny", body)


class UnattendedCliTests(unittest.TestCase):
    def test_retire_and_restore_pass_unattended_and_report_once(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            evals = _skill(project)
            with _attended(False):
                code, retired, err = _run(project, "skill", "retire", "--name", "demo",
                                          "--reason", "stale")
                self.assertEqual(code, 0, retired)
                code, restored, err_2 = _run(project, "skill", "restore",
                                             "--seq", str(retired["sequence"]))
                self.assertEqual(code, 0, restored)
                _code, status, _err = _run(project, "status")
            lifecycle = json.loads(evals.read_text(encoding="utf-8"))["lifecycle"]
        self.assertEqual(retired["unattended"], LINE.format(how="retire"))
        self.assertIn(LINE.format(how="retire"), err)
        self.assertNotIn("unattended", restored)
        self.assertNotIn("unattended session", err_2)
        self.assertEqual(lifecycle, "active")
        self.assertEqual(status["skills_changed_unattended"],
                         [LINE.format(how="retire, restore")])

    def test_forge_passes_unattended_and_reports(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with _attended(False):
                code, payload, err = _run(project, *_forge_argv(archive))
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["unattended"], LINE.format(how="forge"))
        self.assertIn(LINE.format(how="forge"), err)

    def test_attended_cli_changes_are_not_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _skill(project)
            with _attended(True):
                code, retired, _err = _run(project, "skill", "retire", "--name", "demo",
                                           "--reason", "stale")
                _code, status, _err = _run(project, "status")
        self.assertEqual(code, 0, retired)
        self.assertNotIn("unattended", retired)
        self.assertNotIn("skills_changed_unattended", status)


class LongArchiveTests(unittest.TestCase):
    def test_a_change_older_than_five_hundred_records_is_still_seen(self) -> None:
        from godmode_runtime.godmode_skillchange import (
            SUBJECT, record_unattended_change, unattended_changes)
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            first = record_unattended_change(archive, "S-early", "demo", "edit")
            for index in range(510):
                archive.append("action", SUBJECT,
                               {"session": "S-other", "skill": f"s{index}", "how": "edit"})
            again = record_unattended_change(archive, "S-early", "demo", "retire")
            rows = unattended_changes(archive, "S-early")
        self.assertIsNotNone(first)
        self.assertIsNone(again, "the skill already changed in this session")
        self.assertEqual([(row["skill"], row["how"]) for row in rows],
                         [("demo", ["edit", "retire"])])


class BoundaryLockTests(unittest.TestCase):
    def _retired(self, project: Path) -> int:
        """A retirement record made before the lock was declared."""
        with _attended(True):
            code, retired, _err = _run(project, "skill", "retire", "--name", "demo",
                                       "--reason", "stale")
        self.assertEqual(code, 0, retired)
        return int(retired["sequence"])

    def test_every_cli_writer_is_refused_in_every_session(self) -> None:
        for flag in (True, False):
            with self.subTest(attended=flag), isolated_project() as (project, _s, _a, archive):
                archive.initialize()
                evals = _skill(project)
                seq = self._retired(project)
                _lock(project, "skills/**")
                before = evals.read_text(encoding="utf-8")
                with _attended(flag):
                    retire = _run(project, "skill", "retire", "--name", "demo", "--reason", "x")
                    restore = _run(project, "skill", "restore", "--seq", str(seq))
                    forge = _run(project, *_forge_argv(archive, "fresh"))
                for code, payload, err in (retire, restore, forge):
                    self.assertNotEqual(code, 0, payload)
                    self.assertIn("declared design surface", json.dumps(payload) + err)
                self.assertEqual(evals.read_text(encoding="utf-8"), before)
                self.assertFalse((project / "skills" / "fresh").exists())

    def test_an_unlisted_skill_is_not_locked_by_anothers_boundary(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _skill(project, "other")
            _lock(project, "skills/demo/**")
            with _attended(False):
                code, payload, _err = _run(project, "skill", "retire", "--name", "other",
                                           "--reason", "stale")
        self.assertEqual(code, 0, payload)

    def test_the_operators_verified_password_moves_the_lock(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            _skill(project)
            _lock(project)
            with _attended(True):
                wrong = _run(project, "skill", "retire", "--name", "demo", "--reason", "x",
                             "--as-operator", "--password-stdin", stdin="not it\n")
                right = _run(project, "skill", "retire", "--name", "demo", "--reason", "x",
                             "--as-operator", "--password-stdin", stdin=PASSWORD + "\n")
        self.assertNotEqual(wrong[0], 0, wrong[1])
        self.assertEqual(right[0], 0, right[1])
        self.assertEqual(right[1]["lifecycle"], "deprecated")


_REMEDY = re.compile(r'`! "(?P<launcher>[^"]+)" (?P<command>authorize stage --operation "[^"]+")`')


def _stage_as_printed(test: unittest.TestCase, project: Path, refusal: str) -> str:
    """Run the staging command a refusal names, exactly as printed, with the
    password typed on stdin the way the other authorize tests supply it."""
    match = _REMEDY.search(refusal)
    test.assertIsNotNone(match, refusal)
    test.assertTrue(Path(match["launcher"]).is_file(), match["launcher"])
    code, staged, err = _run(project, *shlex.split(match["command"]), "--password-stdin",
                             stdin=PASSWORD + "\n")
    test.assertEqual(code, 0, (staged, err))
    test.assertTrue(staged["staged"], staged)
    return staged["operation"]


class StagedApprovalTests(unittest.TestCase):
    """The password-staged approval each boundary refusal names unlocks the
    locked skill for one change - the hook's Edit/Write and the skill
    commands alike - and is spent by it."""

    def test_the_hooks_remedy_stages_an_edit_that_then_passes_once(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            target = _skill(project).parent / "SKILL.md"
            _lock(project)
            write = {"file_path": str(target), "content": "# a\n"}
            with _attended(True):
                refused = _hook(project, "Write", write)
                self.assertEqual(refused[0], "deny", refused)
                reason = json.loads(refused[1])["hookSpecificOutput"]["permissionDecisionReason"]
                operation = _stage_as_printed(self, project, reason)
                allowed = _hook(project, "Write", write)
                spent = _hook(project, "Edit", {"file_path": str(target),
                                                "old_string": "# demo", "new_string": "# b"})
        self.assertEqual(operation, "edit file skills/demo/SKILL.md")
        self.assertEqual(allowed[0], "allow", allowed)
        self.assertEqual(spent[0], "deny", spent)

    def test_the_skill_commands_remedy_stages_a_retire_that_then_passes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            evals = _skill(project)
            _lock(project)
            with _attended(False):
                code, refused, err = _run(project, "skill", "retire", "--name", "demo",
                                          "--reason", "x")
                self.assertNotEqual(code, 0, refused)
                operation = _stage_as_printed(self, project, json.loads(err)["message"])
                code, retired, err = _run(project, "skill", "retire", "--name", "demo",
                                          "--reason", "x")
                again = _run(project, "skill", "restore", "--seq", str(retired.get("sequence")))
            lifecycle = json.loads(evals.read_text(encoding="utf-8"))["lifecycle"]
        self.assertEqual(operation, "retire skill demo")
        self.assertEqual(code, 0, (retired, err))
        self.assertEqual(lifecycle, "deprecated")
        self.assertNotEqual(again[0], 0, again[1])

    def test_an_edit_approval_is_not_spent_by_a_whole_skill_command(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            evals = _skill(project)
            _lock(project)
            code, staged, err = _run(project, "authorize", "stage", "--operation",
                                     "edit file skills/demo/godmode-evals.json", "--password-stdin",
                                     stdin=PASSWORD + "\n")
            self.assertEqual(code, 0, (staged, err))
            with _attended(False):
                code, retired, err = _run(project, "skill", "retire", "--name", "demo",
                                          "--reason", "x")
            lifecycle = json.loads(evals.read_text(encoding="utf-8")).get("lifecycle")
        self.assertNotEqual(code, 0, retired)
        self.assertIn('retire skill demo', json.loads(err)["message"])
        self.assertNotEqual(lifecycle, "deprecated")


    def test_a_later_refusal_leaves_the_staged_approval_unspent(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            target = _skill(project).parent / "SKILL.md"
            target.write_text("# frozen title\n<!-- GODMODE-EDITABLE-START -->\nbody\n"
                              "<!-- GODMODE-EDITABLE-END -->\n", encoding="utf-8")
            _lock(project)
            code, staged, err = _run(project, "authorize", "stage", "--operation",
                                     "edit file skills/demo/SKILL.md", "--password-stdin",
                                     stdin=PASSWORD + "\n")
            self.assertEqual(code, 0, (staged, err))
            with _attended(True):
                frozen = _hook(project, "Edit", {"file_path": str(target),
                                                 "old_string": "# frozen title",
                                                 "new_string": "# new title"})
                allowed = _hook(project, "Edit", {"file_path": str(target),
                                                  "old_string": "body", "new_string": "text"})
                spent = _hook(project, "Edit", {"file_path": str(target),
                                                "old_string": "body", "new_string": "text"})
        self.assertNotEqual(frozen[0], "allow", frozen)
        self.assertIn("editable region", frozen[1])
        self.assertEqual(allowed[0], "allow", allowed)
        self.assertEqual(spent[0], "deny", spent)

    def _stage(self, project: Path, operation: str) -> None:
        code, staged, err = _run(project, "authorize", "stage", "--operation", operation,
                                 "--password-stdin", stdin=PASSWORD + "\n")
        self.assertEqual(code, 0, (staged, err))

    def test_a_declared_tool_gate_leaves_the_staged_approval_unspent(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            target = _skill(project).parent / "SKILL.md"
            _lock(project)
            self._stage(project, "edit file skills/demo/SKILL.md")
            policy = project / ".godmode-authorization-policy.json"
            policy.write_text(json.dumps({"tool_gates": {"Write": "deny"}}), encoding="utf-8")
            write = {"file_path": str(target), "content": "# a\n"}
            with _attended(True):
                gated = _hook(project, "Write", write)
                policy.unlink()
                allowed = _hook(project, "Write", write)
        self.assertNotEqual(gated[0], "allow", gated)
        self.assertIn("declared tool gate", gated[1])
        self.assertEqual(allowed[0], "allow", allowed)

    def test_a_patch_with_one_unspendable_approval_spends_none(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            first = _skill(project).parent / "SKILL.md"
            second = first.parent / "notes.md"
            second.write_text("notes\n", encoding="utf-8")
            _lock(project)
            self._stage(project, "edit file skills/demo/SKILL.md")
            self._stage(project, "edit file skills/demo/notes.md")
            # The second approval is staged but can no longer be spent: its
            # signature no longer matches.
            store = json.loads(broker.path.read_text(encoding="utf-8"))
            token = store["staged"][-1]["token"]
            store["staged"][-1]["token"] = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
            broker.path.write_text(json.dumps(store), encoding="utf-8")
            patch = (f"*** Begin Patch\n*** Update File: {first}\n@@\n-# demo\n+# a\n"
                     f"*** Update File: {second}\n@@\n-notes\n+more\n*** End Patch\n")
            codex = {"GODMODE_HOST": "codex"}
            with _attended(True):
                refused = _hook(project, "apply_patch", {"input": patch}, codex)
                alone = _hook(project, "Edit", {"file_path": str(first),
                                                "old_string": "# demo", "new_string": "# a"})
        self.assertNotEqual(refused[0], "allow", refused)
        self.assertEqual(alone[0], "allow", alone)

if __name__ == "__main__":
    unittest.main()

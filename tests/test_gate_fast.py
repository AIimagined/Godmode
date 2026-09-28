"""The fast pre-tool gate: one table lookup, allow or escalate, never a guess.

`fast_verdict` is checked here against the same corpus `test_gate_corpus.py`
built from real denials, plus its own targeted red/green pairs. The corpus
check is deliberately ONE-DIRECTIONAL: it asserts fast-allow implies
full-allow, and never the converse. A command the fast gate escalates may
still be one the full sentinel would allow - that just means the full hook
paid its own cost to say so, which is always safe. A command the fast gate
allows that the full sentinel would ask or refuse about is the one failure
mode this module exists to make impossible, and that is the one direction
this test enforces. Written this way, the test is robust to `godmode_sentinel`
changing under it (a concurrent task on this same plan is doing exactly
that): a segment the sentinel newly starts recognising only ever makes the
corpus's `expected`/`fullv` pair agree *more* often, never less.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import re
import shutil
import subprocess
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = PLUGIN_ROOT / "hooks"
FAST_GATE = HOOKS_DIR / "godmode_gate_fast.py"
TABLE_PATH = HOOKS_DIR / "gate_table.json"

_spec = importlib.util.spec_from_file_location("godmode_gate_fast", FAST_GATE)
fast = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fast)

SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tests.test_gate_corpus import corpus_entries, _decision  # noqa: E402
from tests._gate_mode_isolation import park_local_policy, restore_local_policy  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    _raw_segments, _executable_text, _FIND_MUTATION, _contained, classify_action,
)
from tests._host_env import scrubbed_env  # noqa: E402


def setUpModule() -> None:
    # The end-to-end smokes below pipe through the real hook against THIS
    # repo, so a local observe-mode declaration replaces their decision
    # envelope with an advisory - see _gate_mode_isolation's docstring.
    park_local_policy()


def tearDownModule() -> None:
    restore_local_policy()


def payload(command: str, tool: str = "Bash") -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
    }


def _governed_project() -> Path:
    """A fresh git checkout with its own initialized archive, so a
    subprocess driven against it is governed no matter whether THIS repo's
    own checkout has ever run `godmode init` - see `UngovernedProject`
    below for what an ungoverned checkout does instead (silent allow, no
    archive touched). Some subprocess smokes below used to run with `cwd`
    on this checkout, so on a fresh, uninitialized install they fell
    through that same silent-allow path, and every assertion expecting a
    real escalation or denial found nothing on stdout instead. The caller
    owns cleanup (`shutil.rmtree`)."""
    project = Path(tempfile.mkdtemp(prefix="godmode-gate-fast-project-"))
    for command in (["init", "-q"], ["config", "user.email", "gate-fast@example.invalid"],
                    ["config", "user.name", "gate-fast"]):
        subprocess.run(["git", *command], cwd=project, check=True, capture_output=True)
    from godmode_runtime.godmode_anchor import resolve_anchor
    from godmode_runtime.godmode_chronicle import Chronicle
    Chronicle(resolve_anchor(project)).initialize()
    return project


def _table() -> dict[str, Any]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


TABLE = _table()


class TableShape(unittest.TestCase):
    """The provisional fixture itself: schema-shaped, freshness-agnostic
    (nothing here pins `generated_from` - Task 5 replaces this file's
    contents, not its shape, and this suite must survive that swap)."""

    def test_required_keys_present(self) -> None:
        for key in ("version", "generated_from", "floor", "read_heads",
                    "mutation_heads", "db_clients", "git_ask", "git_refuse",
                    "find_mutation_flags", "flag_denylist",
                    "output_flags_by_head"):
            self.assertIn(key, TABLE)

    def test_output_flags_by_head_matches_the_sentinels_own_table(self) -> None:
        """Final review Critical finding C2's fix: `output_flags_by_head` is
        an exported copy of `_OUTPUT_FLAGS_BY_HEAD`, not a retyped one - pin
        it against the real dict directly so the two can never drift."""
        from godmode_runtime.godmode_sentinel import _OUTPUT_FLAGS_BY_HEAD
        expected = {head: set(flags) for head, flags in _OUTPUT_FLAGS_BY_HEAD.items()}
        actual = {head: set(flags) for head, flags in TABLE["output_flags_by_head"].items()}
        self.assertEqual(actual, expected)

    def test_floor_is_conservative_read_only_in_full_sentinel(self) -> None:
        """Every literal floor phrase, run bare, is R0 in the full sentinel
        today. This is the parity property Task 5's own table build will
        re-check for real; this fixture is built to already satisfy it."""
        for phrase in TABLE["floor"]["claude-code"]:
            with self.subTest(phrase=phrase):
                verdict = classify_action(phrase, project_root=PLUGIN_ROOT)
                self.assertEqual(verdict["tier"], "R0", phrase)

    def test_read_heads_are_r0_in_full_sentinel_bare(self) -> None:
        for head in TABLE["read_heads"]:
            with self.subTest(head=head):
                verdict = classify_action(f"{head} somefile", project_root=PLUGIN_ROOT)
                self.assertEqual(verdict["tier"], "R0", head)

    def test_find_mutation_flags_match_the_sentinels_own_set(self) -> None:
        """Review round 1, Critical finding 1: the fast gate's find-flag
        check only covered `-exec`/`-delete`, missing `-execdir`/`-ok`/
        `-okdir` from `_FIND_MUTATION` (godmode_sentinel.py). Now
        table-driven; this is the drift guard tying the table's flag set to
        the regex's own alternation, parsed directly from the compiled
        pattern rather than retyped by hand - so a sixth flag added to
        `_FIND_MUTATION` later shows up here as a mismatch instead of
        silently reopening the gap.
        """
        match = re.search(r"-\(\?:([^)]+)\)", _FIND_MUTATION.pattern)
        self.assertIsNotNone(match, _FIND_MUTATION.pattern)
        sentinel_flags = {f"-{name}" for name in match.group(1).split("|")}
        self.assertEqual(set(TABLE["find_mutation_flags"]), sentinel_flags)

    def test_flag_denylist_entries_name_real_floor_phrases(self) -> None:
        floor_phrases = set(TABLE["floor"]["claude-code"])
        for phrase in TABLE["flag_denylist"]:
            self.assertIn(phrase, floor_phrases, phrase)

    def test_denylisted_git_output_flags_are_gated_in_full_sentinel(self) -> None:
        """The full sentinel closed its `--output=<file>` gap (review Critical
        finding 2, fixed in the sentinel lane). The fast gate's denylist is
        now redundant-but-still-correct defense in depth: fast escalates,
        full gates the write. This pins the full sentinel's side so the pair
        can never silently reopen."""
        for phrase, flags in TABLE["flag_denylist"].items():
            for flag in flags:
                if not flag.startswith("--"):
                    # Short flags (-o) sit in the denylist as fast-gate
                    # caution only: git rejects them on log/diff/show, so
                    # the full sentinel owes them nothing.
                    continue
                command = f"{phrase} {flag}=/tmp/x"
                with self.subTest(command=command):
                    verdict = classify_action(command, project_root=PLUGIN_ROOT)
                    self.assertNotEqual(verdict["tier"], "R0", command)


class Equivalence(unittest.TestCase):
    def test_fast_allow_iff_full_sentinel_allows(self) -> None:
        for entry in corpus_entries():
            tool = entry.get("tool") or "Bash"
            fastv = fast.fast_verdict(payload(entry["operation"], tool), TABLE)
            fullv = _decision(entry["operation"], tool)
            if fastv == "allow":
                self.assertEqual(fullv, "allow", entry["operation"][:80])


class SegmentSplitEquivalence(unittest.TestCase):
    """Drift guard for the local duplicate. `_blanked_segments` splits at the
    same boundaries as `godmode_sentinel._raw_segments` for every command
    this suite exercises - the two must never learn to disagree about where
    a segment ends, even though one blanks quotes and the other keeps them."""

    def _samples(self) -> list[str]:
        return [entry["operation"] for entry in corpus_entries()] + [
            "git status && ls -la", "echo hi | grep x", "a; b; c",
            'echo "a; b" && echo c', "ls\r\ncat file.txt",
        ]

    def test_segment_count_matches_the_source_of_truth(self) -> None:
        for command in self._samples():
            with self.subTest(command=command[:60]):
                local = fast._blanked_segments(command)
                source = _raw_segments(command)
                self.assertEqual(len(local), len(source), command[:80])

    def test_segment_content_matches_the_source_of_truth(self) -> None:
        """Review round 1, Minor finding 1: the original guard only checked
        segment *count*. `_executable_text`, applied per-segment to
        `_raw_segments`'s raw (quote-intact) output, blanks quotes the same
        way `_blanked_segments` does in one fused pass - a segment boundary
        only ever falls where the quote-tracking state is already `None`
        (that's what makes it a boundary), so blanking each raw segment
        independently is provably equivalent to blanking during the single
        fused pass, and the two lists must now match element-for-element,
        not just in length.
        """
        for command in self._samples():
            with self.subTest(command=command[:60]):
                local = fast._blanked_segments(command)
                source = [_executable_text(segment).strip()
                          for segment in _raw_segments(command)]
                self.assertEqual(local, source, command[:80])


class NoArchiveIO(unittest.TestCase):
    def test_allow_path_opens_no_files(self) -> None:
        opened: list[Any] = []
        real_open = builtins.open

        def spy(*args: Any, **kwargs: Any) -> Any:
            opened.append(args[0] if args else kwargs.get("file"))
            return real_open(*args, **kwargs)

        builtins.open = spy
        try:
            verdict = fast.fast_verdict(payload("git status"), TABLE)
        finally:
            builtins.open = real_open
        self.assertEqual(verdict, "allow")
        self.assertEqual(opened, [])


class UngovernedProject(unittest.TestCase):
    """Field walk 2026-09-05: on a project nobody ran `godmode init` in,
    every mutating tool call still escalated to the full hook, which loaded
    the runtime and spawned git only to print the not-initialized notice
    (380-520 ms, slower than a governed project). A plain git checkout
    with no archive under its metadata dir has nothing to gate: the fast
    gate answers that itself, with stats only, and stays silent."""

    def _git_dir(self, root: Path) -> Path:
        git = root / ".git"
        git.mkdir()
        (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        return git

    def test_a_git_checkout_without_an_archive_is_ungoverned(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git_dir(root)
            (root / "src").mkdir()
            self.assertTrue(fast.ungoverned_project(root / "src"))

    def test_an_archive_under_the_metadata_dir_means_governed(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (self._git_dir(root) / "godmode-state").mkdir()
            self.assertFalse(fast.ungoverned_project(root))

    def test_a_git_file_that_points_nowhere_escalates(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
            self.assertFalse(fast.ungoverned_project(root), ".git file pointing nowhere")

    def test_a_non_git_directory_is_ungoverned_until_its_archive_exists(self) -> None:
        """Field report 2026-09-23: a directory that is not a repository
        escalated every mutating call into a second interpreter. Its
        archive lives in the application home under the salted key
        `resolve_anchor` derives; only that directory's existence counts."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project, home = base / "project", base / "state"
            project.mkdir()
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(home)}):
                self.assertTrue(fast.ungoverned_project(project), "no application home yet")
                scripts = str(HOOKS_DIR.parent / "scripts")
                if scripts not in sys.path:
                    sys.path.insert(0, scripts)
                from godmode_runtime.godmode_anchor import resolve_anchor
                Path(resolve_anchor(project).archive_root).mkdir(parents=True)
                self.assertFalse(fast.ungoverned_project(project), "archive present")

    def test_a_linked_worktree_follows_its_common_dir(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            main = base / "main"
            main.mkdir()
            git = self._git_dir(main)
            linked = base / "linked"
            linked.mkdir()
            admin = git / "worktrees" / "linked"
            admin.mkdir(parents=True)
            (admin / "HEAD").write_text("ref: refs/heads/other\n", encoding="utf-8")
            (admin / "commondir").write_text("../..\n", encoding="utf-8")
            (linked / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}):
                self.assertTrue(fast.ungoverned_project(linked))
                (git / "godmode-state").mkdir()
                self.assertFalse(fast.ungoverned_project(linked))

    def test_the_gate_stays_silent_and_skips_the_full_hook_on_an_ungoverned_project(self) -> None:
        # D-3: "skips the full hook" used to be inferred from elapsed time
        # (< 2.0s) - flaky under load (a field gate saw 2.47s on an
        # otherwise-correct run). The state that bound stood in for is
        # asserted directly instead: `FULL_HOOK` is swapped for a STUB
        # that only touches a marker file, run through a throwaway copy of
        # the fast gate script (the files it imports: `godmode_stdin.py`
        # and `godmode_initstate.py`, plus its own `gate_table.json`); the marker's
        # absence afterward IS "the full hook never ran", not a proxy for it.
        import os, shutil, tempfile
        with tempfile.TemporaryDirectory() as temporary, \
             tempfile.TemporaryDirectory(prefix="godmode-stub-hook-") as stub_dir:
            root = Path(temporary)
            self._git_dir(root)
            stub = Path(stub_dir)
            for name in ("godmode_gate_fast.py", "godmode_stdin.py", "godmode_initstate.py",
                         "gate_table.json"):
                shutil.copy2(HOOKS_DIR / name, stub / name)
            marker = stub / "full-hook-ran.marker"
            (stub / "godmode_session_hook.py").write_text(
                "import pathlib, sys\n"
                f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )
            def run(command: str) -> subprocess.CompletedProcess[bytes]:
                body = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                   "tool_input": {"command": command},
                                   "cwd": str(root)})
                return subprocess.run(
                    [sys.executable, str(stub / "godmode_gate_fast.py")], input=body.encode(),
                    capture_output=True, cwd=str(root), timeout=60,
                    env=scrubbed_env(GODMODE_STATE_HOME=str(root / "state")))

            # Ordinary mutating work: silent, and the stub copy's missing
            # runtime is never needed.
            done = run("npm install")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), b"", done.stdout[:300])
            # A harm-class command whose classifier cannot be reached (the
            # stub has no runtime beside it) fails closed, still without
            # the full hook.
            done = run("git push --force")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn(b'"deny"', done.stdout)
            self.assertFalse(marker.exists(), "the full hook was spawned")


class EditClearance(unittest.TestCase):
    """R11: an ordinary re-edit of a file the full hook already cleared, in
    the same session, is decided by the fast gate without the full hook -
    and every check that can refuse an edit still fires the moment its
    trigger exists. Driven through the real gate and post-edit hook."""

    SESSION = "s-edit"

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="godmode-edit-clearance-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.project = _governed_project()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        (self.project / "app.py").write_text("def parse(text):\n    return text\n",
                                             encoding="utf-8")
        for command in (["add", "-A"], ["commit", "-qm", "seed"]):
            subprocess.run(["git", *command], cwd=self.project, check=True,
                           capture_output=True)
        self.home = self.base / "state"
        self.target = str(self.project / "app.py")

    def _payload(self, target: str | None = None, tool: str = "Edit",
                 session: str | None = None, **tool_input: Any) -> dict[str, Any]:
        tool_input = tool_input or {"old_string": "return text", "new_string": "return text"}
        return {"hook_event_name": "PreToolUse", "tool_name": tool,
                "session_id": session or self.SESSION, "cwd": str(self.project),
                "tool_input": {"file_path": target or self.target, **tool_input}}

    def _hook(self, script: str, body: dict[str, Any], *args: str,
              **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-I", "-B", str(HOOKS_DIR / script), *args],
            input=json.dumps(body).encode(), capture_output=True, cwd=str(self.project),
            timeout=120, env=scrubbed_env(GODMODE_STATE_HOME=str(self.home), **env))

    def _gate(self, body: dict[str, Any], **env: str) -> str:
        done = self._hook("godmode_gate_fast.py", body, **env)
        text = done.stdout.decode("utf-8").strip()
        if done.returncode == 2:
            return "deny"
        if not text:
            return "allow"
        decoded = json.loads(text)
        specific = decoded.get("hookSpecificOutput") or {}
        return specific.get("permissionDecision") or decoded.get("decision") or "allow"

    def _edit(self, body: dict[str, Any] | None = None, **env: str) -> str:
        body = body or self._payload()
        decision = self._gate(body, **env)
        if decision == "allow":
            self._hook("godmode_post_edit.py", {**body, "hook_event_name": "PostToolUse"}, **env)
        return decision

    def _cleared(self, body: dict[str, Any] | None = None) -> bool:
        return fast.edit_cleared(body or self._payload(), self.project, TABLE)

    def _clear(self) -> None:
        """Two ordinary edits: the first enrolls the file in the change,
        the second is allowed for a standing reason and cleared."""
        self.assertEqual(self._edit(), "allow")
        self.assertFalse(self._cleared(), "a first edit must not be cleared")
        self.assertEqual(self._edit(), "allow")
        self.assertTrue(self._cleared(), "the second silent allow should clear the file")

    def _archive(self) -> Any:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        return Chronicle(resolve_anchor(self.project))

    def test_a_cleared_re_edit_needs_no_full_hook_and_the_full_hook_agrees(self) -> None:
        self._clear()
        # Parity: the full hook, asked directly, allows the same call silently.
        full = self._hook("godmode_session_hook.py", self._payload(), "pre-action")
        self.assertEqual(full.returncode, 0, full.stderr[-600:])
        self.assertEqual(full.stdout.strip(), b"")
        # The re-edit is decided without starting the full hook at all.
        spawned = self.base / "spawned"
        stub = self.base / "stub_hook.py"
        stub.write_text(f"open({str(spawned)!r}, 'w').close()\n", encoding="utf-8")
        code = ("import runpy,sys;sys.argv=[sys.argv[1]];import importlib.util as u;"
                "s=u.spec_from_file_location('g',sys.argv[0]);m=u.module_from_spec(s);"
                "s.loader.exec_module(m);m.FULL_HOOK=__import__('pathlib').Path(" + repr(str(stub))
                + ");raise SystemExit(m.main())")
        done = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(FAST_GATE)],
                              input=json.dumps(self._payload()).encode(), capture_output=True,
                              timeout=60, env=scrubbed_env(GODMODE_STATE_HOME=str(self.home)))
        self.assertEqual((done.returncode, done.stdout.strip()), (0, b""), done.stderr[-600:])
        self.assertFalse(spawned.exists(), "the full hook was started for a cleared re-edit")

    def test_the_clearance_survives_an_operator_prompt(self) -> None:
        self._clear()
        prompt = {"hook_event_name": "UserPromptSubmit", "prompt": "keep going on the parser",
                  "session_id": self.SESSION, "cwd": str(self.project)}
        done = self._hook("godmode_session_hook.py", prompt, "user-prompt")
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        kinds = [record["kind"] for record in self._archive().read_events()]
        self.assertIn("request", kinds)
        self.assertTrue(self._cleared())

    def test_another_session_a_new_file_or_a_relative_path_escalates(self) -> None:
        self._clear()
        self.assertFalse(self._cleared(self._payload(session="other")))
        (self.project / "b.py").write_text("x = 1\n", encoding="utf-8")
        self.assertFalse(self._cleared(self._payload(str(self.project / "b.py"))))
        self.assertFalse(self._cleared(self._payload("app.py")))
        self.assertFalse(self._cleared(self._payload(tool="apply_patch")))

    def test_a_protected_path_is_never_cleared_even_when_listed(self) -> None:
        self._clear()
        common = self.project / ".git"
        clearance = json.loads((common / fast.CLEARANCE_NAME).read_text(encoding="utf-8"))
        for relative in (".env", ".godmode-authorization-policy.json", "skills/x/SKILL.md",
                         ".github/workflows/ci.yml", "CODEFREEZE"):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
            clearance["targets"].append(relative)
        (common / fast.CLEARANCE_NAME).write_text(json.dumps(clearance), encoding="utf-8")
        for relative in (".env", ".godmode-authorization-policy.json", "skills/x/SKILL.md",
                         ".github/workflows/ci.yml", "CODEFREEZE"):
            with self.subTest(path=relative):
                self.assertFalse(self._cleared(self._payload(str(self.project / relative))))
        # Secret-shaped and skill targets reach the full hook: it still stops
        # the secret, and it sees every skill edit so an unattended one is
        # reported. The placeholder policy and freeze files would otherwise
        # decide first.
        for relative in (".godmode-authorization-policy.json", "CODEFREEZE"):
            (self.project / relative).unlink()
        self.assertNotEqual(self._gate(self._payload(str(self.project / ".env"))), "allow")
        skill_edit = self._hook("godmode_gate_fast.py",
                                self._payload(str(self.project / "skills/x/SKILL.md")),
                                GODMODE_ATTENDED="0")
        self.assertIn("skills/x changed (", skill_edit.stdout.decode("utf-8"))

    def test_the_design_boundary_still_denies(self) -> None:
        self._clear()
        (self.project / ".godmode-boundaries.json").write_text(
            json.dumps({"ui": {"declared": ["app.py"]}}), encoding="utf-8")
        self.assertFalse(self._cleared())
        self.assertEqual(self._gate(self._payload()), "deny")

    def test_the_scope_fence_still_stops_it(self) -> None:
        self._clear()
        from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start
        archive = self._archive()
        specify(archive, "S-1", "narrow fix", {"objective": "o", "outcome": "u",
                                               "acceptance": "a", "non_goals": "n"})
        contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
        contract.update({"accept": "cmd:x", "editable": "docs/**"})
        start(archive, "S-1", "narrow fix", contract)
        approve(archive, "S-1")
        self.assertFalse(self._cleared())
        self.assertIn(self._gate(self._payload()), ("ask", "deny"))

    def test_a_frozen_region_still_denies(self) -> None:
        self._clear()
        (self.project / "app.py").write_text(
            "def parse(text):\n    return text\n# GODMODE-EDITABLE-START\nx = 1\n"
            "# GODMODE-EDITABLE-END\n", encoding="utf-8")
        self.assertFalse(self._cleared())
        self.assertIn(self._gate(self._payload()), ("ask", "deny"))

    def test_a_declared_tool_gate_a_stop_flag_and_a_ceiling_still_stop_it(self) -> None:
        for name, content in ((".godmode-authorization-policy.json",
                               json.dumps({"tool_gates": {"Edit": "deny"}})),
                              (".godmode-stop", "stop\n"),
                              (".godmode-ceilings.json", json.dumps({"tool_calls": 1}))):
            with self.subTest(setting=name):
                self.setUp()
                # The stop flag is read at a session's boundary.
                self._archive().append("session", "session-open", {}, evidence=[])
                self._clear()
                (self.project / name).write_text(content, encoding="utf-8")
                self.assertFalse(self._cleared())
                self.assertEqual(self._gate(self._payload()), "deny")

    def test_plan_first_still_asks_for_a_new_file(self) -> None:
        self._clear()
        big = "\n".join(f"line_{i} = {i}" for i in range(80)) + "\n"
        body = self._payload(str(self.project / "new_module.py"), tool="Write", content=big)
        self.assertFalse(self._cleared(body))
        self.assertIn(self._gate(body), ("ask", "deny"))

    def test_a_pinned_evaluator_still_denies(self) -> None:
        self._clear()
        from godmode_runtime.godmode_sentinel import pin_evaluator
        pin_evaluator(self._archive(), self.project, self.target)
        self.assertFalse(self._cleared())
        self.assertEqual(self._gate(self._payload()), "deny")

    def test_any_record_an_edit_check_reads_voids_the_clearance(self) -> None:
        for kind, subject, data in (("attestation", "check:retest:tests.test_app",
                                     {"status": "blocked"}),
                                    ("plan", "plan:x", {"state": "approved"}),
                                    ("checkpoint", "handover", {"status": "green"}),
                                    ("decision", "sources-exemption:README.md", {})):
            with self.subTest(kind=kind):
                self.setUp()
                self._clear()
                self._archive().append(kind, subject, data, evidence=[])
                self.assertFalse(self._cleared())

    def test_two_red_retests_stop_the_clearance_being_granted(self) -> None:
        archive = self._archive()
        for _ in range(2):
            archive.append("attestation", "check:retest:tests.test_app",
                           {"status": "blocked"}, evidence=[])
        self.assertEqual(self._edit(), "allow")
        self.assertEqual(self._edit(), "allow")
        self.assertFalse(self._cleared())

    def test_a_project_whose_archive_is_gone_is_not_cleared(self) -> None:
        self._clear()
        shutil.rmtree(self.project / ".git" / "godmode-state")
        self.assertFalse(self._cleared())

    def test_a_host_that_hears_no_session_start_is_not_cleared(self) -> None:
        self._clear()
        from unittest import mock
        with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}):
            self.assertFalse(self._cleared())


def _uninitialized_repo(base: Path) -> Path:
    project = base / "project"
    project.mkdir()
    git = project / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    return project


class UninitializedGuard(unittest.TestCase):
    """An installed Godmode guards harm-class commands in a project nobody
    initialized: the host's own ask where it has one, a deny naming the
    remedy where it has none, and nothing for ordinary work. No archive is
    created and nothing is written into the working tree."""

    FORCE_PUSH = "git push --force"

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="godmode-uninit-guard-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.project = _uninitialized_repo(self.base)
        self.home = self.base / "state"

    def _run(self, command: str, tool: str = "Bash", cwd: Path | None = None,
             session: str = "s-1", event: str = "PreToolUse",
             **env: str) -> dict[str, Any] | None:
        cwd = cwd or self.project
        body = {"hook_event_name": event, "tool_name": tool, "session_id": session,
                "tool_input": {"command": command}, "cwd": str(cwd)}
        done = subprocess.run(
            [sys.executable, "-I", "-B", str(FAST_GATE)], input=json.dumps(body).encode(),
            capture_output=True, cwd=str(cwd), timeout=60,
            env=scrubbed_env(GODMODE_STATE_HOME=str(self.home), **env))
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        text = done.stdout.decode("utf-8").strip()
        return json.loads(text) if text else None

    def _decision(self, body: dict[str, Any] | None) -> str:
        if body is None:
            return "allow"
        specific = body.get("hookSpecificOutput") or {}
        return specific.get("permissionDecision") or body.get("decision") or "allow"

    def _grok(self, command: str, **kwargs: Any) -> dict[str, Any] | None:
        return self._run(command, tool="run_terminal_command", GROK_AGENT="1", **kwargs)

    def _no_ask(self, command: str, **kwargs: Any) -> dict[str, Any] | None:
        # A host whose hook dialect has no `ask` (Gemini's BeforeTool); Grok
        # gained `ask` and now takes the ask path like Claude.
        return self._run(command, tool="run_shell_command", event="BeforeTool", **kwargs)

    def _write_setting(self, value: str) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "godmode-settings.json").write_text(
            json.dumps({"uninitialized": value}), encoding="utf-8")

    def _assert_nothing_created(self) -> None:
        self.assertFalse((self.project / ".git" / "godmode-state").exists(), "archive created")
        self.assertFalse((self.home / "projects").exists(), "archive created")
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), [".git"])

    def test_a_force_push_asks_on_a_host_with_ask(self) -> None:
        body = self._run(self.FORCE_PUSH)
        self.assertEqual(self._decision(body), "ask")
        reason = body["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("godmode config set uninitialized off", reason)
        self.assertIn("godmode init", reason)
        self._assert_nothing_created()

    def test_a_force_push_is_denied_with_the_remedy_on_a_host_without_ask(self) -> None:
        # Grok reads `ask` now, so it gets the host prompt, not the deny.
        self.assertEqual(self._decision(self._grok(self.FORCE_PUSH, session="g")), "ask")
        body = self._no_ask(self.FORCE_PUSH)
        self.assertEqual(body["decision"], "deny")
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
        for remedy in ("godmode init", "password", "godmode config set uninitialized off"):
            self.assertIn(remedy, body["reason"])
        self._assert_nothing_created()

    def test_ordinary_work_is_silent_and_creates_nothing(self) -> None:
        for command in ("git status", "npm install", "python -m unittest", "rm -rf build",
                        "git commit -m x"):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command))
        self._assert_nothing_created()

    def test_a_delete_outside_the_project_asks_or_is_denied(self) -> None:
        for command in ("rm -rf ../other", "rm -rf /", "rm ~/notes.txt"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")
                self.assertEqual(self._decision(self._no_ask(command, session=command)), "deny")

    def test_a_compound_command_is_judged_by_its_worst_part(self) -> None:
        for command in ("echo x ; git push --force", "echo x && git push --force",
                        "ls | git push --force", "(cd . ; git push --force)"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")
                self.assertEqual(self._decision(self._no_ask(command, session=command)), "deny")

    def test_a_push_spelled_through_shell_quoting_asks(self) -> None:
        # ANSI-C and locale quoting leave no `push` word in the text; the
        # screen must still hand them to the classifier.
        for command in ("git \"pu\"$'sh' -f", "git pu$\"sh\" --force"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")

    def test_a_program_or_git_verb_built_at_run_time_asks(self) -> None:
        # The classifier cannot name the program (an expression or a
        # variable as the command word, a substitution as git's verb); on
        # a call that already named a harm-class word that is not cleared.
        for command, tool in (("& ('gi'+'t') push -f", "PowerShell"),
                              ("$g push --force", "Bash"),
                              ("git $(printf pu)sh -f", "Bash")):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command, tool=tool)), "ask")
        self.assertIsNone(self._run("echo $(date) && git status"))

    def test_a_push_spelled_through_a_variable_asks(self) -> None:
        for command in ("x=sh; git pu$x -f", "git pu$@sh -f", "git pu$*sh -f"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")

    def test_a_harm_class_word_completed_by_an_expansion_asks(self) -> None:
        # The expansion sits in the verb, a flag or the program itself, and
        # the classifier cannot read what runs; an empty `$@` leaves the
        # plain harm-class spelling.
        for command in ("g''it p${_}ush -f", "git reset --ha$@rd HEAD~3",
                        "gh rel$@ease create v1", "r$@m -rf /tmp/x", "npm pub$@lish",
                        "git pu`printf s`h -f", "git pu{s,}h -f", "git pu?h -f",
                        "git reset $x HEAD~3"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")
        # A variable standing for a whole ordinary argument stays ordinary.
        for command in ("echo $HOME", 'git commit -m "$msg"', "git add $f", "make $t",
                        "curl $url", "git log $REV", "LD=a$B make", "date +%Y%m%d"):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command))

    def test_releases_and_history_rewrites_ask(self) -> None:
        for command in ("npm publish", "gh release create v1", "git reset --hard HEAD~3",
                        "git branch -D topic", "git push origin v1.0"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")

    def test_machine_wide_off_is_silent(self) -> None:
        self._write_setting("off")
        self.assertIsNone(self._run(self.FORCE_PUSH))
        self.assertIsNone(self._grok(self.FORCE_PUSH))
        self.assertIsNone(self._no_ask(self.FORCE_PUSH))

    def test_repository_off_is_silent_in_that_repository_only(self) -> None:
        with (self.project / ".git" / "config").open("a", encoding="utf-8") as handle:
            handle.write("[godmode]\n\tuninitialized = off\n")
        other = self.base / "other"
        other.mkdir()
        (other / ".git").mkdir()
        (other / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        self.assertIsNone(self._run(self.FORCE_PUSH))
        self.assertEqual(self._decision(self._run(self.FORCE_PUSH, cwd=other)), "ask")

    def test_a_repository_guard_overrides_a_machine_off(self) -> None:
        self._write_setting("off")
        with (self.project / ".git" / "config").open("a", encoding="utf-8") as handle:
            handle.write("[GodMode]\n\tUninitialized = guard\n")
        self.assertEqual(self._decision(self._run(self.FORCE_PUSH)), "ask")

    def test_turning_the_guard_off_is_itself_asked_about(self) -> None:
        for command in ("godmode config set uninitialized off",
                        "git config godmode.uninitialized off",
                        "git config --local godmode.uninitialized off ; git push --force",
                        "godmode config set uninitialized off && git push --force",
                        "echo {} > ~/.godmode/godmode-settings.json"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")
                self.assertEqual(self._decision(self._no_ask(command, session=command)), "deny")

    def test_a_write_resolving_to_the_setting_is_asked_about_however_spelled(self) -> None:
        # The file a write lands in decides, not how its path is spelled:
        # `.`/`..`, a directory change earlier in the call (behind a flag,
        # or already made by the host shell: the call's own `cwd`), a glob.
        settings_glob = (self.home / "godmode-setting?.json").as_posix()
        write = r"printf '[\x67odmode]\n\tuninitialize\x64 = off\n' >> config"
        git_dir = self.project / ".git"
        for command, tool, cwd in (
                (r"printf '[\x67odmode]\n\tuninitialize\x64 = off\n' >> .git/./config",
                 "Bash", None),
                (f"cd .git && {write}", "Bash", None),
                ("echo x >> .gi?/conf*", "Bash", None),
                (f"echo {{}} > {settings_glob}", "Bash", None),
                (write, "Bash", git_dir),
                ("Add-Content config x", "PowerShell", git_dir),
                (f"cd -- .git && {write}", "Bash", None),
                (f"cd -P .git && {write}", "Bash", None),
                (f"cd -LP .git && {write}", "Bash", None),
                ("Set-Location -Path .git; Add-Content config x", "PowerShell", None),
                ("Set-Location -LiteralPath .git; Add-Content config x", "PowerShell", None),
                ("Set-Location -Path:.git; Add-Content config x", "PowerShell", None)):
            with self.subTest(command=command, cwd=cwd):
                self.assertEqual(self._decision(self._run(command, tool=tool, cwd=cwd)), "ask")
                self.assertEqual(self._decision(
                    self._no_ask(command, cwd=cwd, session=command)), "deny")
        for command in ("echo x > docs/config", "cd docs && echo x > notes",
                        "cd .git && cd .. && echo x >> config"):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command))

    def test_a_directory_change_behind_a_flag_still_moves_the_write(self) -> None:
        # The directory is the first word that is not a flag, in either shell.
        write = r"printf '[godmode]\n\tuninit%s = off\n' ialized >> config"
        for command, tool in ((f"cd -- .git && {write}", "Bash"),
                              (f"cd -P .git && {write}", "Bash"),
                              (f"cd -LP .git && {write}", "Bash"),
                              ("Set-Location -Path .git; Add-Content config x", "PowerShell"),
                              ("Set-Location -LiteralPath .git; Add-Content config x", "PowerShell"),
                              ("Set-Location -Path:.git; Add-Content config x", "PowerShell"),
                              ("Set-Location -ErrorAction Stop .git; Add-Content config x",
                               "PowerShell")):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command, tool=tool)), "ask")

    def test_a_write_is_judged_from_the_one_directory_the_shell_is_in(self) -> None:
        # One current directory, followed through `cd`, `cd -`, `pushd` and
        # `popd`: returning to the project root first stays allowed.
        for command, tool in (("cd .git && cd .. && echo x >> config", "Bash"),
                              ("pushd .git && popd && echo x >> config", "Bash"),
                              ("cd .git && cd - && echo x >> config", "Bash"),
                              ("Push-Location .git; Pop-Location; Add-Content config x",
                               "PowerShell")):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command, tool=tool))
        # A change that may not have happened, or that the text cannot
        # place, keeps the directory it would have left.
        for command in ("cd .git && echo x >> config",
                        "cd .git && cd - && cd - && echo x >> config",
                        "cd .git; false && cd ..; echo x >> config",
                        "cd .git || cd ..; echo x >> config",
                        "cd .git; cd missing; echo x >> config",
                        'cd .git; echo "x; cd .."; echo x >> config',
                        "cd .git # ; cd ..\necho x >> config",
                        "cd .git; cat <<EOF\ncd ..\nEOF\necho x >> config",
                        "cd .git; (cd ..); echo x >> config",
                        "cd .git; eval cd ..; echo x >> config",
                        "if true; then cd .git; fi; echo x >> config"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")

    def test_a_write_through_a_link_to_the_setting_asks(self) -> None:
        # A path is judged by what the filesystem resolves it to.
        try:
            os.symlink(self.project / ".git", self.project / "g", target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks need a privilege here: {error}")
        for command in ("printf x >> g/config", "cd g && echo x >> config"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")
        self.assertIsNone(self._run("echo x > docs/config"))

    def test_a_write_through_a_hard_link_or_a_link_made_in_the_same_call_asks(self) -> None:
        try:
            os.link(self.project / ".git" / "config", self.project / "c")
        except OSError as error:
            self.skipTest(f"hard links are not available here: {error}")
        self.assertEqual(self._decision(self._run("printf x >> c")), "ask")
        for command in ("ln -s .git g && printf x >> g/config",
                        "ln -s .. up && cd up/project/.git && echo x >> config",
                        "cmd /c mklink /J g .git & echo x >> g\\config"):
            with self.subTest(command=command):
                self.assertEqual(self._decision(self._run(command)), "ask")

    def test_a_write_from_a_call_already_inside_the_git_directory_asks(self) -> None:
        # The host shell kept an earlier `cd .git`: the call's own `cwd`
        # is where a bare `config` lands.
        command = r"printf '[godmode]\n\tuninit%s = off\n' ialized >> config"
        self.assertEqual(self._decision(self._run(command, cwd=self.project / ".git")), "ask")
        self.assertEqual(self._decision(
            self._no_ask(command, cwd=self.project / ".git", session="n")), "deny")

    def test_an_edit_of_the_repository_config_is_asked_about(self) -> None:
        body = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                "tool_input": {"file_path": str(self.project / ".git" / "config"),
                               "content": "[godmode]\nuninitialized = off\n"},
                "cwd": str(self.project)}
        done = subprocess.run(
            [sys.executable, "-I", "-B", str(FAST_GATE)], input=json.dumps(body).encode(),
            capture_output=True, cwd=str(self.project), timeout=60,
            env=scrubbed_env(GODMODE_STATE_HOME=str(self.home)))
        self.assertIn(b'"ask"', done.stdout)

    def test_the_notice_reaches_a_host_without_session_start_once(self) -> None:
        first = self._grok("git status")
        self.assertEqual(first["decision"], "allow")
        notice = first["hookSpecificOutput"]["additionalContext"]
        self.assertIn("installed but NOT initialized here", notice)
        self.assertIn("only harm-class commands are guarded", notice)
        self.assertIn("godmode config set uninitialized off", notice)
        self.assertIsNone(self._grok("git status"))
        self.assertIsNone(self._grok("npm install"))
        self.assertIsNotNone(self._grok("git status", session="s-2"), "a new session hears it")
        self._assert_nothing_created()

    def test_the_full_hook_guards_the_same_when_the_fast_gate_is_unsure(self) -> None:
        # A `GIT_DIR` override makes the stat-only check unsure, so the
        # call escalates; the full hook, finding no archive, asks the same.
        git_dir = str(self.project / ".git")
        self.assertEqual(self._decision(self._run(self.FORCE_PUSH, GIT_DIR=git_dir)), "ask")
        self.assertNotIn(self._decision(self._run("npm install", GIT_DIR=git_dir)),
                         ("ask", "deny"))
        self._assert_nothing_created()

    def test_a_host_with_session_start_gets_no_notice_on_its_calls(self) -> None:
        self.assertIsNone(self._run("git status"))

    def test_the_notice_is_not_given_when_the_guard_is_off(self) -> None:
        self._write_setting("off")
        self.assertIsNone(self._grok("git status"))

    def test_ordinary_work_never_imports_the_runtime(self) -> None:
        """The ordinary path stays the stat-only path: no module from the
        runtime package is imported for it, read from the interpreter's own
        module table after `main()` returns. A harm-class command is the
        only one that pays for the classifier."""
        script = (
            "import io, json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import godmode_stdin, godmode_gate_fast as gate\n"
            "godmode_stdin.read_first_json = lambda: sys.argv[1].encode()\n"
            "sys.stdout = io.StringIO()\n"
            "gate.main()\n"
            "sys.stdout = sys.__stdout__\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.startswith('godmode_runtime'))))\n")

        def loaded(command: str) -> list[str]:
            body = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                               "tool_input": {"command": command}, "cwd": str(self.project)})
            done = subprocess.run(
                [sys.executable, "-I", "-B", "-c", script, body], capture_output=True,
                cwd=str(self.project), timeout=60,
                env=scrubbed_env(GODMODE_STATE_HOME=str(self.home)))
            self.assertEqual(done.returncode, 0, done.stderr[-600:])
            return json.loads(done.stdout.decode().strip().splitlines()[-1])

        for command in ("npm install", "python -m unittest", "cargo build", "make"):
            with self.subTest(command=command):
                self.assertEqual(loaded(command), [])
        self.assertIn("godmode_runtime.godmode_sentinel", loaded(self.FORCE_PUSH))


class UninitializedGuardScreen(unittest.TestCase):
    """The keyword screen is what keeps ordinary work off the classifier,
    so it must never miss a command the classifier calls harm-class."""

    def test_every_harm_class_command_is_a_candidate(self) -> None:
        samples = [entry["operation"] for entry in corpus_entries()] + [
            "git push", "git push --force", "git -C . push -f", "git reset --hard",
            "git clean -fdx", "git branch -D x", "rm -rf /", "rm -rf ../x",
            "Remove-Item -Recurse ..\\x", "del C:\\x", "npm publish", "twine upload dist/*",
            "gh release create v1", "make release", "claude plugin eval",
            "psql -c 'DROP TABLE users'", "find / -delete", "find . -exec touch {} ;",
            "vssadmin delete shadows /all", "tmutil delete x",
            "bash -c 'git push --force'", "python -c \"import os; os.system('rm -rf /')\"",
            "echo pw | godmode authorize stage --password-stdin",
            "g\"i\"t pu''sh --force", "git p\\ush --force", "r^m -rf ..\\x",
            "git \"pu\"$'sh' -f", "git pu$\"sh\" -f", "git $(printf pu)sh -f",
            "git ${x:-push} -f",
        ]
        missed = []
        for command in samples:
            verdict = classify_action(command, project_root=PLUGIN_ROOT, tool_name="Bash")
            harmful = fast._harm_category(verdict, str(PLUGIN_ROOT), _contained)
            if harmful and not fast.harm_candidate(payload(command), [str(PLUGIN_ROOT)]):
                missed.append((command, harmful))
        self.assertEqual(missed, [])

    def test_an_expansion_spliced_into_a_word_is_a_candidate(self) -> None:
        # `$@` and `$*` expand to nothing and `$x` to what an earlier
        # assignment set: the word that runs is not the word in the text.
        for command in ("x=sh; git pu$x -f", "git pu$@sh -f", "git pu$*sh -f",
                        "r$@m -rf /tmp/x", "npm pub$@lish", "git $x -f",
                        "git pu`printf s`h -f", "git pu{s,}h -f", "git pu?h -f",
                        "set x=s&& git pu%x%h -f", 'tmux new -d "$C"',
                        "python -m godmode_runtime.godmode_console authorize stage x",
                        "python scripts/godmode_runtime/godmode_console.py authorize stage x"):
            with self.subTest(command=command):
                self.assertTrue(fast.harm_candidate(payload(command), ["."]))

    def test_a_script_the_classifier_reads_is_read_by_the_screen(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "ship.py").write_text(
                'import subprocess\nsubprocess.run(["git", "push", "--force"])\n', encoding="utf-8")
            (Path(temporary) / "calm.py").write_text("print(1)\n", encoding="utf-8")
            self.assertTrue(fast.harm_candidate(payload("python ship.py"), [temporary]))
            self.assertFalse(fast.harm_candidate(payload("python calm.py"), [temporary]))

    def test_the_script_heads_match_the_classifier(self) -> None:
        from godmode_runtime.godmode_sentinel import _SCRIPT_HEADS, _MAX_SCRIPT_BYTES
        self.assertEqual(fast._SCRIPT_HEADS, _SCRIPT_HEADS)
        self.assertEqual(fast._MAX_SCRIPT_BYTES, _MAX_SCRIPT_BYTES)

    def test_ordinary_commands_are_not_candidates(self) -> None:
        for command in ("npm install", "python -m unittest", "cargo build", "make",
                        "git commit -m wip", "pytest -q tests"):
            with self.subTest(command=command):
                self.assertFalse(fast.harm_candidate(payload(command), ["."]))

    def test_a_delete_inside_the_project_is_not_harm(self) -> None:
        for command, harmful in (("rm -rf build", False), ("rm -rf ../x", True),
                                 ("rm $TARGET", True), ("ls | xargs rm", True),
                                 ("rm -rf build/*", False)):
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, tool_name="Bash")
                got = fast._harm_category(verdict, str(PLUGIN_ROOT), _contained)
                self.assertEqual(got is not None, harmful, verdict)


class AntigravityPayloadShape(unittest.TestCase):
    """Tenth field report 2026-09-05: Antigravity delivers
    `{"toolCall": {"name": "run_command", "args": {"CommandLine": ...}}}`.
    The fast gate read only toolName/toolInput.command, so every
    Antigravity call escalated to the full hook and the fast path never
    applied there."""

    def test_a_read_only_command_line_allows_in_process(self) -> None:
        payload = {"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}}
        self.assertEqual(fast.fast_verdict(payload, TABLE), "allow")

    def test_a_mutating_command_line_still_escalates(self) -> None:
        payload = {"toolCall": {"name": "run_command",
                                "args": {"CommandLine": "git push " + "--force"}}}
        self.assertEqual(fast.fast_verdict(payload, TABLE), "escalate")

    def test_an_unknown_nested_tool_escalates(self) -> None:
        payload = {"toolCall": {"name": "write_to_file", "args": {"CommandLine": "git status"}}}
        self.assertEqual(fast.fast_verdict(payload, TABLE), "escalate")


class FailOpen(unittest.TestCase):
    """'Fail open' here means fail toward escalation, never toward allow -
    the gate's only safe direction when anything is uncertain."""

    def test_internal_exception_escalates(self) -> None:
        self.assertEqual(
            fast.fast_verdict({"tool_input": {"command": None}}, {"broken": True}),
            "escalate",
        )

    def test_missing_table_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status"), None), "escalate")

    def test_malformed_table_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status"), []), "escalate")
        self.assertEqual(fast.fast_verdict(payload("git status"), "not a dict"), "escalate")

    def test_corrupt_table_shapes_all_escalate(self) -> None:
        corrupt_tables = [
            {},
            {"floor": None, "read_heads": ["ls"]},
            {"floor": {"claude-code": ["git status"]}, "read_heads": "ls,cat"},
            {"floor": {"claude-code": [1, 2, 3]}, "read_heads": ["ls"]},
            {"floor": {}, "read_heads": None},
        ]
        for table in corrupt_tables:
            with self.subTest(table=table):
                self.assertEqual(fast.fast_verdict(payload("git status"), table), "escalate")

    def test_forced_internal_exception_still_escalates(self) -> None:
        """Not just an anticipated bad-input shape - a genuinely unexpected
        exception raised deep inside the verdict path must still resolve to
        escalate, never propagate and never allow."""
        real_segments = fast._blanked_segments
        fast._blanked_segments = lambda command: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            verdict = fast.fast_verdict(payload("git status"), TABLE)
        finally:
            fast._blanked_segments = real_segments
        self.assertEqual(verdict, "escalate")

    def test_fenced_tools_always_escalate(self) -> None:
        for tool in ("Edit", "Write", "NotebookEdit"):
            with self.subTest(tool=tool):
                pl = {"hook_event_name": "PreToolUse", "tool_name": tool,
                      "tool_input": {"file_path": "x.py", "content": "y"}}
                self.assertEqual(fast.fast_verdict(pl, TABLE), "escalate")

    def test_unknown_tool_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status", tool="Read"), TABLE),
                         "escalate")


class KnownShapes(unittest.TestCase):
    """Green controls: the exact shapes the floor is built to allow, and the
    exact shapes it must still escalate even though the floor's head or
    phrase matches on the surface."""

    def test_bare_floor_reads_allow(self) -> None:
        for command in ("git status", "git log", "ls -la", "cat file.txt",
                        "grep -rn pattern .", "git remote -v"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_redirect_always_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status > out.txt"), TABLE),
                         "escalate")
        self.assertEqual(fast.fast_verdict(payload("cat file.txt >> log"), TABLE),
                         "escalate")

    def test_find_exec_and_delete_escalate(self) -> None:
        self.assertEqual(
            fast.fast_verdict(payload("find . -name x -exec rm {} +"), TABLE),
            "escalate")
        self.assertEqual(fast.fast_verdict(payload("find . -delete"), TABLE), "escalate")

    def test_find_execdir_ok_okdir_escalate(self) -> None:
        """Review round 1, Critical finding 1 - reproduced live against the
        pre-fix module (fast: allow, full: R4/protected) for all three;
        fixed by table-driving the full `_FIND_MUTATION` flag set instead
        of a hand-picked two-flag subset."""
        for command in ("find . -execdir rm {} ;", "find . -ok rm {} ;",
                         "find . -okdir rm {} ;"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_find_without_a_mutation_flag_still_allows(self) -> None:
        """Green control: the fix must not make ordinary `find` protected."""
        self.assertEqual(fast.fast_verdict(payload("find . -name x"), TABLE), "allow")

    def test_git_output_flag_escalates_on_log_diff_show(self) -> None:
        """Review round 1, Critical finding 2 - reproduced live against the
        pre-fix module (fast: allow, full: R0 - a real, unrecorded write the
        full sentinel doesn't yet catch either; see the changelog fragment
        for the separately-tracked sentinel-lane fix). `--output=<file>`,
        `--output <file>`-shaped (bare `--output` token), and bare `-o`
        must all escalate."""
        for command in ("git log --output=/tmp/x", "git diff --output=/tmp/x",
                         "git show --output=/tmp/x", "git log --output /tmp/x",
                         "git log -o /tmp/x", "git diff -o /tmp/x",
                         "git show -o /tmp/x"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_log_diff_show_without_a_write_flag_still_allow(self) -> None:
        """Green controls: the fix must not degrade the fast path's
        everyday utility - ordinary log/diff formatting flags stay allowed."""
        for command in ("git log --oneline -20", "git diff --stat",
                         "git show --stat", "git log -- src/foo.py"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_glued_short_flag_denylist_escalates(self) -> None:
        """Task 5 deferred-minor fix: the denylist match compared a trailing
        token to the denylisted flag exactly (after stripping any `=value`),
        which caught `-o /tmp/x` (two tokens) and `-o=x` but not git's own
        glued short-flag spelling `-oFILE` (one token, no separator at all) -
        `git log -o/tmp/x` fast-allowed a real, unrecorded write. Matching
        must prefix-match short (single-dash, single-character) denylisted
        flags against each trailing token instead of comparing for equality."""
        for command in ("git log -o/tmp/x", "git diff -o/tmp/x",
                         "git show -o/tmp/x"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_glued_short_flag_fix_does_not_overmatch_long_flags(self) -> None:
        """Green control: a long flag must never prefix-match - only the
        exact `--output`/`--output=...` forms are denylisted, so an unrelated
        long flag that happens to start with the same letters stays allowed."""
        self.assertEqual(
            fast.fast_verdict(payload("git log --oneline"), TABLE), "allow")

    def test_bare_git_branch_create_escalates(self) -> None:
        """The one real mutation reachable without any flag at all on this
        floor - a bare trailing word after `git branch` creates a branch."""
        self.assertEqual(fast.fast_verdict(payload("git branch new-feature"), TABLE),
                         "escalate")

    def test_git_branch_delete_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git branch -d old"), TABLE),
                         "escalate")

    def test_git_remote_v_with_trailing_token_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git remote -v origin"), TABLE),
                         "escalate")

    def test_compound_command_with_one_unrecognised_segment_escalates(self) -> None:
        self.assertEqual(
            fast.fast_verdict(payload("git status && rm -rf build"), TABLE),
            "escalate")

    def test_unrecognised_head_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("npm view pkg version"), TABLE),
                         "escalate")

    def test_bare_tr_is_on_the_floor(self) -> None:
        """Reverses the provisional table's deliberate exclusion. That
        fixture left `tr` off the floor because `classify_action` did not
        yet recognise a bare `tr` as read-only (one of the FP3 corpus
        entries this same plan's Task 3 exists to fix). Task 5's generator
        re-verifies this live against the sentinel at build time
        (`scripts/dev/build_decision_table.py::_build_read_heads`) rather
        than trusting the old exclusion: `classify_action("tr a b")` is R0
        now, so `tr` belongs on the floor, and the fast gate must fast-allow
        it exactly like every other read head.
        """
        self.assertIn("tr", TABLE["read_heads"])
        self.assertEqual(fast.fast_verdict(payload("tr a b"), TABLE), "allow")

    def test_a_directory_change_before_a_read_stays_on_the_fast_path(self) -> None:
        """2026-09-25: `cd <dir> && git log` escalated every time and ran
        past the host's timeout under load. `cd` changes no file; the rest
        of the command is still judged segment by segment."""
        for command in ("cd src && git log --oneline -5", "cd .. && git status",
                        "cd sub; ls -la"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")
        for command in ("cd src && rm -rf build", "cd src && git push",
                        "cd src > out.txt", "cd $(rm -rf x)"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "escalate")


class Adversarial(unittest.TestCase):
    """Final whole-branch review (final-review.md), two Critical findings.
    Synthetic, hand-constructed probes - deliberately NOT added to
    `tests/fixtures/gate_corpus.json`, whose provenance is real denials
    only; a synthetic entry there would corrupt that population. This class
    is where synthetic adversarial coverage belongs instead.
    """

    def test_c1_command_substitution_escalates(self) -> None:
        """Reproduced red against the pre-fix module (fast: allow, exit 0,
        silent - the full hook never invoked; full sentinel: R4 or R5,
        protected). A REGRESSION from this plan's own pre-fast-gate
        baseline, which refused `cat $(rm -rf /)` outright - the fast gate
        had reopened a hole the branch itself had closed."""
        for command in (
            "cat $(rm -rf build)",
            "echo $(git push --force origin main)",
            "ls `rm -rf x`",
            "diff <(cat a) <(cat b)",
            "cat <(rm -rf build)",
            "grep x <(rm -rf build)",
            "echo hi >(tee /etc/hosts)",
        ):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_c1_quoting_does_not_exempt_substitution(self) -> None:
        """The fix is a RAW scan on purpose: `"$(...)"` inside double quotes
        still runs the inner command (the shell only suppresses
        word-splitting of the result), so a quote-aware exemption here would
        reopen the exact gap this fixes through a quote."""
        self.assertEqual(
            fast.fast_verdict(payload('echo "$(rm -rf build)"'), TABLE),
            "escalate")

    def test_c1_green_controls_unaffected(self) -> None:
        """A bare `$` not followed by `(` is ordinary text, not a
        substitution marker - ordinary floor-clean commands must stay
        allowed."""
        for command in ("git status", 'grep "price $40" f.txt',
                         "echo $HOME", "ls -la"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_c2_sort_output_flag_escalates(self) -> None:
        """Reproduced red against the pre-fix module (fast: allow, silent;
        full sentinel: R2/ask via `_OUTPUT_FLAGS_BY_HEAD["sort"]`). The
        read-head branch matched on head alone and never consulted an
        output-flag table at all - the git-phrase branch's `flag_denylist`
        fix from review round 1 covered only git, not the other read heads
        that share the same write-capable-flag shape."""
        for command in ("sort -o /etc/hosts f.txt",
                         "sort --output=/etc/hosts f.txt",
                         "sort -o/etc/hosts f.txt",
                         "sort --output /etc/hosts f.txt"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_c2_sort_without_an_output_flag_still_allows(self) -> None:
        """Green controls: ordinary `sort` usage - including short flags
        that are not the denylisted `-o` - must stay fast-allowed."""
        for command in ("sort f.txt", "sort -u f.txt", "sort -n -r data.csv"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_c1_and_c2_end_to_end_through_the_real_script(self) -> None:
        """The exact end-to-end smoke the review asked for: pipe the C1
        payload into the actual script and confirm the full hook's
        refusal JSON appears on stdout, proving escalation - not just the
        in-process `fast_verdict` call - actually happens. Run against a
        project this test governs itself (see `_governed_project`), not
        THIS checkout, so it proves the same thing on a fresh install."""
        project = _governed_project()
        try:
            raw = json.dumps(payload("cat $(rm -rf build)")).encode("utf-8")
            result = subprocess.run(
                [sys.executable, str(FAST_GATE)],
                input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=project, timeout=30,
            )
            self.assertIn(b"permissionDecision", result.stdout)
        finally:
            shutil.rmtree(project, ignore_errors=True)


class RepeatedVerdicts(unittest.TestCase):
    """D-3: this used to bound 1000 calls to under a second - a throughput
    claim, not a correctness one, and the wrong kind of assertion to make
    on a clock (`benchmarks/gate_latency.py` is where that claim now lives,
    as printed percentiles with nothing to flake). What is left worth
    asserting here: the verdict itself never drifts across repeated calls
    - no call mutates `TABLE` or otherwise leaves state behind that would
    change what the next call decides."""

    def test_a_thousand_repeats_all_agree(self) -> None:
        verdicts = {fast.fast_verdict(payload("git status"), TABLE) for _ in range(1000)}
        self.assertEqual(verdicts, {"allow"})


class EndToEndSmoke(unittest.TestCase):
    """Real subprocess invocations of the fast gate script itself, exactly
    as the host would run it."""

    def _run(self, command: str, tool: str = "Bash",
              cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
        raw = json.dumps(payload(command, tool=tool)).encode("utf-8")
        return subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd or PLUGIN_ROOT, timeout=30,
        )

    def test_a_floor_read_exits_silently(self) -> None:
        result = self._run("git status")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_a_refused_mutation_escalates_to_the_full_hook(self) -> None:
        """Run against a project this test governs itself
        (`_governed_project`), not THIS checkout: a mutation escalates to
        the full hook only when there is something for it to gate, and a
        fresh, uninitialized install has nothing under THIS checkout's own
        `.git` to find."""
        project = _governed_project()
        try:
            result = self._run("git push --force", cwd=project)
            self.assertIn(b"permissionDecision", result.stdout)
            self.assertIn(b"deny", result.stdout)
        finally:
            shutil.rmtree(project, ignore_errors=True)

    def test_empty_stdin_escalates_without_crashing(self) -> None:
        """Empty input carries no `hook_event_name: PreToolUse`, so the full
        hook it escalates to takes its non-pretool branch (`return 0 if
        preview["allow"] else 3`) rather than the pretool one - confirmed
        directly against `godmode_session_hook.py` before writing this
        assertion, not assumed. The point of this test is only that the
        fast gate never crashes and always mirrors whatever the full hook
        actually does, exit code included."""
        result = subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )
        direct = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "godmode_session_hook.py"), "pre-action"],
            input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )
        self.assertEqual(result.returncode, direct.returncode)
        self.assertEqual(result.stdout, direct.stdout)

    def test_a_full_check_past_the_deadline_refuses_instead_of_timing_out_open(self) -> None:
        """A host runs the tool when a hook outlives its timeout, so the fast
        gate must answer first: a hung full check is a refusal (exit 2)."""
        import io
        from unittest import mock
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "true; git push origin HEAD:main"}}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            hung = Path(tmp) / "hung.py"
            hung.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            sys.path.insert(0, str(HOOKS_DIR))
            import godmode_stdin
            err = io.StringIO()
            with mock.patch.object(godmode_stdin, "read_first_json", lambda: payload), \
                    mock.patch.object(fast, "FULL_HOOK", hung), \
                    mock.patch.object(fast, "FULL_HOOK_DEADLINE_SECONDS", 1), \
                    mock.patch.object(fast, "ungoverned_project", lambda _p: False), \
                    mock.patch.object(sys, "stderr", err):
                code = fast.main()
        self.assertEqual(code, 2)
        self.assertIn("could not decide", err.getvalue())

    def test_a_read_or_local_run_past_the_deadline_is_allowed_without_the_archive(self) -> None:
        """The archive lock is what hangs the full check while a suite
        runs; a read or a local computation is judged without it."""
        import io
        from unittest import mock
        sys.path.insert(0, str(HOOKS_DIR))
        import godmode_stdin
        with tempfile.TemporaryDirectory() as tmp:
            hung = Path(tmp) / "hung.py"
            hung.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            for command, expected in (("python -m pytest -q tests/test_x.py && echo done", 0),
                                      ("git log --oneline -3 | head -2", 0),
                                      ("rm -rf ../elsewhere", 2)):
                payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                      "tool_input": {"command": command}}).encode()
                err, out = io.StringIO(), io.StringIO()
                with self.subTest(command=command), \
                        mock.patch.object(godmode_stdin, "read_first_json", lambda p=payload: p), \
                        mock.patch.object(fast, "FULL_HOOK", hung), \
                        mock.patch.object(fast, "FULL_HOOK_DEADLINE_SECONDS", 1), \
                        mock.patch.object(fast, "ungoverned_project", lambda _p: False), \
                        mock.patch.object(sys, "stderr", err), \
                        mock.patch.object(sys, "stdout", out):
                    self.assertEqual(fast.main(), expected, err.getvalue())
                    if expected == 0:
                        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()


class S12BWidening(unittest.TestCase):
    """Corpus-driven widening: null-target redirects and five new floor
    heads resolve fast; every other redirect and every protected shape
    still escalates. The full sentinel graded each widened shape R0 before
    the rule existed - the fast path only caught up."""

    def _fast(self, command):
        return fast.fast_verdict(payload(command), TABLE)

    def test_null_target_redirects_resolve_fast(self) -> None:
        for command in ("ls > /dev/null", "grep -c x f 2>/dev/null",
                        "git status >/dev/null 2>/dev/null",
                        "wc -l f >> /dev/null"):
            self.assertEqual(self._fast(command), "allow", command)

    def test_a_file_target_still_escalates(self) -> None:
        for command in ("ls > out.txt", "ls 2> err.log",
                        "cat f >> notes.md", "sort f > /dev/null.bak"):
            self.assertEqual(self._fast(command), "escalate", command)

    def test_the_new_heads_resolve_fast_and_stay_r0_in_the_sentinel(self) -> None:
        for command in ("rev f", "date +%s", "basename /a/b",
                        "dirname /a/b", "realpath ."):
            self.assertEqual(self._fast(command), "allow", command)
            self.assertEqual(_decision(command), "allow", command)

    def test_a_protected_tail_behind_a_null_redirect_still_escalates(self) -> None:
        self.assertEqual(
            self._fast("cat f > /dev/null && git push --force origin main"),
            "escalate")

    def test_an_output_flag_behind_a_null_redirect_still_escalates(self) -> None:
        # sort -o writes a file regardless of where stdout goes.
        self.assertEqual(self._fast("sort -o /etc/hosts f 2>/dev/null"),
                         "escalate")


class PayloadGrammarParity(unittest.TestCase):
    """G-8: one payload grammar. `hooks/godmode_stdin.read_first_json`
    already tolerates a UTF-8 BOM prefix, CRLF line endings, a trailing
    newline, trailing non-JSON data after the first object, and two
    concatenated JSON objects - it resolves on the FIRST complete object
    and never waits for or requires EOF. Both stages read through that
    same reader, but each then re-decodes the bytes it returns on its own:
    the full hook used to do that with a plain `json.loads`, which raises
    on a leading BOM (`Unexpected UTF-8 BOM`) and on anything after the
    first object (`Extra data`) - so a payload the reader itself already
    tolerated still refused with 'Operation description cannot be empty'.
    These are real subprocess invocations of both scripts, exactly as a
    host would run them, for a read-only command (must silently allow on
    both) and a protected one (must deny on both)."""

    _READ_ONLY = payload("git status")
    _DENY = payload("git push --force origin main")

    def setUp(self) -> None:
        # Each test governs its own project (`_governed_project`) rather
        # than running `cwd` on THIS checkout: `_direct`'s own docstring
        # notes it used to spawn against the live archive here, and a
        # fresh, uninitialized install has no archive under THIS
        # checkout's `.git` for the full hook to gate against at all.
        self.project = _governed_project()
        # The full hook asks some things once per session (a fresh archive's
        # unread required sources, for one); whichever shape runs first would
        # get that ask instead of a silent allow, so the result depended on
        # which test module used the session before this one. One throwaway
        # call spends those asks before any shape is compared.
        self._direct(json.dumps(self._READ_ONLY).encode("utf-8"))

    def tearDown(self) -> None:
        shutil.rmtree(self.project, ignore_errors=True)

    @staticmethod
    def _shapes(base: dict[str, Any]) -> dict[str, bytes]:
        plain = json.dumps(base).encode("utf-8")
        return {
            "bom": b"\xef\xbb\xbf" + plain,
            "crlf": json.dumps(base, indent=2).encode("utf-8").replace(b"\n", b"\r\n"),
            "trailing_newline": plain + b"\n",
            "trailing_data": plain + b"\nthis is not json at all",
            "two_concatenated_objects": plain + plain,
        }

    def _direct(self, raw: bytes) -> subprocess.CompletedProcess[bytes]:
        # Incident 2026-09-18 (chain fork at sequence 19211): this spawn ran
        # the real hook against the LIVE archive with no isolated state
        # home, racing the installed plugin's own hooks under a different
        # lock scheme. Every real-hook spawn gets its own state home AND
        # its own governed project (`self.project`, from `setUp`) rather
        # than THIS checkout - a git project's archive lives under its own
        # `.git`, which `GODMODE_STATE_HOME` does not redirect, so running
        # with `cwd` on THIS checkout still reached the live archive (or,
        # on a fresh install, no archive at all).
        with tempfile.TemporaryDirectory() as state_home:
            return subprocess.run(
                [sys.executable, str(HOOKS_DIR / "godmode_session_hook.py"), "pre-action"],
                input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self.project, timeout=30,
                env={**os.environ, "GODMODE_STATE_HOME": state_home},
            )

    def _fast(self, raw: bytes) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=self.project, timeout=30,
        )

    def test_read_only_command_allows_on_both_stages_for_every_shape(self) -> None:
        for shape, raw in self._shapes(self._READ_ONLY).items():
            with self.subTest(shape=shape):
                direct = self._direct(raw)
                fast_result = self._fast(raw)
                self.assertEqual(direct.returncode, 0, (shape, direct.stderr))
                self.assertEqual(direct.stdout, b"", (shape, direct.stderr))
                self.assertEqual(fast_result.returncode, 0, (shape, fast_result.stderr))
                self.assertEqual(fast_result.stdout, b"", (shape, fast_result.stderr))

    def test_forced_push_denies_on_both_stages_for_every_shape(self) -> None:
        # A malformed payload also denies pre-action (fail-closed, Task 2),
        # but with exit 2 and a generic "no operation described in a
        # malformed payload" reason - that would make this test pass
        # trivially without the parser fix actually working. Pinning the
        # real classifier's exit code (0) and its command-specific reason
        # text ("irreversible", the same wording `classify_action` gives
        # this exact command bare) proves the command was actually parsed
        # and classified, not merely refused as unreadable.
        baseline = self._direct(json.dumps(self._DENY).encode("utf-8"))
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertIn(b"irreversible", baseline.stdout)
        for shape, raw in self._shapes(self._DENY).items():
            with self.subTest(shape=shape):
                direct = self._direct(raw)
                fast_result = self._fast(raw)
                self.assertEqual(direct.returncode, 0, (shape, direct.stderr))
                self.assertEqual(direct.stdout, baseline.stdout, (shape, direct.stderr))
                self.assertEqual(fast_result.returncode, 0, (shape, fast_result.stderr))
                self.assertEqual(fast_result.stdout, baseline.stdout, (shape, fast_result.stderr))

"""R-5 + NS-10a: one wiring path, two modes, marker-delimited merge.

`godmode_wire.wire()` is the single function behind both `hooks wire --all`
and its `--dry-run` preview - same rendering, same comparisons, dry-run
only suppresses the write. Every host writer it drives owns exactly one
region of a file it may have to share with foreign content (a JSON object
owns a `"godmode"` key, a JSON array's Godmode entries carry `"_godmode":
true`) and is byte-identical on a second run; a hand-edit inside that
region is refused as `[CONFLICT]` unless `--force`. `merge_text_block()` is
the literal `<!-- godmode:begin -->`/`<!-- godmode:end -->` primitive for a
plain text/TOML shared config, proven directly here against a generic
fixture; NS-6's Copilot instructions block is its first real host target
(`tests/test_host_manifests.py::CopilotManifestTests`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as HM  # noqa: E402
from godmode_runtime import godmode_wire as W  # noqa: E402
from godmode_runtime.godmode_anchor import is_linked_worktree, resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_hooks  # noqa: E402


def _digests(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _run_git(["init", "-q"], path)
    _run_git(["config", "user.email", "hooks-wire-test@example.com"], path)
    _run_git(["config", "user.name", "Hooks Wire Test"], path)
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    _run_git(["add", "README.md"], path)
    _run_git(["commit", "-q", "-m", "init"], path)


class WireFunctionMergeTests(unittest.TestCase):
    """Direct tests of `godmode_wire.wire()` - no CLI, no archive."""

    def test_a_fresh_project_creates_every_known_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(all(line.startswith("[CREATE]") for line in report["lines"]))
            self.assertEqual(sorted(report["changed"]), sorted(W.WIRE_HOSTS))
            for host in W.WIRE_HOSTS:
                self.assertEqual(W.wire_status(project)[host], "in-sync")

    def test_merging_twice_produces_byte_identical_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            before = _digests(project)
            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            after = _digests(project)
            self.assertEqual(before, after)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertEqual(report["changed"], [])
            self.assertTrue(all(line.startswith("[OK]") for line in report["lines"]),
                            report["lines"])

    def test_a_user_owned_key_outside_the_markers_survives_antigravity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".agents").mkdir(parents=True)
            (project / ".agents" / "hooks.json").write_text(
                json.dumps({"someOtherPlugin": {"enabled": True, "note": "hand-authored"}},
                           indent=2) + "\n", encoding="utf-8")
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            doc = json.loads((project / ".agents" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["someOtherPlugin"], {"enabled": True, "note": "hand-authored"})
            self.assertIn("godmode", doc)
            # Re-running does not disturb the foreign key either.
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            doc2 = json.loads((project / ".agents" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(doc2["someOtherPlugin"], {"enabled": True, "note": "hand-authored"})

    def test_a_user_owned_block_outside_the_markers_survives_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            (project / ".codex" / "hooks.json").write_text(json.dumps({
                "hooks": {"SessionStart": [{"hooks": [
                    {"type": "command", "command": "echo user-owned"}]}]}
            }, indent=2) + "\n", encoding="utf-8")
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            doc = json.loads((project / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            commands = [entry["command"] for block in doc["hooks"]["SessionStart"]
                        for entry in block["hooks"]]
            self.assertIn("echo user-owned", commands)
            godmode_blocks = [b for b in doc["hooks"]["SessionStart"] if b.get("_godmode") is True]
            self.assertTrue(godmode_blocks)

    def test_a_hand_edit_inside_the_owned_block_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            target = project / ".agents" / "hooks.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["godmode"]["enabled"] = False  # tamper without recomputing the digest
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            normalized = [line.replace("\\", os.sep).replace("/", os.sep)
                         for line in report["lines"]]
            self.assertIn("[CONFLICT] antigravity: .agents" + os.sep + "hooks.json", normalized)
            self.assertEqual(report["changed"], [])
            self.assertEqual(W.wire_status(project)["antigravity"], "drifted")
            # The conflict blocks the WHOLE batch - even the untouched
            # hosts write nothing this call.
            self.assertEqual(report["changed"], [])

    def test_the_report_names_the_target_project_relative_under_an_aliased_root(self) -> None:
        """The 0.3.28 release preflight ran under an aliased temp directory
        and the conflict line printed the absolute resolved path where every
        other run prints `.agents/hooks.json`. The target comes back from
        the containment check resolved; the project is whatever spelling
        the caller passed. A `..` segment is the portable stand-in for an
        alias: same directory, different spelling, and `relative_to` on the
        raw pair raises exactly as it does under a short-name alias."""
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "sub").mkdir()
            aliased = Path(temp) / "sub" / ".."
            report = W.wire(aliased, ["antigravity"], dry_run=True, force=False)
            normalized = [line.replace("\\", os.sep).replace("/", os.sep)
                          for line in report["lines"]]
            self.assertEqual(
                normalized, ["[CREATE] antigravity: .agents" + os.sep + "hooks.json"])
            self.assertEqual(
                W._rel(aliased, (Path(temp) / ".agents" / "hooks.json").resolve()),
                os.path.join(".agents", "hooks.json"))

    def test_force_overwrites_a_conflicted_host_and_stamps_a_fresh_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            target = project / ".agents" / "hooks.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["godmode"]["enabled"] = False
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=True)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertIn("antigravity", report["changed"])
            self.assertEqual(W.wire_status(project)["antigravity"], "in-sync")

    def test_wire_all_reports_in_sync_after_a_clean_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            status = W.wire_status(project)
            self.assertEqual(status, {host: "in-sync" for host in W.WIRE_HOSTS})

    def test_wire_status_reports_absent_before_any_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            status = W.wire_status(project)
            self.assertEqual(status, {host: "absent" for host in W.WIRE_HOSTS})

    def test_dry_run_leaves_every_file_under_the_project_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
            before = _digests(project)
            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=True, force=False)
            after = _digests(project)
            self.assertEqual(before, after)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(all(line.startswith("[CREATE]") for line in report["lines"]))
            self.assertEqual(report["changed"], [])

    def test_dry_run_after_a_real_apply_still_touches_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, list(W.WIRE_HOSTS), dry_run=False, force=False)
            before = _digests(project)
            report = W.wire(project, list(W.WIRE_HOSTS), dry_run=True, force=False)
            after = _digests(project)
            self.assertEqual(before, after)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(all(line.startswith("[OK]") for line in report["lines"]))


class WireFixRound1Tests(unittest.TestCase):
    """Fix round 1 (task-4-review.md B1-B4, N1, N4, N8): legacy adoption,
    foreign top-level keys, unforceable malformed JSON, adopt-on-match for a
    missing digest, deterministic event order, `wire()` not raising past a
    missing source, and a forced conflict recorded as such."""

    def test_b2_codex_foreign_top_level_keys_survive_a_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            (project / ".codex" / "hooks.json").write_text(json.dumps({
                "version": 1, "notify": {"enabled": True}, "hooks": {},
            }, indent=2) + "\n", encoding="utf-8")
            report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            doc = json.loads((project / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["version"], 1)
            self.assertEqual(doc["notify"], {"enabled": True})
            self.assertIn("hooks", doc)

    def test_b3_malformed_codex_json_is_unforceable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            target = project / ".codex" / "hooks.json"
            target.write_text("{not valid json", encoding="utf-8")
            before = target.read_bytes()
            report = W.wire(project, ["codex"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(any("not valid JSON" in line for line in report["lines"]),
                             report["lines"])

    def test_b3_malformed_antigravity_json_is_unforceable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".agents").mkdir(parents=True)
            target = project / ".agents" / "hooks.json"
            target.write_text("{not valid json", encoding="utf-8")
            before = target.read_bytes()
            report = W.wire(project, ["antigravity"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(any("not valid JSON" in line for line in report["lines"]),
                             report["lines"])

    def test_b1_legacy_codex_blocks_are_adopted_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            HM.write_codex_project_hooks(W._PLUGIN_ROOT, project)
            target = project / ".codex" / "hooks.json"

            # n4: a foreign, hand-authored block sharing an event with
            # adopted legacy content must survive the adoption verbatim -
            # this is the assertion that would catch a regression in
            # `legacy_matched`'s foreign filter (e.g. it swallowing every
            # block in the event instead of only the ones it matched).
            doc = json.loads(target.read_text(encoding="utf-8"))
            foreign_block = {"hooks": [{"type": "command", "command": "echo foreign"}]}
            doc["hooks"]["SessionStart"].append(foreign_block)
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            before_doc = json.loads(target.read_text(encoding="utf-8"))
            before_counts = {event: len(blocks) for event, blocks in before_doc["hooks"].items()}
            self.assertFalse(
                any(block.get("_godmode") is True
                    for blocks in before_doc["hooks"].values() for block in blocks),
                "legacy writer must not have tagged anything")

            report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[UPDATE]"), report["lines"])
            after_doc = json.loads(target.read_text(encoding="utf-8"))
            after_counts = {event: len(blocks) for event, blocks in after_doc["hooks"].items()}
            self.assertEqual(before_counts, after_counts,
                              "adopting the legacy blocks must not duplicate them")

            session_start = after_doc["hooks"]["SessionStart"]
            self.assertIn(foreign_block, session_start,
                          "the foreign block sharing the adopted event must survive")
            tagged = [b for b in session_start if b.get("_godmode") is True]
            self.assertTrue(tagged, "the adopted legacy block must come back tagged")
            self.assertEqual(len(tagged), len(before_doc["hooks"]["SessionStart"]) - 1,
                              "every legacy block except the foreign one must be tagged")

            report2 = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertTrue(report2["lines"][0].startswith("[OK]"), report2["lines"])
            after_doc2 = json.loads(target.read_text(encoding="utf-8"))
            after_counts2 = {event: len(blocks) for event, blocks in after_doc2["hooks"].items()}
            self.assertEqual(before_counts, after_counts2)
            self.assertIn(foreign_block, after_doc2["hooks"]["SessionStart"],
                          "the foreign block must still survive a no-op re-run")

    def test_n5_the_written_event_order_is_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["codex"], dry_run=False, force=False)
            doc = json.loads(
                (project / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            events = list(doc["hooks"])
            self.assertEqual(events, sorted(events),
                              "N1: the written event order must be sorted, not "
                              "set-iteration order")

    def test_b4_legacy_antigravity_and_opencode_are_adopted_via_wire_all(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            HM.write_antigravity_project_hooks(W._PLUGIN_ROOT, project)
            HM.write_opencode_project_shim(W._PLUGIN_ROOT, project)
            status_before = W.wire_status(project)
            self.assertEqual(status_before["antigravity"], "drifted")
            self.assertEqual(status_before["opencode"], "drifted")

            report = W.wire(project, ["antigravity", "opencode"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(all(line.startswith("[UPDATE]") for line in report["lines"]),
                             report["lines"])

            status_after = W.wire_status(project)
            self.assertEqual(status_after["antigravity"], "in-sync")
            self.assertEqual(status_after["opencode"], "in-sync")

    def test_b4_a_genuinely_tampered_legacy_antigravity_file_still_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            HM.write_antigravity_project_hooks(W._PLUGIN_ROOT, project)
            target = project / ".agents" / "hooks.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["godmode"]["enabled"] = False  # tamper - no digest was ever recorded either
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, ["antigravity"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertTrue(report["lines"][0].startswith("[CONFLICT]"), report["lines"])
            self.assertEqual(W.wire_status(project)["antigravity"], "drifted")

    def test_b4_a_genuinely_tampered_legacy_opencode_file_still_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            HM.write_opencode_project_shim(W._PLUGIN_ROOT, project)
            target = project / ".opencode" / "plugins" / "godmode.js"
            target.write_text(target.read_text(encoding="utf-8") + "\n// tampered\n",
                               encoding="utf-8")

            report = W.wire(project, ["opencode"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertTrue(report["lines"][0].startswith("[CONFLICT]"), report["lines"])

    def test_a_new_codex_file_is_written_with_lf_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["codex"], dry_run=False, force=False)
            raw = (project / ".codex" / "hooks.json").read_bytes()
            self.assertIsNone(re.search(rb"\r\n", raw))

    def test_a_crlf_codex_file_stays_crlf_after_an_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            target = project / ".codex" / "hooks.json"
            content = json.dumps({"hooks": {}}, indent=2) + "\n"
            target.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))

            report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            raw = target.read_bytes()
            self.assertIsNone(re.search(rb"(?<!\r)\n", raw),
                               "every newline in a CRLF file must stay CRLF")

    def test_wire_catches_a_missing_source_artifact_instead_of_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            fake_root = Path(temp) / "fake-plugin-root"
            fake_root.mkdir()
            with mock.patch.object(W, "_PLUGIN_ROOT", fake_root):
                report = W.wire(project, ["opencode"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            # n1: an unreadable source is `invalid`, not a plain `conflict`,
            # and gets its own label.
            self.assertTrue(report["lines"][0].startswith("[INVALID]"), report["lines"])
            self.assertFalse((project / ".opencode").exists())

    def test_forcing_past_a_conflict_notes_it_was_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["antigravity"], dry_run=False, force=False)
            target = project / ".agents" / "hooks.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["godmode"]["enabled"] = False
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, ["antigravity"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[UPDATE]"), report["lines"])
            self.assertIn("forced over conflict", report["lines"][0])


class WireFixRound2Tests(unittest.TestCase):
    """Fix round 2 (`task-4-rereview.md` B5, B6): an off-shape (but
    parseable) codex `hooks` region is refused as `invalid`, never silently
    iterated and rewritten; and the codex digest verifies the region as
    stored on disk, not a reconstruction filtered through today's rendered
    event set."""

    def _assert_invalid_and_byte_identical(self, project: Path, before: bytes) -> None:
        target = project / ".codex" / "hooks.json"
        report = W.wire(project, ["codex"], dry_run=False, force=False)
        self.assertEqual(report["summary"], "blocked; no changes made")
        self.assertTrue(report["lines"][0].startswith("[INVALID]"), report["lines"])
        self.assertEqual(target.read_bytes(), before)

        # B5 is unforceable, same as B3: --force cannot clear it either.
        report_forced = W.wire(project, ["codex"], dry_run=False, force=True)
        self.assertEqual(report_forced["summary"], "blocked; no changes made")
        self.assertTrue(report_forced["lines"][0].startswith("[INVALID]"),
                        report_forced["lines"])
        self.assertEqual(target.read_bytes(), before)

    def test_b5_hooks_value_not_a_dict_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            content = json.dumps({"hooks": ["user", "data"], "keep": 1}, indent=2) + "\n"
            target = project / ".codex" / "hooks.json"
            target.write_text(content, encoding="utf-8")
            self._assert_invalid_and_byte_identical(project, target.read_bytes())

    def test_b5_event_value_a_string_not_a_list_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            content = json.dumps({"hooks": {"MyEvent": "python custom.py"}}, indent=2) + "\n"
            target = project / ".codex" / "hooks.json"
            target.write_text(content, encoding="utf-8")
            self._assert_invalid_and_byte_identical(project, target.read_bytes())

    def test_b5_event_value_a_dict_not_a_list_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            content = json.dumps(
                {"hooks": {"MyEvent": {"matcher": "*", "hooks": []}}}, indent=2) + "\n"
            target = project / ".codex" / "hooks.json"
            target.write_text(content, encoding="utf-8")
            self._assert_invalid_and_byte_identical(project, target.read_bytes())

    def test_b5_a_known_events_value_a_dict_not_a_list_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            content = json.dumps(
                {"hooks": {"Stop": {"matcher": "*", "hooks": []}}}, indent=2) + "\n"
            target = project / ".codex" / "hooks.json"
            target.write_text(content, encoding="utf-8")
            self._assert_invalid_and_byte_identical(project, target.read_bytes())

    def test_b5_block_entries_not_dicts_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".codex").mkdir(parents=True)
            content = json.dumps({"hooks": {"Stop": ["not-a-dict"]}}, indent=2) + "\n"
            target = project / ".codex" / "hooks.json"
            target.write_text(content, encoding="utf-8")
            self._assert_invalid_and_byte_identical(project, target.read_bytes())

    def test_b6_a_renderer_event_added_reads_as_update_not_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["codex"], dry_run=False, force=False)
            original = HM.codex_project_hooks

            def with_extra_event(root):
                doc = original(root)
                doc = {"hooks": dict(doc["hooks"])}
                doc["hooks"]["NewEvent"] = [
                    {"hooks": [{"type": "command", "command": "echo new"}]}]
                return doc

            with mock.patch.object(HM, "codex_project_hooks", side_effect=with_extra_event):
                report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[UPDATE]"), report["lines"])

    def test_b6_a_renderer_event_removed_reads_as_update_not_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["codex"], dry_run=False, force=False)
            original = HM.codex_project_hooks

            def without_stop_event(root):
                doc = original(root)
                return {"hooks": {k: v for k, v in doc["hooks"].items() if k != "Stop"}}

            with mock.patch.object(HM, "codex_project_hooks", side_effect=without_stop_event):
                report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[UPDATE]"), report["lines"])

    def test_b6_an_unchanged_render_still_reads_ok_after_a_clean_apply(self) -> None:
        # Sanity companion to the two probes above: with no renderer change
        # at all, a second wire must still be a no-op - the B6 fix (region
        # built from events present on disk) must not turn every ordinary
        # rerun into a spurious update.
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["codex"], dry_run=False, force=False)
            report = W.wire(project, ["codex"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[OK]"), report["lines"])


class CopilotAndKiroWireTests(unittest.TestCase):
    """NS-6 (Task 6): Copilot's `.github/hooks/godmode.json` uses the JSON
    owned-key strategy (the whole `"hooks"` region is godmode's own, a
    foreign top-level key survives), its `.github/copilot-instructions.md`
    block uses the literal `merge_text_block()` text-marker primitive, and
    Kiro's `.kiro/hooks.json` uses the array-tag strategy (`"_godmode":
    true` per rule block), mirroring Codex's own adoption/conflict rules."""

    def test_copilot_creates_both_files_and_reports_one_combined_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            report = W.wire(project, ["copilot"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[CREATE]"), report["lines"])
            self.assertTrue((project / ".github" / "hooks" / "godmode.json").is_file())
            self.assertTrue((project / ".github" / "copilot-instructions.md").is_file())
            self.assertEqual(W.wire_status(project)["copilot"], "in-sync")

    def test_copilot_foreign_top_level_key_in_hooks_json_survives_a_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".github" / "hooks").mkdir(parents=True)
            (project / ".github" / "hooks" / "godmode.json").write_text(
                json.dumps({"someOtherTool": {"enabled": True}}, indent=2) + "\n",
                encoding="utf-8")
            W.wire(project, ["copilot"], dry_run=False, force=False)
            doc = json.loads(
                (project / ".github" / "hooks" / "godmode.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["someOtherTool"], {"enabled": True})
            self.assertIn("hooks", doc)

    def test_copilot_foreign_content_in_instructions_md_survives_a_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".github").mkdir(parents=True)
            (project / ".github" / "copilot-instructions.md").write_text(
                "# Project instructions\n\nHand-authored content.\n", encoding="utf-8")
            W.wire(project, ["copilot"], dry_run=False, force=False)
            text = (project / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
            self.assertIn("Hand-authored content.", text)
            self.assertIn(W.BEGIN_MARKER, text)
            self.assertIn("godmode_gate_fast.py", text)

    def test_copilot_a_hand_edit_inside_the_hooks_json_owned_key_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["copilot"], dry_run=False, force=False)
            target = project / ".github" / "hooks" / "godmode.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["hooks"]["PreToolUse"] = []  # tamper without recomputing the digest
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, ["copilot"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertTrue(report["lines"][0].startswith("[CONFLICT]"), report["lines"])
            self.assertEqual(W.wire_status(project)["copilot"], "drifted")

    def test_copilot_a_hand_edit_inside_the_instructions_block_is_a_conflict_without_force(
            self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["copilot"], dry_run=False, force=False)
            target = project / ".github" / "copilot-instructions.md"
            before = target.read_bytes()
            tampered = target.read_text(encoding="utf-8").replace(
                "godmode_gate_fast.py", "some-other-script.py")
            target.write_text(tampered, encoding="utf-8")
            tampered_bytes = target.read_bytes()

            report = W.wire(project, ["copilot"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertTrue(report["lines"][0].startswith("[CONFLICT]"), report["lines"])
            # B1: a conflict without --force changes nothing - byte-identical
            # to the hand-edited file on disk, not silently reverted.
            self.assertEqual(target.read_bytes(), tampered_bytes)
            self.assertNotEqual(target.read_bytes(), before)
            self.assertEqual(W.wire_status(project)["copilot"], "drifted")

    def test_copilot_force_over_a_conflicted_instructions_block_restores_it(self) -> None:
        """B1: `--force` over a conflicted `copilot-instructions.md` block
        used to report success while leaving the drift on disk (the writer
        wrote back `merge_text_block`'s own unchanged-on-conflict return
        value). It must genuinely overwrite the block, the same way every
        other host's force already does, while everything outside the
        block - a hand-authored preamble - survives byte-for-byte."""
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".github").mkdir(parents=True)
            target = project / ".github" / "copilot-instructions.md"
            target.write_text("# Project instructions\n\nHand-authored preamble.\n",
                              encoding="utf-8")
            W.wire(project, ["copilot"], dry_run=False, force=False)
            tampered = target.read_text(encoding="utf-8").replace(
                "godmode_gate_fast.py", "some-other-script.py")
            target.write_text(tampered, encoding="utf-8")

            report = W.wire(project, ["copilot"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertIn("(forced over conflict)", report["lines"][0])

            restored = target.read_text(encoding="utf-8")
            self.assertIn("godmode_gate_fast.py", restored)
            self.assertNotIn("some-other-script.py", restored)
            self.assertIn("Hand-authored preamble.", restored)
            self.assertEqual(W.wire_status(project)["copilot"], "in-sync")

    def test_copilot_malformed_hooks_json_is_unforceable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".github" / "hooks").mkdir(parents=True)
            target = project / ".github" / "hooks" / "godmode.json"
            target.write_text("{not valid json", encoding="utf-8")
            before = target.read_bytes()
            report = W.wire(project, ["copilot"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(report["lines"][0].startswith("[INVALID]"), report["lines"])

    def test_kiro_creates_the_file_and_routes_through_the_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            report = W.wire(project, ["kiro"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "safe to apply")
            self.assertTrue(report["lines"][0].startswith("[CREATE]"), report["lines"])
            doc = json.loads(
                (project / ".kiro" / "hooks.json").read_text(encoding="utf-8"))
            command = doc["hooks"]["toolCall"][0]["hooks"][0]["command"]
            self.assertIn("run-hook.cmd", command)
            self.assertIn("godmode_gate_fast.py", command)
            self.assertNotIn(HM.KIRO_ROOT_TOKEN, command)
            self.assertEqual(W.wire_status(project)["kiro"], "in-sync")

    def test_kiro_foreign_rule_blocks_survive_a_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".kiro").mkdir(parents=True)
            (project / ".kiro" / "hooks.json").write_text(json.dumps({
                "hooks": {"toolCall": [{"hooks": [
                    {"type": "command", "command": "echo user-owned"}]}]}
            }, indent=2) + "\n", encoding="utf-8")
            W.wire(project, ["kiro"], dry_run=False, force=False)
            doc = json.loads((project / ".kiro" / "hooks.json").read_text(encoding="utf-8"))
            commands = [entry["command"] for block in doc["hooks"]["toolCall"]
                        for entry in block["hooks"]]
            self.assertIn("echo user-owned", commands)
            tagged_blocks = [b for b in doc["hooks"]["toolCall"] if b.get("_godmode") is True]
            self.assertTrue(tagged_blocks)

    def test_kiro_a_hand_edit_inside_the_tagged_block_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            W.wire(project, ["kiro"], dry_run=False, force=False)
            target = project / ".kiro" / "hooks.json"
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["hooks"]["toolCall"][0]["hooks"][0]["command"] = "echo tampered"
            target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            report = W.wire(project, ["kiro"], dry_run=False, force=False)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertTrue(report["lines"][0].startswith("[CONFLICT]"), report["lines"])
            self.assertEqual(W.wire_status(project)["kiro"], "drifted")

    def test_kiro_malformed_hooks_json_is_unforceable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".kiro").mkdir(parents=True)
            target = project / ".kiro" / "hooks.json"
            target.write_text("{not valid json", encoding="utf-8")
            before = target.read_bytes()
            report = W.wire(project, ["kiro"], dry_run=False, force=True)
            self.assertEqual(report["summary"], "blocked; no changes made")
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(report["lines"][0].startswith("[INVALID]"), report["lines"])

    def test_both_hosts_are_registered_through_godmode_wire_not_a_dedicated_writer(self) -> None:
        """NS-6's own instruction: copilot/kiro route "through godmode_wire" -
        `cmd_hooks`'s explicit `--host copilot`/`--host kiro` branch has no
        dedicated `write_*_project_*` function of its own, unlike codex/
        opencode/antigravity; it falls through to `godmode_wire.wire()`."""
        import argparse as _argparse
        from godmode_runtime.godmode_console import Runtime, cmd_hooks
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle

        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = _argparse.Namespace(hooks_command="wire", host="copilot",
                                           force=False, all=False, dry_run=False)
                result = cmd_hooks(args, runtime)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.payload["summary"], "safe to apply")
            self.assertTrue((project / ".github" / "hooks" / "godmode.json").is_file())


class MergeTextBlockTests(unittest.TestCase):
    """The literal `<!-- godmode:begin -->` / `<!-- godmode:end -->`
    primitive for a text/TOML shared config (NS-10a), exercised directly
    against a generic fixture body; `CopilotAndKiroWireTests` above proves
    it against its first real host target."""

    def test_a_fresh_empty_file_creates_the_block(self) -> None:
        merged, state = W.merge_text_block("", "GODMODE_VAR=1")
        self.assertEqual(state, "create")
        self.assertIn(W.BEGIN_MARKER, merged)
        self.assertIn(W.END_MARKER, merged)
        self.assertIn("GODMODE_VAR=1", merged)

    def test_a_user_owned_line_outside_the_markers_survives(self) -> None:
        existing = "export USER_VAR=hello\n"
        merged, state = W.merge_text_block(existing, "GODMODE_VAR=1")
        self.assertEqual(state, "update")
        self.assertTrue(merged.startswith(existing))
        merged_again, state_again = W.merge_text_block(merged, "GODMODE_VAR=1")
        self.assertEqual(state_again, "ok")
        self.assertEqual(merged_again, merged)
        self.assertIn("export USER_VAR=hello", merged_again)

    def test_merging_twice_is_byte_identical(self) -> None:
        merged, _ = W.merge_text_block("preamble\n", "GODMODE_VAR=1")
        merged_twice, state = W.merge_text_block(merged, "GODMODE_VAR=1")
        self.assertEqual(state, "ok")
        self.assertEqual(merged, merged_twice)

    def test_a_hand_edit_inside_the_block_is_a_conflict(self) -> None:
        merged, _ = W.merge_text_block("preamble\n", "GODMODE_VAR=1")
        tampered = merged.replace("GODMODE_VAR=1", "GODMODE_VAR=HACKED")
        result, state = W.merge_text_block(tampered, "GODMODE_VAR=1")
        self.assertEqual(state, "conflict")
        self.assertEqual(result, tampered)  # refused: nothing changes

    def test_content_after_the_block_also_survives_an_update(self) -> None:
        merged, _ = W.merge_text_block("preamble\n", "GODMODE_VAR=1")
        with_trailer = merged + "trailing user content\n"
        result, state = W.merge_text_block(with_trailer, "GODMODE_VAR=2")
        self.assertEqual(state, "update")
        self.assertIn("preamble", result)
        self.assertIn("trailing user content", result)
        self.assertIn("GODMODE_VAR=2", result)

    def test_n7_a_crlf_existing_file_stamps_the_new_block_in_crlf(self) -> None:
        existing = "preamble\r\nmore preamble\r\n"
        merged, state = W.merge_text_block(existing, "GODMODE_VAR=1")
        self.assertEqual(state, "update")
        self.assertTrue(merged.startswith(existing))
        # Every newline, inside the stamped block and outside it, is CRLF -
        # no mixed endings introduced by the merge.
        self.assertIsNone(re.search(r"(?<!\r)\n", merged), merged)

    def test_n7_a_crlf_existing_block_updates_and_stays_crlf(self) -> None:
        merged, _ = W.merge_text_block("preamble\r\n", "GODMODE_VAR=1")
        self.assertIsNone(re.search(r"(?<!\r)\n", merged), merged)
        updated, state = W.merge_text_block(merged, "GODMODE_VAR=2")
        self.assertEqual(state, "update")
        self.assertIsNone(re.search(r"(?<!\r)\n", updated), updated)
        self.assertIn("GODMODE_VAR=2", updated)


class HooksWireAllCommandTests(unittest.TestCase):
    """`godmode hooks wire --all [--dry-run]` through `cmd_hooks`."""

    def _runtime(self, project: Path) -> Runtime:
        anchor = resolve_anchor(project)
        archive = Chronicle(anchor)
        archive.initialize()
        return Runtime(anchor=anchor, archive=archive)

    def test_wire_all_creates_every_host_and_reports_safe_to_apply(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                          all=True, dry_run=False)
                result = cmd_hooks(args, runtime)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.payload["summary"], "safe to apply")
            self.assertTrue((project / ".codex" / "hooks.json").exists())
            self.assertTrue((project / ".agents" / "hooks.json").exists())
            self.assertTrue((project / ".opencode" / "plugins" / "godmode.js").exists())

    def test_wire_all_dry_run_leaves_the_tree_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            (project / "keepme.txt").write_text("do not touch\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                before = _digests(project)
                args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                          all=True, dry_run=True)
                result = cmd_hooks(args, runtime)
                after = _digests(project)
            self.assertEqual(before, after)
            self.assertEqual(result.payload["summary"], "safe to apply")
            self.assertTrue(all(line.startswith("[CREATE]") for line in result.payload["lines"]))

    def test_hooks_status_reports_wire_state_per_host(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                wire_args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                               all=True, dry_run=False)
                cmd_hooks(wire_args, runtime)
                status_args = argparse.Namespace(hooks_command="status", host="claude", git=False)
                result = cmd_hooks(status_args, runtime)
            self.assertIn("wire_state", result.payload)
            for host in W.WIRE_HOSTS:
                self.assertEqual(result.payload["wire_state"][host], "in-sync")

    def test_hooks_status_reports_absent_before_any_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                status_args = argparse.Namespace(hooks_command="status", host="claude", git=False)
                result = cmd_hooks(status_args, runtime)
            for host in W.WIRE_HOSTS:
                self.assertEqual(result.payload["wire_state"][host], "absent")

    def test_n6_all_with_an_explicit_host_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                args = argparse.Namespace(hooks_command="wire", host="codex", force=False,
                                          all=True, dry_run=False)
                result = cmd_hooks(args, runtime)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("error", result.payload)
            self.assertFalse((project / ".codex").exists())
            self.assertFalse((project / ".agents").exists())
            self.assertFalse((project / ".opencode").exists())

    def test_n7_dry_run_with_an_unknown_host_gives_the_friendly_message(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                runtime = self._runtime(project)
                args = argparse.Namespace(hooks_command="wire", host="grok", force=False,
                                          all=False, dry_run=True)
                result = cmd_hooks(args, runtime)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("hooks wire knows codex", result.payload.get("error", ""))


class CodexLinkedWorktreeRefusalUnderWireAllTests(unittest.TestCase):
    """N-13's refusal must still fire when codex is only one of several
    hosts `--all` would otherwise wire - a real `git worktree add`, like
    `tests/test_codex_premise.py`, not a mocked anchor."""

    def test_wire_all_refuses_from_a_real_linked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)
            worktree = base / "linked"
            _run_git(["worktree", "add", str(worktree), "-b", "wt-branch"], primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(worktree)
                self.assertTrue(is_linked_worktree(anchor))
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                          all=True, dry_run=False)
                result = cmd_hooks(args, runtime)

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.payload["host"], "codex")
            self.assertFalse((worktree / ".codex").exists())
            # The refusal blocks the WHOLE batch, not only codex.
            self.assertFalse((worktree / ".agents").exists())
            self.assertFalse((worktree / ".opencode").exists())

    def test_wire_all_dry_run_also_refuses_from_a_linked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)
            worktree = base / "linked"
            _run_git(["worktree", "add", str(worktree), "-b", "wt-branch"], primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(worktree)
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                          all=True, dry_run=True)
                result = cmd_hooks(args, runtime)

            self.assertEqual(result.exit_code, 2)
            self.assertFalse((worktree / ".codex").exists())

    def test_wire_all_passes_from_the_primary_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(primary)
                self.assertFalse(is_linked_worktree(anchor))
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host=None, force=False,
                                          all=True, dry_run=False)
                result = cmd_hooks(args, runtime)

            self.assertEqual(result.exit_code, 0)
            self.assertTrue((primary / ".codex" / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()

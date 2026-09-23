"""C-12 + N-5: per-section brief caps, a named trim, and three-zone text.

The session brief is held to a cap per section (records, laws, next
actions, issues) and says in `trimmed` how many entries each section lost,
so a short section is never read as a short history. The brief and the Stop
boundary's block messages share one layout, built by one renderer: the rule
on the first line, the detail in the middle, a closing checklist last.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
for entry in (SCRIPTS, PLUGIN_ROOT, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_lens import (  # noqa: E402
    BRIEF_SECTION_CAPS,
    SESSION_BRIEF_TOKENS,
    build_context_brief,
    cap_brief_sections,
    fit_brief,
    render_three_zone,
)

from _host_env import scrubbed_env, scrubbed_environment  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"


def _zones(text: str) -> tuple[str, str, list[str]]:
    """Split a three-zone message into (rule, detail, checklist items)."""
    rule, _, rest = text.partition("\n")
    detail, marker, checklist = rest.partition("Checklist:\n")
    items = [line[2:] for line in checklist.splitlines() if line.startswith("- ")]
    return rule, detail.strip("\n"), items if marker else []


class TheRenderer(unittest.TestCase):
    def test_rule_first_detail_middle_checklist_last(self) -> None:
        text = render_three_zone("Rule here.", "detail line", ["first", "second"])
        self.assertEqual(text, "Rule here.\ndetail line\nChecklist:\n- first\n- second")

    def test_the_rule_is_always_one_line(self) -> None:
        text = render_three_zone("a rule\nthat wrapped\n", "d", ["x"])
        self.assertEqual(text.splitlines()[0], "a rule that wrapped")

    def test_an_empty_zone_is_left_out(self) -> None:
        self.assertEqual(render_three_zone("R.", "", []), "R.")
        self.assertEqual(render_three_zone("R.", "", ["c"]), "R.\nChecklist:\n- c")


class SectionCaps(unittest.TestCase):
    def test_the_caps_are_the_declared_ones(self) -> None:
        self.assertEqual(BRIEF_SECTION_CAPS,
                         {"records": 24, "laws": 8, "next_actions": 6, "issues": 10})

    def test_each_section_is_held_to_its_cap_and_the_trim_is_named(self) -> None:
        brief = {
            "records": [{"sequence": n} for n in range(30)],
            "laws": [f"law {n}" for n in range(9)],
            "next_actions": [f"do {n}" for n in range(10)],
            "issues": [{"kind": n} for n in range(10)],
        }
        cap_brief_sections(brief)
        self.assertEqual(len(brief["records"]), 24)
        self.assertEqual(brief["records"][0], {"sequence": 6}, "records keep the newest")
        self.assertEqual(brief["laws"], [f"law {n}" for n in range(8)])
        self.assertEqual(brief["next_actions"], [f"do {n}" for n in range(6)])
        self.assertEqual(len(brief["issues"]), 10)
        self.assertEqual(brief["trimmed"], {"records": 6, "laws": 1, "next_actions": 4})

    def test_a_brief_within_its_caps_carries_no_trim(self) -> None:
        brief = {"records": [1, 2], "laws": {"compiled_rules": 0}}
        cap_brief_sections(brief)
        self.assertNotIn("trimmed", brief)

    def test_fit_drops_the_oldest_records_and_counts_them(self) -> None:
        brief = {"doctrine": "d" * 400,
                 "records": [{"sequence": n, "data": "x" * 200} for n in range(10)]}
        fit_brief(brief, budget_tokens=300)
        self.assertLessEqual(len(json.dumps(brief, separators=(",", ":"))) // 4, 300)
        kept = [r["sequence"] for r in brief["records"]]
        self.assertEqual(kept, list(range(10 - len(kept), 10)), "the newest records survive")
        self.assertEqual(brief["trimmed"]["records"], 10 - len(kept))

    def test_the_context_brief_names_its_ladder_drop(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for i in range(60):
                archive.append("decision", f"ruling-{i}",
                               {"status": "ruled", "detail": "d" * 120}, evidence=[])
            brief = build_context_brief(anchor, archive, token_budget=150)
            self.assertTrue(brief.get("records_dropped"))
            self.assertEqual(brief["trimmed"]["records"], brief["records_dropped"])


class TheSessionBriefIsThreeZones(unittest.TestCase):
    def _session_start(self, project: Path) -> str:
        observe = importlib.import_module("test_observe_mode")
        out = observe._session_start(project)
        return out["hookSpecificOutput"]["additionalContext"]

    def test_rule_json_checklist(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "midway", {"status": "active", "next": ["a"]},
                           evidence=[])
            context = self._session_start(project)
            rule, detail, checklist = _zones(context)
            self.assertTrue(rule.startswith("Godmode recovered this bounded"))
            brief = json.loads(detail)
            self.assertIn("records", brief)
            self.assertTrue(checklist)
            self.assertIn("godmode checkpoint", checklist[-1])

    def test_a_grown_archive_is_fitted_and_says_what_it_trimmed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            for i in range(60):
                archive.append("decision", f"ruling-{i}",
                               {"status": "ruled", "detail": "d" * 90}, evidence=[])
                archive.append("checkpoint", f"cp-{i}",
                               {"status": "ok", "next": "n" * 60}, evidence=[])
            context = self._session_start(project)
            _rule, detail, checklist = _zones(context)
            brief = json.loads(detail)
            self.assertTrue(brief["trimmed"]["records"])
            within = len(detail) // 4 <= SESSION_BRIEF_TOKENS
            self.assertTrue(within or not brief["records"],
                            "records remain while the brief is over its budget")
            self.assertTrue(any("trimmed" in item for item in checklist))


class TheStopBlockIsThreeZones(unittest.TestCase):
    def test_the_done_bar_reads_rule_detail_checklist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-zones-") as name:
            base = Path(name)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with scrubbed_environment(GODMODE_STATE_HOME=str(state)):
                Chronicle(resolve_anchor(project)).initialize()
            transcript = project / "transcript.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "do it"}}),
                json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "text",
                     "text": "All wrapped up. The migration is complete and all tests pass."}]}}),
            ]), encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(HOOK), "stop", "--project", str(project)],
                input=json.dumps({"transcript_path": str(transcript)}),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180, env=scrubbed_env(GODMODE_STATE_HOME=str(state)))
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "block")
            rule, detail, checklist = _zones(payload["reason"])
            self.assertIn("THE DONE BAR", rule)
            self.assertTrue(detail.startswith("Unbacked: "))
            self.assertIn("--verify", checklist[0])
            self.assertIn("blocks only once", checklist[-1])


if __name__ == "__main__":
    unittest.main()

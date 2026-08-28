"""S6: the three field-report gaps close (obligations 4435, 4436, 4482).

4435: a standing instruction lands in the archive on FIRST telling - the
correction detector only ever caught the second - and promotes after one
session, because an explicit directive outranks an inferred correction.
4436: three runtimes shared one archive and raced its chain; doctor --deep
now names every cached install whose version differs from the running one.
4482: a reversal and a withdrawal both came from hand-reading a test file;
`context why` now answers "which tests name this symbol" directly.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    law_candidates, record_correction_candidate, record_instruction_candidate,
)


class InstructionCandidateTests(unittest.TestCase):
    PROMPT = "always include the godmode feedback section in every report"

    def test_a_standing_instruction_becomes_a_candidate_on_first_telling(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_instruction_candidate(archive, self.PROMPT, session="S-1")
        self.assertIsNotNone(record)
        self.assertEqual(record["data"]["origin"], "instruction")
        self.assertEqual(record["data"]["status"], "candidate")
        # Keywords and digest only - never the sentence.
        self.assertNotIn(self.PROMPT, str(record["data"].get("value", "")))
        self.assertNotIn(self.PROMPT, record["subject"])

    def test_an_ordinary_prompt_is_ignored(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_instruction_candidate(
                archive, "fix the failing parser test", session="S-1")
        self.assertIsNone(record)

    def test_an_instruction_cluster_promotes_after_one_session(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_instruction_candidate(archive, self.PROMPT, session="S-1")
            clusters = law_candidates(archive)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["origin"], "instruction")
        self.assertTrue(clusters[0]["promotable"])

    def test_a_correction_cluster_still_needs_three_sessions(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_correction_candidate(
                archive, "wrong again, you missed the same check", session="S-1")
            clusters = law_candidates(archive)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["origin"], "correction")
        self.assertFalse(clusters[0]["promotable"])

    def test_the_prompt_boundary_fires_the_detector(self) -> None:
        # Wiring pin: the hook source calls the detector beside the
        # correction detector - a capability an agent must volunteer is
        # unbuilt until a boundary fires it.
        source = (PLUGIN_ROOT / "hooks" / "godmode_session_hook.py").read_text(
            encoding="utf-8")
        self.assertIn("record_instruction_candidate(", source)


class RuntimeCensusTests(unittest.TestCase):
    def _fake_home(self, base: Path, versions: dict[str, str]) -> None:
        for label, version in versions.items():
            constants = (base / ".claude" / "plugins" / "cache" / "aiimagined"
                         / "godmode" / label / "scripts" / "godmode_runtime"
                         / "godmode_constants.py")
            constants.parent.mkdir(parents=True, exist_ok=True)
            constants.write_text(
                f'RUNTIME_VERSION = "{version}"\n', encoding="utf-8")

    def test_census_lists_every_cached_install(self) -> None:
        import tempfile
        from godmode_runtime.godmode_host_manifests import runtime_census

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._fake_home(home, {"0.3.0": "0.3.0", "0.3.1": "0.3.1"})
            installs = runtime_census(home)
        self.assertEqual(sorted(i["version"] for i in installs),
                         ["0.3.0", "0.3.1"])

    def test_only_a_differing_version_raises_an_issue(self) -> None:
        import tempfile
        from godmode_runtime.godmode_host_manifests import runtime_census_issues

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._fake_home(home, {"0.3.0": "0.3.0", "0.3.1": "0.3.1"})
            issues = runtime_census_issues("0.3.1", home)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "stale-runtime-cache")
        self.assertIn("0.3.0", issues[0]["detail"])

    def test_an_empty_home_is_quiet(self) -> None:
        import tempfile
        from godmode_runtime.godmode_host_manifests import runtime_census_issues

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(runtime_census_issues("0.3.1", Path(tmp)), [])


class WhyGuardsTests(unittest.TestCase):
    def test_why_names_the_tests_citing_a_symbol(self) -> None:
        from godmode_runtime.godmode_lens import why

        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            tests = project / "tests"
            tests.mkdir()
            (tests / "test_frob.py").write_text(
                "# pins frobnicate: the missing branch is deliberate\n",
                encoding="utf-8")
            answer = why(anchor, archive, "frobnicate")
        self.assertEqual(answer["guards"]["symbol"], "frobnicate")
        self.assertIn("tests/test_frob.py", answer["guards"]["tests_naming"])
        self.assertIn("pin", answer["guards"]["note"])

    def test_an_unnamed_symbol_reports_no_pin_honestly(self) -> None:
        from godmode_runtime.godmode_lens import why

        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            answer = why(anchor, archive, "unnamedthing")
        self.assertEqual(answer["guards"]["tests_naming"], [])
        self.assertIn("no test names this symbol", answer["guards"]["note"])


if __name__ == "__main__":
    unittest.main()

"""Dual-verdict absorption, push disclosure, and overwrite disclosure.

- upstream_verdicts: "N/A - different surface" answers CAN WE IMPORT IT,
  never HAVE THEY SOLVED A PROBLEM WE ALSO HAVE; every enumerated item owes
  an import verdict AND a behaviour verdict, and confirmed-* needs its
  proving line (L-288/L-289/L-308).
- push disclosure: a push to a deploy-wired branch IS a deploy action; the
  approver must see the automation's name beside the push (L-69/L-322).
- overwrite disclosure: writing a "new" file onto an existing filename is an
  overwrite bet; the impact names it (L-314 #2).
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_parity import upstream_verdicts  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class UpstreamVerdictTests(unittest.TestCase):
    def test_an_unrecorded_item_is_unread(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            report = upstream_verdicts(archive, ["0.7.108-fix-audio-mux"])
        self.assertEqual(report["unread"], ["0.7.108-fix-audio-mux"])
        self.assertEqual(report["verdict"], "absorption-open")

    def test_an_import_only_verdict_is_half(self) -> None:
        # The L-289 defect verbatim: n-a on importability, silence on whether
        # the same bug lives in our reimplementation.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "absorb:0.7.108-fix-audio-mux",
                           {"import_verdict": "n-a"}, evidence=[])
            report = upstream_verdicts(archive, ["0.7.108-fix-audio-mux"])
        self.assertEqual(len(report["half_verdicted"]), 1)
        self.assertIn("behaviour verdict",
                      report["half_verdicted"][0]["problems"][0])

    def test_a_confirmed_behaviour_without_a_proving_line_is_half(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "absorb:0.7.108-fix-audio-mux",
                           {"import_verdict": "n-a",
                            "behaviour_verdict": "confirmed-dont"}, evidence=[])
            report = upstream_verdicts(archive, ["0.7.108-fix-audio-mux"])
        self.assertEqual(len(report["half_verdicted"]), 1)
        self.assertIn("proving line", report["half_verdicted"][0]["problems"][0])

    def test_a_full_verdict_with_proof_closes_the_item(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "absorb:0.7.108-fix-audio-mux",
                           {"import_verdict": "n-a",
                            "behaviour_verdict": "confirmed-dont"},
                           evidence=["file:lib/audio_mux.py"])
            report = upstream_verdicts(archive, ["0.7.108-fix-audio-mux"])
        self.assertEqual(report["verdict"], "absorbed")

    def test_a_qualified_import_verdict_is_read_by_its_leading_token(self) -> None:
        # The sweep writes the reason beside the verdict - "n-a - different
        # surface (postgres table)", "skip (FAISS dependency)", "adopt -
        # candidate, not built". The verdict is the leading token; the rest
        # is why, and must not turn a full verdict into a half one.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for item, verdict in (("a", "n-a - different surface (postgres table)"),
                                  ("b", "skip (FAISS/BGE dependencies)"),
                                  ("c", "adopt - candidate, not built")):
                archive.append("decision", f"absorb:{item}",
                               {"import_verdict": verdict,
                                "behaviour_verdict": "unverified"}, evidence=[])
            report = upstream_verdicts(archive, ["a", "b", "c"])
        self.assertEqual(report["verdict"], "absorbed", report["half_verdicted"])
        self.assertEqual([e["import_verdict"] for e in report["verdicted"]],
                         ["n-a", "skip", "adopt"])

    def test_an_honest_unverified_needs_no_proof(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "absorb:0.7.109-shader-default",
                           {"import_verdict": "skip",
                            "behaviour_verdict": "unverified"}, evidence=[])
            report = upstream_verdicts(archive, ["0.7.109-shader-default"])
        self.assertEqual(report["verdict"], "absorbed")


class PushDisclosureTests(unittest.TestCase):
    def test_a_push_names_its_wired_workflow(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            workflows = project / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "deploy.yml").write_text(
                "on:\n  push:\n    branches: [main]\njobs: {}\n",
                encoding="utf-8")
            verdict = classify_action("git push origin main",
                                      project_root=project)
        joined = " ".join(verdict["impact"])
        self.assertIn("deploy.yml", joined)
        self.assertIn("push-triggered automation", joined)

    def test_a_push_with_no_wired_workflow_stays_plain(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            verdict = classify_action("git push origin main",
                                      project_root=project)
        self.assertNotIn("push-triggered automation",
                         " ".join(verdict["impact"]))

    def test_a_manual_only_workflow_is_not_named(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            workflows = project / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "manual.yml").write_text(
                "on:\n  workflow_dispatch: {}\njobs: {}\n", encoding="utf-8")
            verdict = classify_action("git push origin main",
                                      project_root=project)
        self.assertNotIn("manual.yml", " ".join(verdict["impact"]))


class OverwriteDisclosureTests(unittest.TestCase):
    def test_writing_onto_an_existing_file_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            existing = project / "module.py"
            existing.write_text("original = True\n", encoding="utf-8")
            verdict = classify_action(f"Write file {existing}",
                                      project_root=project)
        self.assertIn("OVERWRITES", " ".join(verdict["impact"]))
        self.assertFalse(verdict["protected"])

    def test_writing_a_genuinely_new_file_is_plain(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            verdict = classify_action(f"Write file {project / 'fresh.py'}",
                                      project_root=project)
        self.assertNotIn("OVERWRITES", " ".join(verdict["impact"]))


if __name__ == "__main__":
    unittest.main()

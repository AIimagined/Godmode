"""M22 class-claim sweeps and guard-citation resolution.

- M22: a fix that says "every caller" and diffs one file made the user the
  sweep, five recurrences in one recorded session (L-201/L-253/L-257/L-278).
- guard_citations_resolve: a registry index missing 43 shipped fixes let two
  of them be extended blind; a guard citing a deleted path is a fix that can
  silently revert (L-133/L-247, checklist rows 174/252). Drift is reported
  in BOTH directions - dead citation and guard-with-no-anchor.

Planted violation seen red, innocent form seen green, per detector.
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

from godmode_runtime.godmode_mistakes import class_claim_single_file  # noqa: E402
from godmode_runtime.godmode_reconcile import guard_citations_resolve  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _change(sequence: int, subject: str, files: list[str],
            evidence: list[str] | None = None, plan: str = "") -> dict:
    return {
        "kind": "change", "sequence": sequence, "subject": subject,
        "data": {"files": files, "plan": plan},
        "evidence": evidence or [],
    }


class ClassClaimTests(unittest.TestCase):
    def test_an_every_caller_fix_on_one_file_is_reported(self) -> None:
        findings = class_claim_single_file([
            _change(1, "guard every caller of resolveDir", ["lib/serve.py"])])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["detector"], "class-claim-single-file")

    def test_a_swept_single_file_fix_is_clean(self) -> None:
        findings = class_claim_single_file([
            _change(1, "guard every caller of resolveDir", ["lib/serve.py"],
                    evidence=["searched:rg resolveDir lib/ app/ -> 1 site"])])
        self.assertEqual(findings, [])

    def test_a_multi_file_class_fix_is_clean(self) -> None:
        findings = class_claim_single_file([
            _change(1, "guard every caller of resolveDir",
                    ["lib/serve.py", "lib/render.py", "app/api.py"])])
        self.assertEqual(findings, [])

    def test_an_instance_scoped_fix_is_clean(self) -> None:
        findings = class_claim_single_file([
            _change(1, "fix the serve-route resolver", ["lib/serve.py"])])
        self.assertEqual(findings, [])


class GuardCitationTests(unittest.TestCase):
    def test_a_dead_citation_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append(
                "invariant", "render QC fails closed",
                {"status": "active"},
                evidence=["file:tests/test_render_qc.py"])
            report = guard_citations_resolve(archive, project)
        self.assertEqual(report["verdict"], "guard-drift")
        self.assertEqual(report["dead_citations"][0]["path"],
                         "tests/test_render_qc.py")

    def test_a_resolving_citation_is_clean(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            guard = project / "tests" / "test_render_qc.py"
            guard.parent.mkdir(parents=True, exist_ok=True)
            guard.write_text("def test_qc(): assert True\n", encoding="utf-8")
            archive.append(
                "invariant", "render QC fails closed",
                {"status": "active"},
                evidence=["file:tests/test_render_qc.py"])
            report = guard_citations_resolve(archive, project)
        self.assertEqual(report["verdict"], "resolved")

    def test_a_guard_lesson_with_no_anchor_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append(
                "lesson", "always strip dead refs on the edit lane",
                {"status": "active", "generalized_guard": True}, evidence=[])
            report = guard_citations_resolve(archive, project)
        self.assertEqual(len(report["unanchored_guards"]), 1)

    def test_a_plain_lesson_without_guard_flag_is_ignored(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append(
                "lesson", "the vendor CLI resyncs skills on any run",
                {"status": "active"}, evidence=[])
            report = guard_citations_resolve(archive, project)
        self.assertEqual(report["checked"], 0)
        self.assertEqual(report["verdict"], "resolved")


if __name__ == "__main__":
    unittest.main()

"""The look of the product, which an agent may not quietly redraw.

The scope fence is task-scoped: this change may touch these files, and the
claim expires with the plan. A design boundary is the opposite shape. It
outlives every plan, nobody re-declares it per task, and the thing it protects
is not correctness but a decision somebody made on purpose — so it lives in
configuration and it refuses rather than asks.

Enforcement reads declared globs only. A heuristic may propose them and never
decide them: auto-detection would freeze a `.tsx` file that is pure server-side
data loading, miss a UI change made in a plain route file, and silently move
its own scope when somebody adds an import — so yesterday's allowed edit
becomes today's refusal with no diff to explain it. A gate whose scope moves on
its own cannot be audited, and this project issues explicit scoped capabilities
everywhere else rather than inferring intent.

Undeclared means unenforced, and `doctor` says so. That is what stops
fail-open from rotting into nobody noticing.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_fence import (  # noqa: E402
    BOUNDARY_CONFIG, declared_design, design_verdict, propose_design,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _write_boundary(project: Path, declared, excepted=None) -> None:
    payload = {"ui": {"declared": list(declared)}}
    if excepted is not None:
        payload["ui"]["except"] = list(excepted)
    (project / BOUNDARY_CONFIG).write_text(json.dumps(payload), encoding="utf-8")


class DeclarationTests(unittest.TestCase):
    def test_no_config_means_no_boundary(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            self.assertIsNone(declared_design(project))

    def test_declared_globs_are_read_back(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**", "**/*.css"])
            self.assertEqual(declared_design(project)["declared"],
                             ["src/components/**", "**/*.css"])

    def test_an_empty_declaration_is_not_a_boundary(self) -> None:
        """An empty list is somebody having started and not finished. Treating
        it as a boundary would freeze nothing while reporting configured."""
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, [])
            self.assertIsNone(declared_design(project))

    def test_unreadable_config_is_not_silently_an_open_boundary(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / BOUNDARY_CONFIG).write_text("{not json", encoding="utf-8")
            with self.assertRaises(Exception):
                declared_design(project)


class VerdictTests(unittest.TestCase):
    def test_a_declared_design_file_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**"])
            verdict = design_verdict(project, "src/components/Button.tsx")
        self.assertFalse(verdict["allowed"])

    def test_a_file_outside_the_boundary_is_ordinary_work(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**"])
            verdict = design_verdict(project, "src/server/routes.ts")
        self.assertTrue(verdict["allowed"])

    def test_an_exception_carves_out_what_lives_inside_the_tree(self) -> None:
        """Tests and stories sit inside component trees, and freezing them
        blocks ordinary work that changes nothing anybody looks at."""
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**"],
                            ["src/components/**/*.test.tsx"])
            verdict = design_verdict(project, "src/components/Button.test.tsx")
        self.assertTrue(verdict["allowed"])

    def test_no_config_allows_and_names_itself_unconfigured(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            verdict = design_verdict(project, "src/components/Button.tsx")
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["boundary"], "unconfigured")

    def test_the_refusal_names_the_capability_that_unfreezes_it(self) -> None:
        """`run it yourself` is not an answer for a boundary the operator owns,
        and a refusal that names no remedy is the failure this project has
        already shipped once."""
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**"])
            verdict = design_verdict(project, "src/components/Button.tsx")
        self.assertIn("authorize stage", verdict["remedy"])

    def test_the_refusal_says_it_is_a_decision_not_a_defect(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _write_boundary(project, ["src/components/**"])
            verdict = design_verdict(project, "src/components/Button.tsx")
        self.assertIn("design", verdict["detail"])


class ProposalTests(unittest.TestCase):
    def test_the_proposer_finds_candidate_globs(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "src" / "components").mkdir(parents=True)
            (project / "src" / "components" / "Button.tsx").write_text("x", encoding="utf-8")
            (project / "src" / "server").mkdir(parents=True)
            (project / "src" / "server" / "routes.ts").write_text("x", encoding="utf-8")
            proposed = propose_design(project)
        self.assertIn("src/components/**", proposed)

    def test_the_proposer_does_not_claim_plain_typescript(self) -> None:
        """A `.ts` route file is not a design surface, and a proposer that
        swept it in would be trained out of by the first false freeze."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "src" / "server").mkdir(parents=True)
            (project / "src" / "server" / "routes.ts").write_text("x", encoding="utf-8")
            proposed = propose_design(project)
        self.assertEqual(proposed, [])

    def test_the_proposer_never_writes_the_config(self) -> None:
        """It proposes. A scope that installs itself is the auto-detection this
        boundary exists to refuse."""
        with isolated_project() as (project, _s, _a, _archive):
            (project / "src" / "components").mkdir(parents=True)
            (project / "src" / "components" / "Button.tsx").write_text("x", encoding="utf-8")
            propose_design(project)
            self.assertFalse((project / BOUNDARY_CONFIG).exists())


class RemedyTests(unittest.TestCase):
    """Every command these verdicts name has to run.

    Three separate defects fixed in this same session were all one shape: a
    mechanism that existed, a report that pointed at it, and using it changing
    nothing or erroring outright. Naming a fourth without checking would be
    careless rather than unlucky.
    """

    def test_the_proposer_the_unconfigured_verdict_names_is_a_real_command(self) -> None:
        from godmode_runtime.godmode_console import _build_parser

        parsed = _build_parser().parse_args(["boundaries", "propose-ui"])
        self.assertTrue(callable(parsed.handler))

    def test_the_proposer_runs_and_reports_candidates(self) -> None:
        from godmode_runtime.godmode_console import main

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "src" / "components").mkdir(parents=True)
            (project / "src" / "components" / "Button.tsx").write_text("x", encoding="utf-8")
            self.assertEqual(
                main(["--project", str(project), "boundaries", "propose-ui"]), 0)

    @staticmethod
    def _run(project: Path, *argv: str) -> dict:
        from godmode_runtime.godmode_console import main

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main(["--project", str(project), *argv])
        return json.loads(buffer.getvalue())

    def test_doctor_reports_a_project_with_no_declared_boundary(self) -> None:
        """Fails open on purpose — so the gap has to be visible somewhere, or
        it rots into nobody noticing, and a guard that governs nothing looks
        identical from the inside to one that governs everything."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            payload = self._run(project, "doctor")
        self.assertEqual(payload["design_boundary"], "unconfigured")

    def test_doctor_reports_a_declared_boundary_as_configured(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_boundary(project, ["src/components/**"])
            payload = self._run(project, "doctor")
        self.assertEqual(payload["design_boundary"], "declared")


class HookEnforcementTests(unittest.TestCase):
    HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"

    def _decide(self, project: Path, file_path: str) -> tuple[str, str]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": file_path},
            "cwd": str(project),
        }
        done = subprocess.run(
            [sys.executable, str(self.HOOK), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        )
        body = (done.stdout or "").strip()
        if not body:
            return "allow", ""
        specific = json.loads(body).get("hookSpecificOutput") or {}
        return (str(specific.get("permissionDecision", "?")),
                str(specific.get("permissionDecisionReason", "")))

    def test_a_design_edit_is_denied_not_merely_questioned(self) -> None:
        """The operator said this needs their permission. A one-key `ask` in
        the middle of a long agent run is not permission — it is the same
        keystroke as every other confirmation that session."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_boundary(project, ["src/components/**"])
            decision, reason = self._decide(
                project, str(project / "src" / "components" / "Button.tsx"))
        self.assertEqual(decision, "deny", reason)

    def test_a_project_with_no_boundary_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            decision, reason = self._decide(
                project, str(project / "src" / "components" / "Button.tsx"))
        self.assertEqual(decision, "allow", reason)


if __name__ == "__main__":
    unittest.main()

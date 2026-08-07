"""Every gate CI runs, run here, with the exit code actually checked.

CI went red on `untrusted` while the local battery reported it green. Two
mistakes made that possible, and this file exists so neither can repeat.

The first was methodological: the local check piped the command through `head`,
so `$?` reported the exit status of `head` — always zero. A verification that
cannot fail proves nothing, which is the failure mode this project exists to
catch, committed by its own author against its own product.

The second was structural: the workflow was the only place several gates ran,
so nothing local could have caught a regression in them. The gate list is now
read out of the workflow file itself, so a gate added to CI without a local
counterpart fails here rather than on a push.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PLUGIN_ROOT / ".github" / "workflows" / "godmode-verify.yml"

# Gates whose failure is a finding about the repository rather than a defect,
# and which therefore may legitimately exit non-zero here.
_REPORT_ONLY: frozenset[str] = frozenset()


def _workflow_gates() -> list[str]:
    """Every `godmode.py --project . <gate>` invocation the workflow runs."""
    text = WORKFLOW.read_text(encoding="utf-8")
    found: list[str] = []
    # Bounded to the line: a greedy match runs straight into the next YAML key.
    for match in re.finditer(
        r"godmode\.py\s+--project\s+\.\s+([^\n]+)", text
    ):
        # Cut at the first shell operator: a redirect belongs to the step, not
        # to the gate's argument list.
        gate = re.split(r"[>|;&]", match.group(1))[0]
        gate = " ".join(gate.split())
        if gate and gate not in found:
            found.append(gate)
    return found


class WorkflowGateTests(unittest.TestCase):
    def test_the_workflow_is_readable_and_declares_gates(self) -> None:
        gates = _workflow_gates()
        self.assertGreaterEqual(len(gates), 8, gates)
        self.assertIn("selftest --brief", gates)

    def test_every_gate_the_workflow_runs_passes_here(self) -> None:
        failures: list[str] = []
        for gate in _workflow_gates():
            if gate in _REPORT_ONLY:
                continue
            done = subprocess.run(
                [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
                 "--project", str(PLUGIN_ROOT), *gate.split()],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
            )
            if done.returncode != 0:
                tail = (done.stdout or done.stderr).strip().splitlines()
                failures.append(f"{gate} -> exit {done.returncode}: {tail[-1] if tail else ''}")
        self.assertEqual(failures, [], "gates CI runs that fail locally:\n" + "\n".join(failures))


class ActionManifestTests(unittest.TestCase):
    """The composite action failed to load for a fortnight, unnoticed.

    Both defects were invisible to every check that existed: the manifest is
    only parsed by GitHub, so nothing local ever read it. These assert the two
    shapes that actually broke it.
    """

    MANIFEST = PLUGIN_ROOT / "action.yml"

    def _inputs_block(self) -> str:
        text = self.MANIFEST.read_text(encoding="utf-8")
        return text.split("inputs:", 1)[1].split("\nruns:", 1)[0]

    def test_no_github_context_inside_inputs(self) -> None:
        """Expressions are evaluated in a manifest, and `github` is not bound
        there - even inside a description, where it reads as documentation."""
        hits = re.findall(r"\$\{\{[^}]*\bgithub\b[^}]*\}\}", self._inputs_block())
        self.assertEqual(hits, [], f"github context is unavailable in inputs: {hits}")

    def test_run_scalars_are_not_quote_prefixed(self) -> None:
        """`run: "$VAR" more words` is not a YAML scalar; it parses as a quoted
        string followed by rubbish, and the manifest fails to load whole."""
        bad = [
            line.strip()
            for line in self.MANIFEST.read_text(encoding="utf-8").splitlines()
            if re.match(r'\s*run:\s*"', line) and not line.rstrip().endswith('"')
        ]
        self.assertEqual(bad, [], f"run scalars that start quoted but continue: {bad}")

    def test_every_step_declares_a_shell(self) -> None:
        text = self.MANIFEST.read_text(encoding="utf-8")
        runs = text.count("      run:")
        shells = text.count("      shell:")
        self.assertGreaterEqual(shells, runs,
                                "a composite step with `run` must declare `shell`")

    def test_manifest_declares_the_required_roots(self) -> None:
        text = self.MANIFEST.read_text(encoding="utf-8")
        for key in ("name:", "description:", "runs:", "  using: composite"):
            self.assertIn(key, text, key)


if __name__ == "__main__":
    unittest.main()

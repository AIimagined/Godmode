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


if __name__ == "__main__":
    unittest.main()

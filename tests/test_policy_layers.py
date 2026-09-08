"""Two-layer authorization policy, tightest-wins (obligation 10274).

An operator-level policy above the project's `.godmode-authorization-policy.json`
is the governance ceiling: the project layer may add protected categories,
add approvals, add tool gates, add ask_only categories, shorten the
capability TTL, raise the nag posture and keep the interpreter posture at
ask, and can never do the opposite. `operator --policy` names which layer
decided each key. The operator file lives under GODMODE_STATE_HOME.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime.godmode_sentinel import (  # noqa: E402
    OPERATOR_POLICY_FILENAME, POLICY_FILENAME, explain_policy, local_authorization_policy,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _write(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


class PolicyLayerTests(unittest.TestCase):
    def test_the_project_layer_can_only_tighten_the_operator_ceiling(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            _write(Path(os.environ["GODMODE_STATE_HOME"]) / OPERATOR_POLICY_FILENAME, {
                "password_required": ["deploy"],
                "capability_ttl_seconds": 300,
                "nag_posture": "standard",
                "inline_interpreter": "ask",
                "tool_gates": {"WebFetch": "ask"},
                "ask_only": ["git-history-or-remote"],
            })
            _write(project / POLICY_FILENAME, {
                "password_required": ["database"],
                "capability_ttl_seconds": 900,
                "nag_posture": "quiet",
                "inline_interpreter": "scan",
                "tool_gates": {"WebFetch": "deny", "Bash": "ask"},
                "ask_only": ["filesystem"],
                "gate_mode": "observe",
            })
            policy = local_authorization_policy(archive)
            self.assertEqual(set(policy["password_required"]), {"deploy", "database"})
            self.assertEqual(policy["capability_ttl_seconds"], 300)
            self.assertEqual(policy["nag_posture"], "standard")
            self.assertEqual(policy["inline_interpreter"], "ask")
            self.assertEqual(policy["tool_gates"], {"WebFetch": "deny", "Bash": "ask"})
            self.assertEqual(set(policy["ask_only"]), {"git-history-or-remote", "filesystem"})
            # Observe is a loosening: the operator layer did not grant it.
            self.assertNotIn("gate_mode", policy)

    def test_no_operator_file_leaves_the_project_policy_exactly_as_before(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            _write(project / POLICY_FILENAME, {"password_required": ["database"], "gate_mode": "observe"})
            policy = local_authorization_policy(archive)
            self.assertEqual(policy["password_required"], ("database",))
            self.assertEqual(policy["gate_mode"], "observe")

    def test_explain_names_the_layer_that_decided_each_key(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            _write(Path(os.environ["GODMODE_STATE_HOME"]) / OPERATOR_POLICY_FILENAME,
                   {"password_required": ["deploy"], "capability_ttl_seconds": 300})
            _write(project / POLICY_FILENAME,
                   {"password_required": ["database"], "capability_ttl_seconds": 900,
                    "nag_posture": "strict"})
            report = explain_policy(archive)
            decided = {row["key"]: row["decided_by"] for row in report["keys"]}
            self.assertEqual(decided["capability_ttl_seconds"], "operator")
            self.assertEqual(decided["password_required"], "both")
            self.assertEqual(decided["nag_posture"], "project")
            self.assertTrue(report["layers"]["operator"]["present"])
            self.assertTrue(report["layers"]["project"]["present"])


if __name__ == "__main__":
    unittest.main()

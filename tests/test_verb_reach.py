"""The census counts verbs against what names them (obligation 10121).

Measured by hand on 2026-09-08: 120 verbs, 5 named by a shipped skill, 26 by
a hook nudge, 34 by docs only, 57 by nothing. The utilization census counted
record kinds and was green over that gap. This makes the verb the unit: a
verb is reachable on every host and fires on none unless a skill line or a
hook nudge names it at the moment of demand (a controlled study in the
research ledger, 2026-09-08: skills act as procedural anchors, and actual-use
precision collapses as the pool grows, so verbs are named from the five
existing skills and the nudges, never from new skills).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_census as census  # noqa: E402
from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class VerbReachTests(unittest.TestCase):
    def test_every_console_verb_is_measured(self) -> None:
        report = census.verb_reach(PLUGIN_ROOT)
        parser = console._build_parser()
        verbs = {name for action in parser._actions
                 if isinstance(action, __import__("argparse")._SubParsersAction)
                 for name in action.choices}
        self.assertEqual({v["verb"] for v in report["verbs"]}, verbs)
        for entry in report["verbs"]:
            self.assertEqual(set(entry) >= {"verb", "skill", "nudge", "docs"}, True, entry)

    def test_counts_and_the_unnamed_list_agree(self) -> None:
        report = census.verb_reach(PLUGIN_ROOT)
        unnamed = [v["verb"] for v in report["verbs"] if not (v["skill"] or v["nudge"] or v["docs"])]
        self.assertEqual(sorted(report["unnamed"]), sorted(unnamed))
        self.assertEqual(report["counts"]["total"], len(report["verbs"]))
        self.assertEqual(report["counts"]["unnamed"], len(unnamed))

    def test_the_unnamed_count_never_rises_above_the_ceiling(self) -> None:
        report = census.verb_reach(PLUGIN_ROOT)
        self.assertLessEqual(report["counts"]["unnamed"], census.UNNAMED_VERB_CEILING,
                             f"verbs named nowhere: {report['unnamed']}")
        # Named by a skill or a nudge is the demand path; docs-only is not.
        # The message names the verbs (CI run 102, 2026-09-10: a bare count
        # sent the reader to the census module to learn which two).
        self.assertLessEqual(report["counts"]["undemanded"], census.UNDEMANDED_VERB_CEILING,
                             f"verbs no shipped SKILL.md or hook nudge names: {report['undemanded']}")

    def test_doctor_carries_the_verb_reach_metric(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(project), "doctor"])
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertIn("verb_reach", payload)
        self.assertIn("unnamed", payload["verb_reach"])
        self.assertIn("ceiling", payload["verb_reach"])


if __name__ == "__main__":
    unittest.main()

"""A controlled holdout: two arms, one metric, a verdict computed not asserted.

Absorbed 2026-08-27 from an upstream plugin's holdout harness. The
experiment ledger adjudicated one cycle against its own baseline
(`before`/`after`, epsilon). A holdout is the other question: with the
change on for some runs and off for others, does the metric differ by
more than epsilon between the arms? Medians, so one bad run does not
decide; at least two observations per arm, or the answer is `underpowered`
rather than a guess; `indistinguishable` when the arms sit within epsilon,
which is a real answer and the honest one for most changes.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_holdout import record_holdout  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-holdout-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            yield root, Chronicle(resolve_anchor(root))


class HoldoutTests(unittest.TestCase):
    def test_treatment_wins_by_more_than_epsilon(self) -> None:
        with _project() as (root, archive):
            record = record_holdout(archive, root, name="terse-brief", metric="tokens",
                                    control=[100, 110, 105], treatment=[70, 72, 69],
                                    epsilon=5, lower_is_better=True)
        data = record["data"]
        self.assertEqual(data["verdict"], "treatment")
        self.assertEqual(data["medians"], {"control": 105.0, "treatment": 70.0})
        self.assertEqual(data["n"], {"control": 3, "treatment": 3})
        self.assertEqual(record["kind"], "verdict")  # the same kind a cycle's adjudication uses
        self.assertTrue(record["subject"].startswith("holdout:terse-brief"))

    def test_within_epsilon_is_indistinguishable(self) -> None:
        with _project() as (root, archive):
            data = record_holdout(archive, root, name="x", metric="m",
                                  control=[10, 11], treatment=[10.5, 11.5], epsilon=2)["data"]
        self.assertEqual(data["verdict"], "indistinguishable")

    def test_one_observation_per_arm_is_underpowered_not_a_verdict(self) -> None:
        with _project() as (root, archive):
            data = record_holdout(archive, root, name="x", metric="m",
                                  control=[10], treatment=[50], epsilon=1)["data"]
        self.assertEqual(data["verdict"], "underpowered")

    def test_cli_records_and_underpowered_reaches_the_exit(self) -> None:
        with _project() as (root, archive):
            archive.initialize()  # the console refuses an uninitialised project, by design
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "experiment", "holdout",
                                     "--name", "x", "--metric", "m", "--epsilon", "1",
                                     "--control", "10", "--treatment", "50"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "underpowered")


if __name__ == "__main__":
    unittest.main()

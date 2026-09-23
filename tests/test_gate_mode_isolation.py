"""park_local_policy()/restore_local_policy() isolate both policy layers.

`tests/_gate_mode_isolation.py` parks the checkout's own
`.godmode-authorization-policy.json` (the PROJECT layer) so hook-subprocess
tests get the shipped enforce default regardless of what this checkout has
declared. `godmode_sentinel.operator_policy_path()` names a second,
OPERATOR layer above it - `$GODMODE_STATE_HOME/godmode-authorization-policy.json`
- and an operator who has declared one (e.g. an `ask_only` list) fed the
same hook-subprocess tests that policy too, since nothing parked it.

This test proves the fix: while parked, `operator_policy_path()` resolves
under a fresh, empty temp directory, so a policy file sitting under a fake
"operator home" is not the path read - without ever touching that fake
home's file, and without ever going near the real `~/.godmode`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tests._gate_mode_isolation import park_local_policy, restore_local_policy  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    OPERATOR_POLICY_FILENAME, operator_policy_path,
)


class OperatorLayerParkedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fake_home_dir = tempfile.TemporaryDirectory(prefix="godmode-fake-operator-home-")
        self.fake_home = Path(self._fake_home_dir.name)
        self.fake_policy = self.fake_home / OPERATOR_POLICY_FILENAME
        self.fake_policy.write_text(
            json.dumps({"ask_only": ["a-fake-operator-declared-category"]}),
            encoding="utf-8",
        )
        self._prior_state_home = os.environ.get("GODMODE_STATE_HOME")
        os.environ["GODMODE_STATE_HOME"] = str(self.fake_home)

    def tearDown(self) -> None:
        if self._prior_state_home is None:
            os.environ.pop("GODMODE_STATE_HOME", None)
        else:
            os.environ["GODMODE_STATE_HOME"] = self._prior_state_home
        self._fake_home_dir.cleanup()

    def test_fake_operator_policy_is_live_before_parking(self) -> None:
        # Sanity: without parking, the fake home's file IS what
        # operator_policy_path() names - the baseline this test's park
        # assertion below is a change from.
        self.assertEqual(operator_policy_path(), self.fake_policy)
        self.assertTrue(operator_policy_path().exists())

    def test_parking_stops_the_fake_operator_policy_from_being_read(self) -> None:
        park_local_policy()
        try:
            parked_path = operator_policy_path()
            # The path operator_policy_path() names is no longer the fake
            # home's file, and whatever it does name does not exist - the
            # read a broker would do (a missing-file read) sees
            # exactly the "no operator layer" outcome it would see with no
            # operator file declared at all.
            self.assertNotEqual(parked_path, self.fake_policy)
            self.assertFalse(parked_path.exists())
            # The fake home's own file is untouched - parking isolates the
            # read path, it does not move or delete anyone's declaration.
            self.assertTrue(self.fake_policy.exists())
            self.assertEqual(
                json.loads(self.fake_policy.read_text(encoding="utf-8")),
                {"ask_only": ["a-fake-operator-declared-category"]},
            )
        finally:
            restore_local_policy()

    def test_restoring_reads_the_fake_operator_policy_again(self) -> None:
        park_local_policy()
        restore_local_policy()
        self.assertEqual(operator_policy_path(), self.fake_policy)
        self.assertTrue(operator_policy_path().exists())


if __name__ == "__main__":
    unittest.main()

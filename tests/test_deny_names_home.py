"""The deny-names list has a durable home outside the repository.

`GODMODE_DENY_NAMES` (an explicit path) has always been the way to supply the
project's private deny list. This adds a fallback: when that variable is
unset, the check now also looks for `deny-names.txt` in Godmode's own
per-user state home (`application_home()`), so the class can be measured
without exporting a variable in every shell. The env var still wins when set,
and with neither present the class stays `unmeasured`, not `clean` - an
absent instrument is graded distinctly from a negative result.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import no_external_source_names as N  # noqa: E402


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(body)


class DenyNamesDurableHome(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_falls_back_to_state_home_when_env_var_is_unset(self) -> None:
        state_home = self.tmp / "state-home"
        _write(
            state_home / "deny-names.txt",
            "alphaname\n# a comment line, ignored\nbetaname\n",
        )
        with patch.dict(
            os.environ,
            {"GODMODE_STATE_HOME": str(state_home)},
            clear=False,
        ):
            os.environ.pop("GODMODE_DENY_NAMES", None)
            names = N._deny_from_env()
        self.assertEqual(names, ["alphaname", "betaname"])

    def test_explicit_env_var_wins_over_the_state_home(self) -> None:
        state_home = self.tmp / "state-home"
        _write(state_home / "deny-names.txt", "alphaname\n")

        other = self.tmp / "elsewhere" / "other-names.txt"
        _write(other, "gammaname\n")

        with patch.dict(
            os.environ,
            {
                "GODMODE_STATE_HOME": str(state_home),
                "GODMODE_DENY_NAMES": str(other),
            },
            clear=False,
        ):
            names = N._deny_from_env()
        self.assertEqual(names, ["gammaname"])

    def test_neither_present_returns_none(self) -> None:
        empty_home = self.tmp / "empty-state-home"
        empty_home.mkdir(parents=True, exist_ok=True)
        with patch.dict(
            os.environ,
            {"GODMODE_STATE_HOME": str(empty_home)},
            clear=False,
        ):
            os.environ.pop("GODMODE_DENY_NAMES", None)
            names = N._deny_from_env()
        self.assertIsNone(names)


if __name__ == "__main__":
    unittest.main()

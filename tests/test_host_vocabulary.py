"""The five host names are declared three times; they must stay one set.

`_ADAPTERS` maps a host to the function that reads its event dialect,
`_PRETOOL_MANIFEST_SPECS` maps it to the manifest file, event key and
latency budget its proof reads, and `_SOFT_ELIGIBLE_HOSTS` names the hosts
that may reach a SOFT interception grade. Three different facts about one
vocabulary - a reasonable split, since a function, a three-tuple and a
membership flag do not belong in one structure.

The vocabulary drifting is the part that has already cost something. The
comment above `_PRETOOL_MANIFEST_SPECS["codex"]` records it: the entry
named an event Codex cannot fire, and the proof answered "budget unknown"
rather than failing - a host present in one structure and wrong in
another produces a degraded answer, not an error.

A sixth host added to `_ADAPTERS` alone would adapt its events, have no
manifest to prove against, and be ineligible for a SOFT grade, with
nothing anywhere saying why.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_hookproof import (  # noqa: E402
    _PRETOOL_MANIFEST_SPECS,
    _SOFT_ELIGIBLE_HOSTS,
)
from godmode_runtime.godmode_hostevent import _ADAPTERS  # noqa: E402


class VocabularyTests(unittest.TestCase):
    def test_every_adapted_host_has_a_manifest_spec(self) -> None:
        from godmode_runtime.godmode_hookproof import NO_DECLARED_PRETOOL_BUDGET

        self.assertEqual(
            set(_ADAPTERS), set(_PRETOOL_MANIFEST_SPECS) | NO_DECLARED_PRETOOL_BUDGET,
            "a host whose events are adapted but whose manifest is unnamed "
            "answers 'budget unknown' from `hooks proof` instead of failing")
        # The exemption is for a boundary that declares no timeout at all
        # (OpenCode's shim awaits the gate), never a way to skip naming one.
        self.assertEqual(
            NO_DECLARED_PRETOOL_BUDGET & set(_PRETOOL_MANIFEST_SPECS), frozenset())

    def test_every_adapted_host_may_reach_a_soft_grade(self) -> None:
        self.assertEqual(
            set(_ADAPTERS), set(_SOFT_ELIGIBLE_HOSTS),
            "a host missing here is silently ineligible for a SOFT grade")

    def test_each_manifest_spec_is_shaped_as_path_event_budget(self) -> None:
        for host, spec in _PRETOOL_MANIFEST_SPECS.items():
            with self.subTest(host=host):
                path, event, budget = spec
                self.assertTrue(path and event)
                self.assertGreater(budget, 0)


if __name__ == "__main__":
    unittest.main()

"""Every runtime module's own self-check, found rather than remembered.

Each module carries a `_self_check` that exercises its behaviour directly, and
each was wired into the suite by hand, one test class at a time. That works
until someone adds a module and does not — which happened, and the new module's
self-check sat unexercised while the suite reported green.

Discovering them removes the step that can be forgotten. A module that grows a
self-check is covered the moment it exists, and one whose self-check starts
failing is reported by name.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import godmode_runtime  # noqa: E402


def _modules_with_self_checks() -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    for info in pkgutil.iter_modules(godmode_runtime.__path__):
        module = importlib.import_module(f"godmode_runtime.{info.name}")
        check = getattr(module, "_self_check", None)
        if callable(check):
            found.append((info.name, check))
    return sorted(found)


class SelfCheckTests(unittest.TestCase):
    def test_every_module_self_check_passes(self) -> None:
        failures: list[str] = []
        for name, check in _modules_with_self_checks():
            try:
                check()  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001 - the module names its own fault
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_discovery_found_the_known_modules(self) -> None:
        """Guards the discovery itself: an import path that silently found
        nothing would make the test above pass while checking nothing."""
        names = {name for name, _ in _modules_with_self_checks()}
        self.assertGreaterEqual(len(names), 12, sorted(names))
        for expected in ("godmode_charter", "godmode_sentinel", "godmode_trust"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()

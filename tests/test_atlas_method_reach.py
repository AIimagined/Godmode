"""A method called through an instance is reached, not orphaned.

Call edges were only recorded when the called name was defined in the
SAME file. `from x import y` was handled separately, but a method reached
through an instance - `archive.reanchor()` in another module - is never
imported by name, so it linked to nothing. Every public method not also
called inside its own file therefore read as an orphan.

Measured before the fix: of nine symbols sampled from this project's
orphan report, seven were live code - `reanchor` (called by `db
--reanchor`), `expunge`, `latest`, `orphaned`, `adopt`, `public_view`,
`register_kind_invariant`. A 78% false-positive rate on a report whose
own source comment says noise makes it "worse than no report".

The fix trades precision for honesty in the cheaper direction. Matching a
called attribute by NAME can mark a same-named method elsewhere as
reached, so some genuinely dead code goes unreported. For an advisory
about reinvention pressure a false negative costs a missed cleanup; a
false positive costs someone deleting live code, or - more likely, and
what happened here - learning to ignore the report.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_atlas import build as build_atlas  # noqa: E402


def _project(files: dict[str, str]) -> Path:
    base = Path(tempfile.mkdtemp())
    for name, body in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return base


class MethodReachTests(unittest.TestCase):
    def _orphan_names(self, files: dict[str, str]) -> set[str]:
        atlas = build_atlas(_project(files))
        return {entry["name"] for entry in atlas.orphans()}

    def test_a_method_called_through_an_instance_is_reached(self) -> None:
        names = self._orphan_names({
            "store.py": (
                "class Store:\n"
                "    def reanchor(self):\n"
                "        return 1\n"
            ),
            "console.py": (
                "from store import Store\n"
                "def main():\n"
                "    Store().reanchor()\n"
            ),
        })
        self.assertNotIn("reanchor", names)

    def test_a_method_nobody_calls_is_still_an_orphan(self) -> None:
        # The fix must not silence the report entirely.
        names = self._orphan_names({
            "store.py": (
                "class Store:\n"
                "    def never_used_anywhere(self):\n"
                "        return 1\n"
            ),
            "console.py": "def main():\n    return 2\n",
        })
        self.assertIn("never_used_anywhere", names)

    def test_a_property_read_through_an_instance_is_reached(self) -> None:
        """A property is read, never called, so call edges cannot see it.

        `Symbol.id` in this project is exactly that shape - used as
        `symbol.id` throughout `godmode_atlas` itself - and was reported
        dead because nothing ever writes `symbol.id()`.
        """
        names = self._orphan_names({
            "store.py": (
                "class Store:\n"
                "    @property\n"
                "    def token(self):\n"
                "        return 1\n"
            ),
            "console.py": (
                "from store import Store\n"
                "def main():\n"
                "    return Store().token\n"
            ),
        })
        self.assertNotIn("token", names)

    def test_a_plain_function_call_still_resolves(self) -> None:
        names = self._orphan_names({
            "helpers.py": "def helper():\n    return 1\n",
            "console.py": (
                "from helpers import helper\n"
                "def main():\n"
                "    return helper()\n"
            ),
        })
        self.assertNotIn("helper", names)


if __name__ == "__main__":
    unittest.main()

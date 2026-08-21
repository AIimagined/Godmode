"""One list of read-only tools, not two that happen to agree today.

`hooks/godmode_session_hook.py` decided which tools skip the full check,
and `godmode_hostevent.py` decided which tools an adapter reports as
reads. Both held the same six names as separate literals in separate
files, so they agreed by coincidence and nothing would have said so if
they stopped.

The failure that shape produces is quiet and one-directional. Add a
genuinely read-only tool to the adapter and the gate still charges it the
full check - merely slow. Add one to the gate and the adapter keeps
classifying it as a mutation, or the reverse: the gate waves through a
tool the adapter believes can write. A disagreement about what can mutate
is not the kind of drift worth discovering from behaviour.

Pinned by identity rather than equality on purpose. Equal contents is the
property that already held while the duplication existed; only one owner
makes divergence impossible instead of unlikely.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (str(SCRIPTS), str(HOOKS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from godmode_runtime import godmode_constants  # noqa: E402
from godmode_runtime import godmode_hostevent  # noqa: E402


class SingleOwnerTests(unittest.TestCase):
    def test_the_constant_module_owns_the_list(self) -> None:
        self.assertTrue(godmode_constants.READ_ONLY_TOOLS)

    def test_the_adapter_reads_the_shared_list(self) -> None:
        self.assertIs(godmode_hostevent._CLAUDE_READ_TOOLS,
                      godmode_constants.READ_ONLY_TOOLS)

    def test_the_gate_hook_reads_the_shared_list(self) -> None:
        import godmode_session_hook

        self.assertIs(godmode_session_hook._READ_ONLY_TOOLS,
                      godmode_constants.READ_ONLY_TOOLS)

    def test_a_read_tool_and_a_write_tool_are_not_confused(self) -> None:
        # A guard on the contents themselves, so a future edit that empties
        # or inverts the set fails here rather than in the field.
        self.assertIn("Read", godmode_constants.READ_ONLY_TOOLS)
        self.assertNotIn("Write", godmode_constants.READ_ONLY_TOOLS)
        self.assertNotIn("Bash", godmode_constants.READ_ONLY_TOOLS)


if __name__ == "__main__":
    unittest.main()

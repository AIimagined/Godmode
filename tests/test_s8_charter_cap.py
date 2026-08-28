"""S8 addendum: the code-of-law role compiles ADVISORY at most.

Laws are ADVISORY by the law module's own contract (HARD stays with the
charter's directive documents), yet the first committed law file minted
seven unattested HARD rules from its guard sentences and blocked
`status remaining` within the hour of its creation.
"""
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_charter import RECORD_ROLES  # noqa: E402


class LawFileCompilesAdvisoryTests(unittest.TestCase):
    def test_code_of_law_is_a_record_role(self) -> None:
        # Membership is the whole mechanism: RECORD_ROLES members are capped
        # to ADVISORY at compile time, with capped_from naming the cap.
        self.assertIn("code-of-law", RECORD_ROLES)


if __name__ == "__main__":
    unittest.main()

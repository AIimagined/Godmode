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


class LawDedupTests(unittest.TestCase):
    """One subject, one law: a retried promotion wrote the same law twice,
    and two pre-compiler lessons shared a subject - each rendered twice."""

    def test_the_newest_record_per_subject_is_the_law(self) -> None:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).parent))
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_law import top_laws

        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("lesson", "one-subject",
                           {"status": "active", "generalized_guard": "old guard"},
                           evidence=[])
            archive.append("lesson", "one-subject",
                           {"status": "active", "generalized_guard": "new guard"},
                           evidence=[])
            laws = top_laws(archive, 10)
            self.assertEqual(
                [l["subject"] for l in laws].count("one-subject"), 1)
            self.assertIn("new guard", laws[0]["guard"])
            archive.append("lesson", "one-subject", {"status": "retired"},
                           evidence=[])
            self.assertEqual(top_laws(archive, 10), [])


if __name__ == "__main__":
    unittest.main()

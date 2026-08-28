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

from godmode_runtime.godmode_charter import SKIPPED_ROLES, compile_charter  # noqa: E402


class LawFileCompilesAdvisoryTests(unittest.TestCase):
    def test_code_of_law_is_skipped_entirely(self) -> None:
        # Round two of the same night: the ADVISORY cap still minted twenty
        # rules the checkability review then demanded decisions for. The law
        # file is delivery, not source - the charter never mints rules from
        # it, and the wrapper skill plus the brief remain its channel.
        self.assertIn("code-of-law", SKIPPED_ROLES)
        import tempfile
        from pathlib import Path as _Path

        body = "\n".join([
            "# GODMODE CODE OF LAW",
            "",
            "## Law 1 - x  [ADVISORY]",
            "Guard: Always record every claim before stating it.",
            "",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = _Path(tmp)
            (root / "GODMODE-CODE-OF-LAW.md").write_text(body, encoding="utf-8")
            charter = compile_charter(root)
        law_rules = charter.get("by_role", {}).get("code-of-law", [])
        self.assertEqual(list(law_rules), [])


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


class PromotedClusterIsConsumedTests(unittest.TestCase):
    def test_a_promoted_cluster_leaves_the_candidate_list(self) -> None:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).parent))
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_law import (
            law_candidates, promote_candidate, record_instruction_candidate)

        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_instruction_candidate(
                archive, "always preview destructive removals first",
                session="S-1")
            cluster = law_candidates(archive)[0]
            promote_candidate(archive, cluster["first_seq"],
                              guard="Preview destructive removals first.",
                              subject="preview-first")
            self.assertEqual(law_candidates(archive), [])


if __name__ == "__main__":
    unittest.main()

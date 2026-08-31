"""Fresh-lessons overlay and the what-was-learned line.

A lesson recorded at the moment of discovery must be load-bearing in the
same session, not after the next law compile: the overlay reads the law
file's own provenance lines and surfaces every living guarded lesson
missing from them, marked fresh-uncompiled, on the pre-action advisory
path only. And a checkpoint written while the newest incident postdates
the newest lesson carries one advisory line: the failure taught nothing
on the record yet.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_law import compile_laws, fresh_laws  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _lesson(archive, subject, guard):
    archive.append("lesson", subject,
                   {"value": "observed", "generalized_guard": guard,
                    "status": "active"})


class FreshLawsTests(unittest.TestCase):
    def test_with_no_law_file_every_guarded_lesson_is_fresh(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "new-rule", "quote every path")
            fresh = fresh_laws(archive, project)
            self.assertEqual(len(fresh), 1)
            self.assertEqual(fresh[0]["marker"], "fresh-uncompiled")

    def test_a_compiled_lesson_is_not_fresh(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "old-rule", "quote every path")
            compile_laws(archive, project)
            self.assertEqual(fresh_laws(archive, project), [])

    def test_a_lesson_recorded_after_compile_is_fresh_immediately(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "old-rule", "quote every path")
            compile_laws(archive, project)
            _lesson(archive, "mid-session", "cite the run beside the file")
            fresh = fresh_laws(archive, project)
            self.assertEqual([f["subject"] for f in fresh], ["mid-session"])


if __name__ == "__main__":
    unittest.main()


class CheckpointLearnNagTests(unittest.TestCase):
    def _checkpoint(self, runtime):
        import argparse
        from godmode_runtime.godmode_console import cmd_checkpoint
        args = argparse.Namespace(
            review=False, summary="wrap", status="active",
            next_action="continue", hypothesis=None, outcome=None,
            evidence=["file:README.md"], session=None)
        return cmd_checkpoint(args, runtime)

    def _runtime(self, anchor, archive):
        from godmode_runtime.godmode_console import Runtime
        return Runtime(anchor=anchor, archive=archive)

    def test_an_unlearned_incident_draws_the_advisory(self) -> None:
        with isolated_project() as (_p, _s, anchor, archive):
            archive.initialize()
            archive.append("incident", "export broke", {"detail": "boom"})
            result = self._checkpoint(self._runtime(anchor, archive))
            self.assertIn("advisories", result.payload)
            self.assertIn("lesson", result.payload["advisories"][0])

    def test_a_recorded_lesson_silences_it(self) -> None:
        with isolated_project() as (_p, _s, anchor, archive):
            archive.initialize()
            archive.append("incident", "export broke", {"detail": "boom"})
            _lesson(archive, "export-rule", "bound the export size")
            result = self._checkpoint(self._runtime(anchor, archive))
            self.assertNotIn("advisories", result.payload)

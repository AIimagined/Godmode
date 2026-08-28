"""Sprint L1 of the Code of Law loop (spec: 2026-08-28-code-of-law-spec.md).

The law file is a GENERATED authority document: `law compile` folds every
lesson that carries a generalized guard into a bounded, provenance-carrying
`GODMODE-CODE-OF-LAW.md` at the project root, plus a wrapper skill so
hook-less hosts fire it. The file is a bound authority role, so the charter,
the required-sources counter and `attest` consume it with no new machinery.
The SessionStart brief carries the top laws within its existing budget.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    LAW_FILENAME, compile_laws, top_laws,
)


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-law-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


def _lesson(archive, subject, value, guard=None):
    data = {"status": "active", "value": value}
    if guard:
        data["generalized_guard"] = guard
    return archive.append("lesson", subject, data, evidence=[])


class CompileTests(unittest.TestCase):
    def test_guarded_lessons_become_laws_with_provenance(self) -> None:
        with _project() as (root, archive):
            first = _lesson(archive, "probe-reach", "a probe that reached nothing",
                            guard="read the checked counters before quoting a verdict")
            _lesson(archive, "no-guard-here", "an observation without a guard")
            report = compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 1)
        self.assertEqual(report["skipped_without_guard"], 1)
        self.assertIn("read the checked counters", text)
        self.assertIn(f"seq:{first['sequence']}", text)
        self.assertIn("ADVISORY", text)
        # Generated, and says so - a hand edit would be overwritten.
        self.assertIn("generated", text.lower())

    def test_compile_is_idempotent_byte_for_byte(self) -> None:
        with _project() as (root, archive):
            _lesson(archive, "one", "value", guard="always do the thing")
            compile_laws(archive, root)
            before = (root / LAW_FILENAME).read_bytes()
            compile_laws(archive, root)
            self.assertEqual(before, (root / LAW_FILENAME).read_bytes())

    def test_the_file_is_bounded_even_with_many_lessons(self) -> None:
        with _project() as (root, archive):
            for index in range(60):
                _lesson(archive, f"lesson-{index}", "v" * 200,
                        guard=("guard sentence " + str(index)) * 8)
            report = compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        self.assertLessEqual(report["laws"], report["cap"])
        self.assertGreater(report["dropped_over_cap"], 0)
        # The bound is stated in the artifact, not silent (no-silent-caps).
        self.assertIn(str(report["dropped_over_cap"]), text)

    def test_the_wrapper_skill_is_written_and_names_the_law_file(self) -> None:
        with _project() as (root, archive):
            _lesson(archive, "one", "value", guard="a guard")
            compile_laws(archive, root)
            skill = root / "skills" / "godmode-code-of-law" / "SKILL.md"
            self.assertTrue(skill.is_file())
            body = skill.read_text(encoding="utf-8")
        self.assertIn(LAW_FILENAME, body)
        self.assertIn("name: godmode-code-of-law", body)

    def test_the_law_file_is_a_bound_authority_role(self) -> None:
        from godmode_runtime.godmode_corpus import resolve_roles

        with _project() as (root, archive):
            _lesson(archive, "one", "value", guard="a guard")
            compile_laws(archive, root)
            bound = {b.path.name for b in resolve_roles(root).bindings}
        self.assertIn(LAW_FILENAME, bound)


class TopLawsTests(unittest.TestCase):
    def test_top_laws_are_newest_guarded_first_and_bounded(self) -> None:
        with _project() as (_root, archive):
            for index in range(6):
                _lesson(archive, f"lesson-{index}", "v", guard=f"guard {index}")
            top = top_laws(archive, 3)
        self.assertEqual(len(top), 3)
        self.assertIn("guard 5", top[0]["guard"])
        for law in top:
            self.assertLessEqual(len(law["guard"]), 200)


class BriefTests(unittest.TestCase):
    def test_session_start_brief_carries_the_top_laws(self) -> None:
        with _project() as (root, archive):
            _lesson(archive, "probe-reach", "value",
                    guard="read the checked counters before quoting a verdict")
            compile_laws(archive, root)
            done = subprocess.run(
                [sys.executable, str(HOOKS / "godmode_session_hook.py"),
                 "session-start", "--project", str(root)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180,
                env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
            )
        payload = json.loads(done.stdout)
        laws = payload["brief"].get("laws")
        self.assertTrue(laws, payload["brief"].keys())
        self.assertIn("checked counters", json.dumps(laws))


if __name__ == "__main__":
    unittest.main()

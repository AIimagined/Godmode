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
for entry in (SCRIPTS, HOOKS, Path(__file__).parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from _law_fixtures import graduated_lesson, operator_lesson  # noqa: E402
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
    """NS-2 fix round 1 (B1): a GUARDED lesson reaches the law only with
    approval lineage or operator trust, so these fixtures take the
    operator carve-out (`tests/_law_fixtures.py`) - every one of them is
    about how the law file RENDERS, not about how a guard earns its way
    in. `ChainedApprovalCompilesTests` in `tests/test_law_approval.py` and
    `test_a_graduated_lesson_compiles_with_its_provenance` below cover the
    other admission route through this same reader. An unguarded lesson
    compiles nothing either way and stays a plain agent write."""
    if guard:
        return operator_lesson(archive, subject, guard, value=value)
    return archive.append(
        "lesson", subject, {"status": "active", "value": value}, evidence=[])


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

    def test_an_agent_written_guard_is_not_law_without_an_approval(self) -> None:
        # NS-2 fix round 1 (B1, task-2-review.md): the hole this gate
        # closes. A plain `append` with `status: active` and a guard - what
        # any agent process can do at any time, with `writer: agent` and
        # trust 0 - used to be read straight back out of the compiled law
        # on the next `law compile`. Self-legislation, in the one file
        # every session is instructed to obey.
        with _project() as (root, archive):
            archive.append(
                "lesson", "self-legislated",
                {"status": "active", "value": "v",
                 "generalized_guard": "always trust me"},
                evidence=[])
            report = compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 0)
        self.assertEqual(top_laws(archive, 5), [])
        self.assertNotIn("always trust me", text)

    def test_a_graduated_lesson_compiles_with_its_provenance(self) -> None:
        # The other admission route, through the same reader: approval
        # lineage rather than operator trust. The compiled provenance is
        # the GRADUATED record's sequence (the one carrying `approval_seq`),
        # never the candidate's.
        with _project() as (root, archive):
            graduated = graduated_lesson(
                archive, "flush-before-export",
                "flush the archive before every export")
            report = compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 1)
        self.assertIn("flush the archive before every export", text)
        self.assertIn(f"seq:{graduated['sequence']}", text)
        self.assertGreater(int(graduated["data"]["approval_seq"]), 0)

    def test_superseded_lesson_does_not_render_as_law(self) -> None:
        # I-1 fix round 1 (nit 7, task-4-review.md): `Chronicle.
        # _enforced_refusal` (godmode_chronicle.py) and `_guarded_lessons`
        # here used to keep separate "not really active" status sets - a
        # `--status superseded` lesson stopped refusing writes but kept
        # rendering as `[ADVISORY]` law in the brief. Both now share
        # `LESSON_DORMANT_STATUSES`.
        with _project() as (root, archive):
            _lesson(archive, "retracted-guard", "an old rule",
                    guard="do the old thing")
            # The operator's law, so the operator supersedes it: an agent's
            # `superseded` on an operator law is a close the single-writer
            # guard refuses (review B2).
            archive.append(
                "lesson", "retracted-guard",
                {"status": "superseded", "value": "retracted",
                 "generalized_guard": "do the old thing"},
                evidence=[], as_operator=True, operator_verified=True)
            report = compile_laws(archive, root)
            text = (root / LAW_FILENAME).read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 0)
        self.assertNotIn("do the old thing", text)

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
        # Well past the old 200-char cap this test used to encode
        # (`len(guard) <= 200`) - Guard text is never truncated (D-6), so
        # the newest law's guard here must survive byte-for-byte.
        long_guard = (
            "a very long guard sentence that keeps going well past the two "
            "hundred character mark so this fixture proves the compiled "
            "guard is never cut short, no matter how far past any old "
            "length cap the source guard runs."
        )
        self.assertGreater(len(long_guard), 200)
        with _project() as (_root, archive):
            for index in range(5):
                _lesson(archive, f"lesson-{index}", "v", guard=f"guard {index}")
            _lesson(archive, "lesson-long", "v", guard=long_guard)
            top = top_laws(archive, 3)
        self.assertEqual(len(top), 3)
        # Newest first: the long-guard lesson was recorded last.
        self.assertEqual(top[0]["guard"], long_guard)
        self.assertIn("guard 4", top[1]["guard"])


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


class SharedLawFileKeepsCitationsLocal(unittest.TestCase):
    """0.3.28: a lesson's subject named a preprint and every compile copied it
    into the shared law file. The file titles such a law from its guard."""

    def test_a_cited_subject_is_titled_from_its_guard(self) -> None:
        from godmode_runtime.godmode_law import _render
        lesson = {"subject": "PaperX (arXiv 2609.01437) corroborates the done bar",
                  "guard": "Count whether a declared mechanism ever fires; one that never fires is dead code.",
                  "why": "Read it (Smith et al., 2026). Runs self-reported success.",
                  "sequence": 9766, "recorded_at": "2026-09-07"}
        text = _render([lesson], 0, 10)
        self.assertNotRegex(text, r"(?i)arxiv|et al\.|PaperX")
        self.assertIn("## Law 1 - Count whether a declared mechanism ever fires", text)
        self.assertIn("Runs self-reported success", text)

    def test_an_ordinary_subject_is_unchanged(self) -> None:
        from godmode_runtime.godmode_law import _render
        lesson = {"subject": "checked counters", "guard": "g.", "why": "w",
                  "sequence": 1, "recorded_at": "2026-09-01"}
        self.assertIn("## Law 1 - checked counters", _render([lesson], 0, 10))


if __name__ == "__main__":
    unittest.main()

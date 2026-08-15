"""U-E3: differential-evidence detector - diff before theory.

Mechanizes varunraj-kinetiq §4.8a / L-267: when two comparable states exist,
a root-cause claim without the differential is inadmissible as a finding.

`record_differential` records a comparison of two archived states -
`{subject, a_ref, b_ref, delta, method}` - as a `differential` record;
`diff:<seq>` resolves iff the record exists AND both `a_ref`/`b_ref` also
resolve. `record_claim`'s detector fires only when root-cause vocabulary
(`ROOT_CAUSE_VOCAB`) is found OUTSIDE quotes/code spans AND the archive
holds two or more comparable-state records (checkpoint/verdict/metric)
sharing the claim's salient terms; it then requires a RESOLVING `diff:` or
`verdict:` citation, or the claim is downgraded naming the comparable seqs.
No comparable states at all leaves the claim untouched - absence of the
instrument is a stated gap, never a penalty, same discipline as U-T2.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PYTHON = f'"{sys.executable}"'

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime.godmode_attest import (  # noqa: E402
    open_session,
    record_claim,
    record_differential,
)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


def _checkpoint(archive, subject: str) -> dict:
    """A comparable-state fixture: a `checkpoint` record under `subject`."""
    return archive.append("checkpoint", subject, {"status": "captured"}, evidence=[])


class DowngradeTests(unittest.TestCase):
    def test_root_cause_claim_with_comparables_and_no_diff_downgrades(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            s1 = _checkpoint(archive, "render pipeline")
            s2 = _checkpoint(archive, "render pipeline")
            out = record_claim(
                archive, project, session,
                "the root cause is the pipeline reorder", "verified",
                cites=["file:notes.txt"],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertTrue(out["data"]["downgraded"])
        self.assertIn(f"seq:{s1['sequence']}", out["data"]["reason"])
        self.assertIn(f"seq:{s2['sequence']}", out["data"]["reason"])

    def test_with_diff_citation_resolves(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            _checkpoint(archive, "render pipeline")
            _checkpoint(archive, "render pipeline")
            (project / "a.py").write_text("a\n", encoding="utf-8")
            (project / "b.py").write_text("b\n", encoding="utf-8")
            diff = record_differential(
                archive, "render pipeline", "file:a.py", "file:b.py",
                ["reordered the passes"], "read",
            )
            out = record_claim(
                archive, project, session,
                "the root cause is the pipeline reorder", "verified",
                cites=[f"diff:{diff['sequence']}"],
            )
        self.assertEqual(out["data"]["grade"], "verified")
        self.assertFalse(out["data"]["downgraded"])

    def test_a_confirmed_verdict_citation_also_satisfies_it(self) -> None:
        from godmode_runtime.godmode_verdict import record_verdict

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            _checkpoint(archive, "render pipeline")
            _checkpoint(archive, "render pipeline")
            (project / "witness.txt").write_text("42\n", encoding="utf-8")
            verdict = record_verdict(
                archive, project, "the pipeline reorder caused it", "42",
                "file:witness.txt", f'{PYTHON} -c "exit(0)"',
            )
            self.assertEqual(verdict["data"]["disposition"], "confirmed")
            out = record_claim(
                archive, project, session,
                "the root cause is the pipeline reorder", "verified",
                cites=[f"verdict:{verdict['sequence']}"],
            )
        self.assertEqual(out["data"]["grade"], "verified")


class StatedGapsTests(unittest.TestCase):
    def test_no_comparable_states_leaves_the_claim_untouched(self) -> None:
        """Absence of the differential instrument is never a penalty."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            out = record_claim(
                archive, project, session,
                "the root cause is the pipeline reorder", "verified",
                cites=["file:notes.txt"],
            )
        self.assertEqual(out["data"]["grade"], "verified")
        self.assertFalse(out["data"]["downgraded"])

    def test_quoted_root_cause_prose_is_untouched(self) -> None:
        """Reporting what someone else said is not asserting a mechanism -
        even with two comparable states sitting right there to diff."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            _checkpoint(archive, "cache eviction")
            _checkpoint(archive, "cache eviction")
            out = record_claim(
                archive, project, session,
                "user said 'the root cause is a stale cache eviction' - investigating",
                "verified", cites=["file:notes.txt"],
            )
        self.assertEqual(out["data"]["grade"], "verified")
        self.assertNotIn("differential", out["data"].get("reason", ""))

    def test_root_cause_in_a_code_span_is_untouched(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            _checkpoint(archive, "log line")
            _checkpoint(archive, "log line")
            out = record_claim(
                archive, project, session,
                "the log line literally says `the root cause is X` verbatim",
                "verified", cites=["file:notes.txt"],
            )
        self.assertEqual(out["data"]["grade"], "verified")

    def test_ordinary_claims_are_not_held_to_this_at_all(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            out = record_claim(
                archive, project, session, "the notes file exists", "verified",
                cites=["file:notes.txt"],
            )
        self.assertEqual(out["data"]["grade"], "verified")


class CitationIntegrityTests(unittest.TestCase):
    """`diff:<seq>` resolves iff the record exists AND both refs resolve.

    These claims are still gated through the U-E3 detector (two comparable
    states, root-cause vocabulary) - which is *why* a non-resolving `diff:`
    downgrades here rather than being read as an ordinary unresolved
    citation: the detector's own early return reports the failure in
    `reason` (naming the comparable states and what to cite instead) rather
    than in the generic `unresolved` list.
    """

    def test_diff_citation_needs_both_refs_to_resolve(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            _checkpoint(archive, "z state")
            _checkpoint(archive, "z state")
            diff = record_differential(
                archive, "z state", "file:missing-a.py", "file:missing-b.py",
                ["placeholder"], "read",
            )
            out = record_claim(
                archive, project, session, "the root cause is z state", "verified",
                cites=[f"diff:{diff['sequence']}"],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertTrue(out["data"]["downgraded"])
        self.assertIn("diff:", out["data"]["reason"])

    def test_a_diff_citation_naming_no_record_does_not_resolve(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            _checkpoint(archive, "z state")
            _checkpoint(archive, "z state")
            out = record_claim(
                archive, project, session, "the root cause is z state", "verified",
                cites=["diff:99999"],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertTrue(out["data"]["downgraded"])
        self.assertIn("diff:", out["data"]["reason"])

    def test_diff_resolution_itself_is_independent_of_the_root_cause_detector(self) -> None:
        """A claim that never trips the U-E3 detector (no root-cause
        vocabulary) still needs any `diff:` it cites to resolve, through the
        ordinary unresolved-citation path - proving `_citation_resolves`'s
        `diff:` handling directly, decoupled from the detector's own gate."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            diff = record_differential(
                archive, "z state", "file:missing-a.py", "file:missing-b.py",
                ["placeholder"], "read",
            )
            out = record_claim(
                archive, project, session, "notes.txt exists in the project", "verified",
                cites=[f"diff:{diff['sequence']}"],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertIn(f"diff:{diff['sequence']}", out["data"]["unresolved"])


class RecordDifferentialTests(unittest.TestCase):
    def test_delta_over_the_item_cap_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_differential(
                    archive, "x", "file:a.py", "file:b.py",
                    [f"item {i}" for i in range(21)], "read",
                )

    def test_a_delta_item_over_the_character_cap_is_truncated(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = record_differential(
                archive, "x", "file:a.py", "file:b.py", ["a" * 300], "read",
            )
        self.assertEqual(len(record["data"]["delta"][0]), 160)

    def test_method_must_be_read_or_a_cmd_reference(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_differential(
                    archive, "x", "file:a.py", "file:b.py", [], "eyeballed it",
                )

    def test_a_differential_cannot_reference_another_differential(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_differential(archive, "x", "diff:1", "file:b.py", [], "read")

    def test_both_refs_are_required(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_differential(archive, "x", "", "file:b.py", [], "read")


class PlantTests(unittest.TestCase):
    def test_deleting_the_differential_record_file_stops_the_citation_resolving(self) -> None:
        """The mandated plant. The differential is deleted while it is still
        the newest record in the archive, so the hash chain stays contiguous
        for everything recorded before it - a real re-grade is what appends
        next. That re-grade is what proves the citation stopped resolving:
        the same claim that would have resolved (see `test_with_diff_citation_
        resolves` above) now downgrades once its cited record is gone."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "differential")
            _checkpoint(archive, "render pipeline")
            _checkpoint(archive, "render pipeline")
            (project / "a.py").write_text("a\n", encoding="utf-8")
            (project / "b.py").write_text("b\n", encoding="utf-8")
            diff = record_differential(
                archive, "render pipeline", "file:a.py", "file:b.py",
                ["reordered the passes"], "read",
            )
            seq = diff["sequence"]
            files = list(archive.events.glob(f"{seq:012d}-*.godmode.json"))
            self.assertEqual(len(files), 1, "expected one file for the differential record")
            files[0].unlink()
            out = record_claim(
                archive, project, session,
                "the root cause is the pipeline reorder", "verified",
                cites=[f"diff:{seq}"],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertTrue(out["data"]["downgraded"])
        self.assertIn("diff:", out["data"]["reason"])


class ConsoleSmokeTests(unittest.TestCase):
    """Pins the bundled KeyError fix from the U-E3 commit (a pre-existing
    bug, found while smoke-testing this exact path): `record_claim`'s
    differential and external-primary-source downgrade paths stored the
    claimed grade under `"requested"` instead of `"claimed_grade"` - the
    key `cmd_claim` (`godmode_console.py`) reads directly, so `godmode
    claim` KeyError'd on either path pre-fix. Nothing exercised `godmode
    claim` through the console layer before this - the fully green unit
    suite never would have caught it, or a regression of it."""

    def test_a_differential_downgrade_through_the_console_layer_reports_cleanly(self) -> None:
        import contextlib
        import io
        import json as jsonlib

        from godmode_runtime.godmode_console import main

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _checkpoint(archive, "render pipeline")
            _checkpoint(archive, "render pipeline")
            (project / "notes.txt").write_text("x\n", encoding="utf-8")
            opened = main(
                ["--project", str(project), "session", "open", "--label", "console"])
            self.assertEqual(opened, 0)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "--project", str(project), "claim",
                    "the root cause is the pipeline reorder",
                    "--grade", "verified", "--cite", "file:notes.txt",
                ])
        payload = jsonlib.loads(out.getvalue())
        # A downgrade is a finding, reported as a nonzero exit - "clean" here
        # means "well-formed JSON and no uncaught exception", not exit 0.
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["grade"], "hypothesis")
        self.assertTrue(payload["downgraded"])
        # This is the assertion that KeyErrors pre-fix: `cmd_claim` reads
        # `data["claimed_grade"]` into this "claimed" field.
        self.assertEqual(payload["claimed"], "verified")


if __name__ == "__main__":
    unittest.main()

"""A PASS verdict names what it did not check as empty, and payload files decode strictly."""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_strictjson import strict_loads  # noqa: E402
from godmode_runtime.godmode_verdict import record_verdict  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class StrictLoadsTests(unittest.TestCase):
    ALLOWED = frozenset({"claim", "value"})

    def test_duplicate_key_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            strict_loads('{"claim": "a", "claim": "b", "value": 1}', self.ALLOWED)

    def test_unknown_field_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            strict_loads('{"claim": "a", "value": 1, "extra": true}', self.ALLOWED)

    def test_trailing_data_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            strict_loads('{"claim": "a", "value": 1} {"more": 1}', self.ALLOWED)

    def test_clean_payload(self) -> None:
        self.assertEqual(strict_loads('{"claim": "a", "value": 1}', self.ALLOWED)["value"], 1)


class VerdictRulesTests(unittest.TestCase):
    def _witness(self, project: Path) -> str:
        path = project / "witness.txt"; path.write_text("ok\n", encoding="utf-8"); return f"file:{path.name}"

    def test_pass_with_not_checked_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                record_verdict(archive, project, "it works", "yes", self._witness(project),
                               f"{sys.executable} -c \"import sys; sys.exit(0)\"", not_checked=["the Windows leg"])
            self.assertIn("not_checked", str(ctx.exception))

    def test_witness_equal_to_checker_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cmd = f"{sys.executable} -c \"import sys; sys.exit(0)\""
            with self.assertRaises(ArchiveError):
                record_verdict(archive, project, "it works", "yes", f"cmd:{cmd}", cmd)

    def test_criterion_without_evidence_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_verdict(archive, project, "it works", "yes", self._witness(project),
                               f"{sys.executable} -c \"import sys; sys.exit(0)\"", criteria={"tests green": ""})

    def test_pass_with_everything_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_verdict(archive, project, "it works", "yes", self._witness(project),
                                    f"{sys.executable} -c \"import sys; sys.exit(0)\"",
                                    checked=["exit code"], criteria={"tests green": "cmd exit 0"})
            self.assertEqual(record["data"]["checked"], ["exit code"])
            self.assertEqual(record["data"]["not_checked"], [])


class RawAppendInvariantTests(unittest.TestCase):
    """Review finding 1 (BLOCKING): N-11's three rules mirrored in
    `godmode_invariants._verdict_invariants`, modeled on
    `tests/test_tool_error_gate.py`'s `RawAppendDefenseInDepthTests` - a
    hand-built `data` dict pushed straight through `archive.append`, never
    through `record_verdict`, must still be held to the same three rules."""

    _BASE = {
        "claim": "x", "claimed_value": "1",
        "witness": {"kind": "file", "ref": "witness.txt"},
        "disposition": "confirmed", "run_state": "terminated",
        "acquitted_by": "independent",
    }

    def test_raw_confirmed_with_not_checked_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}],
                     "not_checked": ["the Windows leg"]},
                    evidence=[],
                )

    def test_raw_confirmed_with_blank_criterion_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}],
                     "criteria": {"tests green": ""}},
                    evidence=[],
                )

    def test_raw_confirmed_with_checker_equal_to_witness_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "witness": {"kind": "cmd", "ref": "true"},
                     "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}]},
                    evidence=[],
                )

    def test_raw_confirmed_with_checker_equal_to_witness_modulo_spacing_is_refused(self) -> None:
        """Re-review finding B: the invariant used to compare with a raw
        `==`, so an extra space between witness ref and checker command
        evaded it even though `record_verdict` already refused the exact
        same pair on the normal path (finding 2)."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "witness": {"kind": "cmd", "ref": "true  --x"},
                     "checks": [{"checker": "true --x", "exit": 0, "disposition": "confirmed"}]},
                    evidence=[],
                )

    def test_raw_non_confirmed_with_checker_equal_to_witness_is_refused(self) -> None:
        """Final review S1: the witness/checker rule is unconditional in
        `record_verdict` (checked before any fold ever runs), so a raw
        append with a non-`confirmed` disposition (here `witness-malformed`)
        must be refused too - the invariant used to gate this rule on
        `disposition == "confirmed"` and let it through unrefused."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "disposition": "witness-malformed",
                     "witness": {"kind": "cmd", "ref": "true"},
                     "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}]},
                    evidence=[],
                )

    def test_raw_confirmed_with_non_dict_criteria_is_refused(self) -> None:
        """Re-review finding C: a `criteria` that is not a dict (a list, a
        string) used to skip the blank-evidence check silently instead of
        being refused as malformed."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {**self._BASE,
                     "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}],
                     "criteria": ["tests green"]},
                    evidence=[],
                )

    def test_raw_confirmed_with_everything_named_is_accepted(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            record = archive.append(
                "verdict", "raw",
                {**self._BASE,
                 "checks": [{"checker": "true", "exit": 0, "disposition": "confirmed"}],
                 "not_checked": [], "criteria": {"tests green": "cmd exit 0"}},
                evidence=[],
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")


class VerdictPayloadCLITests(unittest.TestCase):
    """CLI-layer coverage for review findings 3/4/5/6 and Q1 -
    `godmode_console.py`'s `--payload`/`--criterion` wiring, exercised
    through `console.main` in-process (no subprocess needed)."""

    def _witness(self, project: Path) -> None:
        (project / "witness.txt").write_text("ok\n", encoding="utf-8")

    def _main(self, argv: list[str]) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            code = console.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_missing_flag_message_names_only_what_is_missing(self) -> None:
        """Finding 3: only --checker is absent; the refusal must name it,
        not fall back to listing all four."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--claim", "x", "--value", "y", "--witness", "file:witness.txt",
            ])
            self.assertEqual(code, 1)
            self.assertIn("--checker", output)
            self.assertNotIn("--claim,", output)

    def test_payload_checked_as_string_is_refused(self) -> None:
        """Finding 4/coordinator ruling: 'checked' must be a list of
        strings, not silently exploded from a string into one-char items."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            payload_path = project / "verdict.json"
            payload_path.write_text(json.dumps({
                "claim": "x", "value": "y", "witness": "file:witness.txt",
                "checker": "true", "checked": "exit code",
            }), encoding="utf-8")
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--payload", str(payload_path),
            ])
            self.assertEqual(code, 2)
            self.assertIn("checked", output)
            self.assertIn("list of strings", output)

    def test_payload_criteria_not_dict_str_str_is_refused(self) -> None:
        """Coordinator ruling: 'criteria' must be a dict of str to str."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            payload_path = project / "verdict.json"
            payload_path.write_text(json.dumps({
                "claim": "x", "value": "y", "witness": "file:witness.txt",
                "checker": "true", "criteria": {"tests green": 1}},
            ), encoding="utf-8")
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--payload", str(payload_path),
            ])
            self.assertEqual(code, 2)
            self.assertIn("criteria", output)

    def test_missing_payload_file_exits_with_clean_error_not_traceback(self) -> None:
        """Q1: a missing/unreadable --payload file is the CLI's normal
        exit-2 error vocabulary, never a raw traceback at exit 1."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--payload", str(project / "nope.json"),
            ])
            self.assertEqual(code, 2)
            self.assertIn("ArchiveError", output)
            self.assertNotIn("Traceback", output)

    def test_non_utf8_payload_file_exits_with_clean_error_not_traceback(self) -> None:
        """Re-review finding A (the one residual of Q1): a non-UTF-8
        payload file (e.g. a UTF-16LE redirect from Windows PowerShell 5.1)
        used to escape as a raw UnicodeDecodeError traceback at exit 1."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            payload_path = project / "verdict.json"
            payload_path.write_bytes('{"claim": "x"}'.encode("utf-16"))
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--payload", str(payload_path),
            ])
            self.assertEqual(code, 2)
            self.assertIn("ArchiveError", output)
            self.assertNotIn("Traceback", output)

    def test_duplicate_criterion_name_is_refused(self) -> None:
        """Finding 5: a repeated --criterion name must not silently
        overwrite the earlier value."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--claim", "x", "--value", "y", "--witness", "file:witness.txt",
                "--checker", "true", "--criterion", "a=1", "--criterion", "a=2",
            ])
            self.assertEqual(code, 2)
            self.assertIn("twice", output)

    def test_empty_criterion_name_is_refused(self) -> None:
        """Finding 5: --criterion =evidence has no name."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--claim", "x", "--value", "y", "--witness", "file:witness.txt",
                "--checker", "true", "--criterion", "=evidence",
            ])
            self.assertEqual(code, 2)

    def test_payload_criteria_and_flag_criterion_together_is_refused(self) -> None:
        """Finding 6: --payload's 'criteria' and --criterion on the same
        command line used to silently drop --criterion; now refused."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            payload_path = project / "verdict.json"
            payload_path.write_text(json.dumps({
                "claim": "x", "value": "y", "witness": "file:witness.txt",
                "checker": "true", "criteria": {"a": "b"}},
            ), encoding="utf-8")
            code, output = self._main([
                "--project", str(project), "verdict", "record",
                "--payload", str(payload_path), "--criterion", "c=d",
            ])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

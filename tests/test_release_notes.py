"""`godmode release-notes build|check`: a note is derived from the
changelog and held to its shape."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from godmode_runtime.godmode_release_notes import build_notes, check_notes, notes_path  # noqa: E402

CHANGELOG = """# Changelog

## [Unreleased]

## [1.2.0] - 2026-09-10

### Added

- Perimeter checks. `godmode perimeter add` declares a boot command; `tests/test_perimeter.py` pins it.
- The scope gate blocks a done claim while asks are open.

### Fixed

- A bare `godmode status` prints the survey.

## [1.1.0] - 2026-09-01

### Added

- Older thing.
"""


class _ProjectHelpers(unittest.TestCase):
    """Shared fixture builders - not itself a test case with test_* methods."""

    def _project(self, changelog: str = CHANGELOG) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="godmode-notes-")
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return root

    def _baseline(self, root: Path, version: str, *, n: int = 21,
                   fast_ms: float = 100.0, escalate_ms: float = 400.0) -> None:
        (root / "benchmarks").mkdir(parents=True, exist_ok=True)
        (root / "benchmarks" / "gate_latency_baseline.json").write_text(json.dumps({
            "schema": "godmode-gate-latency-baseline-v1", "n": n, "runtime_version": version,
            "phases": {"fast_allow": {"p95_ms": fast_ms}, "escalate": {"p95_ms": escalate_ms}},
        }), encoding="utf-8")


class ReleaseNotesTests(_ProjectHelpers):
    def test_build_derives_the_note_from_the_changelog_section(self) -> None:
        root = self._project()
        report = build_notes(root, "1.2.0")
        self.assertTrue(report["written"], report)
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertIn("# Godmode v1.2.0", text)
        self.assertIn("## Added", text)
        self.assertIn("## Fixed", text)
        self.assertIn("## Verifying", text)
        self.assertIn("python -m unittest tests.test_perimeter", text)
        self.assertNotIn("Older thing", text)
        self.assertEqual(check_notes(root, "1.2.0")["ok"], True)

    def test_build_refuses_without_a_section_or_over_an_existing_note(self) -> None:
        root = self._project()
        self.assertFalse(build_notes(root, "9.9.9")["written"])
        build_notes(root, "1.2.0")
        self.assertFalse(build_notes(root, "1.2.0")["written"])
        self.assertTrue(build_notes(root, "1.2.0", force=True)["written"])

    def test_check_names_a_missing_note_narration_and_an_uncovered_entry(self) -> None:
        root = self._project()
        missing = check_notes(root, "1.2.0")
        self.assertFalse(missing["ok"])
        self.assertIn("note-missing", [f["check"] for f in missing["findings"]])
        path = notes_path(root, "1.2.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Godmode v1.2.0\n\nThe batch release. After three cuts we pushed it.\n\n"
                        "## Added\n\n- Perimeter checks.\n\n## Verifying\n\n- run it\n", encoding="utf-8")
        report = check_notes(root, "1.2.0")
        codes = [f["check"] for f in report["findings"]]
        self.assertIn("release-note-narration", codes)
        self.assertIn("entry-uncovered", codes)  # the scope gate and the bare status are not in the note
        path.write_text("# Godmode v1.2.0\n\n## Added\n\n- Perimeter checks.\n\n## Changed\n\n## Verifying\n\n- run it\n",
                        encoding="utf-8")
        report = check_notes(root, "1.2.0")
        self.assertIn("empty-section", [f["check"] for f in report["findings"]])
        self.assertFalse(report["ok"])


class BenchmarkLineTests(_ProjectHelpers):
    """G-9: `build_notes` carries the gate-latency p95 line under a
    `## Benchmarks` section when this version's baseline exists;
    `check_notes` refuses a note that lacks it. Baselines here are
    fabricated by `_baseline` - never a live measurement."""

    def test_build_includes_the_line_when_the_versions_baseline_exists(self) -> None:
        root = self._project()
        self._baseline(root, "1.2.0", n=21, fast_ms=100.0, escalate_ms=400.0)
        report = build_notes(root, "1.2.0")
        self.assertTrue(report["written"], report)
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertIn("## Benchmarks", text)
        self.assertIn("Gate latency (p95, n=21): fast_allow 100 ms, escalate 400 ms", text)
        self.assertEqual(check_notes(root, "1.2.0")["ok"], True)

    def test_build_omits_the_section_without_a_matching_baseline(self) -> None:
        root = self._project()  # no benchmarks/ directory at all
        build_notes(root, "1.2.0")
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertNotIn("## Benchmarks", text)

    def test_build_omits_the_section_when_the_baseline_is_for_another_version(self) -> None:
        root = self._project()
        self._baseline(root, "9.9.9")  # a different version's baseline
        build_notes(root, "1.2.0")
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertNotIn("## Benchmarks", text)
        self.assertEqual(check_notes(root, "1.2.0")["ok"], True)

    def test_check_refuses_a_note_missing_the_line_when_the_baseline_exists(self) -> None:
        root = self._project()
        self._baseline(root, "1.2.0", n=21, fast_ms=100.0, escalate_ms=400.0)
        path = notes_path(root, "1.2.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Godmode v1.2.0\n\n## Added\n\n- Perimeter checks.\n\n"
                         "- The scope gate blocks a done claim while asks are open.\n\n"
                         "## Fixed\n\n- A bare `godmode status` prints the survey.\n\n"
                         "## Verifying\n\n- run it\n", encoding="utf-8")
        report = check_notes(root, "1.2.0")
        self.assertIn("benchmark-line-missing", [f["check"] for f in report["findings"]])
        self.assertFalse(report["ok"])

    def test_build_omits_the_section_when_the_baseline_carries_no_n(self) -> None:
        """`_benchmark_baseline` requires `n` (mirroring `gate_latency.
        MIN_SAMPLES`) so `_benchmark_line` can never be asked to print
        `n=?` - a baseline missing its own sample count is treated as no
        baseline at all."""
        root = self._project()
        (root / "benchmarks").mkdir(parents=True, exist_ok=True)
        (root / "benchmarks" / "gate_latency_baseline.json").write_text(json.dumps({
            "schema": "godmode-gate-latency-baseline-v1", "runtime_version": "1.2.0",
            "phases": {"fast_allow": {"p95_ms": 100.0}, "escalate": {"p95_ms": 400.0}},
        }), encoding="utf-8")
        build_notes(root, "1.2.0")
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertNotIn("## Benchmarks", text)
        self.assertNotIn("n=?", text)

    def test_build_omits_the_section_when_the_baseline_n_is_below_the_floor(self) -> None:
        root = self._project()
        self._baseline(root, "1.2.0", n=5, fast_ms=100.0, escalate_ms=400.0)
        build_notes(root, "1.2.0")
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertNotIn("## Benchmarks", text)
        self.assertNotIn("n=?", text)

    def test_check_does_not_require_the_line_when_baseline_is_for_another_version(self) -> None:
        root = self._project()
        self._baseline(root, "9.9.9")
        path = notes_path(root, "1.2.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Godmode v1.2.0\n\n## Added\n\n- Perimeter checks.\n\n"
                         "- The scope gate blocks a done claim while asks are open.\n\n"
                         "## Fixed\n\n- A bare `godmode status` prints the survey.\n\n"
                         "## Verifying\n\n- run it\n", encoding="utf-8")
        report = check_notes(root, "1.2.0")
        self.assertNotIn("benchmark-line-missing", [f["check"] for f in report["findings"]])


if __name__ == "__main__":
    unittest.main()

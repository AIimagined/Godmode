"""CX-6: the release gate.

No host may be documented as enforced/`HARD` in `README.md` or
`docs/CAPABILITY-COVERAGE.md` unless (a) this e2e suite carries a scenario
class that actually exercises that host, AND (b) the negative control
(`DisabledHookScenarioTests` - a hook with no live proof, or a previously
proven one marked uninstalled, must never grade `HARD`) exists and passes.

As of this task, no host row in either document claims `HARD`/"enforced" by
default - both documents describe the MECHANISM (the five-level scale) and
name each host's honestly-measured tier (`PARTIAL` for this checkout's own
Claude install, `not independently live-probed` for Codex/Grok,
`UNAVAILABLE` for the three adapter-only hosts) rather than asserting a
blanket claim. This test is a REGRESSION gate for that honesty: it fails
the moment a future edit adds a per-host `HARD`/"enforced" claim without the
e2e coverage and passing negative control to back it, not a claim about
today's prose (which currently trips nothing, by design).

**Fix round 1** (`.superpowers/sdd/2026-08-16-cx/task-cx6-review.md`)
fixed two Critical holes in this gate's own matching logic, both
demonstrated live by the reviewer against the real file:

- **C1** - the "e2e backing" check used to be `marker in suite_source`: a
  bare substring search over `test_host_e2e.py`'s raw text, satisfied by a
  code comment (`# TODO: revisit cursor blink rate...`) exactly as well as
  real scenario coverage. Replaced with `host_scenario_registry.
  host_is_backed`: a checked-in, hand-declared registry resolved by REAL
  IMPORT and `unittest.TestLoader` introspection - see that module's own
  docstring. `ComentDecoyDoesNotSatisfyBackingTests` below is the red-first
  repro, kept green after the fix.
- **C2** - combined README/coverage rows (`"OpenCode, Cursor, Gemini CLI"`)
  used to be matched by checking each `_KNOWN_HOSTS` name as a SUBSTRING of
  the whole label, in tuple order, breaking on the first hit - so a claim
  anywhere in that row's text was always attributed to whichever host
  happened to be checked first (`"Cursor"`, alphabetically ahead of neither
  `"OpenCode"` nor `"Gemini CLI"` in the tuple, but a substring of the
  combined label regardless of which host the prose was actually about).
  `_host_table_rows` now SPLITS the label on its own separator and matches
  each segment EXACTLY (case-insensitively), never by containment - a
  combined row that carries an enforcement claim anywhere in its text is
  now attributed to EVERY host named in that row, independently, which is
  the fail-closed direction (over-attributing a claim to a host is safe;
  silently dropping one is not). `CombinedRowMisattributionTests` below is
  the red-first repro.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
README = PLUGIN_ROOT / "README.md"
COVERAGE = PLUGIN_ROOT / "docs" / "CAPABILITY-COVERAGE.md"
E2E_HOST_SUITE = Path(__file__).resolve().parent / "test_host_e2e.py"

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import host_scenario_registry as registry  # noqa: E402

# The six documented per-host names this project's own tables ever name a
# ROW after (never "godmode", "the plugin", or a mechanism name - those are
# not hosts and a mention of `HARD` near them is not a per-host claim).
_KNOWN_HOSTS = ("Claude Code", "Codex", "Grok", "Cursor", "Gemini CLI", "OpenCode")

# A markdown table row: `| **Host Name** | ... |`. Only rows shaped like
# this are read as a per-host claim - prose paragraphs that MENTION a host
# name near the word "HARD" (this file's own module docstring does exactly
# that) are not table rows and are correctly ignored.
_TABLE_ROW = re.compile(r"^\|\s*\*\*([^*|]+)\*\*\s*\|(.*)\|\s*$")

_ENFORCED_CLAIM = re.compile(r"\bHARD\b|\benforced\b", re.IGNORECASE)

# C2 fix: a combined bold cell's own internal separator - "OpenCode, Cursor,
# Gemini CLI" splits on ",". A "/" is accepted too (no shipped row uses it
# today, but a future row might, and splitting on both costs nothing).
_LABEL_SEPARATOR = re.compile(r"[,/]")


def _host_table_rows(path: Path) -> list[tuple[str, str]]:
    """`[(host_label, full_row_text)]` for every markdown table row in
    `path` whose bold cell names one or more of `_KNOWN_HOSTS`.

    C2 fix: the bold cell is split on its own separator and each SEGMENT is
    matched to a known host by EXACT (case-insensitive) equality, never by
    substring containment - a combined cell contributes one `(host, row)`
    pair per host it names, all pointing at the SAME row text, so a claim
    anywhere in that row is independently evaluated against every host it
    names rather than silently attributed to only one of them by tuple
    order (the reviewer's C2 repro, kept green by
    `CombinedRowMisattributionTests` below).
    """
    rows: list[tuple[str, str]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW.match(line.strip())
        if not match:
            continue
        label = match.group(1).strip()
        segments = [seg.strip() for seg in _LABEL_SEPARATOR.split(label) if seg.strip()]
        for segment in segments:
            for known in _KNOWN_HOSTS:
                if known.lower() == segment.lower():
                    rows.append((known, line))
                    break
    return rows


def _hosts_claimed_enforced(readme: Path = README, coverage: Path = COVERAGE
                            ) -> dict[str, list[str]]:
    """`{host: [source_lines_making_the_claim]}` - only rows whose text
    itself carries `HARD`/"enforced", not the surrounding document. Paths
    are parameters (defaulting to the real files) so tests can feed a
    fabricated row without touching the real docs."""
    claims: dict[str, list[str]] = {}
    for path in (readme, coverage):
        for host, row in _host_table_rows(path):
            if _ENFORCED_CLAIM.search(row):
                claims.setdefault(host, []).append(f"{path.name}: {row.strip()}")
    return claims


_HOST_TO_E2E_MARKER = {
    "Claude Code": "claude",
    "Codex": "codex",
    "Grok": "grok",
    "Cursor": "cursor",
    "Gemini CLI": "gemini",
}


class ReleaseGateTests(unittest.TestCase):
    def test_no_host_row_claims_hard_or_enforced_without_e2e_backing(self) -> None:
        claims = _hosts_claimed_enforced()
        if not claims:
            # The honest, expected state today (see module docstring) - the
            # gate has nothing to enforce, which is not the same as never
            # having run: the assertions below still execute, over an empty
            # dict, so a future claim is caught the moment it appears.
            return
        for host, rows in claims.items():
            marker = _HOST_TO_E2E_MARKER.get(host)
            with self.subTest(host=host):
                self.assertIsNotNone(
                    marker, f"{host} claims HARD/enforced but has no known e2e host marker")
                # C1 fix: STRUCTURAL backing via `host_scenario_registry.
                # host_is_backed` - real import + unittest introspection,
                # never a substring search over `test_host_e2e.py`'s text.
                backed, detail = registry.host_is_backed(marker)
                self.assertTrue(
                    backed,
                    f"{host} claims HARD/enforced in {rows!r} but is not structurally "
                    f"backed by host_scenario_registry.HOST_SCENARIO_REGISTRY: {detail}")

    def test_the_negative_control_exists_and_passes(self) -> None:
        """`DisabledHookScenarioTests` (no proof, and a previously-proven
        hook later marked uninstalled) must exist in the e2e suite and pass
        - the one control every enforced/`HARD` claim anywhere in this
        project's docs is required to be backed by, per this file's own
        module docstring."""
        import test_host_e2e  # noqa: PLC0415 - deliberately local, see module docstring

        self.assertTrue(
            hasattr(test_host_e2e, "DisabledHookScenarioTests"),
            "the negative control class must exist in tests/e2e/test_host_e2e.py")
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(test_host_e2e.DisabledHookScenarioTests)
        self.assertGreater(suite.countTestCases(), 0, "the negative control has no tests")
        result = unittest.TestResult()
        suite.run(result)
        self.assertTrue(
            result.wasSuccessful(),
            f"the negative control (disabled hook => not HARD) must pass: "
            f"{result.failures + result.errors}")


class CommentDecoyDoesNotSatisfyBackingTests(unittest.TestCase):
    """Fix round 1, C1: red-first, kept green. The reviewer's exact repro -
    a fake file body containing a host's name ONLY inside an unrelated
    comment - used to satisfy the old `marker in suite_source` check
    identically to real coverage. The new mechanism never reads file text
    at all, so this repro cannot influence it even in principle; the tests
    below prove that by construction, not by re-running the old check."""

    DECOY_SOURCE = (
        "class DisabledHookScenarioTests(unittest.TestCase):\n"
        "    def test_a_hook_with_no_proof_at_all_never_grades_hard(self): pass\n"
        "# TODO: revisit cursor blink rate in the demo GIF, unrelated to this suite\n"
    )

    def test_the_decoy_text_itself_would_have_fooled_the_old_bare_substring_check(self) -> None:
        """Sanity check on the repro itself: the OLD vulnerability really
        existed - `"cursor" in DECOY_SOURCE` is True, proving this decoy is
        the same shape the reviewer used, not a weaker stand-in."""
        self.assertIn("cursor", self.DECOY_SOURCE)

    def test_a_host_with_no_registry_entry_is_never_backed_however_much_decoy_text_exists(
        self,
    ) -> None:
        """The new mechanism, given a host that genuinely has no registered
        coverage, reports unbacked - regardless of what text happens to
        exist anywhere on disk (this decoy string is never even read by
        `host_is_backed`, which is the point: there is no code path from
        "text on disk" to "backed" left to exploit)."""
        fake_registry = {"decoy-host": (("test_host_e2e", "NoSuchScenarioClassAtAll"),)}
        backed, detail = registry.host_is_backed("decoy-host", registry=fake_registry)
        self.assertFalse(backed)
        self.assertIn("does not exist", detail)

    def test_a_registry_entry_naming_a_real_class_with_zero_test_methods_fails_closed(
        self,
    ) -> None:
        """A registry pointing at a REAL, IMPORTABLE class that simply has
        no test methods (the closest a registry entry could get to "just a
        comment") still fails - `unittest.TestCase` itself, the base class,
        has no `test_*` methods of its own."""
        fake_registry = {"decoy-host": (("unittest", "TestCase"),)}
        backed, detail = registry.host_is_backed("decoy-host", registry=fake_registry)
        self.assertFalse(backed)
        self.assertIn("zero discoverable test methods", detail)

    def test_real_hosts_are_genuinely_backed_by_real_nonempty_test_cases(self) -> None:
        """Positive control: every host this project's docs could name is
        backed today, proven the same way a false claim would be caught -
        not asserted, introspected."""
        for host in ("claude", "codex", "grok", "cursor", "gemini"):
            with self.subTest(host=host):
                backed, detail = registry.host_is_backed(host)
                self.assertTrue(backed, detail)


class CombinedRowMisattributionTests(unittest.TestCase):
    """Fix round 1, C2: red-first, kept green. The reviewer's exact repro -
    a combined bold cell naming three hosts, with a claim in the row's
    prose that names only ONE of them by name - used to attribute the claim
    to whichever host's name happened to substring-match first in
    `_KNOWN_HOSTS` tuple order (always `"Cursor"`, never the host the claim
    was actually about), and silently drop the other two hosts entirely."""

    def _write_fake_doc(self, tmp_path: Path, row: str) -> Path:
        doc = tmp_path / "fake-combined-row.md"
        doc.write_text(row + "\n", encoding="utf-8")
        return doc

    def test_a_combined_row_yields_one_pair_per_named_host_not_only_the_first_match(
        self,
    ) -> None:
        import tempfile

        row = "| **OpenCode, Cursor, Gemini CLI** | shipped | plain description |"
        with tempfile.TemporaryDirectory() as raw:
            doc = self._write_fake_doc(Path(raw), row)
            rows = _host_table_rows(doc)
        hosts_found = {host for host, _ in rows}
        # The OLD first-match-wins behavior would have produced only
        # {"Cursor"} here - proven directly, not asserted, by comparing
        # against what a substring-in-tuple-order scan would have returned.
        old_behavior_would_find = None
        for known in _KNOWN_HOSTS:
            if known.lower() in "opencode, cursor, gemini cli":
                old_behavior_would_find = known
                break
        self.assertEqual(old_behavior_would_find, "Cursor",
                         "confirms the OLD bug's own failure mode, for contrast")
        self.assertEqual(hosts_found, {"OpenCode", "Cursor", "Gemini CLI"})

    def test_the_reviewers_gemini_claims_hard_repro_attributes_to_every_named_host(
        self,
    ) -> None:
        """The reviewer's exact repro row: the claim's own prose names
        Gemini CLI specifically, but the combined cell also names Cursor
        and OpenCode. The fix's fail-closed design (Important: evaluate
        the WHOLE row for every host it names, not just the host the claim
        is grammatically about) means all three are flagged - never zero,
        never only the wrong one."""
        import tempfile

        row = ("| **OpenCode, Cursor, Gemini CLI** | adapters | Gemini CLI's pre-tool "
              "boundary is now HARD-enforced; Cursor and OpenCode remain UNAVAILABLE. |")
        with tempfile.TemporaryDirectory() as raw:
            doc = self._write_fake_doc(Path(raw), row)
            claims = _hosts_claimed_enforced(readme=doc, coverage=doc)
        self.assertEqual(set(claims), {"OpenCode", "Cursor", "Gemini CLI"})
        # And OpenCode, which has no known e2e marker at all, correctly
        # fails the gate outright rather than being silently skipped -
        # exercised directly here since the real README never claims this.
        marker = _HOST_TO_E2E_MARKER.get("OpenCode")
        self.assertIsNone(marker, "OpenCode structurally cannot back a HARD claim")

    def test_the_real_shipped_combined_row_is_read_correctly_today(self) -> None:
        """The REAL `README.md` row this fix must parse correctly (review's
        own citation, `README.md:237`, unchanged by this fix round) -
        confirms the fix against the actual shipped file, not only a
        synthetic one."""
        rows = _host_table_rows(README)
        hosts_in_combined_row = {
            host for host, row in rows
            if "OpenCode" in row and "Cursor" in row and "Gemini CLI" in row
        }
        self.assertEqual(hosts_in_combined_row, {"OpenCode", "Cursor", "Gemini CLI"})


if __name__ == "__main__":
    unittest.main()

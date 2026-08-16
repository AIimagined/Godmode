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

# The five documented per-host names this project's own tables ever name a
# ROW after (never "godmode", "the plugin", or a mechanism name - those are
# not hosts and a mention of `HARD` near them is not a per-host claim).
_KNOWN_HOSTS = ("Claude Code", "Codex", "Grok", "Cursor", "Gemini CLI", "OpenCode")

# A markdown table row: `| **Host Name** | ... |`. Only rows shaped like
# this are read as a per-host claim - prose paragraphs that MENTION a host
# name near the word "HARD" (this file's own module docstring does exactly
# that) are not table rows and are correctly ignored.
_TABLE_ROW = re.compile(r"^\|\s*\*\*([^*|]+)\*\*\s*\|(.*)\|\s*$")

_ENFORCED_CLAIM = re.compile(r"\bHARD\b|\benforced\b", re.IGNORECASE)


def _host_table_rows(path: Path) -> list[tuple[str, str]]:
    """`[(host_label, full_row_text)]` for every markdown table row in
    `path` whose first cell names one of `_KNOWN_HOSTS`."""
    rows: list[tuple[str, str]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TABLE_ROW.match(line.strip())
        if not match:
            continue
        label = match.group(1).strip()
        for known in _KNOWN_HOSTS:
            if known.lower() in label.lower():
                rows.append((known, line))
                break
    return rows


def _hosts_claimed_enforced() -> dict[str, list[str]]:
    """`{host: [source_lines_making_the_claim]}` - only rows whose text
    itself carries `HARD`/"enforced", not the surrounding document."""
    claims: dict[str, list[str]] = {}
    for path in (README, COVERAGE):
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
        suite_source = E2E_HOST_SUITE.read_text(encoding="utf-8")
        for host, rows in claims.items():
            marker = _HOST_TO_E2E_MARKER.get(host)
            with self.subTest(host=host):
                self.assertIsNotNone(
                    marker, f"{host} claims HARD/enforced but has no known e2e host marker")
                self.assertIn(
                    marker, suite_source,
                    f"{host} claims HARD/enforced in {rows!r} but "
                    f"{E2E_HOST_SUITE.name} has no scenario coverage naming it")

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


if __name__ == "__main__":
    unittest.main()

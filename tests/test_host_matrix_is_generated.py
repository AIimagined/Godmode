"""`docs/HOST-FEATURE-REACH.md` cannot silently drift from the code (R-4),
and the generator itself refuses a host row that cites neither a reference
nor a replicating test (R-0's guard, NS-10b's own capability enum feeding
the feature-reach grid).

The doc keeps its own prose (intro, root-causes narrative, the verb-layer
census, the dated status log) as a template outside one marker pair
(`godmode_reach.MATRIX_BEGIN`/`MATRIX_END`); `generate_matrix_document`
only ever rewrites what sits between them.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import argparse

from godmode_runtime import godmode_reach as reach  # noqa: E402
from godmode_runtime.godmode_console import cmd_hooks  # noqa: E402

DOC_PATH = PLUGIN_ROOT / "docs" / "HOST-FEATURE-REACH.md"


class HostMatrixDriftTests(unittest.TestCase):
    def test_committed_doc_matches_the_generator(self) -> None:
        committed = DOC_PATH.read_text(encoding="utf-8")
        generated = reach.generate_matrix_document(committed)
        self.assertEqual(
            generated, committed,
            "docs/HOST-FEATURE-REACH.md is stale - regenerate with "
            "`godmode hooks status --matrix --write`",
        )

    def test_the_doc_carries_the_marker_pair(self) -> None:
        committed = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn(reach.MATRIX_BEGIN, committed)
        self.assertIn(reach.MATRIX_END, committed)
        self.assertLess(committed.index(reach.MATRIX_BEGIN),
                         committed.index(reach.MATRIX_END))

    def test_the_generated_body_names_every_host_and_feature(self) -> None:
        body = reach.render_matrix_tables()
        for host in reach.HOSTS:
            self.assertIn(host, body, host)
        for feature in reach.FEATURES:
            self.assertIn(feature, body, feature)

    def test_generator_raises_without_a_marker_pair(self) -> None:
        with self.assertRaises(ValueError):
            reach.generate_matrix_document("# no markers here\n")


class MatrixRefusesAnUncitedRowTests(unittest.TestCase):
    """R-0: a host with neither a reference nor a replication test blocks
    the whole matrix from being generated - never a silently-printed
    "unverifiable" row."""

    def test_validate_reach_citations_is_clean_today(self) -> None:
        self.assertEqual(reach.validate_reach_citations(), [])

    def test_a_seeded_row_without_reference_or_test_is_refused(self) -> None:
        bare = {"cursor": {"reference": "", "replication_test": "", "next_probe": ""}}
        with mock.patch.dict(reach.REACH, bare):
            self.assertEqual(reach.validate_reach_citations(), ["cursor"])
            with self.assertRaises(reach.MatrixGuardError):
                reach.render_matrix_tables()
            with self.assertRaises(reach.MatrixGuardError):
                reach.generate_matrix_document(DOC_PATH.read_text(encoding="utf-8"))

    def test_a_row_naming_only_a_reference_is_not_refused(self) -> None:
        with mock.patch.dict(
            reach.REACH,
            {"cursor": {"reference": "ledger:207", "replication_test": "", "next_probe": ""}},
        ):
            self.assertEqual(reach.validate_reach_citations(), [])
            reach.render_matrix_tables()  # must not raise

    def test_a_row_naming_only_a_replication_test_is_not_refused(self) -> None:
        with mock.patch.dict(
            reach.REACH,
            {"cursor": {"reference": "",
                        "replication_test": "tests.test_x.T.test_y",
                        "next_probe": ""}},
        ):
            self.assertEqual(reach.validate_reach_citations(), [])
            reach.render_matrix_tables()  # must not raise

    def test_claude_and_grok_need_no_citation(self) -> None:
        # Both are proven by a chronicled live session per the doc's own
        # Status log, not by replication - the static guard exempts them.
        self.assertNotIn("claude", reach.MATRIX_CITATION_HOSTS)
        self.assertNotIn("grok", reach.MATRIX_CITATION_HOSTS)

    def test_a_shape_invalid_reference_does_not_satisfy_the_guard_alone(self) -> None:
        """Fix round 1, nit 4: `reference` must be shape-valid
        `ledger:<digits>`, not any truthy string."""
        with mock.patch.dict(
            reach.REACH,
            {"cursor": {"reference": "some-file.md", "replication_test": "", "next_probe": ""}},
        ):
            self.assertEqual(reach.validate_reach_citations(), ["cursor"])

    def test_a_shape_valid_reference_alone_satisfies_the_guard(self) -> None:
        with mock.patch.dict(
            reach.REACH,
            {"cursor": {"reference": "ledger:1", "replication_test": "", "next_probe": ""}},
        ):
            self.assertEqual(reach.validate_reach_citations(), [])


class LiveProofExemptionTests(unittest.TestCase):
    """Fix round 1, B1: `MATRIX_CITATION_HOSTS` is derived from `REACH`'s
    own `live_proof` field, never a hardcoded host-name tuple - and every
    hook host's row carries an honest `live_proof` value, never a blank."""

    def test_claude_and_grok_carry_a_live_proof_citation(self) -> None:
        self.assertTrue(reach.REACH["claude"]["live_proof"])
        self.assertTrue(reach.REACH["grok"]["live_proof"])
        self.assertIn("seq:", reach.REACH["claude"]["live_proof"])
        self.assertIn("seq:", reach.REACH["grok"]["live_proof"])

    def test_a_host_gains_exemption_the_moment_its_row_carries_live_proof(self) -> None:
        # The derivation, not a name literal, is what exempts a host: seed
        # cursor with a live_proof and it drops out of the citation set with
        # no code change beyond the data.
        with mock.patch.dict(reach.REACH, {"cursor": {**reach.REACH["cursor"],
                                                       "live_proof": "seq:1"}}):
            citation_hosts = tuple(
                host for host in reach.HOOK_HOSTS
                if not reach.REACH.get(host, {}).get("live_proof"))
            self.assertNotIn("cursor", citation_hosts)

    def test_the_reference_table_renders_a_live_proof_column(self) -> None:
        body = reach.render_matrix_tables()
        self.assertIn("Live proof", body)
        self.assertIn(reach._neutral_live_proof(reach.REACH["claude"]["live_proof"]), body)
        self.assertIn(reach._neutral_live_proof(reach.REACH["grok"]["live_proof"]), body)
        # The doc states what was proven and when, never the internal
        # archive sequence number that backs the claim.
        self.assertNotIn("seq:", body)


class ReferenceReadStateTests(unittest.TestCase):
    """Fix round 1, B3: a bare `reference` names an entry still to read
    (the private R-1 ledger table's own `import_verdict: unread` note for
    every row it backs) - only a reference paired with a passing
    `replication_test` is honestly rendered as read."""

    def test_a_bare_reference_reads_still_to_read(self) -> None:
        cell = reach._reference_cell({"reference": "ledger:99", "replication_test": ""})
        self.assertIn("still to read", cell)
        self.assertNotIn("(read)", cell)

    def test_a_reference_with_a_replication_test_reads_as_read(self) -> None:
        cell = reach._reference_cell(
            {"reference": "ledger:193", "replication_test": "tests.test_x.T.test_y"})
        self.assertIn("(read)", cell)

    def test_a_live_proof_host_needs_no_reference(self) -> None:
        cell = reach._reference_cell({"reference": "", "live_proof": "seq:1"})
        self.assertIn("live proof", cell)

    def test_todays_cursor_gemini_antigravity_rows_are_still_to_read(self) -> None:
        for host in ("cursor", "gemini", "antigravity"):
            self.assertIn("still to read", reach._reference_cell(reach.REACH[host]), host)

    def test_todays_codex_row_is_read(self) -> None:
        self.assertIn("(read)", reach._reference_cell(reach.REACH["codex"]))


class FeatureReachReasonsTableTests(unittest.TestCase):
    """Fix round 1, B2: every non-`yes` cell's reason is rendered - the
    doc's own "every 'no' here is a stated gap" line is now true of the
    generated block, not just the surrounding prose."""

    def test_every_non_yes_cell_appears_in_the_reasons_table(self) -> None:
        body = reach.render_matrix_tables()
        table = reach.reach_table()
        for host in reach.HOSTS:
            for feature in reach.FEATURES:
                cell = table[host][feature]
                if cell["status"] == "yes":
                    continue
                row = f"| {host} | {feature} | {cell['status']} | {cell['reason']}"
                self.assertIn(row, body, (host, feature))

    def test_a_capability_downgrade_reason_is_rendered(self) -> None:
        body = reach.render_matrix_tables()
        self.assertIn(
            "unreachable: gemini does not declare the additionalContext channel", body)


class MissingHostCapabilitiesEntryFailsLoudlyTests(unittest.TestCase):
    """Fix round 1, nit 2/3: a host declared in `HOSTS`/`_TABLE` with no
    `HOST_CAPABILITIES` entry must raise, never silently read as "declares
    nothing"."""

    def test_a_missing_host_raises_instead_of_reading_as_empty(self) -> None:
        from godmode_runtime import godmode_host_manifests as host_manifests

        with mock.patch.dict(host_manifests.HOST_CAPABILITIES, {}, clear=True):
            with self.assertRaises(KeyError):
                reach._capability_unreachable("claude", "advisories")
            with self.assertRaises(KeyError):
                reach._capabilities_table()


class HostCapabilitiesFeedTheGridTests(unittest.TestCase):
    """NS-10b: `godmode_reach.reach_table()` reads
    `godmode_host_manifests.HOST_CAPABILITIES`, not just `_TABLE`'s own
    hand-authored cells - a feature needing a channel the host does not
    declare reads unreachable before any live probe."""

    def test_gemini_has_no_message_channel_and_its_advisory_cells_read_no(self) -> None:
        from godmode_runtime import godmode_host_manifests as host_manifests

        gemini_channels = host_manifests.HOST_CAPABILITIES["gemini"]["stdout"]
        self.assertNotIn("additionalContext", gemini_channels)
        table = reach.reach_table()
        self.assertEqual(table["gemini"]["advisories"]["status"], "no")
        self.assertIn("unreachable", table["gemini"]["advisories"]["reason"])

    def test_a_cell_already_no_is_never_upgraded_by_the_capability_check(self) -> None:
        table = reach.reach_table()
        self.assertEqual(table["goose"]["pre-tool-gate"]["status"], "no")

    def test_declaring_every_channel_for_a_host_downgrades_nothing(self) -> None:
        from godmode_runtime import godmode_host_manifests as host_manifests

        with mock.patch.dict(
            host_manifests.HOST_CAPABILITIES,
            {"gemini": {**host_manifests.HOST_CAPABILITIES["gemini"],
                        "stdout": host_manifests.STDOUT_CHANNELS}},
        ):
            table = reach.reach_table()
        # advisories was downgraded only because the channel was missing;
        # once declared, the cell reverts to its authored value.
        self.assertEqual(table["gemini"]["advisories"]["status"], "partial")


class WriteWithoutMatrixRefusesTests(unittest.TestCase):
    """Fix round 1, nit 5: `hooks status --write` with no `--matrix` used to
    be silently accepted and ignored (the non-matrix branch never reads
    `--write` at all)."""

    def test_write_without_matrix_is_refused(self) -> None:
        args = argparse.Namespace(hooks_command="status", host="claude",
                                   git=False, matrix=False, write=True)
        result = cmd_hooks(args, runtime=None)
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--matrix", result.payload["error"])

    def test_write_with_matrix_is_unaffected(self) -> None:
        args = argparse.Namespace(hooks_command="status", host="claude",
                                   git=False, matrix=True, write=False)
        result = cmd_hooks(args, runtime=None)
        self.assertIn(result.payload["matrix"], ("current", "drifted"))


if __name__ == "__main__":
    unittest.main()

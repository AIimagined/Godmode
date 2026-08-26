"""Claim-gate enforcement on public surfaces.

The claim gate downgrades an unsupported claim - but only a claim that
went through `godmode claim`. Prose typed into README never met it. This
closes that gap with a definition and a scan.

A claim on a public surface is a sentence that carries a measured number
with a unit or percent, or a capability verb that promises an outcome
(prevents, guarantees, eliminates, ensures, blocks every, catches every).
It is covered when the same sentence names how to reproduce it - a
backticked `godmode` command, a test or docs path, or a commit - or when a
`claim` record in the archive carries the same text. Everything else on a
public surface is description, and description is not gated.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_claimscan import PUBLIC_SURFACES, scan_public_surfaces  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-scan-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            yield root, Chronicle(resolve_anchor(root))


class ClaimScanTests(unittest.TestCase):
    def test_a_bare_number_is_uncovered_and_a_cited_one_is_covered(self) -> None:
        with _project() as (root, archive):
            (root / "README.md").write_text(
                "Latency fell 60% in the last release.\n\n"
                "The suite runs 2637 tests (`godmode attest --status ran`).\n\n"
                "This tool prevents every regression.\n\n"
                "It keeps a record of what happened.\n",
                encoding="utf-8")
            report = scan_public_surfaces(root, archive)
        texts = [u["sentence"] for u in report["uncovered"]]
        self.assertIn("Latency fell 60% in the last release.", texts)
        self.assertIn("This tool prevents every regression.", texts)
        self.assertNotIn("The suite runs 2637 tests (`godmode attest --status ran`).", texts)
        self.assertEqual(report["scanned"], ["README.md"])
        self.assertEqual(report["verdict"], "uncovered")

    def test_a_recorded_claim_covers_its_sentence(self) -> None:
        with _project() as (root, archive):
            (root / "README.md").write_text("Latency fell 60%.\n", encoding="utf-8")
            archive.append("claim", "Latency fell 60%.", {"text": "Latency fell 60%.", "grade": "measured"})
            report = scan_public_surfaces(root, archive)
        self.assertEqual(report["uncovered"], [])
        self.assertEqual(report["verdict"], "covered")

    def test_description_is_not_gated(self) -> None:
        with _project() as (root, archive):
            (root / "README.md").write_text(
                "Godmode keeps a local record. It never phones home.\n", encoding="utf-8")
            report = scan_public_surfaces(root, archive)
        self.assertEqual(report["uncovered"], [])

    def test_scan_is_a_flag_on_claim_and_uncovered_reaches_the_exit(self) -> None:
        with _project() as (root, _archive):
            (root / "README.md").write_text("Saves 40% of tokens.\n", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "claim", "--scan"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "uncovered")

    def test_this_repository_s_own_public_surfaces_are_covered(self) -> None:
        # The enforcement itself: every public surface this plugin ships is
        # scanned with an empty archive, so coverage must come from the
        # prose naming its own reproduction.
        with tempfile.TemporaryDirectory() as state:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": state}, clear=False):
                archive = Chronicle(resolve_anchor(PLUGIN_ROOT))
                report = scan_public_surfaces(PLUGIN_ROOT, archive)
        self.assertEqual(sorted(report["scanned"]), sorted(
            s for s in PUBLIC_SURFACES if (PLUGIN_ROOT / s).exists()))
        self.assertEqual(report["uncovered"], [],
                         "\n".join(f"{u['file']}:{u['line']}: {u['sentence']}" for u in report["uncovered"]))


if __name__ == "__main__":
    unittest.main()

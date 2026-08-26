"""C-05: output-quality findings, severity-ranked, with guarded remediation.

Three detectors already produce quality findings in three shapes - docs
lint, the swallow scanner, the minimality report - and a reader who wants
"what is wrong with this tree, worst first" has to run all three and merge
by hand. `quality` folds them into one canonical, severity-ranked list.

The guard on remediation is structural, not a flag: every finding carries a
remedy as a *proposal*, and the command executes none of them. The test
proves both halves - the ranking, and that the tree is byte-identical after
the run.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
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
from godmode_runtime.godmode_quality import RANK, quality_report  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _seed(project: Path) -> None:
    # One high (a machine-specific path) and one medium (an open marker)
    # docs-lint finding, so the ranking has two severities to order.
    (project / "docs").mkdir(exist_ok=True)
    (project / "docs" / "notes.md").write_text(
        "See C:\\Users\\someone\\work for the files.\n\nTODO finish this section\n",
        encoding="utf-8")


class QualityReportTests(unittest.TestCase):
    def test_findings_are_ranked_worst_first(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed(project)
            report = quality_report(project, archive)
        ranks = [RANK[f["severity"]] for f in report["findings"]]
        self.assertGreaterEqual(len(ranks), 2, report)
        self.assertEqual(ranks, sorted(ranks), "findings are not worst-first")
        self.assertEqual(report["findings"][0]["severity"], "high")

    def test_every_finding_is_a_proposal_and_nothing_is_executed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed(project)
            before = _tree_digest(project)
            report = quality_report(project, archive)
            after = _tree_digest(project)
        self.assertEqual(before, after, "quality changed the tree")
        for finding in report["findings"]:
            self.assertEqual(finding["remediation"], "proposal", finding)
            for key in ("source", "severity", "path", "line", "message", "remedy"):
                self.assertIn(key, finding, finding)

    def test_a_high_finding_reaches_the_exit_status(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            _seed(project)
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(project), "quality"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"], "findings-present")
        self.assertGreaterEqual(payload["counts"]["high"], 1)


if __name__ == "__main__":
    unittest.main()

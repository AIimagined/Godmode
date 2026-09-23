"""One reader, one window: every surface that reads open asks - the stop
hook's scope block, `godmode_iteration.open_scope`, `review_requests`, and
the push preflight's open-asks finding - now fold over the exact same
records through `godmode_requests`'s own reader.

Before this, the five call sites asked the archive for a different number
of request records each (200 at two of them, 600 at the rest), so a busy
session could show an ask as open on one surface while another had already
stopped looking far enough back to see it - the report of a closed ask
that a surface reading fewer records still called open. Naming one shared
number does not end that class by itself: a still-open ask has no artefact
anywhere else (see `godmode_requests`'s module docstring), so it must not
expire just because enough later, unrelated asks got recorded after it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, PLUGIN_ROOT / "hooks", Path(__file__).parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_iteration import open_scope  # noqa: E402
from godmode_runtime.godmode_preflight import push_preflight  # noqa: E402
from godmode_runtime.godmode_requests import (  # noqa: E402
    REQUEST_WINDOW, digest, record_request, review_requests,
)
from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402

ASK = "please sweep the render pipeline before the cut"


def _git_project(base: Path) -> Path:
    project = base / "repo"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"],
                   cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=project, capture_output=True)
    (project / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, capture_output=True)
    return project


class OneReaderAgreementTests(unittest.TestCase):
    """Open then closed for one subject: every surface agrees, both times."""

    def _asks(self, report: dict) -> list[str]:
        return [j.get("check") for j in report.get("judgment", [])]

    def test_open_then_closed_agrees_on_every_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gm-request-reader-") as tmp:
            import os
            from unittest import mock

            base = Path(tmp)
            project = _git_project(base)
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                                 clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()

                first = record_request(archive, ASK, session="host-1")
                subject = str(first["subject"])

                # Open: every surface says so.
                self.assertIsNotNone(hook._scope_block_reason(
                    archive, "Everything is complete and shipped.", "host-1"))
                self.assertTrue(open_scope(archive, "host-1")["asks"])
                self.assertEqual(
                    review_requests(archive.read_events())["verdict"],
                    "open-requests")
                self.assertIn("open-operator-asks",
                              self._asks(push_preflight(project, archive=archive)))

                archive.append("request", subject,
                               {"status": "closed", "digest": digest(subject)},
                               evidence=[])

                # Closed: every surface agrees - none still calls it open.
                self.assertIsNone(hook._scope_block_reason(
                    archive, "Everything is complete and shipped.", "host-1"))
                self.assertEqual(open_scope(archive, "host-1")["asks"], [])
                self.assertEqual(
                    review_requests(archive.read_events())["verdict"],
                    "no-open-requests")
                self.assertNotIn("open-operator-asks",
                                 self._asks(push_preflight(project, archive=archive)))


class WindowOverflowTests(unittest.TestCase):
    """An ask does not expire by record count: the window only flags that
    an archive has grown large, it never hides an ask that is still open."""

    def test_an_open_ask_survives_hundreds_of_later_unrelated_asks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gm-request-window-") as tmp:
            import os
            from unittest import mock

            base = Path(tmp)
            project = _git_project(base)
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                                 clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()

                record_request(archive, ASK, session="host-1")
                self.assertGreater(650, 0)
                for index in range(650):
                    record_request(archive, f"unrelated filler ask number {index}")

                self.assertIsNotNone(hook._scope_block_reason(
                    archive, "Everything is complete and shipped.", "host-1"))

                scope = open_scope(archive, "host-1")
                self.assertTrue(any("sweep" in line for line in scope["asks"]),
                                scope["asks"])
                self.assertTrue(scope["window_overflow"])

                report = review_requests(archive.read_events())
                self.assertTrue(report["window_overflow"])
                self.assertTrue(any("sweep" in f["request"] for f in report["findings"]),
                                report["findings"])

                preflight_report = push_preflight(project, archive=archive)
                checks = [j for j in preflight_report["judgment"]
                          if j.get("check") == "open-operator-asks"]
                self.assertTrue(checks)
                self.assertIn("sweep", checks[0].get("detail", ""))

    def test_the_shared_window_constant_is_six_hundred(self) -> None:
        self.assertEqual(REQUEST_WINDOW, 600)


if __name__ == "__main__":
    unittest.main()

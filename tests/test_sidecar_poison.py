"""Every sidecar or cache the chronicle writes beside the archive is
derived state: a poisoned one over an intact archive never turns `doctor`
red or bricks a read. One subtest per sidecar per poison shape (not JSON at
all; JSON of the wrong shape)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime import godmode_console  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

SIDECARS = {
    "read-index": Chronicle._INDEX_NAME,
    "checkpoint-registry": "godmode-checkpoint-registry.json",
    "enforce-index": Chronicle._ENFORCE_INDEX_NAME,
    "cold-registry": "godmode-cold-registry.json",
    "brief-echo": "godmode-brief-echo.json",
    "claim-echo": "godmode-claim-echo.json",
}
POISONS = {
    "not-json": b"{not json at all",
    "wrong-shape": json.dumps({"garbage": True, "records": "no", "entries": 7}).encode("utf-8"),
}


def _doctor(project: Path) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = godmode_console.main(["--project", str(project), "doctor"])
    return code, json.loads(out.getvalue())


class SidecarPoisonTests(unittest.TestCase):
    def test_a_poisoned_sidecar_over_an_intact_archive_leaves_doctor_green(self) -> None:
        for sidecar, name in SIDECARS.items():
            for poison, body in POISONS.items():
                with self.subTest(sidecar=sidecar, poison=poison):
                    with isolated_project() as (project, _s, _a, archive):
                        archive.initialize()
                        for i in range(12):
                            archive.append("decision", f"r-{i}", {"status": "ruled"}, evidence=[])
                        archive.append("checkpoint", "mid", {"status": "progress"})
                        archive.read_events()
                        (archive.root / name).write_bytes(body)
                        code, report = _doctor(project)
                        self.assertEqual(code, 0, report)
                        self.assertTrue(report["healthy"], report.get("issues"))
                        # The archive still reads, and reads whole.
                        fresh = Chronicle(archive.anchor)
                        self.assertEqual(len(fresh.read_events()), 13)


if __name__ == "__main__":
    unittest.main()

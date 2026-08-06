from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_netgate import capture, differential  # noqa: E402


class CaptureTests(unittest.TestCase):
    def test_planted_getaddrinfo_is_detected(self) -> None:
        # Plant-and-observe: a child that deliberately touches the resolver must
        # show up in the capture, or the whole gate is theatre.
        with tempfile.TemporaryDirectory() as temporary:
            report = capture(
                [
                    sys.executable,
                    "-c",
                    "import socket\n"
                    "try:\n"
                    "    socket.getaddrinfo('localhost', 80)\n"
                    "except OSError:\n"
                    "    pass\n",
                ],
                Path(temporary),
            )
        self.assertFalse(report["clean"], report)
        self.assertTrue(report["connections"], report)
        events = {entry["event"] for entry in report["connections"]}
        self.assertIn("socket.getaddrinfo", events, report)

    def test_networkless_child_reports_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = capture([sys.executable, "-c", "print(1)"], Path(temporary))
        self.assertEqual(report["exit_code"], 0, report)
        self.assertTrue(report["clean"], report)
        self.assertEqual(report["connections"], [], report)


class DifferentialTests(unittest.TestCase):
    def test_cli_surfaces_make_no_connections(self) -> None:
        # Kept to init + doctor so the test stays fast; the full five-surface
        # sweep is the CI job's business. "{project}" is substituted with the
        # throwaway project differential creates, and differential also points
        # GODMODE_STATE_HOME at a temp dir so nothing touches real state.
        script = str(PLUGIN_ROOT / "scripts" / "godmode.py")
        commands = [
            [sys.executable, script, "--project", "{project}", name]
            for name in ("init", "doctor")
        ]
        report = differential(PLUGIN_ROOT, commands=commands)
        self.assertEqual(report["violations"], [], report)
        self.assertTrue(report["clean"], report)
        self.assertEqual(len(report["commands_run"]), 2, report)


if __name__ == "__main__":
    unittest.main()

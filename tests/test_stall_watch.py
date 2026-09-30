"""An approval that waits thirty minutes is recorded once and announced once."""
from __future__ import annotations

import os
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

from godmode_runtime import godmode_stallwatch as stall  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class StallRecordTests(unittest.TestCase):
    def test_an_ask_with_nothing_after_it_is_unanswered(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            asked = archive.append("action", "gate-asked", {"tier": "R4"}, evidence=[])
            self.assertFalse(stall.answered(archive, asked["sequence"]))
            archive.append("action", "capability-consumed", {"category": "x"}, evidence=[])
            self.assertTrue(stall.answered(archive, asked["sequence"]))

    def test_a_stall_is_recorded_once_per_ask(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            asked = archive.append("action", "gate-asked", {"tier": "R4"}, evidence=[])
            first = stall.record_stall(archive, asked["sequence"], 1800, "git push origin main")
            self.assertIsNotNone(first)
            self.assertEqual(first["data"]["what"], "git push origin main")
            self.assertIsNone(stall.record_stall(archive, asked["sequence"], 1800, "again"))
            self.assertEqual(len(archive.select(kind="action", subject=stall.SUBJECT)), 1)

    def test_the_watcher_records_and_notifies_only_a_stall(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            asked = archive.append("action", "gate-asked", {"tier": "R4"}, evidence=[])
            shown: list[str] = []
            outcome = stall.watch(str(project), asked["sequence"], "git push origin main",
                                  wait_seconds=1800, sleep=lambda _s: None,
                                  notifier=lambda text: shown.append(text) or True)
            self.assertEqual(outcome, "stalled")
            self.assertEqual(len(shown), 1)
            self.assertIn("30 minutes", shown[0])
            self.assertIn("git push origin main", shown[0])
            answered = archive.append("action", "gate-asked", {"tier": "R4"}, evidence=[])
            archive.append("action", "capability-consumed", {"category": "x"}, evidence=[])
            self.assertEqual(
                stall.watch(str(project), answered["sequence"], "x", wait_seconds=1,
                            sleep=lambda _s: None, notifier=lambda t: shown.append(t) or True),
                "answered")
            self.assertEqual(len(shown), 1)


class NotifyTests(unittest.TestCase):
    def test_each_platform_names_its_own_program_and_carries_the_text(self) -> None:
        text = "Godmode: an approval has waited"
        windows = stall.notify_argv(text, "win32")
        self.assertEqual(windows[0], "powershell")
        self.assertIn("$env:GODMODE_NOTE", windows[-1])
        self.assertNotIn(text, " ".join(windows))
        mac = stall.notify_argv(text, "darwin", exists=lambda _p: True)
        self.assertEqual((mac[0], mac[-1]), ("/usr/bin/osascript", text))
        linux = stall.notify_argv(text, "linux", exists=lambda _p: True)
        self.assertEqual(linux, ["/usr/bin/notify-send", "Godmode", text])
        self.assertIsNone(stall.notify_argv(text, "linux", exists=lambda _p: False))

    def test_notify_passes_the_text_in_the_environment_and_never_raises(self) -> None:
        calls: list[dict] = []

        def run(argv, **kwargs):
            calls.append(kwargs)

        self.assertTrue(stall.notify("waited", run=run, platform="win32"))
        self.assertEqual(calls[0]["env"]["GODMODE_NOTE"], "waited")

        def broken(argv, **kwargs):
            raise OSError("no display")

        self.assertFalse(stall.notify("waited", run=broken, platform="win32"))


class SpawnTests(unittest.TestCase):
    def test_the_watcher_is_started_detached_with_the_ask_named(self) -> None:
        seen: list[tuple[list[str], dict]] = []
        self.assertTrue(stall.spawn_watch("C:/p", 41, "git push", popen=lambda a, **k: seen.append((a, k))))
        argv, kwargs = seen[0]
        self.assertEqual(argv[-3:], ["C:/p", "41", "git push"])
        self.assertIn("-I", argv)
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"])
        else:
            self.assertTrue(kwargs["start_new_session"])

    def test_a_watcher_that_cannot_start_does_not_fail_the_ask(self) -> None:
        def broken(argv, **kwargs):
            raise OSError("no python")

        self.assertFalse(stall.spawn_watch("C:/p", 1, "x", popen=broken))


if __name__ == "__main__":
    unittest.main()

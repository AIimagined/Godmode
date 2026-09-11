"""A transcript that spells the project through an alias still credits
the read. CI 2026-09-11: Windows runners hand the temp directory out in
8.3 short form (RUNNER~1) and macOS reaches it through /var -> /private/var;
the resolved project root matched neither spelling, so every Read in the
transcript went uncredited and the sources gate asked on every turn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_sources import transcript_reads  # noqa: E402
from test_short_path_containment import _short_form  # noqa: E402


def _transcript(path: Path, read_path: str) -> None:
    entry = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": read_path}}]}}
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")


class AliasedProjectSpellingTests(unittest.TestCase):
    def test_a_read_through_the_projects_alias_is_credited(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "proj"
            project.mkdir()
            (project / "GODMODE.md").write_text("# rules\n", encoding="utf-8")
            alias = None
            if os.name == "nt":
                alias = _short_form(str(project))
            if alias is None or alias.lower() == str(project).lower():
                # No alias on this volume: the symlink form stands in.
                link = Path(raw) / "link"
                try:
                    os.symlink(project, link, target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest("no short name and no symlink available here")
                alias = str(link)
            transcript = Path(raw) / "t.jsonl"
            _transcript(transcript, str(Path(alias) / "GODMODE.md"))
            self.assertIn("godmode.md" if os.name == "nt" else "GODMODE.md",
                          transcript_reads(transcript, project))


if __name__ == "__main__":
    unittest.main()

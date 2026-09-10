"""Field feedback, 2026-09-11, second batch.

A doc edit on `docs/release-notes.md` read as a release write: the
external-write verbs matched a word inside a path. And a claim arrived
`--grade verified` beside a cited check that had just failed; the record
said "verified" and the support line counted passes as "executed".
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = PLUGIN_ROOT / "tests"
for entry in (SCRIPTS, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


class ReleaseWordInsideAPathTests(unittest.TestCase):
    def test_a_verb_word_inside_a_filename_is_not_the_verb(self) -> None:
        for command in (
            'sed -i "s/foo/bar/" docs/release-notes.md',
            "sed -i 's/x/y/' docs/deploy-guide.md",
            "cp templates/publish.yml .github/workflows/publish.yml",
            "godmode release-notes check 0.3.25",
            "python scripts/godmode.py --json release-notes build 0.3.25",
        ):
            self.assertNotEqual(classify_action(command)["category"], "release-or-external-write", command)

    def test_the_verb_in_command_position_still_counts(self) -> None:
        for command in ("gh release create v1.0", "npm publish", "vercel deploy --prod"):
            self.assertEqual(classify_action(command)["category"], "release-or-external-write", command)


class ClaimVerifyRedCheckTests(unittest.TestCase):
    def test_a_check_that_ran_red_caps_a_verified_claim_at_observed(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime import godmode_console as console
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            console.main(["--project", str(project), "session", "open", "--label", "t"])
            out = io.StringIO()
            with redirect_stdout(out):
                code = console.main([
                    "--project", str(project), "--json", "claim", "the suite is green",
                    "--grade", "verified", "--cite", "cmd:python -c \"import sys; sys.exit(1)\"", "--verify",
                ])
            self.assertNotEqual(code, 2, out.getvalue())
            record = archive.select(kind="claim", limit=1)[-1]["data"]
        self.assertEqual(record["grade"], "observed", record)
        self.assertIn("1/1 cited command(s) executed just now, 0 passed", out.getvalue())


if __name__ == "__main__":
    unittest.main()

"""A claim records where its evidence comes from, a command citation never
keeps a secret, and a citation that needs a shell is refused with the
two forms that work."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_attest import (  # noqa: E402
    independence_tier, record_claim, refuse_shell_grammar, scrub_citation)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class IndependenceTests(unittest.TestCase):
    def test_the_strongest_citation_sets_the_tier(self) -> None:
        self.assertEqual(independence_tier([]), "self")
        self.assertEqual(independence_tier(["file:README.md"]), "external")
        self.assertEqual(independence_tier(["file:x", "seq:12"]), "recorded")
        self.assertEqual(independence_tier(["seq:12", "cmd:pytest -q"]), "attested")

    def test_a_recorded_claim_carries_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record = record_claim(archive, project, "S-1", "the build is green", "observed",
                                  cites=["file:README.md"])
            self.assertEqual(record["data"]["independence"], "external")
            record = record_claim(archive, project, "S-1", "nothing cited", "hypothesis")
            self.assertEqual(record["data"]["independence"], "self")


class ScrubTests(unittest.TestCase):
    def test_a_secret_shaped_token_never_reaches_the_record(self) -> None:
        token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
        scrubbed = scrub_citation(f"cmd:curl -H 'Authorization: {token}' https://api.example")
        self.assertNotIn(token, scrubbed)
        self.assertIn("[redacted]", scrubbed)
        self.assertTrue(scrubbed.startswith("cmd:curl"))
        self.assertEqual(scrub_citation("cmd:pytest -q tests"), "cmd:pytest -q tests")
        self.assertEqual(scrub_citation(f"seq:{token}"), f"seq:{token}")


class ShellGrammarTests(unittest.TestCase):
    def test_shell_grammar_is_refused_with_the_working_forms(self) -> None:
        for command in ("pytest -q | tail -3", "make check && echo ok", "diff <(a) <(b)",
                        "python x.py > out.txt", "a; b"):
            with self.subTest(command=command), self.assertRaises(ArchiveError) as ctx:
                refuse_shell_grammar(command)
            self.assertIn("bash -c", str(ctx.exception))
            self.assertIn("file:", str(ctx.exception))
        for command in ("pytest -q tests/test_x.py", "python -c 'print(1 > 0)'",
                        'grep -n "a|b" file.txt'):
            with self.subTest(command=command):
                refuse_shell_grammar(command)


if __name__ == "__main__":
    unittest.main()

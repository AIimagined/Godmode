"""A printed stage line runs as pasted and stages the exact command.

The staged text must equal the command byte for byte. The hint used to
print the operation as a JSON string, which bash and PowerShell both read
differently from JSON: `$VAR` expanded, `\\"` was not an escape in
PowerShell, and the staging never matched.
"""
from __future__ import annotations

from pathlib import Path
import shlex
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_sentinel  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    bash_quoted, powershell_quoted, stage_operation_hint)

AWKWARD = [
    'git commit -m "fix: it\'s done" && git push origin "$BRANCH"',
    "python -c \"print('a', \\\"b\\\")\"",
    "cat <<'EOF' > x.txt\nline `one` $two\nEOF",
    "echo it''s $(date) ; rm -rf 'a b'",
]


def _powershell_unquoted(word: str) -> str:
    assert word.startswith("'") and word.endswith("'"), word
    return word[1:-1].replace("''", "'")


class StageLineQuotingTests(unittest.TestCase):
    def test_the_bash_word_reads_back_byte_for_byte(self) -> None:
        for operation in AWKWARD:
            with self.subTest(operation=operation):
                self.assertEqual(shlex.split(bash_quoted(operation)), [operation])

    def test_the_powershell_word_reads_back_byte_for_byte(self) -> None:
        for operation in AWKWARD:
            with self.subTest(operation=operation):
                word = powershell_quoted(operation)
                self.assertEqual(_powershell_unquoted(word), operation)
                self.assertNotIn("$", word.replace(operation.replace("'", "''"), ""))

    def test_the_hint_carries_both_forms_on_windows(self) -> None:
        operation = AWKWARD[0]
        with mock.patch.object(godmode_sentinel.os, "name", "nt"):
            hint = stage_operation_hint(PLUGIN_ROOT, operation)
        self.assertIn(f"--operation {bash_quoted(operation)}`", hint)
        self.assertIn(f"--operation {powershell_quoted(operation)}`", hint)


if __name__ == "__main__":
    unittest.main()

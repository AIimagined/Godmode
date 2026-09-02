"""The shipped package compiles without SyntaxWarning.

Field-observed 2026-09-02, minutes after the operator installed 0.3.12:
`godmode_status.py:670` carried "\\s" in a non-raw string, and every
install printed a SyntaxWarning on first import. Tests never failed
because a warning is not an error - here it is one.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class SyntaxWarningTests(unittest.TestCase):
    def test_every_shipped_module_compiles_warning_free(self) -> None:
        sources = sorted((PLUGIN_ROOT / "scripts").rglob("*.py"))
        sources += sorted((PLUGIN_ROOT / "hooks").glob("*.py"))
        self.assertGreater(len(sources), 50)
        # The filter must be an interpreter flag: set from inside the
        # process, the compile-time warning lands in a dedup registry and
        # the second occurrence is silently swallowed.
        code = (
            "import sys\n"
            "bad = []\n"
            "for path in sys.argv[1:]:\n"
            "    source = open(path, encoding='utf-8').read()\n"
            "    try:\n"
            "        compile(source, path, 'exec')\n"
            "    except (SyntaxError, SyntaxWarning) as exc:\n"
            "        bad.append(f'{path}: {exc}')\n"
            "print('\\n'.join(bad))\n"
            "sys.exit(1 if bad else 0)\n"
        )
        result = subprocess.run(
            [sys.executable, "-W", "error::SyntaxWarning", "-c", code,
             *map(str, sources)],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

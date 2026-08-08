"""Damage an agent does to source with its own tools.

A failure taxonomy built from real coding-agent incidents gives this its own
section — the agent's tooling, not the product's code. Three of its entries were
committed during the session that read it:

* a scripted edit wrote a regex whose `\\b` collapsed into a literal backspace
  byte, so every pattern silently matched nothing;
* a here-document halved backslashes twice more, producing source that parsed
  but meant something else;
* each was found only because a test failed afterwards, never by the write.

The write reported success every time. Nothing looked at what landed.

These monitors look. A file changed in this diff must still parse, and must not
carry control characters that no editor would have produced — the exact residue
of a shell mangling a pattern on the way to disk.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_integrity import source_damage  # noqa: E402


def _repo(**files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-source-")
    root = Path(holder.name)
    for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                    ["config", "user.name", "d"]):
        subprocess.run(["git", *command], cwd=root, capture_output=True)
    (root / "keep.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, capture_output=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    holder._root = root  # type: ignore[attr-defined]
    return holder


def _codes(findings: list[dict]) -> set[str]:
    return {finding["monitor"] for finding in findings}


class ControlCharacterTests(unittest.TestCase):
    """The literal defect: `\\b` written through a shell became `\\x08`."""

    def test_a_collapsed_escape_is_reported(self) -> None:
        damaged = 'PATTERN = r"(?i)\x08[\\w.-]+/[\\w.-]+"\n'
        holder = _repo(**{"rule.py": damaged})
        with holder:
            findings = source_damage(holder._root)  # type: ignore[attr-defined]
        self.assertIn("control-characters", _codes(findings))
        self.assertTrue(any("rule.py" in f["path"] for f in findings))

    def test_the_finding_names_the_byte_and_the_line(self) -> None:
        holder = _repo(**{"rule.py": 'A = 1\nB = "\x08"\n'})
        with holder:
            finding = [f for f in source_damage(holder._root)  # type: ignore[attr-defined]
                       if f["monitor"] == "control-characters"][0]
        self.assertIn("0x08", finding["detail"])
        self.assertIn("line 2", finding["detail"])

    def test_tabs_and_newlines_are_not_damage(self) -> None:
        holder = _repo(**{"fine.py": "def f():\n\treturn 1\n"})
        with holder:
            self.assertNotIn("control-characters",
                             _codes(source_damage(holder._root)))  # type: ignore[attr-defined]

    def test_a_binary_file_is_not_scanned_as_source(self) -> None:
        holder = _repo()
        root = holder._root  # type: ignore[attr-defined]
        with holder:
            (root / "logo.png").write_bytes(bytes(range(32)) * 4)
            self.assertNotIn("control-characters", _codes(source_damage(root)))


class SyntaxTests(unittest.TestCase):
    def test_a_changed_python_file_that_no_longer_parses_is_reported(self) -> None:
        holder = _repo(**{"broken.py": "def f(:\n    return 1\n"})
        with holder:
            findings = source_damage(holder._root)  # type: ignore[attr-defined]
        self.assertIn("unparseable-source", _codes(findings))

    def test_a_valid_change_is_clean(self) -> None:
        holder = _repo(**{"good.py": "def f():\n    return 2\n"})
        with holder:
            self.assertEqual(source_damage(holder._root), [])  # type: ignore[attr-defined]

    def test_an_unchanged_file_is_not_reported(self) -> None:
        """Only what this diff touched. A pre-existing oddity elsewhere is not
        this pass's finding, and reporting it trains the reader to skip."""
        holder = _repo()
        root = holder._root  # type: ignore[attr-defined]
        with holder:
            (root / "untouched.py").write_text("x = \x08\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-q", "-m", "pre-existing"],
                           cwd=root, capture_output=True)
            self.assertEqual(source_damage(root), [])


class BlockingTests(unittest.TestCase):
    def test_source_damage_blocks(self) -> None:
        """A file that does not parse cannot be reviewed, so this is not
        advisory: the write already failed and nobody noticed."""
        holder = _repo(**{"broken.py": "def f(:\n"})
        with holder:
            for finding in source_damage(holder._root):  # type: ignore[attr-defined]
                self.assertTrue(finding["blocking"], finding)


class ThisRepositoryTests(unittest.TestCase):
    def test_the_shipped_tree_carries_no_control_characters(self) -> None:
        """The bug that produced this monitor shipped into a working tree and
        was committed; this asserts the tree is clean of that residue now."""
        offenders = []
        for path in sorted((PLUGIN_ROOT / "scripts").rglob("*.py")):
            raw = path.read_bytes()
            if any(byte in raw for byte in (0x08, 0x0b, 0x0c, 0x00)):
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"control characters in source: {offenders}")


if __name__ == "__main__":
    unittest.main()

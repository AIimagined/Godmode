"""`checksums` claims two independent clones agree. Found reading a
copy-paste detector's baseline hashing (2026-09-10): the manifest hashed
on-disk bytes, so a project without an `eol=lf` attribute produced one
manifest from a Windows autocrlf clone and another from a Linux one; this
repository pins eol=lf, so its own CI proof never saw the gap. Text files
are now hashed with CR stripped, binary files byte-for-byte, and the
report says which rule it applied.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_bindings import release_checksums  # noqa: E402


def _repo(root: Path, files: dict[str, bytes]) -> None:
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    for name, body in files.items():
        (root / name).write_bytes(body)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


class ChecksumsLineEndingTests(unittest.TestCase):
    def test_a_crlf_clone_and_an_lf_clone_produce_one_manifest(self) -> None:
        binary = bytes(range(256)) + b"\r\n" + bytes(range(256))
        with tempfile.TemporaryDirectory() as raw_a, tempfile.TemporaryDirectory() as raw_b:
            a, b = Path(raw_a), Path(raw_b)
            _repo(a, {"doc.md": b"one\r\ntwo\r\n", "blob.bin": binary})
            _repo(b, {"doc.md": b"one\ntwo\n", "blob.bin": binary})
            first, second = release_checksums(a), release_checksums(b)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(first["normalization"], "text files hashed with CR stripped; binary files byte-for-byte")

    def test_binary_bytes_are_hashed_as_stored(self) -> None:
        with tempfile.TemporaryDirectory() as raw_a, tempfile.TemporaryDirectory() as raw_b:
            a, b = Path(raw_a), Path(raw_b)
            _repo(a, {"blob.bin": b"\x00\r\n\x01"})
            _repo(b, {"blob.bin": b"\x00\n\x01"})
            self.assertNotEqual(release_checksums(a)["manifest_sha256"],
                                release_checksums(b)["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()

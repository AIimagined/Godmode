"""The archive told as dated prose: deterministic, template-driven, local.

Views render state; the digest renders the STORY - what happened, in
order, with the numbers the records already carry. No model, no
paraphrase: every sentence is assembled from record fields, so the same
archive always produces the same digest.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_digest import render_digest  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-digest-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


class DigestTests(unittest.TestCase):
    def test_the_story_carries_incidents_claims_and_lessons(self) -> None:
        with _archive() as (root, archive):
            from godmode_runtime.godmode_attest import record_claim, resolve_claim
            from godmode_runtime.godmode_mistakes import record_incident
            (root / "README.md").write_text("x", encoding="utf-8")
            record_incident(archive, "the bed gate broke on posix",
                            "reproduced on an aliased temp dir",
                            failure_class="environment-failure",
                            turning_point=True,
                            cites=["file:README.md"])
            archive.append("lesson", "aliased paths need canonicalization",
                           {"value": "seen once",
                            "generalized_guard": "canonicalize before compare"})
            claim = record_claim(archive, root, "S", "the bed suite holds",
                                 "observed", cites=["file:README.md"],
                                 confidence=0.9)
            resolve_claim(archive, root, "S", claim["sequence"], "held",
                          cites=["file:README.md"])
            digest = render_digest(archive)
            self.assertIn("the bed gate broke on posix", digest)
            self.assertIn("environment-failure", digest)
            self.assertIn("turning point", digest)
            self.assertIn("canonicalize before compare", digest)
            self.assertIn("resolved held", digest)

    def test_deterministic(self) -> None:
        with _archive() as (root, archive):
            archive.append("lesson", "one lesson",
                           {"value": "v", "generalized_guard": "g"})
            self.assertEqual(render_digest(archive), render_digest(archive))

    def test_since_bounds_the_story(self) -> None:
        with _archive() as (root, archive):
            early = archive.append("lesson", "ancient lesson",
                                   {"value": "v", "generalized_guard": "old"})
            late = archive.append("lesson", "recent lesson",
                                  {"value": "v", "generalized_guard": "new"})
            digest = render_digest(archive, since=late["sequence"])
            self.assertIn("recent lesson", digest)
            self.assertNotIn("ancient lesson", digest)

    def test_empty_archive_is_an_honest_sentence(self) -> None:
        with _archive() as (root, archive):
            digest = render_digest(archive)
            self.assertIn("no records", digest)


if __name__ == "__main__":
    unittest.main()

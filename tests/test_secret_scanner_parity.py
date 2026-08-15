"""Two secret scanners, one question - the seam is what must be tested.

Found by an adversarial sweep: the sentinel's archive gate
(find_secret_shapes, blocks credential-shaped payloads from being stored)
and the egress staged-file scan (_SECRET_KINDS, names the kind and masks
the value) each covered shapes the other missed. A connection string
pasted into a claim was stored verbatim by the archive while the egress
scan would have caught it staged; ghp_/sk- prefixes were the reverse; JWTs
and Slack tokens escaped both. Two functions answering the same question
with different rules is a defect even when both are individually "right" -
so this test pins every canonical example against BOTH scanners, and a
shape added to one without the other goes red here.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_egress import _secret_on_line  # noqa: E402
from godmode_runtime.godmode_sentinel import find_secret_shapes  # noqa: E402


# One canonical, syntactically valid but fabricated example per shape.
# godmode: allow-secret on every line - these are the test fixtures the
# scanners exist to catch, not credentials.
CANONICAL = {
    "aws-access-key": "AKIAIOSFODNN7EXAMPLE",  # godmode: allow-secret
    "private-key-header": "-----BEGIN RSA PRIVATE KEY-----",  # godmode: allow-secret
    "forge-token": "ghp_16C7e42F292c6912E7710c838347Ae178B4a",  # godmode: allow-secret
    "provider-key": "sk-proj-abc123def456ghi789jkl012mno345",  # godmode: allow-secret
    "jwt": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N"),  # godmode: allow-secret
    "connection-string-password":
        "postgres" + "://admin:hunter2sekrit@db.internal:5432/prod",  # godmode: allow-secret
    "slack-token": "xoxb-2444333222111-1234567890123-AbCdEf",  # godmode: allow-secret
    "bearer-token": "Bearer abc123def456ghi789",  # godmode: allow-secret
}

INNOCENT = [
    "the quick brown fox jumps over the lazy dog",
    "commit 3f50a20de9b133d7079ad35f2d458613d38e09f1",
    "0bd779d4f389fece4178da9b12f7796444072114c54c9d684a03d4c74e38bf96",
    "skill.md and tokens.json are ordinary filenames",
]


class SeamParityTests(unittest.TestCase):
    def test_every_canonical_shape_is_caught_by_the_sentinel_gate(self) -> None:
        for kind, example in CANONICAL.items():
            findings = find_secret_shapes({"v": example})
            self.assertTrue(findings, f"sentinel gate missed {kind}: a payload "
                                      "carrying this shape would be STORED verbatim")

    def test_every_canonical_shape_is_caught_by_the_egress_scan(self) -> None:
        for kind, example in CANONICAL.items():
            hit = _secret_on_line(example)
            self.assertIsNotNone(hit, f"egress scan missed {kind}: this shape "
                                      "would reach a staged commit unnamed")

    def test_egress_names_the_kind_and_masks_the_value(self) -> None:
        kind, masked = _secret_on_line(CANONICAL["slack-token"])
        self.assertEqual(kind, "slack-token")
        self.assertNotIn(CANONICAL["slack-token"], masked)

    def test_innocent_content_passes_both(self) -> None:
        for text in INNOCENT:
            self.assertEqual(find_secret_shapes({"v": text}), [],
                             f"sentinel false positive on: {text}")
            self.assertIsNone(_secret_on_line(text),
                              f"egress false positive on: {text}")


if __name__ == "__main__":
    unittest.main()

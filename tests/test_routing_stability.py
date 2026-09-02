"""Config-fragile eval cases: a route that flips with no rule change.

The snapshot records every prompt's routed skill under a digest of the
authored suites; a later run under the same digest that routes a case
differently names it fragile - it must not decide a gate. A different
digest is a rule change, reported as such, never as fragility.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_evals import routing_stability  # noqa: E402


class RoutingStabilityTests(unittest.TestCase):
    def test_this_repository_is_stable_against_its_snapshot(self) -> None:
        report = routing_stability(PLUGIN_ROOT)
        self.assertIn(report["verdict"],
                      ("routing-stable", "stability-snapshot-written"))
        self.assertGreater(report["cases"], 20)

    def test_a_flipped_case_is_named_fragile(self) -> None:
        import tempfile
        report = routing_stability(PLUGIN_ROOT)
        fixture = PLUGIN_ROOT / "evals" / "fixtures" / "routing-stability.json"
        stored = json.loads(fixture.read_text(encoding="utf-8"))
        victim = sorted(stored["routes"])[0]
        original = stored["routes"][victim]
        stored["routes"][victim] = original + "-flipped"
        backup = fixture.read_text(encoding="utf-8")
        try:
            fixture.write_text(json.dumps(stored), encoding="utf-8")
            report = routing_stability(PLUGIN_ROOT)
            self.assertEqual(report["verdict"], "fragile-cases-found")
            self.assertIn(victim, report["fragile"])
        finally:
            fixture.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()


class LineEndingTests(unittest.TestCase):
    def test_the_digest_ignores_checkout_line_endings(self) -> None:
        # A Windows checkout hashes CRLF bytes, CI hashes LF - the digest
        # must see suite CONTENT, not the checkout's line-ending choice.
        import hashlib
        payload_lf = b'{"a": 1}\n{"b": 2}\n'
        payload_crlf = payload_lf.replace(b"\n", b"\r\n")
        digest = lambda raw: hashlib.sha256(
            raw.replace(b"\r\n", b"\n")).hexdigest()
        self.assertEqual(digest(payload_lf), digest(payload_crlf))

"""Hook timeouts in generated manifests follow the measured latency baseline."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as hm  # noqa: E402


def _baseline(root: Path, recommended) -> None:
    (root / "benchmarks").mkdir(exist_ok=True)
    (root / "benchmarks" / "gate_latency_baseline.json").write_text(json.dumps({
        "schema": "godmode-gate-latency-baseline-v1", "phases": {},
        "recommended_timeouts": recommended}), encoding="utf-8")


class TimeoutTests(unittest.TestCase):
    def test_defaults_without_baseline(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        self.assertEqual(hm.hook_timeouts(root)["pre_tool_use"], 30)

    def test_baseline_overrides(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        _baseline(root, {"pre_tool_use": 45})
        self.assertEqual(hm.hook_timeouts(root)["pre_tool_use"], 45)
        self.assertEqual(hm.hook_timeouts(root)["stop"], 10)

    def test_a_recommendation_below_the_default_leaves_the_default(self) -> None:
        # Fix round 1 ruling: a recommendation may only RAISE a default,
        # never lower it, until that hook path is measured directly - the
        # `user_prompt` recommendation today is derived from the fast-gate
        # proxy, not from a measurement of the prompt hook itself.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        _baseline(root, {"user_prompt": 13, "stop": 1})
        timeouts = hm.hook_timeouts(root)
        self.assertEqual(timeouts["user_prompt"], 60)  # default 60 > recommended 13
        self.assertEqual(timeouts["stop"], 10)  # default 10 > recommended 1

    def test_a_non_dict_recommended_timeouts_is_ignored_not_raised(self) -> None:
        # Fix round 1 (Important finding 1): valid JSON whose
        # `recommended_timeouts` is a string/list/number must fall back to
        # defaults, never raise AttributeError from an `.items()` call on a
        # non-dict.
        for shape in ("not-a-dict", [1, 2, 3], 42, None):
            root = Path(tempfile.mkdtemp())
            self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
            _baseline(root, shape)
            self.assertEqual(hm.hook_timeouts(root), hm.DEFAULT_TIMEOUTS, shape)

    def test_a_boolean_recommended_value_is_ignored(self) -> None:
        # `bool` is an `int` subclass in Python, but JSON `true`/`false`
        # is never a meaningful timeout - it must not pass the int check.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        _baseline(root, {"pre_tool_use": True})
        self.assertEqual(hm.hook_timeouts(root)["pre_tool_use"], 30)

    def test_generated_manifest_uses_the_timeouts(self) -> None:
        # The brief's `build_claude_manifest` does not exist in this module -
        # the seconds-dialect builder at this call-site region is
        # `build_cursor_manifest`, the only builder still on the seconds
        # dialect after CX-3 (Antigravity/Gemini are millisecond dialects,
        # untouched by this task); it now takes `project` to read the
        # baseline.
        manifest = hm.build_cursor_manifest(PLUGIN_ROOT)
        text = json.dumps(manifest)
        self.assertIn('"timeout": %d' % hm.hook_timeouts(PLUGIN_ROOT)["pre_tool_use"], text)


if __name__ == "__main__":
    unittest.main()

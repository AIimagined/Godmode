"""B4-2/B4-3: what godmode itself injects per session, measured and capped.

The continuity brief degrades through a typed-compression ladder
(`build_context_brief`: full records -> masked views -> dropped-but-counted),
and the session hook's emission is hard-capped at CLAUDE_CONTEXT_LIMIT with a
mid-JSON truncation as the last resort - a backstop that, if it ever fires,
hands the host an unparseable brief. Nothing enforced any of this
mechanically: MASKS coverage went stale as CX/B3 added writers (a kind
without a mask compresses to a default that may keep nothing its payload
holds), and no test red-lined when a grown archive pushed the rendered brief
toward the cap.

The masks completeness registry is grep-built from the writers themselves
(AST, literal-kind `archive.append` calls) so a new writer is swept in
automatically, and grow-only via a pinned floor so coverage can only widen.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_compress import MASKS, compress_record  # noqa: E402

from test_godmode_runtime import isolated_project  # noqa: E402


def _written_kinds() -> dict[str, set[str]]:
    """Every record kind written with a literal in a chronicle append, mapped
    to the files that write it. Grep-built (AST): a `.append("kind", subject,
    payload, ...)` call with three-plus arguments is a chronicle write; a
    two-argument `list.append` never matches."""
    kinds: dict[str, set[str]] = {}
    sources = list((SCRIPTS / "godmode_runtime").glob("*.py"))
    sources += list((PLUGIN_ROOT / "hooks").glob("*.py"))
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and len(node.args) >= 3
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                kinds.setdefault(node.args[0].value, set()).add(path.name)
    return kinds


# The coverage floor at the moment this test shipped - grow-only, the same
# discipline as the corpus floor: masks may be added, never removed, even if
# a writer later disappears (old archives still hold its records and still
# need the typed view).
_MASK_FLOOR = frozenset({
    "action", "attestation", "branch", "change", "checkpoint", "claim",
    "criterion", "database", "decision", "differential", "incident",
    "inventory", "invariant", "lesson", "metric", "obligation", "pin",
    "plan", "refusal", "request", "session", "sprint", "upstream-diff",
    "verdict",
})


class MasksCoverEveryShippedWriter(unittest.TestCase):
    def test_every_kind_written_has_a_declared_mask(self) -> None:
        kinds = _written_kinds()
        self.assertGreater(len(kinds), 10, "the AST scan found too few writers "
                           "to be believed - the scan itself is broken")
        missing = sorted(kind for kind in kinds if kind not in MASKS)
        self.assertEqual(missing, [], "shipped writers without a declared "
                         f"mask (falls back to a default that may keep "
                         f"nothing the payload holds): {missing}")

    def test_the_mask_registry_is_grow_only(self) -> None:
        gone = sorted(_MASK_FLOOR - set(MASKS))
        self.assertEqual(gone, [], "masks removed from the registry; old "
                         "archives still hold these kinds")

    def test_a_masked_view_keeps_a_declared_field_when_present(self) -> None:
        """The mask is honest both ways: kept fields survive, removed fields
        are named. Exercised through a kind this batch adds a mask for."""
        record = {"kind": "pin", "subject": "evaluator-pinned", "sequence": 7,
                  "data": {"action": "pin", "path": "bench/eval.py",
                           "sha256": "a" * 64, "policy_view_sha256": "b" * 64}}
        view = compress_record(record)
        self.assertIn("action", view["data"])
        self.assertIn("sha256", view["mask"]["removed"])
        self.assertEqual(view["mask"]["reconstruct"], "seq:7")


class BriefMeasureCountsOnly(unittest.TestCase):
    """B4-2: `godmode brief --measure` - bytes and estimated tokens per
    section, counts only, never a body."""

    def _measure(self, project: Path) -> dict:
        from godmode_runtime import godmode_console as console
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = console.main(["--project", str(project), "brief",
                                 "measure the brief", "--measure"])
        return {"exit_code": code, **json.loads(out.getvalue())}

    def test_measure_reports_bytes_and_tokens_per_section(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "GODMODE.md").write_text("guide text\n" * 50,
                                                encoding="utf-8")
            payload = self._measure(project)
            self.assertEqual(payload["exit_code"], 0)
            sections = payload["measure"]["sections"]
            self.assertIn("context", sections)
            for name, entry in sections.items():
                self.assertGreaterEqual(entry["bytes"], 0, name)
                self.assertEqual(entry["tokens_est"], max(1, entry["bytes"] // 4),
                                 name)
            total = payload["measure"]["total"]
            self.assertEqual(total["bytes"],
                             sum(e["bytes"] for e in sections.values()))

    def test_measure_never_carries_a_body(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            marker = "SEVENTEEN-GREEN-LLAMAS"
            (project / "GODMODE.md").write_text(f"guide {marker}\n" * 30,
                                                encoding="utf-8")
            payload = self._measure(project)
            self.assertNotIn(marker, json.dumps(payload))


class GrownArchiveStaysUnderTheCap(unittest.TestCase):
    """B4-2's red-line: the session hook's emission on a grown archive must
    fit the documented cap WITHOUT the mid-JSON truncation backstop firing -
    a truncated brief is an unparseable brief."""

    def test_session_brief_fits_the_cap_and_parses(self) -> None:
        import importlib
        import importlib.util
        observe = importlib.import_module("test_observe_mode")
        spec = importlib.util.spec_from_file_location(
            "godmode_session_hook_for_limit",
            PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        CLAUDE_CONTEXT_LIMIT = hook.CLAUDE_CONTEXT_LIMIT
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            for i in range(150):
                archive.append("decision", f"ruling-{i}",
                               {"status": "ruled", "detail": "d" * 90},
                               evidence=[])
                archive.append("checkpoint", f"cp-{i}",
                               {"status": "ok", "next": "n" * 60}, evidence=[])
                archive.append("lesson", f"lesson-{i}",
                               {"status": "open", "generalized_guard": "g" * 70},
                               evidence=[])
            brief = observe._session_start(project)
            context = brief["hookSpecificOutput"]["additionalContext"]
            self.assertLessEqual(len(context), CLAUDE_CONTEXT_LIMIT)
            self.assertNotIn("[brief truncated locally]", context)
            _prefix, _, payload = context.partition("\n")
            json.loads(payload)  # parseable - the truncation backstop never fired

    def test_context_brief_ladder_lands_inside_its_budget(self) -> None:
        from godmode_runtime.godmode_lens import build_context_brief
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            for i in range(80):
                archive.append("decision", f"ruling-{i}",
                               {"status": "ruled", "detail": "d" * 120},
                               evidence=[])
            brief = build_context_brief(anchor, archive, token_budget=800)
            within = brief["estimated_tokens"] <= 800
            emptied = not brief["records"] and brief.get("records_dropped")
            self.assertTrue(within or emptied,
                            "the ladder neither landed inside the budget nor "
                            "declared what it dropped")


if __name__ == "__main__":
    unittest.main()

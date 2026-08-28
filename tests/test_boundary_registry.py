"""Every surface a host feeds, tested where the host feeds it.

Four gate defects reached released builds — PowerShell denied, shell loops
denied, every file edit denied, committing denied. All four were invisible to a
suite of hundreds of passing tests for one reason: the tests fed the classifier
strings written by hand, and the host sends something else. `write file
README.md` passed while the host sends `edit file C:\\...\\file.py`, which the
classifier read as outside the working tree.

Fixing the gate fixed one surface. The blind spot is structural: any surface
consuming an externally-shaped payload can pass every test one layer below the
boundary and fail at it.

So the surfaces are enumerated. Each either has a test that crosses its real
boundary, or a stated reason why not — the same coverage-is-stated pattern as
the falsification harness, because a registry that quietly lists only the
covered ones reads as covering everything.
"""

from __future__ import annotations

from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


# surface -> (what feeds it, the test that crosses that boundary)
BOUNDARY_TESTS: dict[str, tuple[str, str]] = {
    "pre-tool gate": (
        "the host's PreToolUse JSON payload, through the hook process",
        "tests/test_hook_end_to_end.py"),
    "installed plugin build": (
        "the same payload, against the artifact a user actually receives",
        "tests/probe_installed_build.py"),
    "composite action manifest": (
        "GitHub's manifest parser, which is the only thing that ever read it",
        "tests/test_ci_gates.py"),
    "portable plugin manifest": (
        "another client's schema validator, against a closed field set",
        "tests/test_portable_manifest.py"),
    "session transcript": (
        "the host's own session log, as written to disk",
        "tests/test_usage.py"),
    "release gates": (
        "the workflow file's own gate list, with exit codes checked",
        "tests/test_ci_gates.py"),
    "user-prompt hook": (
        "the host's UserPromptSubmit payload, through the hook process and "
        "into a real archive",
        "tests/test_request_hook.py"),
    "session-end hook": (
        "the host's SessionEnd payload (no summary, as the host sends it), "
        "through the hook's main and into a real archive",
        "tests/test_session_end_auto_checkpoint.py"),
    "post-edit hook": (
        "the host's PostToolUse payload for Write/Edit, through the hook "
        "process, with the policy both off and on",
        "tests/test_post_edit_hook.py"),
    "stop hook": (
        "the host's Stop payload with a real transcript file, through the "
        "hook process - claim-shaped final text with and without a record",
        "tests/test_stop_claim_advisory.py"),
    "opencode adapter": (
        "the shipped Bun shim, driven by Bun against the real gate: deny "
        "throws, allow passes, missing root fails closed",
        "tests/test_opencode_plugin.py"),
}

# Surfaces with no boundary test, and why. Listed rather than omitted.
NO_BOUNDARY_TEST: dict[str, str] = {
    "session-start hook": "emits a brief rather than a decision; a wrong brief "
                          "degrades the session but cannot permit an operation",
    "pre-compact hook": "same shape as session-start, and it fires on a host "
                        "event no test can schedule",
    "cursor adapter": "an instruction file consumed by a host this project "
                      "cannot run in CI; no boundary test written yet",
    "gemini adapter": "an instruction file consumed by a host this project "
                      "cannot run in CI; no boundary test written yet",
}


class RegistryTests(unittest.TestCase):
    def test_every_named_boundary_test_exists(self) -> None:
        missing = [
            path for _surface, (_feeder, path) in BOUNDARY_TESTS.items()
            if not (PLUGIN_ROOT / path).is_file()
        ]
        self.assertEqual(missing, [], f"the registry names a test that is not there: {missing}")

    def test_no_surface_claims_both_a_test_and_an_excuse(self) -> None:
        overlap = sorted(set(BOUNDARY_TESTS) & set(NO_BOUNDARY_TEST))
        self.assertEqual(overlap, [], f"contradictory coverage claims: {overlap}")

    def test_the_covered_set_is_not_silently_empty(self) -> None:
        self.assertGreaterEqual(len(BOUNDARY_TESTS), 5)

    def test_every_reason_says_something(self) -> None:
        """An empty reason is an omission wearing the clothes of a decision."""
        for surface, reason in NO_BOUNDARY_TEST.items():
            self.assertGreater(len(reason), 25, surface)


class NewSurfaceTests(unittest.TestCase):
    """A surface added without a boundary test must fail here, not in a release.

    The hooks manifest is the list of what the host actually invokes, so a hook
    appearing there is a surface whether or not anyone remembered this file.
    """

    def test_every_hook_the_host_invokes_is_accounted_for(self) -> None:
        import json

        manifest = PLUGIN_ROOT / "hooks" / "hooks.json"
        declared = json.loads(manifest.read_text(encoding="utf-8"))
        events = {
            str(event).lower()
            for event in (declared.get("hooks") or {}).keys()
        }
        # Map the host's event names onto the surfaces named above. CX-3
        # merged Codex's own native, snake_case event keys into this same
        # shared file (`session_start`, `pre_tool_use`) alongside Claude's
        # CamelCase ones - they invoke the exact same CLI branches
        # (`session-start`/the fast gate) as their Claude-cased aliases, so
        # they map onto the SAME already-registered surfaces, not new ones.
        known = {
            "pretooluse": "pre-tool gate",
            "pre_tool_use": "pre-tool gate",
            "sessionstart": "session-start hook",
            "session_start": "session-start hook",
            "userpromptsubmit": "user-prompt hook",
            "precompact": "pre-compact hook",
            "sessionend": "session-end hook",
            "stop": "session-end hook",
            "posttooluse": "post-edit hook",
        }
        unaccounted = []
        for event in sorted(events):
            surface = known.get(event)
            if surface is None:
                unaccounted.append(f"{event} (no surface named for it)")
            elif surface not in BOUNDARY_TESTS and surface not in NO_BOUNDARY_TEST:
                unaccounted.append(f"{event} -> {surface}")
        self.assertEqual(
            unaccounted, [],
            "a hook the host invokes has neither a boundary test nor a stated "
            f"reason for lacking one: {unaccounted}")


if __name__ == "__main__":
    unittest.main()

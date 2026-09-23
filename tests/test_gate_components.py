"""A compound command is classified per component; the worst component decides; unknown denies."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import godmode_runtime.godmode_sentinel as sentinel  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "gate_corpus.json"


class ComponentTests(unittest.TestCase):
    def test_mixed_call_names_both_components(self) -> None:
        preview = classify_action("git status && git push --force origin main", project_root=PLUGIN_ROOT)
        tiers = [c["tier"] for c in preview["components"]]
        self.assertEqual(len(tiers), 2)
        self.assertEqual(preview["tier"], "R5")
        self.assertEqual(tiers[1], "R5")
        self.assertFalse(preview["components"][0]["protected"])

    def test_unknown_component_denies_by_default(self) -> None:
        preview = classify_action("ls && frobnicate --now", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["components"][1]["category"], "unknown-command")

    def test_single_command_has_one_component(self) -> None:
        preview = classify_action("git status", project_root=PLUGIN_ROOT)
        self.assertEqual(len(preview["components"]), 1)


class SeparatorScopeTests(unittest.TestCase):
    """Review round 1, S1: deny-by-default applies after every sequencing
    separator, not only `&&` - `;`, a newline and `&` run an unrecognised
    second command exactly as unconditionally as `&&` does when the first
    component succeeds, and `||` runs it whenever the first component is
    arranged to fail. `|` (S3/S4) stays exempt: the pipe position is where
    an unrecognised name is idiomatically a filter, and the corpus backs
    that (every pipe-position unrecognised head in the regression fixture
    is a filter, not a smuggled second command)."""

    def test_semicolon_denies_an_unrecognised_second_command(self) -> None:
        preview = classify_action("ls ; frobnicate --now", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_newline_denies_an_unrecognised_second_command(self) -> None:
        preview = classify_action("ls\nfrobnicate --now", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_background_ampersand_denies_an_unrecognised_second_command(self) -> None:
        preview = classify_action("ls & frobnicate --now", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_or_denies_an_unrecognised_second_command(self) -> None:
        preview = classify_action("ls || frobnicate --now", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_the_pipe_position_stays_a_filter_exemption(self) -> None:
        preview = classify_action("cat x | frobnicate", project_root=PLUGIN_ROOT)
        self.assertFalse(preview["protected"])


class HeadShapeTests(unittest.TestCase):
    """Review round 1, S2: the head shape widened to catch a path-, tilde-
    or quote-spelled unknown command, not only a bareword one - the most
    likely spelling of a genuinely unrecognised command (a relative or
    absolute path to it) was exactly the one the original regex missed."""

    def test_a_relative_path_head_is_denied(self) -> None:
        preview = classify_action("ls ; ./frobnicate.sh", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_quoted_head_is_denied(self) -> None:
        preview = classify_action('ls && "frobnicate"', project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")


class ResolvedHeadTests(unittest.TestCase):
    """Review round 2, N1: the head is resolved the same way `_categorize`
    itself resolves it - past a leading env-assignment prefix - never read
    from raw, un-stripped `argv[0]`. `FOO=1 frobnicate` escaped round 1's
    own fix (`_argv_tokens("FOO=1 frobnicate")[0]` is `"FOO=1"`, which
    `_PLAIN_COMMAND_HEAD` correctly rejects, so the deny never fired)."""

    def test_an_env_assignment_prefix_does_not_hide_the_command(self) -> None:
        preview = classify_action("ls && FOO=1 frobnicate", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")


class PrefixRunnerTests(unittest.TestCase):
    """Review round 2, N2: a pinned read-only head that is also a prefix
    runner (carries another command as its own argument) must not launder
    whatever it runs - `_SEQUENCED_READ_ONLY_HEADS` matching on the head
    alone let `time ./frobnicate.sh` and `do frobnicate` through at
    `time`'s/`do`'s name alone. `time node ...`, the corpus's own reason
    `time` is pinned, must stay allowed."""

    def test_a_prefix_runner_does_not_launder_an_unrecognised_command(self) -> None:
        preview = classify_action("ls && time ./frobnicate.sh", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    # Final review S5 (Task 5 parked residual): the runner's own OPTION
    # (`-p`) used to resolve as the remainder's head, `_PLAIN_COMMAND_HEAD`
    # correctly rejected it, and the deny above never fired - `-p` is
    # stripped before the recursive head test now, so this must deny
    # exactly the same as the bare `time ./frobnicate.sh` case above.
    def test_a_prefix_runner_option_does_not_launder_an_unrecognised_command(self) -> None:
        preview = classify_action("ls && time -p ./frobnicate.sh", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_stripped_control_keyword_does_not_launder_an_unrecognised_command(self) -> None:
        # `do` is not in `_PREFIX_RUNNER_HEADS` at all - `_categorize`'s own
        # `_CONTROL_PREFIX` strips it before a head is ever resolved, so
        # `do frobnicate` already reads as plain `frobnicate`.
        preview = classify_action("ls && do frobnicate", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_recognised_interpreter_after_the_runner_stays_allowed(self) -> None:
        preview = classify_action(
            "time node packages/render-headless/frames.js --composition x",
            project_root=PLUGIN_ROOT)
        self.assertFalse(preview["protected"])


class PrefixRunnerRemainderLocationTests(unittest.TestCase):
    """Review round 3, D1: the runner's remainder must be cut from the
    STRIPPED text `_categorize` resolved the head from, never from the
    raw segment - round 2's own fix located `head` by searching the raw
    text, so any prefix `_categorize` itself strips (an env assignment, a
    control keyword, a nested one) desynchronised the search, the helper
    returned `None`, and the branch silently allowed instead of denying.
    Every one of these denied at `1edba11` (before the base rule even had
    a prefix-runner concept) and regressed to allowed at `7e5d887`."""

    def test_an_env_assignment_before_the_runner_still_denies(self) -> None:
        preview = classify_action("ls && FOO=1 time ./frobnicate.sh", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_stripped_control_keyword_before_the_runner_still_denies(self) -> None:
        preview = classify_action("ls && do time ./frobnicate.sh", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")

    def test_a_nested_control_structure_before_the_runner_still_denies(self) -> None:
        preview = classify_action(
            "ls && if true; then time ./frobnicate.sh; fi", project_root=PLUGIN_ROOT)
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unknown-command")


class PinnedHeadTests(unittest.TestCase):
    """Review round 1 (S1) / round 2 (N3): every name in
    `_SEQUENCED_READ_ONLY_HEADS`/`_PREFIX_RUNNER_HEADS` is load-bearing -
    removing it must flip at least one real corpus row away from its
    `expected` outcome. Round 1's own version of this test classified each
    SEGMENT STANDALONE, which over-reports "exercised": a segment that only
    ever reaches the deny rule by way of the multi-segment branch (a line
    the substitution branch instead returns as ONE component never gets
    there at all) can pass a standalone check while never being load-
    bearing in the real component path - `echo` did exactly this, passed
    round 1's test, and flipped zero corpus rows when actually removed; it
    is gone from the pinned set now that this test would catch it."""

    @staticmethod
    def _decision(operation: str) -> str:
        verdict = classify_action(operation, project_root=PLUGIN_ROOT)
        if not verdict["protected"]:
            return "allow"
        return "refuse" if verdict["tier"] == "R5" else "ask"

    def _flips_without(self, attr: str, name: str) -> int:
        entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
        original = getattr(sentinel, attr)
        setattr(sentinel, attr, original - {name})
        try:
            return sum(1 for entry in entries
                       if self._decision(entry["operation"]) != entry["expected"])
        finally:
            setattr(sentinel, attr, original)

    def test_every_pinned_head_is_load_bearing(self) -> None:
        for name in sorted(sentinel._SEQUENCED_READ_ONLY_HEADS):
            with self.subTest(head=name):
                flips = self._flips_without("_SEQUENCED_READ_ONLY_HEADS", name)
                self.assertGreaterEqual(
                    flips, 1, f"{name!r} is pinned but removing it flips no corpus row")

    def test_every_prefix_runner_is_load_bearing(self) -> None:
        for name in sorted(sentinel._PREFIX_RUNNER_HEADS):
            with self.subTest(head=name):
                flips = self._flips_without("_PREFIX_RUNNER_HEADS", name)
                self.assertGreaterEqual(
                    flips, 1, f"{name!r} is pinned but removing it flips no corpus row")


if __name__ == "__main__":
    unittest.main()

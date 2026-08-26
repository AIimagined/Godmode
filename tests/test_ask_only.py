"""`ask_only`: the focused posture, and the digest that proposes it.

Field report (2026-08-27, another project, one session in observe mode):
304 would-have-asked, 0 would-have-denied. 137 inline interpreter runs, 78
scratchpad writes, 46 heredoc test-file writes - and the thirteen moments
that were genuinely risky (worktree discards, a remote write, process
kills) sat in the same "ask" bucket. In enforce mode that is an interrupt
a minute, ~97% on reversible work. Alert fatigue, then off within a day.

`ask_only` in the policy names the categories that keep asking. Every
other R2/R3 ask becomes an allow with an `action` record that says it was
silenced by `ask_only`. R4 still asks and R5 still denies whatever the
list says - the list narrows attention, it never lowers the ceiling.

`roi --digest` computes the list from the observed records - the four
irreversible categories plus any category that produced an R4/R5 event -
and states how many asks it keeps and silences. Propose, never install:
the operator writes the key by hand.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_roi import IRREVERSIBLE_CATEGORIES, roi_digest  # noqa: E402
from godmode_runtime.godmode_sentinel import POLICY_FILENAME, local_authorization_policy  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-askonly-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            yield root, Chronicle(resolve_anchor(root))


def _observed(archive, category: str, tier: str, n: int) -> None:
    for i in range(n):
        archive.append("refusal", category, {
            "category": category, "tier": tier, "observed": True,
            "would_have": "deny" if tier == "R5" else "ask",
            "operation": f"op-{category}-{i}", "tool": "Bash", "reason": "test",
        })


class AskOnlyPolicyTests(unittest.TestCase):
    def test_ask_only_parses_as_a_category_tuple(self) -> None:
        with _project() as (root, archive):
            (root / POLICY_FILENAME).write_text(
                json.dumps({"ask_only": ["worktree-discard", "process-control"]}),
                encoding="utf-8")
            policy = local_authorization_policy(archive)
        self.assertEqual(policy["ask_only"], ("worktree-discard", "process-control"))

    def test_a_malformed_ask_only_refuses_loudly(self) -> None:
        with _project() as (root, archive):
            (root / POLICY_FILENAME).write_text(json.dumps({"ask_only": "worktree-discard"}),
                                                encoding="utf-8")
            with self.assertRaises(AuthorizationError):
                local_authorization_policy(archive)


class DigestTuneTests(unittest.TestCase):
    def test_the_tune_keeps_the_irreversible_and_silences_the_rest(self) -> None:
        self.assertEqual(IRREVERSIBLE_CATEGORIES, (
            "worktree-discard", "git-history-or-remote",
            "release-or-external-write", "process-control"))
        with _project() as (root, archive):
            (root / POLICY_FILENAME).write_text('{"gate_mode": "observe"}', encoding="utf-8")
            _observed(archive, "interpreter-opaque-inline", "R2", 137)
            _observed(archive, "worktree-file-mutation", "R2", 78)
            _observed(archive, "unknown-command", "R3", 46)
            _observed(archive, "filesystem-mutation", "R4", 17)
            _observed(archive, "process-control", "R3", 6)
            _observed(archive, "worktree-discard", "R3", 3)
            _observed(archive, "git-history-or-remote", "R3", 2)
            _observed(archive, "release-or-external-write", "R4", 2)
            digest = roi_digest(archive)
        tune = digest["tune"]
        self.assertEqual(digest["would_have_asked"], 291)
        # The four irreversible categories, plus filesystem-mutation because
        # it produced R4 events - sorted, no duplicates.
        self.assertEqual(tune["ask_only"], sorted({
            *IRREVERSIBLE_CATEGORIES, "filesystem-mutation"}))
        self.assertEqual(tune["asks_kept"], 17 + 6 + 3 + 2 + 2)
        self.assertEqual(tune["asks_silenced"], 137 + 78 + 46)
        self.assertEqual(tune["silenced_by_category"]["interpreter-opaque-inline"], 137)
        self.assertEqual(tune["policy"], {"ask_only": tune["ask_only"]})
        self.assertIn("by hand", tune["note"])

    def test_no_observed_records_means_no_tune(self) -> None:
        with _project() as (_root, archive):
            digest = roi_digest(archive)
        self.assertIsNone(digest["tune"])


if __name__ == "__main__":
    unittest.main()

"""Depth tests for the sentinel: mutating-flag classification, capability
scoping to repository identity, and policy-driven tier/TTL behaviour.

These exist because the safe-inspection prefix match was verified live to
classify `git branch -d X` as read-only: a pattern that can match a mutating
flag form is a hole in the boundary, not a convenience.
"""

from __future__ import annotations

from contextlib import contextmanager
import base64
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
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker,
    classify_action,
)


PASSWORD = "correct-horse-local-only"  # godmode: allow-secret


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def token_body(token: str) -> dict:
    encoded = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


class BranchMutationClassificationTests(unittest.TestCase):
    def test_branch_delete_and_rename_forms_are_protected(self) -> None:
        for operation in (
            "git branch -d feature/login",
            "git branch -D feature/login",
            "git branch --delete feature/login",
            "git branch --delete --force feature/login",
            "git branch -m old-name new-name",
            "git branch -M old-name new-name",
            "git branch --move old new",
            "git branch -c source copy",
            "git branch -f main HEAD~3",
            "git branch --force main HEAD~3",
        ):
            preview = classify_action(operation)
            self.assertTrue(preview["protected"], operation)
            self.assertEqual(preview["category"], "git-branch-mutation", operation)

    def test_branch_listing_forms_stay_read_only_r0(self) -> None:
        for operation in (
            "git branch",
            "git branch --list",
            "git branch --list 'feature/*'",
            "git branch -a",
            "git branch -v",
            "git branch -vv",
            "git branch -avv",
            "git branch --show-current",
            "git branch --merged main",
            "git branch --contains abc123",
        ):
            preview = classify_action(operation)
            self.assertFalse(preview["protected"], operation)
            self.assertEqual(preview["category"], "read-only-inspection", operation)
            self.assertEqual(preview["tier"], "R0", operation)

    def test_branch_creation_fails_closed(self) -> None:
        # `git branch topic` creates a ref; it must never pass as inspection.
        preview = classify_action("git branch topic")
        self.assertTrue(preview["protected"])

    def test_force_delete_is_r5_with_second_confirmation(self) -> None:
        preview = classify_action("git branch -D feature/login")
        self.assertEqual(preview["tier"], "R5")
        self.assertTrue(preview["second_confirmation_required"])
        # Plain delete is history mutation, not the irreversible tier.
        gentle = classify_action("git branch -d feature/login")
        self.assertEqual(gentle["tier"], "R3")
        self.assertFalse(gentle["second_confirmation_required"])
        # --delete --force is the long spelling of -D.
        long_form = classify_action("git branch --delete --force feature/login")
        self.assertEqual(long_form["tier"], "R5")

    def test_safe_prefix_cannot_smuggle_a_second_command(self) -> None:
        preview = classify_action("git branch --list && rm important.txt")
        self.assertTrue(preview["protected"])


class TagStashRemoteClassificationTests(unittest.TestCase):
    def test_tag_listing_is_safe_but_tag_creation_is_not(self) -> None:
        for operation in ("git tag", "git tag -l 'v*'", "git tag --list", "git tag -n9"):
            preview = classify_action(operation)
            self.assertFalse(preview["protected"], operation)
            self.assertEqual(preview["tier"], "R0", operation)
        for operation in ("git tag v1.0.0", "git tag -a v1.0.0 -m release", "git tag -d v1.0.0"):
            preview = classify_action(operation)
            self.assertTrue(preview["protected"], operation)
            self.assertEqual(preview["category"], "git-history-or-remote", operation)

    def test_stash_listing_is_safe_but_stash_mutation_is_not(self) -> None:
        for operation in ("git stash list", "git stash show", "git stash show -p stash@{0}"):
            preview = classify_action(operation)
            self.assertFalse(preview["protected"], operation)
        for operation in ("git stash drop stash@{0}", "git stash pop", "git stash clear", "git stash"):
            preview = classify_action(operation)
            self.assertTrue(preview["protected"], operation)
        # `git stash drop` is a git mutation; the word "drop" alone must not
        # send it to the database category.
        self.assertEqual(
            classify_action("git stash drop stash@{0}")["category"],
            "git-history-or-remote",
        )

    def test_remote_listing_is_safe_but_remote_mutation_is_not(self) -> None:
        for operation in ("git remote", "git remote -v", "git remote show origin",
                          "git remote get-url origin"):
            preview = classify_action(operation)
            self.assertFalse(preview["protected"], operation)
        for operation in ("git remote add origin example", "git remote remove origin",
                          "git remote set-url origin example", "git remote prune origin"):
            preview = classify_action(operation)
            self.assertTrue(preview["protected"], operation)
            self.assertEqual(preview["category"], "git-history-or-remote", operation)


class RiskTierTests(unittest.TestCase):
    def test_tiers_cover_the_ladder(self) -> None:
        # A commit sits at R2 with a file edit, not at R3 with history
        # rewriting: it is local, reversible, and loses nothing. It was gated
        # until a live session showed that made committing impossible, because
        # no host tool call carries a field a capability could travel in.
        # `--amend`, `reset` and `push` are the operations that earn R3+.
        expectations = {
            "git status": "R0",
            "git commit -m 'save'": "R2",
            "git commit --amend": "R3",
            "delete from users where id = 4": "R3",
            "change an unspecified production setting": "R3",
            "git push origin main": "R4",
            "deploy the release to production": "R4",
            "rm -rf build/": "R4",
        }
        for operation, tier in expectations.items():
            preview = classify_action(operation)
            self.assertEqual(preview["tier"], tier, operation)
            self.assertFalse(preview["second_confirmation_required"], operation)

    def test_destructive_forms_are_r5(self) -> None:
        for operation in (
            "git push --force origin main",
            "git push -f origin main",
            "git push --force-with-lease origin main",
            "git reset --hard HEAD~3",
            "git clean -fd",
            "git clean --force",
            "DROP TABLE users",
            "truncate table events",
        ):
            preview = classify_action(operation)
            self.assertEqual(preview["tier"], "R5", operation)
            self.assertTrue(preview["second_confirmation_required"], operation)

    def test_unclassified_mutation_never_drops_below_r3(self) -> None:
        preview = classify_action("perform an unnamed maintenance operation")
        self.assertEqual(preview["category"], "unclassified-mutation")
        self.assertEqual(preview["tier"], "R3")


class CapabilityScopeTests(unittest.TestCase):
    def test_capability_refuses_consume_under_another_context(self) -> None:
        operation = "git push origin main"
        here = {"project_key": "aaa111", "worktree": "w" * 64, "head": "abc123"}
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            for field, label in (
                ("project_key", "repository"),
                ("worktree", "worktree"),
                ("head", "HEAD"),
            ):
                token = broker.issue(operation, PASSWORD, ttl_seconds=60, context=here)
                elsewhere = dict(here)
                elsewhere[field] = "different-" + field
                with self.assertRaises(AuthorizationError) as caught:
                    broker.consume(operation, token, context=elsewhere)
                self.assertIn(f"another {label}", str(caught.exception))
            # A matching context still consumes.
            token = broker.issue(operation, PASSWORD, ttl_seconds=60, context=here)
            result = broker.consume(operation, token, context=dict(here))
            self.assertNotIn("unscoped", result)

    def test_default_context_binds_to_the_anchor_and_round_trips(self) -> None:
        operation = "git push origin main"
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue(operation, PASSWORD, ttl_seconds=60)
            self.assertEqual(token_body(token)["context"]["project_key"], anchor.project_key)
            result = broker.consume(operation, token)
            self.assertNotIn("unscoped", result)

    def test_context_free_tokens_still_consume_but_are_marked_unscoped(self) -> None:
        operation = "git push origin main"
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue(operation, PASSWORD, ttl_seconds=60, context={})
            self.assertNotIn("context", token_body(token))
            result = broker.consume(operation, token)
            self.assertTrue(result["unscoped"])


class AuthorizationPolicyTests(unittest.TestCase):
    @staticmethod
    def write_policy(project: Path, payload) -> None:
        (project / ".godmode-authorization-policy.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def issued_lifetime(self, archive) -> int:
        broker = CapabilityBroker(archive)
        broker.configure(PASSWORD)
        token = broker.issue("git push origin main", PASSWORD)
        body = token_body(token)
        return body["expires_at"] - body["issued_at"]

    def test_policy_ttl_clamps_to_60_and_900(self) -> None:
        for configured, expected in ((30, 60), (5000, 900), (300, 300)):
            with isolated_project() as (project, _state, _anchor, archive):
                archive.initialize()
                self.write_policy(project, {"capability_ttl_seconds": configured})
                self.assertEqual(self.issued_lifetime(archive), expected)

    def test_without_a_policy_the_default_ttl_stays_current(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertEqual(self.issued_lifetime(archive), 180)

    def test_password_required_extends_but_never_shrinks_protection(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            # Without policy a read-only request is refused as unnecessary.
            with self.assertRaises(AuthorizationError):
                broker.request("git status")
            self.write_policy(
                project,
                {"password_required": ["read-only-inspection"]},
            )
            asked = broker.request("git status")
            self.assertEqual(asked["state"], "requested")
            # Already-protected categories are unaffected: extension only.
            self.assertTrue(classify_action("git push origin main")["protected"])

    def test_a_malformed_policy_fails_closed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".godmode-authorization-policy.json").write_text(
                "{not json", encoding="utf-8"
            )
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with self.assertRaises(AuthorizationError):
                broker.issue("git push origin main", PASSWORD)


if __name__ == "__main__":
    unittest.main()

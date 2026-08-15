"""`godmode init --profile novice|standard|strict` (U-E8).

A new project and a mature one want different STARTING points on the same
tighten-only authorization ratchet - never a different ratchet. `standard`
is a pinned no-op (today's defaults, byte-for-byte); `novice` widens
`approval_required` to two categories the classifier otherwise allows at
its own discretion; `strict` widens it to `release-or-external-write` and
only *suggests* `password_required` (never writes it - see
godmode_profile.py's own docstring for why). No profile may ever remove an
`approval_required` category already explicit in
`.godmode-authorization-policy.json`; attempting to is refused, naming the
category, which is the plant this unit ships.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_profile import (  # noqa: E402
    POLICY_FILENAME, PROFILE_NAMES, apply_profile,
)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker, classify_action, local_authorization_policy,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _run(project: Path, *argv: str):
    from godmode_runtime.godmode_console import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = main(["--project", str(project), *argv])
    payload = json.loads(buffer.getvalue())
    return exit_code, payload


class NoProfileIsUntouched(unittest.TestCase):
    """Regression pin: absent `--profile`, `init` is exactly what it was."""

    def test_plain_init_has_no_profile_key_and_writes_no_policy_file(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            exit_code, payload = _run(project, "init")
            self.assertEqual(exit_code, 0)
            self.assertNotIn("profile", payload)
            self.assertFalse((project / POLICY_FILENAME).exists())

    def test_init_with_roles_and_detect_unaffected_by_profile_support(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            exit_code, payload = _run(project, "init", "--detect")
            self.assertEqual(exit_code, 0)
            self.assertNotIn("profile", payload)
            self.assertIn("detect", payload)


class StandardIsANoOp(unittest.TestCase):
    def test_standard_writes_no_policy_file_on_a_fresh_project(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            result = apply_profile(project, "standard")
            self.assertFalse(result["written"])
            self.assertFalse((project / POLICY_FILENAME).exists())
            self.assertIn("(profile: standard)", result["posture"][0])

    def test_standard_via_init_matches_absent_profile_on_disk(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            exit_code, payload = _run(project, "init", "--profile", "standard")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["profile"]["profile"], "standard")
            self.assertFalse((project / POLICY_FILENAME).exists())

    def test_standard_does_not_disturb_an_existing_explicit_policy(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            apply_profile(project, "strict")
            before = (project / POLICY_FILENAME).read_text(encoding="utf-8")
            result = apply_profile(project, "standard")
            self.assertFalse(result["written"])
            self.assertEqual((project / POLICY_FILENAME).read_text(encoding="utf-8"), before)


class NoviceIsAskHeavy(unittest.TestCase):
    def test_novice_widens_approval_required_with_provenance(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            result = apply_profile(project, "novice")
            self.assertTrue(result["written"])
            self.assertIn("worktree-file-mutation", result["approval_required"])
            self.assertIn("git-branch-create", result["approval_required"])
            for line in result["posture"]:
                self.assertIn("(profile: novice)", line)
            on_disk = json.loads((project / POLICY_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(
                sorted(on_disk["approval_required"]),
                ["git-branch-create", "worktree-file-mutation"],
            )

    def test_novice_makes_an_ordinary_edit_ask_instead_of_allow(self) -> None:
        """The probe: an R2 file write, silently allowed by default, now asks."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            apply_profile(project, "novice")
            policy = local_authorization_policy(archive)
            before = classify_action("write file notes.txt", project_root=project)
            after = classify_action(
                "write file notes.txt", project_root=project,
                require_approval=policy.get("approval_required", ()),
            )
            self.assertFalse(before["protected"])
            self.assertTrue(after["protected"])
            self.assertNotEqual(after["tier"], "R5")  # ask, never a stop

    def test_novice_reapplied_is_idempotent(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            apply_profile(project, "novice")
            second = apply_profile(project, "novice")
            self.assertFalse(second["written"])


class StrictIsFullEnforcement(unittest.TestCase):
    def test_strict_widens_approval_required_for_release_or_external_write(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            result = apply_profile(project, "strict")
            self.assertTrue(result["written"])
            self.assertEqual(result["approval_required"], ["release-or-external-write"])
            self.assertIn("(profile: strict)", result["posture"][0])

    def test_strict_only_suggests_password_required_never_writes_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            result = apply_profile(project, "strict")
            self.assertTrue(
                any("password_required" in s for s in result.get("suggestions", [])),
                result,
            )
            on_disk = json.loads((project / POLICY_FILENAME).read_text(encoding="utf-8"))
            self.assertNotIn("password_required", on_disk)

    def test_strict_makes_a_release_op_ask_via_the_real_policy_reader(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            apply_profile(project, "strict")
            policy = local_authorization_policy(archive)
            self.assertEqual(list(policy.get("approval_required", ())), ["release-or-external-write"])


class TightenOnlyRatchet(unittest.TestCase):
    """The plant this unit ships: a weaker profile over an explicit stronger
    one is refused, naming the setting - never silently applied."""

    def test_strict_then_novice_is_refused_naming_the_dropped_setting(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            apply_profile(project, "strict")
            with self.assertRaises(AuthorizationError) as ctx:
                apply_profile(project, "novice")
            self.assertIn("release-or-external-write", str(ctx.exception))
            # Refused, not partially applied: the file is untouched.
            on_disk = json.loads((project / POLICY_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(on_disk["approval_required"], ["release-or-external-write"])

    def test_novice_then_strict_is_also_refused_naming_both_settings(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            apply_profile(project, "novice")
            with self.assertRaises(AuthorizationError) as ctx:
                apply_profile(project, "strict")
            message = str(ctx.exception)
            self.assertIn("git-branch-create", message)
            self.assertIn("worktree-file-mutation", message)

    def test_cli_surfaces_the_refusal_as_a_typed_error_exit_2(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            exit_code, _ = _run(project, "init", "--profile", "strict")
            self.assertEqual(exit_code, 0)
            from godmode_runtime.godmode_console import main

            buffer = io.StringIO()
            from contextlib import redirect_stderr

            with redirect_stdout(io.StringIO()), redirect_stderr(buffer):
                exit_code = main(["--project", str(project), "init", "--profile", "novice"])
            self.assertEqual(exit_code, 2)
            self.assertIn("release-or-external-write", buffer.getvalue())

    def test_a_hand_edited_policy_is_equally_protected(self) -> None:
        """Tighten-only does not care who wrote the file - only that it is
        already on record. A hand-authored entry is exactly as protected as
        one a profile wrote."""
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / POLICY_FILENAME).write_text(
                json.dumps({"approval_required": ["database-mutation"]}), encoding="utf-8"
            )
            with self.assertRaises(AuthorizationError) as ctx:
                apply_profile(project, "novice")
            self.assertIn("database-mutation", str(ctx.exception))


class UnknownProfile(unittest.TestCase):
    def test_apply_profile_rejects_a_name_outside_the_closed_set(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            with self.assertRaises(Exception):
                apply_profile(project, "expert")

    def test_profile_names_is_exactly_the_documented_three(self) -> None:
        self.assertEqual(set(PROFILE_NAMES), {"novice", "standard", "strict"})


if __name__ == "__main__":
    unittest.main()

"""NS-12f: the eval matrix runs each skill under every model the operator
declares, and flags a skill that only passes under its authoring model.

This harness makes no model or network call anywhere - it never has. So the
flag logic here is proven entirely against fabricated `results_by_model`
fixtures: dicts of pre-decided pass/fail outcomes per model per skill. No
test in this file invokes a model, opens a socket, or shells out to one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from _host_env import scrubbed_environment  # noqa: E402
from _repo_copy import copy_repo_without_git, initialise  # noqa: E402
from godmode_runtime.godmode_evals import (  # noqa: E402
    CROSS_MODEL_SCHEMA,
    DEFAULT_MODEL,
    _authoring_model,
    _declared_models,
    cross_model_matrix,
)


class DeclaredModelsTests(unittest.TestCase):
    def test_default_is_a_single_row_when_nothing_declared(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                self.assertEqual(_declared_models(root), [DEFAULT_MODEL])

    def test_env_var_is_comma_separated_trimmed_and_deduped(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.dict(
                os.environ, {"GODMODE_EVAL_MODELS": " alpha-model, beta-model ,alpha-model"},
                clear=False,
            ):
                self.assertEqual(_declared_models(root), ["alpha-model", "beta-model"])

    def test_settings_file_is_read_when_env_var_absent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".godmode-evals.json").write_text(
                json.dumps({"models": ["gamma-model", "delta-model"]}), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                self.assertEqual(
                    _declared_models(root), ["gamma-model", "delta-model"])

    def test_env_var_wins_over_settings_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".godmode-evals.json").write_text(
                json.dumps({"models": ["from-file"]}), encoding="utf-8")
            with mock.patch.dict(
                os.environ, {"GODMODE_EVAL_MODELS": "from-env"}, clear=False
            ):
                self.assertEqual(_declared_models(root), ["from-env"])

    def test_malformed_settings_file_reads_as_declared_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".godmode-evals.json").write_text("not json", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                self.assertEqual(_declared_models(root), [DEFAULT_MODEL])

    def test_settings_file_without_models_list_reads_as_declared_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".godmode-evals.json").write_text(
                json.dumps({"other_key": True}), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                self.assertEqual(_declared_models(root), [DEFAULT_MODEL])


class AuthoringModelTests(unittest.TestCase):
    def test_skill_md_frontmatter_wins(self):
        with tempfile.TemporaryDirectory() as raw:
            skill_dir = Path(raw) / "skills" / "alpha"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: alpha\nmodel: skill-declared-model\n---\n", encoding="utf-8")
            self.assertEqual(
                _authoring_model(skill_dir, ["fallback-model"]), "skill-declared-model")

    def test_purpose_md_used_when_skill_md_has_no_model_line(self):
        with tempfile.TemporaryDirectory() as raw:
            skill_dir = Path(raw) / "skills" / "alpha"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: alpha\ndescription: does things\n---\n", encoding="utf-8")
            (skill_dir / "PURPOSE.md").write_text(
                "authoring_model: purpose-declared-model\n", encoding="utf-8")
            self.assertEqual(
                _authoring_model(skill_dir, ["fallback-model"]), "purpose-declared-model")

    def test_falls_back_to_first_declared_model(self):
        with tempfile.TemporaryDirectory() as raw:
            skill_dir = Path(raw) / "skills" / "alpha"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: alpha\ndescription: does things\n---\n", encoding="utf-8")
            self.assertEqual(
                _authoring_model(skill_dir, ["first-declared", "second-declared"]),
                "first-declared")

    def test_falls_back_when_skill_directory_does_not_exist(self):
        # A fabricated-fixture test may never create a skill directory at
        # all; the fallback must still hold rather than raise.
        missing = Path(tempfile.gettempdir()) / "godmode-nonexistent-skill-dir-xyz"
        self.assertEqual(_authoring_model(missing, ["only-declared"]), "only-declared")


class CrossModelMatrixTests(unittest.TestCase):
    """All fabricated: `results_by_model` is handed in directly, so no real
    routing or behaviour eval, model, or network call ever runs here."""

    def test_default_single_row_never_flags_anything(self):
        report = cross_model_matrix(
            Path("unused"),
            models=[DEFAULT_MODEL],
            results_by_model={DEFAULT_MODEL: {"alpha": True, "beta": False}},
            authoring_models={"alpha": DEFAULT_MODEL, "beta": DEFAULT_MODEL},
        )
        self.assertEqual(report["schema"], CROSS_MODEL_SCHEMA)
        self.assertEqual(report["models"], [DEFAULT_MODEL])
        self.assertEqual(report["model_specific_skills"], [])
        self.assertEqual(report["verdict"], "cross-model-clean")
        # One row per skill per model - two skills, one model, two rows.
        self.assertEqual(len(report["rows"]), 2)

    def test_one_row_per_skill_per_model(self):
        report = cross_model_matrix(
            Path("unused"),
            models=["model-a", "model-b", "model-c"],
            results_by_model={
                "model-a": {"alpha": True, "beta": True},
                "model-b": {"alpha": True, "beta": True},
                "model-c": {"alpha": True, "beta": True},
            },
            authoring_models={"alpha": "model-a", "beta": "model-b"},
        )
        self.assertEqual(len(report["rows"]), 6)
        pairs = {(row["skill"], row["model"]) for row in report["rows"]}
        self.assertEqual(
            pairs,
            {
                ("alpha", "model-a"), ("alpha", "model-b"), ("alpha", "model-c"),
                ("beta", "model-a"), ("beta", "model-b"), ("beta", "model-c"),
            },
        )

    def test_passes_only_under_authoring_model_is_flagged(self):
        # The paper's negative-transfer case: a skill leaning on a
        # low-level workaround that only its authoring model tolerates.
        report = cross_model_matrix(
            Path("unused"),
            models=["author-model", "other-model"],
            results_by_model={
                "author-model": {"quirky": True},
                "other-model": {"quirky": False},
            },
            authoring_models={"quirky": "author-model"},
        )
        self.assertEqual(report["model_specific_skills"], ["quirky"])
        self.assertTrue(report["skills"]["quirky"]["model_specific"])
        self.assertEqual(report["skills"]["quirky"]["passing_models"], ["author-model"])
        self.assertEqual(report["verdict"], "model-specific-skills-found")

    def test_passing_under_every_model_is_not_flagged(self):
        report = cross_model_matrix(
            Path("unused"),
            models=["author-model", "other-model"],
            results_by_model={
                "author-model": {"portable": True},
                "other-model": {"portable": True},
            },
            authoring_models={"portable": "author-model"},
        )
        self.assertEqual(report["model_specific_skills"], [])
        self.assertFalse(report["skills"]["portable"]["model_specific"])
        self.assertEqual(report["verdict"], "cross-model-clean")

    def test_failing_under_every_model_is_not_model_specific(self):
        # A skill that fails everywhere, including under its own authoring
        # model, is a plain failure - not evidence of a transfer problem.
        report = cross_model_matrix(
            Path("unused"),
            models=["author-model", "other-model"],
            results_by_model={
                "author-model": {"broken": False},
                "other-model": {"broken": False},
            },
            authoring_models={"broken": "author-model"},
        )
        self.assertEqual(report["model_specific_skills"], [])
        self.assertFalse(report["skills"]["broken"]["model_specific"])
        self.assertEqual(report["skills"]["broken"]["passing_models"], [])

    def test_single_declared_model_never_flags_even_if_authoring_only(self):
        # Only one model declared: there is no "other model" to fail under,
        # so nothing can be model-specific by definition.
        report = cross_model_matrix(
            Path("unused"),
            models=["only-model"],
            results_by_model={"only-model": {"solo": True}},
            authoring_models={"solo": "only-model"},
        )
        self.assertEqual(report["model_specific_skills"], [])
        self.assertEqual(report["verdict"], "cross-model-clean")

    def test_authoring_model_not_declared_is_never_flagged(self):
        # The authoring model itself was never included in the declared
        # list, so the matrix has no basis to say the skill "only" works
        # under it.
        report = cross_model_matrix(
            Path("unused"),
            models=["model-a", "model-b"],
            results_by_model={
                "model-a": {"orphan": True},
                "model-b": {"orphan": False},
            },
            authoring_models={"orphan": "model-not-in-matrix"},
        )
        self.assertEqual(report["model_specific_skills"], [])

    def test_partial_pass_across_more_than_two_models_is_flagged(self):
        report = cross_model_matrix(
            Path("unused"),
            models=["model-a", "model-b", "model-c"],
            results_by_model={
                "model-a": {"picky": True},
                "model-b": {"picky": False},
                "model-c": {"picky": False},
            },
            authoring_models={"picky": "model-a"},
        )
        self.assertEqual(report["model_specific_skills"], ["picky"])

    def test_deterministic(self):
        kwargs = dict(
            models=["model-a", "model-b"],
            results_by_model={
                "model-a": {"alpha": True, "beta": False},
                "model-b": {"alpha": False, "beta": False},
            },
            authoring_models={"alpha": "model-a", "beta": "model-a"},
        )
        first = cross_model_matrix(Path("unused"), **kwargs)
        second = cross_model_matrix(Path("unused"), **kwargs)
        self.assertEqual(first, second)


class CrossModelMatrixRealHarnessTests(unittest.TestCase):
    """Exactly one test touches the real (still model-independent, still no
    model or network call) harness, to prove the default path - no models
    declared, no `results_by_model` supplied - produces a live, non-empty,
    trivially clean matrix against this repository's own shipped skills."""

    def test_repo_default_matrix_is_clean_with_no_models_declared(self):
        # The probes (`planmode specify`, `guard`, `law show`, ...) run the
        # real CLI with `--project .` and WRITE. For a git checkout the
        # archive lives under the git directory and `GODMODE_STATE_HOME`
        # does not redirect it, so this used to write to the developer's
        # live archive while claiming a disposable state home. The probes
        # now run inside a non-git copy of the repository (`_repo_copy`),
        # where the state home is honoured and thrown away with the copy.
        with tempfile.TemporaryDirectory() as raw:
            project = copy_repo_without_git(Path(raw))
            with scrubbed_environment(GODMODE_STATE_HOME=str(Path(raw) / "state")):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                initialise(project)
                # The proof of isolation: the archive landed under the
                # disposable state home, which a git checkout never uses.
                self.assertTrue(any((Path(raw) / "state").rglob("*")),
                                "init did not write under GODMODE_STATE_HOME")
                report = cross_model_matrix(project)
        self.assertEqual(report["models"], [DEFAULT_MODEL])
        self.assertEqual(report["model_specific_skills"], [])
        self.assertEqual(report["verdict"], "cross-model-clean")
        self.assertTrue(report["rows"])
        for row in report["rows"]:
            self.assertEqual(row["model"], DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()


class EvalsReportCarriesTheMatrixTests(unittest.TestCase):
    """The matrix is a property of `godmode evals` itself, not only of the
    library: the JSON report carries a `models` section with the schema,
    and the brief line stays a scalar headline."""

    def test_evals_payload_carries_models_section(self) -> None:
        import argparse
        from godmode_runtime import godmode_console as console
        # `cmd_evals` runs the behaviour probes, and they write (see the
        # matrix test above): same non-git copy, same disposable state home.
        with tempfile.TemporaryDirectory() as raw:
            project = copy_repo_without_git(Path(raw))
            with scrubbed_environment(GODMODE_STATE_HOME=str(Path(raw) / "state")):
                os.environ.pop("GODMODE_EVAL_MODELS", None)
                initialise(project)
                # The proof of isolation: the archive landed under the
                # disposable state home, which a git checkout never uses.
                self.assertTrue(any((Path(raw) / "state").rglob("*")),
                                "init did not write under GODMODE_STATE_HOME")
                runtime = console._runtime(str(project))
                args = argparse.Namespace(write_snapshots=False, write_baseline=False,
                                          ratchet=False, determinism=False)
                payload = console.cmd_evals(args, runtime).payload
        self.assertIn("models", payload)
        self.assertEqual(payload["models"]["schema"], CROSS_MODEL_SCHEMA)
        self.assertTrue(payload["models"]["rows"])
        self.assertNotIn("models", console._brief_line(payload))

"""I-6: a staged code file with no green retest newer than its last edit is
refused at `git commit`; `godmode retest --run` (an attestation citing the
pinning test) clears it; a docs-only commit is never checked at all.

Fix round 1 adds: an uncovered file (no pinning test at all) blocks under
its own `uncovered` category, never folded into the stale list (S3); a
staged deletion is never checked (S4); a retest command whose citation
exceeds `run_check`'s 160-character cap is still recognized via the
structural `data["modules"]` field (S1); and the pre-commit guard's own
"no archive initialized" skip - upstream of this module entirely, at
`godmode_console._cmd_guard_git_hook` - is exercised through the real CLI.

Fix round 2 adds: a rounded-but-actually-stale saved index is never trusted
(D1); a closure-check inspection failure (an atlas build past its own time
budget) blocks unconditionally, even with no declared `git_backstop` policy
(D2iii); `deleted` is re-derived even when only `staged` was supplied (D4);
and a file with no `edit-recorded` action at all lands in its own
`unattested` category, cleared by a retest attestation's per-path blob hash
even on the dirty tree the normal edit-then-retest flow always has (D5).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_closure, godmode_githooks  # noqa: E402
from godmode_runtime.godmode_attest import run_check  # noqa: E402
from godmode_runtime.godmode_closure import (  # noqa: E402
    closure_survey,
    stale_staged_files,
    uncovered_staged_files,
    unattested_staged_files,
)
from godmode_runtime.godmode_retest import retest_plan  # noqa: E402
from test_githooks import _cli  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


def _seed(project: Path) -> None:
    """`scripts/widgetry.py` (returns 1) pinned by `tests/test_widgetry.py`
    (asserts 2) - the same shape `tests/test_retest.py` already uses,
    relocated under `scripts/`/`tests/` so the closure check's own Python-
    under-scripts-or-tests filter actually covers it."""
    (project / "scripts").mkdir()
    (project / "tests").mkdir()
    (project / "scripts" / "widgetry.py").write_text(
        "def widgetry():\n    return 1\n", encoding="utf-8")
    (project / "tests" / "test_widgetry.py").write_text(
        "import unittest\n"
        "from scripts.widgetry import widgetry\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_it(self):\n"
        "        self.assertEqual(widgetry(), 2)\n",
        encoding="utf-8",
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "baseline")


def _run_retest(archive, project: Path) -> None:
    """Mirrors `godmode_console.cmd_retest`'s real wiring (fix round 2):
    `modules=`/`blob_paths=` both threaded through, not just `modules=`."""
    plan = retest_plan(project, base="HEAD")
    for entry in plan["commands"]:
        if not entry.get("command"):
            continue
        argv = entry["command"].split()
        if argv and argv[0] == "python":
            argv[0] = sys.executable
        run_check(archive, "s1", project, f"retest:{entry['runner']}", argv, timeout=60,
                  modules=entry.get("modules"), blob_paths=entry.get("pinned_sources"))


class ClosurePreCommitTests(unittest.TestCase):
    def test_edit_without_retest_is_refused_naming_the_file(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            archive.append("action", "edit-recorded",
                           {"path": "scripts/widgetry.py", "operation": "edit:1"}, evidence=[])

            stale = stale_staged_files(project, archive)
            self.assertEqual([s["path"] for s in stale], ["scripts/widgetry.py"])

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "closure-not-attested")
            self.assertIn("scripts/widgetry.py", decision["reason"])
            self.assertIn("retest --run", decision["reason"])

    def test_retest_run_clears_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            archive.append("action", "edit-recorded",
                           {"path": "scripts/widgetry.py", "operation": "edit:1"}, evidence=[])

            _run_retest(archive, project)

            self.assertEqual(stale_staged_files(project, archive), [])
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)

    def test_docs_only_commit_is_never_checked(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _git(project, "commit", "-q", "--allow-empty", "-m", "root")
            (project / "docs").mkdir()
            (project / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
            _git(project, "add", "-A")

            self.assertEqual(stale_staged_files(project, archive), [])
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)

    def test_no_edit_record_but_blob_matches_a_clean_green_retest_is_not_stale(self) -> None:
        """A file staged with byte-identical content to what a green retest
        already covered *while the tree was clean* - no new `edit-recorded`
        at all, e.g. a git-applied patch that reintroduced known-good bytes
        - is not stale. The current commit's own content for that path is
        irrelevant; only the retested blob at the retest's own recorded
        HEAD is compared."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            archive.append("action", "edit-recorded",
                           {"path": "scripts/widgetry.py", "operation": "edit:1"}, evidence=[])
            _run_retest(archive, project)
            _git(project, "commit", "-q", "-m", "widgetry v2")

            # A second, manual retest run against the now-clean tree (HEAD
            # H1: widgetry() == 2) - this is the "clean tree" green record
            # the blob-equality fallback is allowed to trust.
            run_check(archive, "s1", project, "retest:unittest",
                      [sys.executable, "-m", "unittest", "tests.test_widgetry"], timeout=60)

            # History moves on: widgetry() changes again and is committed
            # directly (H2), well past the retested content.
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 5\n", encoding="utf-8")
            _git(project, "add", "-A")
            _git(project, "commit", "-q", "-m", "widgetry v3")

            # The bytes retested at H1 are reintroduced and staged with no
            # edit-recorded action - the git-applied-patch case.
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")

            staged = subprocess.run(
                ["git", "-C", str(project), "diff", "--cached", "--name-only"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertIn("scripts/widgetry.py", staged, "test setup: expected a staged change")

            # Both buckets a no-edit-record file could land in if the
            # fallback failed - `stale` alone is no longer a strong enough
            # assertion since fix round 2 moved every no-edit-record case
            # to `unattested` (never `stale`).
            self.assertEqual(stale_staged_files(project, archive), [])
            self.assertEqual(unattested_staged_files(project, archive), [])


class UncoveredFileTests(unittest.TestCase):
    """S3 (coordinator ruling): a file no test pins at all - directly or
    through a dependent - blocks under its own `uncovered` category, with
    its own remedy, and is never present in `stale_staged_files`'s list
    (that remedy, "run `retest --run`", is a dead end for a file nothing
    retests)."""

    def test_uncovered_file_blocks_with_its_own_category_and_remedy(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _git(project, "commit", "-q", "--allow-empty", "-m", "root")
            (project / "scripts").mkdir()
            (project / "scripts" / "lonely.py").write_text(
                "def lonely():\n    return 1\n", encoding="utf-8")
            _git(project, "add", "-A")

            self.assertEqual(uncovered_staged_files(project, archive), ["scripts/lonely.py"])
            # Never folded into the stale list under a retest remedy that
            # could never clear it.
            self.assertEqual(stale_staged_files(project, archive), [])

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "uncovered")
            self.assertEqual(decision["uncovered_files"], ["scripts/lonely.py"])
            self.assertIn("scripts/lonely.py", decision["reason"])
            self.assertIn("add a pinning test", decision["reason"])
            self.assertNotIn("retest --run", decision["reason"])


class StagedDeletionTests(unittest.TestCase):
    """S4: a staged deletion of a `.py` under `scripts/`/`hooks/`/`tests/`
    has no closure of its own to attest (it no longer exists) and must
    never be permanently uncommittable through the cooperative path."""

    def test_staged_deletion_is_never_blocked(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            _git(project, "rm", "-q", "tests/test_widgetry.py")

            self.assertEqual(stale_staged_files(project, archive), [])
            self.assertEqual(uncovered_staged_files(project, archive), [])
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)


class MultiModuleCitationTests(unittest.TestCase):
    """S1: `run_check`'s one evidence entry (`cmd:<command>`) is truncated
    at 160 characters. A retest command naming several modules can lose a
    trailing one entirely from that string - this proves the structural
    `data["modules"]` field (written when `run_check` is given `modules=`)
    is what `stale_staged_files` actually reads, not the truncated text."""

    def test_a_pinning_module_past_the_160_char_citation_cap_is_still_recognized(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            padding_modules = [f"tests.test_padding_module_number_{i:02d}" for i in range(6)]
            for dotted in padding_modules:
                (project / "tests" / f"{dotted.rsplit('.', 1)[-1]}.py").write_text(
                    "PADDING = 1\n", encoding="utf-8")
            _git(project, "add", "-A")
            _git(project, "commit", "-q", "-m", "padding modules")

            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            archive.append("action", "edit-recorded",
                           {"path": "scripts/widgetry.py", "operation": "edit:1"}, evidence=[])

            all_modules = padding_modules + ["tests.test_widgetry"]
            command = [sys.executable, "-m", "unittest", *all_modules]
            citation_body = " ".join(command)
            self.assertGreater(len(citation_body), 160,
                               "test setup: command must exceed run_check's citation cap")
            truncated = citation_body[:160]
            self.assertNotIn("tests.test_widgetry", truncated,
                            "test setup: tests.test_widgetry must fall outside the truncated citation")

            outcome = run_check(archive, "s1", project, "retest:unittest", command,
                                timeout=60, modules=all_modules)
            self.assertTrue(outcome["passed"], outcome)

            self.assertEqual(stale_staged_files(project, archive), [])
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)


class NoArchiveSkipTests(unittest.TestCase):
    """Q4: the check is skipped cleanly (allow, with a stated reason) when
    godmode was never initialized for this project - that skip lives
    upstream of `godmode_closure` entirely, at
    `godmode_console._cmd_guard_git_hook` (`runtime.archive.initialized()`
    -> allow), and is exercised here through the real CLI so nothing in
    this module's own code path is ever reached."""

    def test_pre_commit_guard_allows_when_godmode_is_not_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            state_home = base / "state"
            project.mkdir()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            # No `godmode init` ever run for this project - no archive.

            result = _cli(project, state_home, "guard", "--git-hook", "pre-commit")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "allow")
            self.assertIn("not initialized", payload["reason"])


class SavedIndexFreshnessTests(unittest.TestCase):
    """D1 (re-review, blocking): `load_index`'s `confidence` is `round(len(
    fresh) / total, 2)` and reads `1.0` for anything at or above 99.5%
    fresh - `report["stale"]` is the honest signal, and comparing a rounded
    number to `1.0` anywhere a decision depends on "nothing is stale" is
    exactly the fixed defect."""

    def test_a_rounded_but_actually_stale_report_is_never_trusted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / ".godmode-atlas-index.json").write_text("{}", encoding="utf-8")
            # `confidence == 1.0` (rounded) while `stale` is non-empty - the
            # exact shape the re-review demonstrated at 250+ tracked files.
            rounded_but_stale = {
                "atlas": {"built_at": None, "project": None, "files": 1, "symbols": 0,
                         "edges": 0, "unparsed": 0},
                "fresh": [], "stale": ["scripts/widgetry.py"], "missing": [],
                "confidence": 1.0,
            }
            with mock.patch.object(godmode_closure, "load_index",
                                  return_value=rounded_but_stale) as mocked_load, \
                 mock.patch.object(godmode_closure, "rehydrate_index") as mocked_rehydrate, \
                 mock.patch.object(godmode_closure, "build_atlas",
                                   wraps=godmode_closure.build_atlas) as mocked_build:
                godmode_closure._atlas_for_closure(project)
                mocked_load.assert_called_once()
                mocked_rehydrate.assert_not_called()
                mocked_build.assert_called_once()

    def test_a_genuinely_fresh_report_is_rehydrated_without_a_rebuild(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / ".godmode-atlas-index.json").write_text("{}", encoding="utf-8")
            genuinely_fresh = {
                "atlas": {"built_at": None, "project": None, "files": 1, "symbols": 0,
                         "edges": 0, "unparsed": 0},
                "fresh": ["scripts/widgetry.py"], "stale": [], "missing": [],
                "confidence": 1.0,
            }
            with mock.patch.object(godmode_closure, "load_index",
                                  return_value=genuinely_fresh), \
                 mock.patch.object(godmode_closure, "rehydrate_index") as mocked_rehydrate, \
                 mock.patch.object(godmode_closure, "build_atlas") as mocked_build:
                godmode_closure._atlas_for_closure(project)
                mocked_rehydrate.assert_called_once()
                mocked_build.assert_not_called()


class RefreshAtlasIndexTests(unittest.TestCase):
    """D3: a saved index actually gets written, `rehydrate_index`
    reconstructs a real graph from it, and `cmd_retest`'s `--run` wiring
    (`refresh_atlas_index`) is what writes it after a successful run."""

    def test_refresh_writes_an_index_the_closure_check_then_rehydrates(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            report = godmode_closure.refresh_atlas_index(project)
            self.assertIsNotNone(report)
            index_path = project / ".godmode-atlas-index.json"
            self.assertTrue(index_path.is_file())

            from godmode_runtime.godmode_atlas import build as build_atlas, rehydrate_index

            rehydrated = rehydrate_index(index_path, project)
            direct = build_atlas(project, roots=("scripts", "hooks", "tests"))
            self.assertEqual(sorted(rehydrated.files), sorted(direct.files))
            key = lambda view: json.dumps(view, sort_keys=True)  # noqa: E731
            self.assertEqual(
                sorted((s.view() for s in rehydrated.symbols), key=key),
                sorted((s.view() for s in direct.symbols), key=key),
            )
            self.assertEqual(
                sorted((e.view() for e in rehydrated.edges), key=key),
                sorted((e.view() for e in direct.edges), key=key),
            )


class RetestCliRefreshesIndexTests(unittest.TestCase):
    """D2/D3: `godmode retest --run` through the REAL CLI writes/refreshes
    `.godmode-atlas-index.json` on a successful run."""

    def test_retest_run_via_the_cli_writes_the_saved_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            state_home = base / "state"
            project.mkdir()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")

            self.assertEqual(_cli(project, state_home, "init").returncode, 0)
            opened = _cli(project, state_home, "session", "open")
            self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
            index_path = project / ".godmode-atlas-index.json"
            self.assertFalse(index_path.is_file())
            result = _cli(project, state_home, "retest", "--run")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(index_path.is_file(), "retest --run did not write the saved index")


class ClosureFailureBlocksUnconditionallyTests(unittest.TestCase):
    """D2iii (re-review, blocking): an atlas build that trips its own time
    budget must refuse the commit - not silently degrade to an advisory
    allow just because `git_backstop` was never declared. The closure
    check has no declared-policy gate at all (S8); its own failure path
    must not introduce one."""

    def test_atlas_budget_exhaustion_blocks_even_without_declared_policy(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            # `git_backstop` is NOT declared anywhere in this project - the
            # advisory-allow shape `_inspection_failed_result` would have
            # produced must not appear here.

            with mock.patch.object(godmode_closure, "_ATLAS_BUDGET_SECONDS", 0.0):
                decision = godmode_githooks._evaluate_pre_commit(archive, project)

            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "inspection-failed")
            self.assertNotIn("advisory", decision["reason"])
            # Fix round 3 (coordinator ruling b): the trip message names the
            # remedy - `godmode retest --run` builds (and saves) the index.
            self.assertIn("godmode retest --run", decision["reason"])
            # Round 2's message already contained the bare word "build"
            # ("atlas build did not finish...") - that alone never
            # discriminated the round-3 fix. Pin the remedy clause itself.
            self.assertIn("to build the index", decision["reason"])


class PreCommitBudgetTests(unittest.TestCase):
    """Fix round 3 (coordinator ruling b): the commit-time closure build's
    budget is 180s - raised from round 2's 60s, which the re-review
    measured at 94.6% consumed (56.77s) on a cold, real main-checkout
    build, not the warm-worktree figure round 2's own comment cited."""

    def test_the_commit_time_budget_is_180_seconds(self) -> None:
        self.assertEqual(godmode_closure._ATLAS_BUDGET_SECONDS, 180.0)


class RefreshAtlasIndexIsUnboundedTests(unittest.TestCase):
    """Fix round 3 (coordinator ruling a): `refresh_atlas_index` (the
    `godmode retest --run` path) is the deliberate operator action that
    builds the index and must not be bound by the commit-time budget - a
    budget trip at commit time must still have a reachable remedy."""

    def test_refresh_ignores_the_commit_time_budget(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            # A budget of 0.0 would trip `_atlas_for_closure`'s bounded
            # build instantly (see `ClosureFailureBlocksUnconditionallyTests`
            # above); `refresh_atlas_index` must still succeed because it
            # never threads this budget through to `build_atlas` at all.
            with mock.patch.object(godmode_closure, "_ATLAS_BUDGET_SECONDS", 0.0):
                report = godmode_closure.refresh_atlas_index(project)

            self.assertIsNotNone(report, "refresh_atlas_index must be unbounded")
            self.assertTrue((project / ".godmode-atlas-index.json").is_file())


class EmptyIndexCountsAsMissingTests(unittest.TestCase):
    """N1 (re-review 2, ruled): an index with zero stored files reads as
    "fully fresh" under `not stale and not missing` alone, since
    `load_index` only ever iterates the index's own stored files. Ruled:
    an empty index counts as MISSING, so it must never be rehydrated -
    it forces the same real rebuild a genuinely stale/missing report does."""

    def test_an_empty_index_forces_a_rebuild_not_a_rehydrate(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / ".godmode-atlas-index.json").write_text("{}", encoding="utf-8")
            empty_but_unstale = {
                "atlas": {"built_at": None, "project": None, "files": 0, "symbols": 0,
                         "edges": 0, "unparsed": 0},
                "fresh": [], "stale": [], "missing": [], "confidence": 0.0,
            }
            with mock.patch.object(godmode_closure, "load_index",
                                  return_value=empty_but_unstale), \
                 mock.patch.object(godmode_closure, "rehydrate_index") as mocked_rehydrate, \
                 mock.patch.object(godmode_closure, "build_atlas",
                                   wraps=godmode_closure.build_atlas) as mocked_build:
                godmode_closure._atlas_for_closure(project)
                mocked_rehydrate.assert_not_called()
                mocked_build.assert_called_once()


class DeletedIndependentOfStagedTests(unittest.TestCase):
    """D4 (re-review, non-blocking): a caller supplying `staged` alone (the
    signature allows it) must still get a real, re-derived `deleted` set -
    not silently default to "nothing was deleted"."""

    def test_deleted_is_rederived_when_only_staged_is_supplied(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            _git(project, "rm", "-q", "tests/test_widgetry.py")

            survey = closure_survey(project, archive, staged=["tests/test_widgetry.py"])
            self.assertEqual(survey, {"stale": [], "uncovered": [], "unattested": []})


class UnattestedCategoryTests(unittest.TestCase):
    """D5 (coordinator ruling, fix round 2): a staged file with no
    `edit-recorded` action at all AND no green retest covering its current
    content lands in its own `unattested` category - never `stale`, whose
    remedy ("stage the retest result") is a no-op for a file that was
    never recorded as edited to begin with."""

    def test_no_edit_record_and_no_retest_is_unattested_not_stale(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")
            # No edit-recorded action, no retest run at all.

            self.assertEqual(stale_staged_files(project, archive), [])
            self.assertEqual(unattested_staged_files(project, archive),
                             [{"path": "scripts/widgetry.py", "last_green_retest_seq": None}])

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "unattested")
            self.assertIn("scripts/widgetry.py", decision["reason"])
            self.assertIn("retest --run", decision["reason"])
            self.assertIn("record the edit", decision["reason"])
            self.assertNotIn("stage the result", decision["reason"])
            # Fix round 3 (N3, ruled): the remedy no longer says "on a clean
            # tree" - a dirty-tree `retest --run` is exactly what clears
            # this block (proved by `BlobHashRetestSatisfiesUnattestedTests`
            # below), so the old wording under-sold the actual remedy.
            self.assertNotIn("on a clean tree", decision["reason"])


class BlobHashRetestSatisfiesUnattestedTests(unittest.TestCase):
    """D5 (coordinator ruling, fix round 2): the NORMAL flow - an edit
    outside the tracked-tool surface (an IDE, `git apply`, `sed`), then
    `godmode retest --run` while the tree is still dirty with that very
    edit, then stage and commit - is satisfied. `run_check`'s per-path
    blob-hash capture (`blob_paths=`, threaded from `cmd_retest`'s new
    `pinned_sources`) is what makes this possible on a dirty tree, where
    round 1's clean-tree-only fallback never could."""

    def test_a_dirty_tree_retest_with_blob_hashes_clears_the_no_edit_record_file(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            # The "IDE edit" - no `edit-recorded` action written for it.
            (project / "scripts" / "widgetry.py").write_text(
                "def widgetry():\n    return 2\n", encoding="utf-8")
            _git(project, "add", "-A")

            plan = retest_plan(project, base="HEAD")
            self.assertEqual(plan["pinned"], {"tests/test_widgetry.py": ["scripts/widgetry.py"]})
            entry = next(c for c in plan["commands"] if c["runner"] == "unittest")
            self.assertEqual(entry["pinned_sources"], ["scripts/widgetry.py"])
            argv = [sys.executable, "-m", "unittest", *entry["modules"]]
            outcome = run_check(archive, "s1", project, "retest:unittest", argv, timeout=60,
                                modules=entry["modules"], blob_paths=entry["pinned_sources"])
            self.assertTrue(outcome["passed"], outcome)

            # The tree is still dirty (the staged edit is not committed) -
            # exactly the shape round 1's `dirty == 0` fallback could never
            # satisfy for the file actually being retested.
            dirty = subprocess.run(
                ["git", "-C", str(project), "status", "--porcelain=v1"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertTrue(dirty.strip(), "test setup: expected a dirty tree at retest time")

            self.assertEqual(unattested_staged_files(project, archive), [])
            self.assertEqual(stale_staged_files(project, archive), [])
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)


if __name__ == "__main__":
    unittest.main()

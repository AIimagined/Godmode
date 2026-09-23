"""Push preflight: disposable worktree, two-bucket triage, honest skips.

The stage runs BEFORE the password prompt and feeds it, never bypasses
it: a banned-term scan over the tracked files (the private list lives
outside the repo; absent means the check reports itself skipped, the
same contract the privacy test already has) and an optional suite
command. Findings come back in two buckets - mechanical (a scrub can
fix them; named with the remedy) and judgment (a person decides). The
worktree is disposable on every exit path, and a dirty tree is refused
before anything runs: preflight validates a state, and a dirty tree is
not a state anyone can push.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_preflight import push_preflight  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


_FAILING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        self.fail('red')\n"
_PASSING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        pass\n"


def _sharded_repo(tmp: Path, failing: str) -> Path:
    """A repo whose `tests/` holds four modules, one of them red."""
    repo = _repo(tmp)
    tests = repo / "tests"
    tests.mkdir()
    for name in ("a", "b", "c", "d"):
        body = _FAILING if name == failing else _PASSING
        (tests / f"test_{name}.py").write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "tests")
    return repo


class StallWatchdogTests(unittest.TestCase):
    """2026-09-23: a shard stalled at zero CPU and the only verdict an hour
    later was a bare timeout. The watchdog stops a stalled test within its
    limit and names where it stuck."""

    def _run(self, body: str, stall: float) -> tuple[subprocess.CompletedProcess, float]:
        import time
        from godmode_runtime.godmode_preflight import watchdog_command
        tmp = tempfile.mkdtemp()
        Path(tmp, "test_probe_mod.py").write_text(body, encoding="utf-8")
        started = time.monotonic()
        done = subprocess.run(watchdog_command(["test_probe_mod"], stall_seconds=stall),
                              cwd=tmp, capture_output=True, text=True, timeout=120)
        return done, time.monotonic() - started

    def test_a_stalled_test_is_stopped_and_named(self) -> None:
        from godmode_runtime.godmode_preflight import stall_summary
        done, took = self._run(
            "import time, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_hangs(self):\n"
            "        time.sleep(60)\n", stall=2)
        self.assertNotEqual(done.returncode, 0)
        self.assertLess(took, 30)
        summary = stall_summary(done.stderr)
        self.assertIsNotNone(summary, done.stderr[-500:])
        self.assertIn("test_probe_mod.py", summary)

    def test_healthy_tests_pass_and_report_no_stall(self) -> None:
        from godmode_runtime.godmode_preflight import stall_summary
        done, _ = self._run(
            "import time, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        time.sleep(1.5)\n"
            "    def test_b(self):\n"
            "        time.sleep(1.5)\n", stall=2)
        self.assertEqual(done.returncode, 0, done.stderr[-500:])
        self.assertIsNone(stall_summary(done.stderr))


class ShardIndexTests(unittest.TestCase):
    """One shard is a leg of a fan-out, and says so.

    A CI matrix runs the shards in parallel, so each process runs one index
    and must run exactly the modules that index owns - the same modules
    wherever it runs, or the shards do not add up to the suite. An index
    outside the range is a broken matrix, not something to clamp, and a
    single leg must never attest the green the staging gate reads.
    """

    def test_the_deal_is_deterministic_and_covers_every_module(self) -> None:
        from godmode_runtime.godmode_preflight import shard_modules

        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            deal = shard_modules(repo / "tests", 4)
            self.assertEqual(deal, shard_modules(repo / "tests", 4))
            flat = [name for shard in deal for name in shard]
            self.assertEqual(sorted(flat), sorted(set(flat)), "a module is in two shards")
            self.assertEqual(
                sorted(flat),
                ["tests.test_a", "tests.test_b", "tests.test_c", "tests.test_d"],
            )

    def test_an_out_of_range_shard_index_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            for index in (4, -1):
                with self.subTest(index=index):
                    with self.assertRaises(ArchiveError) as caught:
                        push_preflight(repo, suite=["python", "-m", "unittest", "discover"],
                                       suite_shards=4, shard_index=index)
                    message = str(caught.exception)
                    self.assertIn(str(index), message)
                    self.assertIn("0 to 3", message)

    def test_a_shard_runs_only_the_modules_that_index_owns(self) -> None:
        from godmode_runtime.godmode_preflight import shard_modules

        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            deal = shard_modules(repo / "tests", 4)
            red = next(i for i, names in enumerate(deal) if "tests.test_c" in names)
            green = next(i for i in range(4) if i != red)

            report = push_preflight(repo, suite=["python -m unittest discover"],
                                    suite_shards=4, shard_index=red)
            suite = [f for f in report["judgment"] if f["check"] == "suite"]
            self.assertEqual(len(suite), 1, report["judgment"])
            self.assertIn(f"shard {red}", suite[0]["detail"])
            self.assertEqual(report["shards_ran"], [red])

            report = push_preflight(repo, suite=["python -m unittest discover"],
                                    suite_shards=4, shard_index=green)
            self.assertEqual([f for f in report["judgment"] if f["check"] == "suite"], [])
            self.assertEqual(report["shards_ran"], [green])

    def test_one_green_shard_does_not_attest_the_suite_as_run(self) -> None:
        # `authorize stage` reads `status == "ran"` and nothing else. A
        # quarter of the suite must not be enough to stage a push.
        from unittest import mock

        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle

        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            state = Path(tmp) / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                archive = Chronicle(resolve_anchor(repo))
                archive.initialize()
                push_preflight(repo, suite=["python -m unittest discover"],
                               archive=archive, suite_shards=4, shard_index=0)
                attested = [r for r in archive.select(kind="attestation", limit=100)
                            if str(r.get("subject", "")) == "preflight"]
                self.assertTrue(attested, "no preflight attestation recorded")
                data = attested[-1].get("data") or {}
                self.assertEqual(data.get("status"), "incomplete")
                self.assertEqual(data.get("shards"), 4)
                self.assertEqual(data.get("shards_ran"), [0])


class PreflightTests(unittest.TestCase):
    def test_a_dirty_tree_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
            with self.assertRaises(ArchiveError):
                push_preflight(repo)

    def test_an_untracked_only_tree_is_not_refused_and_says_so(self) -> None:
        # The disposable worktree is built from HEAD, which an untracked file
        # is not part of, so refusing it protected nothing and blocked every
        # run behind stray scratch output. The report still names the gap.
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            (repo / "scratch.tmp.json").write_text("{}\n", encoding="utf-8")
            report = push_preflight(repo)
            self.assertTrue(any("untracked files are not in the snapshot" in s
                                for s in report["skipped"]), report["skipped"])

    def test_missing_term_list_reports_itself_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            report = push_preflight(repo)
            self.assertIn("banned-term scan", report["skipped"][0])
            self.assertEqual(report["mechanical"], [])
            self.assertEqual(report["judgment"], [])

    def test_a_term_hit_is_a_mechanical_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            terms = Path(tmp) / "terms.txt"
            terms.write_text("secretproject\n", encoding="utf-8")
            (repo / "code.py").write_text("# secretproject lives here\n",
                                          encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "leak")
            os.environ["GODMODE_COVERAGE_TERMS"] = str(terms)
            try:
                report = push_preflight(repo)
            finally:
                del os.environ["GODMODE_COVERAGE_TERMS"]
            tree_hits = [f for f in report["mechanical"]
                         if f["check"] == "banned-term"]
            self.assertEqual(len(tree_hits), 1)
            self.assertIn("code.py", tree_hits[0]["detail"])
            # The same term committed to history now also draws the
            # history-scope finding - both surfaces, both named.
            self.assertTrue(any(f["check"] == "history-terms"
                                for f in report["mechanical"]))
            # The term itself never appears in the finding - same contract
            # as the privacy test: red output must not be the second leak.
            self.assertNotIn("secretproject", str(report))

    def test_a_failing_suite_is_a_judgment_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            report = push_preflight(
                repo, suite=[sys.executable, "-c", "raise SystemExit(3)"])
            self.assertEqual(len(report["judgment"]), 1)
            self.assertIn("exit 3", report["judgment"][0]["detail"])

    def test_a_timed_out_suite_is_a_judgment_finding_not_a_traceback(self) -> None:
        # Round 7 of the 0.3.18 gate: the suite outran the clock and the
        # gate died as a bare TimeoutExpired, taking the hour of output
        # with it. The kill is a verdict a person reads, with the tail.
        from unittest import mock

        from godmode_runtime import godmode_preflight

        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            with mock.patch.object(godmode_preflight, "SUITE_TIMEOUT_SECONDS", 1):
                report = push_preflight(
                    repo, suite=[sys.executable, "-u", "-c",
                                 "import sys, time; sys.stderr.write('test_slow_one ... ');"
                                 "sys.stderr.flush(); time.sleep(20)"])
            suite = [f for f in report["judgment"] if f["check"] == "suite"]
            self.assertEqual(len(suite), 1)
            self.assertIn("killed after 1s", suite[0]["detail"])
            self.assertIn("test_slow_one", suite[0]["detail"])

    def test_the_worktree_is_gone_on_every_exit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            push_preflight(repo,
                           suite=[sys.executable, "-c", "raise SystemExit(1)"])
            listing = subprocess.run(
                ["git", "worktree", "list"], cwd=repo,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(len(listing.strip().splitlines()), 1)

    def test_cleanup_is_confirmed_not_assumed(self) -> None:
        # The effect of a control action is confirmed, never assumed: the
        # report states whether the disposable worktree is actually gone.
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            report = push_preflight(repo)
            self.assertEqual(report["cleanup"], "confirmed")

    def test_zero_assumptions_on_record_draws_the_probe(self) -> None:
        # The reasoning probe at the one genuinely high-stakes moment:
        # a push resting on no recorded assumption gets asked what it
        # rests on. One recorded assumption silences it.
        from unittest import mock
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            state = Path(tmp) / "state"
            with mock.patch.dict(os.environ,
                                 {"GODMODE_STATE_HOME": str(state)},
                                 clear=False):
                archive = Chronicle(resolve_anchor(repo))
                archive.initialize()
                report = push_preflight(repo, archive=archive)
                probes = [f for f in report["judgment"]
                          if f["check"] == "assumptions"]
                self.assertEqual(len(probes), 1)
                self.assertIn("rest", probes[0]["detail"])
                archive.append("assumption", "the bed assumes nothing moves",
                               {"detail": "test fixture"})
                report = push_preflight(repo, archive=archive)
                probes = [f for f in report["judgment"]
                          if f["check"] == "assumptions"]
                self.assertEqual(probes, [])

    def test_history_terms_scan_catches_a_scrubbed_leak(self) -> None:
        # A term deleted from the tree still lives in the deletion diff -
        # the exact class the 2026-09-02 field miss proved. The preflight
        # must read history, not the tree.
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            (repo / "notes.md").write_text("secretproject was here\n",
                                           encoding="utf-8")
            _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "add notes")
            (repo / "notes.md").write_text("clean now\n", encoding="utf-8")
            _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "scrub notes")
            terms = Path(tmp) / "terms.txt"
            terms.write_text("secretproject\n", encoding="utf-8")
            os.environ["GODMODE_COVERAGE_TERMS"] = str(terms)
            try:
                report = push_preflight(repo)
            finally:
                del os.environ["GODMODE_COVERAGE_TERMS"]
            history_findings = [f for f in report["mechanical"]
                                if f["check"] == "history-terms"]
            self.assertEqual(len(history_findings), 1)
            self.assertNotIn("secretproject", str(report))



if __name__ == "__main__":
    unittest.main()


class OpenAsksGateTests(unittest.TestCase):
    """A cut over open operator asks is the goal-misread class as
    machinery - every open stated request is a preflight finding."""

    def _project(self):
        import sys as _sys, tempfile
        from pathlib import Path as _P
        from contextlib import contextmanager
        from unittest import mock
        import os as _os
        root_dir = _P(__file__).resolve().parents[1]
        for entry in (str(root_dir / "scripts"),):
            if entry not in _sys.path:
                _sys.path.insert(0, entry)
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        import subprocess as _sp

        @contextmanager
        def ctx():
            with tempfile.TemporaryDirectory(prefix="gm-asks-") as tmp:
                base = _P(tmp)
                proj = base / "p"
                proj.mkdir()
                _sp.run(["git", "init", "-q"], cwd=proj, capture_output=True)
                (proj / "a.txt").write_text("x", encoding="utf-8")
                _sp.run(["git", "add", "-A"], cwd=proj, capture_output=True)
                _sp.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                         "commit", "-qm", "init"], cwd=proj,
                        capture_output=True)
                state = base / "state"
                with mock.patch.dict(_os.environ,
                                     {"GODMODE_STATE_HOME": str(state)},
                                     clear=False):
                    archive = Chronicle(resolve_anchor(proj))
                    archive.initialize()
                    yield proj, archive
        return ctx()

    def test_open_ask_is_a_finding(self) -> None:
        from godmode_runtime.godmode_preflight import push_preflight
        from godmode_runtime.godmode_requests import record_request
        with self._project() as (proj, archive):
            record_request(archive, "sweep the upstream repos before the cut")
            report = push_preflight(proj, archive=archive)
            checks = [j.get("check") for j in report["judgment"]]
            self.assertIn("open-operator-asks", checks)

    def test_no_open_asks_no_finding(self) -> None:
        from godmode_runtime.godmode_preflight import push_preflight
        with self._project() as (proj, archive):
            report = push_preflight(proj, archive=archive)
            checks = [j.get("check") for j in report["judgment"]]
            self.assertNotIn("open-operator-asks", checks)

    def test_a_designated_suite_runs_without_being_asked(self) -> None:
        # THE RATCHET RULE on this gate's own miss: three CI-red releases
        # on stale pins while "run the suite first" lived as a lesson and
        # a per-call flag. Recorded once, the suite runs on every
        # preflight - a failing designation is a judgment finding.
        import sys as _sys
        from godmode_runtime.godmode_preflight import push_preflight
        with self._project() as (proj, archive):
            archive.append("criterion", "preflight-suite",
                           {"command": f'"{_sys.executable}" -c "import sys; sys.exit(3)"'})
            report = push_preflight(proj, archive=archive)
            checks = [j.get("check") for j in report["judgment"]]
            self.assertIn("suite", checks)
            self.assertNotIn("suite: no command designated",
                             " ".join(report.get("skipped", [])))

    def test_a_subject_closure_clears_the_finding(self) -> None:
        # Field-caught at the 0.3.17 gate (2026-09-04): the closure command
        # this very finding prescribes writes the digest of the SUBJECT,
        # not of the prompt text, and the gate's latest-per-digest rebuild
        # never saw it - close, re-run, still blocked.
        from godmode_runtime.godmode_preflight import push_preflight
        from godmode_runtime.godmode_requests import record_request
        from godmode_runtime.godmode_requests import digest as request_digest
        with self._project() as (proj, archive):
            record = record_request(
                archive, "sweep the upstream repos before the cut")
            subject = record["subject"]
            archive.append("request", subject,
                           {"value": "served", "status": "closed",
                            "digest": request_digest(subject),
                            "source": "stated"})
            report = push_preflight(proj, archive=archive)
            checks = [j.get("check") for j in report["judgment"]]
            self.assertNotIn("open-operator-asks", checks)


class AdvisorySeverityGateTests(OpenAsksGateTests):
    """An advisory-severity judgment finding rides a clean verdict; a
    blocking or severity-less one turns it - the skip at the bottom of
    `push_preflight` has never had a direct test of its own."""

    def test_an_advisory_finding_leaves_the_verdict_clean_but_still_appears(self) -> None:
        import sys as _sys
        from unittest import mock

        from godmode_runtime.godmode_preflight import push_preflight

        finding = {"check": "host-reach", "severity": "advisory",
                  "detail": "advisory: still reachable by replication test"}
        with self._project() as (proj, archive):
            archive.append("assumption", "the bed assumes nothing moves",
                           {"detail": "test fixture"})
            archive.append("criterion", "preflight-suite",
                           {"command": f'"{_sys.executable}" -c "pass"'})
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=finding):
                report = push_preflight(proj, archive=archive)
            self.assertEqual(report["verdict"], "clean")
            self.assertIn(finding, report["judgment"])

    def test_a_blocking_or_severity_less_finding_turns_the_verdict(self) -> None:
        from unittest import mock

        from godmode_runtime.godmode_preflight import push_preflight

        blocking = {"check": "host-reach", "severity": "blocking",
                   "detail": "blocking: no replication test, no reference"}
        with self._project() as (proj, archive):
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=blocking):
                report = push_preflight(proj, archive=archive)
            self.assertEqual(report["verdict"], "findings")
            self.assertIn(blocking, report["judgment"])

        severity_less = {"check": "host-reach", "detail": "no severity declared at all"}
        with self._project() as (proj, archive):
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=severity_less):
                report = push_preflight(proj, archive=archive)
            self.assertEqual(report["verdict"], "findings")
            self.assertIn(severity_less, report["judgment"])

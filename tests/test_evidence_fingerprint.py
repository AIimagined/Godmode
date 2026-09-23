"""A claim is stale when the tree it was made on changed; a dangling seq cite is refused."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_attest import record_claim, stale_claims  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_fingerprint import tree_fingerprint  # noqa: E402
from godmode_runtime.godmode_verdict import record_verdict  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    # Q5 (review): 30s, not the implicit no-timeout default - a hung git
    # must not hang the whole suite.
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=30)


class FingerprintTests(unittest.TestCase):
    def _repo(self, project: Path) -> None:
        # Q5: `-b main` so the branch name never depends on the
        # developer's `init.defaultBranch`; `commit.gpgsign=false` and
        # `core.autocrlf=false` so a signing-enabled or autocrlf global
        # config cannot fail this test for reasons unrelated to the code.
        _git(project, "init", "-q", "-b", "main")
        (project / "a.py").write_text("x = 1\n", encoding="utf-8")
        _git(project, "add", "-A")
        _git(project, "-c", "user.email=t@t", "-c", "user.name=t",
             "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
             "commit", "-q", "-m", "root")

    def test_edit_after_claim_is_stale(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            before = tree_fingerprint(project)["digest"]
            record_claim(archive, project, "S1", "a.py sets x", "observed", cites=["file:a.py"])
            (project / "a.py").write_text("x = 2\n", encoding="utf-8")
            self.assertNotEqual(before, tree_fingerprint(project)["digest"])
            reasons = {s["reason"] for s in stale_claims(archive, project)}
            self.assertTrue({"changed", "tree-changed"} & reasons, reasons)

    def test_sibling_file_is_tree_changed_not_changed(self) -> None:
        # Q4: the headline behaviour this task adds - the tree moved even
        # though the CITED file's own hash did not - had zero binding
        # coverage; `test_edit_after_claim_is_stale` passes on the
        # pre-existing per-citation `changed` path alone.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            record_claim(archive, project, "S1", "a.py sets x", "observed", cites=["file:a.py"])
            (project / "sibling.py").write_text("y = 1\n", encoding="utf-8")
            reasons = {s["reason"] for s in stale_claims(archive, project)}
            self.assertIn("tree-changed", reasons)
            self.assertNotIn("changed", reasons)

    def test_cmd_only_claim_is_never_tree_flagged(self) -> None:
        # Q4: "pure `cmd:` claims re-run instead - leave them alone" (the
        # brief's own words) had no test naming it.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            record = record_claim(archive, project, "S1", "the suite passed",
                                   "observed", cites=["cmd:true"])
            (project / "sibling.py").write_text("y = 1\n", encoding="utf-8")
            sequences = {s["sequence"] for s in stale_claims(archive, project)}
            self.assertNotIn(record["sequence"], sequences)

    def test_tree_fingerprint_outside_git_is_no_git(self) -> None:
        # Q4: the `no-git` branch had no test either.
        with isolated_project() as (project, _s, _a, _archive):
            self.assertEqual(tree_fingerprint(project)["digest"], "no-git")

    def test_stale_claims_computes_fingerprint_once(self) -> None:
        # Q1 (blocking): `tree_fingerprint` must be computed at most once
        # per `stale_claims` run, never once per claim - measured, not
        # inferred, by counting every git-reading call `tree_fingerprint`
        # makes (`run_git`, folded per N5 into the one implementation both
        # the `head`/git-dir probe and the `status`/`diff`/`diff --cached`
        # reads go through) over 50 stale claims. All 50 cite the same
        # unchanged file, so none trips the per-citation `changed` path -
        # only the tree-wide check can fire here, and it must still cost
        # one fingerprint, not fifty.
        from godmode_runtime import godmode_fingerprint as _fp

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            for i in range(50):
                record_claim(archive, project, "S1", f"a.py sets x ({i})",
                             "observed", cites=["file:a.py"])
            (project / "sibling.py").write_text("y = 1\n", encoding="utf-8")
            calls = {"n": 0}
            real_run_git = _fp.run_git

            def _counted_run_git(*args, **kwargs):
                calls["n"] += 1
                return real_run_git(*args, **kwargs)

            with mock.patch.object(_fp, "run_git", side_effect=_counted_run_git):
                stale_claims(archive, project)
            self.assertLessEqual(calls["n"], 4, calls["n"])

    def test_seq_cite_to_an_old_record_resolves_past_the_select_window(self) -> None:
        # N1 (blocking): the in-range existence scan must not silently
        # inherit `Chronicle.select`'s 500-record clamp - a cite naming
        # sequence 5 on a 540-record archive still names a record that
        # exists, and citing it must not be refused as if it did not.
        #
        # R2 (review): `grade="verified"` here, not `"observed"` - only the
        # verified ladder ever consults `unresolved`, so a claim graded
        # `"observed"` would pass this test even if the SOFT resolver
        # (`_citation_resolves`'s own `seq:` branch) still silently
        # inherited the 500-record clamp and reported `seq:5` unresolved;
        # asserting the returned GRADE is what actually pins that the soft
        # path was fixed too, not just the hard `require_seq_cite` refusal.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for i in range(540):
                archive.append("claim", f"filler {i}", {"text": f"filler {i}"})
            record = record_claim(archive, project, "S1", "rests on an old record",
                                  "verified", cites=["seq:5"])
            self.assertEqual(record["data"]["grade"], "verified", record["data"])
            self.assertFalse(record["data"]["downgraded"], record["data"])

    def test_untrusted_digest_scan_runs_once_for_many_tool_citations(self) -> None:
        # N7 (blocking): `bb21d17`'s C3-residue fix (the `untrusted_digests`
        # parameter threaded through `_citation_resolves` and its `tool:`
        # fallback) was silently reverted by a staging race in fix round 2.
        # Restored; this pins it with a count, not just behaviour - an
        # 8-`tool:`-citation claim must run exactly one
        # `_untrusted_digests` scan (the one `record_claim` takes up
        # front), not one per citation on top of that.
        from godmode_runtime import godmode_attest as _ga

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("action", "untrusted-content-seen", {"digest": "deadbeef"})
            calls = {"n": 0}
            real_scan = _ga._untrusted_digests

            def _counted_scan(*args, **kwargs):
                calls["n"] += 1
                return real_scan(*args, **kwargs)

            with mock.patch.object(_ga, "_untrusted_digests", side_effect=_counted_scan):
                record_claim(archive, project, "S1", "cites many tool results",
                             "observed", cites=[f"tool:d{i}" for i in range(8)])
            self.assertEqual(calls["n"], 1, calls["n"])

    def test_dangling_seq_cite_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            with self.assertRaises(ArchiveError):
                record_claim(archive, project, "S1", "rests on a record", "observed", cites=["seq:999999"])

    def test_malformed_seq_cite_refused_not_crashed(self) -> None:
        # S1 (blocking): `rest.isdigit()` admits a superscript ("seq:²")
        # and `int()` on it raised an uncaught ValueError, not the refusal
        # a referential-integrity violation requires. Plain non-digit text
        # must refuse the same way, not silently pass through.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            with self.assertRaises(ArchiveError):
                record_claim(archive, project, "S1", "superscript sequence",
                             "observed", cites=["seq:²"])
            with self.assertRaises(ArchiveError):
                record_claim(archive, project, "S1", "non-numeric sequence",
                             "observed", cites=["seq:abc"])

    def test_verdict_witness_change_is_stale(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize(); self._repo(project)
            witness = project / "w.txt"; witness.write_text("v1\n", encoding="utf-8")
            record_verdict(archive, project, "w says v1", "v1", "file:w.txt",
                           f"{sys.executable} -c \"import sys; sys.exit(0)\"", checked=["w.txt"])
            witness.write_text("v2\n", encoding="utf-8")
            reasons = {s["reason"] for s in stale_claims(archive, project)}
            self.assertIn("witness-changed", reasons)


if __name__ == "__main__":
    unittest.main()

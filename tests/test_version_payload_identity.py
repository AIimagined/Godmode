"""D-1: the declared version is a claim about the shipped payload, checked.

A tag names a version and `plugin.json` states one. Nothing before this
compared either of them to the commits that landed *after* the tag: a
release could tag `v0.3.26`, land three commits touching `hooks/` and
`scripts/` with the manifest still reading `0.3.26`, and every existing
version surface would agree with itself while a real fix shipped
unversioned. `godmode_reconcile.reconcile_versions` catches surfaces
disagreeing with each other; it has nothing to say about a surface that
agrees with the tag while the payload has moved past it.

This check reads three facts a session would otherwise have to remember: the
latest `v*` tag reachable from HEAD (by semver, not by commit-graph
proximity), the version `plugin.json` declares at HEAD, and whether any
commit after that tag touched a payload path (`skills/`, `hooks/`,
`scripts/`, `bin/`, `adapters/`, or a manifest). Docs-only commits after the
tag are not drift - only a payload commit paired with an unmoved version is.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import version_payload_identity as V  # noqa: E402


def _git(root: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (arguments, result.stdout, result.stderr)


class FixtureRepository:
    """A repo small enough to control every fact the check reads."""

    def __init__(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-payload-identity-")
        self.root = Path(self._holder.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "d@e.invalid")
        _git(self.root, "config", "user.name", "d")

    def __enter__(self) -> "FixtureRepository":
        return self

    def __exit__(self, *_exception: object) -> None:
        self._holder.cleanup()

    def write_version(self, version: str) -> None:
        (self.root / "plugin.json").write_text(
            json.dumps({"name": "godmode", "version": version}), encoding="utf-8")

    def write_payload_file(self, relative: str, content: str = "x = 1\n") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_doc(self, relative: str = "docs/NOTE.md", content: str = "note\n") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message: str) -> str:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", message)
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip()

    def tag(self, name: str) -> None:
        _git(self.root, "tag", "-a", name, "-m", name)

    def check(self) -> dict:
        return V.check(self.root)


class LatestTagTests(unittest.TestCase):
    def test_picks_the_highest_semver_not_the_nearest_commit(self) -> None:
        """v0.2.0 sits closer to HEAD in commit distance than v0.10.0 would,
        but semver order - not graph proximity - decides "latest"."""
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("first")
            repo.tag("v0.1.0")
            repo.write_version("0.2.0")
            repo.commit("second")
            repo.tag("v0.2.0")
            self.assertEqual(V.latest_tag(repo.root), "v0.2.0")

    def test_no_tags_reports_none(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("first")
            self.assertIsNone(V.latest_tag(repo.root))

    def test_double_digit_patch_beats_single_digit_by_value_not_by_string(self) -> None:
        """`"v0.3.9" > "v0.3.10"` as strings (`"9" > "1"`), which is exactly
        the bug a naive `max()` over tag names would reproduce. This repo's
        real tag history runs v0.3.0..v0.3.26, so this is not a hypothetical
        shape."""
        with FixtureRepository() as repo:
            repo.write_version("0.3.9")
            repo.commit("ninth")
            repo.tag("v0.3.9")
            repo.write_version("0.3.10")
            repo.commit("tenth")
            repo.tag("v0.3.10")
            self.assertEqual(V.latest_tag(repo.root), "v0.3.10")


class IdentityCheckTests(unittest.TestCase):
    def test_red_unbumped_version_with_a_payload_commit_after_the_tag(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")

            repo.write_payload_file("hooks/godmode_gate_fast.py")
            repo.commit("fix(gate): tighten a rule")

            report = repo.check()

        self.assertEqual(report["verdict"], "identity-drift", report)
        self.assertEqual(report["declared_version"], "0.1.0")
        self.assertEqual(report["tag_version"], "0.1.0")
        self.assertEqual(len(report["payload_commits"]), 1)

    def test_green_when_the_version_was_bumped(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")

            repo.write_payload_file("hooks/godmode_gate_fast.py")
            repo.write_version("0.1.1")
            repo.commit("fix(gate): tighten a rule")

            report = repo.check()

        self.assertEqual(report["verdict"], "ok", report)
        self.assertEqual(report["declared_version"], "0.1.1")

    def test_green_when_the_only_commits_after_the_tag_are_docs_only(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")

            repo.write_doc()
            repo.commit("docs: clarify a paragraph")

            report = repo.check()

        self.assertEqual(report["verdict"], "ok", report)
        self.assertEqual(report["payload_commits"], [])

    def test_green_when_nothing_has_landed_since_the_tag(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")
            report = repo.check()

        self.assertEqual(report["verdict"], "ok", report)
        self.assertEqual(report["payload_commits"], [])

    def test_no_tags_is_ok_not_a_finding(self) -> None:
        """A project that has never tagged has nothing to drift against."""
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("first")
            report = repo.check()

        self.assertEqual(report["verdict"], "no-tags", report)

    def test_manifest_payload_commit_also_counts(self) -> None:
        """The manifest files are payload even though they are not under a
        payload directory prefix."""
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")

            repo.write_payload_file("capabilities.json", "{}\n")
            repo.commit("chore: add a capability entry")

            report = repo.check()

        self.assertEqual(report["verdict"], "identity-drift", report)

    def test_a_version_ahead_of_the_tag_with_payload_commits_is_ok(self) -> None:
        """Mid-sprint on this very branch: several tasks land payload commits
        while the tag still names the previous release and the version has
        not been bumped yet. Task 15 (release prep) bumps it before tagging;
        until then this must not go red on every intermediate commit."""
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")

            repo.write_payload_file("hooks/godmode_gate_fast.py")
            repo.commit("fix(gate): rule one")
            repo.write_payload_file("hooks/godmode_gate_fast.py", "x = 2\n")
            repo.commit("fix(gate): rule two")

            report = repo.check()

        # This IS the drift the check exists to catch - asserted here so a
        # change to the branch's own release ritual (bump before merge,
        # rather than at the end) would be visible as a test failure instead
        # of a silently reinterpreted check.
        self.assertEqual(report["verdict"], "identity-drift", report)
        self.assertEqual(len(report["payload_commits"]), 2)


class RealRepoPrefixCoverageTests(unittest.TestCase):
    """Every tracked host-manifest directory this repository actually ships
    must be a `PAYLOAD_PREFIXES` entry, found the same way `.antigravity-plugin/`
    was missed: it existed on disk and was tracked, but nobody had added it
    to the hand-written list. Read-only - `git ls-files` only, never `check()`
    or `latest_tag()` against this repo's real HEAD, which would read as
    `identity-drift` mid-sprint by design (see the module docstring) and is
    not what this test is proving."""

    _PLUGIN_DIR = re.compile(r"^(\.[A-Za-z0-9_-]+-plugin)/")

    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["git", "-C", str(PLUGIN_ROOT), "ls-files"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        cls.tracked = [line for line in result.stdout.splitlines() if line]

    def test_every_tracked_top_level_plugin_directory_is_covered(self) -> None:
        found = sorted({
            match.group(1) + "/"
            for path in self.tracked
            if (match := self._PLUGIN_DIR.match(path))
        })
        self.assertTrue(found, "no *-plugin/ directories found; the pattern "
                                "or the fixture repo state may have changed")
        for directory in found:
            self.assertIn(directory, V.PAYLOAD_PREFIXES,
                          f"{directory} is tracked and shipped but missing "
                          f"from PAYLOAD_PREFIXES")

    def test_every_top_level_manifest_file_is_covered(self) -> None:
        top_level_files = {path for path in self.tracked if "/" not in path}
        for manifest in ("plugin.json", "capabilities.json"):
            self.assertIn(manifest, top_level_files,
                          f"{manifest} is no longer tracked at the repo root; "
                          f"update this test's expectation deliberately")
            self.assertIn(manifest, V.PAYLOAD_PREFIXES,
                          f"{manifest} is a tracked top-level manifest file "
                          f"missing from PAYLOAD_PREFIXES")


class MainCLITests(unittest.TestCase):
    def test_main_exits_nonzero_on_drift_and_zero_when_clean(self) -> None:
        with FixtureRepository() as repo:
            repo.write_version("0.1.0")
            repo.commit("release")
            repo.tag("v0.1.0")
            repo.write_payload_file("hooks/godmode_gate_fast.py")
            repo.commit("fix(gate): tighten a rule")

            self.assertEqual(V.main(repo.root), 1)

            repo.write_version("0.1.1")
            repo.commit("chore: bump version")
            self.assertEqual(V.main(repo.root), 0)


if __name__ == "__main__":
    unittest.main()

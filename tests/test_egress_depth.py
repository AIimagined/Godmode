"""S8 depth: path containment, destination disclosure, user privacy rules, redaction.

These tests pin the egress boundary's hard edges: a path that resolves outside the
project root is refused before it is ever read, user-declared never-leave rules
block a disclosure exactly like a discovered secret, and the "redact further and
send less" choice produces a manifest a user can actually approve. Fixtures build
their own temp projects so no test depends on the repository's own layout.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_egress import (  # noqa: E402
    _contained,
    manifest,
    notice,
    scan_paths,
)

# Assembled at runtime so this test file never carries a contiguous secret-shaped
# literal that a boundary scan of the repository would flag.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


@contextmanager
def sample_project():
    """A project directory with a sibling file OUTSIDE it, to aim escapes at."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        (project / "src").mkdir(parents=True)
        (project / "src" / "ok.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8")
        outside = base / "outside.txt"
        outside.write_text("host secret material lives here\n", encoding="utf-8")
        yield project, outside


def write_privacy(project: Path, payload: dict) -> None:
    (project / ".godmode-privacy.json").write_text(
        json.dumps(payload), encoding="utf-8")


class PathContainmentTests(unittest.TestCase):
    """A path escaping the project root is refused, named, and never read."""

    def test_parent_escape_is_refused_in_manifest(self) -> None:
        with sample_project() as (project, _outside):
            scope = manifest(project, ["../outside.txt", "src/ok.py"])
            included = {item["path"] for item in scope["included"]}
            self.assertEqual(included, {"src/ok.py"}, scope)
            escape = next(item for item in scope["withheld"]
                          if item["path"] == "../outside.txt")
            self.assertIn("path-escape", escape["reason"])
            self.assertEqual(scope["path_escapes"],
                             [{"path": "../outside.txt", "kind": "path-escape"}])

    def test_parent_escape_is_refused_in_scan_paths(self) -> None:
        with sample_project() as (project, _outside):
            report = scan_paths(project, ["../outside.txt"])
            self.assertFalse(report["clean"], report)
            kinds = {finding["kind"] for finding in report["findings"]}
            self.assertIn("path-escape", kinds)
            # Refused means never read: no line, no excerpt, no content detail.
            escape = next(f for f in report["findings"] if f["kind"] == "path-escape")
            self.assertNotIn("secret", json.dumps(escape).lower())

    def test_absolute_path_is_refused(self) -> None:
        with sample_project() as (project, outside):
            scope = manifest(project, [str(outside)])
            self.assertEqual(scope["included"], [], scope)
            self.assertEqual(scope["path_escapes"][0]["kind"], "path-escape")
            report = scan_paths(project, [str(outside)])
            self.assertFalse(report["clean"], report)
            self.assertEqual(report["findings"][0]["kind"], "path-escape")

    def test_contained_helper_verdicts(self) -> None:
        with sample_project() as (project, outside):
            inside = _contained(project, "src/ok.py")
            self.assertIsNotNone(inside)
            self.assertEqual(inside, (project / "src" / "ok.py").resolve())
            self.assertIsNone(_contained(project, "../outside.txt"))
            self.assertIsNone(_contained(project, str(outside)))
            # Re-entering the root through .. is not an escape.
            self.assertIsNotNone(_contained(project, "src/../src/ok.py"))


class DestinationTests(unittest.TestCase):
    """S8.2: the disclosure names the receiving party, or says it cannot."""

    def test_named_destination_appears_in_disclosure(self) -> None:
        with sample_project() as (project, _outside):
            disclosure = notice("git push origin main", "publish", project,
                                ["src/ok.py"], destination="origin (git remote)")
            self.assertTrue(disclosure["destination_known"])
            self.assertEqual(disclosure["destination"], "origin (git remote)")

    def test_unknown_destination_is_said_not_omitted(self) -> None:
        with sample_project() as (project, _outside):
            disclosure = notice("curl example", "fetch", project, ["src/ok.py"])
            self.assertFalse(disclosure["destination_known"])
            self.assertIn("destination", disclosure)
            self.assertIn("unknown", disclosure["destination"].lower())


class NeverLeaveTests(unittest.TestCase):
    """S8.3: user-declared classes extend the built-in denials, never shrink them."""

    def test_never_leave_glob_blocks_matching_file(self) -> None:
        with sample_project() as (project, _outside):
            (project / "secret-plans").mkdir()
            (project / "secret-plans" / "roadmap.md").write_text(
                "Q3 acquisition targets.\n", encoding="utf-8")
            write_privacy(project, {"never_leave": ["secret-plans/*"]})
            scope = manifest(project, ["secret-plans/roadmap.md", "src/ok.py"])
            self.assertFalse(scope["clean"], scope)
            withheld = {i["path"]: i["reason"] for i in scope["withheld"]}
            self.assertIn("user-declared never-leave",
                          withheld["secret-plans/roadmap.md"])
            disclosure = notice("git push", "publish", project,
                                ["secret-plans/roadmap.md", "src/ok.py"])
            self.assertTrue(disclosure["blocked"], disclosure)
            reasons = " | ".join(i["reason"] for i in disclosure["excluded"])
            self.assertIn("user-declared never-leave", reasons)

    def test_user_sensitive_paths_extend_builtin_denials(self) -> None:
        with sample_project() as (project, _outside):
            (project / "notes.internal.md").write_text("internal\n", encoding="utf-8")
            (project / ".env").write_text("A=1\n", encoding="utf-8")
            write_privacy(project, {"sensitive_paths": ["*.internal.md"]})
            scope = manifest(project, ["notes.internal.md", ".env"])
            withheld = {i["path"]: i["reason"] for i in scope["withheld"]}
            self.assertIn("user-declared sensitive path", withheld["notes.internal.md"])
            # The built-in tuple still applies: extend, never shrink.
            self.assertIn("environment file", withheld[".env"])

    def test_missing_or_invalid_privacy_file_changes_nothing(self) -> None:
        with sample_project() as (project, _outside):
            baseline = manifest(project, ["src/ok.py"])
            self.assertTrue(baseline["clean"], baseline)
            (project / ".godmode-privacy.json").write_text("{not json", encoding="utf-8")
            after = manifest(project, ["src/ok.py"])
            self.assertTrue(after["clean"], after)
            self.assertEqual([i["path"] for i in after["included"]], ["src/ok.py"])


class RedactionTests(unittest.TestCase):
    """S8.3: 'redact further and send less' is a real choice, not a caption."""

    def test_redact_unblocks_scope_whose_only_violation_is_never_leave(self) -> None:
        with sample_project() as (project, _outside):
            (project / "secret-plans").mkdir()
            (project / "secret-plans" / "roadmap.md").write_text(
                "Q3 targets.\n", encoding="utf-8")
            write_privacy(project, {"never_leave": ["secret-plans/*"]})
            blocked = notice("git push", "publish", project,
                             ["secret-plans/roadmap.md", "src/ok.py"])
            self.assertTrue(blocked["blocked"], blocked)
            redacted = notice("git push", "publish", project,
                              ["secret-plans/roadmap.md", "src/ok.py"], redact=True)
            self.assertFalse(redacted["blocked"], redacted)
            self.assertEqual(redacted["data_proposed"], ["src/ok.py"])
            item = next(i for i in redacted["excluded"]
                        if i["path"] == "secret-plans/roadmap.md")
            self.assertEqual(item, {"path": "secret-plans/roadmap.md",
                                    "included": False, "reason": "redacted"})

    def test_redacted_manifest_never_carries_secret_excerpts(self) -> None:
        with sample_project() as (project, _outside):
            (project / "leaky.py").write_text(
                f'ACCESS = "{AWS_KEY}"\n', encoding="utf-8")
            scope = manifest(project, ["leaky.py", "src/ok.py"], redact=True)
            self.assertTrue(scope["clean"], scope)
            self.assertEqual(scope["secrets_found_in"], [])
            item = next(i for i in scope["withheld"] if i["path"] == "leaky.py")
            self.assertEqual(item["reason"], "redacted")
            dump = json.dumps(scope)
            self.assertNotIn(AWS_KEY, dump)
            self.assertNotIn(AWS_KEY[:8], dump)  # not even a masked prefix

    def test_without_redact_secret_still_blocks(self) -> None:
        with sample_project() as (project, _outside):
            (project / "leaky.py").write_text(
                f'ACCESS = "{AWS_KEY}"\n', encoding="utf-8")
            disclosure = notice("git push", "publish", project, ["leaky.py"])
            self.assertTrue(disclosure["blocked"], disclosure)


if __name__ == "__main__":
    unittest.main()

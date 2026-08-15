"""U-E2: cross-project precedent exchange - file-carried, advisory-foreign.

No network, no daemon, no shared mutable state: the operator carries a file
from one project's archive to another's. `export_precedents()` turns one
domain's register entries into a self-verifying JSON string;
`import_precedents()` verifies that file's own whole-file content hash and
appends the entries into a SEPARATE `reg-foreign:` namespace, where they stay
strictly advisory - never local, never binding, never part of conflict
detection - until a human explicitly promotes one with `adopt_precedent()`.
"""

from __future__ import annotations

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

from godmode_runtime.godmode_errors import ArchiveError, GodmodeError  # noqa: E402
from godmode_runtime import godmode_register  # noqa: E402
from godmode_runtime.godmode_register import (  # noqa: E402
    adopt_precedent,
    export_precedents,
    import_precedents,
    register,
    set_state,
)
from godmode_runtime.godmode_precheck import precheck, render  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _establish(archive, subject: str, *, state: str = "established",
                evidence: list[str] | None = None) -> dict:
    """`reg:<domain>:<key>` -> a real register record, the way a human would write one."""
    prefix, domain, key = subject.split(":", 2)
    assert prefix == "reg"
    return set_state(archive, domain, key, state, evidence or [f"file:{key}.md"])


class Roundtrip(unittest.TestCase):
    def test_export_import_surfaces_labeled_foreign(self) -> None:
        with isolated_project() as (_p1, _s1, _a1, a1), isolated_project() as (_p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:css-not-js", state="rejected-precedent")
            blob = export_precedents(a1, domain="approach")
            import_precedents(a2, blob)
            folded = register(a2, domain="approach")
            self.assertNotIn("css-not-js", folded)  # local namespace untouched
            foreign = register(a2, domain="approach", foreign=True)
            self.assertEqual(foreign["css-not-js"]["state"], "rejected-precedent")
            self.assertTrue(foreign["css-not-js"]["foreign"])

    def test_export_file_shape_is_the_documented_contract(self) -> None:
        with isolated_project() as (_p1, _s1, _a1, a1):
            _establish(a1, "reg:approach:x", evidence=["file:notes.md", "witness:seq:1"])
            doc = json.loads(export_precedents(a1, domain="approach"))
        self.assertIn("origin", doc)
        self.assertEqual(len(doc["origin"]), 16)
        self.assertIn("content_hash", doc)
        self.assertEqual(doc["entries"], [{
            "key": "x", "state": "established",
            "statements": ["file:notes.md", "witness:seq:1"], "evidence_count": 2,
        }])

    def test_precheck_surfaces_a_foreign_precedent_labeled_and_advisory_only(self) -> None:
        with isolated_project() as (p1, _s1, _a1, a1), isolated_project() as (p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:vector-search-over-corpus", state="rejected-precedent")
            import_precedents(a2, export_precedents(a1, domain="approach"))
            report = precheck(p2, a2, "bring back vector search over corpus")
        self.assertTrue(report["foreign_precedents"], report)
        hit = report["foreign_precedents"][0]
        self.assertEqual(hit["key"], "vector-search-over-corpus")
        self.assertIn("foreign precedent (from", hit["message"])
        # Advisory everywhere: a foreign-only hit never flips the verdict, and
        # never joins the local rejected_precedents/already_rejected findings.
        self.assertEqual(report["verdict"], "no-prior-work-found")
        self.assertEqual(report["rejected_precedents"], [])
        self.assertIn("foreign precedent (from", render(report))

    def test_an_unrelated_task_does_not_surface_the_foreign_precedent(self) -> None:
        with isolated_project() as (p1, _s1, _a1, a1), isolated_project() as (p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:vector-search-over-corpus", state="rejected-precedent")
            import_precedents(a2, export_precedents(a1, domain="approach"))
            report = precheck(p2, a2, "invoice rounding for VAT")
        self.assertEqual(report["foreign_precedents"], [])


class TrustBoundary(unittest.TestCase):
    def test_tampered_byte_refused_archive_untouched(self) -> None:
        with isolated_project() as (_p1, _s1, _a1, a1), isolated_project() as (_p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:x")
            blob = export_precedents(a1, domain="approach")
            doc = json.loads(blob)
            doc["entries"][0]["state"] = "established"  # already true; the point is ANY byte moved
            doc["entries"][0]["key"] = "tampered"
            evil = json.dumps(doc)  # content_hash NOT recomputed - this is the tamper
            before = len(a2.read_events())
            with self.assertRaises(GodmodeError):
                import_precedents(a2, evil)
            self.assertEqual(len(a2.read_events()), before)

    def test_foreign_can_never_arrive_binding(self) -> None:
        """The plant: a hand-crafted export whose entry claims `binding: True`,
        with a VALID content hash recomputed over the tampered document using
        the module's own hasher (not a forged/stale hash) - the tamper here is
        entirely in what the entry claims, not in the file's integrity. Import
        must still succeed (the hash is genuinely valid), and the foreign fold
        must show `binding` forced to `False` regardless."""
        with isolated_project() as (_p1, _s1, _a1, a1), isolated_project() as (_p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:y")
            raw = export_precedents(a1, domain="approach")
            doc = json.loads(raw)
            doc["entries"][0]["binding"] = True
            unsigned = {k: v for k, v in doc.items() if k != "content_hash"}
            doc["content_hash"] = godmode_register._content_hash(unsigned)
            blob = json.dumps(doc)

            import_precedents(a2, blob)  # succeeds: the hash IS valid

            foreign = register(a2, domain="approach", foreign=True)
        self.assertIn("y", foreign)
        self.assertFalse(foreign["y"]["binding"])

    def test_a_malformed_document_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            with self.assertRaises(GodmodeError):
                import_precedents(archive, "not json at all")

    def test_a_missing_content_hash_is_refused(self) -> None:
        with isolated_project() as (_p1, _s1, _a1, a1), isolated_project() as (_p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:x")
            doc = json.loads(export_precedents(a1, domain="approach"))
            del doc["content_hash"]
            with self.assertRaises(ArchiveError):
                import_precedents(a2, json.dumps(doc))


class Adoption(unittest.TestCase):
    def test_adopt_promotes_with_lineage(self) -> None:
        with isolated_project() as (_p1, _s1, _a1, a1), isolated_project() as (_p2, _s2, _a2, a2):
            _establish(a1, "reg:approach:x")
            import_precedents(a2, export_precedents(a1, domain="approach"))
            promoted = adopt_precedent(a2, "approach", "x")
            local = register(a2, domain="approach")
        self.assertIn("x", local)  # now local
        self.assertEqual(local["x"]["state"], "established")
        self.assertTrue(
            any(e.startswith("file:precedent-export:") for e in promoted["data"]["evidence"]),
            promoted["data"]["evidence"],
        )

    def test_adopting_an_unimported_key_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            with self.assertRaises(ArchiveError):
                adopt_precedent(archive, "approach", "never-imported")


class ConsoleSmoke(unittest.TestCase):
    def test_export_import_adopt_round_trip_through_the_cli(self) -> None:
        """Two SEQUENTIAL `isolated_project()` scopes, not nested: `main()`
        re-resolves the project's anchor from the ambient `GODMODE_STATE_HOME`
        env var on every call, and two isolated_project() context managers
        active at once would leave that env var pointed at whichever one
        entered last for BOTH projects' `main()` calls. The exported blob is
        carried across as a plain string, exactly the way the operator would
        carry the file itself."""
        from godmode_runtime.godmode_console import main

        with isolated_project() as (p1, _s1, _a1, a1):
            a1.initialize()
            _establish(a1, "reg:approach:cli-key")
            out_file = Path(p1) / "export.json"
            exit_export = main([
                "--project", str(p1), "precedent", "export",
                "--domain", "approach", "--out", str(out_file),
            ])
            self.assertEqual(exit_export, 0)
            blob = out_file.read_text(encoding="utf-8")

        with isolated_project() as (p2, _s2, _a2, a2):
            a2.initialize()
            transfer_file = Path(p2) / "incoming.json"
            transfer_file.write_text(blob, encoding="utf-8")

            exit_import = main([
                "--project", str(p2), "precedent", "import", str(transfer_file),
            ])
            self.assertEqual(exit_import, 0)

            exit_adopt = main([
                "--project", str(p2), "precedent", "adopt",
                "--domain", "approach", "--key", "cli-key",
            ])
            self.assertEqual(exit_adopt, 0)
            self.assertIn("cli-key", register(a2, domain="approach"))


if __name__ == "__main__":
    unittest.main()

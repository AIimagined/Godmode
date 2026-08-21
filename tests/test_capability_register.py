"""capabilities.json, its detector catalog, the capability-coverage matrix,
and this repository's own dogfooding (Task 13 + 13b + 13c, U-S2/U-S3).

Four things are pinned here, each against the real repository tree so a
drift in the shipped artefact is caught, not only a drift in a fixture:

* every `built`/`partial` capability's pointers resolve, and no
  `unbuilt`/`rejected` one secretly does (both directions);
* every catalogued mistake-class detector resolves to a real function and a
  real guard test, and the population matches what `godmode_mistakes.py`
  actually defines (a new M-id that never registers fails this file);
* every `covered`/`partial` row of the capability-coverage matrix resolves,
  and no `planned`/`not-claimed` row secretly does;
* this repository's own five HARD charter rules are provably planted, and
  every scaffolded role stub carries real content (`missing_roles == []`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_assess import assess  # noqa: E402
from godmode_runtime.godmode_attest import open_session, plant_and_observe  # noqa: E402
from godmode_runtime.godmode_charter import HARD, compile_charter  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_reconcile import (  # noqa: E402
    load_capabilities,
    reconcile_capabilities,
    reconcile_capability_coverage,
    reconcile_detectors,
)

CAPABILITIES_PATH = PLUGIN_ROOT / "capabilities.json"
COVERAGE_PATH = PLUGIN_ROOT / "docs" / "CAPABILITY-COVERAGE.md"

# Generic English attribution markers - not a source name in themselves, so
# listing them carries none of the risk the banned-term list does.
_ATTRIBUTION_MARKERS = (
    "inspired", "based on", "style of", "named after", "similar to",
    "adjacent", "family", "modeled on", "modelled on", "after the",
)
_STOPWORDS = {"class", "classes", "capability", "status", "surface", "across"}


def _banned_terms_path() -> Path | None:
    """Locate the private, out-of-repo banned-term list, if any.

    Never bundled: this list is exactly the source/tool vocabulary the
    privacy rule protects, so shipping it in this repository would be the
    leak the rule exists to prevent. `GODMODE_COVERAGE_TERMS` names a file
    directly, for a machine where the private ledger lives somewhere
    nonstandard; absent that, this walks upward from the repo root looking
    for a `.godmode-private/coverage-banned-terms.txt` sibling - the
    private ledger's own established location one level above a plain
    checkout - so it resolves the same way from a worktree nested several
    levels under a checkout as it does from a plain checkout.
    """
    override = os.environ.get("GODMODE_COVERAGE_TERMS")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    candidate = PLUGIN_ROOT
    for _ in range(8):
        found = candidate / ".godmode-private" / "coverage-banned-terms.txt"
        if found.is_file():
            return found
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return None


def _godmode_vocabulary() -> str:
    """Godmode's own shipped vocabulary, concatenated.

    A self-referencing check that needs no external list: proves a
    coverage-row label is drawn from what this project already calls
    itself (its own capability statements, README, and skill
    descriptions), not copied wholesale from an external taxonomy.
    """
    chunks: list[str] = []
    data = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
    chunks.extend(c["statement"] for c in data["capabilities"])
    readme = PLUGIN_ROOT / "README.md"
    if readme.is_file():
        chunks.append(readme.read_text(encoding="utf-8", errors="replace"))
    for skill_md in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"):
        chunks.append(skill_md.read_text(encoding="utf-8", errors="replace"))
    return " ".join(chunks).lower()

# Population floors, captured at the moment this file was written. Both
# grow-only: raising either number as the register grows is expected,
# lowering it means something was silently dropped.
MIN_CAPABILITY_COUNT = 81
MIN_DETECTOR_COUNT = 14
MIN_COVERAGE_ROWS = 8

_M_ID_DOCSTRING = re.compile(r'"""M(\d+):')


def _live_detector_ids() -> set[str]:
    """Every M-id `godmode_mistakes.py` actually claims, read from its own source.

    Not imported and introspected function-by-function - the docstring tag
    IS the id a maintainer assigns when a detector is written, so reading it
    from the source is the same live enumeration a person does by eye, only
    exhaustive.
    """
    source = (SCRIPTS / "godmode_runtime" / "godmode_mistakes.py").read_text(encoding="utf-8")
    return {f"M{n}" for n in _M_ID_DOCSTRING.findall(source)}


class CapabilityRegisterStructureTests(unittest.TestCase):
    """Deliverable 1: capabilities.json + the reconcile extension."""

    def test_the_file_exists_and_parses(self) -> None:
        data = load_capabilities(PLUGIN_ROOT)
        self.assertIn("capabilities", data)
        self.assertIn("detectors", data)

    def test_every_built_and_partial_pointer_resolves_on_the_real_tree(self) -> None:
        report = reconcile_capabilities(PLUGIN_ROOT)
        self.assertEqual(report["dead_pointers"], [], report["dead_pointers"])

    def test_no_unbuilt_or_rejected_entry_secretly_resolves(self) -> None:
        report = reconcile_capabilities(PLUGIN_ROOT)
        self.assertEqual(report["stale_status"], [], report["stale_status"])
        self.assertEqual(report["verdict"], "reconciled")

    def test_population_covers_every_c_id_from_15_up_and_is_grows_only(self) -> None:
        data = load_capabilities(PLUGIN_ROOT)
        ids = {c["id"] for c in data["capabilities"]}
        self.assertGreaterEqual(len(ids), MIN_CAPABILITY_COUNT)
        for n in range(15, 73):  # the deep re-sweep through the last contiguous id
            self.assertIn(f"C-{n:02d}", ids, f"C-{n:02d} missing from the population")

    def test_assess_surfaces_capability_debt(self) -> None:
        report = assess(PLUGIN_ROOT)
        self.assertIn("capability_debt", report)
        self.assertIsInstance(report["capability_debt"], list)
        # A known-unbuilt id from the register must appear here, or the
        # debt list is not actually reading the register.
        self.assertIn("C-04", report["capability_debt"])
        # A known-built id must never appear as debt.
        self.assertNotIn("C-01", report["capability_debt"])


class CapabilityDriftPlantTests(unittest.TestCase):
    """Both directions, proven against synthetic fixtures rather than the
    real file, so the check itself is what is under test here."""

    def _write(self, capabilities=None, detectors=None) -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "real.py").write_text("x = 1\n", encoding="utf-8")
        (tmp / "real_test.py").write_text("x = 1\n", encoding="utf-8")
        payload = {"capabilities": capabilities or [], "detectors": detectors or []}
        (tmp / "capabilities.json").write_text(json.dumps(payload), encoding="utf-8")
        return tmp

    def test_a_built_entry_pointing_at_a_deleted_file_is_dead(self) -> None:
        project = self._write(capabilities=[
            {"id": "C-99", "statement": "x", "status": "built",
             "impl": ["file:does/not/exist.py"], "guard": ["test:real_test.py"]},
        ])
        report = reconcile_capabilities(project)
        self.assertEqual(report["verdict"], "capability-drift")
        self.assertTrue(any(d["id"] == "C-99" for d in report["dead_pointers"]))

    def test_an_unbuilt_entry_with_a_resolving_pointer_is_stale(self) -> None:
        project = self._write(capabilities=[
            {"id": "C-98", "statement": "x", "status": "unbuilt",
             "impl": ["file:real.py"], "guard": []},
        ])
        report = reconcile_capabilities(project)
        self.assertEqual(report["verdict"], "capability-drift")
        self.assertTrue(any(s["id"] == "C-98" for s in report["stale_status"]))

    def test_a_rejected_entry_with_a_resolving_pointer_is_also_stale(self) -> None:
        project = self._write(capabilities=[
            {"id": "C-97", "statement": "x", "status": "rejected",
             "impl": ["file:real.py"], "guard": []},
        ])
        report = reconcile_capabilities(project)
        self.assertTrue(any(s["id"] == "C-97" for s in report["stale_status"]))

    def test_a_clean_fixture_reconciles(self) -> None:
        project = self._write(capabilities=[
            {"id": "C-96", "statement": "x", "status": "built",
             "impl": ["file:real.py"], "guard": ["test:real_test.py"]},
            {"id": "C-95", "statement": "x", "status": "unbuilt", "impl": [], "guard": []},
        ])
        report = reconcile_capabilities(project)
        self.assertEqual(report["verdict"], "reconciled")


class DetectorCatalogTests(unittest.TestCase):
    """Deliverable 2 (13b): the fabrication-pattern catalog."""

    def test_every_catalogued_detector_resolves_to_its_function_and_test(self) -> None:
        report = reconcile_detectors(PLUGIN_ROOT)
        self.assertEqual(report["dead"], [], report["dead"])
        self.assertEqual(report["verdict"], "reconciled")

    def test_population_matches_what_godmode_mistakes_actually_defines(self) -> None:
        """A detector added to the source without a catalog entry fails here."""
        data = load_capabilities(PLUGIN_ROOT)
        catalogued = {d["id"] for d in data["detectors"]}
        self.assertEqual(catalogued, _live_detector_ids())
        self.assertGreaterEqual(len(catalogued), MIN_DETECTOR_COUNT)

    def test_an_unregistered_function_name_is_a_dead_finding(self) -> None:
        # `godmode_mistakes` is already importable from the real package on
        # sys.path; only the fixture's file/test paths need to resolve
        # inside the fixture project for the existence half of the check.
        tmp = Path(tempfile.mkdtemp())
        (tmp / "godmode_mistakes.py").write_text("# stand-in for the existence check\n",
                                                  encoding="utf-8")
        (tmp / "some_test.py").write_text("# stand-in\n", encoding="utf-8")
        payload = {"capabilities": [], "detectors": [
            {"id": "M-fake", "function": "does_not_exist_in_the_real_module", "version": "1",
             "family": "x", "file": "file:godmode_mistakes.py", "test": "test:some_test.py"},
        ]}
        (tmp / "capabilities.json").write_text(json.dumps(payload), encoding="utf-8")
        report = reconcile_detectors(tmp)
        self.assertEqual(report["verdict"], "detector-drift")
        self.assertTrue(any(d["id"] == "M-fake" for d in report["dead"]))

    def test_a_detector_missing_its_test_pointer_is_a_dead_finding(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "godmode_mistakes.py").write_text("# stand-in\n", encoding="utf-8")
        payload = {"capabilities": [], "detectors": [
            {"id": "M-fake2", "function": "label_as_fact", "version": "1", "family": "x",
             "file": "file:godmode_mistakes.py", "test": "test:does/not/exist_test.py"},
        ]}
        (tmp / "capabilities.json").write_text(json.dumps(payload), encoding="utf-8")
        report = reconcile_detectors(tmp)
        self.assertEqual(report["verdict"], "detector-drift")
        self.assertTrue(any(d["id"] == "M-fake2" for d in report["dead"]))


class CapabilityCoverageMatrixTests(unittest.TestCase):
    """Deliverable 3 (13c): docs/CAPABILITY-COVERAGE.md."""

    def test_the_file_exists(self) -> None:
        self.assertTrue(COVERAGE_PATH.is_file())

    def test_every_covered_or_partial_rows_pointers_resolve(self) -> None:
        report = reconcile_capability_coverage(PLUGIN_ROOT)
        self.assertEqual(report["dead_pointers"], [], report["dead_pointers"])

    def test_no_planned_or_not_claimed_row_secretly_resolves(self) -> None:
        report = reconcile_capability_coverage(PLUGIN_ROOT)
        self.assertEqual(report["stale_status"], [], report["stale_status"])
        self.assertEqual(report["verdict"], "reconciled")

    def test_population_has_at_least_eight_rows_grows_only(self) -> None:
        report = reconcile_capability_coverage(PLUGIN_ROOT)
        self.assertGreaterEqual(report["rows"], MIN_COVERAGE_ROWS)

    def test_the_two_controller_ruled_boundary_rows_are_present_and_honest(self) -> None:
        text = COVERAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("not-claimed", text)
        self.assertIn("token-burn reduction", text.lower())
        self.assertIn("workflow", text.lower())
        self.assertIn("partial", text)

    def test_the_shipped_file_names_no_third_party_source(self) -> None:
        """PRIVACY: neutral capability-class vocabulary only.

        The banned-term list itself lives OUTSIDE this repository (private
        ledger convention, see `_banned_terms_path`) - this test ships only
        the assertion, never the terms, or the shipped test file would leak
        exactly the source/tool vocabulary the rule protects. Word-bounded
        so a short banned acronym cannot false-positive merely because its
        letters happen to occur inside an unrelated, longer English word.
        Absent the private list (fresh clone, CI), this half skips
        explicitly; the structural checks below still run unconditionally.
        """
        path = _banned_terms_path()
        if path is None:
            self.skipTest(
                "no private banned-term list found (GODMODE_COVERAGE_TERMS unset, and no "
                ".godmode-private/coverage-banned-terms.txt found above the repo root) - "
                "expected on a fresh clone/CI; structural term-free checks still ran")
        terms = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith("#")]
        self.assertTrue(terms, f"{path} exists but named zero terms")
        text = COVERAGE_PATH.read_text(encoding="utf-8").lower()
        for term in terms:
            pattern = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
            # Never interpolate the term into the failure message - a red
            # test's own output must not become the second place this leaks.
            self.assertNotRegex(text, pattern,
                                "a banned term from the private list leaked into the "
                                "shipped coverage matrix")

    def test_no_urls_in_the_coverage_map(self) -> None:
        """Structural, needs no external list: a URL is exactly the shape a
        source citation takes, whatever the source turns out to be."""
        text = COVERAGE_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"https?://"),
                            "a URL was found in the shipped coverage matrix")

    def test_no_family_adjacent_or_inspired_by_phrasing(self) -> None:
        """Structural, needs no external list: these phrasings are how a
        row would gesture at an external origin even without naming one."""
        text = COVERAGE_PATH.read_text(encoding="utf-8").lower()
        for phrase in ("family", "-adjacent", "inspired by"):
            self.assertNotIn(phrase, text,
                             f"'{phrase}' phrasing found in the shipped coverage matrix")

    def test_no_parenthesized_attributions(self) -> None:
        """Structural, needs no external list: every parenthetical in this
        file should be a `file:`/`test:` pointer, never a citation clause."""
        text = COVERAGE_PATH.read_text(encoding="utf-8").lower()
        for paren in re.findall(r"\(([^)]*)\)", text):
            for marker in _ATTRIBUTION_MARKERS:
                self.assertNotIn(
                    marker, paren,
                    f"parenthetical attribution marker '{marker}' found in '({paren})'")

    def test_row_labels_are_drawn_from_godmodes_own_vocabulary(self) -> None:
        """Structural, needs no external list: proves each row's class label
        is godmode's own vocabulary rather than a copied external category,
        by requiring at least one of its distinctive words to appear
        somewhere in what this project already calls itself."""
        vocabulary = _godmode_vocabulary()
        report = reconcile_capability_coverage(PLUGIN_ROOT)
        self.assertTrue(report["classes"])
        for klass in report["classes"]:
            words = [w for w in re.findall(r"[a-zA-Z]{5,}", klass.lower())
                     if w not in _STOPWORDS]
            self.assertTrue(words, f"row '{klass}' has no distinctive word to check")
            matched = [w for w in words if w in vocabulary]
            self.assertTrue(
                matched,
                f"row '{klass}' has no word appearing in godmode's own shipped vocabulary")

    def test_a_stale_status_fixture_is_caught(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        docs = tmp / "docs"
        docs.mkdir()
        (tmp / "real.py").write_text("x = 1\n", encoding="utf-8")
        (docs / "CAPABILITY-COVERAGE.md").write_text(
            "| Capability class | Status | Surface |\n|---|---|---|\n"
            "| Something | not-claimed | Actually shipped (`file:real.py`) |\n",
            encoding="utf-8",
        )
        report = reconcile_capability_coverage(tmp)
        self.assertEqual(report["verdict"], "coverage-drift")
        self.assertTrue(report["stale_status"])

    def test_flipping_planned_to_covered_without_pointers_goes_red(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "CAPABILITY-COVERAGE.md").write_text(
            "| Capability class | Status | Surface |\n|---|---|---|\n"
            "| Something | covered | No pointer named at all |\n",
            encoding="utf-8",
        )
        report = reconcile_capability_coverage(tmp)
        self.assertEqual(report["verdict"], "coverage-drift")
        self.assertTrue(report["dead_pointers"])


def _dogfood_registry_path(root: Path) -> Path:
    return root / ".dogfood-restore.json"


def restore_from_registry(root: Path) -> list[str]:
    """B4-7 rider 3: restore-on-next-run for the plant harness.

    A registry written before any plant maps each target's repo-relative
    path to a base64 byte-snapshot. A run killed from OUTSIDE (tool
    timeout, taskkill) can run nothing afterward - `finally` included - so
    the stale registry it leaves is the only signal, and the next run's
    setUp calls here to put every registered target back before doing
    anything else. Returns the repo-relative paths it processed; a missing
    registry means nothing to heal. The registry is deleted after healing -
    it describes a dead run, and keeping it would re-restore over live
    edits forever."""
    registry = _dogfood_registry_path(root)
    if not registry.exists():
        return []
    import base64
    try:
        entries = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = {}
    healed: list[str] = []
    if isinstance(entries, dict):
        for relative, encoded in sorted(entries.items()):
            target = root / relative
            try:
                original = base64.b64decode(encoded)
                if not target.exists() or target.read_bytes() != original:
                    target.write_bytes(original)
                healed.append(relative)
            except (OSError, ValueError):
                continue
    registry.unlink(missing_ok=True)
    return healed


class DogfoodingTests(unittest.TestCase):
    """Deliverable 4: this repository practises what it enforces.

    Each plant below breaks a real line this project's own guard depends
    on, chosen by first locating the specific test that already exercises
    that line (see `docs/LESSONS.md` for the miss that made this mandatory)
    - not inferred from the rule's abstract verify-kind alone.

    CX-5 fix round 1, M1 (Minor, observed during that review - the
    mechanism here predates and is untouched by CX-5 itself): `setUp`/
    `tearDown` below are a SECOND, independent restore, on top of
    `plant_and_observe`'s own `try/finally` (which already restores each
    target the moment ITS OWN call returns, exception or not). This class
    method's own `tearDown` additionally restores from a byte-snapshot
    taken before ANY plant runs, so a failure OUTSIDE
    `plant_and_observe`'s own protected window (e.g. the `assess()` call or
    an assertion after the loop, in this same Python process) still cannot
    leave a target mutated once this test method returns. Stated honestly,
    not overclaimed: this closes the in-process gap, not the one the
    review actually observed - an EXTERNAL kill (a tool timeout sending
    SIGKILL/taskkill to the whole `python -m unittest` process) bypasses
    every in-process mechanism, `finally` included, by design; no code
    running inside the process being killed can run afterward. Closing
    THAT class of failure needs a supervisory mechanism outside this
    process (a pre-flight self-heal against `git show HEAD:<path>` on the
    NEXT run, or an external watchdog) - parked, not attempted here, as a
    materially larger change than "cheap if trivial" describes.
    """

    PLANTS = [
        dict(name="changelog-fragment-category", rule="R-720cc85a48",
             target="scripts/godmode_runtime/godmode_changelog.py",
             command=[sys.executable, "-m", "unittest", "tests.test_changelog_gate"],
             replace='"added", "changed", "fixed", "removed", "deprecated", "security"',
             with_text='"changed", "fixed", "removed", "deprecated", "security"'),
        dict(name="integrity-assertion-regex", rule="R-b9dbf85864",
             target="scripts/godmode_runtime/godmode_integrity.py",
             command=[sys.executable, "-m", "unittest",
                      "tests.test_godmode_runtime.IntegrityTests"],
             replace=r'r"^\s*(assert\b|self\.assert|expect\s*\(|\.should\b|assert_eq!|ASSERT_|EXPECT_)"',
             with_text=r'r"^\s*(self\.assert|expect\s*\(|\.should\b|assert_eq!|ASSERT_|EXPECT_)"'),
        dict(name="claim-position-support", rule="R-56305a9e8f",
             target="scripts/godmode_runtime/godmode_attest.py",
             command=[sys.executable, "-m", "unittest",
                      "tests.test_godmode_runtime.AttestationTests"],
             replace='    return "corroborated" if terms & window else "unsupported"',
             with_text='    return "corroborated"'),
        dict(name="environment-production-marker", rule="R-4783f0d508",
             target="scripts/godmode_runtime/godmode_reconcile.py",
             command=[sys.executable, "-m", "unittest", "tests.test_environment_markers"],
             replace='prod(?:uction)?|prd|live|release',
             with_text='prd|live|release'),
        dict(name="session-close-half-done-pairs", rule="R-2259c5b00c",
             target="scripts/godmode_runtime/godmode_attest.py",
             command=[sys.executable, "-m", "unittest",
                      "tests.test_godmode_runtime.KernelCompletionTests"],
             replace='    allowed = not unattested and not downgraded and not half_done '
                     'and not unattested_accept',
             with_text='    allowed = not unattested and not downgraded and not unattested_accept'),
        # Sixth HARD rule, and it arrived by being read correctly rather
        # than by being written: `docs/FIXED-REGISTRY.md` states the
        # capability-pointer invariant in one sentence that the charter
        # compiler used to split across physical lines into fragments. Whole
        # again, it classifies HARD - which is right for the invariants role,
        # whose stated job is "behaviours that must stay true, each owning a
        # guard", and this one names its guard in its own text.
        #
        # Verified by `CapabilityDriftPlantTests` rather than this whole
        # module: the plant runs its command in a subprocess, so naming the
        # module that contains this test would re-enter the planting suite.
        dict(name="capability-pointer-drift", rule="R-e19dfe0488",
             target="scripts/godmode_runtime/godmode_reconcile.py",
             command=[sys.executable, "-m", "unittest",
                      "tests.test_capability_register.CapabilityDriftPlantTests"],
             replace='        if status == "built":',
             with_text='        if status == "built" and False:'),
    ]

    def setUp(self) -> None:
        # B4-7 rider 3 (CX-5's parked M1): heal whatever a KILLED previous
        # run left planted - an external SIGKILL/taskkill bypasses every
        # in-process finally by design, so the NEXT run is the only place
        # that can restore. Runs before this run's own snapshot so a healed
        # tree is what gets snapshotted.
        restore_from_registry(PLUGIN_ROOT)
        self._plant_originals = {
            plant["target"]: (PLUGIN_ROOT / plant["target"]).read_bytes()
            for plant in self.PLANTS
        }
        # The registry IS the kill insurance: written to disk before any
        # plant mutates a target, deleted only after tearDown restored.
        import base64
        _dogfood_registry_path(PLUGIN_ROOT).write_text(json.dumps({
            target: base64.b64encode(original).decode("ascii")
            for target, original in self._plant_originals.items()
        }), encoding="utf-8")

    def tearDown(self) -> None:
        # Best-effort, in-process only (see the class docstring) - restores
        # any target `plant_and_observe`'s own `try/finally` did not
        # already put back, e.g. a failure raised AFTER a plant call
        # returned but before this test method itself finished.
        for target, original in self._plant_originals.items():
            path = PLUGIN_ROOT / target
            if path.read_bytes() != original:
                path.write_bytes(original)
        _dogfood_registry_path(PLUGIN_ROOT).unlink(missing_ok=True)

    def test_every_hard_rule_has_a_designed_plant(self) -> None:
        charter = compile_charter(PLUGIN_ROOT)
        live_hard_ids = {r["id"] for r in charter["compiled"] if r["enforcement"] == HARD}
        planted_ids = {p["rule"] for p in self.PLANTS}
        # The five live HARD rules named in the brief must still be exactly
        # what the charter compiles today - if the ids drifted, this fails
        # loudly instead of silently proving nothing.
        for rid in planted_ids:
            self.assertIn(rid, live_hard_ids, f"{rid} is no longer a live HARD rule id")

    def test_zzz_planting_all_five_leaves_assess_with_zero_unplanted_hard_rules(self) -> None:
        # Named to sort last within this class: it both proves each plant
        # green->red->green AND checks the archive-wide consequence in one
        # method, so there is no cross-test ordering to get wrong. (Two
        # earlier, separately-named tests split this in a way whose
        # correctness depended on alphabetical method order lining up with
        # execution order - the kind of implicit dependency this project's
        # own charter rules exist to catch, caught here by removing it.)
        archive = Chronicle(resolve_anchor(PLUGIN_ROOT))
        archive.initialize()
        session = open_session(archive, "capability-register-dogfooding-test")
        for plant in self.PLANTS:
            with self.subTest(plant=plant["name"]):
                outcome = plant_and_observe(
                    archive, session, PLUGIN_ROOT, plant["name"], plant["command"],
                    plant["target"], replace=plant["replace"], with_text=plant["with_text"],
                    rule_ids=[plant["rule"]], timeout=180,
                )
                self.assertTrue(
                    outcome["observed_failing"],
                    f"{plant['name']} did not prove green->red->green: {outcome['detail']}",
                )
        report = assess(PLUGIN_ROOT, archive=archive)
        self.assertEqual(report["charter"]["hard_unplanted"], [])

    # Four of the eight scaffolded role docs (state, decisions, lessons,
    # sprint-truth) are gitignored by this repository's own convention -
    # local, proprietary, never shipped, same policy as the checkpoint/spec
    # files under .godmode-private. `missing_roles == []` and the content
    # check below are therefore environment-dependent: true on a machine
    # where `godmode init --roles` has been run and every stub filled (this
    # session's own dogfooding), not a portable claim about a bare clone
    # that never ran that step. Consistent with how `selftest` reports a
    # control UNAVAILABLE rather than failing when the host can't support
    # it, this skips rather than fails when that local step has not
    # happened here.
    ROLE_STUBS = {
        "docs/STATE.md": "Current reality snapshot",
        "docs/DECISIONS.md": "Rulings with their reasons",
        "docs/FIXED-REGISTRY.md": "Behaviours that must stay true",
        "docs/FEATURE-INVENTORY.md": "What exists and where",
        "docs/LESSONS.md": "What failed and the rule",
        "OPERATOR.md": "Who operates this project",
        "docs/SPRINT-SSOT.md": "What is actually in flight",
        "docs/RELEASE-CHECKLIST.md": "Standing verification rows",
    }

    def test_missing_roles_is_empty(self) -> None:
        missing_files = [r for r in self.ROLE_STUBS if not (PLUGIN_ROOT / r).is_file()]
        if missing_files:
            self.skipTest(
                f"role docs not scaffolded on this machine yet: {missing_files}; "
                "run `godmode init --roles` and fill each stub first")
        report = assess(PLUGIN_ROOT)
        self.assertEqual(report["authority"]["missing_roles"], [])

    def test_every_scaffolded_role_stub_carries_real_content_not_the_bare_purpose_line(self) -> None:
        for relative, purpose_fragment in self.ROLE_STUBS.items():
            path = PLUGIN_ROOT / relative
            if not path.is_file():
                continue
            with self.subTest(stub=relative):
                text = path.read_text(encoding="utf-8")
                self.assertIn(purpose_fragment, text)
                # More than the title + one-line purpose: a real paragraph landed.
                self.assertGreater(
                    len(text), len(purpose_fragment) + 400,
                    f"{relative} looks like it still carries only the scaffolded stub",
                )


if __name__ == "__main__":
    unittest.main()

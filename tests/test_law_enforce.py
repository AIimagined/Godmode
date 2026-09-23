"""I-1 (0.3.28 Plan 5 Task 4): guards that execute, not advise.

WHY: laws were rendered `[ADVISORY]` prose only - a lesson's guard was
something a brief carried and a session could ignore. A lesson may now carry
`enforce: {kind, predicate}`; `Chronicle.append` refuses a write of `kind`
whose `data` matches `predicate`, the guard text standing in as the remedy.
The grammar is exactly three operators (`==`, `contains`, `matches`), always
read against the incoming record's `data` - never `evidence` or any other
top-level field - with dotted field paths and "missing field never matches".

`H6AbsorbFixtureTests` below is a PARALLEL, hypothetical fixture shaped like
`godmode_absorb.validate_absorb`'s rule (an adopt/extend verdict needs a
source-code cite) - not a reproduction of it, and not the "first `enforce`
instance" for that rule. The real rule keys on `evidence`
(`godmode_absorb.py:73-93`, `is_source_cite()`); this grammar reads `data`
only, by design, and cannot reach `evidence` at all - extending it there is
a legitimate follow-up, not this fixture's job. See the class docstring for
what changed after task-4-review.md's Blocking 4/H6 finding.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    EnforceFieldTooLong,
    enforce_predicate_matches,
    parse_enforce_predicate,
    parse_enforce_spec,
)


@contextlib.contextmanager
def isolated_archive():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict("os.environ", {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    # A refusal (`GodmodeError`) is printed to stderr, never stdout - see
    # `godmode_console.main`'s except clause - so both are captured here and
    # whichever one is non-empty is the payload.
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip() or err.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _remember_enforce(project: Path, subject: str, guard: str, enforce: str, **extra: str):
    argv = [
        "remember", "--kind", "lesson", "--subject", subject,
        "--value", guard, "--guard", guard, "--enforce", enforce,
    ]
    for key, value in extra.items():
        argv += [f"--{key.replace('_', '-')}", value]
    return _run(project, *argv)


class GrammarTests(unittest.TestCase):
    """Each operator parses; each malformed shape is refused with a remedy."""

    def test_equals_operator_parses(self) -> None:
        parsed = parse_enforce_predicate("status == closed")
        self.assertEqual(parsed, {"field": "status", "op": "==", "literal": "closed"})

    def test_contains_operator_parses(self) -> None:
        parsed = parse_enforce_predicate("value contains TODO")
        self.assertEqual(parsed, {"field": "value", "op": "contains", "literal": "TODO"})

    def test_matches_operator_parses(self) -> None:
        parsed = parse_enforce_predicate(r"value matches (?i)todo")
        self.assertEqual(parsed["op"], "matches")
        self.assertEqual(parsed["literal"], "(?i)todo")

    def test_dotted_field_path_parses(self) -> None:
        parsed = parse_enforce_predicate("import_verdict.kind == adopt")
        self.assertEqual(parsed["field"], "import_verdict.kind")

    def test_no_operator_refused(self) -> None:
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_predicate("value TODO")
        self.assertIn("field == literal", str(ctx.exception))

    def test_empty_field_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            parse_enforce_predicate(" == closed")

    def test_empty_literal_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            parse_enforce_predicate("status == ")

    def test_bad_regex_refused(self) -> None:
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_predicate("value matches (unterminated")
        self.assertIn("does not compile", str(ctx.exception))

    def test_unrecognised_kind_refused(self) -> None:
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_spec("kind=not-a-real-kind;predicate=value == x")
        self.assertIn("not-a-real-kind", str(ctx.exception))

    def test_missing_predicate_clause_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            parse_enforce_spec("kind=decision")

    def test_malformed_predicate_refused_at_remember_time(self) -> None:
        """The CLI surfaces the same refusal, with a remedy, before the
        record ever reaches the archive."""
        with isolated_archive() as (project, archive):
            code, payload = _remember_enforce(
                project, "bad-predicate", "guard text",
                "kind=decision;predicate=value ??? x")
            self.assertNotEqual(code, 0)
            self.assertEqual(payload.get("error"), "ArchiveError")
            self.assertIn("field == literal", payload.get("message", ""))
            self.assertEqual(
                [r for r in archive.read_events() if r["kind"] == "lesson"], [])

    def test_enforce_without_guard_refused(self) -> None:
        with isolated_archive() as (project, _archive):
            code, payload = _run(
                project, "remember", "--kind", "lesson", "--subject", "no-guard",
                "--value", "v", "--enforce", "kind=decision;predicate=value == x")
            self.assertNotEqual(code, 0)
            self.assertIn("--guard", payload.get("message", ""))

    def test_leftmost_operator_wins_not_longest(self) -> None:
        # Fix round 1 (nit 6): "==" occurs BEFORE "contains" in this text -
        # the longest-operator-first parse used to check "contains" first
        # (it is the longer marker), split on that instead, and refuse a
        # well-formed "==" predicate with a confusing "field must be a
        # dotted path" remedy. The first marker to actually occur wins.
        parsed = parse_enforce_predicate("value == some text that contains a word")
        self.assertEqual(parsed["field"], "value")
        self.assertEqual(parsed["op"], "==")
        self.assertEqual(parsed["literal"], "some text that contains a word")

    def test_enforce_literal_over_max_refused(self) -> None:
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_predicate("value == " + ("x" * 257))
        self.assertIn("256", str(ctx.exception))

    def test_enforce_literal_at_max_accepted(self) -> None:
        parsed = parse_enforce_predicate("value == " + ("x" * 256))
        self.assertEqual(len(parsed["literal"]), 256)

    def test_nested_quantifier_regex_refused(self) -> None:
        for shape in (r"(a+)+", r"(a*)*", r"(a+)*", r"(a*)+"):
            with self.subTest(shape=shape):
                with self.assertRaises(ArchiveError) as ctx:
                    parse_enforce_predicate(f"value matches {shape}$")
                self.assertIn("quantifies a group", str(ctx.exception))

    def test_quantified_group_regex_refused_round_2(self) -> None:
        # Blocking 2, round 2: re-review measured these three shapes parsing
        # clean under round 1's narrower refusal and then blowing up far
        # inside the 4,096-character text cap - `(a|aa)+$` (alternation
        # inside a quantified group, 3.44s at 32 scanned characters),
        # `(a+){2,}$` (a `{n,}` bound on a quantified group, 22.2s at 26),
        # and `(a|a?)+$` (49.3s at 24). The widened rule refuses ANY
        # quantifier following a closing paren, so all three are refused at
        # parse time regardless of what the group contains, and so is the
        # plain, non-catastrophic `(ab)+` round 1 let through - the honest
        # trade for a rule that does not need to enumerate every
        # catastrophic shape (see `_enforce_regex_quantifier_violation`,
        # which round 3 further tightened - see the tests below).
        for shape in (r"(a|aa)+", r"(a+){2,}", r"(a|a?)+", r"(ab)+"):
            with self.subTest(shape=shape):
                with self.assertRaises(ArchiveError) as ctx:
                    parse_enforce_predicate(f"value matches {shape}$")
                # A grouped alternation is refused before its quantifier is
                # reached (round 4), so either reason closes the shape.
                self.assertTrue(
                    "quantifies a group" in str(ctx.exception)
                    or "alternates inside a group" in str(ctx.exception),
                    str(ctx.exception))
                self.assertIn("contains literal", str(ctx.exception))

    def test_alternation_inside_a_group_refused_round_4(self) -> None:
        # Re-review round 3: `(a|aa)` chained needs no quantifier to blow up
        # (unfinished in 90 s at the 4,096 cap), so an alternation inside a
        # group is refused outright; top-level branches stay allowed.
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_predicate(r"value matches (a|aa)(a|aa)(a|aa)X")
        self.assertIn("alternates inside a group", str(ctx.exception))
        self.assertIn("contains literal", str(ctx.exception))
        with self.assertRaises(ArchiveError):
            parse_enforce_predicate(r"value matches (?:foo|bar)X")
        parse_enforce_predicate(r"value matches ^TODO|^FIXME")  # top-level branches: fine

    def test_two_quantified_atoms_now_refused_round_3(self) -> None:
        # Blocking 1, round 3: `[a-z]+\d{1,40}$` parsed clean under round 2
        # (a quantifier on an atom/class, never a group) - re-review
        # measured that STACKED quantified atoms are polynomial and just as
        # unusable at the 4,096-character cap as a quantified group
        # (`a+a+a+a+X`: 44.6s at 200 scanned characters, unfinished at
        # 4,096). Round 3 tightens the rule to AT MOST ONE quantifier
        # anywhere in the pattern, so this two-quantifier shape - one on
        # `[a-z]`, one on `\d` - is now refused too.
        with self.assertRaises(ArchiveError) as ctx:
            parse_enforce_predicate(r"value matches [a-z]+\d{1,40}$")
        self.assertIn("more than one quantifier", str(ctx.exception))
        self.assertIn("contains literal", str(ctx.exception))

    def test_stacked_quantified_atoms_and_classes_refused_round_3(self) -> None:
        # Ruling (round 3, fix 1): the exact shapes re-review measured as
        # accepted-but-polynomial under round 2's group-only refusal.
        for shape in (r"a+a+a+a+X", r"[ab]*[ab]*c", r"a*a*b", r"(a+)(a+)b"):
            with self.subTest(shape=shape):
                with self.assertRaises(ArchiveError) as ctx:
                    parse_enforce_predicate(f"value matches {shape}")
                self.assertIn("contains literal", str(ctx.exception))

    def test_single_quantifier_shapes_accepted_round_3(self) -> None:
        # A single quantified atom or character class, plus free anchors
        # and literals, is exactly the grammar round 3 keeps legal - and
        # the one the boundedness claim in `enforce_predicate_matches`
        # actually rests on (linear in the scanned length).
        for shape in (r"^TODO.*$", r"x+$", r"[0-9]+"):
            with self.subTest(shape=shape):
                parsed = parse_enforce_predicate(f"value matches {shape}")
                self.assertEqual(parsed["literal"], shape)

    def test_single_quantifier_worst_case_completes_at_the_text_cap(self) -> None:
        # Ruling (round 3, fix 1): "time the accepted worst case against
        # 4096 chars and assert it completes" - no wall-clock assertion on
        # duration, just that a single quantifier over the full scan cap
        # actually returns (it must, being linear - this is the bound the
        # boundedness claim rests on).
        text = "a" * 4096
        self.assertTrue(enforce_predicate_matches("value matches a+$", {"value": text}))
        self.assertFalse(enforce_predicate_matches("value matches b+$", {"value": text}))

    def test_scanned_text_over_max_is_truncated_not_silently_missed(self) -> None:
        # Blocking 2, corrected round 2 (nit 2a): round 1's over-cap
        # behaviour was "never matches" - itself a guard evasion, verified
        # in re-review: an armed `value contains TODO` predicate missed the
        # needle when an unrelated tail padded the value past 4,096
        # characters, while the same 9-character value without the padding
        # was refused. `enforce_predicate_matches` now truncates to the
        # first `_ENFORCE_TEXT_MAX` characters instead of refusing to look
        # at all, so a needle inside that window is still found - only a
        # needle that starts entirely past the cap is missed, and that
        # residual is now stated in the docstring rather than left silent.
        needle_near_the_start = "TODO " + ("x" * 4200)
        self.assertTrue(
            enforce_predicate_matches("value contains TODO", {"value": needle_near_the_start}))
        needle_past_the_cap = ("x" * 4200) + "TODO"
        self.assertFalse(
            enforce_predicate_matches("value contains TODO", {"value": needle_past_the_cap}))

    def test_scanned_text_at_and_under_max_matches_normally(self) -> None:
        short_value = "TODO" + ("x" * 4091)
        self.assertTrue(
            enforce_predicate_matches("value contains TODO", {"value": short_value}))

    def test_enforce_forbidden_kind_refused_at_parse_time(self) -> None:
        for kind in ("refusal", "action", "checkpoint"):
            with self.subTest(kind=kind):
                with self.assertRaises(ArchiveError) as ctx:
                    parse_enforce_spec(f"kind={kind};predicate=value == x")
                self.assertIn("audit trail", str(ctx.exception))

    def test_enforce_on_non_lesson_kind_refused_loudly(self) -> None:
        # Nit 5: a silent drop is a worse failure than a loud one.
        with isolated_archive() as (project, archive):
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "not-a-lesson",
                "--value", "v", "--enforce", "kind=decision;predicate=value == x")
            self.assertNotEqual(code, 0)
            self.assertIn("--enforce", payload.get("message", ""))
            self.assertEqual(archive.read_events(), [])


class RefusalTests(unittest.TestCase):
    def test_matching_write_refused_with_guard_and_seq(self) -> None:
        with isolated_archive() as (project, archive):
            code, payload = _remember_enforce(
                project, "no-todo-comments", "do not leave TODO comments in shipped code",
                "kind=decision;predicate=value contains TODO")
            self.assertEqual(code, 0)
            lesson_seq = payload["record"]["sequence"]

            with self.assertRaises(ArchiveError) as ctx:
                archive.append("decision", "ship-it", {"value": "left a TODO here", "status": "active"})
            message = str(ctx.exception)
            self.assertIn("do not leave TODO comments in shipped code", message)
            self.assertIn(f"seq:{lesson_seq}", message)

    def test_no_match_passes(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "no-todo-comments-2", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            record = archive.append("decision", "ship-it-clean", {"value": "all done", "status": "active"})
            self.assertEqual(record["kind"], "decision")

    def test_missing_field_never_matches(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "needs-region", "every deploy names a region",
                "kind=action;predicate=region == us-east")
            # `region` absent entirely - a missing field never matches, so this passes.
            record = archive.append("action", "deploy", {"value": "deployed", "status": "active"})
            self.assertEqual(record["kind"], "action")

    def test_dotted_field_path_evaluated_over_data(self) -> None:
        matched = enforce_predicate_matches(
            "import_verdict.kind == adopt", {"import_verdict": {"kind": "adopt"}})
        self.assertTrue(matched)
        self.assertFalse(enforce_predicate_matches(
            "import_verdict.kind == adopt", {"import_verdict": {"kind": "diverge"}}))

    def test_kind_scoping_only_refuses_its_own_kind(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "decisions-only", "no TODOs in decisions",
                "kind=decision;predicate=value contains TODO")
            # Same offending text, different kind - the enforce lesson named
            # `decision`, not `action`, so this is not its business.
            record = archive.append("action", "note-it", {"value": "TODO later", "status": "active"})
            self.assertEqual(record["kind"], "action")


class MatchesOverCapTests(unittest.TestCase):
    """Blocking 2, round 3: round 2's truncate-then-scan for `matches`
    reintroduced the exact hazard round 1's docstring had named as the
    reason not to truncate - a refusal for a match the full value never
    contained. `matches` against an over-cap field now refuses the write
    fail-closed instead of guessing either direction; `contains`/`==` are
    unaffected (truncation can only ever LOSE a `contains` match, and `==`
    is unconditionally false against a longer value either way)."""

    def test_matches_over_cap_raises_fail_closed(self) -> None:
        with self.assertRaises(EnforceFieldTooLong) as ctx:
            enforce_predicate_matches("value matches x", {"value": "x" * 4097})
        self.assertIn("too long for an enforce predicate", str(ctx.exception))
        self.assertIn("shorten it or cite it as evidence", str(ctx.exception))

    def test_matches_at_cap_still_evaluates_normally(self) -> None:
        # The boundary itself (exactly 4,096) is not "over cap" - only a
        # field STRICTLY longer than the cap refuses.
        self.assertTrue(
            enforce_predicate_matches("value matches x$", {"value": "y" * 4095 + "x"}))

    def test_invented_refusal_from_round_2_truncation_no_longer_matches_or_passes(self) -> None:
        # The two shapes re-review measured inventing a match from
        # truncation now raise instead of silently returning True.
        needle_moved_by_truncation = "x" * 4092 + "TODO" + "y" * 40
        with self.assertRaises(EnforceFieldTooLong):
            enforce_predicate_matches("value matches TODO$", {"value": needle_moved_by_truncation})
        lookahead_defeated_by_truncation = "x" * 4096 + "APPROVED"
        with self.assertRaises(EnforceFieldTooLong):
            enforce_predicate_matches(
                r"value matches ^(?!.*APPROVED)", {"value": lookahead_defeated_by_truncation})

    def test_contains_and_equals_are_unaffected_by_the_matches_fix(self) -> None:
        over_cap = "x" * 4097
        # `contains`: truncation can only ever LOSE a match, never invent one.
        self.assertFalse(enforce_predicate_matches("value contains y", {"value": over_cap + "y"}))
        self.assertTrue(enforce_predicate_matches("value contains x", {"value": over_cap}))
        # `==`: unconditionally false against a value longer than the
        # (256-character-capped) literal, truncated or not.
        self.assertFalse(enforce_predicate_matches("value == " + "x" * 256, {"value": over_cap}))

    def test_over_cap_matches_field_refuses_the_write_end_to_end(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "todo-suffix-guard", "no TODO suffix",
                "kind=decision;predicate=value matches TODO$")
            with self.assertRaises(ArchiveError) as ctx:
                archive.append(
                    "decision", "ship-it-over-cap",
                    {"value": "x" * 4092 + "TODO" + "y" * 40, "status": "active"})
            message = str(ctx.exception)
            self.assertIn("too long for an enforce predicate", message)
            self.assertIn("shorten it or cite it as evidence", message)


class DoctorSeedsEnforceIndexCliTests(unittest.TestCase):
    def test_godmode_doctor_seeds_the_sidecar(self) -> None:
        # I-1 fix round 3 (B1 deployment note): `godmode doctor` warms
        # `godmode-enforce.index.json` from its own unlocked full walk -
        # the end-to-end wiring for `Chronicle.seed_enforce_index` (see
        # `tests/test_chronicle_depth.py` for the lock-free proof).
        with isolated_archive() as (project, archive):
            for index in range(30):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            sidecar = archive.root / "godmode-enforce.index.json"
            sidecar.unlink()
            self.assertFalse(sidecar.is_file())
            code, _payload = _run(project, "doctor")
            self.assertEqual(code, 0)
            self.assertTrue(sidecar.is_file())


class HookExemptionTests(unittest.TestCase):
    """Blocking 3: a hook's own writes are exempt from enforcement, and an
    enforce spec naming one of the gate's audit-trail kinds is refused at
    authoring time (see GrammarTests.test_enforce_forbidden_kind_refused_
    at_parse_time above for that half)."""

    def test_hook_writer_is_exempt_from_enforcement(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "block-decisions", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
            with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
                record = archive.append(
                    "decision", "ship-it", {"value": "has a TODO", "status": "active"})
            self.assertEqual(record["writer"], "hook")

    def test_enforce_targeting_forbidden_kind_refused_at_append_time(self) -> None:
        # Defence-in-depth: a raw `Chronicle.append` that builds the
        # `enforce` dict by hand, bypassing `godmode_law.parse_enforce_
        # spec`, is refused too (`godmode_invariants._lesson_invariants`).
        with isolated_archive() as (project, archive):
            with self.assertRaises(ArchiveError) as ctx:
                archive.append(
                    "lesson", "block-actions",
                    {"value": "v", "status": "active", "generalized_guard": "g",
                     "enforce": {"kind": "action", "predicate": "value == x"}})
            self.assertIn("audit trail", str(ctx.exception))


class SupersessionAndLockoutTests(unittest.TestCase):
    def test_active_lesson_with_no_enforce_or_supersede_is_refused(self) -> None:
        # Ruling 4: an ordinary `remember --kind lesson` on the same subject
        # must not be able to silently disarm an active guard by omission.
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "no-todo-comments-5", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            code, payload = _run(
                project, "remember", "--kind", "lesson", "--subject", "no-todo-comments-5",
                "--value", "an unrelated update")
            self.assertNotEqual(code, 0)
            self.assertIn("silently disarmed", payload.get("message", ""))
            # The guard must still be armed - the refused write never landed.
            with self.assertRaises(ArchiveError):
                archive.append("decision", "ship-it-3", {"value": "TODO", "status": "active"})

    def test_reaffirming_enforce_is_accepted(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "no-todo-comments-6", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            code, _payload = _remember_enforce(
                project, "no-todo-comments-6", "no TODOs, reaffirmed",
                "kind=decision;predicate=value contains TODO")
            self.assertEqual(code, 0)
            with self.assertRaises(ArchiveError) as ctx:
                archive.append("decision", "ship-it-4", {"value": "still TODO", "status": "active"})
            self.assertIn("reaffirmed", str(ctx.exception))

    def test_superseded_lifts_the_refusal(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "no-todo-comments-3", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            with self.assertRaises(ArchiveError):
                archive.append("decision", "ship-it", {"value": "TODO", "status": "active"})
            # The same subject, a new record, status superseded - the
            # newest-per-subject dedup this task shares with `top_laws`
            # (godmode_law._guarded_lessons) means this now wins.
            _run(project, "remember", "--kind", "lesson", "--subject", "no-todo-comments-3",
                 "--value", "retracted", "--status", "superseded")
            record = archive.append("decision", "ship-it-2", {"value": "still has a TODO", "status": "active"})
            self.assertEqual(record["kind"], "decision")

    def test_status_retired_also_lifts_the_refusal(self) -> None:
        # Nit (round 2): `retired` is one of `LESSON_DORMANT_STATUSES`
        # alongside `superseded` and `candidate` - the completeness rule
        # used to accept only the literal string "superseded" and refuse a
        # `--status retired` write on a guarded subject, even though
        # `retired` already takes a lesson out of enforcement everywhere
        # else. Any dormant status now lifts the guard the same way.
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "no-todo-comments-7", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            with self.assertRaises(ArchiveError):
                archive.append("decision", "ship-it-5", {"value": "TODO", "status": "active"})
            code, _payload = _run(
                project, "remember", "--kind", "lesson", "--subject", "no-todo-comments-7",
                "--value", "retracted", "--status", "retired")
            self.assertEqual(code, 0)
            record = archive.append(
                "decision", "ship-it-6", {"value": "still has a TODO", "status": "active"})
            self.assertEqual(record["kind"], "decision")

    def test_amend_cli_keeps_an_enforcing_guard_armed(self) -> None:
        # Blocking 3, end to end through the real verb: `amend_law` used to
        # build its replacement lesson from scratch and carry forward only
        # `standing`, never `enforce` - so `godmode law amend` on a law it
        # protects raised the very supersession refusal this feature adds,
        # with no way for the operator to comply. `enforce` is now carried
        # forward the same way `standing` is.
        with isolated_archive() as (project, archive):
            code, payload = _remember_enforce(
                project, "no-todo-comments-8", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            self.assertEqual(code, 0)
            law_seq = payload["record"]["sequence"]
            code, payload = _run(
                project, "law", "amend", "--law", str(law_seq),
                "--guard", "no TODOs, reworded via amend")
            self.assertEqual(code, 0, payload)
            # The guard is still armed - the amendment reworded it rather
            # than silently disarming it.
            with self.assertRaises(ArchiveError):
                archive.append("decision", "ship-it-7", {"value": "a TODO here", "status": "active"})

    def test_self_lockout_impossible(self) -> None:
        with isolated_archive() as (project, archive):
            # An enforce rule that names `lesson` as its own target kind
            # must never block recording a lesson - not even the corrective
            # one that would supersede it.
            _remember_enforce(
                project, "block-all-lessons", "never happens",
                "kind=lesson;predicate=value == x")
            record = archive.append(
                "lesson", "block-all-lessons",
                {"value": "x", "status": "superseded", "generalized_guard": "retracted"})
            self.assertEqual(record["kind"], "lesson")

    def test_a_lesson_record_itself_is_never_refused(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(
                project, "reject-everything", "never happens",
                "kind=lesson;predicate=value contains x")
            # A fresh, unrelated lesson also carrying "x" in its value must
            # still land - lessons are categorically exempt from enforcement.
            record = archive.append(
                "lesson", "another-lesson",
                {"value": "contains an x", "status": "active", "generalized_guard": "g"})
            self.assertEqual(record["kind"], "lesson")


class CacheTests(unittest.TestCase):
    def test_cache_invalidates_on_a_new_lesson(self) -> None:
        with isolated_archive() as (project, archive):
            # Build up archive history with no enforcing lesson yet, and
            # force the enforce index to fold all of it in.
            for i in range(25):
                archive.append("action", f"warmup-{i}", {"value": "nothing special", "status": "active"})
            before = archive.append("decision", "still-clean", {"value": "TODO", "status": "active"})
            self.assertEqual(before["kind"], "decision")
            # `_write_record`'s own incremental bump (mirroring the events
            # cache's own extension trick) keeps the index caught up to the
            # record just sealed, including it - the cheap proxy for "the
            # archive head this index was built against".
            folded_before = archive._enforce_index_upto
            self.assertEqual(folded_before, len(archive.read_events()))

            # Now record the enforcing lesson - the index must pick it up
            # on the very next append, not stay pinned to the old state.
            _remember_enforce(
                project, "no-todo-comments-4", "no TODOs",
                "kind=decision;predicate=value contains TODO")
            with self.assertRaises(ArchiveError):
                archive.append("decision", "should-be-refused", {"value": "a TODO here", "status": "active"})
            self.assertGreater(archive._enforce_index_upto, folded_before)


class H6AbsorbFixtureTests(unittest.TestCase):
    """A parallel, HYPOTHETICAL `enforce` guard shaped like H6 - not a
    reproduction of it. (task-4-review.md, Blocking 4/H6, fix round 1.)

    H6 (`godmode_absorb.validate_absorb`) refuses an adopt/extend verdict
    with no SOURCE citation - it decides by reading `evidence` (via
    `is_source_cite()`, `godmode_absorb.py:73-93`) for a `file:`/`receipt:`
    entry that is not a README/docs path. The enforce grammar reads a
    write's `data` only, by design (see module docstring) - it never sees
    `evidence`, so it cannot express H6's actual discriminator (cited
    source vs. cited README). Round 1's review found the PRIOR version of
    this fixture papered over that gap with a `cite-kind:readme` marker
    invented for the test - it appears nowhere in the product; no real
    `absorb:*` write has ever carried it.

    This fixture instead guards the one HALF of H6 a real, persisted `data`
    field actually expresses: `import_verdict` (set by `cmd_remember` for
    every absorb decision, `godmode_console.py:3782`). Read literally, the
    guard below refuses every `adopt` verdict on this subject, cited or
    not - a strictly BLUNTER rule than H6's own, kept only to prove the
    enforce mechanism reaches a real field on a real write shape.
    Extending the grammar to read `evidence` so H6's actual rule becomes
    expressible is a legitimate follow-up, not this task's job.
    """

    GUARD = "an absorb decision recorded on this subject always needs another look first"
    PREDICATE = "import_verdict == adopt"

    def test_adopt_verdict_refused(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(project, "h6-shaped-guard", self.GUARD,
                               f"kind=decision;predicate={self.PREDICATE}")
            with self.assertRaises(ArchiveError) as ctx:
                archive.append(
                    "decision", "absorb:some-upstream-thing",
                    {"value": "import_verdict:adopt behaviour_verdict:confirmed-have",
                     "import_verdict": "adopt", "status": "active"})
            self.assertIn(self.GUARD, str(ctx.exception))

    def test_other_verdicts_pass(self) -> None:
        with isolated_archive() as (project, archive):
            _remember_enforce(project, "h6-shaped-guard-2", self.GUARD,
                               f"kind=decision;predicate={self.PREDICATE}")
            record = archive.append(
                "decision", "absorb:another-thing",
                {"value": "import_verdict:diverge behaviour_verdict:confirmed-have",
                 "import_verdict": "diverge", "status": "active"})
            self.assertEqual(record["kind"], "decision")


if __name__ == "__main__":
    unittest.main()

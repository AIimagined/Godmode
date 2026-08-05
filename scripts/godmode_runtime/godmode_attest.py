"""Make a skipped step a blocking state instead of an apology afterwards.

Two mechanisms, both deliberately dumb so they cannot be reasoned around:

* Attestation. Every mandated step records what it did, including finding nothing.
  A HARD rule with no attestation blocks the gate it guards.
* Claim binding. An assertion about project state cites records that must resolve.
  An unresolvable citation downgrades the claim to a hypothesis automatically — it
  is not warned about, it is demoted.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

STATUSES = ("ran", "empty", "skipped", "blocked")
GRADES = ("observed", "hypothesis", "verified", "unknown")

_FILE_CITE = re.compile(r"^file:(?P<path>[^#]+)(?:#L(?P<start>\d+)(?:-L?(?P<end>\d+))?)?$")
_RECORD_CITE = re.compile(r"^rec:(?P<digest>[0-9a-f]{6,64})$")

# Named because naming them is the intervention. Each entry is a thought that has
# preceded a skipped step, mapped to the gate it predicts. Surfaced on a block so the
# reasoning is interrupted rather than the action alone.
RATIONALIZATIONS: tuple[tuple[str, str], ...] = (
    ("This one is small enough to skip the check.", "before_mutation"),
    ("The answer seems obvious already.", "before_approach"),
    ("No code is written yet, so this is not a change.", "before_approach"),
    ("The suite passed, so the blast radius is covered.", "before_completion"),
    ("I already know what that document says.", "session_open"),
    ("The status label is recent enough to trust.", "before_completion"),
    ("I will record the evidence after this step.", "session_close"),
)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    trigger: str
    missing: tuple[dict[str, Any], ...]

    def view(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trigger": self.trigger,
            "allowed": self.allowed,
            "missing": list(self.missing),
        }
        if not self.allowed:
            payload["watch_for"] = [
                text for text, trigger in RATIONALIZATIONS if trigger == self.trigger
            ] or [text for text, _ in RATIONALIZATIONS]
        return payload


def agent_fingerprint() -> dict[str, Any]:
    """Identify who is acting, so drift between models is attributable."""
    return {
        "host": os.environ.get("GODMODE_HOST") or os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "unknown",
        "model": os.environ.get("GODMODE_MODEL", "unknown"),
        "effort": os.environ.get("GODMODE_EFFORT", "unknown"),
    }


def open_session(archive: Chronicle, label: str) -> str:
    record = archive.append(
        "session", label, {"state": "open", "agent": agent_fingerprint()}, evidence=[]
    )
    return f"S-{record['record_hash'][:12]}"


def _sessions(archive: Chronicle) -> list[dict[str, Any]]:
    return archive.select(kind="session", limit=200)


def latest_session(archive: Chronicle) -> str | None:
    records = _sessions(archive)
    if not records:
        return None
    # select() is chronological, so the newest session is the last element.
    return f"S-{records[-1]['record_hash'][:12]}"


def record_step(
    archive: Chronicle,
    session: str,
    step: str,
    status: str,
    result: str = "",
    evidence: list[str] | None = None,
    rule_ids: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ArchiveError(f"Unknown attestation status '{status}'; expected one of {', '.join(STATUSES)}")
    if status == "skipped" and not reason.strip():
        # A skip without a reason is the failure this module exists to stop.
        raise ArchiveError("A skipped step requires --reason stating why it was skipped")
    return archive.append(
        "attestation",
        step,
        {
            "session": session,
            "status": status,
            "result": result,
            "reason": reason,
            "rule_ids": sorted(rule_ids or []),
            "agent": agent_fingerprint(),
        },
        evidence=evidence or [],
    )


def run_check(
    archive: Chronicle,
    session: str,
    project: Path,
    name: str,
    command: list[str],
    rule_ids: list[str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    """Run a declared check and attest its exit code, rather than its report.

    An attestation an agent writes about its own work is a report. The gate it
    satisfies is then only as good as the agent's willingness to say the check
    failed, which is exactly the moment it is least inclined to. So the runner
    records the result: a non-zero exit is stored as `blocked`, and `blocked` never
    satisfies a gate, so a failing check cannot be attested into a pass.
    """
    import subprocess

    try:
        completed = subprocess.run(
            command, cwd=str(project), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        code = completed.returncode
        tail = ((completed.stdout or "") + (completed.stderr or "")).strip().splitlines()
        detail = " | ".join(tail[-3:])[:300] if tail else "(no output)"
    except FileNotFoundError:
        code, detail = 127, f"command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        code, detail = 124, f"timed out after {timeout}s"

    passed = code == 0
    record = record_step(
        archive,
        session,
        f"check:{name}",
        "ran" if passed else "blocked",
        result=f"exit {code}: {detail}",
        evidence=[f"cmd:{' '.join(command)[:160]}"],
        rule_ids=rule_ids,
        reason="" if passed else f"check failed with exit {code}",
    )
    return {
        "check": name,
        "command": command,
        "exit_code": code,
        "passed": passed,
        "detail": detail,
        "attested": "ran" if passed else "blocked",
        "sequence": record["sequence"],
    }


def plant_and_observe(
    archive: Chronicle,
    session: str,
    project: Path,
    name: str,
    command: list[str],
    target: str,
    replace: str | None = None,
    with_text: str = "",
    append: str | None = None,
    rule_ids: list[str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    """Prove a guard can fail, by breaking the thing it guards and watching it.

    A guard that has never been seen failing is a suggestion. It may be asserting
    nothing, testing the wrong surface, or silently skipping - and all three look
    exactly like a pass. So the sequence is green, then red with a planted
    violation, then green again once restored. Only that whole sequence attests.

    The plant itself is verified to have landed: a mutation that changed no bytes
    would produce a green run that reads as "the guard held" when nothing was ever
    broken.
    """
    import subprocess

    path = project / target
    if not path.is_file():
        raise ArchiveError(f"Cannot plant a violation in a missing file: {target}")
    original = path.read_bytes()

    def run() -> int:
        try:
            done = subprocess.run(command, cwd=str(project), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
            return done.returncode
        except FileNotFoundError:
            return 127
        except subprocess.TimeoutExpired:
            return 124

    steps: dict[str, Any] = {}
    try:
        steps["baseline"] = run()

        text = original.decode("utf-8", errors="replace")
        if append is not None:
            mutated = text + ("" if text.endswith("\n") else "\n") + append + "\n"
        elif replace is not None:
            mutated = text.replace(replace, with_text, 1)
        else:
            raise ArchiveError("A plant needs --replace or --append")

        planted_bytes = mutated.encode("utf-8")
        # A plant that changes nothing turns the whole exercise into a green run
        # that proves only that the file was untouched.
        if planted_bytes == original:
            raise ArchiveError(
                f"The planted violation changed no bytes in {target}; the guard would "
                "have been observed passing against unmodified code"
            )
        path.write_bytes(planted_bytes)
        steps["planted_bytes_changed"] = len(planted_bytes) - len(original)
        steps["with_violation"] = run()
    finally:
        path.write_bytes(original)
    steps["restored"] = run()

    green_first = steps["baseline"] == 0
    went_red = steps["with_violation"] != 0
    green_again = steps["restored"] == 0
    proven = green_first and went_red and green_again

    if proven:
        detail = f"green({steps['baseline']}) -> red({steps['with_violation']}) -> green({steps['restored']})"
        reason = ""
    else:
        detail = (
            f"baseline={steps['baseline']} planted={steps['with_violation']} "
            f"restored={steps['restored']}"
        )
        reason = (
            "guard did not fail against a planted violation" if green_first and not went_red
            else "guard was not green before planting" if not green_first
            else "state did not return to green after restoring"
        )

    record = record_step(
        archive, session, f"guard:{name}",
        "ran" if proven else "blocked",
        result=f"{'observed failing' if proven else 'not observed failing'}: {detail}",
        evidence=[f"cmd:{' '.join(command)[:120]}", f"file:{target}"],
        rule_ids=rule_ids,
        reason=reason,
    )
    return {
        "guard": name,
        "target": target,
        "sequence": steps,
        "observed_failing": proven,
        "detail": detail,
        "reason": reason,
        "attested": "ran" if proven else "blocked",
        "record": record["sequence"],
    }


def attested_rule_ids(archive: Chronicle, session: str) -> set[str]:
    covered: set[str] = set()
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") != session:
            continue
        if data.get("status") in ("ran", "empty"):
            covered.update(data.get("rule_ids", []))
    return covered


def gate(archive: Chronicle, session: str, charter: dict[str, Any], trigger: str) -> Verdict:
    """Block when a HARD rule for this trigger has no attestation in this session."""
    covered = attested_rule_ids(archive, session)
    missing = tuple(
        {"id": rule["id"], "text": rule["text"], "source": rule["source"], "verify": rule["verify"]}
        for rule in charter["compiled"]
        if rule["trigger"] == trigger
        and rule["enforcement"] == "HARD"
        and rule["id"] not in covered
    )
    return Verdict(allowed=not missing, trigger=trigger, missing=missing)


# Words too common to corroborate anything. A claim whose only overlap with the
# cited line is "the" has not been corroborated.
_STOPWORDS = frozenset("""
about after all also and any are because been before being both but can cannot did
does doing done during each either else every for from had has have how into its
itself just like made make many may might more most must never new non not now off
once only other our out over own same should since some such than that the their
them then there these they this those through too under until use used using very
was were what when where which while who why will with within would your
""".split())

# How far either side of a cited line a supporting term may sit. A claim usually
# refers to a small region rather than one exact line, but not to a whole file.
POSITION_WINDOW = 3


def _salient(text: str) -> set[str]:
    """Distinctive terms, with identifiers split into their parts.

    Prose says "the widget renders" where code says `render_widget`. Comparing the
    two as whole tokens finds no overlap and reports a correct citation as drifted,
    so identifiers contribute both their whole form and their parts, and a crude
    plural stem closes the rest of the gap.
    """
    found: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        parts = [token] + re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", token)
        for part in parts:
            lowered = part.lower()
            if len(lowered) < 4 or lowered in _STOPWORDS:
                continue
            found.add(lowered)
            if lowered.endswith("s") and len(lowered) > 4:
                found.add(lowered[:-1])
    return found


def _position_support(project: Path, citation: str, claim: str) -> str | None:
    """Does the cited line actually say anything the claim is about?

    A citation that resolves proves the location exists; it does not prove the
    location is the right one. Reported positions drifting off target while still
    pointing at real lines is a documented failure of agent-produced findings, and
    it is undetectable by checking existence alone.

    Returns "corroborated", "unsupported", or None when no honest judgement is
    possible - a claim with no distinctive terms cannot be corroborated or refuted,
    and guessing either way would be worse than abstaining.
    """
    match = _FILE_CITE.match(citation)
    if not match or match.group("start") is None:
        return None
    terms = _salient(claim)
    if not terms:
        return None
    target = project / match.group("path")
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    low = max(0, start - 1 - POSITION_WINDOW)
    high = min(len(lines), end + POSITION_WINDOW)
    window = _salient(" ".join(lines[low:high]))
    return "corroborated" if terms & window else "unsupported"


def _citation_resolves(project: Path, archive: Chronicle, citation: str) -> bool:
    match = _RECORD_CITE.match(citation)
    if match:
        digest = match.group("digest")
        return any(
            record["record_hash"].startswith(digest)
            for record in archive.select(limit=2000)
        )
    match = _FILE_CITE.match(citation)
    if match:
        target = project / match.group("path")
        if not target.is_file():
            return False
        start = match.group("start")
        if start is None:
            return True
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return False
        return 1 <= int(start) <= len(lines)
    return False


def record_claim(
    archive: Chronicle,
    project: Path,
    session: str,
    text: str,
    grade: str,
    cites: list[str] | None = None,
) -> dict[str, Any]:
    """Persist a claim, downgrading it when its citations do not resolve.

    Not a warning. A claim the evidence does not support is stored as a hypothesis,
    because a claim asserted at full confidence is what a later session will trust.
    """
    if grade not in GRADES:
        raise ArchiveError(f"Unknown claim grade '{grade}'; expected one of {', '.join(GRADES)}")
    citations = cites or []
    unresolved = [
        citation for citation in citations if not _citation_resolves(project, archive, citation)
    ]
    # A citation can resolve and still point at the wrong place. Existence and
    # support are separate claims, so they are checked separately.
    unsupported = [
        citation
        for citation in citations
        if citation not in unresolved
        and _position_support(project, citation, text) == "unsupported"
    ]
    effective = grade
    reason = ""
    if grade == "verified":
        if not citations:
            effective, reason = "hypothesis", "no citation"
        elif unresolved:
            effective, reason = "hypothesis", "citation does not resolve"
        elif unsupported:
            effective, reason = "hypothesis", "cited location does not support the claim"
    record = archive.append(
        "claim",
        text[:120],
        {
            "session": session,
            "text": text,
            "claimed_grade": grade,
            "grade": effective,
            "unresolved": unresolved,
            "unsupported": unsupported,
            "downgraded": effective != grade,
            "reason": reason,
        },
        evidence=citations,
    )
    return record


_NEGATION = re.compile(
    r"\b(?:not|never|no longer|cannot|can't|doesn't|does not|isn't|is not|"
    r"won't|will not|without|disabled|removed|absent|missing|fails?)\b"
)


def reflect(archive: Chronicle, text: str, limit: int = 200) -> dict[str, Any]:
    """Check a new claim against what the record already says.

    Run as its own step rather than folded into producing the claim, for the same
    reason a review is not done by the author: the pass that generates an assertion
    is the pass least able to notice it contradicts something.

    This flags, it does not decide. Polarity disagreement between two claims about
    the same subject is a lead worth a human look, and calling it a contradiction
    outright would manufacture findings.
    """
    terms = _salient(text)
    if not terms:
        return {"checked": 0, "conflicts": [], "note": "claim has no distinctive terms to compare"}

    polarity = bool(_NEGATION.search(text.lower()))
    conflicts: list[dict[str, Any]] = []
    checked = 0
    for record in archive.select(kind="claim", limit=limit):
        data = record["data"]
        prior = str(data.get("text", ""))
        if not prior or prior == text:
            continue
        checked += 1
        overlap = terms & _salient(prior)
        # Two distinctive terms in common means the claims are about the same thing;
        # one is coincidence in prose this short.
        if len(overlap) < 2:
            continue
        if bool(_NEGATION.search(prior.lower())) != polarity:
            conflicts.append({
                "prior": prior[:160],
                "prior_grade": data.get("grade"),
                "shared_terms": sorted(overlap)[:6],
                "why": "the two claims share a subject but disagree in polarity",
            })
    return {
        "checked": checked,
        "conflicts": conflicts[:5],
        "verdict": "conflict-suspected" if conflicts else "no-conflict-found",
    }


def close_session(archive: Chronicle, session: str, charter: dict[str, Any]) -> dict[str, Any]:
    """Refuse closure while any HARD rule is unattested or any claim is unsupported."""
    covered = attested_rule_ids(archive, session)
    unattested = [
        {"id": rule["id"], "text": rule["text"], "trigger": rule["trigger"]}
        for rule in charter["compiled"]
        if rule["enforcement"] == "HARD" and rule["id"] not in covered
    ]
    downgraded = [
        {"text": record["data"]["text"], "unresolved": record["data"]["unresolved"]}
        for record in archive.select(kind="claim", limit=500)
        if record["data"].get("session") == session and record["data"].get("downgraded")
    ]
    allowed = not unattested and not downgraded
    return {
        "session": session,
        "closed": allowed,
        "unattested_hard_rules": unattested,
        "downgraded_claims": downgraded,
        "watch_for": [] if allowed else [text for text, _ in RATIONALIZATIONS],
    }


def _self_check() -> None:
    import tempfile
    from unittest import mock

    from .godmode_anchor import resolve_anchor
    from .godmode_charter import compile_charter

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            charter = compile_charter(project)
            session = open_session(archive, "self-check")

            hard = [r for r in charter["compiled"] if r["enforcement"] == "HARD"]
            assert hard, charter["enforcement"]
            trigger = hard[0]["trigger"]

            # Unattested HARD rule blocks its gate and names the rationalizations.
            blocked = gate(archive, session, charter, trigger)
            assert not blocked.allowed
            assert blocked.view()["watch_for"]

            # A skip must state a reason; a bare skip is refused outright.
            try:
                record_step(archive, session, "preflight", "skipped")
                raise AssertionError("a reasonless skip must be refused")
            except ArchiveError:
                pass

            # An attested step opens the gate. 'empty' counts: finding nothing is a finding.
            record_step(archive, session, "preflight", "empty",
                        result="no overlapping invariant", rule_ids=[hard[0]["id"]])
            assert gate(archive, session, charter, trigger).allowed

            # A claim citing nothing cannot be 'verified'.
            bare = record_claim(archive, project, session, "The retry path is disabled.", "verified")
            assert bare["data"]["grade"] == "hypothesis", bare["data"]

            # A claim whose cited line actually mentions it stays verified.
            good = record_claim(archive, project, session,
                                "Commit requires an explicit ask.", "verified",
                                cites=["file:GODMODE.md#L2"])
            assert good["data"]["grade"] == "verified", good["data"]

            # A claim whose citation resolves but points somewhere unrelated is
            # downgraded: existence is not support, and drifted positions are the
            # documented failure mode of agent-reported findings.
            (project / "rotate.py").write_text(
                "def rotate():\n    return 1\n\n\ndef unrelated():\n    return 2\n",
                encoding="utf-8",
            )
            drifted = record_claim(archive, project, session,
                                   "Retention policy expires audit rows after ninety days.",
                                   "verified", cites=["file:rotate.py#L5"])
            assert drifted["data"]["grade"] == "hypothesis", drifted["data"]
            assert drifted["data"]["unsupported"] == ["file:rotate.py#L5"], drifted["data"]
            assert "does not support" in drifted["data"]["reason"], drifted["data"]

            # And one that lands on the right line survives.
            landed = record_claim(archive, project, session,
                                  "The rotate function returns a value.", "verified",
                                  cites=["file:rotate.py#L1"])
            assert landed["data"]["grade"] == "verified", landed["data"]

            # A claim citing a missing file is downgraded and blocks closure.
            record_claim(archive, project, session, "The absent module is wired.", "verified",
                         cites=["file:nope.py#L1"])
            verdict = close_session(archive, session, charter)
            assert not verdict["closed"]
            assert verdict["downgraded_claims"]

            # A failing check cannot be attested into a pass: the runner records the
            # exit code, and 'blocked' never satisfies a gate.
            # Distinct ids, because a rule already attested earlier in this check
            # would make the coverage assertions pass for the wrong reason.
            failed_rule, passed_rule = "R-checkfail", "R-checkpass"
            failing = run_check(archive, session, project, "failing",
                                [sys.executable, "-c", "raise SystemExit(3)"],
                                rule_ids=[failed_rule])
            assert failing["exit_code"] == 3 and not failing["passed"], failing
            assert failing["attested"] == "blocked", failing
            assert failed_rule not in attested_rule_ids(archive, session), \
                "a failed check satisfied the rule it was run for"

            passing = run_check(archive, session, project, "passing",
                                [sys.executable, "-c", "print('ok')"], rule_ids=[passed_rule])
            assert passing["passed"] and passing["attested"] == "ran", passing
            assert passed_rule in attested_rule_ids(archive, session), \
                "a passing check did not satisfy its rule"

            missing = run_check(archive, session, project, "absent",
                                ["definitely-not-a-real-binary-xyz"])
            assert missing["exit_code"] == 127 and not missing["passed"], missing

            # A guard must be seen failing. A real guard goes green -> red -> green.
            (project / "value.txt").write_text("42\n", encoding="utf-8")
            real_guard = [sys.executable, "-c",
                          "import pathlib,sys; sys.exit(0 if pathlib.Path('value.txt')"
                          ".read_text().strip()=='42' else 1)"]
            proven = plant_and_observe(archive, session, project, "value", real_guard,
                                       target="value.txt", replace="42", with_text="99",
                                       rule_ids=["R-guard"])
            assert proven["observed_failing"], proven
            assert proven["sequence"]["baseline"] == 0 and proven["sequence"]["with_violation"] != 0
            assert "R-guard" in attested_rule_ids(archive, session)
            # The file is byte-identical afterwards; a plant must never leak.
            assert (project / "value.txt").read_text(encoding="utf-8") == "42\n"

            # A guard that asserts nothing stays green under the plant and is refused.
            hollow = [sys.executable, "-c", "raise SystemExit(0)"]
            weak = plant_and_observe(archive, session, project, "hollow", hollow,
                                     target="value.txt", replace="42", with_text="99",
                                     rule_ids=["R-hollow"])
            assert not weak["observed_failing"], weak
            assert "did not fail" in weak["reason"], weak
            assert "R-hollow" not in attested_rule_ids(archive, session)

            # A plant that changes nothing is refused rather than read as a pass.
            try:
                plant_and_observe(archive, session, project, "noop", real_guard,
                                  target="value.txt", replace="absent-token", with_text="x")
                raise AssertionError("a no-op plant must be refused")
            except ArchiveError as exc:
                assert "changed no bytes" in str(exc), exc

            # Reflection notices that a new claim disagrees with a recorded one.
            record_claim(archive, project, session,
                         "The rotation guard is enabled for every account.", "observed")
            echo = reflect(archive, "The rotation guard is not enabled for every account.")
            assert echo["verdict"] == "conflict-suspected", echo
            assert echo["conflicts"][0]["shared_terms"], echo

            # Agreement is not flagged, and neither is an unrelated subject.
            assert reflect(archive, "The rotation guard is enabled for every account today."
                           )["verdict"] == "no-conflict-found"
            assert reflect(archive, "Billing exports run nightly.")["verdict"] == "no-conflict-found"

    print("godmode_attest self-check OK")


if __name__ == "__main__":
    _self_check()

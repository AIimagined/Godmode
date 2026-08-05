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
    effective = grade
    if grade == "verified" and (unresolved or not citations):
        effective = "hypothesis"
    record = archive.append(
        "claim",
        text[:120],
        {
            "session": session,
            "text": text,
            "claimed_grade": grade,
            "grade": effective,
            "unresolved": unresolved,
            "downgraded": effective != grade,
        },
        evidence=citations,
    )
    return record


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

            # A claim citing a real file line stays verified.
            good = record_claim(archive, project, session, "The gate exists.", "verified",
                                cites=["file:GODMODE.md#L2"])
            assert good["data"]["grade"] == "verified", good["data"]

            # A claim citing a missing file is downgraded and blocks closure.
            record_claim(archive, project, session, "The absent module is wired.", "verified",
                         cites=["file:nope.py#L1"])
            verdict = close_session(archive, session, charter)
            assert not verdict["closed"]
            assert verdict["downgraded_claims"]

    print("godmode_attest self-check OK")


if __name__ == "__main__":
    _self_check()

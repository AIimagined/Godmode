"""Constraints this codebase credits to someone else.

R17, the correction-side twin of R11. R11 governs what a source may fund; this
governs what a source may authorise overwriting.

The failure is specific and common. A comment says a value is what it is
because an outside authority requires it. An agent reads the code, judges the
value wrong on the code's own terms, and changes it. The deviation may have
been deliberate, and the agent is the party least able to tell: it can read the
code and has almost certainly not read the authority.

This does not decide correctness, and deliberately cannot. It fires at the
moment of an edit and says: this line credits someone else, so read them before
changing what they said. An advisory rather than a refusal, because the line
may well be wrong and nothing here can know that.

**Precision over reach.** A finding needs an attribution phrase *and* a
constraint on the same line. A line that merely points at a specification is
documentation, and flagging it would make the check noise - and a noisy check
gets switched off, which is worse than not having written it.
"""
from __future__ import annotations

import re
from typing import Any

#: Crediting a statement to an outside authority. `per` is deliberately
#: narrow: "one advisory per file" is not an attribution, so the word must be
#: followed by something that names an authority rather than a unit.
_ATTRIBUTION = re.compile(
    r"(?i)"
    r"\bper\s+(?:the\s+)?(?:RFC\s*\d+|[A-Z][\w.-]*\s+(?:spec|specification|standard|docs|"
    r"documentation|manual|guide|reference))\b"
    r"|\baccording to\s+(?:the\s+)?\w+"
    r"|\bas\s+(?:required|specified|documented|defined|mandated)\s+by\b"
    r"|\b(?:upstream|the\s+vendor|the\s+platform|the\s+provider|the\s+API|the\s+protocol)"
    r"\s+(?:requires?|mandates?|specifies?|says?|states?|documents?|expects?)\b"
    r"|\bthe\s+[\w.-]+\s+(?:docs|documentation|spec|specification|manual|standard)\s+"
    r"(?:requires?|mandates?|specifies?|says?|states?)\b"
    r"|\bRFC\s*\d+\s+(?:requires?|mandates?|specifies?|says?|states?)\b"
    # Possessive attribution: "Grok's own docs", "Codex's build doc". This is
    # how this codebase actually credits host vendors, and the host manifest
    # module is where an agent is most likely to "correct" a value that a
    # vendor's documentation, not our judgement, put there.
    r"|\b[A-Z][\w.-]*['’]s\s+(?:own\s+)?(?:docs?|documentation|spec|specification|"
    r"manual|guide|build\s+doc|reference)\b"
)

#: A constraint the attribution is about. Without one, the line is a pointer to
#: reading material rather than a rule someone else owns.
_CONSTRAINT = re.compile(
    r"(?i)\b(?:must|shall|requires?|required|mandates?|may\s+not|cannot|"
    r"maximum|minimum|at\s+most|at\s+least|ceiling|floor|limit|"
    r"lowercase|uppercase|exactly)\b"
    r"|\b\d+\s*(?:seconds?|ms|milliseconds?|bytes?|items?|chars?|characters?|"
    r"entries|rows|calls?)\b"
)

REMEDY = (
    "Read the authority this line credits before changing what it says. The "
    "difference from what the code would otherwise do may be deliberate, and "
    "the source is the only place that settles it. If the attribution is stale, "
    "say so in the same edit."
)


#: How many following lines may complete an attribution. Prose wraps: this
#: codebase routinely credits a host vendor on one line and states what that
#: vendor requires on the next, and a strictly per-line scan found nothing at
#: all across the runtime - measured, not assumed. Bounded at three because an
#: unbounded window joins unrelated statements and manufactures findings.
_WRAP_WINDOW = 3


def attributed_constraints(path: str, text: str) -> list[dict[str, Any]]:
    """Passages crediting an outside authority with a constraint.

    The attribution must appear on the reported line; the constraint may fall
    within the next few lines, because prose wraps. A blank line ends the
    window: separate paragraphs are separate statements, and joining them is
    how a detector starts inventing findings.

    One finding per attributing line. The shape matches what the post-edit hook
    already renders for the documentation and swallow checks, so it needs no
    special handling there.
    """
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, 1):
        if not _ATTRIBUTION.search(line):
            continue
        window = [line]
        for offset in range(index, min(index + _WRAP_WINDOW, len(lines))):
            following = lines[offset]
            if not following.strip():
                break
            window.append(following)
        if not _CONSTRAINT.search(" ".join(window)):
            continue
        findings.append({
            "path": path,
            "line": index,
            "check": "attributed-constraint",
            "severity": "advisory",
            "why": "this line credits an outside authority with a constraint; "
                   "the deviation it describes may be deliberate",
            "remedy": REMEDY,
            "excerpt": line.strip()[:160],
        })
    return findings

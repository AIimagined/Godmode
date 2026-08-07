"""Obligations that outlived the reason they were recorded.

The continuity machinery here is good at "do not forget X" and had nothing for
"stop repeating X, it is done". Both are continuity failures and only one was
implemented, so a next-action recorded validly and made moot by a later event
was restated in every handover until a human noticed it.

The case that produced this module: "publish the v0.2.2 release page", recorded
when v0.2.2 was the newest release, carried through three more handovers after
v0.2.3 and v0.2.4 had superseded it, and retired only when the owner asked why
it was still there. Nothing had invalidated it, because nothing could.

Two signals, deliberately dull:

* **carried-unchanged** - restated across three or more handovers with no
  change. It needs no understanding of the text at all, and it is the signal
  that would have caught the case above.
* **version-superseded** - the same standing obligation recorded later about a
  higher version, which makes the earlier one an obligation about a release
  nobody will install.

Findings, never closures. Auto-retiring would be the mirror mistake: the fix
for carrying something too long must not become dropping it too early. Each
finding is phrased as the question a reader should answer.
"""

from __future__ import annotations

import re
from typing import Any

# Three handovers, not two. Two is a task still in progress; the signal is
# persistence across a third, by which point nothing about it has moved.
CARRIED_THRESHOLD = 3

_VERSION = re.compile(r"\bv?(\d+(?:\.\d+){1,3})\b")
_NOISE = re.compile(r"[^a-z0-9\s]")
# The separator is optional: "Owner: update the plugin" and "owner update the
# plugin" are one obligation labelled two ways, and treating them as two would
# reset the count that is the whole signal.
_LEADING_ROLE = re.compile(r"(?i)^\s*(?:owner|build queue|next|todo)\s*[:\-]?\s+")


def normalise_obligation(text: str) -> str:
    """The standing obligation, with the particulars stripped out.

    Versions are removed rather than kept: "publish the v0.2.2 page" and
    "publish the v0.2.5 page" are one standing obligation about two releases,
    and recognising that is precisely what makes the earlier one retirable.
    """
    reduced = _LEADING_ROLE.sub("", text.strip().lower())
    reduced = _VERSION.sub(" ", reduced)
    reduced = _NOISE.sub(" ", reduced)
    return " ".join(reduced.split())


# A semicolon joins two obligations. Treating "update the plugin; publish the
# page" as one string meant neither half could ever be recognised as repeated,
# which is why the first version of this module found nothing in the archive
# it was written from.
_COMPOUND = re.compile(r"\s*[;]\s*|\s+-\s+")

# Wording drifts while the obligation stays the same: "publish the release
# page only" and "publish the release page (skip the older ones)" are one
# standing item. Exact matching after normalisation could not see that, so
# obligations are grouped by overlap instead. The threshold is deliberately
# high - a false grouping invents a stale obligation, which is worse than
# missing one, because it teaches the reader to distrust the report.
SIMILARITY = 0.6
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "and", "or", "of", "for", "in", "on", "at", "is",
    "it", "this", "that", "then", "only", "also", "with", "from", "by", "be",
})


def _tokens(normalised: str) -> frozenset[str]:
    return frozenset(word for word in normalised.split() if word not in _STOPWORDS)


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    """Jaccard similarity: shared tokens over all tokens seen in either."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def split_obligations(text: str) -> list[str]:
    """One recorded line may carry several obligations."""
    return [part.strip() for part in _COMPOUND.split(text) if part.strip()]


def _versions(text: str) -> list[tuple[int, ...]]:
    parsed: list[tuple[int, ...]] = []
    for raw in _VERSION.findall(text):
        try:
            parsed.append(tuple(int(part) for part in raw.split(".")))
        except ValueError:
            continue
    return parsed


def _highest(text: str) -> tuple[int, ...] | None:
    found = _versions(text)
    return max(found) if found else None


def review_obligations(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Report obligations a later handover may have made moot.

    `records` are checkpoint records oldest first, as the archive stores them.
    """
    # Greedy clustering by overlap, first match wins. Enough for a few dozen
    # obligations, and it keeps the grouping explainable: every member of a
    # cluster shares most of its words with the one that opened it.
    clusters: list[tuple[frozenset[str], list[tuple[int, str]]]] = []
    handovers = 0
    total = 0
    for record in records:
        obligations = (record.get("data") or {}).get("next") or []
        if not isinstance(obligations, list):
            continue
        handovers += 1
        sequence = int(record.get("sequence", 0))
        for obligation in obligations:
            for part in split_obligations(str(obligation)):
                tokens = _tokens(normalise_obligation(part))
                if not tokens:
                    continue
                total += 1
                for existing, members in clusters:
                    if _overlap(existing, tokens) >= SIMILARITY:
                        members.append((sequence, part))
                        break
                else:
                    clusters.append((tokens, [(sequence, part)]))

    findings: list[dict[str, Any]] = []
    for _tokenset, occurrences in clusters:
        sequences = [sequence for sequence, _ in occurrences]

        if len(occurrences) >= CARRIED_THRESHOLD:
            findings.append({
                "code": "carried-unchanged",
                "obligation": occurrences[-1][1],
                "carried": len(occurrences),
                "first_seen": min(sequences),
                "last_seen": max(sequences),
                "detail": f"restated in {len(occurrences)} handovers without changing",
                "question": "is this still worth doing, or was it overtaken?",
            })

        # The same standing obligation recorded later about a higher version
        # leaves the earlier one pointing at a release nobody will install.
        newest = max((v for _, text in occurrences
                      for v in [_highest(text)] if v is not None), default=None)
        if newest is None:
            continue
        # One finding per distinct obligation, at its earliest sighting. The
        # same wording recorded in several handovers is one thing to decide
        # about, and repeating it makes the report look busier than the
        # backlog actually is.
        reported: set[str] = set()
        for sequence, text in sorted(occurrences):
            current = _highest(text)
            if current is None or current >= newest or text in reported:
                continue
            reported.add(text)
            findings.append({
                "code": "version-superseded",
                "obligation": text,
                "carried": len(occurrences),
                "first_seen": sequence,
                "last_seen": max(sequences),
                "detail": "the same obligation was later recorded for "
                          + ".".join(str(part) for part in newest),
                "question": "does anything still need this older release, "
                            "or does the newer one cover it?",
            })

    findings.sort(key=lambda f: (-f["carried"], f["obligation"]))
    return {
        "handovers_examined": handovers,
        "obligations_seen": total,
        "findings": findings,
        # Stated so an empty report cannot be read as "nothing was examined".
        "verdict": "no-stale-obligations" if not findings else "review-required",
    }


def _self_check() -> None:
    records = [
        {"sequence": 1, "data": {"next": ["Owner: publish the v0.2.2 Release page",
                                          "Owner: update the plugin and re-test"]}},
        {"sequence": 2, "data": {"next": ["Owner: publish the v0.2.4 Release page",
                                          "Owner: update the plugin and re-test"]}},
        {"sequence": 3, "data": {"next": ["Owner: publish the v0.2.5 Release page",
                                          "Owner: update the plugin and re-test"]}},
    ]
    report = review_obligations(records)
    codes = {finding["code"] for finding in report["findings"]}
    assert "carried-unchanged" in codes, report
    assert "version-superseded" in codes, report
    superseded = [f["obligation"] for f in report["findings"]
                  if f["code"] == "version-superseded"]
    assert any("v0.2.2" in text for text in superseded), superseded
    assert not any("v0.2.5" in text for text in superseded), superseded
    assert all("question" in finding for finding in report["findings"]), report

    clean = review_obligations([{"sequence": 1, "data": {"next": ["one"]}},
                                {"sequence": 2, "data": {"next": ["two"]}}])
    assert clean["verdict"] == "no-stale-obligations", clean

    print("godmode_obligations self-check OK")

"""Which tags have no release, computed rather than remembered.

An agent stated which releases were published from seventeen-hour-old recall,
while holding working API access it had used minutes earlier for something
else. The external-claim detector exists and would have graded that assertion,
but it is reachable only through `record_claim` - so it never sees anything
said rather than recorded. This runtime governs what is written down, not what
is said, and no widening of a detector changes that: it would still depend on
the agent routing its own sentence through a check, which is the failure rather
than the fix.

So the fact is made computable instead. A handover saying "one tag is
unpublished" should be reading that, not recalling it.

**No network here.** Comparison is a pure function over two lists; the caller
supplies whatever it fetched, and this module has no opinion about how. That
keeps the deciding half offline, testable, and consistent with a runtime that
does not reach out on its own.
"""

from __future__ import annotations

from typing import Any


def _version_key(tag: str) -> tuple[int, ...]:
    """Order by version, not by string: v0.2.10 follows v0.2.9."""
    parts: list[int] = []
    for chunk in tag.lstrip("vV").split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def compare_releases(
    tags: list[str] | None, published: list[str] | None
) -> dict[str, Any]:
    """Tags without a release, and releases whose tag has gone.

    `published` of None means the release list could not be read. That is
    reported as insufficient data rather than as an empty list, because
    "nothing is published" and "nobody could tell" are different facts and
    collapsing them is the false certainty this exists to remove.
    """
    tag_list = sorted(set(tags or []), key=_version_key)

    if published is None:
        return {
            "tags_examined": len(tag_list),
            "releases_examined": None,
            "newest_tag": tag_list[-1] if tag_list else None,
            "unpublished": None,
            "published_without_tag": None,
            "verdict": "insufficient-data",
            "reason": "the published releases could not be read; "
                      "no conclusion about what is unpublished follows",
        }

    release_list = sorted(set(published), key=_version_key)
    unpublished = [tag for tag in tag_list if tag not in set(release_list)]
    # A release whose tag has gone is a broken download, and only the
    # comparison can see it.
    orphaned = [name for name in release_list if name not in set(tag_list)]

    if not tag_list:
        verdict = "no-tags"
    elif unpublished:
        verdict = "unpublished-tags"
    else:
        verdict = "all-tags-published"

    return {
        "tags_examined": len(tag_list),
        "releases_examined": len(release_list),
        "newest_tag": tag_list[-1] if tag_list else None,
        "unpublished": unpublished,
        "published_without_tag": orphaned,
        "verdict": verdict,
    }


def render(report: dict[str, Any]) -> str:
    """One line a handover can carry instead of a remembered claim."""
    if report["verdict"] == "insufficient-data":
        return "release state unknown: " + str(report.get("reason", ""))
    if report["verdict"] == "no-tags":
        return "no tags exist, so nothing is awaiting a release."
    if not report["unpublished"]:
        return f"every tag through {report['newest_tag']} has a published release."
    listed = ", ".join(report["unpublished"])
    return f"tagged but not published: {listed}."


def _self_check() -> None:
    report = compare_releases(["v0.2.9", "v0.2.10"], ["v0.2.9"])
    assert report["unpublished"] == ["v0.2.10"], report
    assert report["newest_tag"] == "v0.2.10", report
    assert "v0.2.10" in render(report), render(report)

    clean = compare_releases(["v0.2.5"], ["v0.2.5"])
    assert clean["verdict"] == "all-tags-published", clean

    unknown = compare_releases(["v0.2.6"], None)
    assert unknown["verdict"] == "insufficient-data", unknown
    assert unknown["unpublished"] is None, unknown

    orphan = compare_releases(["v0.2.5"], ["v0.2.5", "v9.9.9"])
    assert orphan["published_without_tag"] == ["v9.9.9"], orphan

    print("godmode_release self-check OK")

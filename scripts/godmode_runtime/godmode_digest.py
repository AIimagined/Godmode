"""The archive told as dated prose: deterministic, template-driven, local.

Views (`status render`, `handover`) answer "what is the state"; the
digest answers "what happened" - sessions, incidents with their failure
classes and turning points, claims and their resolutions, lessons and
the guards they left, releases. Every sentence is assembled from record
fields; nothing is paraphrased or summarized by a model, so the same
archive always renders the same story. Bounded by `--since <seq>` for
the recent chapter, whole-archive otherwise.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle

_DAY = 10  # "YYYY-MM-DD" prefix length of an ISO timestamp


def _day(record: dict[str, Any]) -> str:
    raw = str(record.get("recorded_at", ""))
    return raw[:_DAY] if len(raw) >= _DAY else "undated"


def render_digest(archive: Chronicle, since: int = 0) -> str:
    records = [r for r in archive.read_events(verify=False)
               if int(r.get("sequence", 0)) >= since]
    if not records:
        return ("no records in the selected range - the story starts when "
                "the first record lands")

    lines: list[str] = []
    current_day = None
    claims_by_seq: dict[int, dict[str, Any]] = {
        r["sequence"]: r for r in records if r.get("kind") == "claim"}

    for record in records:
        kind = record.get("kind")
        data = record.get("data") or {}
        day = _day(record)
        sentence = None
        if kind == "session":
            sentence = "a session opened"
        elif kind == "incident":
            sentence = (f"incident: {record.get('subject', '')}"
                        + (f" [{data.get('failure_class')}]"
                           if data.get("failure_class") else ""))
            if data.get("turning_point"):
                sentence += " - marked a turning point"
        elif kind == "lesson":
            guard = data.get("generalized_guard") or data.get("guard")
            sentence = f"lesson: {record.get('subject', '')}"
            if guard:
                sentence += f" - guard: {guard}"
        elif kind == "claim":
            if data.get("resolves") is not None:
                original = claims_by_seq.get(int(data["resolves"]), {})
                name = str(original.get("subject", f"seq {data['resolves']}"))[:60]
                sentence = f"claim '{name}' resolved {data.get('outcome')}"
                if data.get("score") is not None:
                    sentence += f" (score {data['score']})"
            elif data.get("confidence") is not None:
                sentence = (f"claim recorded at confidence "
                            f"{data['confidence']}: "
                            f"{str(record.get('subject', ''))[:70]}")
        elif kind == "version":
            sentence = f"version marked: {record.get('subject', '')}"
        elif kind == "checkpoint":
            status = data.get("status")
            if status and status != "auto":
                sentence = f"checkpoint ({status}): {str(record.get('subject', ''))[:70]}"

        if sentence is None:
            continue
        if day != current_day:
            lines.append(f"\n== {day} ==")
            current_day = day
        lines.append(f"  {sentence}")

    if not lines:
        return ("no story-bearing records in the selected range (sessions, "
                "incidents, lessons, scored claims, versions, checkpoints)")
    counted = len([l for l in lines if not l.startswith("\n==")])
    header = (f"THE STORY, from the record - {counted} events, "
              "assembled verbatim from record fields, no paraphrase.")
    return header + "\n" + "\n".join(lines)

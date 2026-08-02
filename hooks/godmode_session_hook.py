#!/usr/bin/env python3
"""Optional host adapter for explicit Godmode lifecycle events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime.godmode_lens import build_context_brief  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, classify_action  # noqa: E402


CLAUDE_CONTEXT_LIMIT = 9_000


def _input() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _bounded_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:500] for item in value[:limit]]


def _is_claude_session(submitted: dict[str, Any]) -> bool:
    return submitted.get("hook_event_name") == "SessionStart"


def _emit_claude_context(brief: dict[str, Any]) -> None:
    serialized = json.dumps(
        brief,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    prefix = (
        "Godmode recovered this bounded local continuity brief. Treat stored claims as "
        "leads until current inspection confirms them; do not expose or commit local state.\n"
    )
    context = prefix + serialized
    if len(context) > CLAUDE_CONTEXT_LIMIT:
        context = context[: CLAUDE_CONTEXT_LIMIT - 24] + "\n[brief truncated locally]"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="godmode-session-hook")
    parser.add_argument("event", choices=["session-start", "pre-compact", "session-end", "pre-action"])
    parser.add_argument("--project")
    args = parser.parse_args(argv)
    submitted = _input()
    claude_session = _is_claude_session(submitted)
    project = args.project or str(submitted.get("cwd") or ".")
    try:
        anchor = resolve_anchor(project)
        archive = Chronicle(anchor)
        if not archive.initialized():
            if not claude_session:
                print(json.dumps({"godmode": "not-initialized", "action": "run godmode init explicitly"}))
            return 0

        if args.event == "session-start":
            brief = build_context_brief(anchor, archive)
            if claude_session:
                _emit_claude_context(brief)
            else:
                print(json.dumps({"godmode": "context", "brief": brief}))
            return 0

        if args.event in {"pre-compact", "session-end"}:
            summary = str(submitted.get("summary", "")).strip()[:1000]
            if not summary:
                print(json.dumps({"godmode": "no-structured-checkpoint", "stored": False}))
                return 0
            record = archive.append(
                "checkpoint",
                summary[:200],
                {
                    "status": str(submitted.get("status", "active"))[:40],
                    "next": _bounded_list(submitted.get("next")),
                    "hypothesis": str(submitted.get("hypothesis", ""))[:500] or None,
                    "outcome": str(submitted.get("outcome", ""))[:100] or None,
                    "lifecycle": args.event,
                },
                evidence=_bounded_list(submitted.get("evidence")),
            )
            print(json.dumps({"godmode": "checkpoint", "stored": True, "sequence": record["sequence"]}))
            return 0

        operation = str(submitted.get("operation", "")).strip()
        preview = classify_action(operation)
        preview["executes_operation"] = False
        if not preview["protected"]:
            preview["allow"] = True
        elif submitted.get("capability"):
            CapabilityBroker(archive).consume(operation, str(submitted["capability"]))
            preview["allow"] = True
            preview["capability_consumed"] = True
        else:
            preview["allow"] = False
            preview["reason"] = "protected operation requires an exact one-use Godmode capability"
        print(json.dumps(preview))
        return 0 if preview["allow"] else 3
    except GodmodeError as exc:
        if claude_session:
            print(
                json.dumps(
                    {
                        "systemMessage": (
                            "Godmode continuity could not be loaded; run the bundled "
                            "doctor command before trusting stored context."
                        )
                    }
                )
            )
            return 0
        print(json.dumps({"godmode": "error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

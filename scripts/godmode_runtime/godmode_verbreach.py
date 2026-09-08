"""Verb reach: what names each console verb, so the census counts the unit
that matters (obligation 10121).

Measured by hand on 2026-09-08: 120 verbs; a shipped skill named 5, a hook
nudge 26, docs only 34, nothing 57. The utilization census counts record
kinds and was green over that gap. A verb nothing names is reachable on
every host and fires on none, because the model has no reason to run it.

Tiers, from the controlled skill study in the research ledger (skills work
as procedural anchors at the moment of demand; a reference index is not
one): `skill` means a SKILL.md body names the verb; `nudge` means a hook
or a stop/next-action emitter names it; `docs` means only documentation
or a skill's reference file does. Skill or nudge is a demand path; docs
alone is not.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any

# Ratchets: the counts may fall, never rise. Lower them when verbs gain a
# demand path; a test holds the line.
# 2026-09-09: measured 120 verbs, 0 unnamed, 0 without a skill line or a
# nudge, after the "Verbs at the moment of demand" sections were written
# into the specialist skills. A new verb must arrive with its demand path.
UNNAMED_VERB_CEILING = 0
UNDEMANDED_VERB_CEILING = 0

_SKILL_GLOB = "skills/*/SKILL.md"
_NUDGE_FILES = (
    "hooks/godmode_session_hook.py",
    "hooks/godmode_post_edit.py",
    "hooks/godmode_gate_fast.py",
    "scripts/godmode_runtime/godmode_stop.py",
    "scripts/godmode_runtime/godmode_metrics.py",
    "scripts/godmode_runtime/godmode_requests.py",
    # The prompt-shape and failure nudges, and the claim-time advisories,
    # name verbs at the moment of demand too.
    "scripts/godmode_runtime/godmode_precheck.py",
    "scripts/godmode_runtime/godmode_attest.py",
)
_DOC_GLOBS = ("docs/**/*.md", "README.md", "skills/*/references/*.md")


def parser_verbs(parser: argparse.ArgumentParser) -> list[str]:
    """Every top-level subcommand the given parser registers."""
    names: set[str] = set()
    for action in parser._actions:  # noqa: SLF001 - argparse keeps no public list
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            names.update(action.choices)
    return sorted(names)


def console_verbs() -> list[str]:
    """The CLI's own registry, read at call time. The console imports this
    module (through the census), so the parser is fetched by name here
    rather than imported at module level: a runtime read, not an import
    edge, and the console passes its verbs in whenever it calls."""
    import importlib

    console = importlib.import_module("godmode_runtime.godmode_console")
    return parser_verbs(console._build_parser())  # noqa: SLF001


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _names(text: str, verb: str) -> bool:
    # `godmode <verb>` in prose or code, or the verb as a backticked token.
    pattern = re.compile(r"godmode(?:\.py)?(?: --project \S+)? " + re.escape(verb) + r"(?![\w-])")
    if pattern.search(text):
        return True
    return f"`{verb}`" in text


_PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def verb_reach(project: Path | None = None,
               verbs: list[str] | None = None) -> dict[str, Any]:
    # A property of the plugin, not of the governed project: the skills,
    # hooks and docs scanned are the ones this install ships.
    root = Path(project) if project is not None else _PLUGIN_ROOT
    names = list(verbs) if verbs is not None else console_verbs()
    skill_text = "\n".join(_read(p) for p in root.glob(_SKILL_GLOB))
    nudge_text = "\n".join(_read(root / rel) for rel in _NUDGE_FILES)
    doc_text = "\n".join(_read(p) for g in _DOC_GLOBS for p in root.glob(g))
    verbs = []
    for verb in names:
        entry = {
            "verb": verb,
            "skill": _names(skill_text, verb),
            "nudge": _names(nudge_text, verb),
            "docs": _names(doc_text, verb),
        }
        verbs.append(entry)
    unnamed = [v["verb"] for v in verbs if not (v["skill"] or v["nudge"] or v["docs"])]
    undemanded = [v["verb"] for v in verbs if not (v["skill"] or v["nudge"])]
    return {
        "verbs": verbs,
        "unnamed": unnamed,
        "undemanded": undemanded,
        "counts": {
            "total": len(verbs),
            "skill": sum(1 for v in verbs if v["skill"]),
            "nudge": sum(1 for v in verbs if v["nudge"]),
            "docs_only": sum(1 for v in verbs if v["docs"] and not (v["skill"] or v["nudge"])),
            "unnamed": len(unnamed),
            "undemanded": len(undemanded),
        },
        "ceilings": {"unnamed": UNNAMED_VERB_CEILING, "undemanded": UNDEMANDED_VERB_CEILING},
    }


def doctor_metric(project: Path | None = None,
                  verbs: list[str] | None = None) -> dict[str, Any]:
    report = verb_reach(project, verbs)
    return {
        "total": report["counts"]["total"],
        "unnamed": report["counts"]["unnamed"],
        "undemanded": report["counts"]["undemanded"],
        "ceiling": UNNAMED_VERB_CEILING,
        "undemanded_ceiling": UNDEMANDED_VERB_CEILING,
        "over_ceiling": (report["counts"]["unnamed"] > UNNAMED_VERB_CEILING
                         or report["counts"]["undemanded"] > UNDEMANDED_VERB_CEILING),
    }

"""Feed the classifiers garbage and require them to fail closed.

Every gate in this runtime decides from a string somebody else wrote: an
operation description, a path, a citation, a migration, a config file. Unit
tests exercise the inputs the author imagined. This exercises the ones they did
not - unicode, nulls, separators, quotes, comment markers, encodings, lengths -
and asserts the properties that must hold for ANY input rather than for the
handful chosen:

* a classifier never raises, and anything it does not recognise is protected;
* a path check never reads outside the project root;
* an unresolvable citation never earns a verified grade;
* a config reader degrades to defaults or a typed error, never a stray
  TypeError escaping to the caller.

Every run is seeded and the seed travels with each finding, so a failure is
replayed rather than hunted: same seed, same case index, same input.
"""

from __future__ import annotations

import hashlib
import json
import random
import string
import tempfile
from pathlib import Path
from typing import Any, Callable

from .godmode_anchor import resolve_anchor
from .godmode_chronicle import Chronicle
from .godmode_dbmgr import migration_review
from .godmode_egress import _contained
from .godmode_errors import GodmodeError
from .godmode_sentinel import classify_action

FAMILIES: tuple[str, ...] = ("command", "path", "sql", "citation", "config")

# Fragments chosen because each has broken a parser somewhere in the wild.
_NASTY: tuple[str, ...] = (
    "", " ", chr(9), chr(10), chr(13) + chr(10), chr(0), chr(27) + "[31m",
    chr(0x202E), chr(0xFEFF), chr(0x200B), chr(11), chr(12),
    "'", '"', "`", "\\", "$(", "${", ";", "|", "&&", ">", "<", "*", "?",
    "..", "../", "..\\", "/", "\\\\", "//", "%2e%2e%2f", "%00", "~",
    "--", "/*", "*/", "#", "  ", chr(0x1F600), chr(0x01C5), chr(0x0130),
    "A" * 300, "0" * 64,
)

_MUTATION_VERBS: tuple[str, ...] = (
    "rm", "delete", "drop", "push", "force", "reset", "clean", "truncate",
    "chmod", "mv", "rmdir", "-D",
)

_SAFE_STEMS: tuple[str, ...] = (
    "git status", "git log", "git diff", "ls", "cat", "grep", "git show",
)

_MUTATING_STEMS: tuple[str, ...] = (
    "git push", "git reset --hard", "rm -rf", "git branch -D", "git clean -f",
    "DROP TABLE users", "git push --force",
)

_CONFIG_FILES: tuple[str, ...] = (
    ".godmode-roles.json", ".godmode-rca.json", ".godmode-docs.json",
    ".godmode-ceilings.json", ".godmode-experiment.json",
    ".godmode-dependency-policy.json", ".godmode-privacy.json",
    ".godmode-loop.json",
)


def _finding(family: str, case: int, seed: int, given: str,
             broke: str, severity: str) -> dict[str, Any]:
    return {
        "family": family, "case": case, "seed": seed,
        "input": repr(given)[:200], "invariant": broke, "severity": severity,
    }


def _garbage(rng: random.Random, base: str = "") -> str:
    parts = [base] if base else []
    for _ in range(rng.randint(1, 4)):
        if rng.random() < 0.7:
            parts.append(rng.choice(_NASTY))
        else:
            parts.append("".join(rng.choice(string.printable[:94])
                                 for _ in range(rng.randint(1, 12))))
    rng.shuffle(parts)
    return "".join(parts)


def _fuzz_command(rng: random.Random, seed: int, iterations: int,
                  project: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for case in range(iterations):
        mutating = rng.random() < 0.5
        stem = rng.choice(_MUTATING_STEMS if mutating else _SAFE_STEMS)
        operation = _garbage(rng, stem) if rng.random() < 0.6 else stem
        try:
            verdict = classify_action(operation)
        except GodmodeError:
            continue  # A typed refusal is a correct answer, not a crash.
        except Exception as exc:  # noqa: BLE001 - any other escape is the finding
            findings.append(_finding("command", case, seed, operation,
                                     f"raised {exc.__class__.__name__}", "critical"))
            continue
        if not isinstance(verdict, dict) or "protected" not in verdict:
            findings.append(_finding("command", case, seed, operation,
                                     "verdict missing the protected decision", "critical"))
            continue
        lowered = operation.lower()
        if not verdict["protected"] and any(v in lowered for v in _MUTATION_VERBS):
            findings.append(_finding(
                "command", case, seed, operation,
                "classified read-only while naming a mutation verb", "critical"))
    return findings


def _fuzz_path(rng: random.Random, seed: int, iterations: int,
               project: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    root = project.resolve()
    for case in range(iterations):
        candidate = _garbage(rng, rng.choice(["", "../", "/etc/", "..\\", "src/"]))
        try:
            resolved = _contained(project, candidate)
        except Exception as exc:  # noqa: BLE001
            findings.append(_finding("path", case, seed, candidate,
                                     f"raised {exc.__class__.__name__}", "high"))
            continue
        if resolved is None:
            continue
        try:
            inside = Path(resolved).resolve().is_relative_to(root)
        except (OSError, ValueError):
            inside = False
        if not inside:
            findings.append(_finding(
                "path", case, seed, candidate,
                "accepted a path resolving outside the project root", "critical"))
    return findings


def _fuzz_sql(rng: random.Random, seed: int, iterations: int,
              project: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for case in range(iterations):
        shape = rng.choice([
            "DELETE FROM orders", "UPDATE orders SET total = 0",
            "DROP TABLE orders", "CREATE TABLE orders (id INT)",
            "ALTER TABLE orders DROP COLUMN total",
        ])
        statement = shape + (_garbage(rng) if rng.random() < 0.5 else "")
        try:
            review = migration_review(statement)
        except Exception as exc:  # noqa: BLE001
            findings.append(_finding("sql", case, seed, statement,
                                     f"raised {exc.__class__.__name__}", "critical"))
            continue
        kinds = {f.get("check") for f in review.get("findings", [])}
        upper = statement.upper()
        unguarded = ("WHERE" not in upper
                     and any(verb in upper for verb in ("DELETE FROM", "UPDATE ")))
        if unguarded and not ({"delete-without-where", "update-without-where"} & kinds):
            findings.append(_finding(
                "sql", case, seed, statement,
                "unbounded DELETE/UPDATE not flagged", "high"))
        if "DROP " in upper and "-- rollback:" not in statement.lower():
            if "drop-without-rollback" not in kinds:
                findings.append(_finding(
                    "sql", case, seed, statement,
                    "DROP without a rollback note not flagged", "high"))
    return findings


def _fuzz_citation(rng: random.Random, seed: int, iterations: int,
                   project: Path) -> list[dict[str, Any]]:
    from .godmode_attest import open_session, record_claim

    findings: list[dict[str, Any]] = []
    archive = Chronicle(resolve_anchor(project))
    archive.initialize()
    session = open_session(archive, "fuzz")
    for case in range(iterations):
        citation = _garbage(rng, rng.choice(["file:", "rec:", "cmd:", "doc:", ""]))
        try:
            record = record_claim(archive, project, session,
                                  f"case {case} holds", "verified", cites=[citation])
        except GodmodeError:
            continue
        except Exception as exc:  # noqa: BLE001
            findings.append(_finding("citation", case, seed, citation,
                                     f"raised {exc.__class__.__name__}", "critical"))
            continue
        if record["data"]["grade"] == "verified":
            findings.append(_finding(
                "citation", case, seed, citation,
                "unresolvable citation earned a verified grade", "critical"))
    return findings


def _fuzz_config(rng: random.Random, seed: int, iterations: int,
                 project: Path) -> list[dict[str, Any]]:
    from .godmode_corpus import resolve_roles
    from .godmode_guardrails import declared_ceilings
    from .godmode_loop import repeat_threshold
    from .godmode_method import configured_spines
    from .godmode_reconcile import doc_triggers

    readers: tuple[tuple[str, Callable[[Path], Any]], ...] = (
        (".godmode-roles.json", resolve_roles),
        (".godmode-ceilings.json", declared_ceilings),
        (".godmode-loop.json", repeat_threshold),
        (".godmode-rca.json", configured_spines),
        (".godmode-docs.json", doc_triggers),
    )
    findings: list[dict[str, Any]] = []
    for case in range(iterations):
        name, reader = readers[case % len(readers)]
        body = rng.choice([
            _garbage(rng), "{", "[]", "null", "0",
            json.dumps({"roles": _garbage(rng)}),
            json.dumps({"spines": [None, 1]}),
            json.dumps({"repeat_threshold": _garbage(rng)}),
            json.dumps({"triggers": _garbage(rng)}),
        ])
        target = project / name
        try:
            target.write_text(body, encoding="utf-8")
        except OSError:
            continue
        try:
            reader(project)
        except GodmodeError:
            pass  # A typed refusal is the contract.
        except Exception as exc:  # noqa: BLE001
            findings.append(_finding("config", case, seed, f"{name}={body}",
                                     f"raised {exc.__class__.__name__}", "high"))
        finally:
            target.unlink(missing_ok=True)
    return findings


_RUNNERS: dict[str, Callable[[random.Random, int, int, Path], list[dict[str, Any]]]] = {
    "command": _fuzz_command,
    "path": _fuzz_path,
    "sql": _fuzz_sql,
    "citation": _fuzz_citation,
    "config": _fuzz_config,
}


def fuzz(seed: int = 0, iterations: int = 200,
         families: tuple[str, ...] | None = None,
         project: Path | None = None) -> dict[str, Any]:
    """Run the seeded families and report every invariant that broke."""
    chosen = tuple(families or FAMILIES)
    unknown = [name for name in chosen if name not in _RUNNERS]
    if unknown:
        raise GodmodeError(f"Unknown fuzz families: {', '.join(unknown)}")

    per_family = max(1, iterations // len(chosen))
    results: dict[str, Any] = {}
    digest = hashlib.sha256()

    with tempfile.TemporaryDirectory() as raw:
        base = Path(project) if project else Path(raw) / "project"
        base.mkdir(parents=True, exist_ok=True)
        (base / "src").mkdir(exist_ok=True)
        (base / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
        for name in chosen:
            # One generator per family, derived from the run seed: adding a
            # family cannot shift the inputs another family sees.
            rng = random.Random(f"{seed}:{name}")
            findings = _RUNNERS[name](rng, seed, per_family, base)
            digest.update(f"{name}:{len(findings)}:{rng.random()}".encode("utf-8"))
            results[name] = {"cases": per_family, "findings": findings}

    all_findings = [f for family in results.values() for f in family["findings"]]
    critical = [f for f in all_findings if f["severity"] == "critical"]
    return {
        "seed": seed,
        "iterations": per_family * len(chosen),
        "families": results,
        "corpus_digest": digest.hexdigest()[:16],
        "critical": len(critical),
        "findings_total": len(all_findings),
        "verdict": "findings" if all_findings else "fail-closed",
        "replay": f"godmode fuzz --seed {seed} --iterations {per_family * len(chosen)}",
    }

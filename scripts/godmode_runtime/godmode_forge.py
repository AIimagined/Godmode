"""Original, deterministic project-skill authoring for Godmode."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .godmode_errors import ForgeError
from .godmode_sentinel import enforce_private_payload


_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class SkillProposal:
    name: str
    purpose: str
    gap_evidence: str
    repeated_uses: int
    positive_triggers: tuple[str, ...]
    negative_triggers: tuple[str, ...]
    assertions: tuple[str, ...]

    def validate(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ForgeError("Skill name must be lowercase hyphen-case")
        if len(self.purpose.strip()) < 20 or len(self.purpose) > 500:
            raise ForgeError("Purpose must contain 20-500 characters")
        if len(self.gap_evidence.strip()) < 30:
            raise ForgeError("A concrete capability-gap observation is required")
        if self.repeated_uses < 2:
            raise ForgeError("A new skill requires at least two observed reusable uses")
        if len(self.positive_triggers) < 2 or len(self.negative_triggers) < 2:
            raise ForgeError("Provide at least two positive and two near-negative triggers")
        if not self.assertions:
            raise ForgeError("Provide at least one observable behavior assertion")
        enforce_private_payload(
            {
                "purpose": self.purpose,
                "gap_evidence": self.gap_evidence,
                "positive": self.positive_triggers,
                "negative": self.negative_triggers,
                "assertions": self.assertions,
            }
        )
        combined = "\n".join(
            (self.purpose, self.gap_evidence, *self.positive_triggers, *self.negative_triggers)
        )
        if re.search(r"(?i)https?://", combined):
            raise ForgeError("Forge inputs must describe the capability without external source references")


def _description(proposal: SkillProposal) -> str:
    first_trigger = proposal.positive_triggers[0].strip().rstrip(".")
    description = f"{proposal.purpose.strip().rstrip('.')}. Use when {first_trigger.lower()}."
    return description[:1024]


def _skill_markdown(proposal: SkillProposal) -> str:
    description = _description(proposal)
    checks = "\n".join(f"- {assertion.strip().rstrip('.')}" for assertion in proposal.assertions)
    positives = "\n".join(f"- {trigger.strip()}" for trigger in proposal.positive_triggers)
    negatives = "\n".join(f"- {trigger.strip()}" for trigger in proposal.negative_triggers)
    return f"""---
name: {proposal.name}
description: {_yaml_string(description)}
---

# {proposal.name.replace('-', ' ').title()}

## Outcome

{proposal.purpose.strip().rstrip('.')}.

## Route

Use this skill for requests such as:

{positives}

Do not route these nearby requests here:

{negatives}

## Workflow

1. Inspect the current project and identify the concrete input and desired result.
2. State any material assumption that cannot be established from local evidence.
3. Make the smallest coherent change that satisfies the requested result.
4. Run the strongest available verification that directly proves the result.
5. Report the outcome, evidence, and any remaining limit without claiming more.

## Acceptance

{checks}

If an assertion cannot be proved, report the unmet assertion and next safe action.
"""


def _openai_yaml(proposal: SkillProposal) -> str:
    display = proposal.name.replace("-", " ").title()
    short = proposal.purpose.strip().rstrip(".")
    if len(short) > 64:
        short = short[:61].rstrip() + "..."
    if len(short) < 25:
        short = (short + " for verified project work").strip()[:64]
    return (
        "# Generated locally by Godmode.\n"
        "interface:\n"
        f"  display_name: {_yaml_string(display)}\n"
        f"  short_description: {_yaml_string(short)}\n"
        f"  default_prompt: {_yaml_string(f'Use ${proposal.name} to complete this request and prove its acceptance checks.')}\n"
    )


def _eval_payload(proposal: SkillProposal) -> dict[str, Any]:
    return {
        "schema": "godmode-skill-eval-v1",
        "skill": proposal.name,
        "routing": {
            "positive": list(proposal.positive_triggers),
            "near_negative": list(proposal.negative_triggers),
        },
        "behavior_assertions": list(proposal.assertions),
        "baseline_required": True,
        "claims_require_evidence": True,
    }


# The structured learning loop (S14-04): each phase has a named implementation,
# so "the system learns" is a pipeline you can point at, not a vibe. The
# registry is the extension point - a project may add phases, never bypass them.
LEARNING_LOOP: dict[str, str] = {
    "scanner": "godmode_attest.recurrences - counts repeated, evidenced gaps",
    "analyzer": "godmode_forge.SkillProposal.validate - routing and behavior gates",
    "writer": "godmode_forge.forge_skill - emits the skill tree from the proposal",
    "verifier": "godmode_forge.validate_skill - structural gate on the output",
}


# C-23. The hosts this plugin ships an adapter or manifest for. A fixture
# per host states what the skill is expected to produce when it fires
# there - the thing a host's own eval runner compares against - so the
# assertion "this skill works on N hosts" has N files behind it, not a
# sentence.
FIXTURE_HOSTS: tuple[str, ...] = ("claude", "codex", "cursor", "gemini", "grok")


def _fixture_payload(proposal: SkillProposal, host: str) -> dict[str, Any]:
    return {
        "host": host,
        "skill": proposal.name,
        "cases": [
            {"trigger": trigger, "expected": list(proposal.assertions)}
            for trigger in proposal.positive_triggers
        ],
        "note": "expected output per positive trigger; a host eval runner "
                "compares its observed output against `expected`",
    }


def forge_skill(destination_root: str | Path, proposal: SkillProposal) -> Path:
    proposal.validate()
    root = Path(destination_root).expanduser().resolve(strict=False)
    if root.exists() and root.is_symlink():
        raise ForgeError("Destination root cannot be a symlink")
    skill_dir = root / proposal.name
    if skill_dir.exists():
        raise ForgeError(f"Skill already exists: {skill_dir}")
    skill_dir.mkdir(parents=True, exist_ok=False)
    try:
        _atomic_text(skill_dir / "SKILL.md", _skill_markdown(proposal))
        _atomic_text(skill_dir / "agents" / "openai.yaml", _openai_yaml(proposal))
        _atomic_text(
            skill_dir / "godmode-evals.json",
            json.dumps(_eval_payload(proposal), indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_text(
            skill_dir / "references" / "godmode-gap-evidence.md",
            "# Godmode Capability Gap\n\n"
            f"Observed reusable uses: {proposal.repeated_uses}\n\n"
            f"{proposal.gap_evidence.strip()}\n",
        )
        for host in FIXTURE_HOSTS:
            _atomic_text(
                skill_dir / "fixtures" / host / "expected.json",
                json.dumps(_fixture_payload(proposal, host), indent=2, ensure_ascii=False) + "\n",
            )
        validate_skill(skill_dir)
    except Exception:
        for path in sorted(skill_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        skill_dir.rmdir()
        raise
    return skill_dir


# Safety hard-fails. Narrow on purpose: each pattern is content no honest
# skill body carries - piping a remote script straight into a shell,
# instruction-override language, or reaching for credential files.
_SKILL_SAFETY_FLAGS = (
    ("pipe-to-shell", re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:ba|z|da)?sh\b", re.IGNORECASE)),
    ("instruction-override", re.compile(
        r"(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior|earlier)\s+instructions",
        re.IGNORECASE)),
    ("credential-reach", re.compile(
        r"(?:\.aws/credentials|id_rsa\b|\.netrc\b|\.npmrc\b.*_authToken)", re.IGNORECASE)),
    ("destructive-sweep", re.compile(r"\brm\s+-rf\s+[/~]", re.IGNORECASE)),
)

_TRIGGER = re.compile(r"(?i)\buse\s+(?:when|before|for|whenever|at|on|after)\b")
_BACKTICKED = re.compile(r"`([^`\n]{2,60})`")


def lint_skill(skill_dir: str | Path) -> dict[str, Any]:
    """Three structural facets on one skill; the verdict names its own scope.

    `scope` reads the description alone: a skill without an explicit
    trigger cannot be routed to. `delivery` reads the body against the
    description's promise: every backticked term advertised up front must
    appear in the body, because a body silently narrower than its
    description is the mismatch that survives review. `safety` hard-fails
    on injection-shaped content - there is no soft pass on that facet.

    The report carries `verdict_scope: structural`: a lint pass is a
    statement about text shape, never a claim the skill helps a live task.
    """
    root = Path(skill_dir).resolve(strict=True)
    content = (root / "SKILL.md").read_text(encoding="utf-8")
    match = _FRONTMATTER.match(content)
    description = ""
    if match:
        for line in match.group("body").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() == "description":
                description = value.strip()
    body = content[match.end():] if match else content

    facets: dict[str, dict[str, Any]] = {}

    if not description:
        facets["scope"] = {"passed": False, "why": "no description in frontmatter"}
    elif not _TRIGGER.search(description):
        facets["scope"] = {
            "passed": False,
            "why": "description names no explicit trigger (use when/before/for)",
        }
    else:
        facets["scope"] = {"passed": True, "why": ""}

    promised = [term for term in _BACKTICKED.findall(description)]
    undelivered = [term for term in promised if term.split()[0] not in body]
    facets["delivery"] = (
        {"passed": False,
         "why": "advertised but absent from the body: " + ", ".join(undelivered)}
        if undelivered else {"passed": True, "why": ""}
    )

    fired = [name for name, pattern in _SKILL_SAFETY_FLAGS if pattern.search(content)]
    facets["safety"] = (
        {"passed": False, "why": "hard flag(s): " + ", ".join(fired)}
        if fired else {"passed": True, "why": ""}
    )

    # S19 item 5 - the bundle facet: a skill is a directory, and its graph
    # must hold. A referenced file that does not exist is a dead link the
    # agent hits at load time; a bundled file nothing references is an
    # orphan paying storage and context for no path that reaches it.
    # Links are read from every markdown file in the bundle, so a
    # reference reached through references/ still anchors its own links.
    findings: list[str] = []
    referenced: set[str] = set()
    link = re.compile(r"\[[^\]]*\]\(([^)#\s]+)\)|`((?:references|scripts|assets)/[^`\s]+)`")
    markdown_files = [root / "SKILL.md"] + sorted(root.rglob("*.md"))
    seen_md: set[Path] = set()
    for md in markdown_files:
        if md in seen_md or not md.is_file():
            continue
        seen_md.add(md)
        for m in link.finditer(md.read_text(encoding="utf-8", errors="replace")):
            target = (m.group(1) or m.group(2) or "").strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md.parent / target)
            # A markdown LINK asserts a bundle-relative path - missing is
            # a dead link. A backticked path is a HINT: it counts as a
            # reference when the file exists in the bundle, and stays
            # silent when it does not (prose legitimately backticks
            # plugin-root paths like scripts/godmode.py).
            if resolved.is_file():
                referenced.add(str(resolved.resolve()))
            elif m.group(1):
                findings.append(
                    f"dead link: {md.relative_to(root)} -> {target}")
    for bundled in sorted(root.rglob("*")):
        if not bundled.is_file() or bundled.name == "SKILL.md":
            continue
        relative = bundled.relative_to(root).as_posix()
        # Convention-loaded files are reachable by NAME, not by reference:
        # the evals machinery reads godmode-evals.json and host adapters
        # read agents/*.yaml without any prose link existing.
        if (bundled.name == "godmode-evals.json"
                or relative.startswith("agents/")):
            continue
        if str(bundled.resolve()) not in referenced:
            findings.append(f"orphan: {relative} is "
                            "reachable from no reference")
    facets["bundle"] = (
        {"passed": False, "findings": findings,
         "why": f"{len(findings)} graph finding(s)"}
        if findings else {"passed": True, "findings": [], "why": ""}
    )

    return {
        "skill": root.name,
        "facets": facets,
        "passed": all(facet["passed"] for facet in facets.values()),
        "verdict_scope": "structural",
    }


def validate_skill(skill_dir: str | Path) -> dict[str, Any]:
    root = Path(skill_dir).resolve(strict=True)
    skill_file = root / "SKILL.md"
    metadata_file = root / "agents" / "openai.yaml"
    eval_file = root / "godmode-evals.json"
    if not all(path.is_file() for path in (skill_file, metadata_file, eval_file)):
        raise ForgeError("Skill is missing SKILL.md, agents/openai.yaml, or godmode-evals.json")
    content = skill_file.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(content)
    if not match:
        raise ForgeError("SKILL.md frontmatter is missing")
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"}:
        raise ForgeError("SKILL.md frontmatter must contain only name and description")
    if fields["name"] != root.name or not _NAME.fullmatch(fields["name"]):
        raise ForgeError("Skill name must match its directory")
    if not fields["description"] or len(fields["description"]) > 1024:
        raise ForgeError("Skill description is empty or too long")
    if not re.search(r"(?i)\buse\s+(?:when|before|for)\b", fields["description"]):
        raise ForgeError("Skill description must include an explicit trigger")
    if len(content.splitlines()) > 500:
        raise ForgeError("SKILL.md exceeds the 500-line Godmode limit")
    try:
        evals = json.loads(eval_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ForgeError("godmode-evals.json is invalid") from exc
    if len(evals.get("routing", {}).get("positive", [])) < 2:
        raise ForgeError("Skill requires at least two positive routing cases")
    if len(evals.get("routing", {}).get("near_negative", [])) < 2:
        raise ForgeError("Skill requires at least two near-negative routing cases")
    if not evals.get("behavior_assertions"):
        raise ForgeError("Skill requires observable behavior assertions")
    # C-23. A forged skill carries one fixture per host and is refused when
    # one is missing. A hand-written skill that never had a `fixtures/`
    # directory is not refused - it predates the fixtures and reports
    # `fixture_hosts: 0` honestly - but a directory that exists and is
    # incomplete is a forged skill someone broke, and that is refused.
    fixture_hosts = 0
    fixtures_root = root / "fixtures"
    for host in (FIXTURE_HOSTS if fixtures_root.is_dir() else ()):
        fixture_file = fixtures_root / host / "expected.json"
        if not fixture_file.is_file():
            raise ForgeError(f"Skill is missing the expected-output fixture for {host}")
        try:
            fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ForgeError(f"Expected-output fixture for {host} is invalid") from exc
        if fixture.get("host") != host or not fixture.get("cases"):
            raise ForgeError(f"Expected-output fixture for {host} names the wrong host or no cases")
        fixture_hosts += 1
    return {
        "valid": True,
        "name": fields["name"],
        "lines": len(content.splitlines()),
        "positive_cases": len(evals["routing"]["positive"]),
        "near_negative_cases": len(evals["routing"]["near_negative"]),
        "assertions": len(evals["behavior_assertions"]),
        "fixture_hosts": fixture_hosts,
    }

"""Compile a project's prose operating guidance into addressable rules.

Prose cannot be enforced. A paragraph that says "never push without asking" is a
suggestion with formatting; a rule with an id, a trigger and a verification method is
a gate. This module performs that conversion and is honest about its limits: a rule
whose compliance cannot be checked is admitted and labelled ADVISORY, never dropped
and never dressed up as enforced.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .godmode_corpus import Binding, Segment, resolve_roles, segment_document

HARD = "HARD"
SOFT = "SOFT"
ADVISORY = "ADVISORY"

TRIGGERS = (
    "session_open",
    "before_approach",
    "before_mutation",
    "before_completion",
    "session_close",
    "always",
)

# A rule only earns HARD when a shape below tells us how to check it. The table is
# deliberately small: guessing a verification method would manufacture exactly the
# false enforcement the honest-enforcement guarantee exists to prevent.
_SHAPES: tuple[tuple[str, str, str, str], ...] = (
    # pattern, verify kind, trigger, enforcement
    #
    # Ordered: first match wins, so the specific development disciplines are tried
    # before the general shapes that would otherwise absorb them into a weaker check.
    (r"\b(?:failing test|test first|test-first|red before green|red-green)\b"
     r"|\bbefore (?:writing |any )?implementation\b"
     r"|\bimplementation before\b.*\btest\b",
     "test_precedes_implementation", "before_mutation", HARD),
    (r"\b(?:seen to fail|watch it fail|observed failing|plant(?:ed)? (?:a )?violation)\b"
     r"|\bguard\b.*\bfail(?:s|ing)? first\b",
     "guard_observed_failing", "before_completion", HARD),
    (r"\breview(?:ed)? before (?:merge|merging|commit|committing|shipping|release)\b"
     r"|\b(?:no|never) merge\b.*\breview\b"
     r"|\bcode review\b.*\b(?:required|mandatory|before)\b",
     "review_recorded", "before_completion", HARD),
    (r"\bcite[sd]?\b|\bevidence (?:before|first)\b|\bwith evidence\b",
     "citation_resolves", "before_completion", HARD),
    (r"\bnever\b.*\bwithout\b|\bnot\b.*\bunless\b|\bonly (?:after|with)\b",
     "attestation_present", "before_mutation", HARD),
    (r"\bbefore (?:any|every|touching|changing|proposing|writing|the fix)\b|\bpre-?flight\b",
     "attestation_present", "before_mutation", HARD),
    (r"\b(?:both|together|and its guard|paired|same pass)\b",
     "pair_complete", "before_completion", HARD),
    (r"\b(?:check|read|scan|search|verify) .*\bfirst\b",
     "attestation_present", "before_approach", HARD),
    (r"\bevery (?:fix|change|task|bug) .*\bguard\b|\bguard\b.*\bmust\b",
     "attestation_present", "before_completion", HARD),
    (r"\bre-?run\b|\bmust pass\b|\bexit(?:s)? (?:zero|non-zero)\b",
     "command_exit_zero", "before_completion", SOFT),
    # A gate that failed without reaching its target. The verdict is then about
    # the harness - an argv slip, a missing fixture, a shallow checkout - and
    # reads as a fault in the thing under test. Recorded here because a check
    # written for this project called a correct detector broken when a runner
    # gave it no history to walk.
    (r"\bgate\b.*\breach(?:ed)?\b|\bharness\b|\bargv\b"
     r"|\b(?:verify|confirm)\b.*\bgate\b.*\b(?:ran|target)\b"
     r"|\bexercis(?:e|ed|ing)\b.*\btarget\b",
     "target_exercised", "before_completion", HARD),
    # Attribution by a positive identifier rather than resemblance. Naming the
    # wrong vendor in an operational instruction sends a person to spend money
    # on a healthy system.
    (r"\bpositive identifier\b|\bkey prefix\b|\bendpoint\b.*\bidentif\b"
     r"|\battribut(?:e|ion)\b.*\b(?:provider|vendor)\b",
     "identifier_cited", "before_completion", HARD),
    # A repair that is not idempotent, or that detects a symptom rather than
    # the fixed state, turns an upstream fix into a regression the second time
    # it runs.
    (r"\bidempoten\w+\b|\bdetect\b.*\bfixed state\b|\brun twice\b"
     r"|\btwice\b.*\b(?:same|identical|stable)\b|\bconverg\w+\b",
     "idempotence_shown", "before_completion", HARD),
    # The mechanism that performed the mutation, not the event that preceded
    # it. A trigger presented as a cause survives review because the timeline
    # is true.
    (r"\bmechanism\b.*\b(?:not|rather than)\b.*\bevent\b"
     r"|\btrigger\b.*\bcause\b|\bname the mechanism\b",
     "mechanism_named", "before_completion", HARD),
    # Evidence discipline. A live project's mistake ledger records the same
    # failure in every variant - the nearest available evidence accepted as
    # sufficient - and its own rules against it compiled as ADVISORY here,
    # because they matched no shape and the fallback blocks nothing. These
    # name the family: a conclusion that must cite what confirmed it.
    (r"\bdiff(?:ed|ing)?\b|\bdifferential\b|\bbefore and after\b|\bcompare\b.*\bfirst\b"
     r"|\bpre/?post\b",
     "differential_cited", "before_completion", HARD),
    (r"\babsence\b|\bsearch miss\b|\bnot found\b.*\bconclude\b|\bconclude\b.*\bmissing\b"
     r"|\bnever (?:conclude|assume)\b",
     "second_probe_cited", "before_completion", HARD),
    (r"\bfrom the code alone\b|\balone\b.*\b(?:design|intent|rule)\b"
     r"|\b(?:design|intent)\b.*\bdocument\b|\bauthoritative source\b",
     "authority_cited", "before_approach", HARD),
    (r"\bhave not (?:observed|measured|confirmed|verified)\b"
     r"|\bnot (?:observed|measured|confirmed)\b|\bcheapest observation\b"
     r"|\bstate a cause\b|\bunconfirmed\b",
     "observation_cited", "before_completion", HARD),
    (r"\benumerate\b|\blist every\b|\breport (?:what|every|all)\b",
     "record_field_set", "before_completion", SOFT),
)

# Lines that read as directives. Everything else is narration.
_DIRECTIVE = re.compile(
    r"\b(?:must|never|always|do not|don't|shall|require[sd]?|before|after|"
    r"ensure|verify|confirm|check|prohibited|forbidden|mandatory)\b",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_NOISE = re.compile(r"^\s*(?:\||#|>|<)")


_BOOTSTRAP = re.compile(
    r"^(?:fix|hotfix|revert|guard|prevent|block|refuse|stop)\b|"
    r"\b(?:never again|regression|no longer|must not)\b",
    re.IGNORECASE,
)


def bootstrap_rules(project: Path, limit: int = 200) -> dict[str, Any]:
    """Candidate invariants mined from the project's own commit history.

    A repository with history already knows what went wrong; each fix/revert
    subject is a rule someone paid for once. Candidates are for review, not
    enforcement - promotion to the charter stays a human decision.
    """
    from .godmode_anchor import run_git

    raw = run_git(project, "log", f"--max-count={limit}", "--pretty=%h%x09%s")
    if raw is None:
        return {"candidates": [], "note": "no git history to bootstrap from"}
    candidates = []
    seen: set[str] = set()
    for line in raw.splitlines():
        commit, _, subject = line.partition("\t")
        if not _BOOTSTRAP.search(subject):
            continue
        normalized = subject.strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append({
            "commit": commit,
            "subject": subject.strip()[:140],
            "candidate_invariant": f"the condition fixed in {commit} must not recur",
            "promote_with": f"remember --kind invariant --subject \"{subject.strip()[:60]}\" "
                            f"--value \"...\" --evidence commit:{commit}",
        })
    return {
        "commits_scanned": len(raw.splitlines()),
        "candidates": candidates[:50],
        "note": "candidates are for review; promotion to the charter is a human decision",
    }


@dataclass(frozen=True)
class Rule:
    """One compiled, addressable rule."""

    id: str
    role: str
    path: str
    line: int
    text: str
    trigger: str
    enforcement: str
    verify: str

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "source": f"{self.path}:{self.line}",
            "text": self.text,
            "trigger": self.trigger,
            "enforcement": self.enforcement,
            "verify": self.verify,
        }


def _classify(text: str) -> tuple[str, str, str]:
    """Return (enforcement, verify_kind, trigger) for one directive."""
    lowered = text.lower()
    for pattern, kind, trigger, enforcement in _SHAPES:
        if re.search(pattern, lowered):
            return enforcement, kind, trigger
    return ADVISORY, "none", "always"


def _rule_id(role: str, path: str, text: str) -> str:
    digest = hashlib.sha256(f"{role}\x00{path}\x00{text}".encode("utf-8")).hexdigest()
    return f"R-{digest[:10]}"


def _directives(segment: Segment) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    fenced = False
    for offset, raw in enumerate(segment.body.splitlines()):
        if _FENCE.match(raw):
            fenced = not fenced
            continue
        if fenced:
            continue
        line = _BULLET.sub("", raw).strip()
        if not line or _NOISE.match(raw) and not _BULLET.match(raw):
            continue
        # Strip emphasis and inline markup so shape matching sees plain words.
        line = re.sub(r"[*_`]+", "", line).strip()
        if len(line) < 12 or not _DIRECTIVE.search(line):
            continue
        found.append((segment.start_line + offset, line))
    return found


def compile_binding(binding: Binding, project: Path) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for segment in segment_document(binding, project):
        for line, text in _directives(segment):
            enforcement, verify, trigger = _classify(text)
            identifier = _rule_id(segment.role, segment.path, text)
            if identifier in seen:
                continue
            seen.add(identifier)
            rules.append(
                Rule(
                    id=identifier,
                    role=segment.role,
                    path=segment.path,
                    line=line,
                    text=text,
                    trigger=trigger,
                    enforcement=enforcement,
                    verify=verify,
                )
            )
    return rules


def compile_charter(project: Path) -> dict[str, Any]:
    """Compile every bound authority document into a rule set.

    Reported counts are the point: a project learns how much of its own guidance is
    actually checkable, rather than assuming all of it is.
    """
    resolution = resolve_roles(project)
    rules: list[Rule] = []
    for binding in resolution.bindings:
        rules.extend(compile_binding(binding, resolution.project))

    rules.sort(key=lambda rule: (rule.path, rule.line))
    counts = {level: 0 for level in (HARD, SOFT, ADVISORY)}
    by_role: dict[str, int] = {}
    for rule in rules:
        counts[rule.enforcement] += 1
        by_role[rule.role] = by_role.get(rule.role, 0) + 1

    return {
        "rules": len(rules),
        "enforcement": counts,
        "by_role": dict(sorted(by_role.items())),
        "documents": len(resolution.bindings),
        "compiled": [rule.view() for rule in rules],
    }


# A rule about migrations is irrelevant to a stylesheet however the task is worded.
# Traits narrow the rule set deterministically, at the source, instead of injecting
# everything and relying on the model to ignore what does not apply.
_TRAITS: tuple[tuple[str, str], ...] = (
    ("test", r"(^|/)(tests?|spec|__tests__)/|(^|/)test_|_test\.|\.test\.|\.spec\."),
    ("migration", r"(^|/)migrations?/|\.sql$|(^|/)alembic/"),
    ("schema", r"schema|(^|/)models?/|\.prisma$|\.graphql$"),
    ("config", r"\.(json|ya?ml|toml|ini|cfg|env|properties)$|(^|/)\.[a-z]+rc"),
    ("ci", r"(^|/)\.github/workflows/|gitlab-ci|jenkinsfile|azure-pipelines|bitbucket-pipelines"),
    ("docs", r"\.(md|mdx|rst|adoc|txt)$|(^|/)docs?/"),
    ("ui", r"\.(tsx|jsx|vue|svelte|css|scss|html)$|(^|/)(components?|views?|pages?)/"),
    ("security", r"auth|crypto|secret|token|password|credential|session|permission|acl"),
    ("data", r"(^|/)(db|database|repositor(y|ies)|dao|store)/|\.(sqlite3?|db)$"),
    ("generated", r"(^|/)(dist|build|vendor|node_modules|__pycache__|target)/|\.min\."),
    ("entrypoint", r"(^|/)(main|index|app|cli|__main__)\.[a-z]+$"),
    ("infra", r"dockerfile|docker-compose|\.tf$|(^|/)(k8s|helm|charts)/"),
)


# The words a rule actually uses, rather than the trait names. A rule saying "ddl"
# or "stylesheet" names no trait literally, so without this it defaults to universal
# and narrowing quietly does nothing. Recall here is what makes the filter useful;
# a project with its own vocabulary should extend this rather than rename its rules.
_TRAIT_VOCABULARY: tuple[tuple[str, str], ...] = (
    ("test", r"\btests?\b|\bassertions?\b|\bguards?\b|\bcoverage\b|\bfixtures?\b|\bmocks?\b|\bsuite\b"),
    ("migration", r"\bmigrations?\b|\bddl\b|\balter table\b|\bbackfill\b|\brollback script\b"),
    ("schema", r"\bcolumns?\b|\btables?\b|\bindexe?s?\b|\bconstraints?\b|\bschemas?\b|\bnullable\b|\bforeign key\b"),
    ("docs", r"\bdocumentation\b|\bchangelog\b|\breadme\b|\brelease notes?\b|\bhelp page\b|\bdocs?\b"),
    ("ui", r"\binterfaces?\b|\bcomponents?\b|\blayouts?\b|\bstylesheets?\b|\bviewport\b|\bcss\b|\bmodal\b|\bbutton\b|\bscreen\b|\brender(?:s|ing)?\b"),
    ("security", r"\bsecurity\b|\bprivacy\b|\bsecrets?\b|\bcredentials?\b|\bauth\w*\b|\btokens?\b|\bpasswords?\b|\bpermissions?\b"),
    ("config", r"\bconfigs?\b|\bconfiguration\b|\benvironment variables?\b|\bfeature flags?\b|\bsettings\b"),
    ("ci", r"\bci\b|\bpipelines?\b|\bworkflows?\b|\bbuild server\b"),
    ("data", r"\bdatabase\b|\bquer(?:y|ies)\b|\brows?\b|\bledgers?\b|\bretention\b"),
    ("generated", r"\bgenerated\b|\bvendored?\b|\bbuild output\b|\bartifacts?\b"),
    ("infra", r"\bdeploy\w*\b|\bcontainers?\b|\bdocker\b|\bkubernetes\b|\binfrastructure\b"),
    ("entrypoint", r"\bentry ?points?\b|\bcli\b|\bmain\b"),
)


def traits_of(path: str) -> list[str]:
    """Classify one artefact by the characteristics rules can key on."""
    lowered = path.replace("\\", "/").lower()
    found = [name for name, pattern in _TRAITS if re.search(pattern, lowered)]
    suffix = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    if suffix:
        found.append(f"ext:{suffix}")
    return sorted(set(found))


def rule_traits(text: str) -> list[str]:
    """Which artefact characteristics a rule speaks about.

    A rule naming none is universal: it applies everywhere, which is the safe
    default. Narrowing may only ever happen on an explicit mention.
    """
    lowered = text.lower()
    named = [
        name for name, _ in _TRAITS
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", lowered)
    ]
    for name, extra in _TRAIT_VOCABULARY:
        if name not in named and re.search(extra, lowered):
            named.append(name)
    return sorted(set(named))


def applicable_rules(charter: dict[str, Any], path: str) -> dict[str, Any]:
    """Rules that apply to one artefact, and the reason each was kept or dropped."""
    traits = set(traits_of(path))
    kept: list[dict[str, Any]] = []
    narrowed = 0
    for rule in charter["compiled"]:
        wanted = rule.get("traits") or rule_traits(rule["text"])
        if not wanted:
            kept.append({**rule, "why": "universal"})
        elif traits & set(wanted):
            kept.append({**rule, "why": "matches " + ",".join(sorted(traits & set(wanted)))})
        else:
            narrowed += 1
    return {
        "path": path,
        "traits": sorted(traits),
        "applicable": kept,
        "kept": len(kept),
        "narrowed_away": narrowed,
        "total": charter["rules"],
    }


# U-S4 prose linter - negation-heavy detection. A rule can be checkable and
# still read badly: "never commit without a changelog" names the forbidden
# behaviour and puts it first, which is the shape a prohibition-only rule
# takes. Restated positively ("every commit carries a changelog") the same
# rule survives a skim; two or more negations with nothing positive to do
# instead is the signal, not any single "never"/"not".
_NEGATION_TOKENS = re.compile(
    r"\b(?:not|never|no|none|cannot|can't|won't|don't|doesn't|didn't|isn't|"
    r"aren't|without|forbidden|prohibited|disallow(?:ed)?|refus(?:e|es|ed|ing)|"
    r"non-\w+)\b",
    re.IGNORECASE,
)
# Verbs that name what to do rather than what to avoid. Their presence beside
# a negation is exactly the "do X, never Y" shape that is not a candidate for
# this finding - the rule already states the positive half.
_POSITIVE_VERBS = re.compile(
    r"\b(?:state[sd]?|stating|writ(?:e|es|ing|ten)|run|runs|running|"
    r"record(?:ed|s|ing)?|cit(?:e|es|ing|ed)|ensur(?:e|es|ing|ed)|"
    r"confirm(?:ed|s|ing)?|verif(?:y|ies|ied|ying)|check(?:ed|s|ing)?|"
    r"log(?:ged|s|ging)?|report(?:ed|s|ing)?|document(?:ed|s|ing)?|"
    r"declar(?:e|es|ing|ed)|includ(?:e|es|ing|ed)|add(?:ed|s|ing)?|"
    r"us(?:e|es|ing|ed)|keep(?:s|ing)?|kept|mak(?:e|es|ing)|made|"
    r"provid(?:e|es|ing|ed)|attest(?:ed|s|ing)?|nam(?:e|es|ing|ed)|"
    r"observ(?:e|es|ing|ed)|authoriz(?:e|es|ing|ed)|own(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)


def negation_heavy(text: str) -> bool:
    """Whether a directive reads as prohibitions with no positive form.

    Two or more negation tokens and no positive verb: the shape a rule takes
    when it only says what must not happen. The threshold is >=2 because a
    single "never" paired with a positive verb elsewhere in the same
    sentence ("never merge without recording a reviewer") is an ordinary,
    checkable rule; it is the rule with nothing but prohibitions that reads
    as an instruction in how to do the forbidden thing.
    """
    return (
        len(_NEGATION_TOKENS.findall(text)) >= 2
        and not _POSITIVE_VERBS.search(text)
    )


def rules_for(charter: dict[str, Any], trigger: str, enforcement: str | None = None) -> list[dict[str, Any]]:
    return [
        rule
        for rule in charter["compiled"]
        if rule["trigger"] == trigger and (enforcement is None or rule["enforcement"] == enforcement)
    ]


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "GODMODE.md").write_text(
            "# Gates\n"
            "- Never commit without an explicit ask.\n"
            "- Before any fix, scan the invariant registry first.\n"
            "- Every fix must own a guard and its guard must be seen to fail.\n"
            "- A claim must cite evidence before completion.\n"
            "- The product is a local-first control plane.\n"
            "```\nnever run this code block directive\n```\n",
            encoding="utf-8",
        )
        charter = compile_charter(project)

        assert charter["rules"] >= 4, charter["enforcement"]
        assert charter["enforcement"][HARD] >= 3, charter["enforcement"]

        texts = [rule["text"] for rule in charter["compiled"]]
        # Narration is not a rule.
        assert not any("control plane" in text for text in texts), texts
        # Fenced code is never compiled into a rule.
        assert not any("code block directive" in text for text in texts), texts

        kinds = {rule["verify"] for rule in charter["compiled"]}
        assert "citation_resolves" in kinds, kinds

        # Ids are stable across runs, so attestations can reference them durably.
        again = compile_charter(project)
        assert [r["id"] for r in charter["compiled"]] == [r["id"] for r in again["compiled"]]

        # An unverifiable directive is admitted and labelled, never dropped.
        (project / "GODMODE.md").write_text(
            "# Feel\n- The interface must feel premium.\n", encoding="utf-8"
        )
        soft = compile_charter(project)
        assert soft["rules"] == 1, soft
        assert soft["enforcement"][ADVISORY] == 1, soft

    # Development disciplines a project states in prose must compile to gates, not
    # to advisory text that nothing can check.
    with tempfile.TemporaryDirectory() as raw:
        disciplined_project = Path(raw)
        (disciplined_project / "GODMODE.md").write_text(
            "# Discipline\n"
            "- Never write implementation before a failing test exists.\n"
            "- Every guard must be seen to fail before the fix lands.\n"
            "- All changes are reviewed before merge.\n",
            encoding="utf-8",
        )
        disciplined = compile_charter(disciplined_project)
        by_kind = {rule["verify"]: rule for rule in disciplined["compiled"]}
        for expected in ("test_precedes_implementation", "guard_observed_failing", "review_recorded"):
            assert expected in by_kind, (expected, sorted(by_kind))
            assert by_kind[expected]["enforcement"] == HARD, by_kind[expected]
        assert disciplined["enforcement"][ADVISORY] == 0, disciplined["enforcement"]

    # Rules narrow to the artefact they speak about, deterministically.
    with tempfile.TemporaryDirectory() as raw:
        keyed = Path(raw)
        (keyed / "GODMODE.md").write_text(
            "# Rules\n"
            "- Never drop a column without a reversible migration.\n"
            "- Every UI component must be reviewed before merge.\n"
            "- Always confirm the change before committing.\n",
            encoding="utf-8",
        )
        charter = compile_charter(keyed)
        assert charter["rules"] == 3, charter

        assert "migration" in traits_of("db/migrations/0002_add_col.sql")
        assert "test" in traits_of("tests/test_auth.py")
        assert "security" in traits_of("src/auth/session.py")

        migration = applicable_rules(charter, "db/migrations/0002_add_col.sql")
        texts = " ".join(r["text"] for r in migration["applicable"]).lower()
        assert "migration" in texts, migration
        assert "ui component" not in texts, migration
        assert migration["narrowed_away"] >= 1, migration

        component = applicable_rules(charter, "src/components/Button.tsx")
        component_texts = " ".join(r["text"] for r in component["applicable"]).lower()
        assert "ui component" in component_texts, component
        assert "column" not in component_texts, component

        # A rule naming no characteristic is universal and survives every narrowing.
        for probe in ("db/migrations/x.sql", "src/components/Button.tsx", "README.md"):
            kept = " ".join(r["text"] for r in applicable_rules(charter, probe)["applicable"])
            assert "before committing" in kept, (probe, kept)

    print("godmode_charter self-check OK")


if __name__ == "__main__":
    _self_check()

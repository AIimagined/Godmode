"""Census: every verb, skill and work item is assigned to exactly one sprint.

"Everything is covered" is the kind of claim that rots quietly: a verb is added,
nobody maps it, and the plan still says it covers everything. This fails instead.

Run it after any change to the CLI surface, the skills directory, or the plan.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "quality" / "release-coverage.json"


def live_verbs() -> set[str]:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "godmode.py"), "--project", str(ROOT), "--help"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    match = re.search(r"\{([a-z0-9,\-]+)\}", out.replace("\n", ""))
    assert match, "could not read the verb list from --help"
    return set(match.group(1).split(","))


def live_skills() -> set[str]:
    return {p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists()}


manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
sprints = manifest["sprints"]

assigned: list[str] = []
for sprint in sprints.values():
    assigned.extend(sprint["verbs"])

verbs = live_verbs()
skills = live_skills()

duplicates = sorted({v for v in assigned if assigned.count(v) > 1})
unassigned = sorted(verbs - set(assigned))
phantom = sorted(set(assigned) - verbs)

skill_unassigned = sorted(skills - set(manifest["skills"]))
skill_phantom = sorted(set(manifest["skills"]) - skills)

bad_sprint = sorted(
    name for name, s in manifest["skills"].items() if s not in sprints
) + sorted(
    item for item, s in manifest["work_items"].items() if s not in sprints
)

problems = []
if duplicates:
    problems.append(f"verbs assigned to more than one sprint: {duplicates}")
if unassigned:
    problems.append(f"verbs with no sprint: {unassigned}")
if phantom:
    problems.append(f"manifest names verbs that do not exist: {phantom}")
if skill_unassigned:
    problems.append(f"skills with no sprint: {skill_unassigned}")
if skill_phantom:
    problems.append(f"manifest names skills that do not exist: {skill_phantom}")
if bad_sprint:
    problems.append(f"entries pointing at an undefined sprint: {bad_sprint}")

print(f"verbs   {len(verbs):4}  assigned {len(assigned):4}")
print(f"skills  {len(skills):4}  assigned {len(manifest['skills']):4}")
print(f"items   {len(manifest['work_items']):4}")
for key, sprint in sprints.items():
    owned = [i for i, s in manifest["work_items"].items() if s == key]
    print(f"  {key:3} {sprint['title']:34} {len(sprint['verbs']):3} verbs  {len(owned):2} items")

if problems:
    for problem in problems:
        print(f"FAIL: {problem}", file=sys.stderr)
    raise SystemExit(1)
print("\nok: every verb, skill and work item maps to exactly one sprint")

---
name: godmode-skill-forge
description: Create an original, compact project skill after a repeated capability gap is proven. Use when at least two real tasks need the same missing workflow and existing skills do not cover it reliably.
---

# Godmode Skill Forge

## Outcome

Produce a small, validated skill with explicit routing and observable acceptance checks. Do not create a skill for a one-off request, a vague preference, or work already covered by an installed skill.

## Workflow

1. Search the installed and project skill set for an adequate capability.
2. Record the concrete gap and at least two observed reusable uses.
3. Define one purpose, two positive routing examples, two nearby negative examples, and observable behavior assertions.
4. Capture a baseline showing how the current workflow misses the assertions.
5. Run the local forge:

   ```powershell
   python <plugin-root>/scripts/godmode.py --project <path> skill forge --destination <skills-directory> --name <skill-name> --purpose "<purpose>" --gap-evidence "<evidence>" --repeated-uses 2 --positive "<trigger one>" --positive "<trigger two>" --negative "<near miss one>" --negative "<near miss two>" --assertion "<observable result>"
   ```

6. Validate the generated structure with `skill validate`, then use the host's official skill validator when available.
7. Exercise positive, near-negative, and behavior cases. Revise only from observed failures.
8. Remove unnecessary instructions or resources and re-run validation.

Read [godmode-forge-contract.md](references/godmode-forge-contract.md) before approving a new skill.

## Constraints

- Keep frontmatter to `name` and `description`; put interface metadata in `agents/openai.yaml`.
- Use lowercase hyphen-case and make the description state both capability and trigger.
- Prefer progressive disclosure: compact `SKILL.md`, detailed references only when needed.
- Generate original project language and organization. Do not include external URLs, source-project names, copied templates, or imported implementation text.
- Do not invoke a model subprocess, fetch network content, install dependencies, or update itself.
- If two proposals overlap, synthesize one coherent skill using the strongest compatible behaviors and one routing boundary.
- Preserve failed evaluations as evidence; never rewrite a baseline to manufacture improvement.

## Completion

A forged skill is complete only when its structure validates, both positive examples route correctly, near-negative examples stay out, every assertion is evidenced, and its instructions are smaller than the workflow they replace.

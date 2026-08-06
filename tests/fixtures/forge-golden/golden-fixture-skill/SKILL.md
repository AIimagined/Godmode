---
name: golden-fixture-skill
description: "A frozen reference skill used only to detect generator drift in CI. Use when format the golden fixture."
---

# Golden Fixture Skill

## Outcome

A frozen reference skill used only to detect generator drift in CI.

## Route

Use this skill for requests such as:

- format the golden fixture
- regenerate the reference skill

Do not route these nearby requests here:

- unrelated deployment work
- general refactoring

## Workflow

1. Inspect the current project and identify the concrete input and desired result.
2. State any material assumption that cannot be established from local evidence.
3. Make the smallest coherent change that satisfies the requested result.
4. Run the strongest available verification that directly proves the result.
5. Report the outcome, evidence, and any remaining limit without claiming more.

## Acceptance

- output matches the checked-in golden tree
- no timestamp appears in generated text

If an assertion cannot be proved, report the unmet assertion and next safe action.

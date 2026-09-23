# Purpose

This skill exists so a session has one coordinating entry point instead of guessing
among several overlapping capabilities, and so every verb this project ships is named
somewhere an agent will actually read it before acting.

## Gap evidence

- seq:9404 — the root skill said nothing about a PARTIAL hooks status, so an agent
  could still claim the gate had blocked a tool that the gate never actually ran.
- seq:10121 — a census found 57 of 120 verbs were named by no skill, no hook nudge,
  and no doc at all; the count itself was measuring the wrong thing until a skill
  line existed for each one.
- seq:10272 — an internal study of real skill use found selection accuracy collapses
  as the number of skills grows, while naming verbs from the existing few did not;
  the fix was one coordinating skill routing to capabilities, not more skills.

## Promise

Starting or resuming substantive work routes through this skill first, which
establishes current reality, picks one bounded workflow, and only then hands off to
a narrower skill when the task needs one.

Future edits to this skill append their own seq: citation above.

# Purpose

This skill exists so a session has one coordinating entry point instead of guessing
among several overlapping capabilities, and so every verb this project ships is named
somewhere an agent will actually read it before acting.

## Gap evidence

- With no visible status for a partially wired safety hook, an agent could
  still claim a tool had been blocked by a gate that was never actually
  running.
- Many of the commands this project ships were named by no skill, no hook
  nudge, and no documentation at all, leaving an agent to guess which
  capability to reach for.
- Selection accuracy drops as the number of available skills grows, while
  naming the same capabilities from one coordinating skill does not carry
  that cost — so a single entry point routes to capabilities instead of
  adding more skills.

## Promise

Starting or resuming substantive work routes through this skill first, which
establishes current reality, picks one bounded workflow, and only then hands off to
a narrower skill when the task needs one.

Future edits to this skill append their own plain-language evidence above.

---
name: repeated-failure-routing
description: A bug whose last two fixes failed. Should route to the investigation workflow, not to a fresh guess.
tags: [routing, skill-selection]
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite]
---

A test in my project keeps failing. I've tried two different fixes for it already and neither one changed the result. What should I do next?

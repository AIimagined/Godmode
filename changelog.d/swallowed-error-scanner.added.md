`godmode swallow` (U-B3-3): a static scanner for the shapes that discard a
failure instead of reporting it - an empty or pass-only `except`/`catch`
block, a bound exception name that is never referenced, a `{data, error}`
destructure that drops `error`, and a `try` whose success branch logs while
every failure branch stays silent. Python is a real `ast` parse; JS/TS is
regex-shape best-effort, stated as such in the module docstring.

Findings carry `severity: "advisory"` - a hard block on every hit would
punish the non-fatal catches this runtime's own code relies on. What does
fail is a ratchet: `.godmode-swallow-baseline.json` stores a per-file count
of un-exempted findings, and a file whose count exceeds its stored entry is
a `regression`, the command's one hard signal. `--update-baseline` tightens
the file toward current counts but can never raise a stored ceiling, so
re-running it cannot make a real regression disappear - only fixing the
site, or annotating it, does.

A `# godmode: swallow-ok <reason>` (or `// godmode: swallow-ok <reason>` in
JS/TS) comment anywhere in the flagged span exempts that one site from the
count - and its reason is always listed in the report's `exemptions`, never
dropped silently. An annotation with no reason text exempts nothing; the
site stays in `findings`, marked `annotation_without_reason`.

The initial sweep over this repository found 27 sites, all `empty-except`,
spread across 18 files - no `unused-exception-name` or `success-only-log`
hits. All 27 are now the committed baseline rather than annotated
individually: reading them, they are this codebase's own established
degrade-not-block idiom (a best-effort cache read, a permission-hardening
`chmod` that is a no-op on some platforms, a process already gone by the
time it is killed), several already carrying their own inline reasoning.
Annotating them site-by-site belongs to whichever change touches each file
next; this change only had to prove the ratchet catches a new, unreasoned
site landing on top of that baseline.

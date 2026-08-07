Behaviour assertions now execute instead of being counted: an assertion in a
skill's `godmode-evals.json` may carry a `check` (argv command plus expected
exit code and output substring) that runs for real from the project root,
while bare strings stay valid and are reported declared-only. Each of the
five skills ships at least one executable probe. Two new snapshot families
join routing: `charter-rules.json` freezes every compiled rule (id, trigger,
enforcement, verify, text hash) so editing a prose rule shows a field-level
diff, and `ranking.json` freezes the ordered segment selection the context
brief makes for a fixed three-task set, so retrieval drift fails loudly.

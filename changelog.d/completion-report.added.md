The mandatory task-completion report (PRD 23.2) now exists as
`godmode_report.completion_report`: twelve fields assembled from archive
records and read-only git observation instead of composed from memory. The
status verdict is derived, not asserted - "verified" is only reachable when no
claim this session was downgraded and session close would pass, a blocked gate
forces "blocked", and a session with no change records reads "no change
required". Every field carries an uncertainty label from the 23.1 vocabulary,
and `render_markdown` emits the TASK COMPLETION REPORT table (field, value,
label) in a fixed order.

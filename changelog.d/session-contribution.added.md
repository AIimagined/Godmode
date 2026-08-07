`session close`, `status handover`, and the session-end hook now report what
the gates actually did — checks blocked, claims downgraded, steps skipped,
secrets refused, scope drift, and the measured context reduction — each count
carrying the record sequences that produced it. The summary reports activity,
never averted disaster, because that counterfactual is unmeasurable; it stays
silent when nothing fired and is switched off with `.godmode-report.json`
`{"session_summary": false}`.

The §12 lifecycle is now a stage machine read from the archive instead of a
convention: `godmode_stages` derives each stage's entry requirement from records
the work already produced (inventory, parity decision, approved plan, change,
ran check, reconciled docs, undowngraded claim), `stage_gate` checks the whole
prefix up to the target, and `advance` attests entry only when the gate passes.
A stage may be skipped only by a recorded decision that states a reason. The
§15.1 troubleshooting SOP ships in the same module as a fifteen-step checklist
(T0–T14) whose completion is `sop:Tn` attestations; `sop_status` reports the
next required step and names a root-cause claim premature while reproduction,
staleness, and guard-observation remain unattested.

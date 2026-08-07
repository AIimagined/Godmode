Anti-loop fixes and scenario coverage: oscillation rollback now targets the
last STABLE checkpoint (status green/verified, per §15.3) instead of merely the
most recent one; a blocking `loop` verdict carries a four-part plain-language
`notice` (what repeated, what it means, the next safe step, and no further
mutation until the evidence changes); the repetition threshold is configurable
via `.godmode-loop.json` `{"repeat_threshold": n}` clamped to 2..10 (default 3);
and `transport-evidence:` attestations now count as non-model controls for
model blame. The instruction-shaped-content scenario is relabelled from the
mistaken E-13 to SEC-injection, and six golden scenarios are staged: false RCA
(E-04), automated deletion preview (E-11), new-table temptation (E-15), context
brief latency (E-19), session restart (CTX-01), and prior-fix protection
(CTX-02) - 21 staged failures, all caught.

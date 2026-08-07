Chronicle depth work in three parts. Append no longer re-verifies the whole
chain on every write: a `godmode-head.json` hint in the archive root is checked
against the last record file only, falling back to a full verified scan (and
rebuilding the hint) whenever the hint is missing, corrupt, or stale — full
verification is unchanged and still catches mid-chain tampering via
`verify()`/`doctor`. `append(..., dedupe=True)` returns the most recent
byte-identical record of the same kind and subject (marked `"deduplicated":
True`, never persisted) instead of growing the chain; the default is off, and
dedupe never crosses subjects. New `Chronicle.expunge(sequence, reason)` erases
a record's data and evidence after a secret slips the shape scanner: the record
and every subsequent one are re-sealed so the chain still verifies, and an
`incident` tombstone (sequence, reason, old record hash) makes the rewrite
auditable instead of silent.

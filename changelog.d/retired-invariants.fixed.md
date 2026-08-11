Retiring an invariant was reported as contradicting it.

The contradiction detector collected every invariant record ever written for a
subject and called two values a conflict. Retiring an invariant means writing a
new record, with a new value, carrying a retired status — so using the
documented lifecycle produced an error by construction, and `doctor` reported
the archive unhealthy for doing the right thing.

Found by retiring a real invariant once a release closed the condition it
described. The record was correct, the retirement was correct, and the health
check called the pair a defect.

Records whose status puts them out of force — retired, superseded, withdrawn,
revoked — no longer take part in the comparison. A value that no longer binds
cannot contradict one that does.

Three things deliberately unchanged. Two live invariants that disagree are still
an error, which is the case the check exists for. A retired record sitting
beside a live pair does not excuse that pair. And an invariant with no status at
all still counts as live, because records written before status was recorded
must keep being checked — exempting them would retire the detector rather than
the record.

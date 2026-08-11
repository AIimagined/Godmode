# Godmode v0.2.10

A value that is right in its own frame and wrong in the reader's.

Every check this project had asked whether a claim was **supported**. None asked
whether a supported claim was **commensurable** with the sentence carrying it.
That is a different question, and it is the one behind every defect in this
release.

## The shape

Two systems, both internally correct. A value crosses between them and loses the
frame that made it meaningful. Nothing is broken on either side, so nothing
reports anything — and because the error is *uniform*, it survives every
consistency check already running and reads as entirely plausible.

Claim binding cannot reach it. The citation resolves. The cited record holds the
right instant, the right number, the right absence. What went missing was the
frame, dropped in transcription, and no amount of checking the citation will
find it.

## Where it was found

**In prose.** Every store here writes UTC; every operator surface renders the
viewer's zone. A bare time copied from one into a sentence about the other is
wrong by the reader's offset — consistently, across a whole report.

**In a comparison.** `stale_runtime` read a file's modification time on whatever
clock the start time happened to carry. An unlabelled start time meant `tz=None`
— the host's local clock — on one side, and a time meant as UTC on the other.
Measured on a `+05:30` host: a process started **two hours after** the newest
source reported `stale`, and the guard blocked a diagnosis that should have run.
West of UTC it fails the other way and clears a process that is genuinely dead.

**In a crash.** `_parse_time` caught `ValueError`, so a malformed timestamp was
handled — but a *well-formed* one with no offset parsed into a naive instant, and
subtracting that from an aware one raises `TypeError`, which nothing caught. One
unlabelled value anywhere took down the whole context report.

**In a search.** "Nothing found" is true of the search that ran and asserted
about the world. Two searches that miss inside a document holding the answer
produce exactly that sentence, and it reads as a conclusion.

**In a count.** A bare total carries its query's filter and cap invisibly. A
number from a call with a category filter and a silent limit is not the log; it
is a slice of one, and nothing about the number says so.

## What is new

| Surface | What it answers |
|---|---|
| `unframed-clock` | does a time quoted to a person say which clock it came from |
| `claim-from-a-sample` | does an absence name the search that would disprove it, and does a count state its denominator |
| `root-without-code` | does a named cause cite a line of the program it indicts |
| `unretracted-reversal` | is one subject carrying two live answers with neither withdrawn |
| `precheck` → `already_reported` | is this already filed and still open |

`root-without-code` does not accept a `rec:` citation. Pointing at a prior claim
is how an unexamined theory travels between passes, gaining standing at every hop
without ever touching the program. Grading the claim `hypothesis` clears the
check, which is the honest alternative and the point.

`unretracted-reversal` reports two live answers and blocks on three. One revision
can be an honest correction mid-investigation; a third live root means the read
set is still open, and another pass at the same depth will produce a fourth.

`precheck` had two questions — was this built, was this refused — and nothing for
the case in between: a thing already filed and still open. An incident, a
standing obligation, an ask nobody closed matched neither reader and stayed
invisible, so an open item describing the same symptom as the case in hand could
be listed twice in one session and never connected to it.

## Fixed

Retiring an invariant read as contradicting it. Retirement means writing a new
record with a new value and a retired status, so comparing every record ever
written for a subject made the documented lifecycle produce an error by
construction, and `doctor` reported the archive unhealthy for doing the right
thing.

The same defect was then found standing in a second reader. The guard-breadth
check read each record's own status — but the archive is append-only, so a
record cannot go back and mark itself superseded. The correction carries the
status; the record being corrected never can. A later settlement on the same
subject now retires the earlier ruling, and an earlier one does not pre-clear a
ruling written after it. Found by writing a lesson, correcting it, and watching
the original keep firing.

`precheck`'s own symbol list was capped at ten and silent about it — the defect
this release reports twice elsewhere. It now says when it truncates.

The four words for "out of force" have one owner. Two readers asking whether a
record still binds, from two copies of one list, is a disagreement waiting for a
release to expose it — which is exactly how the second instance above survived
the first fix.

## Deliberately not built

Nothing counts reversals inside a single pass. That would need the agent to
volunteer its own reversals, and an agent that reliably did so would not be the
one this exists for. The detectors here all read records that get written
anyway.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_godmode_runtime.MistakeClassTests   # the five detectors
python -m unittest tests.test_precheck                            # the third question
python scripts/godmode.py --project . version --reconcile
python scripts/godmode.py --project . doctor
```

Every new detector reports nothing on this project's own archive — no false
positives on 92 records. The one finding raised during development was real: a
lesson of this release's own writing declared a guard broader than the surface
it cited. It was corrected through the lifecycle rather than around it, and
correcting it is what exposed the append-only defect fixed above.

Two defects in this release were found by a test rather than by reading. The
frame detector's own pattern backtracked past its exemption and reported a
correctly labelled time as unlabelled, and a stripped offset had its own digits
read as a second bare time. Both were plausible on inspection and wrong on
execution, which is the argument for the release notes you are reading rather
than a summary of intent.

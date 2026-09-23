# Purpose

This skill exists so a change, session, or diff that already carries an
accepted claim or verdict gets one independent recheck before that earlier
pass is relied on - and so the recheck ends in a recorded disposition
instead of a private opinion.

## Gap evidence

- seq:11648 — a claim resolved `seq:10712` as `superseded`: a pass that had
  already been recorded was reopened and formally reversed, not silently
  redone. The same pattern recurs across the archive (seq:11651 resolves
  seq:10717; seq:16630 resolves seq:12811; seq:15551 resolves seq:14948) -
  fifteen resolved claims in total carry `outcome: superseded`, each one a
  case where a first pass being accepted was not the end of the story.
- seq:6572 and seq:6573 — the same subject ("OpenCode shim operational")
  was verdicted twice on the same day, and both verdicts came back
  `witness-malformed` from the identical checker
  (`cmd:opencode-external-session-plus-local-rerun`); the disposition never
  held, and the archive carries no third verdict that resolved it. That is
  exactly the failure this skill's step 6 exists to prevent: rerunning the
  same instrument confirms nothing new, so an independent recheck must cite
  a checker the original pass did not already use. A repeated-uses gap
  either way: nothing in the archive names this as its own workflow, so
  each recheck reinvents the sequence of "read the original record, gather
  fresh evidence, record a new verdict, resolve the old one" from scratch.
- seq:10712 — the claim record this skill's own worked example resolves,
  read in full before its resolution to show what "reading the original
  pass" means in practice, not just citing its sequence number.

## Promise

Reviewing an already-accepted change means restating the original claim,
producing independent evidence with its own checker, and closing the loop
with a recorded `held` or `superseded` outcome - never a second opinion
that lives only in the reviewer's head.

Future edits to this skill append their own seq: citation above.

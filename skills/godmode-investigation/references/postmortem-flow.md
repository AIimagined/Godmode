# Postmortem flow

When the failure is closed and its cause must be written down, the postmortem is a
record the runtime can check, not an essay. Run it in this order:

1. **What failed.** The incident holds expected, actual and the red reproduction run
   (step 2 above). Fallback: an incident recorded `--no-repro` stays underspecified
   until a failing command is found; say so in the postmortem.
2. **The RCA checklist.** `godmode checklist template rca --for <label>` prints the six
   steps - what, when, where, why, fix-root, lock - as paste-ready rows. `when` cites a
   bisect or the last green run (`cmd:git bisect ...`, `cmd:git log ...`, or `diff:<seq>`
   from `godmode differential`); `where` names the smallest failing unit; `lock` cites
   the test that fails without the fix.
3. **Why, as a 5-Whys record** with the extended contract: every link cited; a
   `validation` read back from the root (one cited step per link: "if the root were
   fixed, this link would not occur"); three countermeasures - `immediate`,
   `preventive`, and a `detection` that names a check or ratchet. The root is a
   process, check, invariant or design cause: a person, "human error", "forgot" or
   "the last deploy" is where blame stops, not a root, and the contract refuses it.
   Several contributing causes are several `branches`, each with its own links, root and
   validation. Put `"rca": "<label>"` in the record so the checklist is read with it.
4. **Check it.** `godmode method --check-method 5-whys --check-record <file>` exits
   non-zero and names each gap (`chain_not_validated`, `countermeasures_missing:detection`,
   `root_is_blame`, `incomplete:when`). A postmortem is done when it exits 0.
5. **The fix pair.** The fix claim cites the incident with `--fixes` and the surviving
   hypothesis with `hyp:<seq>` (step 7 above); `godmode hypothesis status` shows every
   rival and whether its kill ran.

Must not: publish a postmortem whose `method --check-record` still names a gap; end a
chain at a person; cite a hypothesis whose kill experiment never ran; weaken the
reproduction command so it passes.

Before recording the closing lesson, contrast the failed attempt with the nearest succeeding one - the difference between the two trajectories, not the failure alone, is what generalizes into a guard.

- Two-minute terminal demo script (U-E9): `docs/DEMO.md` walks five real
  commands in order - `godmode scenarios --brief` (23 staged attack/failure
  shapes, live), the 142-command regression corpus story
  (`tests/fixtures/gate_corpus.json` +
  `tests.test_gate_corpus.GateCorpus.test_every_entry_matches_expected`),
  the measured gate numbers quoted verbatim from
  `docs/releases/RELEASE_NOTES_v0.2.11.md` with each figure's own basis
  named beside it, one `godmode verdict record` walk-through showing a
  confirmed and a refuted disposition against the same witness, and
  `godmode init --detect` on a fixture repo. Every command shown is a real
  CLI surface, pinned by `tests/test_demo_doc.py`, which parses the doc's
  fenced commands and asserts each `godmode <subcommand>` resolves in the
  console parser. No causal language ("saves", "prevents") and no session
  provenance beyond neutral "real sessions" - the same discipline U-E1's
  denylist already holds ROI output to.

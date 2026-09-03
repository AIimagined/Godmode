# Godmode v0.3.16

The delivery patch for 0.3.15: the marketplace snapshots a plugin at the
first commit carrying a new version string and never re-fetches an
identical version, so the two CI fix rounds inside the v0.3.15 tag - the
host-contract matcher fix, the opaque-token capture fix, and the
pending-vocabulary gate fix - never reached installs. The sharpened
release rule is now recorded: a fix round after the version push bumps
again, because the version string is the marketplace's cache key.

One fix of its own, found by the installed-cache feature test: a failed
claim resolution now PRINTS its reversal-accounting ask - the advisory
lived in the record while the printed payload dropped it, and an
advisory nobody sees never happened.

## Verifying

- The 0.3.15 Verifying list, against an install of THIS version - the
  full feature test passes 31/31 here where 0.3.15's install scored
  29/31 on the two stranded fixes.
- `godmode claim --resolve <seq> --outcome failed ... ` — the printed
  payload carries the accounting ask.

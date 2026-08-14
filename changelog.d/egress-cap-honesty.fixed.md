`untrusted` no longer claims a clean sweep over files it never read.

`godmode_egress.scan_project` capped its walk at 400 files and stayed silent
about it: once the repository grew past that count, a file sorting later in
the tree - `docs/falsification-probe.md`, planted by the falsifiability
harness itself - fell outside the window, was never opened, and the scan
still reported `"data-only"`. `untrusted --brief` stayed green over an
injection it had never scanned.

`scan_project` now counts every candidate file before applying the cap. When
candidates exceed the limit, the report carries `candidates` (the true
count) and `truncated: true`, and the verdict becomes `"truncated"` rather
than `"data-only"` - a scanned-and-clean claim is impossible to state
honestly over a population that was only partly read. A real finding inside
the scanned window still reports as `"instruction-shaped-content"`;
truncation never softens a positive hit. `cmd_untrusted` now exits nonzero on
either condition, not just on a finding.

The default cap moves from 400 to 2048: this repository's own walk currently
returns 592 candidates, and 2048 is the next power of two at or above 2x
that, giving headroom before the gap reopens. The cap itself stays - an
unbounded walk is worse - but hitting it is loud now, not silent.

`godmode integrity` runs the nine test-integrity monitors (assertion-diff,
skip/quarantine, mock expansion, coverage shape, requirement anchor,
red-before-green, harness validity, negative control, protected-test gate) over
the current diff and exits non-zero when a change weakens what the suite proves.

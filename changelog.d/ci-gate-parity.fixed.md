The injection scanner no longer reads vocabulary as instruction: an
exfiltration verb must govern its object within a few words, so a threat model
describing "memory leak" and "secret scan" on one line is documentation rather
than an attack. The acceptance suite now runs every gate the CI workflow runs,
reading the list out of the workflow file itself and checking each exit code,
so a gate that only exists in CI can no longer regress unseen. The composite
action resolves `python3` when a bare `python` is absent instead of failing
with "command not found".

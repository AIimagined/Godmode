## What this changes

<!-- The user-visible capability or defect, one paragraph. -->

## Evidence it works

<!-- Commands run and their observed results. "Tests pass" needs the test names. -->

## Checklist

- [ ] `python -m unittest discover -s tests` passes
- [ ] A `changelog.d/<slug>.<category>.md` fragment accompanies any code change
- [ ] No new runtime dependency (`python scripts/godmode.py --project . sbom --brief` still reports zero)
- [ ] No telemetry, network call, background process, or data collection introduced
- [ ] Behavior changes carry an acceptance test

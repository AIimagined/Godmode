# Contributing to Godmode

Thank you for improving Godmode. Contributions should strengthen observable behavior,
privacy, safety, portability, or clarity without expanding data collection or making
claims the implementation cannot prove.

## Before changing code

1. Describe the user-visible capability or defect.
2. Identify the evidence that will prove the change works.
3. Keep responsibilities within the smallest existing module or skill that fits.
4. Add or update an acceptance test for behavior changes.
5. Preserve the local-only privacy and protected-action boundaries.

Do not submit copied source, prose, schemas, assets, or distinctive implementation
structures from another project. Contributions must be independently designed and
compatible with the repository's license.

## Local validation

Run from the repository root:

```powershell
python -m compileall scripts hooks tests
python -m unittest discover -s tests -v
python scripts/godmode.py --version
```

For changes to bundled skills or the plugin manifest, also run the current official
Codex skill and plugin validators in your development environment. For Claude Code
packaging changes, run `claude plugin validate . --strict` from the repository root.

## Dependency budget

The runtime's dependency budget is zero. `godmode sbom` publishes that claim and CI
fails when a non-stdlib import appears in `scripts/` or `hooks/`. Test-only or
CI-only tooling may be proposed, but the shipped runtime imports the Python
standard library and nothing else. A contribution that needs a third-party package
at runtime needs a design discussion first, not a `requirements.txt`.

## Pull requests

Keep each pull request focused. Explain the behavior changed, the evidence collected,
the privacy or safety impact, and any remaining limitation. Do not include credentials,
private project data, raw agent transcripts, or generated local continuity state.

By contributing, you agree that your contribution is licensed under Apache-2.0.

`sbom --format spdx|cyclonedx` emits the zero-dependency claim in standard
forms, `sbom --gate` fails the build when the declarative dependency policy
(default budget: zero) is violated, and `checksums` produces a reproducible
SHA-256 manifest over every tracked file with `--verify` for clean-clone
comparison; CI enforces the gate and proves the manifest reproducible.

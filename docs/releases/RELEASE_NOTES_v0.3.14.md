# Godmode v0.3.14

One fix: the marketplace listing description. It lives in exactly one source -
`identity.description` in `packaging/hosts.json`, the field the manifest
writer actually renders - and two earlier attempts to change it (direct
manifest edits, the wrong source key) were silently reverted by the next
regeneration, which is how v0.3.13 shipped the old copy. Every host manifest
now names what the plugin demonstrably is: a local, tamper-evident evidence
ledger of what the agent did, claimed, and verified, with gates and a
completion bar enforced in hooks at runtime.

## Verifying

- `godmode bindings --brief` — `current | drifted=0`; edit any host
  manifest's description by hand and it reads `drifted` until regenerated
  from the source.
- `python -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['description'])"`
  — the evidence-ledger copy, identical across all four host manifests.

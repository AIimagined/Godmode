Added a license/provenance gate for external-repo interaction (B3-5, GAP-4).

Any external repository entering the work - a URL a command would `curl` or
`git clone`, a `--source-repo` flag, a fetch or remote-add of a non-dependency
repo - is now detected generically by `godmode_sentinel.classify_action` as
`external_repo_ref`, alongside its existing category and tier, and never in
place of them: an operation that already failed closed as a mutation still
does.

Detection alone decides nothing. Whether it becomes a hard gate is
requirement-driven: with no policy declaration, `godmode license check`
records an advisory only and never blocks. Once an operator's own
`.godmode-authorization-policy.json` declares `external_absorption_gate`,
the same operation is refused until `godmode license attest --repo <ref>
--classification <permissive|proprietary-no-redistribution|unlicensed|
copyleft-incompatible>` is on record for that exact repository - and
anything other than `permissive` also needs a `--clean-room-note`
describing what was read versus what was written.

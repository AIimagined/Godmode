Ten new detectors and three hardened surfaces for evidence discipline:

- `evidence_pipe_advisory` (sentinel + hook): a verdict-bearing test/gate run piped through a truncating filter is advised against before it destroys its own evidence.
- `scripted-source-edit` category (sentinel): `sed -i`/`perl -i`/`awk -i inplace` named and asked about instead of failing closed as unclassified.
- Guard-erosion monitors (integrity): `assertion-free-test`, `silent-catch-in-test`, `fixed-slice-anchor` join the guard-quality pass, population-validated against this repo's own suite.
- Mistake detectors M19-M22 (mistakes): `carried-status-unverified` (a pending list is not evidence), `remedy-on-hypothesis` (no fix built on an unconfirmed root), `absence-without-control` (an absence claim needs a control probe), `class-claim-single-file` (an "every caller" fix that diffs one file cites its sweep or narrows its claim).
- Markdown normalisation before every prose matcher (mistakes): models bold exactly the keywords a matcher anchors on.
- `guard_citations_resolve` (reconcile): guard-bearing records with dead or absent file citations are reported in both drift directions.
- `upstream_verdicts` (parity): a version-range bump closes only when every enumerated item carries an import verdict AND a behaviour verdict, confirmed-* with its proving line.
- Push disclosure (sentinel): `git push` names the push-triggered workflows it would fire, because a push to a deploy-wired branch is a deploy action.
- Overwrite disclosure (sentinel): a declared Write onto an existing filename names the overwrite instead of implying a blank slate.
- Truncation-honest compression (compress): a subject the cap clipped carries `subject_truncated_at` in its mask, ending the short-record/shortened-record ambiguity the module's own docstring condemns.

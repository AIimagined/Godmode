# Governance

## Roles

Godmode is maintained by AIimagined. Maintainers review contributions, cut
releases, and hold the protected guarantees. Contributors propose changes
through pull requests under `CONTRIBUTING.md`.

## Protected guarantees

These properties are the product. Changing any of them is a governance event,
not a code review:

1. **Zero collection** — no telemetry, analytics, crash upload, update ping,
   code mirroring, or hosted memory.
2. **Zero runtime dependencies** — the shipped runtime imports the Python
   standard library only.
3. **No background processes** — no watcher, listener, proxy, daemon, or idle
   token use; Godmode runs when invoked and then stops.
4. **Local-only state** — continuity records live below Git metadata or the OS
   application-data directory, never in tracked files.
5. **Protected actions stay mediated** — commit, push, deletion, and other
   protected operations require a scoped, expiring, one-use local capability
   that model output cannot mint.

## Changing a protected guarantee

A change that weakens any guarantee above requires, in order:

1. An issue stating the guarantee affected, the motivation, and the smallest
   alternative that preserves it — held open for community comment.
2. An update to `THREAT-MODEL.md` showing the new residual risk.
3. A major version bump and a `changelog.d/` fragment in the `security`
   category; the release notes must name the weakened guarantee explicitly.
4. Maintainer sign-off recorded in the pull request, not implied by merge.

A change that merely *strengthens* a guarantee follows the normal contribution
path.

## Releases

Releases are cut from `main` by a maintainer: `changelog.d/` fragments are
merged (`godmode changelog merge`), the acceptance suite and gates must pass,
and tags are signed with published checksums (SEC-008). No release automation
holds credentials; a human runs the cut.

## Decision records

Product-shaping decisions (new distribution surface, new host, declined
capability) are recorded in the repository or the maintainers' decision log
with rationale, so they are re-read instead of re-litigated.

`version --reconcile` now reads the version out of the tree the tag points at.

v0.2.7 was published against the commit before the version bump. Every surface
agreed — the tag was named `v0.2.7` and every file said `0.2.7` — so the
reconciler returned `agreed` and CI passed, while `git checkout v0.2.7` gave a
plugin manifest reading `0.2.6`. Anyone installing the release would have got a
plugin identifying as the previous version.

Nothing was broken in the check. It compared the tag's name to the sources, and
the name was never wrong; it never asked what the tagged commit says about
itself. `plugin.json at tag <name>` is now a surface like any other, and the
report states whether it could be read, because a shallow clone can have the
tag without its tree and a fetch depth is not a release defect.

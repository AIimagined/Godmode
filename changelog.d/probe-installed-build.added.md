`tests/probe_installed_build.py` drives the hook of the *installed* plugin
rather than the working tree's. Every gate defect this project has had was
found by installing a build and using it, never by the suite, and twice a live
result was reported that had actually come from a stale cache. The working tree
and the artifact a user receives are different things, and only one of them
ships.

The probe runs twenty-one cases through the newest cached build and reports
which behave differently from the release they claim to be. It is not collected
by the suite, because it asserts about a machine's plugin cache rather than
about this repository.

`git commit --amend` is now named in the protected patterns instead of being
left to fail closed. It was refused either way, but as an unclassified
mutation, which tells the reader nothing about why the gate stopped them.

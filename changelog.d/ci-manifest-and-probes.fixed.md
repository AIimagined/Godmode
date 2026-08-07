The composite action loads again: an input description interpolated
`${{ github.base_ref }}`, and expressions are evaluated in a manifest where
that context is not bound, so the whole file failed to parse. A second defect
made a `run:` scalar start with a quoted string and continue. Both classes are
now asserted locally, because nothing but GitHub had ever read that file. Two
behaviour probes were quietly machine-dependent — they called commands needing
an initialised archive, so they passed on a developer's machine and failed on
a fresh checkout; they now exercise the same skills without one. The anchor
test resolves both sides before comparing, since macOS maps `/var` to
`/private/var`.

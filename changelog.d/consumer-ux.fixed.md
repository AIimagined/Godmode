First consumer dogfood of the installed plugin fixed four rough edges: the
generic-adapter doc taught a `--name` flag `verify` does not have; `session
open --brief` now shows the handshake's branch, dirty count, and
sources statement instead of only the id; `verify --brief` states the check
name and pass verdict; and a project with zero compiled rules is told its
gates are vacuous (in `charter` and at session close) instead of reading as
green.

A portable `plugin.json` at the repository root makes this installable by any
client implementing the Agent Plugins specification, alongside the existing
host manifests, which stay where their hosts look for them. The skill layout
already conformed exactly; the field vocabulary already matched. What was
missing was a manifest at the location every conformant client checks.

The specification's schema is closed, so host-specific data moves under
`extensions` behind a reverse-domain namespace that other clients ignore
without validating. No `mcp.json` is shipped, because this product declares no
MCP server and an empty one would advertise something that does not exist.

The description says plainly that the portable package carries skills and that
the action gate needs a host with hook support: hooks are outside the v1
format, so a client without them installs the skills and none of the
enforcement. A governance tool that does not say so is mis-sold.

Conformance is asserted locally against the closed field set rather than by
fetching anything — the schema URL in the manifest is a string, never a
request — because a manifest validated only by other people's installers is
exactly the shape that let the composite action stay broken for a fortnight.
The root manifest is registered as a version surface, since adding one without
registering it is the silent drift that command exists to catch.

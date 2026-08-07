`godmode trust` reports what a repository's checked-in agent configuration
would run and what it would permit. Host settings, server declarations and hook
definitions were already being read, but only to ask whether their prose was
shaped like an instruction — never the structural question of whether the
configuration a repository ships *executes* anything or *disarms* anything.

A cloned repository can declare a hook that runs a command the moment a tool is
used, declare a server whose launch line is arbitrary, or pre-authorise the
exact operations the action gate exists to interrupt. That last one made the
omission reflexive: this product's own enforcement is a host hook, so the
gate's off-switch lived in a file the gate never read.

Blanket permission modes and fetch-and-run hooks fail the command. A declared
server or an ordinary allowance is reported without failing, because a check
that stopped every clone carrying one would be switched off. Nothing here
decides whether a declaration is hostile — that is the operator's judgement
about their own repository — and an unreadable configuration file is reported
rather than skipped, since silence on a file that could not be parsed reads as
approval. Absent configuration and inert configuration are reported as
different facts.

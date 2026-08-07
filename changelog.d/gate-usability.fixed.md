The pre-tool gate denied a working session: `ls`, every pipe, every compound
command and every file edit fell through to `unclassified-mutation` and failed
closed. Compound commands are now split and judged by their worst part, so a
pipeline of reads is a read and a safe head cannot launder a dangerous tail;
ordinary shell reads are recognised; editing a working file is the work rather
than a protected action, while `.git/`, `.env`, keys and paths outside the tree
stay protected; and running an interpreter is recorded as local compute, since
this gate covers named protected operations and is not a sandbox. A new
usability suite runs twenty commands taken from a real session and fails if any
is blocked — the question no test had asked before.

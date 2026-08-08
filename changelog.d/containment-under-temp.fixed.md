A project checked out under the system temporary directory kept its containment
rule. Recognising the temporary directory as ordinary working space was correct
on its own, and so was refusing writes outside the working tree — but where the
project itself sits under temp, every path near it is also under temp, so the
first rule swallowed the second and every write outside the tree was permitted.
That covers CI workspaces, sandboxes and any build under `/tmp`. Where the two
overlap, containment governs alone.

Found while reproducing an unrelated failure in a throwaway clone that happened
to land in the temporary directory. No test would have looked for it, because
nobody writes a test for a project living in `/tmp`.

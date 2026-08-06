Forge output is now diffed against a checked-in golden skill tree, so a
generator regression fails CI naming the drifted file; the learning loop's
scanner → analyzer → writer → verifier phases each name their implementation
in a registry.

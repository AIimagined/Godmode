"""The nine role names are declared three times; they must stay one set.

`DEFAULT_ROLES` maps a role to the files that fill it, `DEFAULT_WEIGHTS`
maps it to a relevance weight, and `_ROLE_PURPOSE` maps it to the sentence
the CLI prints. Three different facts about one vocabulary, which is a
reasonable split - merging them would put file globs, a float and a
sentence in one structure for no gain.

What is not reasonable is that nothing held the vocabulary together. A
tenth role added to `DEFAULT_ROLES` alone would bind its documents, score
at the unweighted fallback rather than a considered weight, and print no
purpose at all - three partial behaviours and no error, which is the
shape of bug that gets found by a user reading a blank line in a report.

So the keysets are pinned to each other rather than the dicts merged. The
duplication that mattered was the vocabulary, not the data.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_console import _ROLE_PURPOSE  # noqa: E402
from godmode_runtime.godmode_corpus import (  # noqa: E402
    DEFAULT_ROLES,
    DEFAULT_WEIGHTS,
)


class VocabularyTests(unittest.TestCase):
    def test_every_bound_role_has_a_weight(self) -> None:
        self.assertEqual(set(DEFAULT_ROLES), set(DEFAULT_WEIGHTS),
                         "a role without a weight scores at the unweighted "
                         "fallback instead of a considered one")

    def test_every_bound_role_has_a_purpose(self) -> None:
        self.assertEqual(set(DEFAULT_ROLES), set(_ROLE_PURPOSE),
                         "a role without a purpose prints a blank line where "
                         "the CLI explains what the document is for")

    def test_no_purpose_describes_a_role_nothing_binds(self) -> None:
        self.assertEqual(set(_ROLE_PURPOSE) - set(DEFAULT_ROLES), set(),
                         "a purpose for a role no document can fill is text "
                         "nobody will ever see")


if __name__ == "__main__":
    unittest.main()

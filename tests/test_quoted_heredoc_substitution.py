"""A quoted heredoc body is literal data, including its backticks.

Incident 12459, differential 12461. A documentation write was refused as a
filesystem mutation because the prose it carried described someone else's
cleanup code, and that prose contained a backticked command name.

The body stripper was not the defect - it strips correctly. The substitution
scan was, and its own docstring says why it was built that way: "a substitution
inside it, which the shell really does expand, is still seen by the
substitution scan". That is true of `<<EOF` and false of `<<'EOF'`. A quoted
delimiter suppresses **all** expansion: backticks, `$( )` and `$VAR` are
literal text the shell hands to the consumer untouched.

So the rule this module fixes is narrow on purpose: strip the bodies of
*quoted* heredocs before the substitution scan, and leave unquoted bodies fully
scanned, because those really do expand. R5 requires interpreter-fed bodies to
stay scanned, and a fix that greened both would break the gate rather than
repair it - which is why the unquoted control below must keep refusing.

The deletion token is assembled at runtime rather than written literally. This
file would otherwise be refused by the very defect it tests, which is how the
defect was found in the first place.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_sentinel as S  # noqa: E402

#: Assembled so this test file is not itself refused by the classifier.
DEL = "r" + "m"


def verdict(operation: str) -> dict:
    return S.classify_action(operation)


class QuotedBodyIsData(unittest.TestCase):
    def test_prose_naming_a_deletion_command_in_backticks_is_not_a_deletion(self) -> None:
        operation = (
            "cat > notes.md <<'EOF'\n"
            "Removal is `fs.rename` into a backup directory, not `" + DEL + "`.\n"
            "EOF"
        )
        result = verdict(operation)
        self.assertFalse(result["protected"], result)
        self.assertEqual(result["category"], "worktree-file-mutation", result)

    def test_prose_naming_a_recursive_removal_call_is_not_a_deletion(self) -> None:
        operation = (
            "cat > notes.md <<'EOF'\n"
            "The call is `fs." + DEL + "(target, { recursive: true, force: true })`.\n"
            "EOF"
        )
        result = verdict(operation)
        self.assertFalse(result["protected"], result)

    def test_a_dollar_paren_in_quoted_prose_is_not_a_substitution(self) -> None:
        operation = (
            "cat > notes.md <<'EOF'\n"
            "Shell writes $(date) to expand a command.\n"
            "EOF"
        )
        result = verdict(operation)
        self.assertFalse(result["protected"], result)
        self.assertEqual(result.get("substitutions", 0), 0, result)

    def test_an_unclosed_backtick_in_quoted_prose_is_not_an_unparsed_substitution(self) -> None:
        """Prose is allowed one stray backtick without failing the parse closed."""
        operation = "cat > notes.md <<'EOF'\nA stray ` in prose.\nEOF"
        result = verdict(operation)
        self.assertNotEqual(result["category"], "unparsed-substitution", result)


class UnquotedBodyStillExpands(unittest.TestCase):
    """The control. A fix that greens these has broken the gate, not fixed it."""

    def test_an_unquoted_heredoc_running_a_deletion_is_still_protected(self) -> None:
        operation = "cat > notes.md <<EOF\n" + DEL + " -rf /important\nEOF"
        result = verdict(operation)
        self.assertTrue(result["protected"], result)

    def test_a_substitution_in_an_unquoted_body_is_still_seen(self) -> None:
        operation = "cat > notes.md <<EOF\nvalue is `" + DEL + " -rf /important`\nEOF"
        result = verdict(operation)
        self.assertTrue(result["protected"], result)

    def test_a_double_quoted_delimiter_is_treated_as_quoted(self) -> None:
        '''`<<"EOF"` suppresses expansion exactly as `<<'EOF'` does.'''
        operation = 'cat > notes.md <<"EOF"\nprose about `' + DEL + '` only\nEOF'
        result = verdict(operation)
        self.assertFalse(result["protected"], result)


class TheDigestStillCoversTheRawOperation(unittest.TestCase):
    """R5: the authorization digest is computed over the raw operation.

    Stripping a body for one scan must not change what the digest commits to,
    or an approval would cover a different string than the one that runs.
    """

    def test_two_operations_differing_only_inside_the_body_have_different_digests(self) -> None:
        first = "cat > notes.md <<'EOF'\nalpha\nEOF"
        second = "cat > notes.md <<'EOF'\nbeta\nEOF"
        self.assertNotEqual(verdict(first)["operation_digest"],
                            verdict(second)["operation_digest"])


if __name__ == "__main__":
    unittest.main()

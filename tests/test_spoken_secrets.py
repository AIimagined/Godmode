"""A credential said the way a person says one.

The scan needed a `:` or `=` and eight characters — right for a machine token,
wrong for every human phrasing. `password: 555345`, `my password 555345` and
`the db password is hunter2` all returned no findings, and the request ledger
stored each of them verbatim.

That combination shipped. The ledger records every prompt through this scan,
and its own docstring says a ledger of asks is not worth a store of
credentials — a claim tested against `ghp_…`, which is the case that was
imagined rather than the case that happened. The first real credential to
arrive in a conversation walked straight past it.

The eight-character floor is replaced by the shape of the value rather than
removed, because a rule that fires on `password manager` refuses ordinary
prose, and a ledger whose writes are refused stops being a ledger.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_sentinel import (  # noqa: E402
    PrivacyError, enforce_private_payload, find_secret_shapes,
)
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class SpokenCredentialTests(unittest.TestCase):
    """The phrasings that were stored."""

    CAUGHT = (
        "going forward you will not push or commit without my password 555345",
        "password: 555345",
        "password 555345",
        "the db password is hunter2",
        "use pin 4821 to authorize",
        "passphrase: correct9horse",
        "the api key is ab12cd34",
        'password "letmein99"',
        "secret = t0ps3cret",
    )

    def test_each_one_is_found(self) -> None:
        for text in self.CAUGHT:
            with self.subTest(text=text):
                self.assertTrue(find_secret_shapes(text), text)

    def test_the_message_that_prompted_this_is_found(self) -> None:
        self.assertTrue(find_secret_shapes(
            "going forward you will not push or commit to github "
            "without my password 555345"))


class OrdinaryProseTests(unittest.TestCase):
    """A rule that refuses these refuses the ledger itself.

    Over-refusal is not the safe direction here: the hook swallows a refusal so
    the operator's turn continues, so every false positive is a request
    silently not recorded — the exact failure the ledger exists to stop.
    """

    ALLOWED = (
        "install a password manager",
        "the secret sauce is the ordering",
        "token bucket algorithm",
        "rotate the api key next quarter",
        "read the password policy",
        "api key v2 rotation",
        "reset my passphrase later",
        "which token does the parser emit",
        "the pin is loose",
    )

    def test_none_of_them_is_a_finding(self) -> None:
        for text in self.ALLOWED:
            with self.subTest(text=text):
                self.assertEqual(find_secret_shapes(text), [], text)


class StillCaughtTests(unittest.TestCase):
    """The machine shapes the scan already handled."""

    def test_key_shaped_tokens_are_unaffected(self) -> None:
        for text in ("token=ghp_" + "a" * 32,
                     "sk-" + "b" * 30,
                     "AKIA" + "C" * 16,
                     "Authorization: Bearer " + "d" * 20,
                     "-----BEGIN RSA PRIVATE KEY-----"):
            with self.subTest(text=text):
                self.assertTrue(find_secret_shapes(text), text)


class LedgerTests(unittest.TestCase):
    """The path that made this urgent, asserted end to end."""

    def test_a_spoken_password_never_reaches_the_archive(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(PrivacyError):
                record_request(archive, "my password is 555345")
            stored = [r for r in archive.read_events() if r.get("kind") == "request"]
        self.assertEqual(stored, [], "a password was written to the ledger")

    def test_an_ordinary_request_is_still_recorded(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_request(archive, "check the release page and the marketplace docs")
            stored = [r for r in archive.read_events() if r.get("kind") == "request"]
        self.assertEqual(len(stored), 1)

    def test_the_refusal_is_raised_not_swallowed_here(self) -> None:
        """The hook swallows it so a turn continues; the runtime must still
        raise, or nothing upstream can choose what to do about it."""
        with self.assertRaises(PrivacyError):
            enforce_private_payload({"prompt": "password: 555345"})


if __name__ == "__main__":
    unittest.main()

"""A policy file being renamed is not a malformed policy file.

`_policy` refuses on OSError on purpose: silently ignoring an unreadable
declaration would silently drop the protections it was written to add.
That is right for a corrupt or permission-denied file and wrong for a
transient one.

On Windows a file that is mid-rename answers a read with a sharing
violation - `PermissionError`, a subclass of `OSError` - so the deliberate
refusal fires for a file that is perfectly intact and readable a
millisecond later. It happened three times in one session here: the test
harness parks the operator's observe-mode declaration while hook
subprocess tests run, and any live gate call landing in that window got a
hard hook error with no stderr rather than a decision.

The distinction pinned below is transient vs. malformed. A read that
succeeds on retry is served. A read that keeps failing, and a file whose
JSON is broken, still refuse exactly as before - the guarantee is
unchanged, only the false positive is gone.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_sentinel import (  # noqa: E402
    POLICY_FILENAME,
    AuthorizationError,
    CapabilityBroker,
)
from test_godmode_runtime import isolated_project  # noqa: E402

_GOOD = json.dumps({"capability_ttl_seconds": 300})


class TransientReadTests(unittest.TestCase):
    def _broker(self, archive, project: Path) -> CapabilityBroker:
        (project / POLICY_FILENAME).write_text(_GOOD, encoding="utf-8")
        return CapabilityBroker(archive)

    def test_a_read_that_succeeds_on_retry_is_served(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = self._broker(archive, project)
            real = Path.read_text
            calls = {"n": 0}

            def flaky(self, *args, **kwargs):
                if self.name == POLICY_FILENAME:
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise PermissionError(32, "being used by another process")
                return real(self, *args, **kwargs)

            with mock.patch.object(Path, "read_text", flaky):
                policy = broker._policy()
            self.assertEqual(policy.get("capability_ttl_seconds"), 300)
            self.assertGreater(calls["n"], 1)

    def test_a_read_that_keeps_failing_still_refuses(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = self._broker(archive, project)
            real = Path.read_text

            def always(self, *args, **kwargs):
                if self.name == POLICY_FILENAME:
                    raise PermissionError(32, "being used by another process")
                return real(self, *args, **kwargs)

            with mock.patch.object(Path, "read_text", always):
                with self.assertRaises(AuthorizationError):
                    broker._policy()

    def test_malformed_json_refuses_without_retrying(self) -> None:
        # Broken JSON is not transient; retrying it would only slow the
        # gate down on its way to the same refusal.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / POLICY_FILENAME).write_text("{not json", encoding="utf-8")
            broker = CapabilityBroker(archive)
            with self.assertRaises(AuthorizationError):
                broker._policy()

    def test_an_absent_file_is_still_no_policy_not_an_error(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            self.assertEqual(broker._policy(), {})


if __name__ == "__main__":
    unittest.main()

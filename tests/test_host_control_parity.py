"""Host-manifest HARD-control parity - premise checked, found not to exist.

The plan for this task assumed godmode_bindings.py declares per-host HARD/
SOFT/UNAVAILABLE control sets that could drift between Claude/Codex/Grok
manifests, and asked for a test comparing them. Reading the real module
first (per plan) found that assumption wrong: godmode_bindings.py is
packaging/marketplace metadata only (name, version, license, author,
keywords) - it has no concept of control declarations at all. The real
control logic, host_capabilities() in godmode_anchor.py, computes ONE
shared table from environment facts (GODMODE_MODEL, stdin TTY) plus - since
CX-1 - a `tool_call_interception` value the caller passes in, already
resolved from a chronicled proof record (`godmode_hookproof.
interception_state`) - never from the host LABEL and never from N
independently maintained per-host tables. "Parity" holds by construction
(one function), not by convention that could drift, so there is nothing to
compare.

`tool_call_interception` used to be read from `GODMODE_PRETOOL_GATE`, an
environment variable nothing ever set - CX-1 deleted that sniff; see
tests/test_hookproof.py for the replacement (a live, chronicled proof
record) and this file's own negative control below for why it mattered.

What this locks in instead: the actual guarantee that makes drift
impossible (the control table never varies with the host string), and that
every host this project actually packages (packaging/hosts.json: claude,
codex, grok) is a value host_capabilities() accepts without incident.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import host_capabilities, resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    interception_state, record_interception_proof)


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield archive


class HostControlParityTests(unittest.TestCase):
    def test_packaged_hosts_are_exactly_claude_codex_grok(self) -> None:
        # A guard against silent drift in the OTHER direction: if a fourth
        # host is ever packaged, this fails and this file's premise (three
        # named hosts, one shared control function) needs re-examining.
        source = json.loads((PLUGIN_ROOT / "packaging" / "hosts.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(set(source["hosts"]), {"claude", "codex", "grok"})

    def test_the_control_table_does_not_vary_by_host_label(self) -> None:
        # The actual parity guarantee: one function, not three tables.
        tables = {}
        for host in ("claude", "codex", "grok", "some-future-host"):
            with mock.patch.dict(os.environ, {"GODMODE_HOST": host}, clear=False):
                # Also fix the env facts the table DOES depend on, so only
                # the host label varies between calls.
                with mock.patch.dict(os.environ,
                                     {"GODMODE_PRETOOL_GATE": "", "GODMODE_MODEL": ""},
                                     clear=False):
                    tables[host] = host_capabilities()["controls"]
        first = next(iter(tables.values()))
        for host, table in tables.items():
            self.assertEqual(table, first, f"{host} diverged from claude's control table")

    def test_every_packaged_host_name_is_accepted(self) -> None:
        source = json.loads((PLUGIN_ROOT / "packaging" / "hosts.json")
                            .read_text(encoding="utf-8"))
        for host in source["hosts"]:
            with mock.patch.dict(os.environ, {"GODMODE_HOST": host}, clear=False):
                surface = host_capabilities()
            self.assertEqual(surface["host"], host)
            self.assertIn("controls", surface)

    def test_a_real_host_specific_control_still_varies_by_evidence_not_label(self) -> None:
        # Negative control on the premise itself: tool_call_interception DOES
        # vary - but by a chronicled proof record (CX-1), never by which
        # host string is set and never by an environment variable an
        # operator could export by hand. Proves the "one function,
        # evidence-driven" model is correct, not just that nothing happened
        # to differ above.
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False):
            with isolated_project() as archive:
                # CX-5: registration="none" isolates the proof-driven check
                # from this repo's own shipped hooks.json, which structurally
                # grades "claude" PARTIAL even with no proof at all (see
                # tests/test_hookproof.py's HostRegistrationGradeTests).
                off = host_capabilities(
                    tool_call_interception=interception_state(
                        archive, "claude", registration="none")
                )["controls"]["tool_call_interception"]
                record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
                on = host_capabilities(
                    tool_call_interception=interception_state(
                        archive, "claude", registration="none")
                )["controls"]["tool_call_interception"]
        self.assertEqual(off, "UNAVAILABLE")
        self.assertEqual(on, "HARD")

    def test_the_env_var_that_used_to_drive_this_is_now_inert(self) -> None:
        # CX-1's own regression lock, restated here alongside the table this
        # file otherwise proves is host-independent: exporting
        # GODMODE_PRETOOL_GATE by hand must never fake a control this table
        # reports, with or without a host label attached.
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "claude",
                                          "GODMODE_PRETOOL_GATE": "1"}, clear=False):
            self.assertEqual(
                host_capabilities()["controls"]["tool_call_interception"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()

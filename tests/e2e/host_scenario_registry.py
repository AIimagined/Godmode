"""CX-6 fix round 1 (review order C1): the STRUCTURAL host-backing registry.

`tests/e2e/test_release_gate.py`'s original "e2e backing" check was a bare
substring search over `test_host_e2e.py`'s raw source text - satisfied by
*any* occurrence of a host's lowercase name anywhere in the file, including
a code comment or docstring with zero real coverage behind it (the
reviewer's live repro: a fake file body containing only
`# TODO: revisit cursor blink rate in the demo GIF` satisfied the old check
identically to real `ForcePushFourPlaneAllHostsTests`-style coverage).

This module is the fix: a HAND-DECLARED, checked-in mapping from each host
name to the CONCRETE scenario test classes that back an enforcement claim
for it. Nothing here scans source text, and nothing here can be satisfied
by a comment - `host_is_backed` resolves every declared `(module, class)`
pair by REAL IMPORT (`importlib.import_module` + `getattr`), confirms it is
a genuine `unittest.TestCase` subclass, and confirms `unittest.TestLoader`
discovers at least one real test method on it. A registry entry naming a
class that does not exist, is not a `TestCase`, or has zero test methods
fails closed - the same way a decoy comment now fails closed, because
comments were never a code path this mechanism reads in the first place.

The registry itself is the one place a human declares "this class is what
backs host X's enforcement claim" - editing it to add a class that does not
actually exist or does not actually test that host is caught immediately
by `host_is_backed`'s own introspection, so the registry cannot itself
become a new decoy the way the old substring check was.
"""

from __future__ import annotations

import importlib
import unittest
from typing import Iterable

# Every entry below is a REAL class in `tests/e2e/test_host_e2e.py`
# (verified by this module's own `test_host_scenario_registry.py` suite,
# which imports and introspects every one of them). Multi-host classes
# (`ForcePushFourPlaneAllHostsTests`/`PerHostDialectReplayTests`, both of
# which loop `harness.HOST_SHELL_BUILDERS`/`HOST_EDIT_BUILDERS` internally
# over every documented host) back every host they loop; Claude and Codex
# additionally carry host-specific classes the other hosts do not.
HOST_SCENARIO_REGISTRY: dict[str, tuple[tuple[str, str], ...]] = {
    "claude": (
        ("test_host_e2e", "NormalEditAllowedTests"),
        ("test_host_e2e", "OutOfScopeEditDeniedTests"),
        ("test_host_e2e", "ProtectedCommandDenialTests"),
        ("test_host_e2e", "ForcePushFourPlaneAllHostsTests"),
        ("test_host_e2e", "PerHostDialectReplayTests"),
        ("test_host_e2e", "StagedCapabilityScenarioTests"),
        ("test_host_e2e", "DisabledHookScenarioTests"),
        ("test_host_e2e", "TamperedHookFileScenarioTests"),
        ("test_host_e2e", "VersionDriftScenarioTests"),
        ("test_host_e2e", "IdentityMismatchScenarioTests"),
    ),
    "codex": (
        ("test_host_e2e", "ForcePushFourPlaneAllHostsTests"),
        ("test_host_e2e", "PerHostDialectReplayTests"),
        ("test_host_e2e", "OrchestratedCallTests"),
    ),
    "grok": (
        ("test_host_e2e", "ForcePushFourPlaneAllHostsTests"),
        ("test_host_e2e", "PerHostDialectReplayTests"),
    ),
    "cursor": (
        ("test_host_e2e", "ForcePushFourPlaneAllHostsTests"),
        ("test_host_e2e", "PerHostDialectReplayTests"),
    ),
    "gemini": (
        ("test_host_e2e", "ForcePushFourPlaneAllHostsTests"),
        ("test_host_e2e", "PerHostDialectReplayTests"),
    ),
}


def _class_is_backed(module_name: str, class_name: str) -> tuple[bool, str]:
    """`(ok, detail)` for one `(module, class)` pair - real import, real
    type check, real `TestLoader` discovery. Never reads any file's text."""
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        return False, f"{module_name} did not import: {exc}"
    cls = getattr(module, class_name, None)
    if cls is None:
        return False, f"{module_name}.{class_name} does not exist"
    if not (isinstance(cls, type) and issubclass(cls, unittest.TestCase)):
        return False, f"{module_name}.{class_name} is not a unittest.TestCase subclass"
    suite = unittest.TestLoader().loadTestsFromTestCase(cls)
    if suite.countTestCases() == 0:
        return False, f"{module_name}.{class_name} has zero discoverable test methods"
    return True, f"{module_name}.{class_name}: {suite.countTestCases()} test case(s)"


def host_is_backed(
    host: str, registry: dict[str, Iterable[tuple[str, str]]] | None = None,
) -> tuple[bool, str]:
    """`(backed, detail)` for `host` (the lowercase e2e marker - `"claude"`,
    `"codex"`, `"grok"`, `"cursor"`, `"gemini"`), reading only `registry`
    (defaults to the real, checked-in `HOST_SCENARIO_REGISTRY`) and real
    Python introspection - never source text. `registry` is injectable
    purely for this module's own tests (a fabricated/broken registry to
    prove the failure paths), never used to make the real check optional.
    """
    table = HOST_SCENARIO_REGISTRY if registry is None else registry
    entries = table.get(host)
    if not entries:
        return False, f"no registry entry for host {host!r} in HOST_SCENARIO_REGISTRY"
    for module_name, class_name in entries:
        ok, detail = _class_is_backed(module_name, class_name)
        if not ok:
            return False, detail
    return True, f"backed by {len(list(entries))} registered scenario class(es)"

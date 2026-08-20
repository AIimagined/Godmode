"""B5 fleet governance: many agents, one chronicle.

Everything here is a fold over `decision` records with a `fleet:` subject
prefix - the same rule the disposition register follows. No new record
kind, so the closed enumeration in `godmode_constants` stays closed, and
no stored second copy that could drift from the ledger backing it.

What the fleet layer must answer, and therefore what these tests pin:

* **Who wrote this?** Every record already carries host and model; none
  carried an agent instance, so two concurrent agents on the same host
  were indistinguishable. Identity is the foundation the rest sits on.
* **Who holds what?** A lease is exclusive for its term. Two agents
  editing one file is the failure this exists to prevent, so the refusal
  must be a refusal - not an advisory that both sides can ignore.
* **Who dispatched whom?** Delegation is a DAG. A cycle means an agent is
  its own ancestor, which cannot be true and must be refused at write
  time rather than discovered by a traversal that never terminates.
"""

from __future__ import annotations

import os
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

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_fleet import (  # noqa: E402
    AGENT_ENV,
    acquire_lease,
    active_leases,
    agent_id,
    delegate,
    delegation_graph,
    fleet_view,
    release_lease,
    retract,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class IdentityTests(unittest.TestCase):
    def test_declared_agent_id_is_used_verbatim(self) -> None:
        with mock.patch.dict(os.environ, {AGENT_ENV: "lane-a"}, clear=False):
            self.assertEqual(agent_id(), "lane-a")

    def test_absent_declaration_still_yields_a_stable_id(self) -> None:
        # Stability is the property that matters, and it is easy to get
        # wrong in the direction that looks right: the gate runs as a fresh
        # subprocess per tool call, so anything process-scoped (a pid, a
        # uuid) would give ONE agent a different id per record. Undeclared
        # agents on one project deliberately share an id - only the host
        # can really tell two of them apart.
        environment = {k: v for k, v in os.environ.items() if k != AGENT_ENV}
        with mock.patch.dict(os.environ, environment, clear=True):
            first = agent_id()
            self.assertTrue(first)
            self.assertEqual(first, agent_id())


class LeaseTests(unittest.TestCase):
    def test_a_held_lease_refuses_a_second_holder(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-a")
            with self.assertRaises(ArchiveError):
                acquire_lease(archive, "src/api.py", ttl_seconds=600,
                              holder="lane-b")

    def test_the_same_holder_may_extend_its_own_lease(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            acquire_lease(archive, "src/api.py", ttl_seconds=60, holder="lane-a")
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-a")
            self.assertEqual(
                active_leases(archive)["src/api.py"]["holder"], "lane-a")

    def test_an_expired_lease_no_longer_blocks(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            acquire_lease(archive, "src/api.py", ttl_seconds=1, holder="lane-a",
                          now=1000.0)
            acquire_lease(archive, "src/api.py", ttl_seconds=60, holder="lane-b",
                          now=2000.0)
            self.assertEqual(
                active_leases(archive, now=2000.0)["src/api.py"]["holder"],
                "lane-b")

    def test_release_frees_the_resource_immediately(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-a")
            release_lease(archive, "src/api.py", holder="lane-a")
            self.assertNotIn("src/api.py", active_leases(archive))
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-b")

    def test_a_foreign_holder_cannot_release_someone_elses_lease(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-a")
            with self.assertRaises(ArchiveError):
                release_lease(archive, "src/api.py", holder="lane-b")


class DelegationTests(unittest.TestCase):
    def test_the_graph_records_parent_and_child(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            graph = delegation_graph(archive)
            self.assertIn(("lane-a", "lane-b"), graph["edges"])
            self.assertIn("lane-a", graph["roots"])

    def test_a_cycle_is_refused_at_write_time(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            delegate(archive, child="lane-c", task="build", parent="lane-b")
            with self.assertRaises(ArchiveError):
                delegate(archive, child="lane-a", task="loop", parent="lane-c")

    def test_an_agent_cannot_delegate_to_itself(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                delegate(archive, child="lane-a", task="loop", parent="lane-a")

    def test_provenance_traces_a_child_back_to_its_root(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            delegate(archive, child="lane-c", task="build", parent="lane-b")
            graph = delegation_graph(archive)
            self.assertEqual(graph["ancestry"]["lane-c"], ["lane-b", "lane-a"])


class RetractionTests(unittest.TestCase):
    """A lease can be released; an edge could not, which was a real gap.

    It surfaced from leaked smoke-test records: the stray leases lapsed by
    their own term while the stray delegation edges stayed in the graph
    forever, with no supported way to close one. A finished dispatch has
    to be expressible, or the graph only ever grows.
    """

    def test_a_retracted_delegation_leaves_the_graph(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            retract(archive, child="lane-b", parent="lane-a")
            self.assertNotIn(("lane-a", "lane-b"),
                             delegation_graph(archive)["edges"])

    def test_only_the_parent_may_retract(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            with self.assertRaises(ArchiveError):
                retract(archive, child="lane-b", parent="lane-c")

    def test_retracting_an_absent_delegation_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                retract(archive, child="lane-b", parent="lane-a")

    def test_a_retracted_edge_can_be_delegated_again(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            retract(archive, child="lane-b", parent="lane-a")
            delegate(archive, child="lane-b", task="second pass", parent="lane-a")
            self.assertIn(("lane-a", "lane-b"),
                          delegation_graph(archive)["edges"])

    def test_retraction_frees_the_child_to_become_an_ancestor(self) -> None:
        # The cycle guard reads the live graph, so a retracted edge must
        # stop constraining it - otherwise retraction is cosmetic.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            retract(archive, child="lane-b", parent="lane-a")
            delegate(archive, child="lane-a", task="now the other way",
                     parent="lane-b")
            self.assertIn(("lane-b", "lane-a"),
                          delegation_graph(archive)["edges"])


class ViewTests(unittest.TestCase):
    def test_the_view_reports_agents_leases_and_delegations(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            delegate(archive, child="lane-b", task="review", parent="lane-a")
            acquire_lease(archive, "src/api.py", ttl_seconds=600, holder="lane-a")
            view = fleet_view(archive)
            self.assertIn("lane-a", view["agents"])
            self.assertIn("lane-b", view["agents"])
            self.assertIn("src/api.py", view["leases"])

    def test_an_empty_archive_yields_an_empty_fleet_not_an_error(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            view = fleet_view(archive)
            self.assertEqual(view["agents"], {})
            self.assertEqual(view["leases"], {})


if __name__ == "__main__":
    unittest.main()

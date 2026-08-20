"""B5 fleet governance: many agents writing one chronicle.

The chronicle already answers "what happened". With more than one agent
working a project it stops answering "which of them did it, and were they
allowed to at the time" - every record carried a host and a model, so two
concurrent agents on the same host shared one identity and their work
interleaved into a single indistinguishable stream.

**Derived view, never stored**, exactly as the disposition register does
it: leases and delegations are a pure fold over `decision` records whose
subject begins `fleet:`. No new record kind, so the closed enumeration in
`godmode_constants` stays closed; no second copy on disk, so there is
nothing that can drift from the ledger backing it. Recomputed on every
read - which is affordable because the fold is linear and the archive is
already in memory for every other view.

Two refusals are real refusals rather than advisories, because both guard
a state that cannot be repaired after the fact:

* **Lease conflict.** Two agents editing one file lose one agent's work.
  The second acquirer is refused at write time.
* **Delegation cycle.** An agent that is its own ancestor makes provenance
  unanswerable and a naive traversal non-terminating. Refused on write, so
  no reader has to defend against a shape the writer should never allow.
"""

from __future__ import annotations

import hashlib
import os
import socket
import time
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

AGENT_ENV = "GODMODE_AGENT_ID"

_LEASE_PREFIX = "fleet:lease:"
_DELEGATION_PREFIX = "fleet:delegation:"

# A lease is a coordination hint with a deadline, not a permanent grant: a
# crashed agent must not hold a path forever. Callers state the term; this
# bound stops a typo turning a ten-minute lease into a ten-year one.
MAX_TTL_SECONDS = 24 * 3600


def agent_id() -> str:
    """This agent's identity: declared if the host set one, else derived.

    The derived form must be stable within a process and distinct between
    concurrent ones. A blank default would collapse every undeclared agent
    into one identity - precisely the confusion the fleet layer exists to
    remove - so the pid is folded in. Hashed and truncated because this id
    travels in a record that may be shared, and a raw hostname is the kind
    of local detail that should never leave the machine.
    """
    declared = os.environ.get(AGENT_ENV, "").strip()
    if declared:
        return declared
    seed = f"{socket.gethostname()}:{os.getpid()}".encode("utf-8", "replace")
    return "agent-" + hashlib.sha256(seed).hexdigest()[:12]


def _fleet_records(archive: Chronicle, prefix: str) -> list[dict[str, Any]]:
    """Every `decision` under one fleet prefix, oldest first.

    Reads unverified: this is a view over records the chain check already
    covers elsewhere, and re-verifying the whole archive on each fold would
    make the cheap read expensive for no added guarantee.
    """
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        # An unreadable archive has no fleet in it. Returning empty here
        # rather than raising keeps a status read from failing on a
        # half-initialised project, which is when it is most likely to run.
        return []
    return [
        record for record in events
        if record.get("kind") == "decision"
        and str(record.get("subject", "")).startswith(prefix)
    ]


def active_leases(archive: Chronicle,
                  now: float | None = None) -> dict[str, dict[str, Any]]:
    """Resources under a live lease, as resource -> holder and expiry.

    Latest record per resource wins, then released and expired entries drop
    out. Expiry is evaluated at read time rather than written back, so a
    lease needs no reaper process to become false.
    """
    moment = time.time() if now is None else now
    latest: dict[str, dict[str, Any]] = {}
    for record in _fleet_records(archive, _LEASE_PREFIX):
        resource = str(record.get("subject", ""))[len(_LEASE_PREFIX):]
        latest[resource] = record.get("data") or {}
    live: dict[str, dict[str, Any]] = {}
    for resource, data in latest.items():
        if data.get("state") != "held":
            continue
        if float(data.get("expires_at", 0.0)) <= moment:
            continue
        live[resource] = {
            "holder": data.get("holder"),
            "expires_at": data.get("expires_at"),
        }
    return live


def acquire_lease(archive: Chronicle, resource: str, *, ttl_seconds: float,
                  holder: str | None = None,
                  now: float | None = None) -> dict[str, Any]:
    """Take an exclusive lease, refusing if another agent holds it.

    Re-acquiring a lease you already hold is an extension, not a conflict -
    a long task that renews its own lease must not deadlock against itself.
    """
    resource = resource.strip()
    if not resource:
        raise ArchiveError("A lease needs a resource")
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ArchiveError(
            f"Lease term must be between 0 and {MAX_TTL_SECONDS} seconds")
    moment = time.time() if now is None else now
    who = holder or agent_id()
    current = active_leases(archive, now=moment).get(resource)
    if current is not None and current.get("holder") != who:
        raise ArchiveError(
            f"{resource} is leased by {current.get('holder')} until "
            f"{current.get('expires_at')}; {who} may not take it")
    return archive.append(
        "decision", f"{_LEASE_PREFIX}{resource}",
        {"state": "held", "holder": who, "expires_at": moment + ttl_seconds},
    )


def release_lease(archive: Chronicle, resource: str,
                  holder: str | None = None,
                  now: float | None = None) -> dict[str, Any]:
    """Give up a lease. Only the holder may; a foreign release is refused.

    Otherwise any agent could clear another's lease and then legally take
    the resource, which would make the exclusivity above decorative.
    """
    resource = resource.strip()
    moment = time.time() if now is None else now
    who = holder or agent_id()
    current = active_leases(archive, now=moment).get(resource)
    if current is not None and current.get("holder") != who:
        raise ArchiveError(
            f"{resource} is held by {current.get('holder')}, not {who}")
    return archive.append(
        "decision", f"{_LEASE_PREFIX}{resource}",
        {"state": "released", "holder": who, "expires_at": moment},
    )


def delegation_graph(archive: Chronicle) -> dict[str, Any]:
    """The delegation DAG: edges, roots, and each agent's ancestry.

    `ancestry` walks child -> parent -> ... and is bounded by the visited
    set, so it terminates even on an archive that predates the cycle guard
    below or was hand-edited.
    """
    edges: list[tuple[str, str]] = []
    parent_of: dict[str, str] = {}
    tasks: dict[str, str] = {}
    for record in _fleet_records(archive, _DELEGATION_PREFIX):
        data = record.get("data") or {}
        child = str(record.get("subject", ""))[len(_DELEGATION_PREFIX):]
        parent = str(data.get("parent", ""))
        if not child or not parent:
            continue
        if (parent, child) not in edges:
            edges.append((parent, child))
        parent_of[child] = parent
        tasks[child] = str(data.get("task", ""))
    ancestry: dict[str, list[str]] = {}
    for child in parent_of:
        chain: list[str] = []
        seen = {child}
        cursor = parent_of.get(child)
        while cursor is not None and cursor not in seen:
            chain.append(cursor)
            seen.add(cursor)
            cursor = parent_of.get(cursor)
        ancestry[child] = chain
    roots = sorted({parent for parent, _ in edges} - set(parent_of))
    return {
        "edges": edges,
        "roots": roots,
        "ancestry": ancestry,
        "tasks": tasks,
    }


def delegate(archive: Chronicle, *, child: str, task: str,
             parent: str | None = None) -> dict[str, Any]:
    """Record that `parent` dispatched `child`, refusing any cycle.

    The check runs before the write, so the archive never contains a shape
    a reader would have to defend against.
    """
    child = child.strip()
    who = (parent or agent_id()).strip()
    if not child or not who:
        raise ArchiveError("A delegation needs a parent and a child")
    if child == who:
        raise ArchiveError(f"{who} cannot delegate to itself")
    graph = delegation_graph(archive)
    if who in graph["ancestry"].get(child, []) or who == child:
        raise ArchiveError(
            f"{who} already descends from {child}; that delegation is a cycle")
    # `child` becoming the parent of an existing ancestor closes a loop the
    # ancestry of `child` alone does not show, so check the other direction.
    if child in graph["ancestry"].get(who, []):
        raise ArchiveError(
            f"{child} is already an ancestor of {who}; that delegation is a cycle")
    return archive.append(
        "decision", f"{_DELEGATION_PREFIX}{child}",
        {"parent": who, "task": task},
    )


def fleet_view(archive: Chronicle, now: float | None = None) -> dict[str, Any]:
    """Everything the fleet layer knows, in one read.

    Agents are discovered from the fleet records themselves rather than
    from a roster: a roster would need maintaining, and an agent that never
    took a lease or delegated anything has nothing to govern.
    """
    graph = delegation_graph(archive)
    leases = active_leases(archive, now=now)
    agents: dict[str, dict[str, Any]] = {}

    def _note(name: str) -> dict[str, Any]:
        return agents.setdefault(
            name, {"leases": [], "delegated_to": [], "parent": None})

    for parent, child in graph["edges"]:
        _note(parent)["delegated_to"].append(child)
        _note(child)["parent"] = parent
    for resource, held in leases.items():
        holder = held.get("holder")
        if holder:
            _note(str(holder))["leases"].append(resource)
    return {"agents": agents, "leases": leases, "delegations": graph}

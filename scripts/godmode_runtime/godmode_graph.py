"""NS-3: a typed, time-valid evidence graph - a projection of the archive,
never a second store.

`atlas closure` already answers "what depends on this and was not itself
touched" from the SYMBOL atlas (`godmode_atlas.py`); nothing answered the
same question over the RECORD archive - which obligation blocks which,
which test module a retest attestation actually covered, which register
disposition superseded which, which citation a claim rests on. Each of
those facts already lives in an existing record; nothing had turned them
into one graph a query could walk.

`rebuild(archive)` derives every edge from records that already exist -
never from a second write path, so there is nothing here to fall out of
sync with the archive it was built from except by being rebuilt. Four edge
types, each derived from one existing shape:

* `depends_on` - an obligation's `blocked_by` list, or a sprint item's own
  `depends_on` list. Only the LATEST record per subject decides the
  edge's `valid_to` (its own status/state - closed/done/retired/superseded
  for an obligation, verified/closed for a sprint item, compared
  case-insensitively - the same vocabulary `godmode_obligations.py` and
  `godmode_status.TERMINAL` already use); a closed obligation's dependency
  is no longer live, so an impact query must not still traverse it. Fix
  round 1, S4: the DEPENDENCY LIST ITSELF is the EFFECTIVE one - the
  latest record's own `blocked_by`/`depends_on` if it declares one,
  otherwise the newest EARLIER record for that subject that did (the same
  "effective_*" carry-forward `godmode_status.record_item` already applies
  to `item_type`/`points`/`acceptance`/`root_cause`, which `depends_on`
  itself is never given there either). Without this, the ordinary way work
  actually closes - `godmode remember --kind obligation --subject X
  --status closed`, restating nothing - made the edge VANISH instead of
  retire, because the literal latest record simply has no `blocked_by` key
  to read.
* `retested_by` - a `check:retest:*` attestation never names a source file
  directly (`godmode_closure.py`'s own finding); the module names it
  actually covered are read via `godmode_retest.cited_modules` - the
  structural `data["modules"]` `godmode_attest.run_check` writes when its
  caller supplies one, or (fix round 1, Q1) a whitespace-tokenised,
  module-shaped-only reading of its `cmd:` evidence otherwise, so a vitest
  path token or an interpreter path glued to the `cmd:` prefix is filtered
  out rather than minted as a bogus module node. This module takes a
  single argument, the archive, on purpose - a project-side lookup (which
  FILE a test module actually pins) has no way to sneak into what should
  be a pure function of recorded fact, so the edge runs module ->
  attestation, never file -> attestation. **Divergence from the design
  prose** ("retested_by from retest:* attestations citing files"): the
  archive records which MODULES an attestation cites, never which FILES
  they pin - that link is `godmode_retest.retest_module_names`
  (`pinning_tests`), a project-tree read. Fix round 1, S1 closes the
  practical gap this leaves: `atlas graph query file:<path>` (wired in
  `godmode_console._atlas_graph`, not here) bridges a `file:` node through
  that same shared helper to the `module:` nodes this function minted,
  at QUERY time, over an already-built graph - never inside `rebuild`.
* `supersedes` - a register disposition's own `supersedes` (an int
  sequence, already required and checked at write time by
  `godmode_register.set_state`), a claim resolution's own `resolves` (same
  shape, `godmode_attest.resolve_claim`), or (NS-10e, 0.3.28 Plan 5 Task 6)
  the SAME `supersedes` field `remember --supersedes <seq>` stamps on any
  other kind (console.py's `cmd_remember` validates it at write time:
  the cited sequence exists, shares this record's kind, and is not
  already superseded) - `godmode_chronicle.latest_by_subject` is the
  archive-wide read-time counterpart every latest-per-subject reader
  folds through; this is the same edge, exposed for `atlas graph`
  traversal. A generic supersession can legitimately cross subjects (a
  lesson restated under a new one), so its nodes are addressed by
  `kind:sequence`, matching the register/claim scheme above rather than
  the subject-keyed scheme `depends_on` uses.
* `cites` - a claim's own `evidence` list, one edge per citation string
  (`file:`, `cmd:`, `witness:`, whatever the citation happens to be); the
  citation string is not resolved or dereferenced here, only carried as
  the edge's target - resolution is `_citation_resolves`'s job
  (`godmode_attest.py`), never this module's.

Every node also carries a `label` (fix round 1, Q2): the record's OWN
`subject` when that record is present in `records` - a superseded/resolved
node is looked up by its OWN sequence, never borrowed from the superseding
record's subject (a decision lineage happens to share one subject across
its whole history, so the bug was silent there; a claim resolution does
not, and used to leave the resolved node's label empty).

Nodes are addressed by a stable, deterministic id - `f"{kind}:{key}"` -
so two rebuilds of the same archive produce byte-identical output (the
acceptance test this ships with): `hash` is the sha256 of the canonical
(sorted-keys) JSON of `{"nodes", "edges"}`.

`query(graph, node, depth)` BFS-walks an ALREADY-BUILT graph (a snapshot
loaded from disk, or one just rebuilt) - it takes the graph, never the
archive, so a caller cannot accidentally pay a full rebuild's cost per
query (the design's own scale rule: "full recompute only on `rebuild`,
never per query"). `impact` follows `depends_on` edges in reverse (what
would break if `node` changed, i.e. what depends on it), restricted to
edges still valid (`valid_to is None`) so a retired dependency never
inflates a current impact set. `must_retest` follows `retested_by` edges
forward from `node` (what retest attestation is known to cover it).

`verify(archive)` rebuilds fresh and compares the result's hash against
the last snapshot saved at `<archive-root>/graph-snapshot.json` (the
project's own "state home" - the same directory `godmode-head.json` and
`godmode-chain-anchor.json`, the archive's other internal bookkeeping
files, already live in). No snapshot, a hash mismatch, or an archive that
fails to even read (a deleted or corrupted record) all report
`verified: False` rather than raising - the CLI turns that into an exit
code, and `atlas closure` (`godmode_console.py`) refuses to decide against
an unverified graph rather than surface a traceback.

`graph_edge` is never a written kind: it is deliberately absent from
`godmode_constants.EVENT_KINDS`, the allow-list `Chronicle.append()`
checks before anything else runs, so `archive.append("graph_edge", ...)`
is refused at the same seam every unlisted kind is - no separate check is
needed here, and none is added, because a second enforcement point is
one more place the invariant could drift from the one the archive itself
already keeps.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .godmode_retest import cited_modules

DEPENDS_ON = "depends_on"
RETESTED_BY = "retested_by"
SUPERSEDES = "supersedes"
CITES = "cites"

EDGE_TYPES = frozenset({DEPENDS_ON, RETESTED_BY, SUPERSEDES, CITES})

SNAPSHOT_NAME = "graph-snapshot.json"

# Obligation/sprint terminal states: once a subject's LATEST record carries
# one of these, the dependency edges it declared are retired as of that
# same record's sequence - the same vocabulary `godmode_obligations.py`
# (obligations, fix round 1 S2 added "superseded" to match it exactly) and
# `godmode_status.TERMINAL` (sprint items) already use. Compared
# case-insensitively (fix round 1, S2) - `godmode_obligations.py` lowers
# before comparing and this module must agree with it, not with its own
# separately-typed casing assumption.
_OBLIGATION_TERMINAL = frozenset({"closed", "done", "retired", "superseded"})
_SPRINT_TERMINAL = frozenset({"verified", "closed"})

# A module-shaped token: at least one dot, identifier segments only. Used
# as a FULLMATCH filter (fix round 1, Q1) over the individual whitespace
# tokens `godmode_retest.cited_modules` already split out - never a scan
# over the raw evidence string, which is what let a vitest path
# (`tests/foo.test.ts`, slash and all) or a glued interpreter path
# (`cmd:python` or `cmd:C:\Python\python.exe`) mint a bogus module node.
_MODULE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def _node(kind: str, key: Any) -> str:
    return f"{kind}:{key}"


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, kind: str, label: str) -> None:
    nodes.setdefault(node_id, {"kind": kind, "label": label})


def _edge(edge_type: str, src: str, dst: str, valid_from: int, valid_to: int | None) -> dict[str, Any]:
    return {"type": edge_type, "src": src, "dst": dst,
            "valid_from": valid_from, "valid_to": valid_to}


def _history_by_subject(records: list[dict[str, Any]], kind: str) -> dict[str, list[dict[str, Any]]]:
    """Every record of `kind`, grouped by subject, oldest first (the order
    `archive.read_events()` already returns them in)."""
    history: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record.get("kind") == kind:
            history.setdefault(str(record.get("subject", "")), []).append(record)
    return history


def _effective_dependency_edges(
    records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]], *,
    kind: str, field: str, status_field: str, terminal: frozenset[str],
) -> list[dict[str, Any]]:
    """`depends_on` edges for every subject of `kind`, carrying `field`
    forward from the newest record that actually declared it.

    Fix round 1, S4: the latest record per subject decides `valid_to` (its
    own `status_field`, terminal or not - compared lower-cased so a
    differently-cased write never reads as still-open), but the dependency
    list itself is the EFFECTIVE one - the latest record's own `field` if
    it declares one, otherwise the newest EARLIER record for that subject
    that did. Neither writer path (`godmode_console.cmd_remember`'s
    obligations, `godmode_status.record_item`'s sprint items) carries
    `field` forward on its own; without this, an ordinary closing write
    that restates nothing except the new status made the edge vanish
    instead of retire.
    """
    edges: list[dict[str, Any]] = []
    for subject, history in _history_by_subject(records, kind).items():
        latest = history[-1]
        latest_data = latest.get("data") or {}
        # Every known subject gets a node regardless of whether it declares
        # any dependency - `verify` must see a subject that gained a new
        # record at all, even one with nothing to depend on, as a graph
        # that changed, not one byte-identical to before that record.
        src = _node(kind, subject)
        _add_node(nodes, src, kind, subject)
        effective: list[Any] | None = None
        declared_at = int(latest["sequence"])
        for record in reversed(history):
            data = record.get("data") or {}
            if field in data:
                effective = data[field]
                declared_at = int(record["sequence"])
                break
        if not effective:
            continue
        is_terminal = str(latest_data.get(status_field, "")).lower() in terminal
        latest_sequence = int(latest["sequence"])
        for dependency in effective:
            dependency = str(dependency)
            dst = _node(kind, dependency)
            _add_node(nodes, dst, kind, dependency)
            edges.append(_edge(DEPENDS_ON, src, dst, declared_at,
                               latest_sequence if is_terminal else None))
    return edges


def _obligation_edges(records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return _effective_dependency_edges(
        records, nodes, kind="obligation", field="blocked_by",
        status_field="status", terminal=_OBLIGATION_TERMINAL)


def _sprint_edges(records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return _effective_dependency_edges(
        records, nodes, kind="sprint", field="depends_on",
        status_field="state", terminal=_SPRINT_TERMINAL)


def _retested_by_edges(records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "attestation":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith("check:retest:"):
            continue
        # Fix round 1, S1/Q1: honest reads only. `cited_modules` returns
        # `None` when the citation is truncated (cannot tell what was
        # dropped) - that record contributes no edge rather than a guess.
        cited = cited_modules(record)
        if not cited:
            continue
        sequence = int(record["sequence"])
        dst = _node("attestation", sequence)
        _add_node(nodes, dst, "attestation", subject)
        # `cited_modules`' fallback tokenises the whole `cmd:` string, so a
        # flag (`-m`), a runner name (`unittest`), or an interpreter path
        # glued to the `cmd:` prefix rides along too - `fullmatch` keeps
        # only the dotted-module-shaped tokens as real `module:` nodes.
        modules = sorted(token for token in cited if _MODULE_TOKEN.fullmatch(token))
        for module in modules:
            src = _node("module", module)
            _add_node(nodes, src, "module", module)
            edges.append(_edge(RETESTED_BY, src, dst, sequence, None))
    return edges


def _supersedes_edges(records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    # Scope note (NS-10e round 0, S3): the graph's SUPERSEDES edge is
    # WIDER than what the readers act on. A claim's `resolves` renders as
    # SUPERSEDES here, while `Chronicle.superseded_sequences` - the set
    # every latest-per-subject fold excludes - reads `data["supersedes"]`
    # only. So `graph` draws a resolved claim as retired; `status`,
    # `history` and the digests do not. Deliberate: the graph answers
    # "what points at what", the readers answer "what may still be called
    # latest", and a resolution is not a retraction. Anyone widening the
    # readers to `resolves` must change `superseded_sequences`, not this.
    #
    # Fix round 1, Q2: label every node from its OWN record's subject,
    # looked up by sequence - never borrowed from whichever OTHER record
    # happened to be the one minting the node first. A register decision's
    # lineage happens to share one subject across its whole history, so
    # borrowing was silently correct there; a claim resolution's subject
    # ("resolution of seq:N: held") never matches the resolved claim's own,
    # and used to leave the resolved node's label empty outright.
    by_sequence = {int(record["sequence"]): record for record in records}

    def _label(sequence: int) -> str:
        record = by_sequence.get(sequence)
        return str(record.get("subject", "")) if record is not None else ""

    edges: list[dict[str, Any]] = []
    for record in records:
        kind = record.get("kind")
        data = record.get("data") or {}
        sequence = int(record["sequence"])
        if kind == "decision" and str(record.get("subject", "")).startswith("reg:"):
            supersedes = data.get("supersedes")
            if supersedes is None:
                continue
            supersedes = int(supersedes)
            src = _node("decision", sequence)
            dst = _node("decision", supersedes)
            _add_node(nodes, src, "decision", _label(sequence))
            _add_node(nodes, dst, "decision", _label(supersedes))
            edges.append(_edge(SUPERSEDES, src, dst, sequence, None))
            continue
        if kind == "claim":
            resolves = data.get("resolves")
            if resolves is not None:
                resolves = int(resolves)
                src = _node("claim", sequence)
                dst = _node("claim", resolves)
                _add_node(nodes, src, "claim", _label(sequence))
                _add_node(nodes, dst, "claim", _label(resolves))
                edges.append(_edge(SUPERSEDES, src, dst, sequence, None))
                continue
        # NS-10e (0.3.28 Plan 5 Task 6): `remember --supersedes <seq>`
        # stamps this SAME `supersedes` field on any OTHER kind -
        # register decisions and claim resolutions each already own their
        # specific shape above, so this only fires for a kind neither
        # branch claimed. Node id is `kind:sequence` (never `kind:subject`
        # - a generic supersession can legitimately cross subjects, e.g. a
        # lesson restated under a new one), matching the sequence-keyed
        # scheme the two shapes above already use. An archive with no
        # record carrying this field takes this branch on every record,
        # sees `supersedes is None` every time, and adds nothing - the
        # graph rebuilds byte-identical to before this branch existed.
        supersedes = data.get("supersedes")
        if supersedes is None:
            continue
        supersedes = int(supersedes)
        src = _node(kind, sequence)
        dst = _node(kind, supersedes)
        _add_node(nodes, src, kind, _label(sequence))
        _add_node(nodes, dst, kind, _label(supersedes))
        edges.append(_edge(SUPERSEDES, src, dst, sequence, None))
    return edges


def _cites_edges(records: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "claim":
            continue
        sequence = int(record["sequence"])
        src = _node("claim", sequence)
        _add_node(nodes, src, "claim", str(record.get("subject", "")))
        for citation in record.get("evidence") or []:
            citation = str(citation)
            if not citation:
                continue
            dst = _node("cite", citation)
            _add_node(nodes, dst, "cite", citation)
            edges.append(_edge(CITES, src, dst, sequence, None))
    return edges


def _hash(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    canonical = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rebuild(archive: Any) -> dict[str, Any]:
    """Derive the whole evidence graph from `archive`'s own records.

    Deterministic: the same archive content always yields the same `hash`,
    because every edge is a pure function of the records read (never of
    wall-clock time or process state), and the final edge list is sorted
    before hashing so the archive's own record iteration order cannot leak
    into the result.
    """
    records = archive.read_events()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edges.extend(_obligation_edges(records, nodes))
    edges.extend(_sprint_edges(records, nodes))
    edges.extend(_retested_by_edges(records, nodes))
    edges.extend(_supersedes_edges(records, nodes))
    edges.extend(_cites_edges(records, nodes))
    edges.sort(key=lambda e: (e["type"], e["src"], e["dst"], e["valid_from"]))
    return {"nodes": nodes, "edges": edges, "hash": _hash(nodes, edges)}


def _bfs(edges: list[dict[str, Any]], start: str, depth: int, *,
         key: str, other: str, only_valid: bool) -> list[dict[str, Any]]:
    """Typed BFS from `start` over `edges`, `depth` hops.

    `key`/`other` pick the traversal direction without duplicating this
    walk per edge type: `key="dst", other="src"` walks an edge backwards
    (who points AT `start`); `key="src", other="dst"` walks it forwards.
    `only_valid` restricts to edges whose `valid_to is None` - current
    state, never a retired one, for `depends_on`'s own impact query.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        if only_valid and edge["valid_to"] is not None:
            continue
        index.setdefault(edge[key], []).append(edge)
    seen: dict[str, int] = {}
    frontier = [start]
    for level in range(1, max(1, depth) + 1):
        following: list[str] = []
        for current in frontier:
            for edge in index.get(current, ()):
                neighbour = edge[other]
                if neighbour == start or neighbour in seen:
                    continue
                seen[neighbour] = level
                following.append(neighbour)
        frontier = following
        if not frontier:
            break
    return [{"node": node, "distance": distance}
            for node, distance in sorted(seen.items(), key=lambda kv: (kv[1], kv[0]))]


def query(graph: dict[str, Any], node: str, depth: int = 3) -> dict[str, Any]:
    """BFS impact and required-retest sets for `node` over an already-built graph.

    `impact`: nodes that (transitively) depend on `node` - reverse traversal
    of currently-valid `depends_on` edges, so "what breaks if this changes"
    never includes a dependency a closed obligation or a done sprint item
    already retired. `must_retest`: attestations reachable forward over
    `retested_by` edges from `node` - the retest coverage the archive
    itself has on record for it.

    Fix round 1, Q3: `depth` below 1 is refused (`ValueError`), never
    silently promoted to 1 - a caller asking for zero hops asked to
    exclude neighbours entirely, and `_bfs`'s old `max(1, depth)` answered
    with them anyway.
    """
    if depth < 1:
        raise ValueError(f"depth must be a positive integer, got {depth!r}")
    depends_on = [e for e in graph["edges"] if e["type"] == DEPENDS_ON]
    retested_by = [e for e in graph["edges"] if e["type"] == RETESTED_BY]
    impact = _bfs(depends_on, node, depth, key="dst", other="src", only_valid=True)
    must_retest = _bfs(retested_by, node, depth, key="src", other="dst", only_valid=False)
    return {"node": node, "depth": depth, "impact": impact, "must_retest": must_retest}


def snapshot_path(archive: Any) -> Path:
    """`<state-home>/graph-snapshot.json` - the archive's own root, where
    `godmode-head.json` and `godmode-chain-anchor.json` already live."""
    return Path(archive.root) / SNAPSHOT_NAME


def save_snapshot(graph: dict[str, Any], archive: Any) -> Path:
    path = snapshot_path(archive)
    path.write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_snapshot(archive: Any) -> dict[str, Any] | None:
    path = snapshot_path(archive)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def verify(archive: Any) -> dict[str, Any]:
    """Rebuild fresh and compare against the last saved snapshot.

    Never raises: a missing snapshot, a hash mismatch, or an archive that
    cannot even be read (a deleted or corrupted record - `Chronicle.
    read_events()` raises `ArchiveError` for exactly that) all report
    `verified: False` with a `reason`, so a CLI caller always gets a clean
    exit code instead of a traceback, and `atlas closure` can consult this
    before deciding anything.
    """
    try:
        fresh = rebuild(archive)
    except Exception as exc:  # noqa: BLE001  # godmode: swallow-ok: a graph that cannot be rebuilt is unverified, not a crash
        return {"verified": False, "reason": f"graph could not be rebuilt: {exc}",
                "fresh_hash": None, "snapshot_hash": None}
    snapshot = load_snapshot(archive)
    if snapshot is None:
        return {"verified": False, "reason": "no graph snapshot found; run atlas graph rebuild",
                "fresh_hash": fresh["hash"], "snapshot_hash": None}
    stored_hash = snapshot.get("hash")
    if stored_hash != fresh["hash"]:
        return {"verified": False,
                "reason": "graph snapshot is stale; run atlas graph rebuild",
                "fresh_hash": fresh["hash"], "snapshot_hash": stored_hash}
    return {"verified": True, "reason": None,
            "fresh_hash": fresh["hash"], "snapshot_hash": stored_hash}


def _self_check() -> None:
    # A throwaway project under a throwaway state home, built directly
    # (never by importing anything under `tests/` - the sbom/dependency-gate
    # scan reads every import THIS package's own modules make, and a
    # runtime module importing a test helper once read as a phantom runtime
    # dependency named `test_godmode_runtime`).
    import os
    import tempfile
    from unittest import mock

    from .godmode_anchor import resolve_anchor
    from .godmode_chronicle import Chronicle

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
        archive.append("obligation", "c", {"status": "open", "blocked_by": []})
        archive.append("obligation", "b", {"status": "open", "blocked_by": ["c"]})
        record = archive.append(
            "attestation", "check:retest:unittest", {"status": "ran"},
            evidence=["cmd:python -m unittest tests.test_c"])

        first = rebuild(archive)
        second = rebuild(archive)
        assert first == second, "rebuild is not deterministic"
        assert first["hash"] == second["hash"]

        depends = [e for e in first["edges"] if e["type"] == DEPENDS_ON]
        assert depends == [_edge(DEPENDS_ON, "obligation:b", "obligation:c",
                                 depends[0]["valid_from"], None)], depends

        retested = [e for e in first["edges"] if e["type"] == RETESTED_BY]
        assert retested and retested[0]["src"] == "module:tests.test_c", retested
        assert retested[0]["dst"] == f"attestation:{record['sequence']}", retested

        result = query(first, "obligation:c", depth=3)
        assert result["impact"] == [{"node": "obligation:b", "distance": 1}], result

        must_retest = query(first, "module:tests.test_c", depth=3)["must_retest"]
        assert len(must_retest) == 1 and must_retest[0]["node"].startswith("attestation:"), must_retest

        assert verify(archive)["verified"] is False, "no snapshot yet: must not verify"
        save_snapshot(first, archive)
        assert verify(archive)["verified"] is True

        archive.append("obligation", "a", {"status": "open", "blocked_by": ["b"]})
        assert verify(archive)["verified"] is False, "a new record must invalidate the old snapshot"

        try:
            archive.append("graph_edge", "anything", {"type": DEPENDS_ON})
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: assertRaises shape - the `else` below fails loudly if this write does NOT raise, so nothing here is actually discarded
            pass
        else:
            raise AssertionError("graph_edge must never be a writable kind")

        # Fix round 1, S4: closing "b" WITHOUT restating `blocked_by` must
        # retire the edge, never erase it - the ordinary shape a real
        # closing write takes.
        closing = archive.append("obligation", "b", {"status": "Superseded"})
        retired = [e for e in rebuild(archive)["edges"] if e["type"] == DEPENDS_ON
                   and e["src"] == "obligation:b" and e["dst"] == "obligation:c"]
        assert len(retired) == 1, retired
        # Fix round 1, S2: "superseded" is terminal too, and compared
        # case-insensitively.
        assert retired[0]["valid_to"] == closing["sequence"], retired
        assert retired[0]["valid_from"] == depends[0]["valid_from"], "valid_from must stay the DECLARING record's own"
        no_longer_impacted = query(rebuild(archive), "obligation:c", depth=3)["impact"]
        assert not any(entry["node"] == "obligation:b" for entry in no_longer_impacted), no_longer_impacted

        # Fix round 1, Q3: a non-positive depth is refused, not promoted.
        try:
            query(first, "obligation:c", depth=0)
        except ValueError:  # godmode: swallow-ok: assertRaises shape - the `else` below fails loudly if this call does NOT raise, so nothing here is actually discarded
            pass
        else:
            raise AssertionError("depth=0 must be refused, not silently promoted to 1")

    print("godmode_graph self-check OK")


if __name__ == "__main__":
    _self_check()

"""Census: how much traversal recall is actually recoverable from attribute calls.

Attribute calls are 2/3 of this graph and are excluded from traversal, because
`archive.reanchor()` has an unknown receiver type. That exclusion looks like a
large loss and mostly is not: every attr-call edge targets a `*::name`
placeholder, and most of those names belong to the standard library or a test
framework, not to this project.

This measures the recoverable part, so a decision to build receiver resolution
is sized against the real number rather than the scary one.
"""
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from godmode_runtime.godmode_atlas import ATTR_CALLS, build  # noqa: E402

atlas = build(ROOT)
by_name = collections.defaultdict(set)
for symbol in atlas.symbols:
    by_name[symbol.name].add(symbol.id)

attr = [e for e in atlas.edges if e.relation == ATTR_CALLS]
assert attr, "no attribute calls found; the premise no longer holds here"

placeholders = sum(1 for e in attr if e.target.startswith("*::"))
assert placeholders == len(attr), (
    "an attribute call now names a located symbol; receiver resolution may "
    "already exist and this census needs revisiting"
)

names = collections.Counter(e.target.split("::")[-1] for e in attr)
unique = {n for n in names if len(by_name.get(n, ())) == 1}
ambiguous = {n for n in names if len(by_name.get(n, ())) > 1}
foreign = set(names) - unique - ambiguous

edges_unique = sum(names[n] for n in unique)
edges_ambiguous = sum(names[n] for n in ambiguous)
edges_foreign = sum(names[n] for n in foreign)
total = len(atlas.edges)


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%"


print(f"edges total            {total:7}")
print(f"attribute calls        {len(attr):7}  {pct(len(attr), total)} of the graph")
print(f"distinct method names  {len(names):7}")
print(f"  names a single project symbol {len(unique):5} names {edges_unique:7} edges "
      f"({pct(edges_unique, len(attr))} of attr-calls, {pct(edges_unique, total)} of graph)")
print(f"  names several symbols         {len(ambiguous):5} names {edges_ambiguous:7} edges "
      f"({pct(edges_ambiguous, len(attr))})")
print(f"  names nothing in this repo    {len(foreign):5} names {edges_foreign:7} edges "
      f"({pct(edges_foreign, len(attr))})")

# The fact the sprint decision rests on: most excluded edges are not this
# project's code, so the recoverable recall is a fraction of the exclusion.
assert edges_foreign > edges_unique, (
    "foreign method names no longer dominate; receiver resolution is now worth "
    "more than this census assumed and the sprint should be re-sized"
)
print(f"\nok: recoverable recall is {pct(edges_unique, total)} of the graph, "
      f"not the {pct(len(attr), total)} the exclusion suggests")

"""Census: where do the atlas's inferred edges actually come from, and how much
of the graph does traversal exclude?

Run for evidence, not as a pass/fail gate: it prints the split and asserts only
the two facts a design decision rests on.
"""
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from godmode_runtime.godmode_atlas import (  # noqa: E402
    ATTR_CALLS, EXTRACTED, INFERRED, _RELATION_BUCKET, build,
)


def suffix(node: str) -> str:
    head = node.split("::")[0].rsplit("/", 1)[-1]
    return "." + head.rsplit(".", 1)[-1] if "." in head else "(none)"


atlas = build(ROOT)
by_relation = collections.defaultdict(collections.Counter)
by_suffix = collections.defaultdict(collections.Counter)
for edge in atlas.edges:
    by_relation[edge.relation][edge.evidence] += 1
    by_suffix[suffix(edge.source)][edge.evidence] += 1

total = len(atlas.edges)
inferred = sum(c[INFERRED] for c in by_relation.values())
attr = sum(by_relation[ATTR_CALLS].values())
traversed = sum(
    sum(c.values()) for rel, c in by_relation.items() if rel in _RELATION_BUCKET
)

print(f"edges {total}  inferred {inferred} ({100*inferred/total:.1f}%)")
print(f"attr-calls {attr} ({100*attr/total:.1f}%) - excluded from traversal")
print(f"traversable {traversed} ({100*traversed/total:.1f}%)")
print("\nby relation:")
for rel, c in sorted(by_relation.items(), key=lambda kv: -sum(kv[1].values())):
    t = sum(c.values())
    print(f"  {rel:12} {c[EXTRACTED]:8} extracted {c[INFERRED]:6} inferred"
          f"  {'(traversed)' if rel in _RELATION_BUCKET else '(excluded)'}")
print("\nby source suffix:")
for suf, c in sorted(by_suffix.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  {suf:8} {c[EXTRACTED]:8} extracted {c[INFERRED]:6} inferred")

# The two facts the design rests on.
code = {r: c for r, c in by_relation.items() if r != "documents"}
assert all(c[INFERRED] == 0 for c in code.values()), \
    "a code relation now carries inferred edges; the design premise changed"
assert ATTR_CALLS not in _RELATION_BUCKET, \
    "attr-calls entered the traversal buckets; the exclusion premise changed"
print("\nok: every code edge is extracted; attr-calls stays out of traversal")

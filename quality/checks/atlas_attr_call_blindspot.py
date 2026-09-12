"""Check: no attribute call resolves to a located symbol.

This is the precondition for `atlas_attr_call_recall.py`. Every attr-call edge
targets a `*::name` placeholder rather than a symbol id, which is why they are
excluded from traversal and why the recall census has to match on bare names.

If receiver resolution is ever added, this check fails first and says so.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from godmode_runtime.godmode_atlas import ATTR_CALLS, _RELATION_BUCKET, build  # noqa: E402

atlas = build(ROOT)
attr = [e for e in atlas.edges if e.relation == ATTR_CALLS]
assert attr, "no attribute calls found; the premise no longer holds here"

located = {symbol.id for symbol in atlas.symbols}
resolved = [e for e in attr if e.target in located]

print(f"attribute calls {len(attr)}, resolved to a located symbol {len(resolved)}")
assert not resolved, (
    f"{len(resolved)} attribute calls now name a located symbol; receiver "
    "resolution exists and the recall census must be re-derived"
)
assert ATTR_CALLS not in _RELATION_BUCKET, "attr-calls entered traversal"
print("ok: every attribute call is an unresolved placeholder, excluded from traversal")

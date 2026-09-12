"""Check: the routing snapshot scores lexical overlap, not agent behaviour.

`_route` compares the prompt's token set against the skill's own description
plus its sibling positive prompts. No model is asked anything, so a positive
passing says the authored prompt reuses the description's vocabulary - not that
a skill fires on what a user would actually type.
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from godmode_runtime import godmode_evals as E  # noqa: E402

route_src = inspect.getsource(E._route)
corpus_src = inspect.getsource(E._corpus)

assert "prompt_tokens & _corpus" in route_src, "routing is no longer token overlap"
assert "len(overlap) / len(prompt_tokens)" in route_src, "score is no longer lexical"
assert '_tokens(suites[skill]["description"])' in corpus_src, \
    "the corpus no longer seeds from the skill's own description"

module_src = inspect.getsource(E)
for forbidden in ("anthropic", "requests", "urllib.request", "httpx"):
    assert forbidden not in module_src, f"{forbidden} appeared; this is no longer offline"

# A prompt in the description's vocabulary routes; the same intent in plain
# words need not. Demonstrate with the real suites.
suites = E.load_suites(ROOT)
assert "godmode" in suites, "godmode suite missing"
authored = next(iter(suites["godmode"]["positive"]))
plain = "I'm picking this project back up after a couple of weeks away and I don't trust my memory of it."

best_a, score_a, _ = E._route(suites, authored, "godmode")
best_p, score_p, _ = E._route(suites, plain, None)

print(f"authored prompt -> {best_a} (score {score_a})")
print(f"  {authored!r}")
print(f"plain phrasing  -> {best_p} (score {score_p})")
print(f"  {plain!r}")
assert score_a > score_p, "the authored prompt no longer scores above plain phrasing"
print("\nok: routing is lexical overlap with the skill's own description")

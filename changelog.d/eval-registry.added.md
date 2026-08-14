Versioned eval registry + grader vocabulary (U-S1).

Scenario coverage (`godmode_scenarios.py`) never named which version of a
staging function produced a "caught" result, so an edited scenario and an
untouched one looked identical in the report. Every scenario now carries a
`name.local.vN` id and a content digest (`sha256` of the staging function's
own source, via `inspect.getsource`) recorded alongside its outcome. A
pinned registry (`SCENARIO_DIGEST_REGISTRY`) freezes the digest each id was
last reviewed at; a scenario whose body changed with its version left alone
surfaces as a `digest-drift` blocking finding in `run()`'s `registry` field
- caught by planting exactly that edit and watching the finding appear.

`godmode_graders.py` is new: a closed vocabulary of deterministic
comparators (`match` with prefix/any-of, `includes`, `fuzzy` mutual
containment, `json_match`) that eval definitions can name instead of
re-inventing string comparisons per skill. `json_match` fails closed -
invalid JSON on either side never matches, even when both sides are
byte-identical malformed input. `godmode_evals.py`'s behaviour-assertion
checks can now declare a `grader` field to use this vocabulary directly, and
a new `compare_eval_results` refuses to diff two result records that carry
different ids: "scores are comparable only within an id."

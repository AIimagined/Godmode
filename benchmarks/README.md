# Benchmarks

Four tasks that check whether this product's mechanisms actually fire, and what
the bounded context brief costs.

```
python benchmarks/benchmark.py
python benchmarks/benchmark.py --json benchmarks/results/<date>.json
```

Needs nothing but this repository and Python — no network, no model, no keys.
Every task builds a throwaway repository, plants a fault, and deletes it.

## Method

The tasks were written from the capabilities this product claims, before any
result was seen. Three are binary: the mechanism either catches the planted
fault or it does not.

| Task | Plants | Passes when |
| --- | --- | --- |
| `planted-regression` | a test weakened with a skip and stripped assertions | the integrity monitors block it |
| `seeded-drift` | one version surface moved out of step | reconciliation fails |
| `spent-hypothesis` | three checkpoints under one unchanged explanation | the loop detector ends that explanation |
| `brief-cost` | nothing — it measures a size | (see below) |

**Every binary task ships its own control.** The same check runs with the fault
absent and must produce the opposite result. A task whose control also fires
measures nothing and is reported as broken rather than as a success — a green
run where the control never ran would be the failure mode this product exists to
catch, committed by its own benchmark.

## On the token figure

`brief-cost` reports what the bounded brief costs against the records it stands
in for. **It is not a saving.** Establishing a saving means doing the same work
twice, once with the brief and once without, and comparing what each consumed.
This harness cannot do that and does not claim to.

The measured session cost of an agent run is a separate question, answered from
the host's own transcript by `godmode_usage`; that reads counts and keeps counts,
and never enters this corpus.

## Results

Committed under `results/`, with the date they were produced. A figure published
anywhere in this project should have a file here behind it.

## Verifying

The harness reports `review-required` and exits non-zero if any planted fault
goes uncaught, any control also fires, or any task errors. A run that reports
`all-mechanisms-fire` has had every control pass as well.

## The two-arm experiment

`ab_resume.py` does what the corpus deliberately does not: the same work twice.

The task is the one the bounded brief exists for — establish what is true about
this project right now. Arm A reads the brief. Arm B runs the commands an agent
reaches for when there is no brief, and pays for their output.

The six facts that constitute "knowing where the project stands" are named
before either arm runs, so neither is scored against a target drawn around its
own output. The derivation commands were chosen as the cheapest sequence that
could recover them, not the most expensive available: stacking the deck against
the alternative would make the result worthless.

**No ratio is published, and that is deliberate.** The arms recover different
numbers of facts, so a normalised figure would compare unlike things. What the
measurement supports is a dominance statement — one arm is no worse on either
axis and better on at least one — and the harness reports that instead, in
whichever direction the numbers point.

```
python benchmarks/ab_resume.py
```

### What it measures, and what it does not

It measures the cost of the material an agent must take in to know where it
stands. It does **not** measure a full agent session: reasoning, tool calls and
retries are not in either arm, so nothing here supports a claim about what a
task costs end to end. The measured cost of a real session is a separate
question, answered from the host's own transcript, which reads counts and keeps
counts.

## Gate latency

`gate_latency.py` times the fast gate itself - p50/p95, in milliseconds, for a
read-only command (fast-allowed, never reaches the full hook) and a mutating
one (escalates to the full hook's classify+archive round trip):

```
python benchmarks/gate_latency.py --write-baseline
python benchmarks/gate_latency.py --check
```

The committed `gate_latency_baseline.json` is **machine-specific**: a p95 in
milliseconds means little compared across different hardware, so `--check`
never compares this machine against another one's number - only against a
baseline captured here. A CI job establishes and checks its own baseline the
same way, on its own runner, rather than comparing against this file; that
wiring is not part of this script and is not added to any workflow here,
because CI machines differ from a contributor's machine and from each other.
`--check` exits `0` within budget, `1` on a regression of 20% or more against
the committed baseline (or a phase the baseline has but the new run is
missing), and `2` when no usable baseline is committed (absent, unparsable,
or written under a different schema).

Below 21 samples, the p95 index lands on or next to the plain sample max, not
a real percentile - `--write-baseline` and `--check` both refuse a smaller
`--n`. `--check` reuses the committed baseline's own sample count by default,
so a check and the baseline it is judged against are always comparing the
same order statistic.

`recommended_timeouts` (also in the baseline file) sizes the hook timeouts a
later plan wires in, clamped between a floor and a ceiling per timeout so an
outlier machine cannot recommend something unusably short or long. On a quiet
machine - roughly under 2 seconds of escalation p95 - all three constants
collapse to their floor (`pre_tool_use` 3s, `stop`/`user_prompt` 10s each) and
look identical regardless of the exact p95 underneath; the committed baseline
above the floor instead (its escalation p95 ran past 2s) is itself the
demonstration that these numbers move with real machine load, not just with
code changes. That is also why a single local `--check` run is **advisory
only** - a reported regression on one run is confirmed by a second run on a
quiet machine, not acted on from the first exit code alone.

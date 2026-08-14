"""Termination algebra + budgets (U-R1): declarative stopping contracts.

A loop that decides for itself when to stop is a loop that never does -
"keep going" is always the locally plausible next step. `Stop` moves the
decision outside that judgment: a predicate over the records a run has
produced since the last check (the *delta*, never the whole archive, so
cost stays O(new) regardless of how long a run has been going), composed
from primitives with `&`/`|` into one condition a caller consults instead
of arguing with itself.

Fail-loud lifecycle: a `Stop` that has already fired is *spent*. Consulting
it again without an explicit `reset()` is not a fresh answer, it is the
same finding reported a second time as if it were new - so it raises
`SpentStopError` instead. A caller that wants to keep going past a fired
Stop must decide to reset it, on purpose, once - not have the Stop quietly
re-arm itself and let the loop treat "still going" as evidence nothing was
ever wrong.

Budget-as-fairness: `attempt(budget_s)` bounds a single subprocess attempt.
Overrun kills the process outright - never lets it run past its allotment
hoping it will finish anyway - and the result carries `run_state:
"truncated"`, the same vocabulary U-V1's verdicts use. That is deliberate:
a truncated result fed into `record_verdict`/`archive.append("verdict", ...)`
as `disposition: "confirmed"` hits the archive-seam refusal in
`godmode_invariants._verdict_invariants` (budget exhaustion must not
impersonate completion) with no code path here needing to know that rule
exists.
"""

from __future__ import annotations

import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .godmode_errors import GodmodeError

Record = dict[str, Any]


class SpentStopError(GodmodeError):
    """A `Stop` fired already and was consulted again without `reset()`."""


class Stop:
    """Base of the algebra: a predicate over a record-delta.

    Subclasses implement `_check(delta) -> str | None` (the reason it
    fired, or `None`) and `_reset()` (clear any accumulated state - a
    counter, a timer, a running best). `__call__` is the public surface:
    it enforces the spent/reset lifecycle so no subclass has to.
    """

    def __init__(self) -> None:
        self._spent = False

    @property
    def spent(self) -> bool:
        return self._spent

    def reset(self) -> None:
        self._spent = False
        self._reset()

    def _reset(self) -> None:  # pragma: no cover - trivial default
        pass

    def _check(self, delta: list[Record]) -> str | None:
        raise NotImplementedError

    def __call__(self, delta: list[Record]) -> str | None:
        if self._spent:
            raise SpentStopError(
                f"{type(self).__name__} already fired and was not reset(); "
                "a spent Stop must not be consulted again until reset() is called"
            )
        reason = self._check(delta)
        if reason is not None:
            self._spent = True
        return reason

    def __and__(self, other: "Stop") -> "And":
        return And(self, other)

    def __or__(self, other: "Stop") -> "Or":
        return Or(self, other)


class _Composite(Stop):
    """Shared plumbing for `And`/`Or`: flatten same-typed nesting so
    `a & b & c` stays one flat group instead of `And(And(a, b), c)`, which
    would otherwise nest the reason string one level deeper per operator.

    Children are consulted via `_check` directly, never `__call__` - the
    composite alone owns spent/reset bookkeeping visible to the caller;
    each child's own accumulated state (a `MaxRecords` counter, a
    `MetricPlateau` history) still advances on every tick, which is what
    lets the same child keep counting across composite calls.
    """

    def __init__(self, *children: Stop) -> None:
        super().__init__()
        self._children: list[Stop] = []
        for child in children:
            if type(child) is type(self):
                self._children.extend(child._children)  # type: ignore[attr-defined]
            else:
                self._children.append(child)

    def _reset(self) -> None:
        for child in self._children:
            child.reset()


class And(_Composite):
    """Fires only once every child has independently fired this tick."""

    def _check(self, delta: list[Record]) -> str | None:
        reasons = [child._check(delta) for child in self._children]
        if reasons and all(reason is not None for reason in reasons):
            return " AND ".join(reasons)  # type: ignore[arg-type]
        return None


class Or(_Composite):
    """Fires the instant any child fires; the reason names that one leaf."""

    def _check(self, delta: list[Record]) -> str | None:
        for child in self._children:
            reason = child._check(delta)
            if reason is not None:
                return reason
        return None


class MaxRecords(Stop):
    """Fires once at least `n` records have been observed, across calls."""

    def __init__(self, n: int) -> None:
        super().__init__()
        self._limit = int(n)
        self._count = 0

    def _check(self, delta: list[Record]) -> str | None:
        self._count += len(delta)
        if self._count >= self._limit:
            return f"MaxRecords({self._limit}): {self._count} records observed"
        return None

    def _reset(self) -> None:
        self._count = 0


class MaxWall(Stop):
    """Fires once `seconds` of wall time have elapsed since construction
    (or the last `reset()`)."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self._limit = float(seconds)
        self._started = time.monotonic()

    def _check(self, delta: list[Record]) -> str | None:
        elapsed = time.monotonic() - self._started
        if elapsed >= self._limit:
            return f"MaxWall({self._limit}s): {elapsed:.3f}s elapsed"
        return None

    def _reset(self) -> None:
        self._started = time.monotonic()


class OperatorStop(Stop):
    """Fires the instant an operator-created flag file exists.

    Presence, not content, is the signal: an operator who wants a run to
    stop touches the file and does not have to know this run's internal
    vocabulary to be heard. The flag is the operator's, not this Stop's -
    `reset()` clears the fired bookkeeping here but never deletes it;
    removing the flag is a separate, deliberate act.
    """

    def __init__(self, flag_path: str | Path) -> None:
        super().__init__()
        self._flag = Path(flag_path)

    def _check(self, delta: list[Record]) -> str | None:
        if self._flag.is_file():
            return f"OperatorStop: flag present at {self._flag}"
        return None


class MetricPlateau(Stop):
    """Fires once a named metric holds flat (within `eps`) across `patience`
    consecutive observations, regardless of direction.

    Observations come from `record["data"][name]` on records in the delta
    that carry it; everything else is ignored. Flatness, not lack of
    improvement, is the signal - a metric oscillating between two values a
    hair apart is not "improving" either, and this predicate does not care
    which direction "better" is for the caller's metric.
    """

    def __init__(self, name: str, eps: float, patience: int) -> None:
        super().__init__()
        self._name = name
        self._eps = float(eps)
        self._patience = int(patience)
        self._last: float | None = None
        self._streak = 0

    def _check(self, delta: list[Record]) -> str | None:
        for record in delta:
            data = record.get("data") or {}
            if self._name not in data:
                continue
            try:
                value = float(data[self._name])
            except (TypeError, ValueError):
                continue
            if self._last is not None and abs(value - self._last) <= self._eps:
                self._streak += 1
            else:
                self._streak = 1
            self._last = value
            if self._streak >= self._patience:
                return (
                    f"MetricPlateau({self._name}): flat for {self._streak} "
                    f"observations at ~{value:g} (eps={self._eps:g})"
                )
        return None

    def _reset(self) -> None:
        self._last = None
        self._streak = 0


class AttemptHandle:
    """What `attempt()` yields: the deadline, and the one operation it
    bounds - running a subprocess to at most the time left on the budget.
    """

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.truncated = False

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def run(self, argv: list[str], **kwargs: Any) -> dict[str, Any]:
        """Run `argv`, bounded by the time left on this attempt's budget.

        An overrun kills the process - never retries silently, never lets
        it keep running past its allotment on the hope it finishes anyway
        - and the result's `run_state` becomes `"truncated"`: U-V1's
        vocabulary for a budget or timeout cutoff, so a caller recording
        this as `confirmed` meets the archive-seam refusal instead of a
        truncated run impersonating a completed one.
        """
        started = time.monotonic()
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("text", True)
        process = subprocess.Popen(argv, **kwargs)
        timeout = self.remaining()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            run_state = "terminated"
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            run_state = "truncated"
            self.truncated = True
        return {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "run_state": run_state,
            "elapsed_s": round(time.monotonic() - started, 3),
        }


@contextmanager
def attempt(budget_s: float) -> Iterator[AttemptHandle]:
    """Budget-as-fairness (U-R1/U-R2): one attempt gets `budget_s` seconds,
    never more - see `AttemptHandle.run` for what happens on overrun.
    """
    yield AttemptHandle(deadline=time.monotonic() + float(budget_s))

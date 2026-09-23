"""D-2: `.github/workflows/godmode-verify.yml` must be hardened.

CI runs on push, pull request and manual dispatch: every push to main or a
release branch and every pull request to main triggers a run, and a public
repository runs these free. The workflow must also be hardened against a compromised or renamed action, a credential that
outlives the job that needed it, a hung step burning the operator's own
runner minutes, and a matrix leg that silently fails or is skipped without
anyone noticing on the page.

This file parses the workflow with the standard library only (no PyYAML - a
YAML parser is not on this project's dependency list, and the checks below
do not need one) and asserts, line by line:

  - every third-party `uses:` reference is pinned to a full 40-hex commit
    SHA, not a mutable tag;
  - every `actions/checkout` step disables credential persistence, so the
    job token is not left on disk after the step that needed it returns;
  - every job declares `timeout-minutes`, so a hang cannot run until the
    workflow-level default (or worse, none) kills it;
  - a named aggregate job depends on every other job and fails the run if
    any of them did not succeed - including cancelled or skipped, not just
    an explicit failure;
  - the dispatch form declares its three inputs with defaults, and the
    sharded preflight job carries the dispatched shard count, the matrix
    index and the suite target through to the command it runs.

Read-only. This test never calls `git ls-remote`, the GitHub API, or runs
the workflow; it only inspects the checked-in YAML text.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PLUGIN_ROOT / ".github" / "workflows" / "godmode-verify.yml"

_TRIGGER_RE = re.compile(r"^on:\s*$")
_JOBS_HEADER_RE = re.compile(r"^jobs:\s*$")
_JOB_NAME_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_USES_RE = re.compile(r"^(\s*)(?:-\s*)?uses:\s*(\S+)\s*(?:#.*)?$")
_MARKETPLACE_REF_RE = re.compile(r"^([^/\s@]+)/([^/\s@]+)@([0-9a-fA-F]+)$")
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_PERSIST_CREDENTIALS_FALSE_RE = re.compile(r"^\s*persist-credentials:\s*false\s*$")
_TIMEOUT_RE = re.compile(r"^\s{4}timeout-minutes:\s*\d+\s*$")
_NEEDS_RE = re.compile(r"^\s*needs:\s*\[(.*)\]\s*$")
_IF_ALWAYS_RE = re.compile(r"^\s*if:\s*always\(\)\s*$")


def _lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _job_blocks() -> dict[str, tuple[int, int]]:
    """Map job id -> (start, end) line-index range, end exclusive.

    Only scans after the top-level ``jobs:`` header so a bare ``key:`` under
    ``on:`` (e.g. ``workflow_dispatch:``) is never mistaken for a job.
    """
    lines = _lines()
    jobs_at = next(i for i, line in enumerate(lines) if _JOBS_HEADER_RE.match(line))
    starts: list[tuple[str, int]] = []
    for i in range(jobs_at + 1, len(lines)):
        match = _JOB_NAME_RE.match(lines[i])
        if match:
            starts.append((match.group(1), i))
    blocks: dict[str, tuple[int, int]] = {}
    for idx, (name, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        blocks[name] = (start, end)
    return blocks


class WorkflowTriggerTests(unittest.TestCase):
    def test_ci_runs_on_push_pull_request_and_dispatch(self) -> None:
        # CI runs on every push to main and release branches (a public
        # repository runs free); dispatch stays for narrowed runs. No
        # schedule: nothing runs that nobody triggered.
        text = WORKFLOW.read_text(encoding="utf-8")
        on_match = re.search(r"^on:\s*\n((?:^\s.*\n?)*)", text, re.MULTILINE)
        self.assertIsNotNone(on_match, "no `on:` block found")
        on_block = on_match.group(1)
        for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertIn(trigger, on_block, trigger)
        self.assertNotIn("schedule:", on_block)
        self.assertIn('branches: [main, "sprint/**"]', on_block)


class DispatchInputTests(unittest.TestCase):
    """The dispatch form is the only control surface this workflow has.

    A `workflow_dispatch`-only workflow is run by hand, so its inputs are how
    the operator narrows a run instead of editing this file (or keeping a
    second one). Three exist, and each must be declared with a default: a
    dispatch that leaves the form alone runs the full, four-shard, every-host
    verification.
    """

    def _on_block(self) -> str:
        text = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"^on:\s*\n((?:^\s.*\n?)*)", text, re.MULTILINE)
        self.assertIsNotNone(match, "no `on:` block found")
        return match.group(1)

    def test_the_dispatch_declares_the_shard_suite_and_host_inputs(self) -> None:
        block = self._on_block()
        self.assertIn("inputs:", block)
        for name, default in (("shards", '"4"'), ("suite", '"discover"'), ("hosts", '"all"')):
            with self.subTest(input=name):
                declared = re.search(
                    rf"^      {name}:\s*\n((?:^ {{8,}}.*\n)*)", block, re.MULTILINE
                )
                self.assertIsNotNone(declared, f"dispatch input {name!r} is not declared")
                body = declared.group(1)
                self.assertRegex(body, r"(?m)^\s+description:\s*\S", f"{name} has no description")
                self.assertRegex(
                    body, rf"(?m)^\s+default:\s*{re.escape(default)}\s*$",
                    f"{name} does not default to {default}",
                )


class ShardJobTests(unittest.TestCase):
    """The sharded preflight job must actually carry the dispatched values.

    A matrix cannot be sized by an input, so the matrix is fixed at four and
    `shards` gates which legs run. Both numbers have to reach the command:
    a job that hard-codes `--suite-shards 4` while the operator dispatched 2
    would run a quarter of the suite and report the whole of it.
    """

    JOB = "preflight-shard"

    def _block(self) -> str:
        blocks = _job_blocks()
        self.assertIn(self.JOB, blocks, f"no {self.JOB!r} job in the workflow")
        start, end = blocks[self.JOB]
        return "\n".join(_lines()[start:end])

    def test_the_shard_job_passes_the_dispatched_shard_count_and_index_through(self) -> None:
        block = self._block()
        self.assertRegex(
            block,
            r"precheck --preflight --suite-shards \$\{\{ \(inputs\.shards \|\| '4'\) \}\}"
            r" --shard-index \$\{\{ matrix\.index \}\}",
            "the shard step does not pass the dispatched shard count and matrix index through",
        )
        self.assertIn("${{ (inputs.suite || 'discover') }}", block, "the shard step ignores the suite input")

    def test_the_matrix_is_four_fixed_legs_gated_by_the_shard_count(self) -> None:
        block = self._block()
        self.assertRegex(block, r"(?m)^\s+index: \[0, 1, 2, 3\]\s*$",
                         "the shard matrix is not the fixed four entries")
        # On the steps, never on the job: GitHub evaluates a job-level `if`
        # before the matrix expands, so `matrix` there fails the whole
        # workflow's parse (first real dispatch, 2026-09-23, HTTP 422). This
        # test accepted any indentation until then, so it pinned the defect.
        self.assertRegex(
            block, r"(?m)^ {8}if: \$\{\{ matrix\.index < fromJSON\(\(inputs\.shards \|\| '4'\)\) \}\}\s*$",
            "the shard legs are not gated by the dispatched shard count",
        )
        self.assertNotRegex(
            "\n".join(_lines()), r"(?m)^ {4}if: .*\bmatrix\.",
            "a job-level `if` reads `matrix`, which GitHub rejects at parse time",
        )

    def test_the_aggregate_job_requires_the_shard_job(self) -> None:
        # Index 0 runs for every legal shard count, so this job is never a
        # whole-job skip and the aggregate can require it unconditionally.
        lines = _lines()
        needs = [line for line in lines if _NEEDS_RE.match(line)]
        self.assertTrue(needs, "no needs: line found")
        self.assertTrue(
            any(self.JOB in line for line in needs),
            f"{self.JOB!r} is in no aggregate needs list",
        )


class ActionsArePinnedTests(unittest.TestCase):
    def test_every_marketplace_action_is_pinned_to_a_full_commit_sha(self) -> None:
        offenders: list[str] = []
        for lineno, line in enumerate(_lines(), start=1):
            match = _USES_RE.match(line)
            if not match:
                continue
            ref = match.group(2)
            if ref.startswith("./") or ref.startswith("docker://"):
                continue  # local/composite action, not a marketplace reference
            owner_repo_ref = _MARKETPLACE_REF_RE.match(ref)
            if owner_repo_ref is None:
                offenders.append(f"{lineno}: unparseable uses: {ref!r}")
                continue
            sha = owner_repo_ref.group(3)
            if not _SHA40_RE.match(sha):
                offenders.append(f"{lineno}: not a full 40-hex commit SHA: {ref!r}")
        self.assertEqual(offenders, [], "\n".join(offenders))


class CheckoutPersistCredentialsTests(unittest.TestCase):
    def test_every_checkout_step_disables_persist_credentials(self) -> None:
        lines = _lines()
        offenders: list[str] = []
        for lineno, line in enumerate(lines):
            match = _USES_RE.match(line)
            if not match or "actions/checkout@" not in match.group(2):
                continue
            uses_indent = _indent(line)
            window_end = len(lines)
            for j in range(lineno + 1, len(lines)):
                if _indent(lines[j]) < uses_indent and lines[j].strip():
                    window_end = j
                    break
            window = lines[lineno + 1 : window_end]
            if not any(_PERSIST_CREDENTIALS_FALSE_RE.match(w) for w in window):
                offenders.append(f"line {lineno + 1}: checkout step has no persist-credentials: false")
        self.assertGreater(
            sum(1 for line in lines if "actions/checkout@" in line),
            0,
            "no checkout step found - test fixture drifted from the workflow",
        )
        self.assertEqual(offenders, [], "\n".join(offenders))


class JobTimeoutTests(unittest.TestCase):
    def test_every_job_declares_a_timeout(self) -> None:
        blocks = _job_blocks()
        self.assertGreater(len(blocks), 0)
        lines = _lines()
        missing = [
            name
            for name, (start, end) in blocks.items()
            if not any(_TIMEOUT_RE.match(lines[i]) for i in range(start, end))
        ]
        self.assertEqual(missing, [], f"jobs missing timeout-minutes: {missing}")


class AggregateJobTests(unittest.TestCase):
    def test_an_aggregate_job_depends_on_every_other_job_and_runs_if_always(self) -> None:
        blocks = _job_blocks()
        lines = _lines()
        all_job_names = set(blocks)

        aggregate_name = None
        needed: set[str] = set()
        for name, (start, end) in blocks.items():
            for i in range(start, end):
                needs_match = _NEEDS_RE.match(lines[i])
                if needs_match:
                    candidates = {n.strip() for n in needs_match.group(1).split(",") if n.strip()}
                    if candidates and candidates == all_job_names - {name}:
                        aggregate_name = name
                        needed = candidates
                    break

        self.assertIsNotNone(
            aggregate_name,
            "no job's needs: lists exactly every other job - no aggregate job found",
        )
        self.assertEqual(needed, all_job_names - {aggregate_name})

        start, end = blocks[aggregate_name]
        has_if_always = any(_IF_ALWAYS_RE.match(lines[i]) for i in range(start, end))
        self.assertTrue(has_if_always, f"aggregate job {aggregate_name!r} has no `if: always()`")

        # The aggregate job must actually gate on failure/cancelled/skipped,
        # not merely declare needs + if: always() and do nothing with them.
        block_text = "\n".join(lines[start:end])
        self.assertRegex(
            block_text,
            r"needs\.\*\.result",
            f"aggregate job {aggregate_name!r} never inspects needs.*.result",
        )
        for outcome in ("failure", "cancelled", "skipped"):
            self.assertIn(
                outcome,
                block_text,
                f"aggregate job {aggregate_name!r} never checks for a {outcome!r} result",
            )


if __name__ == "__main__":
    unittest.main()

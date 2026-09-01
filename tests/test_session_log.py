"""Counts-only session measurement, unit and wired.

Every fixture line below is built to the REAL host transcript shape, pinned
read-only on 2026-08-15 from a local Claude Code session transcript
(`~/.claude/projects/.../<a local session transcript>.jsonl` on this
machine - the specific session identifier is not recorded here) - see the
field-name notes on `_assistant_line`/`_user_line` and the longer note in
`godmode_session_log`'s module docstring. No string from that real transcript
is reproduced anywhere here; every value below is synthetic and neutral,
built only to the observed field NAMES and block `type` values.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime.godmode_session_log import (  # noqa: E402
    REASON_NOT_FOUND,
    REASON_NO_PATH,
    REASON_UNREADABLE,
    measure,
    record_measurement,
)

SENTINEL = "SENTINEL_SECRET_XYZ"


def _assistant_line(*, tool_uses=(), text=None, usage=None):
    """One assistant-role transcript line, built to the pinned real shape.

    Real shape observed: top level `{"type": "assistant", "message": {...},
    "sessionId": ...}`; `message` is `{"role": "assistant", "content": [...],
    "usage": {...}}`; `content` blocks carry `type` in
    `{"thinking", "tool_use", "text"}`; a `tool_use` block is
    `{"type": "tool_use", "id": ..., "name": ..., "input": {...}}`; a `Bash`
    tool_use's `input` carries `{"command": ..., "description": ...}`;
    `usage` carries `input_tokens`/`cache_creation_input_tokens`/
    `cache_read_input_tokens`/`output_tokens`. Only field NAMES are drawn
    from the real file; every value here is synthetic.
    """
    content = [
        {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": tool_input}
        for i, (name, tool_input) in enumerate(tool_uses)
    ]
    if text is not None:
        content.append({"type": "text", "text": text})
    message = {
        "role": "assistant",
        "content": content,
        "usage": usage or {
            "input_tokens": 0, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0, "output_tokens": 0,
        },
    }
    return {"type": "assistant", "message": message, "sessionId": "S-fixture"}


def _user_line(*, tool_result_content="ok"):
    """A user-role line: the observed shape carries `tool_result` blocks."""
    message = {
        "role": "user",
        "content": [{"type": "tool_result", "content": tool_result_content,
                     "is_error": False, "tool_use_id": "toolu_0"}],
    }
    return {"type": "user", "message": message}


def _write_transcript(path: Path, lines: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )


def _all_record_text(archive) -> str:
    blob = []
    for event_path in archive.events.glob("*.json"):
        blob.append(event_path.read_text(encoding="utf-8"))
    return "\n".join(blob)


class MeasureCountsTests(unittest.TestCase):
    def test_counts_tool_calls_commands_and_test_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "t.jsonl"
            _write_transcript(path, [
                _assistant_line(tool_uses=[
                    ("Bash", {"command": "python -m pytest tests/"}),
                    ("Read", {"file_path": "a.py"}),
                ]),
                _user_line(),
                _assistant_line(tool_uses=[("Bash", {"command": "ls"})]),
            ])
            result = measure(path)
        self.assertEqual(result["turns"], 2)
        self.assertEqual(result["tool_calls"], {"Bash": 2, "Read": 1})
        self.assertEqual(result["commands"], 2)
        self.assertEqual(result["test_runs"], 1)
        self.assertTrue(result["content_free"])

    def test_tokens_summed_from_usage_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "t.jsonl"
            _write_transcript(path, [
                _assistant_line(usage={
                    "input_tokens": 10, "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 1, "output_tokens": 20,
                }),
                _assistant_line(usage={
                    "input_tokens": 3, "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0, "output_tokens": 7,
                }),
            ])
            result = measure(path)
        self.assertEqual(result["tokens_in"], 10 + 5 + 1 + 3)
        self.assertEqual(result["tokens_out"], 20 + 7)

    def test_a_torn_tail_line_is_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "t.jsonl"
            path.write_text(
                json.dumps(_assistant_line()) + "\n" + '{"type": "assist',
                encoding="utf-8",
            )
            result = measure(path)
        self.assertEqual(result["turns"], 1)

    def test_unknown_tool_names_bucket_to_a_closed_enum(self) -> None:
        """A closed enum, proven against a tool name that is not in it -
        including one shaped like a content leak, to show it is discarded
        rather than stored verbatim."""
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "t.jsonl"
            odd_name = f"mcp__weird__{SENTINEL}"
            _write_transcript(path, [
                _assistant_line(tool_uses=[(odd_name, {})]),
            ])
            result = measure(path)
        self.assertEqual(result["tool_calls"], {"other": 1})
        self.assertNotIn(odd_name, result["tool_calls"])
        self.assertNotIn(SENTINEL, json.dumps(result))


class StreamingConstraintTests(unittest.TestCase):
    def test_the_source_never_slurps_the_transcript(self) -> None:
        """Implementation constraint, not just an observed outcome: the
        module must not hold a call capable of loading the whole file into
        memory at once."""
        source = (SCRIPTS / "godmode_runtime" / "godmode_session_log.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(".read_text(", source)
        self.assertNotIn(".readlines(", source)
        self.assertNotRegex(source, r"\.read\(\s*\)")

    def test_a_two_megabyte_transcript_streams_and_counts_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "big.jsonl"
            # Padding lives inside a tool_result block (untallied content),
            # not in anything this module reads for classification - keeps
            # the fixture 2MB-scale without perturbing the counts asserted
            # below.
            padding = "x" * 2000
            with path.open("w", encoding="utf-8") as handle:
                for _ in range(1000):
                    handle.write(json.dumps(_user_line(tool_result_content=padding)))
                    handle.write("\n")
                for _ in range(200):
                    handle.write(json.dumps(_assistant_line(tool_uses=[
                        ("Bash", {"command": "npm test"}),
                    ])))
                    handle.write("\n")
            self.assertGreater(path.stat().st_size, 2_000_000)
            result = measure(path)
        self.assertEqual(result["turns"], 200)
        self.assertEqual(result["commands"], 200)
        self.assertEqual(result["test_runs"], 200)


class RecordMeasurementTests(unittest.TestCase):
    def test_measured_true_writes_counts_only(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "t.jsonl"
                _write_transcript(path, [_assistant_line(tool_uses=[("Read", {})])])
                record = record_measurement(archive, path, session="S-1")
        self.assertEqual(record["kind"], "metric")
        self.assertTrue(record["data"]["measured"])
        self.assertEqual(record["data"]["tool_calls"], {"Read": 1})
        self.assertEqual(record["data"]["session"], "S-1")

    def test_the_fix_loop_shape_rides_the_measurement(self) -> None:
        # The stop hook's timeline already carries the fix-loop shape;
        # persisting its COUNTS (never the commands - the 4018 privacy
        # decision) lets cross-session economics see a loop that ended
        # without an incident. Same command failing twice, one mutation.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "t.jsonl"
                fail = {"type": "tool_result", "content": "boom",
                        "is_error": True, "tool_use_id": "toolu_0"}
                _write_transcript(path, [
                    _assistant_line(tool_uses=[("Bash", {"command": "make test"})]),
                    {"type": "user", "message": {"role": "user", "content": [fail]}},
                    _assistant_line(tool_uses=[("Edit", {"file_path": "a.py"})]),
                    _assistant_line(tool_uses=[("Bash", {"command": "make test"})]),
                    {"type": "user", "message": {"role": "user", "content": [dict(fail)]}},
                ])
                record = record_measurement(archive, path, session="S-loop")
        data = record["data"]
        self.assertEqual(data["failing_commands"], 1)
        self.assertEqual(data["max_command_failures"], 2)
        self.assertEqual(data["mutation_turns"], 1)
        self.assertNotIn("make test", json.dumps(data))

    def test_tail_checks_count_verification_past_the_last_change(self) -> None:
        # Checks run AFTER the session's last mutation are verification past
        # the convergence point - the structural definition of an over-long
        # tail. One check before the edit, two after: tail_checks == 2.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "t.jsonl"
                lines = [
                    _assistant_line(tool_uses=[("Bash", {"command": "pytest tests/"})]),
                    _user_line(),
                    _assistant_line(tool_uses=[("Edit", {"file_path": "a.py"})]),
                    _assistant_line(tool_uses=[("Bash", {"command": "pytest tests/"})]),
                    _user_line(),
                    _assistant_line(tool_uses=[("Bash", {"command": "pytest tests/"})]),
                    _user_line(),
                ]
                _write_transcript(path, lines)
                record = record_measurement(archive, path, session="S-tail")
        self.assertEqual(record["data"]["tail_checks"], 2)

    def test_a_missing_transcript_is_a_stated_gap_not_an_error(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            missing = Path(tempfile.gettempdir()) / "godmode-does-not-exist.jsonl"
            record = record_measurement(archive, missing, session="S-1")
        self.assertEqual(record["data"]["measured"], False)
        self.assertEqual(record["data"]["reason"], REASON_NOT_FOUND)

    def test_an_unreadable_transcript_is_a_stated_gap(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                a_directory = Path(raw) / "not-a-file.jsonl"
                a_directory.mkdir()
                record = record_measurement(archive, a_directory, session="S-1")
        self.assertEqual(record["data"]["measured"], False)
        self.assertEqual(record["data"]["reason"], REASON_UNREADABLE)

    def test_no_path_at_all_is_a_stated_gap(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = record_measurement(archive, None, session="S-1")
        self.assertEqual(record["data"]["reason"], REASON_NO_PATH)

    def test_exits_clean_never_raises(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            try:
                record_measurement(archive, "\x00bad-path", session="S-1")
            except Exception as exc:  # noqa: BLE001
                self.fail(f"record_measurement raised: {exc!r}")

    def test_every_stored_string_is_at_most_80_chars(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "t.jsonl"
                _write_transcript(path, [
                    _assistant_line(tool_uses=[("Bash", {"command": "pytest"})]),
                ])
                record_measurement(archive, path, session="S" * 500)
            gap = record_measurement(archive, None, session="s")

            def _walk(value):
                if isinstance(value, str):
                    yield value
                elif isinstance(value, dict):
                    # Keys too, not just values - `tool_calls` is a dict
                    # keyed by tool name, and a claim of "every stored
                    # string" that skipped dict keys would miss exactly the
                    # field the closed tool-name enum exists to bound.
                    for k, v in value.items():
                        yield from _walk(k)
                        yield from _walk(v)
                elif isinstance(value, list):
                    for v in value:
                        yield from _walk(v)

            for record in archive.read_events():
                if record["kind"] != "metric":
                    continue
                for text in _walk(record["data"]):
                    self.assertLessEqual(len(text), 80, text)
            self.assertEqual(gap["data"]["reason"], REASON_NO_PATH)

    def test_content_free_plant_the_sentinel_never_reaches_the_archive(self) -> None:
        """The plant: a sentinel string sits in a Bash command AND in an
        assistant text block. After `record_measurement`, the sentinel must
        not appear anywhere in the whole archive events directory."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "t.jsonl"
                _write_transcript(path, [
                    _assistant_line(
                        tool_uses=[("Bash", {"command": f"echo {SENTINEL}"})],
                        text=f"the plan mentions {SENTINEL} explicitly",
                    ),
                ])
                record_measurement(archive, path, session="S-1")
        self.assertNotIn(SENTINEL, _all_record_text(archive))


class HookWiringTests(unittest.TestCase):
    """The real hook process, session-end, over a real archive - the same
    reason `test_request_hook.py` drives `user-prompt` this way: the module
    can be right while the wiring silently never calls it.
    """

    def setUp(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-session-log-hook-")
        self.project = Path(self._holder.name)
        self.state = self.project / "state"
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                        ["config", "user.name", "d"]):
            subprocess.run(["git", *command], cwd=self.project, capture_output=True)
        (self.project / "README.md").write_text("# t\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"],
                       cwd=self.project, capture_output=True)
        self._environment = dict(os.environ)
        os.environ["GODMODE_STATE_HOME"] = str(self.state)
        done = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
             "--project", str(self.project), "init"],
            capture_output=True, text=True, env=os.environ)
        assert done.returncode == 0, f"init failed: {done.stderr or done.stdout}"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environment)
        self._holder.cleanup()

    def _archive(self):
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        return Chronicle(resolve_anchor(str(self.project)))

    def _metrics(self) -> list[dict]:
        return [r for r in self._archive().read_events() if r.get("kind") == "metric"]

    def _submit(self, payload: dict) -> subprocess.CompletedProcess:
        full = {"hook_event_name": "SessionEnd", "cwd": str(self.project),
                "session_id": "S-hook", **payload}
        return subprocess.run(
            [sys.executable, str(HOOK), "session-end", "--project", str(self.project)],
            input=json.dumps(full), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            cwd=str(self.project), env=os.environ)

    def test_session_end_records_a_metric_from_the_transcript(self) -> None:
        transcript = self.project / "state" / "fixture.jsonl"
        _write_transcript(transcript, [
            _assistant_line(tool_uses=[("Read", {})]),
        ])
        done = self._submit({"transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        metrics = self._metrics()
        self.assertEqual(len(metrics), 1)
        self.assertTrue(metrics[0]["data"]["measured"])

    def test_a_missing_transcript_still_exits_clean(self) -> None:
        done = self._submit({"transcript_path": str(self.project / "no-such-file.jsonl")})
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self._metrics()[0]["data"]["measured"], False)

    def test_measurement_never_blocks_the_checkpoint(self) -> None:
        transcript = self.project / "state" / "fixture.jsonl"
        _write_transcript(transcript, [_assistant_line()])
        done = self._submit({
            "transcript_path": str(transcript),
            "summary": "a structured checkpoint",
            "status": "active",
        })
        self.assertEqual(done.returncode, 0)
        body = json.loads((done.stdout or "").strip())
        self.assertTrue(body.get("stored"))
        checkpoints = [r for r in self._archive().read_events()
                      if r.get("kind") == "checkpoint"]
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(len(self._metrics()), 1)

    def test_a_totally_broken_transcript_path_does_not_crash_the_hook(self) -> None:
        done = self._submit({"transcript_path": "\x00\x01not-a-real-path"})
        self.assertEqual(done.returncode, 0)

    def test_the_sentinel_never_reaches_any_record_via_the_real_hook(self) -> None:
        transcript = self.project / "state" / "fixture.jsonl"
        _write_transcript(transcript, [
            _assistant_line(
                tool_uses=[("Bash", {"command": f"echo {SENTINEL}"})],
                text=f"contains {SENTINEL}",
            ),
        ])
        done = self._submit({"transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        self.assertNotIn(SENTINEL, _all_record_text(self._archive()))

    def test_pre_compact_does_not_measure(self) -> None:
        """Session-end wiring only - pre-compact keeps its pre-existing
        behaviour untouched."""
        transcript = self.project / "state" / "fixture.jsonl"
        _write_transcript(transcript, [_assistant_line()])
        full = {"hook_event_name": "PreCompact", "cwd": str(self.project),
                "session_id": "S-hook", "transcript_path": str(transcript)}
        done = subprocess.run(
            [sys.executable, str(HOOK), "pre-compact", "--project", str(self.project)],
            input=json.dumps(full), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            cwd=str(self.project), env=os.environ)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self._metrics(), [])


if __name__ == "__main__":
    unittest.main()

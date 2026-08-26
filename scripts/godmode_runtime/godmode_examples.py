"""C-24: worked examples as a reproducible fixture corpus.

`docs/DEMO.md` pins its commands against the parser, which proves a
command exists and nothing about what it returns. An example here names a
command, the keys its payload must carry, and the exit code it must
return, and `check_examples` runs every one against the real console in a
throwaway project under a throwaway state home. A worked example that
drifts from the code fails the check instead of misleading a reader.

Each example is one `*.example.json` file:

    {"name": ..., "setup": [["init"]], "command": ["doctor"],
     "expect_keys": ["healthy"], "expect_exit": 0}

`setup` is optional - the commands to run first, in order, whose results
are not checked. Everything runs in-process; no subprocess, no network.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from .godmode_errors import GodmodeError

SUFFIX = ".example.json"


def load_examples(corpus: Path | str) -> list[dict[str, Any]]:
    corpus = Path(corpus)
    examples: list[dict[str, Any]] = []
    for path in sorted(corpus.glob(f"*{SUFFIX}")):
        try:
            example = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GodmodeError(f"Example is unreadable: {path.name}: {exc}") from exc
        for key in ("name", "command", "expect_keys", "expect_exit"):
            if key not in example:
                raise GodmodeError(f"Example {path.name} lacks `{key}`")
        example["_path"] = path.name
        examples.append(example)
    return examples


Runner = Callable[[list[str]], int]


def _run(runner: Runner, project: Path, argv: list[str]) -> tuple[int, Any]:
    # The console is handed in, never imported: this module must not
    # depend on the console that depends on it, and the atlas's
    # import-cycle test reads imports statically, so a lazy import inside
    # a function would still be a cycle on paper.
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = runner(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    try:
        payload = json.loads(text) if text else None
    except json.JSONDecodeError:
        payload = text
    return code, payload


def check_examples(corpus: Path | str, runner: Runner) -> dict[str, Any]:
    """`runner` is the console's `main`; it is passed in so this module
    never imports the console that imports it."""
    results: list[dict[str, Any]] = []
    for example in load_examples(corpus):
        with tempfile.TemporaryDirectory(prefix="godmode-example-") as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            state = Path(temporary) / "state"
            previous = os.environ.get("GODMODE_STATE_HOME")
            os.environ["GODMODE_STATE_HOME"] = str(state)
            try:
                for step in example.get("setup", []):
                    _run(runner, project, [str(token) for token in step])
                code, payload = _run(runner, project, [str(token) for token in example["command"]])
            finally:
                if previous is None:
                    os.environ.pop("GODMODE_STATE_HOME", None)
                else:
                    os.environ["GODMODE_STATE_HOME"] = previous
        present = set(payload) if isinstance(payload, dict) else set()
        missing = [key for key in example["expect_keys"] if key not in present]
        ok = code == int(example["expect_exit"]) and not missing
        results.append({
            "name": example["name"],
            "file": example["_path"],
            "command": example["command"],
            "exit": code,
            "expect_exit": int(example["expect_exit"]),
            "missing_keys": missing,
            "ok": ok,
        })
    stale = [r["name"] for r in results if not r["ok"]]
    return {
        "checked": len(results),
        "results": results,
        "stale": stale,
        "verdict": "stale" if stale else ("reproduced" if results else "empty"),
    }

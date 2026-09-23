"""Shared checks for the Plan 7 skill faces (Task 13's last pair, Task 14).

Every skill face is a thin routing face over verbs that already exist. The
checks here are the ones every face owes, whatever its flow:

- the bundle validates, lints on all four facets, and passes the
  frontmatter lint (negative-scope clause, PURPOSE.md with a `seq:` cite);
- `agents/openai.yaml` is hand-finished, not the forge's generated stub;
- every `godmode ...` command the Deterministic Execution Flow names
  resolves to a real verb path, and every `--flag` it passes is declared by
  that verb's own parser;
- every eval behaviour assertion runs a read-only command;
- the skill's positives route home and its near-negatives do not, measured
  in-process by the same router `godmode evals` uses;
- the skill could have been forged: `skill forge` accepts its purpose,
  routing rows and three cited successes inside a bare, non-git temp
  project (never the live archive).

Everything runs in-process through `godmode_console.main` - nothing spawns
the CLI - and every write lands in a temp project whose archive lives under
a temp `GODMODE_STATE_HOME`.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterator
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_evals import run_routing_evals  # noqa: E402
from godmode_runtime.godmode_forge import lint_skill, validate_skill  # noqa: E402
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402

# Flags the top-level parser owns; a flow may pass them before the verb.
_GLOBAL_FLAGS = {"--project", "--json", "--brief", "--terse", "--version"}
# Read-only command shapes an eval behaviour assertion may run against the
# live project: a parser's help, or the bundle validator/linter.
_READ_ONLY_ASSERTION = re.compile(
    r"^python scripts/godmode\.py (--project \. )?"
    r"(([a-z-]+ )+--help|skill (validate|lint) --path skills/[a-z-]+)$"
)
_SEQ_CITE = re.compile(r"seq:(\d+)")


def skill_dir(name: str) -> Path:
    return PLUGIN_ROOT / "skills" / name


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def flow_commands(directory: Path) -> list[str]:
    """Every inline-backticked `godmode ...` command in the flow section."""
    text = (directory / "SKILL.md").read_text(encoding="utf-8")
    flow = _section(text, "Deterministic Execution Flow")
    return [c for c in re.findall(r"`(godmode [^`]+)`", flow)]


def help_for(path: list[str]) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = console_main([*path, "--help"])
    except SystemExit as exc:  # argparse exits after printing help
        code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue()


def resolve_command(command: str) -> tuple[list[str], str, list[str]]:
    """(verb path, that path's help text, flags passed) for one flow command.

    The verb path is the longest run of plain words after `godmode` that the
    parser's own usage line confirms; a word past it is a positional. Raises
    AssertionError when not even the first word is a verb.
    """
    tokens = command.split()[1:]
    words: list[str] = []
    for token in tokens:
        if not re.fullmatch(r"[a-z][a-z-]*", token):
            break
        words.append(token)
    for depth in range(len(words), 0, -1):
        path = words[:depth]
        code, text = help_for(path)
        if code == 0 and text.startswith("usage: godmode " + " ".join(path)):
            flags = [t.split("=", 1)[0] for t in tokens if t.startswith("--")]
            return path, text, [f for f in flags if f not in _GLOBAL_FLAGS]
    raise AssertionError(f"no godmode verb resolves for: {command}")


def assert_flow_verbs_exist(case, directory: Path) -> None:
    commands = flow_commands(directory)
    case.assertGreaterEqual(len(commands), 3, "a flow names at least three commands")
    for command in commands:
        path, text, flags = resolve_command(command)
        for flag in flags:
            case.assertIn(flag, text, f"{' '.join(path)} declares no {flag} ({command})")


def assert_bundle(case, directory: Path) -> None:
    validated = validate_skill(directory)
    case.assertTrue(validated["valid"], validated)
    case.assertGreaterEqual(validated["positive_cases"], 2)
    case.assertGreaterEqual(validated["near_negative_cases"], 2)
    case.assertGreaterEqual(validated["assertions"], 1)
    linted = lint_skill(directory)
    case.assertTrue(linted["passed"], linted)
    front = lint_frontmatter(directory)
    case.assertTrue(front["passed"], front)
    case.assertEqual(front["findings"], [])
    text = (directory / "SKILL.md").read_text(encoding="utf-8")
    case.assertIn("Not for", text.split("---")[1])
    for heading in ("Use", "Do Not Use", "Deterministic Execution Flow", "Must Not"):
        case.assertTrue(_section(text, heading).strip(), f"missing section {heading}")
    purpose = (directory / "PURPOSE.md").read_text(encoding="utf-8")
    case.assertGreaterEqual(len(set(_SEQ_CITE.findall(purpose))), 2, "PURPOSE cites two records")


def assert_openai_yaml_hand_finished(case, directory: Path) -> None:
    text = (directory / "agents" / "openai.yaml").read_text(encoding="utf-8")
    case.assertNotIn("Generated locally by Godmode", text)
    case.assertNotIn("...", text)
    case.assertNotIn("to complete this request and prove its acceptance checks", text)
    case.assertIn(f"${directory.name}", text)


def assert_assertions_read_only(case, directory: Path) -> None:
    data = json.loads((directory / "godmode-evals.json").read_text(encoding="utf-8"))
    checks = [a["check"] for a in data["behavior_assertions"] if isinstance(a, dict)]
    case.assertTrue(checks, "at least one executable behaviour assertion")
    for check in checks:
        case.assertRegex(check["command"], _READ_ONLY_ASSERTION)
        # The command must also resolve: run its help in-process.
        argv = check["command"].split()[2:]
        if argv[:2] == ["--project", "."]:
            argv = argv[2:]
        if argv[-1] == "--help":
            code, text = help_for(argv[:-1])
            case.assertEqual(code, 0, check["command"])
            case.assertIn(check["expect_contains"], text, check["command"])


def assert_routes_cleanly(case, name: str) -> None:
    report = run_routing_evals(PLUGIN_ROOT)
    entry = report["skills"][name]
    case.assertEqual(entry["positives_routed_correctly"], entry["positives_total"],
                     entry["misrouted"])
    case.assertEqual(entry["near_negatives_rejected"], entry["near_negatives_total"],
                     entry["misrouted"])


@contextmanager
def isolated_project() -> Iterator[tuple[Path, Chronicle]]:
    """A bare, non-git temp project with its own initialized archive."""
    with tempfile.TemporaryDirectory(prefix="godmode-face-") as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        environment = {"GODMODE_STATE_HOME": str(state), "GODMODE_SESSION": "",
                       "GODMODE_AGENT_ID": "", "GODMODE_AS_OPERATOR": ""}
        with mock.patch.dict(os.environ, environment, clear=False):
            anchor = resolve_anchor(project)
            assert not anchor.is_git, "a face fixture must never be a git repository"
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


def run(project: Path, *argv: str) -> tuple[int, dict]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = console_main(["--project", str(project), "--json", *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    text = out.getvalue().strip() or err.getvalue().strip()
    try:
        return code, (json.loads(text) if text else {})
    except json.JSONDecodeError:
        return code, {"raw": text}


def assert_forges(case, directory: Path) -> None:
    """`skill forge` accepts this face's own purpose and routing rows, with
    three distinct cited successes, inside a bare non-git temp project."""
    data = json.loads((directory / "godmode-evals.json").read_text(encoding="utf-8"))
    text = (directory / "SKILL.md").read_text(encoding="utf-8")
    description = re.search(r"^description:\s*\"?(.*?)\"?\s*$", text, re.M).group(1)
    with isolated_project() as (project, archive):
        cites = [
            f"seq:{archive.append('action', f'face-success-{i}', {'gate': 'allow'})['sequence']}"
            for i in range(3)
        ]
        argv = ["skill", "forge", "--name", directory.name,
                "--purpose", description.split(". ")[0],
                "--gap-evidence", "The same workflow was run by hand in two separate sessions",
                "--repeated-uses", "3"]
        for cite in cites:
            argv += ["--success-evidence", cite]
        for prompt in data["routing"]["positive"]:
            argv += ["--positive", prompt]
        for prompt in data["routing"]["near_negative"]:
            argv += ["--negative", prompt]
        argv += ["--assertion", "reports its verdict from a real verb"]
        code, payload = run(project, *argv)
        case.assertEqual(code, 0, payload)
        case.assertEqual(payload["skill_impact"]["outcome"], "accepted", payload)
        case.assertTrue((project / "skills" / directory.name / "SKILL.md").is_file())

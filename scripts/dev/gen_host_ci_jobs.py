#!/usr/bin/env python3
"""NS-8e: renders one CI job per host manifest into the marker-delimited
`# godmode:host-jobs:begin` / `# godmode:host-jobs:end` block of
`.github/workflows/godmode-verify.yml`, and keeps the `required` job's
`needs:` list carrying every generated job's name - both read from the
generator, never retyped by hand, so a host cannot join
`HOOK_ARTIFACTS`/`WIRE_HOSTS` without also gaining a CI leg that proves it
installs and denies.

**Which hosts get a job.** `_union_hosts()` is the union of
`godmode_host_manifests.HOOK_ARTIFACTS` (every host with a generated hook
manifest), `godmode_wire.WIRE_HOSTS` (every host with a project-level wire
route), and Claude - which has neither (it reads `hooks/hooks.json` by
convention, the same shared file Grok also loads: `packaging/hosts.json`'s
own `hosts.claude.note` says so) and would otherwise be the one host this
job set silently skipped.

**How each host installs.** A host in `WIRE_HOSTS` installs the way its own
CLI route does: `hooks wire --host <h>` into a scratch project, then a
`test -f` on the exact path `godmode_wire.wire()` itself reports (a dry run
against a throwaway directory, read here rather than retyped, so a target
path change in that module moves this generator's assertion with it - see
`_wire_target_rel`). A host with no wire route reads its bundled artifact
by convention or by a dedicated builder with nothing yet to merge it into a
project (`packaging/hosts.json`'s `hook_manifests` table is the one place
that names the on-disk path either way); installing it is the same act a
plugin marketplace install already performs for these paths - copying the
file into place - so that copy is what this job does too, then greps the
copy for the launcher reference every one of these manifests carries
(`run-hook.cmd`, checked while `.claude-plugin`/`.grok-plugin`/etc. name a
polyglot launcher; `hooks/run-hook.sh`'s own POSIX generation is Task 3's
concern, not this file's).

**How every job fires and asserts.** Uniform, regardless of install method:
govern the scratch project (`godmode init`, the same step
`stock-host-windows` already takes for the same reason - an ungoverned
checkout answers a protected command with a silent allow by design), then
feed a `git push --force` PreToolUse payload to `hooks/run-hook.sh` and
require `"deny"` in its stdout. A launcher that stops working - wrong exit
code, no JSON, no deny - turns every one of these jobs red, not just one,
because every job fires through the identical shared script; that is also
what makes the corrupted-launcher half of `tests/test_ci_host_jobs.py`'s
red proof host-independent.

**Single source of truth.** `install_body_lines(host)` and
`FIRE_BODY_LINES` are the literal shell text this module puts inside the
generated workflow's `run:` blocks; `tests/test_ci_host_jobs.py` imports
and executes those same lines directly (wrapped in its own `project=`/
`launcher=` preamble) rather than re-describing the logic in Python, so the
committed workflow and the local red test can never quietly disagree about
what a job does.

Usage: `python scripts/dev/gen_host_ci_jobs.py` writes
`.github/workflows/godmode-verify.yml`; `--check` exits 1 (naming the
regenerate command) if the committed file has drifted from what this
module would write today.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from godmode_runtime import godmode_host_manifests as host_manifests  # noqa: E402
from godmode_runtime import godmode_wire  # noqa: E402

WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "godmode-verify.yml"
HOSTS_JSON_PATH = REPO_ROOT / "packaging" / "hosts.json"

BEGIN_MARKER = "  # godmode:host-jobs:begin"
END_MARKER = "  # godmode:host-jobs:end"

# The `required` job's own `needs:` line, byte-exact as it reads before this
# generator ever touches it - matched once, replaced with the same list plus
# every generated job name appended, sorted.
BASE_NEEDS = ("verify", "verify-windows", "stock-host", "stock-host-windows", "netgate", "corpus-differential",
              "vuln-scan", "action",
              "preflight-shard")
_NEEDS_PREFIX = "    needs: ["

# Claude has no `HOOK_ARTIFACTS` builder and no `WIRE_HOSTS` route: it reads
# `hooks/hooks.json` by convention, the same shared file Grok's
# "merge-into-shared" mode also targets (packaging/hosts.json's own
# `hosts.claude.note`). Named here, not derived, because nothing in the
# runtime declares this convention as data the way `HOOK_ARTIFACTS` does for
# every other host.
_CLAUDE_SHARED_FILE = "hooks/hooks.json"

# Every command payload fired below is the identical protected-class probe
# `stock-host-windows` already uses to prove the same launcher denies under
# pwsh - one payload, one deny, proven per host's own install path.
_PROTECTED_COMMAND = "git push --force origin main"

# The literal shell body every fire step runs, referencing `$project` and
# `$launcher` set by the caller's own preamble (the generated YAML sets
# `project="$RUNNER_TEMP/godmode-host-<h>/project"` and
# `launcher="./hooks/run-hook.sh"`; the local test sets both to real
# filesystem paths - see this module's docstring, "single source of truth").
FIRE_BODY_LINES: tuple[str, ...] = (
    'python scripts/godmode.py --project "$project" init >/dev/null',
    'payload=\'{"hook_event_name":"PreToolUse","cwd":"\'"$project"\'","tool_name":"Bash",'
    f'"tool_input":{{"command":"{_PROTECTED_COMMAND}"}}}}\'',
    'out=$(printf \'%s\' "$payload" | "$launcher" godmode_gate_fast.py) '
    '|| { echo "hook exited non-zero"; exit 1; }',
    'printf \'%s\' "$out" | grep -q \'"deny"\' '
    '|| { echo "gate did not deny a protected command: $out"; exit 1; }',
    'echo "denied a protected command through the launcher: ok"',
)


def _union_hosts() -> list[str]:
    """Every host this generated job set covers - see the module docstring's
    "which hosts get a job" section."""
    names = set(host_manifests.HOOK_ARTIFACTS) | set(godmode_wire.WIRE_HOSTS) | {"claude"}
    return sorted(names)


def _hook_manifest_source(host: str) -> str:
    """The repo-relative path to copy for a host with no wire route -
    `packaging/hosts.json`'s own `hook_manifests` table for every host it
    names, or the shared-file convention above for Claude, which that table
    does not carry at all (it is identical to Grok's own entry there)."""
    if host == "claude":
        return _CLAUDE_SHARED_FILE
    data = json.loads(HOSTS_JSON_PATH.read_text(encoding="utf-8"))
    return data["hook_manifests"][host]["path"]


def _wire_target_rel(host: str) -> str:
    """The exact project-relative path `hooks wire --host <host>` writes,
    read from `godmode_wire.wire()` itself against a throwaway directory
    (never applied - `dry_run=True`) rather than retyped, so a target path
    change in that module moves this assertion with it instead of leaving
    it to silently disagree. Copilot's own plan line names two targets
    (`.github/hooks/godmode.json + .github/copilot-instructions.md`); only
    the first - the actual hook manifest - is the artifact this job
    asserts on."""
    with tempfile.TemporaryDirectory() as scratch:
        result = godmode_wire.wire(Path(scratch), [host], dry_run=True, force=False)
    line = result["lines"][0]
    _, _, rel = line.partition(f"{host}: ")
    rel = rel.split(" + ", 1)[0].strip()
    return rel.replace("\\", "/")


def _copy_dest_name(host: str) -> str:
    source = _hook_manifest_source(host)
    suffix = Path(source).suffix or ".json"
    return f"installed-{host}-manifest{suffix}"


def install_body_lines(host: str) -> list[str]:
    """The literal shell lines a host's install step runs, referencing
    `$project` (see `FIRE_BODY_LINES` for the shared-preamble convention).
    Two shapes only: a host in `WIRE_HOSTS` installs through its own CLI
    route; every other host installs by copying its bundled artifact into
    place, the same act a plugin marketplace install performs for it."""
    if host in godmode_wire.WIRE_HOSTS:
        rel = _wire_target_rel(host)
        return [
            f'python scripts/godmode.py --project "$project" hooks wire --host {host}',
            f'test -f "$project/{rel}" '
            f'|| {{ echo "hooks wire --host {host} did not create {rel}"; exit 1; }}',
        ]
    source = _hook_manifest_source(host)
    dest = _copy_dest_name(host)
    return [
        f'cp "{source}" "$project/{dest}"',
        f'grep -q "run-hook" "$project/{dest}" '
        f'|| {{ echo "{host}\'s bundled manifest does not reference the launcher"; exit 1; }}',
    ]


def _job_name(host: str) -> str:
    return f"host-{host}"


def _indent(lines: list[str], spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(f"{pad}{line}" for line in lines)


def render_job(host: str) -> str:
    name = _job_name(host)
    install_lines = [
        "set -e",
        'project="$RUNNER_TEMP"/godmode-host-' + host + "/project",
        'mkdir -p "$project"',
        *install_body_lines(host),
    ]
    fire_lines = [
        "set -e",
        'project="$RUNNER_TEMP"/godmode-host-' + host + "/project",
        'launcher="./hooks/run-hook.sh"',
        'export GODMODE_STATE_HOME="$RUNNER_TEMP"/godmode-host-' + host + "/state",
        *FIRE_BODY_LINES,
    ]
    return (
        f"  {name}:\n"
        f'    name: "Install and fire: {host}"\n'
        # The `hosts` dispatch input narrows the run to a subset of the hosts.
        # `all` (the default) runs every one; naming a subset skips the rest,
        # and the aggregate job then reports the run as incomplete rather than
        # green - which is what a narrowed run is.
        f"    if: ${{{{ (inputs.hosts || 'all') == 'all' || contains(format(',{{0}},', (inputs.hosts || 'all')), ',{host},') }}}}\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 10\n"
        "    env:\n"
        '      GODMODE_ATTENDED: "1"\n'
        "    steps:\n"
        "      - name: Check out repository\n"
        "        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7\n"
        "        with:\n"
        "          persist-credentials: false\n"
        "\n"
        "      - name: Set up Python\n"
        "        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7\n"
        "        with:\n"
        '          python-version: "3.13"\n'
        "\n"
        f"      - name: Install the plugin the way {host} does\n"
        "        run: |\n"
        f"{_indent(install_lines, 10)}\n"
        "\n"
        "      - name: Govern the project and fire one hook through the launcher\n"
        "        run: |\n"
        f"{_indent(fire_lines, 10)}\n"
    )


def render_jobs_block() -> str:
    hosts = _union_hosts()
    jobs = "\n".join(render_job(host) for host in hosts)
    return f"{BEGIN_MARKER}\n{jobs}{END_MARKER}\n"


def render_needs_line() -> str:
    names = BASE_NEEDS + tuple(_job_name(host) for host in _union_hosts())
    return f"{_NEEDS_PREFIX}{', '.join(names)}]"


def generate_workflow(current_text: str) -> str:
    """Splice the generated job block between the marker pair and refresh
    the `required` job's `needs:` line - the two regions this generator
    owns in an otherwise hand-authored file (the same "region, not whole
    file" split `godmode_reach.generate_matrix_document` already uses for
    `docs/HOST-FEATURE-REACH.md`)."""
    if BEGIN_MARKER not in current_text or END_MARKER not in current_text:
        raise ValueError(
            f"{WORKFLOW_PATH} is missing its {BEGIN_MARKER!r}/{END_MARKER!r} "
            "marker pair; the generator has nowhere to write"
        )
    before, rest = current_text.split(BEGIN_MARKER, 1)
    _old_block, after = rest.split(END_MARKER, 1)
    if not after.startswith("\n"):
        raise ValueError(f"{WORKFLOW_PATH}: no newline after {END_MARKER!r}")
    after = after[1:]
    spliced = f"{before}{render_jobs_block()}{after}"

    if _NEEDS_PREFIX not in spliced:
        raise ValueError(
            f"{WORKFLOW_PATH} is missing the required job's {_NEEDS_PREFIX!r} line"
        )
    needs_before, needs_rest = spliced.split(_NEEDS_PREFIX, 1)
    _old_needs, needs_after = needs_rest.split("]", 1)
    return f"{needs_before}{render_needs_line()}{needs_after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 if the committed workflow has drifted from the generator, "
             "without writing anything")
    args = parser.parse_args(argv)

    current = WORKFLOW_PATH.read_text(encoding="utf-8")
    generated = generate_workflow(current)

    if args.check:
        if generated != current:
            print(
                f"{WORKFLOW_PATH} is stale - regenerate with "
                "`python scripts/dev/gen_host_ci_jobs.py`",
                file=sys.stderr,
            )
            return 1
        print(f"{WORKFLOW_PATH} matches the generator")
        return 0

    WORKFLOW_PATH.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {WORKFLOW_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

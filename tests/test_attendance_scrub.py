"""AST enumeration of hook-spawning tests that skip the attendance scrub.

NS-10k fix round 2 (`task-14-rereview.md` B1): `CI=1 python -m unittest
discover -s tests` is the only way to *prove* every module inherits the
ambient `CI` GitHub Actions sets, and it is banned on this machine (a
memory-kill class the round-2 instructions name explicitly). This scans
statically instead: any `subprocess.run`/`Popen`/`check_output` call whose
argv references a shipped hook entry point (`godmode_session_hook.py`,
`godmode_gate_fast.py`, `godmode.py`, `run-hook.cmd`/`.sh`) inherits
`os.environ` - `CI` included - unless the module opts into `_host_env`'s
scrub (`scrubbed_environment` or its plain-dict sibling `scrubbed_env`).
`tests/test_observe_mode.py` and `tests/test_launcher_root_fallback.py`
proved this is a live defect, not a theoretical one: both flipped an
`ask`/`allow` assertion to `deny` under a real `CI=1` run before this round
fixed them.

Forty-seven modules were already unscrubbed before this round, most of them
built for reasons that have nothing to do with the unattended tier. Making
every one of them attendance-safe is not what this round's fix was scoped
to (`task-14-rereview.md`'s ordered fix list names the observe/launcher
pair and every `HOST_MARKERS` importer, not a clean sweep). This test is a
ratchet, the same shape `test_swallow_ratchet_gate.py` already uses for its
own baseline: the pre-existing offenders are named once, below, so the
scan can hold the line - no new unscrubbed spawner, and none of the
modules this round just fixed sliding back - without demanding a rewrite
of forty-seven files nobody asked for this round.

Fix round 3 (NS-10k, task-14-rereview2.md B-B): the scan above described
itself as finding "any `subprocess.run`/`Popen`/`check_output` call ...
that inherits `os.environ`", but only matched a call whose *own source
segment* named a hook file or a name this module assigned from one at
module/class/function scope. Three of the nine round-2 fixes route the
spawn through a helper function whose *parameter* receives the hook path
or argv (`test_antigravity_allow._run`, `test_hook_stdin
._exits_with_stdin_held_open`, `test_launcher_isolation._run`) - the scan
never classified them as hook spawners at all, so `KNOWN_OFFENDERS` and
`test_the_named_fix_round_two_modules_stay_scrubbed` could not have caught
a revert of any of the three: reverting them to build `env=` from
`HOST_MARKERS` by hand left both tests in this module green. The scan now
also resolves one level of indirection - a `subprocess.*` call inside a
helper function, where the implicated parameter is bound to a hook name at
some call site to that helper, in this module. It still cannot see an
in-process `attended()` call with no subprocess at all, or a spawn two
calls removed from the hook path; that remains outside a static AST scan
of this shape, not something this round claims to fix.

`_imports_the_scrub` now checks that the imported name is actually called
somewhere in the module, not merely imported - a module that imports
`scrubbed_env` for one call and builds a second call's `env=` by hand used
to read as fully clean.

Fix round 4 (`task-14-rereview3.md` N-3/N-4/N-5): the one LIVE two-level
case is named rather than left implied. `tests/test_opencode_plugin.py`
builds `env = {**os.environ, ...}` and spawns `bun run harness.mjs`, which
loads the shipped OpenCode shim, which spawns the fast gate with that
inherited environment - Python -> JS shim -> hook, two calls removed, so
this scan reads the module as not spawning a hook at all and it is not on
the baseline below. Only the job-wide `GODMODE_ATTENDED=1` layer covers it.
Harmless today: the class is `skipUnless(BUN)` and its two
attendance-sensitive fixtures assert `blocked` plus "authorize stage", which
holds on either row, because that host folds an ask to a deny anyway and the
unattended sentence is appended, not substituted. Also this round: the verb
list gained `call`/`getoutput`/`getstatusoutput` and `os`'s own spawn verbs,
`from subprocess import run` binds a bare callable name the scan now sees,
a `*args` unpack stops positional matching instead of sliding it, and an
attribute call site must be `self`/`cls`'s own helper. All latent: the
47-name baseline below is byte-identical before and after.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

_HOOK_NAMES = (
    "godmode_session_hook.py", "godmode_gate_fast.py", "godmode.py",
    "run-hook.cmd", "run-hook.sh",
)
_SUBPROCESS_FUNCS = frozenset({
    "run", "Popen", "check_output", "check_call", "call", "getoutput",
    "getstatusoutput",
})
# Fix round 4 (task-14-rereview3.md N-4): the spawn verbs that are not
# `subprocess.*` at all. None is in live use in this suite today - the only
# `os.system` text under `tests/` is a fixture source string written to disk
# - but the scan claims to enumerate hook spawners, and a spawn through
# `os.system` inherits `os.environ` exactly as `subprocess.run` does.
_OS_SPAWN_FUNCS = frozenset({
    "system", "popen", "execv", "execve", "execvp", "execvpe", "execl",
    "execle", "execlp", "spawnv", "spawnve", "spawnvp", "spawnl", "spawnle",
    "spawnlp",
})

# Pre-existing offenders (2026-09-17, fix round 2): modules this scan finds
# spawning a shipped hook entry point through `subprocess` with no
# `_host_env` scrub, as of this round - none of them touched this round.
# `task-14-rereview.md` bounded the fix to `test_observe_mode.py`,
# `test_launcher_root_fallback.py`, and every module that imports
# `HOST_MARKERS` directly (fixed above); this baseline is the honest
# accounting of what is left, not an endorsement that leaving them
# unscrubbed is safe. A name coming off this list (by fixing that module)
# is always welcome and never breaks this test; a name the scan finds that
# is NOT on this list is a regression and fails it.
KNOWN_OFFENDERS = frozenset({
    "test_authorize_ux", "test_brief_next_actions", "test_ci_gates",
    "test_console_exits", "test_convention_docs", "test_day_one_face",
    "test_design_boundary", "test_donebar_roles", "test_evals",
    "test_evals_models", "test_evaluator_pins", "test_failure_semantics",
    "test_falsifier_aging", "test_gate_falsifiability", "test_gate_fast",
    "test_githooks", "test_godmode_runtime", "test_grok_brief_delivery",
    "test_hookproof", "test_hooks_manifest_polyglot",
    "test_host_reports_0_3_25", "test_inline_interpreter_scan",
    "test_investigation_nudge", "test_law", "test_obligation_siblings",
    "test_onboarding", "test_pretool_gate", "test_prompt_shape_nudges",
    "test_request_hook", "test_requests", "test_resume_digest",
    "test_s11_loops", "test_s7_field_gaps", "test_scope_fence",
    "test_session_log", "test_silence_reinjection", "test_stage_from_refusal",
    "test_stop_claim_advisory", "test_stop_completion_gate",
    "test_subagent_scope", "test_tag_push_ci_gate", "test_timeline_advisories",
    "test_tool_gates", "test_two_reversals", "test_usage_ledger",
    "test_verify_offline", "test_verify_promotion",
})


def _hook_labeled_names(tree: ast.AST, source: str) -> set[str]:
    """Names assigned a value whose source mentions a hook entry point,
    e.g. `HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"`, at a
    plain assignment (`ast.Assign`, any scope - module, class or function)
    or an annotated one (`ast.AnnAssign`, e.g. `HOOK: Path = ...`)."""
    labeled: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target] if node.target is not None else []
        else:
            continue
        if value is None:
            continue
        segment = ast.get_source_segment(source, value) or ""
        if any(name in segment for name in _HOOK_NAMES):
            for target in targets:
                if isinstance(target, ast.Name):
                    labeled.add(target.id)
    return labeled


def _subprocess_aliases(tree: ast.AST) -> set[str]:
    """Names bound to the `subprocess` module: the bare name plus any
    `import subprocess as X` alias."""
    aliases = {"subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess" and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def _bare_spawn_names(tree: ast.AST) -> set[str]:
    """Fix round 4 (N-4): names bound to a spawn function directly, by
    `from subprocess import run` / `from subprocess import run as _run` (and
    the same for `os`'s own spawn verbs) - a call through one of these is an
    `ast.Name` call, which the attribute-shaped matcher below cannot see. No
    live use in this suite today; latent, like the widened verb list."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "subprocess":
            verbs = _SUBPROCESS_FUNCS
        elif node.module == "os":
            verbs = _OS_SPAWN_FUNCS
        else:
            continue
        for alias in node.names:
            if alias.name in verbs:
                bound.add(alias.asname or alias.name)
    return bound


def _is_subprocess_call(node: ast.Call, aliases: set[str],
                        bare_names: set[str] | None = None) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in (bare_names or set())
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
        return False
    if func.value.id in aliases and func.attr in _SUBPROCESS_FUNCS:
        return True
    return func.value.id == "os" and func.attr in _OS_SPAWN_FUNCS


def _param_names(func: ast.AST) -> list[str]:
    args = func.args
    names = [a.arg for a in getattr(args, "posonlyargs", [])]
    names.extend(a.arg for a in args.args)
    names.extend(a.arg for a in args.kwonlyargs)
    if args.vararg:
        names.append(args.vararg.arg)
    return names


def _enclosing_function_map(tree: ast.AST) -> dict:
    """Map each descendant node's `id()` to the nearest enclosing
    `FunctionDef`/`AsyncFunctionDef`, if any - one pass, not one `ast.walk`
    per function."""
    enclosing: dict = {}

    def _walk(node: ast.AST, current) -> None:
        for child in ast.iter_child_nodes(node):
            if current is not None:
                enclosing[id(child)] = current
            next_current = child if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)) else current
            _walk(child, next_current)

    _walk(tree, None)
    return enclosing


def _spawns_a_hook(path: Path) -> bool:
    """Whether `path` contains a `subprocess.run`/`Popen`/`check_output`/
    `check_call` call (through a plain or aliased `subprocess` import)
    whose argv names a shipped hook entry point: directly in the call's own
    source, through a module-/class-/function-level constant this file
    itself assigned from one, or through a helper function's parameter that
    some call site in this module binds to one of those names. A spawn two
    calls removed from the hook path (`tests/test_opencode_plugin.py`'s
    Python -> JS shim -> hook is the one live instance), or an in-process
    `attended()` call with no subprocess at all, is outside what this static
    scan can see."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return False

    aliases = _subprocess_aliases(tree)
    bare_names = _bare_spawn_names(tree)
    labeled_patterns = [re.compile(r"\b" + re.escape(name) + r"\b")
                        for name in _hook_labeled_names(tree, source)]

    def _names_a_hook(segment: str) -> bool:
        if any(name in segment for name in _HOOK_NAMES):
            return True
        return any(pattern.search(segment) for pattern in labeled_patterns)

    func_by_name: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_by_name[node.name] = node

    enclosing_of = _enclosing_function_map(tree)

    # helper name -> set of that helper's own parameter names implicated in
    # a subprocess call inside its body (segment named no hook directly).
    helper_param_hits: dict = {}

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and _is_subprocess_call(node, aliases, bare_names)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if _names_a_hook(segment):
            return True
        enclosing = enclosing_of.get(id(node))
        if enclosing is None:
            continue
        params = set(_param_names(enclosing))
        used = {p for p in params
                if re.search(r"\b" + re.escape(p) + r"\b", segment)}
        if used:
            helper_param_hits.setdefault(enclosing.name, set()).update(used)

    for func_name, params in helper_param_hits.items():
        func_node = func_by_name.get(func_name)
        if func_node is None:
            continue
        order = _param_names(func_node)
        for node in ast.walk(tree):
            if node is func_node:
                continue
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif (isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in ("self", "cls")):
                # Fix round 4 (N-5): `self._run(HOOK)` is the live shape (a
                # TestCase method helper); `anything._run(HOOK)` used to
                # match a module-level `_run` of the same name, which is a
                # different function.
                call_name = node.func.attr
            else:
                continue
            if call_name != func_name:
                continue
            for index, arg in enumerate(node.args):
                if isinstance(arg, ast.Starred):
                    # Fix round 4 (N-5): every position after a `*args`
                    # unpack is statically unknowable, so stop rather than
                    # keep counting and line arguments up against the wrong
                    # parameter name. Keyword arguments below are unaffected.
                    break
                if index < len(order) and order[index] in params:
                    arg_segment = ast.get_source_segment(source, arg) or ""
                    if _names_a_hook(arg_segment):
                        return True
            for kw in node.keywords:
                if kw.arg in params:
                    kw_segment = ast.get_source_segment(source, kw.value) or ""
                    if _names_a_hook(kw_segment):
                        return True
    return False


def _imports_the_scrub(path: Path) -> bool:
    """Whether the module both imports `scrubbed_environment`/`scrubbed_env`
    from `_host_env` AND actually calls one of them somewhere - importing
    alone (and building a call's `env=` by hand anyway) does not count."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return False
    imported_as: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("_host_env"):
            for alias in node.names:
                if alias.name in ("scrubbed_environment", "scrubbed_env"):
                    imported_as.add(alias.asname or alias.name)
    if not imported_as:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in imported_as:
            return True
        if isinstance(func, ast.Attribute) and func.attr in imported_as:
            return True
    return False


_OFFENDERS_CACHE: list | None = None


def _current_offenders() -> list:
    """`_spawns_a_hook`/`_imports_the_scrub` re-parse every test file on
    every call; both tests below call this once each, and the result is a
    deterministic function of files already on disk for the duration of the
    process, so compute it once."""
    global _OFFENDERS_CACHE
    if _OFFENDERS_CACHE is None:
        offenders = []
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            if path.stem == "test_attendance_scrub":
                continue
            if _spawns_a_hook(path) and not _imports_the_scrub(path):
                offenders.append(path.stem)
        _OFFENDERS_CACHE = offenders
    return _OFFENDERS_CACHE


class AttendanceScrubRatchetTests(unittest.TestCase):
    def test_no_new_unscrubbed_hook_spawner(self) -> None:
        offenders = set(_current_offenders())
        new = sorted(offenders - KNOWN_OFFENDERS)
        self.assertEqual(
            new, [],
            "these modules spawn a shipped hook via subprocess with no "
            "_host_env scrub and are not on the known-offender baseline "
            "(task-14-rereview.md B1) - either fix them or add them to "
            "KNOWN_OFFENDERS if the module was already this way: "
            + ", ".join(new))

    def test_the_named_fix_round_two_modules_stay_scrubbed(self) -> None:
        """Pinned separately from the ratchet above so a revert of any one
        of these specific fixes fails with a clear name, not just a set
        difference. These are exactly the modules `task-14-rereview.md`
        named or enumerated (`test_observe_mode.py`,
        `test_launcher_root_fallback.py`, and every `HOST_MARKERS`
        importer)."""
        protected = (
            "test_observe_mode", "test_launcher_root_fallback",
            "test_advisory_channel", "test_antigravity_allow",
            "test_cursor_stop", "test_hook_stdin", "test_launcher_isolation",
            "test_subagent_stop", "test_turn_tripwires",
        )
        offenders = set(_current_offenders())
        regressed = sorted(name for name in protected if name in offenders)
        self.assertEqual(regressed, [],
                         "fix round 2 scrubbed these modules; they must not "
                         "spawn a hook unscrubbed again: " + ", ".join(regressed))


if __name__ == "__main__":
    unittest.main()

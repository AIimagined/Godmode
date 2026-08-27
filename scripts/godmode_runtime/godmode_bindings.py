"""Generate every host manifest from one source, so identity cannot drift.

Three hosts is where hand-maintenance stops paying. A version, licence, author or
canonical URL that drifts on one host ships a different identity to that host's
users, and nothing surfaces it until someone compares the manifests by eye.

Projects that ship to many hosts converge on generation for this reason. The
source is one file; each host declares which fields it takes and what it adds.
Adding a fourth host is an entry, not a new tree to keep in step.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import godmode_host_manifests as host_manifests
from .godmode_errors import GodmodeError

SOURCE = "packaging/hosts.json"

# scripts/godmode_runtime/godmode_bindings.py -> parents[2] is the package
# root - the SAME `__file__`-relative resolution `godmode_hookproof.py`'s
# `_PACKAGE_ROOT` already uses, and for the identical reason:
# `registration_report`/`install_verify` report on GODMODE'S OWN shipped
# hook manifests, which live at the installed package's root, never at
# whatever project a caller happens to be governing (`runtime.anchor.
# project_root` in `godmode_console.py` is almost always a DIFFERENT
# directory - the user's repository, which does not ship a
# `packaging/hosts.json` of its own at all).
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _load(project: Path) -> dict[str, Any]:
    path = project / SOURCE
    if not path.is_file():
        raise GodmodeError(f"No binding source at {SOURCE}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GodmodeError(f"{SOURCE} is not valid JSON (line {exc.lineno}): {exc.msg}") from exc


def render(source: dict[str, Any], host: str) -> dict[str, Any]:
    """Build one host's manifest from the shared identity plus its own rules."""
    identity = source["identity"]
    spec = source["hosts"].get(host)
    if spec is None:
        raise GodmodeError(f"Unknown host '{host}'; known: {', '.join(sorted(source['hosts']))}")
    extra = spec.get("extra", {})

    manifest: dict[str, Any] = {}
    for field in spec["fields"]:
        if field in extra and field not in ("keywords_prefix", "author_url"):
            manifest[field] = extra[field]
            continue
        if field == "keywords":
            manifest[field] = list(extra.get("keywords_prefix", [])) + list(identity["keywords"])
            continue
        if field == "author":
            author = dict(identity["author"])
            # Some hosts reject unknown author fields; the shape differs, the name never does.
            if extra.get("author_url") is False:
                author.pop("url", None)
            manifest[field] = author
            continue
        if field in identity:
            manifest[field] = identity[field]
    return manifest


def _serialize(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def _render_hook_artifact(project: Path, host: str, mode: str) -> dict[str, Any]:
    """CX-3: the hook-manifest counterpart of `render()` above, for the
    second artifact kind `packaging/hosts.json`'s `hook_manifests` section
    declares. `mode` comes from that section, never guessed here.

    `merge-into-shared` (Codex today) is the one case that reads the target
    file rather than computing purely from source: Codex's own two managed
    keys are patched into WHATEVER the shared file's other, hand-authored
    keys (Claude's) currently hold, so drift detection only ever fires on
    Codex's own keys, never on an unrelated Claude-only edit. A target that
    does not exist yet reads as an empty base (`{"hooks": {}}`), so a
    from-scratch checkout still produces a valid file.
    """
    if mode == "merge-into-shared":
        target = project / source_hook_path(project, host)
        existing: dict[str, Any] = {"hooks": {}}
        if target.is_file():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {"hooks": {}}
        return host_manifests.merge_host_tools_into_shared(existing)
    artifact = host_manifests.HOOK_ARTIFACTS[host]
    return artifact["build"]()


def source_hook_path(project: Path, host: str) -> str:
    """The one place a hook artifact's path is read from - always
    `packaging/hosts.json`'s `hook_manifests` section, never a literal
    re-typed elsewhere.
    """
    source = _load(project)
    return source["hook_manifests"][host]["path"]


def _hook_manifest_specs(source: dict[str, Any]) -> dict[str, Any]:
    """`hook_manifests`, minus any `_comment`-style documentation key - the
    same convention `packaging/hosts.json` already uses for its `hosts` and
    `adapters` sections, applied here so a plain `.items()` walk never trips
    over a string value where a host spec dict is expected.
    """
    return {k: v for k, v in source.get("hook_manifests", {}).items() if not k.startswith("_")}


def check(project: Path) -> dict[str, Any]:
    """Report every manifest that has drifted from the source, without writing."""
    source = _load(project)
    results: list[dict[str, Any]] = []
    for host, spec in sorted(source["hosts"].items()):
        target = project / spec["path"]
        expected = _serialize(render(source, host))
        if not target.is_file():
            results.append({"host": host, "path": spec["path"], "state": "missing"})
            continue
        actual = target.read_text(encoding="utf-8")
        drifted = actual != expected
        entry: dict[str, Any] = {"host": host, "path": spec["path"],
                                 "state": "drifted" if drifted else "current"}
        if drifted:
            expected_obj = json.loads(expected)
            try:
                actual_obj = json.loads(actual)
            except json.JSONDecodeError:
                entry["differing_fields"] = ["<unparseable>"]
                results.append(entry)
                continue
            keys = set(expected_obj) | set(actual_obj)
            entry["differing_fields"] = sorted(
                k for k in keys if expected_obj.get(k) != actual_obj.get(k)
            ) or ["<formatting only>"]
        results.append(entry)

    for host, spec in sorted(_hook_manifest_specs(source).items()):
        target = project / spec["path"]
        expected = _serialize(_render_hook_artifact(project, host, spec["mode"]))
        if not target.is_file():
            results.append({"host": host, "path": spec["path"], "state": "missing", "kind": "hooks"})
            continue
        actual = target.read_text(encoding="utf-8")
        drifted = actual != expected
        entry = {"host": host, "path": spec["path"], "kind": "hooks",
                 "state": "drifted" if drifted else "current"}
        if drifted:
            entry["differing_fields"] = ["<hook-manifest-content>"]
        results.append(entry)

    drifted = [r for r in results if r["state"] != "current"]
    return {
        "source": SOURCE,
        "hosts": results,
        "drifted": len(drifted),
        "verdict": "current" if not drifted else "drifted",
    }


def write(project: Path) -> dict[str, Any]:
    """Regenerate every host manifest from the source."""
    source = _load(project)
    written: list[str] = []
    for host, spec in sorted(source["hosts"].items()):
        target = project / spec["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        content = _serialize(render(source, host))
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            written.append(spec["path"])

    for host, spec in sorted(_hook_manifest_specs(source).items()):
        target = project / spec["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        content = _serialize(_render_hook_artifact(project, host, spec["mode"]))
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            written.append(spec["path"])

    total = len(source["hosts"]) + len(_hook_manifest_specs(source))
    return {"source": SOURCE, "written": written, "unchanged": total - len(written)}


def registration_report(project: Path | None = None) -> dict[str, Any]:
    """CX-3/CX-1 integration: `hooks status`'s `host_registration` detail.

    `project` defaults to the resolved PACKAGE root (`_PACKAGE_ROOT`), not
    the project a caller happens to be governing - see `_PACKAGE_ROOT`'s own
    comment for why. A caller (a test, chiefly) may still pass an explicit
    `project` to point at a different checkout that also ships its own
    `packaging/hosts.json`.

    Structural and read-only ONLY - does this project's copy of each host's
    hook artifact exist, and does it match what the generator would produce
    right now (`godmode bindings --write` would leave it untouched). This
    deliberately never shells out to a host or reads a host's own runtime
    state - that is `install_verify`'s job, a separate, explicit action, not
    something a passive `status` read should ever trigger as a side effect.
    """
    project = project or _PACKAGE_ROOT
    source = _load(project)
    report: dict[str, Any] = {}

    claude_path = project / "hooks" / "hooks.json"
    report["claude"] = {
        "path": "hooks/hooks.json",
        "manifest_present": claude_path.is_file(),
        "declared_events": ["SessionStart", "UserPromptSubmit", "PreToolUse"],
        "state": "see `last_proof`/`verdict` above (CX-1 live proof, not a structural check)",
    }

    for host, spec in sorted(_hook_manifest_specs(source).items()):
        target = project / spec["path"]
        entry: dict[str, Any] = {"path": spec["path"], "manifest_present": target.is_file()}
        artifact = host_manifests.HOOK_ARTIFACTS.get(host, {})
        if target.is_file():
            expected = _render_hook_artifact(project, host, spec["mode"])
            try:
                actual = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                actual = None
            entry["current"] = actual == expected
            emitted_fn = artifact.get("emitted")
            if actual is not None and emitted_fn is not None:
                entry["declared_events"] = sorted(emitted_fn(actual))
            elif "allowed_events" in artifact:
                entry["declared_events"] = sorted(artifact["allowed_events"])
        gap = artifact.get("gap")
        if gap:
            entry["gap"] = gap
        entry["state"] = "unverifiable"
        report[host] = entry
    return report


# Codex's REAL `~/.codex/config.toml` schema (this repo's own build machine
# carries one - read directly, not guessed): a `[hooks.state]` table whose
# keys are `"<identifier>:<manifest-relative-path>:<event-name>:<n>:<n>"`
# (a plugin id like `godmode@aiimagined` for a marketplace install, or a
# bare filesystem path for a project-local `.codex/hooks.json` - but the
# manifest-relative-path/event-name/index suffix is stable), each holding a
# sub-table with `trusted_hash` always present and `enabled` present ONLY
# sometimes (this build's own godmode entry,
# `godmode@aiimagined:hooks/hooks.json:session_start:0:0`, has no `enabled`
# field at all - only `trusted_hash`).
#
# Fix round 1 (I1, review Important): the prior revision matched on the
# `hooks/hooks.json:<event>:<n>:<n>` SUFFIX alone, with no identifier check
# at all - a DECOY entry from any unrelated plugin that happens to also
# ship a file at that same conventional relative path, registered under an
# unrelated identifier, was silently credited to GODMODE's own registration
# state (the reviewer's live repro: a
# `some-other-plugin@evil:hooks/hooks.json:...` entry forced a false
# `"verified"`). The match is now anchored to the IDENTIFIER too: it must
# start with `<plugin-name>@` - the exact shape this build's own real state
# uses. `plugin_name` is read from `packaging/hosts.json`'s own
# `identity.name` at the call site, never a second, independently-typed
# "godmode" literal here, so this can never quietly drift from the name the
# rest of the package uses. A key whose identifier does not start with
# `<plugin-name>@` is SKIPPED entirely - not counted toward `registered`,
# not counted toward `missing` either (it says nothing about godmode's own
# state) - so a file with ZERO matching identifiers returns an empty dict,
# which `install_verify` then reports as every declared event missing
# (`"partial"`), never a false `"verified"` from unrelated evidence.
def _codex_state_key_pattern(plugin_name: str) -> re.Pattern[str]:
    escaped = re.escape(plugin_name)
    return re.compile(rf"^{escaped}@[^:]*:hooks/hooks\.json:([A-Za-z_][A-Za-z0-9_]*):\d+:\d+$")


def _read_codex_state(state_path: Path, plugin_name: str) -> dict[str, bool] | None:
    """Best-effort read of a Codex config file this process can find.

    `state_path` (an operator-supplied path, the conventional
    `~/.codex/config.toml`, or a test fixture) is read as TOML (stdlib
    `tomllib`, Python 3.11+ - this project's own minimum version). Any file
    that does not parse, or parses without a `[hooks].[state]` table,
    returns `None` - "this process could not read host state", never a
    guessed positive OR negative for an event this function does not
    understand the file well enough to judge.

    A key's own PRESENCE under `hooks.state`, ANCHORED TO THIS PLUGIN'S OWN
    IDENTITY (`_codex_state_key_pattern`, fix round 1 I1), is read as
    "Codex discovered and recorded this hook event for godmode" - true
    regardless of whether that entry also carries an explicit `enabled`
    field (this build's own real state shows an entry can exist with
    `trusted_hash` alone, no `enabled` key at all, and that is still a
    real, live registration - not "unverifiable"). An explicit
    `enabled = false`, when present, overrides that to `False`.
    """
    if not state_path.is_file():
        return None
    try:
        import tomllib
        with state_path.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:  # noqa: BLE001
        return None
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return None
    state = hooks.get("state")
    if not isinstance(state, dict):
        return None
    pattern = _codex_state_key_pattern(plugin_name)
    registered: dict[str, bool] = {}
    for key, value in state.items():
        match = pattern.match(str(key))
        if not match:
            continue
        event = match.group(1)
        enabled = True
        if isinstance(value, dict) and "enabled" in value:
            enabled = bool(value["enabled"])
        registered[event] = registered.get(event, False) or enabled
    # Fix round 1 (I1): ZERO identity-anchored matches means this file says
    # NOTHING about godmode specifically - whether because it is a decoy
    # (the reviewer's repro: only unrelated-plugin entries present) or a
    # genuinely unrelated config - and the caller's job (`install_verify`)
    # is to read that as "unverifiable", the same as a file that had no
    # `[hooks.state]` table at all, never as `"partial"` (which would imply
    # positive evidence about godmode's OWN state that this file does not
    # actually contain).
    return registered or None


def _read_grok_state(state_path: Path | None) -> dict[str, Any] | None:
    """Best-effort read of `grok inspect`'s own report.

    `state_path`, when given, is a captured JSON copy of `grok inspect
    --json`'s output (test fixture, or an operator's own capture) - read
    directly, never shelled out to. Without one, this tries the real `grok`
    executable on PATH with a short timeout; any failure (not found,
    non-zero exit, unparseable output, or a timeout) returns `None`.

    Addendum 6's own quoted `grok inspect` output ("enabled true... hooks
    true, 6 skills counted") is a single AGGREGATE `hooks` boolean, not a
    per-event breakdown - no addendum documents a per-event report shape.
    So when the parsed report carries a `hook_events` mapping (a shape this
    function is willing to trust if a future `grok inspect` version emits
    one), that per-event detail is used; otherwise the aggregate `hooks`
    boolean is applied uniformly to every declared event, and the caller is
    told (`"granularity": "aggregate-only"`) rather than reading a uniform
    answer as if it were per-event evidence.
    """
    import subprocess

    if state_path is not None:
        if not state_path.is_file():
            return None
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    else:
        import shutil
        grok_bin = shutil.which("grok")
        if grok_bin is None:
            return None
        try:
            completed = subprocess.run(
                [grok_bin, "inspect", "--json"], capture_output=True, text=True,
                encoding="utf-8", timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        try:
            data = json.loads(completed.stdout) if completed.stdout.strip() else None
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def install_verify(
    project: Path | None, host: str, *, state_path: Path | None = None,
) -> dict[str, Any]:
    """`godmode hooks install --host <name>`'s verification step.

    `project` follows `registration_report`'s own convention: `None`
    defaults to the resolved package root (`_PACKAGE_ROOT`) - godmode's own
    shipped manifests, not the project being governed.

    Checks each of this host's DECLARED hook events (from its generated
    manifest, or the allowlist when no manifest is on disk yet) against the
    host's own runtime state, where that state is inspectable at all
    (Codex's config, via `_read_codex_state`; Grok's own `inspect` report,
    via `_read_grok_state`). Cursor and Gemini have no documented state-
    inspection point anywhere in the spec addenda - always `"unverifiable"`.

    Verdict:
    - `"unverifiable"` (exit 0): this process could not read the host's own
      state at all. The honest "don't know" - never a failure.
    - `"partial"` (exit 1): the host's state WAS readable, and at least one
      declared event is not confirmed registered - the loud, listed failure
      CX-3 requires ("FAILS NONZERO listing missing hooks when only
      session-start registers").
    - `"verified"` (exit 0): the host's state was readable and every
      declared event is confirmed registered.
    """
    project = project or _PACKAGE_ROOT
    source = _load(project)
    specs = _hook_manifest_specs(source)
    if host == "claude":
        declared = {"SessionStart", "UserPromptSubmit", "PreToolUse"}
    elif host in specs:
        spec = specs[host]
        target = project / spec["path"]
        artifact = host_manifests.HOOK_ARTIFACTS.get(host, {})
        emitted_fn = artifact.get("emitted")
        if target.is_file() and emitted_fn is not None:
            try:
                declared = set(emitted_fn(json.loads(target.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                declared = set(artifact.get("allowed_events", ()))
        else:
            declared = set(artifact.get("allowed_events", ()))
    else:
        raise GodmodeError(f"Unknown host {host!r} for hooks install-verify")

    result: dict[str, Any] = {"host": host, "declared_events": sorted(declared)}

    if host == "codex":
        plugin_name = str(source["identity"]["name"])
        candidates = [state_path] if state_path else [
            Path.home() / ".codex" / "config.toml",
        ]
        state = None
        for candidate in candidates:
            if candidate is not None:
                state = _read_codex_state(candidate, plugin_name)
            if state is not None:
                break
        if state is None:
            result["verdict"] = "unverifiable"
            result["reason"] = "no readable Codex config state found"
            return result
        registered = {name for name in declared if state.get(name)}
        missing = sorted(declared - registered)
        result["registered_events"] = sorted(registered)
        result["missing_events"] = missing
        result["verdict"] = "verified" if not missing else "partial"
        return result

    if host == "grok":
        state = _read_grok_state(state_path)
        if state is None:
            result["verdict"] = "unverifiable"
            result["reason"] = "no readable `grok inspect` report found (grok not on PATH, and no --state-path given)"
            return result
        per_event = state.get("hook_events")
        if isinstance(per_event, dict):
            registered = {name for name in declared if per_event.get(name)}
            result["granularity"] = "per-event"
        else:
            aggregate = bool(state.get("hooks"))
            registered = set(declared) if aggregate else set()
            result["granularity"] = "aggregate-only"
        missing = sorted(declared - registered)
        result["registered_events"] = sorted(registered)
        result["missing_events"] = missing
        result["verdict"] = "verified" if not missing else "partial"
        return result

    result["verdict"] = "unverifiable"
    result["reason"] = f"no documented host-state inspection point for {host!r}"
    return result


def sbom(project: Path) -> dict[str, Any]:
    """List what ships and what it depends on.

    Short by design: the runtime imports only the standard library, so the
    dependency section is empty and that emptiness is the claim worth publishing.
    An empty list is only meaningful next to the check that produced it, so the
    third-party imports found during the scan are reported as the evidence.
    """
    import ast

    source = _load(project)
    stdlib = set(getattr(__import__("sys"), "stdlib_module_names", ()))
    # The project's own packages are imported absolutely from the entry points.
    # Counting them as dependencies would make "no runtime dependencies"
    # unfalsifiable: the number could never reach zero however clean the code was.
    first_party = {
        child.name
        for parent in ("scripts", "hooks")
        for child in (project / parent).glob("*")
        if child.is_dir() and (child / "__init__.py").is_file()
    }
    first_party |= {
        path.stem
        for parent in ("scripts", "hooks")
        for path in (project / parent).glob("*.py")
    }
    modules: list[str] = []
    third_party: set[str] = set()

    for path in sorted((project / "scripts").rglob("*.py")) + sorted((project / "hooks").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        modules.append(path.relative_to(project).as_posix())
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import, part of this package
                    continue
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                if root and root not in stdlib and root not in first_party:
                    third_party.add(root)

    return {
        "product": source["identity"]["name"],
        "version": source["identity"]["version"],
        "license": source["identity"]["license"],
        "modules": len(modules),
        "runtime_dependencies": sorted(third_party),
        "dependency_count": len(third_party),
        "evidence": "every non-relative import in scripts/ and hooks/, compared against the standard library and this project's own packages",
        "first_party": sorted(first_party),
        "verdict": "no-runtime-dependencies" if not third_party else "has-dependencies",
    }


def sbom_spdx(project: Path) -> dict[str, Any]:
    """The same claim in SPDX 2.3 form, so external tooling can validate it."""
    base = sbom(project)
    name = base["product"]
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{name}-{base['version']}",
        # A URN, not a URL: the privacy guard proves no runtime file names a
        # network endpoint, and SPDX accepts any URI here.
        "documentNamespace": f"urn:godmode:spdx:{name}-{base['version']}",
        "creationInfo": {"creators": [f"Tool: {name}-sbom"], "created": "1970-01-01T00:00:00Z"},
        "packages": [{
            "SPDXID": "SPDXRef-Package",
            "name": name,
            "versionInfo": base["version"],
            "licenseConcluded": base["license"],
            "licenseDeclared": base["license"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
        }],
        "relationships": [{
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package",
        }],
    }


def sbom_cyclonedx(project: Path) -> dict[str, Any]:
    """The same claim in CycloneDX 1.5 form."""
    base = sbom(project)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": [{
            "type": "application",
            "name": base["product"],
            "version": base["version"],
            "licenses": [{"license": {"id": base["license"]}}],
        }],
        "dependencies": [{"ref": base["product"], "dependsOn": []}],
    }


DEPENDENCY_POLICY_FILENAME = ".godmode-dependency-policy.json"


def dependency_gate(project: Path) -> dict[str, Any]:
    """The declarative policy gate: a dependency or banned licence fails the build.

    Policy defaults to the product's own promise - zero runtime dependencies -
    and a project may declare `.godmode-dependency-policy.json` with
    {"max_dependencies": N, "banned_licenses": [...]}.
    """
    policy = {"max_dependencies": 0, "banned_licenses": []}
    declared = project / DEPENDENCY_POLICY_FILENAME
    if declared.is_file():
        try:
            policy.update(json.loads(declared.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    base = sbom(project)
    violations: list[str] = []
    if base["dependency_count"] > int(policy["max_dependencies"]):
        violations.append(
            f"{base['dependency_count']} runtime dependencies exceed the budget of "
            f"{policy['max_dependencies']}: {', '.join(base['runtime_dependencies'])}"
        )
    if base["license"] in policy["banned_licenses"]:
        violations.append(f"licence {base['license']} is banned by policy")
    return {
        "policy": policy,
        "observed": {"dependencies": base["dependency_count"], "license": base["license"]},
        "violations": violations,
        "verdict": "within-policy" if not violations else "policy-violation",
    }


def release_checksums(project: Path) -> dict[str, Any]:
    """SHA-256 over every tracked file, in `sha256sum -c` format.

    Deterministic from content alone, so two independent clones produce
    identical output (S1-10's reproducibility claim is checkable).
    """
    import hashlib

    from .godmode_anchor import run_git

    listed = run_git(project, "ls-files")
    if listed is None:
        raise GodmodeError("Checksums need a Git repository to enumerate tracked files")
    lines = []
    for name in sorted(listed.splitlines()):
        path = project / name
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    body = "\n".join(lines) + "\n"
    return {
        "files": len(lines),
        "manifest": body,
        "manifest_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "packaging").mkdir()
        (project / "packaging" / "hosts.json").write_text(json.dumps({
            "identity": {
                "name": "demo", "version": "1.0.0", "description": "d",
                # Not a URL literal: a privacy guard asserts no runtime file contains
                # one, and that absence is what lets the project claim it holds no
                # network endpoint. The field only needs to be a passthrough value.
                "author": {"name": "Owner", "url": "owner-profile"},
                "homepage": "h", "repository": "r", "license": "Apache-2.0",
                "skills": "./skills/", "keywords": ["one"],
            },
            "hosts": {
                "alpha": {"path": ".alpha/plugin.json",
                          "fields": ["name", "version", "license", "author", "keywords"],
                          "extra": {"keywords_prefix": ["alpha-plugin"]}},
                "beta": {"path": ".beta/plugin.json",
                         "fields": ["name", "version", "license", "author"],
                         "extra": {"author_url": False}},
            },
        }), encoding="utf-8")

        first = check(project)
        assert first["verdict"] == "drifted" and first["drifted"] == 2, first

        result = write(project)
        assert len(result["written"]) == 2, result
        assert check(project)["verdict"] == "current"

        alpha = json.loads((project / ".alpha" / "plugin.json").read_text(encoding="utf-8"))
        beta = json.loads((project / ".beta" / "plugin.json").read_text(encoding="utf-8"))
        # Shared identity agrees; host-specific shape differs where declared.
        assert alpha["version"] == beta["version"] == "1.0.0"
        assert alpha["keywords"] == ["alpha-plugin", "one"], alpha
        assert "url" in alpha["author"] and "url" not in beta["author"], (alpha, beta)

        # A change at the source is drift everywhere until regenerated.
        payload = json.loads((project / "packaging" / "hosts.json").read_text(encoding="utf-8"))
        payload["identity"]["version"] = "1.1.0"
        (project / "packaging" / "hosts.json").write_text(json.dumps(payload), encoding="utf-8")
        drifted = check(project)
        assert drifted["drifted"] == 2, drifted
        assert "version" in drifted["hosts"][0]["differing_fields"], drifted

    print("godmode_bindings self-check OK")


if __name__ == "__main__":
    _self_check()

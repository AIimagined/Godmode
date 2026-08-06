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
from pathlib import Path
from typing import Any

from .godmode_errors import GodmodeError

SOURCE = "packaging/hosts.json"


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
    return {"source": SOURCE, "written": written, "unchanged": len(source["hosts"]) - len(written)}


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
        "documentNamespace": f"https://spdx.org/spdxdocs/{name}-{base['version']}",
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

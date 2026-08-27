"""PostToolUse: quality findings for the one file just written. Opt-in.

Absorbed 2026-08-27 from an upstream post-edit diagnostics hook, in this
runtime's shape. Advisory only - PostToolUse cannot block, and quality is
a proposal here as everywhere - and off unless the project's authorization
policy says `"post_edit_quality": true`. Off, this script reads one small
JSON file and exits with nothing on stdout: a project that did not ask
pays one interpreter start and no more. On, it runs the docs lint over a
Markdown file or the swallow scan over a Python file - the same detectors
`godmode quality` folds - and returns the findings as a `systemMessage`,
capped, with the file named. No archive write, no network, no subprocess.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

POLICY_FILENAME = ".godmode-authorization-policy.json"
CAP = 5


def _enabled(project: Path) -> bool:
    try:
        raw = json.loads((project / POLICY_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(raw, dict) and raw.get("post_edit_quality") is True


def _findings(project: Path, target: Path) -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        relative = target.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        relative = target.name
    out: list[str] = []
    suffix = target.suffix.lower()
    if suffix == ".md":
        from godmode_runtime.godmode_docslint import lint_text
        for f in lint_text(relative, text):
            out.append(f"{relative}:{f.get('line', 0)}: {f.get('severity', '')}: "
                       f"{f.get('check', '')} - {f.get('why', '')}")
    elif suffix == ".py":
        from godmode_runtime.godmode_swallow import _python_findings
        findings, _candidates, error = _python_findings(relative, text)
        if error:
            out.append(f"{relative}: {error}")
        for f in findings:
            out.append(f"{relative}:{f.get('line', 0)}: {f.get('severity', '')}: "
                       f"{f.get('check', '')} - {f.get('why', '')}")
    return out


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    project = Path(str(payload.get("cwd") or "."))
    if not _enabled(project):
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path:
        return 0
    lines = _findings(project, Path(str(file_path)))
    if not lines:
        return 0
    shown = lines[:CAP]
    if len(lines) > CAP:
        shown.append(f"... {len(lines) - CAP} more; `godmode quality --format editor` lists all")
    print(json.dumps({"systemMessage": "godmode quality (post-edit, advisory):\n" + "\n".join(shown)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

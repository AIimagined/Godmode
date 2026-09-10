"""`inline_interpreter: "scan"` - the opt-in that reads a Python payload.

Thirteenth field report (utilization census): 321 of one archive's refusal
records were interpreter-opaque-inline asks on heredoc and `python -c`
blocks the agent itself wrote, read by the operator as noise. Reports
fourteen to sixteen each paid two reruns per task to the same ask. Under the
scan posture a Python payload at the head of the segment is parsed with the
standard library's `ast`; it is cleared only when every import comes from a
table of read-only modules and nothing in it can execute, import
dynamically, reach a dunder, or open a file for writing. Anything the
parser cannot read, any other interpreter, and any wrapped head keep the
opaque floor. The default posture is unchanged: this file never flips a
verdict without the policy key.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    POLICY_FILENAME,
    AuthorizationError,
    classify_action,
    local_authorization_policy,
)

READ_ONLY = (
    'python -c "print(1)"',
    'python -c"print(2)"',
    'python -c "import json,sys; print(json.dumps(json.load(sys.stdin)))"',
    'python3 -c "import os; print(os.environ.get(\'HOME\'), os.path.exists(\'x\'))"',
    'python -c "import re,hashlib; print(hashlib.sha256(b\'x\').hexdigest())"',
    'python -c "with open(\'notes.md\') as f: print(len(f.read()))"',
    'python -W ignore -c "from os import path; print(path.sep)"',
    "python - <<'PY'\nimport json\nfrom pathlib import Path\n"
    "d = json.loads(Path('package.json').read_text(encoding='utf-8'))\nprint(d['version'])\nPY",
    "python - <<'EOF'\nimport sys\nfor line in sys.stdin:\n    print(line.rstrip())\nEOF",
)

MUTATING = (
    'python -c "import os; os.remove(\'x\')"',
    'python -c "open(\'x\',\'w\').write(\'y\')"',
    'python -c "open(\'x\', mode=m)"',
    'python -c "from pathlib import Path; Path(\'x\').write_text(\'y\')"',
    'python -c "import subprocess; subprocess.run([\'ls\'])"',
    'python -c "import shutil"',
    'python -c "import socket"',
    'python -c "import requests"',
    'python -c "__import__(\'os\').system(\'ls\')"',
    'python -c "exec(\'print(1)\')"',
    'python -c "import os as o; o.system(\'ls\')"',
    'python -c "from os import remove"',
    'python -c "import sys; sys.modules[\'os\'].system(\'ls\')"',
    'python -c "().__class__.__bases__"',
    'python -c "import sys; sys.path.insert(0, \'scripts\'); import mytool"',
    'python -c "print(1"',
    "python - <<'PY'\nimport json\nopen('out.json', 'w')\nPY",
)

NODE_READ_ONLY = (
    'node -e "console.log(1)"',
    'node -e "const fs = require(\'fs\'); console.log(fs.readFileSync(\'package.json\', \'utf8\').length)"',
    'node -p "require(\'./package.json\').version"',
    'node -e "process.stdout.write(JSON.stringify(require(\'node:os\').cpus().length))"',
)

NODE_MUTATING = (
    'node -e "require(\'fs\').writeFileSync(\'x\', \'1\')"',
    'node -e "require(\'child_process\').execSync(\'ls\')"',
    'node -e "eval(process.argv[1])"',
    'node -e "import(\'fs\').then(m => m.rmSync(\'x\'))"',
    'node -e "fetch(\'http://example.invalid\')"',
    'node -e "require(process.argv[1])"',
    'node -e "new Function(\'return 1\')()"',
)

STILL_OPAQUE = (
    'pwsh -Command "Get-ChildItem"',
    'sudo python -c "print(1)"',
    'bash -c "python -c \'print(1)\'"',
    'echo "print(1)" | python',
    'python - < script.py',
)


def _decision(operation: str, **kwargs) -> str:
    verdict = classify_action(operation, project_root=PLUGIN_ROOT, **kwargs)
    if not verdict["protected"]:
        return "allow"
    return "refuse" if verdict["tier"] == "R5" else "ask"


class ScanPostureClassifierTests(unittest.TestCase):
    def test_default_posture_is_unchanged(self) -> None:
        for command in READ_ONLY + MUTATING + STILL_OPAQUE + NODE_READ_ONLY + NODE_MUTATING:
            with self.subTest(command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertTrue(verdict["protected"])
                self.assertEqual(verdict["category"], "interpreter-opaque-inline")

    def test_read_only_python_payloads_are_cleared_under_scan(self) -> None:
        for command in READ_ONLY:
            with self.subTest(command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, inline_scan=True)
                self.assertFalse(verdict["protected"], verdict)
                self.assertEqual(verdict["category"], "interpreter-inline-read-only")
                self.assertEqual(verdict["tier"], "R1")

    def test_node_read_only_payloads_are_cleared_under_scan(self) -> None:
        for command in NODE_READ_ONLY:
            with self.subTest(command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, inline_scan=True)
                self.assertFalse(verdict["protected"], verdict)
                self.assertEqual(verdict["category"], "interpreter-inline-read-only")

    def test_node_mutating_payloads_keep_the_floor_under_scan(self) -> None:
        for command in NODE_MUTATING:
            with self.subTest(command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, inline_scan=True)
                self.assertTrue(verdict["protected"], verdict)

    def test_mutating_or_unreadable_payloads_keep_the_floor_under_scan(self) -> None:
        for command in MUTATING + STILL_OPAQUE:
            with self.subTest(command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, inline_scan=True)
                self.assertTrue(verdict["protected"], verdict)
                self.assertEqual(verdict["category"], "interpreter-opaque-inline")

    def test_visible_r5_evidence_still_refuses_under_scan(self) -> None:
        self.assertEqual(
            _decision('python -c "print(\'git push --force origin main\')"', inline_scan=True),
            "refuse")

    def test_compound_lines_take_the_worst_part(self) -> None:
        self.assertEqual(_decision('python -c "print(1)" && git status', inline_scan=True), "allow")
        self.assertEqual(_decision('python -c "print(1)" && rm -rf /', inline_scan=True), "refuse")
        self.assertEqual(
            _decision("python - <<'PY'\nprint(1)\nPY\ngit push --force origin main",
                      inline_scan=True),
            "refuse")

    def test_the_cleared_verdict_names_what_was_checked(self) -> None:
        verdict = classify_action('python -c "print(1)"', project_root=PLUGIN_ROOT,
                                  inline_scan=True)
        joined = " ".join(verdict["impact"])
        self.assertIn("ast", joined)
        self.assertIn("inline_interpreter", joined)


@contextmanager
def _project(policy: dict | None):
    with tempfile.TemporaryDirectory(prefix="godmode-inlinescan-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("session", "open", {"status": "open"})
            if policy is not None:
                (root / POLICY_FILENAME).write_text(json.dumps(policy), encoding="utf-8")
            yield root, archive


def _decide(project: Path, command: str) -> str:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow"
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return str(specific.get("permissionDecision", "allow"))


class ScanPosturePolicyTests(unittest.TestCase):
    def test_the_key_accepts_scan_and_ask_only(self) -> None:
        with _project({"inline_interpreter": "scan"}) as (_root, archive):
            self.assertEqual(local_authorization_policy(archive)["inline_interpreter"], "scan")
        with _project({"inline_interpreter": "ask"}) as (_root, archive):
            self.assertEqual(local_authorization_policy(archive)["inline_interpreter"], "ask")
        with _project({"inline_interpreter": "Scan"}) as (_root, archive):
            with self.assertRaises(AuthorizationError):
                local_authorization_policy(archive)
        with _project({"inline_interpreter": True}) as (_root, archive):
            with self.assertRaises(AuthorizationError):
                local_authorization_policy(archive)

    def test_hook_clears_a_read_only_payload_under_scan_and_records_it(self) -> None:
        with _project({"inline_interpreter": "scan"}) as (root, archive):
            self.assertEqual(_decide(root, 'python -c "print(1)"'), "allow")
            self.assertEqual(_decide(root, 'python -c "import shutil"'), "ask")
            cleared = [r for r in archive.read_events(verify=False)
                       if r.get("kind") == "action"
                       and (r.get("data") or {}).get("cleared_by") == "inline_interpreter"]
        self.assertEqual(len(cleared), 1, "the clearance must leave a record")
        self.assertEqual(cleared[0]["data"]["category"], "interpreter-inline-read-only")

    def test_scan_is_the_default_and_ask_still_opts_out(self) -> None:
        # 0.3.24: the ast allowlist is sound, and the ask on every read-only
        # payload was the field's most repeated complaint, so scan is the
        # default posture; an explicit "ask" keeps the old floor.
        with _project(None) as (root, _archive):
            self.assertEqual(_decide(root, 'python -c "print(1)"'), "allow")
        with _project({"inline_interpreter": "ask"}) as (root, _archive):
            self.assertEqual(_decide(root, 'python -c "print(1)"'), "ask")


if __name__ == "__main__":
    unittest.main()

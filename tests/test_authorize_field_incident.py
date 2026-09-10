"""Field incident, 2026-09-11 (a governed project's memory write).

Four defects in one evening: (1) the gate refused a write into the host's
own project-memory directory as "outside the working tree", though that
directory is the host's, not the repository's; (2) the no-terminal error
told the operator to "run from an interactive shell" while the chat's own
command prefix has none and the shim was not on PATH; (3) the agent's
workaround, `echo <password> | ... --password-stdin`, put the password in
two transcripts; (4) the refusal record keeps the operation cut at 500
characters, so `authorize stage --from-last-refusal` staged a digest of
the cut text and the retry of the real command was refused again.
"""
from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = PLUGIN_ROOT / "tests"
for entry in (SCRIPTS, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker, _require_tty, classify_action, stage_from_refusal)
from test_godmode_runtime import isolated_project  # noqa: E402
from test_observe_mode import _decide  # noqa: E402

PASSWORD = "correct horse battery"


class HostMemoryDirectoryTests(unittest.TestCase):
    def test_a_write_into_the_hosts_project_memory_directory_is_an_ordinary_write(self) -> None:
        with tempfile.TemporaryDirectory() as raw_home, tempfile.TemporaryDirectory() as raw_project:
            home, project = Path(raw_home), Path(raw_project)
            memory = home / ".claude" / "projects" / "C--Users-x-repo" / "memory"
            memory.mkdir(parents=True)
            with mock.patch.object(Path, "home", return_value=home):
                redirect = classify_action(
                    f'cat > "{(memory / "rule.md").as_posix()}" <<\'EOF\'\nbody\nEOF',
                    project_root=project)
                elsewhere = classify_action(
                    f'cat > "{(home / "notes.md").as_posix()}" <<\'EOF\'\nbody\nEOF',
                    project_root=project)
        self.assertFalse(redirect["protected"], redirect)
        self.assertTrue(elsewhere["protected"], elsewhere)


class NoTerminalMessageTests(unittest.TestCase):
    def test_the_no_terminal_message_names_where_a_terminal_is(self) -> None:
        with mock.patch.object(sys, "stdin", io.StringIO("")):
            with self.assertRaises(AuthorizationError) as caught:
                _require_tty()
        text = str(caught.exception)
        self.assertIn("separate terminal window", text)
        self.assertIn("bin/godmode", text)


class PasswordInTranscriptTests(unittest.TestCase):
    def test_a_literal_password_piped_into_password_stdin_is_refused_outright(self) -> None:
        for command in (
            "echo 555555666666 | python C:/x/scripts/godmode.py authorize stage --from-last-refusal --password-stdin --ttl 600",
            '"hunter2" | godmode authorize setup --password-stdin',
            "printf '%s' pw | bin/godmode authorize issue --operation 'git push' --password-stdin",
        ):
            verdict = classify_action(command)
            self.assertEqual(verdict["category"], "password-in-transcript", command)
            self.assertEqual(verdict["tier"], "R5", command)
            self.assertTrue(verdict["protected"], command)

    def test_a_password_read_from_a_file_or_a_prompt_is_not_that_shape(self) -> None:
        for command in (
            "python scripts/godmode.py authorize stage --from-last-refusal --password-stdin < .secret",
            "python scripts/godmode.py authorize stage --from-last-refusal",
            "echo staged | tee log.txt",
        ):
            self.assertNotEqual(classify_action(command)["category"], "password-in-transcript", command)


class LongRefusalStagingTests(unittest.TestCase):
    def test_a_refusal_longer_than_the_record_cap_still_stages_the_real_operation(self) -> None:
        operation = "git push --force origin main # " + "x" * 600
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            self.assertEqual(_decide(project, "Bash", {"command": operation})["decision"], "deny")
            record = archive.select(kind="refusal", limit=5)[-1]["data"]
            self.assertTrue(record.get("operation_truncated"))
            self.assertEqual(record.get("operation_digest"),
                             hashlib.sha256(operation.strip().encode()).hexdigest())
            staged_text, digest = stage_from_refusal(archive, with_digest=True)
            self.assertLess(len(staged_text), len(operation))
            broker.stage(staged_text, PASSWORD, 60, operation_digest=digest)
            self.assertIsNotNone(broker.consume_staged(operation))


if __name__ == "__main__":
    unittest.main()

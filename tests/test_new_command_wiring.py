"""Every subcommand added in sprints 6-8 dispatches without an AttributeError.

This exists because one did not. `rollback mark` reached the handler and
died on `runtime.project`, an attribute `Runtime` has never had - the
project path comes from `anchor.project_root`. The other four handlers had
the same mistake and were fixed by a bulk replacement that missed this one,
because its call spans two lines.

It shipped for exactly one reason: the smoke test walked `rollback plan`
and not `rollback mark`. Four of five paths were exercised and the fifth
was assumed.

So this walks every one of them. It asserts almost nothing about content -
the behaviour is covered by each module's own tests - only that dispatch
reaches the handler and returns rather than raising. That is the whole
failure class, and it is the class a hand-written smoke test keeps missing
by one.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

# (argv, extra namespace attributes the subparser would have supplied)
SPRINT_COMMANDS = [
    (["fleet", "show"], {}),
    (["fleet", "lease", "--resource", "src/api.py"],
     {"resource": "src/api.py", "ttl": 600.0, "holder": "lane-a"}),
    (["fleet", "release", "--resource", "src/api.py"],
     {"resource": "src/api.py", "holder": "lane-a"}),
    (["fleet", "delegate", "--child", "lane-b"],
     {"child": "lane-b", "task": "review", "parent": "lane-a"}),
    (["reanchor"], {}),
    (["rollback", "mark", "--command", "pytest", "--exit-code", "0"],
     {"command": "pytest", "exit_code": 0}),
    (["rollback", "plan"], {}),
    (["forecast", "--operation", "git status"], {"operation": "git status"}),
    (["replay"], {}),
    (["governance", "show"], {}),
    (["governance", "promote", "--candidate", "none", "--reason", "test"],
     {"candidate": "none", "reason": "test"}),
]


class EverySprintCommandDispatches(unittest.TestCase):
    def test_each_handler_runs_without_an_attribute_error(self) -> None:
        parser = console._build_parser()
        for argv, extra in SPRINT_COMMANDS:
            with self.subTest(command=" ".join(argv)):
                args = parser.parse_args(argv)
                for key, value in extra.items():
                    setattr(args, key, value)
                self.assertTrue(
                    hasattr(args, "handler"),
                    f"`{' '.join(argv)}` parsed to no handler")
                with isolated_project() as (_p, _s, _a, archive):
                    archive.initialize()
                    runtime = console.Runtime(
                        anchor=archive.anchor, archive=archive)
                    # A refusal is a fine outcome (promoting an unknown
                    # candidate, releasing an unheld lease). A raised
                    # AttributeError is not: it means the handler never ran.
                    result = args.handler(args, runtime)
                    self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()

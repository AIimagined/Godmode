#!/usr/bin/env python3
"""Dedicated Godmode Skill Forge entry point."""

# Developed by AIimagined.

import sys

from godmode_runtime.godmode_console import main


def _forge_arguments(arguments: list[str]) -> list[str]:
    global_arguments: list[str] = []
    forge_arguments: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--project":
            if index + 1 >= len(arguments):
                return [*global_arguments, "--project", "skill", "forge", *forge_arguments]
            global_arguments.extend((argument, arguments[index + 1]))
            index += 2
            continue
        if argument.startswith("--project=") or argument in {"--json", "--version"}:
            global_arguments.append(argument)
        else:
            forge_arguments.append(argument)
        index += 1
    return [*global_arguments, "skill", "forge", *forge_arguments]


if __name__ == "__main__":
    raise SystemExit(main(_forge_arguments(sys.argv[1:])))

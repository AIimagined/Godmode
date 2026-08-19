# Codex adapter — the gate arrives as project config, not as a plugin hook

## Why this exists

On the machine this was developed and measured on, **Codex and Grok load zero
hooks from any plugin.** That is not a godmode-specific failure. Grok's own
debug log is unambiguous: it discovers eight installed plugins carrying hook
files — godmode among them, the rest unrelated third-party plugins — and
then reports

```
hooks: discovery complete total_hooks=0 session_start=0 pre_tool=0 ...
hook discovery complete hook_count=0 error_count=0
```

Zero loaded, zero errors, for every plugin. Codex's `/hooks` panel reports the
same shape from the other side: `Installed: 0` for every event, and its plugin
detail says `Hooks  No plugin hooks.` while listing all six godmode skills.

So the plugin package installs and its skills work on both hosts; the pre-tool
boundary does not arrive through it.

## What does work

Project-level hook config. This is not a guess — a non-godmode hook on this
machine is registered, trusted and `enabled = true` in `~/.codex/config.toml`,
declared in a project's own `.codex/hooks.json` with exactly this shape:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [ { "type": "command", "command": "<one string>" } ] }
    ]
  }
}
```

Two details are load-bearing and both differ from the plugin manifest:

- **The command is a SINGLE STRING.** godmode's shared `hooks/hooks.json`
  splits `command` + `args`, which Claude accepts. Codex's own documented
  example and the working hook on this machine are both one string.
- **The event key is CamelCase** (`PreToolUse`), even though Codex records the
  trust row under a snake_case key (`pre_tool_use`). That normalisation is
  Codex's, not something the file should do — the working hook writes
  `PreToolUse` in the file and shows `pre_tool_use` in the trust table.

## Install

1. Copy `hooks.json` from this directory to `<your project>/.codex/hooks.json`.
2. Replace `<ABSOLUTE-PATH-TO-GODMODE>` with the absolute path of your godmode
   checkout. Absolute, because a project hook has no `${PLUGIN_ROOT}`.
3. Open Codex interactively in that project and run `/hooks`. Codex requires
   you to review and trust a non-managed command hook before it runs; approve
   godmode's entries there.
4. Verify honestly — not with `godmode hooks probe`, which self-injects and
   proves only that the hook script works. Run a **protected** command in a
   Codex session and check that a record lands:

   ```
   godmode observe --report        # or read the archive directly
   ```

   A protected command that reaches the gate writes a `refusal` record. If
   nothing lands, the hook did not run, whatever any probe says.

## Status, stated plainly

The shape and location above are proven on this machine for another tool. They
are **not** yet proven for godmode: the trust approval in step 3 has not been
completed here, so no claim is made that godmode's gate currently runs under
Codex. `README.md`'s host table and the capability coverage map both say the
same thing.

## Grok

Grok has the same plugin-hook outcome (`total_hooks=0`) and the same underlying
options, but no project-level godmode hook has been verified on it, so no
template is shipped here rather than shipping one nobody has seen work.

// Godmode pre-tool gate for OpenCode (https://opencode.ai/docs/plugins/).
//
// Copy this file to `.opencode/plugins/godmode.js` (project) or
// `~/.config/opencode/plugins/godmode.js` (global) and set
// GODMODE_PLUGIN_ROOT to the Godmode checkout or install directory - the
// directory that contains `hooks/godmode_gate_fast.py`.
//
// OpenCode's documented way to stop a tool is to throw from
// `tool.execute.before`, so this shim fails CLOSED on everything a
// CONFIGURED gate says or fails to say: a deny, an `ask` (folded to deny
// with the staged-capability remedy), an unreadable decision, a missing
// interpreter or gate file. Only a silent exit 0 lets the call through.
//
// An UNSET GODMODE_PLUGIN_ROOT is different (field report 2026-08-29: it
// bricked every tool call in a live session, `dir` included, with no
// recoverable path from inside): unconfigured is not hostile, and the
// project doctrine says a broken gate must not brick a session. With no
// root set the shim warns once per session on stderr and allows -
// installing the file alone gates nothing until the root is configured,
// and the warning says exactly that. There is deliberately no bypass
// variable: once the root is set, fail-closed has no override.
//
// Runs under Bun or Node (field report: the host ran Node while the shim
// called Bun.spawn). Nothing here reads the archive; the Python gate owns
// every decision and every record.

const TOOL_MAP = {
  bash: (args) => ["Bash", { command: String(args.command ?? "") }],
  write: (args) => ["Write", { file_path: String(args.filePath ?? args.path ?? "") }],
  edit: (args) => ["Edit", { file_path: String(args.filePath ?? args.path ?? "") }],
  patch: (args) => ["Edit", { file_path: String(args.filePath ?? args.path ?? "") }],
};

function decisionFrom(stdout) {
  // The gate speaks every host's dialect; OpenCode has none of its own, so
  // Claude's key is read first and Grok's second.
  try {
    const body = JSON.parse(stdout);
    const specific = body.hookSpecificOutput || {};
    return {
      decision: specific.permissionDecision || body.decision || "deny",
      reason: specific.permissionDecisionReason || body.reason || stdout,
    };
  } catch {
    return { decision: "deny", reason: `godmode returned an unreadable decision: ${stdout.slice(0, 200)}` };
  }
}

async function runGate(command, payload, directory) {
  const env = { ...process.env, GODMODE_HOST: "opencode", GODMODE_SHIM_BOUNDARY: "opencode" };
  if (typeof globalThis.Bun !== "undefined") {
    const proc = Bun.spawn(command, {
      stdin: "pipe", stdout: "pipe", stderr: "pipe", cwd: directory, env,
    });
    proc.stdin.write(payload);
    proc.stdin.end();
    const stdout = (await new Response(proc.stdout).text()).trim();
    const stderr = (await new Response(proc.stderr).text()).trim();
    const code = await proc.exited;
    return { stdout, stderr, code };
  }
  const { spawnSync } = await import("node:child_process");
  const done = spawnSync(command[0], command.slice(1), {
    input: payload, cwd: directory, env, encoding: "utf-8",
  });
  if (done.error) {
    throw new Error(`godmode: the gate could not be spawned: ${String(done.error.message).slice(0, 200)}`);
  }
  return {
    stdout: String(done.stdout || "").trim(),
    stderr: String(done.stderr || "").trim(),
    code: done.status === null ? 1 : done.status,
  };
}

export const GodmodePlugin = async ({ directory }) => {
  const root = process.env.GODMODE_PLUGIN_ROOT;
  const python = process.env.GODMODE_PYTHON || "python";
  let warnedUnconfigured = false;
  return {
    "tool.execute.before": async (input, output) => {
      const mapper = TOOL_MAP[String(input.tool || "").toLowerCase()];
      if (!mapper) return;
      if (!root) {
        if (!warnedUnconfigured) {
          warnedUnconfigured = true;
          console.warn(
            "godmode: GODMODE_PLUGIN_ROOT is not set, so the gate is NOT " +
            "running - every call passes unexamined. Set it to the Godmode " +
            "checkout (the directory containing hooks/godmode_gate_fast.py) " +
            "and restart OpenCode, or remove .opencode/plugins/godmode.js.");
        }
        return;
      }
      const [toolName, toolInput] = mapper(output.args || {});
      const payload = JSON.stringify({
        session_id: String(input.sessionID || ""),
        cwd: directory,
        hook_event_name: "PreToolUse",
        tool_name: toolName,
        tool_input: toolInput,
      });
      const { stdout, stderr, code } = await runGate(
        [python, `${root}/hooks/godmode_gate_fast.py`], payload, directory);
      if (!stdout && code === 0) return; // silent allow
      if (!stdout) {
        throw new Error(`godmode: the gate exited ${code} without a decision${stderr ? `: ${stderr.slice(0, 200)}` : ""}`);
      }
      const { decision, reason } = decisionFrom(stdout);
      if (decision !== "allow") {
        throw new Error(`godmode: ${reason}`);
      }
    },
  };
};

export default GodmodePlugin;

// Godmode pre-tool gate for OpenCode (https://opencode.ai/docs/plugins/).
//
// Copy this file to `.opencode/plugins/godmode.js` (project) or
// `~/.config/opencode/plugins/godmode.js` (global) and set
// GODMODE_PLUGIN_ROOT to the Godmode checkout or install directory - the
// directory that contains `hooks/godmode_gate_fast.py`.
//
// OpenCode's documented way to stop a tool is to throw from
// `tool.execute.before`, so this shim fails CLOSED: a deny, an `ask` (which
// OpenCode cannot render, so it folds to deny with the staged-capability
// remedy), a missing interpreter, or a missing root all throw. Only a silent
// exit 0 from the gate lets the call through. Nothing here reads the
// archive; the Python gate owns every decision and every record.

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

export const GodmodePlugin = async ({ directory }) => {
  const root = process.env.GODMODE_PLUGIN_ROOT;
  const python = process.env.GODMODE_PYTHON || "python";
  return {
    "tool.execute.before": async (input, output) => {
      const mapper = TOOL_MAP[String(input.tool || "").toLowerCase()];
      if (!mapper) return;
      if (!root) {
        throw new Error("godmode: GODMODE_PLUGIN_ROOT is not set; the gate cannot run, so this call is refused");
      }
      const [toolName, toolInput] = mapper(output.args || {});
      const payload = JSON.stringify({
        session_id: String(input.sessionID || ""),
        cwd: directory,
        hook_event_name: "PreToolUse",
        tool_name: toolName,
        tool_input: toolInput,
      });
      const proc = Bun.spawn([python, `${root}/hooks/godmode_gate_fast.py`], {
        stdin: "pipe",
        stdout: "pipe",
        stderr: "pipe",
        cwd: directory,
        env: { ...process.env, GODMODE_HOST: "opencode" },
      });
      proc.stdin.write(payload);
      proc.stdin.end();
      const stdout = (await new Response(proc.stdout).text()).trim();
      const stderr = (await new Response(proc.stderr).text()).trim();
      const code = await proc.exited;
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

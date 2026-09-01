// Godmode pre-tool gate for the pi coding agent (earendil-works/pi).
//
// pi ships no built-in approval flow - its documentation says to build a
// confirmation flow with extensions, and extensions receive `tool_call`
// events BEFORE tool execution. This extension is that flow: every mapped
// tool call is sent to the Godmode gate, and anything but a silent allow
// blocks the call with the gate's own reason.
//
// Install: copy into the project's pi extensions directory (see pi's
// extension docs for the path your version loads) and set
// GODMODE_PLUGIN_ROOT to the Godmode checkout or install - the directory
// containing `hooks/godmode_gate_fast.py`.
//
// Doctrine, identical to the OpenCode shim: once a root is CONFIGURED the
// shim fails CLOSED on everything - a deny, an `ask` (folded to deny with
// the staged-capability remedy), an unreadable decision, a missing
// interpreter. An UNSET root warns once and allows, because unconfigured
// is not hostile and a broken gate must not brick a session; there is no
// bypass variable once the root is set.
//
// pi extensions execute arbitrary code with no sandbox, which is exactly
// why this file stays thin: nothing here reads the archive or decides
// anything - the Python gate owns every decision and every record.

import { spawnSync } from "node:child_process";

type ToolMapping = [string, Record<string, string>] | null;

const TOOL_MAP: Record<string, (args: Record<string, unknown>) => ToolMapping> = {
  bash: (args) => ["Bash", { command: String(args.command ?? "") }],
  powershell: (args) => ["PowerShell", { command: String(args.command ?? "") }],
  write: (args) => ["Write", { file_path: String(args.path ?? args.file_path ?? "") }],
  edit: (args) => ["Edit", { file_path: String(args.path ?? args.file_path ?? "") }],
};

function decisionFrom(stdout: string): { decision: string; reason: string } {
  try {
    const body = JSON.parse(stdout);
    const specific = body.hookSpecificOutput || {};
    return {
      decision: specific.permissionDecision || body.decision || "deny",
      reason: specific.permissionDecisionReason || body.reason || stdout,
    };
  } catch {
    return {
      decision: "deny",
      reason: `godmode returned an unreadable decision: ${stdout.slice(0, 200)}`,
    };
  }
}

export default function godmodeExtension(pi: {
  on: (event: string, handler: (event: Record<string, unknown>) => void) => void;
  cwd?: string;
}) {
  const root = process.env.GODMODE_PLUGIN_ROOT;
  const python = process.env.GODMODE_PYTHON || "python";
  let warnedUnconfigured = false;

  pi.on("tool_call", (event) => {
    const toolName = String((event as { toolName?: unknown }).toolName ?? "").toLowerCase();
    const mapper = TOOL_MAP[toolName];
    if (!mapper) return;
    if (!root) {
      if (!warnedUnconfigured) {
        warnedUnconfigured = true;
        console.warn(
          "godmode: GODMODE_PLUGIN_ROOT is not set, so the gate is NOT " +
          "running - every call passes unexamined. Set it to the Godmode " +
          "checkout (the directory containing hooks/godmode_gate_fast.py) " +
          "and restart pi, or remove this extension.");
      }
      return;
    }
    const mapped = mapper(((event as { input?: Record<string, unknown> }).input) ?? {});
    if (!mapped) return;
    const [mappedTool, toolInput] = mapped;
    const directory = pi.cwd || process.cwd();
    const payload = JSON.stringify({
      session_id: String((event as { sessionId?: unknown }).sessionId ?? ""),
      cwd: directory,
      hook_event_name: "PreToolUse",
      tool_name: mappedTool,
      tool_input: toolInput,
    });
    const done = spawnSync(python, [`${root}/hooks/godmode_gate_fast.py`], {
      input: payload, cwd: directory, encoding: "utf-8",
      env: { ...process.env, GODMODE_HOST: "pi", GODMODE_SHIM_BOUNDARY: "pi" },
    });
    if (done.error) {
      throw new Error(
        `godmode: the gate could not be spawned: ${String(done.error.message).slice(0, 200)}`);
    }
    const stdout = String(done.stdout || "").trim();
    const stderr = String(done.stderr || "").trim();
    const code = done.status === null ? 1 : done.status;
    if (!stdout && code === 0) return; // silent allow
    if (!stdout) {
      throw new Error(
        `godmode: the gate exited ${code} without a decision${stderr ? `: ${stderr.slice(0, 200)}` : ""}`);
    }
    const { decision, reason } = decisionFrom(stdout);
    if (decision !== "allow") {
      throw new Error(`godmode: ${reason}`);
    }
  });
}

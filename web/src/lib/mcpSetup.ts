// Using seriesmith from an LLM client (Settings › This computer; docs/COMMANDS.md,
// "An LLM driving seriesmith"): the command that starts this install's MCP server
// (GET /seriesmith/mcp), as a client's `mcp add` takes it and as the JSON its
// settings file holds. Nothing is installed: the client starts the server when it
// needs it.

/** GET /seriesmith/mcp: how a client starts this install's server. */
export interface McpLaunch {
  command: string;
  args: string[];
  /** the editor's server it talks to */
  url: string;
  /** "seriesmith": the .venv's launcher; "python": this Python running mcp.py */
  how: "seriesmith" | "python";
  /** the option that leaves out every tool that writes or queues */
  read_only: string;
}

/** A command-line word, quoted when it has to be (a space, a quote, a shell character). */
export function shellWord(w: string): string {
  return /^[\w@%+=:,./\\-]+$/.test(w) ? w : `"${w.replace(/"/g, '\\"')}"`;
}

/** The arguments, with the read-only option when asked. */
export function argsOf(l: Pick<McpLaunch, "args" | "read_only">, readOnly: boolean): string[] {
  return readOnly ? [...l.args, l.read_only] : [...l.args];
}

/** The command alone: what any client runs to start it. */
export function commandLine(command: string, args: string[]): string {
  return [command, ...args].map(shellWord).join(" ");
}

/** A client's `mcp add` (Claude Code's here; Codex and Copilot CLI take the same
 * after their own name). */
export function addCommand(command: string, args: string[], client = "claude"): string {
  return [client, "mcp", "add", "seriesmith", "--", command, ...args].map(shellWord).join(" ");
}

/** The `mcpServers` block most clients' settings take (Claude Desktop, Cursor,
 * Gemini CLI, Windsurf; VS Code's key is `servers`, with "type": "stdio"). */
export function jsonBlock(command: string, args: string[]): string {
  return JSON.stringify({ mcpServers: { seriesmith: { command, args } } }, null, 2);
}

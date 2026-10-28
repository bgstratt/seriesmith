// Settings › This computer › Use from an LLM (lib/mcpSetup.ts): the command that
// starts this install's MCP server, as a client's `mcp add` and as JSON.
import { describe, expect, it } from "vitest";
import { addCommand, argsOf, commandLine, jsonBlock, shellWord } from "../src/lib/mcpSetup";
import { createMockApi } from "../src/mock/mockApi";

const VENV = "C:\\seriesmith\\.venv\\Scripts\\seriesmith.exe";
const PY = "C:\\Program Files\\ComfyUI\\python_embeded\\python.exe";
const FILE = "C:\\Program Files\\ComfyUI\\custom_nodes\\seriesmith\\seriesmith\\mcp.py";

describe("the command line", () => {
  it("quotes only what needs it", () => {
    expect(shellWord(VENV)).toBe(VENV);
    expect(shellWord(PY)).toBe(`"${PY}"`);
    expect(shellWord("--url")).toBe("--url");
    expect(shellWord("http://127.0.0.1:8188")).toBe("http://127.0.0.1:8188");
  });
  it("a client's mcp add: the name, then -- and the command", () => {
    expect(addCommand(VENV, ["mcp"])).toBe(`claude mcp add seriesmith -- ${VENV} mcp`);
    expect(addCommand(PY, [FILE, "--url", "http://127.0.0.1:8188"], "codex"))
      .toBe(`codex mcp add seriesmith -- "${PY}" "${FILE}" --url http://127.0.0.1:8188`);
    expect(commandLine(VENV, ["mcp", "--read-only"])).toBe(`${VENV} mcp --read-only`);
  });
});

describe("the JSON", () => {
  it("is the mcpServers block, its paths escaped", () => {
    const j = JSON.parse(jsonBlock(PY, [FILE]));
    expect(j).toEqual({ mcpServers: { seriesmith: { command: PY, args: [FILE] } } });
    expect(jsonBlock(VENV, ["mcp"])).toContain('"C:\\\\seriesmith\\\\.venv');
  });
});

describe("read-only", () => {
  it("adds the server's option, leaving the launch as it was", () => {
    const l = { args: ["mcp"], read_only: "--read-only" };
    expect(argsOf(l, true)).toEqual(["mcp", "--read-only"]);
    expect(argsOf(l, false)).toEqual(["mcp"]);
    expect(l.args).toEqual(["mcp"]);
  });
});

describe("the mock's launch", () => {
  it("has --url only off the default port", async () => {
    const api = createMockApi(() => {});
    expect((await api.mcpLaunch("8190")).args).toEqual(["mcp"]);
    expect((await api.mcpLaunch("8188")).args).toEqual(["mcp", "--url", "http://127.0.0.1:8188"]);
  });
});

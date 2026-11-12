// `npm test`: vitest, started from the working directory spelled with an upper-case drive
// letter on Windows. From c:\... (VS Code's terminal) vitest's runner loads twice, as
// file:///c:/ and as file:///C:/ (where a test's own `import "vitest"` resolves), and the
// copy a test's `describe` calls has no runner state: "Cannot read properties of
// undefined (reading 'config')" in every file. Anything else runs it as it is.
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const cwd = process.platform === "win32" ? process.cwd().replace(/^[a-z]:/, (d) => d.toUpperCase()) : process.cwd();
const cli = join(cwd, "node_modules", "vitest", "vitest.mjs");
const r = spawnSync(process.execPath, [cli, ...process.argv.slice(2)], { cwd, stdio: "inherit" });
process.exit(r.status ?? 1);

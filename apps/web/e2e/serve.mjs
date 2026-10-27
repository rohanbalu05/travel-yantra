// Serves the standalone build for the end-to-end test: copies the static files
// next to server.js (Next does not put them in standalone), then starts it.
// Run `pnpm build` first, with NEXT_PUBLIC_API_BASE_URL unset for the mock path.
import { spawn } from "node:child_process";
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const standalone = join(web, ".next", "standalone");
if (!existsSync(join(standalone, "server.js"))) {
  console.error("No standalone build: run `pnpm build` first.");
  process.exit(1);
}
cpSync(join(web, ".next", "static"), join(standalone, ".next", "static"), { recursive: true });
mkdirSync(join(standalone, "public"), { recursive: true });
if (existsSync(join(web, "public"))) cpSync(join(web, "public"), join(standalone, "public"), { recursive: true });

const server = spawn(process.execPath, ["server.js"], {
  cwd: standalone,
  stdio: "inherit",
  env: { ...process.env, PORT: process.env.E2E_PORT ?? "3100", HOSTNAME: "127.0.0.1" },
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => server.kill(sig));
server.on("exit", (code) => process.exit(code ?? 0));

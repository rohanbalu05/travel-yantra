// The chat panel's own tests (TY5): pnpm exec vitest run -c components/chat/vitest.config.ts
// Same setup as the app's vitest.config.mts, for the tests that sit next to the panel.
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("../..", import.meta.url)) } },
  test: { root: fileURLToPath(new URL("../..", import.meta.url)), environment: "jsdom", include: ["components/chat/**/*.test.{ts,tsx}"] },
});

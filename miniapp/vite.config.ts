/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Pinned so tests assert against a fixed base URL instead of whatever the
    // developer happens to have in miniapp/.env.
    env: { VITE_API_URL: "http://api.test" },
  },
});

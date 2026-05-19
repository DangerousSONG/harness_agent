import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const uiRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: uiRoot,
  plugins: [react()],
  build: {
    outDir: "dist",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});

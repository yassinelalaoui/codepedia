/// <reference types="vitest/config" />
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Builds a single classic (non-`type="module"`) IIFE bundle vendored into
// doc_generator's assets, mirroring the Mermaid vendoring convention from
// feature 013 (research.md Decision 2/8). `emptyOutDir: false` is required:
// that directory already holds mermaid.min.js and must not be wiped.
export default defineConfig(({ command }) => ({
  // Tailwind runs at build time and emits static CSS into wiki-ui.css. Nothing
  // is fetched at runtime, which is what keeps constitution 2.2 (zero network
  // exposure) intact and lets a generated wiki render fully offline over
  // file:// - the same reason mermaid.min.js is vendored rather than CDN-loaded.
  plugins: [react(), tailwindcss()],
  // Vite's automatic `process.env.NODE_ENV` replacement only applies to app
  // builds, not `build.lib` output - without this, the reference react-dom
  // makes to it survives into the browser bundle unresolved and crashes on
  // load with "ReferenceError: process is not defined". Scoped to the actual
  // `vite build` command only - Vitest also reuses this config but runs
  // under `serve`, and forcing production mode there breaks
  // @testing-library/react's `act()`, which requires a development React build.
  define:
    command === "build"
      ? {
          "process.env.NODE_ENV": JSON.stringify("production"),
        }
      : {},
  build: {
    outDir: resolve(__dirname, "../src/doc_generator/assets"),
    emptyOutDir: false,
    cssCodeSplit: false,
    lib: {
      entry: resolve(__dirname, "src/main.tsx"),
      name: "WikiUi",
      formats: ["iife"],
      fileName: () => "wiki-ui.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) =>
          assetInfo.name === "style.css" ? "wiki-ui.css" : (assetInfo.name ?? "[name][extname]"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
}));

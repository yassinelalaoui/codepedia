/// <reference types="vitest/config" />
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds a single classic (non-`type="module"`) IIFE bundle vendored into
// doc_generator's assets, mirroring the Mermaid vendoring convention from
// feature 013 (research.md Decision 2/8). `emptyOutDir: false` is required:
// that directory already holds mermaid.min.js and must not be wiped.
export default defineConfig({
  plugins: [react()],
  // Vite's automatic `process.env.NODE_ENV` replacement only applies to app
  // builds, not `build.lib` output - without this, the reference react-dom
  // makes to it survives into the browser bundle unresolved and crashes on
  // load with "ReferenceError: process is not defined".
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
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
});

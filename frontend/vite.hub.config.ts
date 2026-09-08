import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The hub page's bundle. A second *invocation* rather than a second entry in
// vite.config.ts, because that config uses `build.lib` with `formats: ["iife"]`
// and a library build in IIFE format takes exactly one entry (research.md §10).
//
// Everything else is deliberately shared with the wiki build: the same plugins,
// and the same `src/styles.css` theme tokens. That sharing is what makes spec
// FR-043 ("looks like the same product") and FR-044a (the same three-state
// appearance control) reuse rather than reimplementation.
//
// The hub is NOT bound by the wiki's zero-fetch rule - it is served over
// loopback and talks to its own origin. The constraint is one-directional, so
// this build never writes into src/doc_generator/assets/ (spec FR-045).
export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  // Same reason as the wiki build: `build.lib` output does not get Vite's
  // automatic NODE_ENV replacement, and without this react-dom's reference to
  // it survives into the browser and throws "process is not defined".
  define:
    command === "build"
      ? {
          "process.env.NODE_ENV": JSON.stringify("production"),
        }
      : {},
  build: {
    outDir: resolve(__dirname, "../src/hub_server/assets"),
    // That directory also holds index.html, the favicon and the brand lockups,
    // which are checked in and must not be wiped by a rebuild.
    emptyOutDir: false,
    cssCodeSplit: false,
    lib: {
      entry: resolve(__dirname, "src/hub.tsx"),
      name: "HubUi",
      formats: ["iife"],
      fileName: () => "hub-ui.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) =>
          assetInfo.name === "style.css" ? "hub-ui.css" : (assetInfo.name ?? "[name][extname]"),
      },
    },
  },
}));

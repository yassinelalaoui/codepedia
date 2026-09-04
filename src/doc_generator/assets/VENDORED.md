# Vendored asset: mermaid.min.js

- Source: https://www.npmjs.com/package/mermaid
- Version: 10.9.8
- File: `dist/mermaid.min.js` (classic UMD/IIFE global build; exposes `window.mermaid`
  when loaded as a plain, non-module `<script>` tag — required so the generated
  documentation renders correctly when opened directly via `file://`, where
  ES-module scripts are blocked by browser CORS policy)
- License: MIT (see https://github.com/mermaid-js/mermaid/blob/master/LICENSE)
- Fetched from: https://cdn.jsdelivr.net/npm/mermaid@10.9.8/dist/mermaid.min.js

This file is bundled with the tool and copied into every generated
documentation output's `assets/` folder so diagrams render with zero runtime
network requests.
# Bundled asset: favicon.ico

- Source: this repository's own brand kit, `docs/brand/favicon.ico`
- Version: tracked with the brand kit; see `docs/brand/README.md`
- File: 16/32/48/64 px multi-resolution ICO
- License: project-owned artwork, not third-party

Copied verbatim rather than referenced, so a generated wiki keeps its tab icon
when moved away from this repository (036 spec FR-020, FR-021). It is bundled
here and copied into every generated wiki's `assets/` folder by
`DocumentationWriter.ensure_wiki_ui_assets`, alongside `mermaid.min.js`, so the
wiki still renders with zero runtime network requests (constitution 2.2).

Unlike `mermaid.min.js` this is first-party artwork; it is listed here so the
copy stays traceable to its source of truth in `docs/brand/`, which remains the
only place the artwork is edited.

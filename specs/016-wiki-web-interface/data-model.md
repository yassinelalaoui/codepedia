# Data Model: Wiki Web Interface

This feature adds one new generated artifact, one new vendored asset, and
reuses every existing entity from 012/013/014/015 unchanged.

## Reused entities

- **`DocumentationSet` / `DocPage`** (`doc_generator`, 012/013): the
  already-generated wiki content this feature reads to build the search
  index and enhances at the home-page level only.
- **`ModuleSymbol` / class / function symbols** (`parser_engine`,
  002/003, surfaced through `doc_generator`): the source of every
  `SearchIndexEntry`'s name and stable id.
- **`VendoredMermaidAsset`** (`doc_generator`, 013): the precedent this
  feature's `WikiUiBundle` directly mirrors.
- **`CreateSessionResponse` / `AskQuestionRequest` / `AskQuestionResponse` /
  `ChatMessageView` / `SessionHistoryResponse` / `ApiErrorResponse`**
  (`chat_api`, 014): unchanged; the chat panel is a client of this existing
  contract, not a change to it.

## New entities

### SearchIndexEntry

Represents one documented, searchable symbol.

Fields:
- `name` — the symbol's display name (e.g. a function or class name).
- `kind` — `"module" | "class" | "method" | "function"`.
- `symbolId` — the symbol's existing stable id (same one used for
  `contentSymbolIds` elsewhere in `doc_generator`).
- `filePath` — the source file the symbol belongs to.
- `pageUrl` — the wiki page URL to navigate to, relative to the wiki root;
  includes a `#<symbol-id-slug>` anchor for anything other than a module's
  own page (per `research.md` Decision 7).

Validation:
- `pageUrl` must always resolve to a real, currently-generated page —
  entries for symbols whose owning page no longer resolves are omitted
  from the index, matching the "drop unresolved links" rule 012/013 already
  apply to `PageLink`s and Mermaid `click` targets.

### SearchIndexDocument

The full generated `search-index.json` file.

Fields:
- `generatedAt` — ISO 8601 UTC timestamp of generation.
- `entries` — `SearchIndexEntry[]`, one per documented symbol.

Relationships:
- Built fresh from the current `DocumentationSet` on every
  `generateRepositoryDocumentation` run (full or incremental), the same way
  every other generated page is; not a static vendored asset like
  `WikiUiBundle` below.
- Consumed client-side by both the search widget (`lib/searchIndex.ts`) and
  the chat panel's citation-link resolution (`research.md` Decision 5).

### WikiUiBundle

The compiled, committed React/TypeScript build output.

Fields:
- `sourcePath` — the vendored files' path inside the `doc_generator`
  package (`src/doc_generator/assets/wiki-ui.js`,
  `src/doc_generator/assets/wiki-ui.css`).
- `outputPath` — their copied location inside a generated documentation
  output (`outputRoot/assets/wiki-ui.js`, `outputRoot/assets/wiki-ui.css`).

Relationships:
- Copied once per `outputRoot` by `DocumentationWriter.ensure_wiki_ui_assets()`,
  mirroring `ensure_mermaid_asset()` (013) exactly — created if missing,
  left untouched once present with matching content.
- Referenced by classic (non-module) `<script>`/`<link>` tags from the
  shared HTML layout every generated page uses.
- Mounts itself into two container elements the layout also provides (see
  `contracts/ui-mount-points.md`): the search widget and the chat panel.

Validation:
- `outputPath` must always resolve inside the configured `outputRoot`,
  subject to the same containment guard as every other file the writer
  creates.

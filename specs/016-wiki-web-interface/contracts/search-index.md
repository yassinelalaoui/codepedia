# `search-index.json` Contract

## Purpose

Define the shape of the generated search-index manifest the search widget
and the chat panel's citation-link resolution both consume client-side.

## Location

Served at `assets/search-index.json`, relative to the wiki root — alongside
`assets/mermaid.min.js` and the vendored UI bundle, via the existing local
server's (015) static mount. Regenerated on every full or incremental
`generateRepositoryDocumentation` run.

## Shape

```json
{
  "generatedAt": "2026-08-12T10:00:00+00:00",
  "entries": [
    {
      "name": "authenticate_user",
      "kind": "function",
      "symbolId": "auth.authenticate_user",
      "filePath": "src/auth/login.py",
      "pageUrl": "modules/login-a1b2c3d4.html#auth-authenticate-user"
    },
    {
      "name": "login",
      "kind": "module",
      "symbolId": "module:repo::...::file::login.py",
      "filePath": "src/auth/login.py",
      "pageUrl": "modules/login-a1b2c3d4.html"
    }
  ]
}
```

Fields, per entry:
- `name` — display name shown in search results.
- `kind` — one of `"module"`, `"class"`, `"method"`, `"function"`.
- `symbolId` — the symbol's stable id, usable to cross-reference a chat
  answer's `citedSymbolIds`.
- `filePath` — usable to cross-reference a chat answer's `citedFilePaths`
  when no more specific symbol match exists.
- `pageUrl` — wiki-root-relative URL; module entries have no anchor,
  class/method/function entries have a `#<symbol-id-slug>` anchor pointing
  at that heading on its owning module page (`research.md` Decision 7).

## Expected behavior

- `entries` contains one item per documented module, class, method, and
  function currently in the generated wiki.
- A symbol whose owning page cannot currently be resolved is omitted
  entirely (not included with a broken `pageUrl`).
- The file is valid JSON and non-empty (`entries` may be an empty array for
  a wiki with no documented symbols yet, but the file itself is always
  well-formed).
- Regenerating documentation with no underlying symbol changes produces
  byte-identical `entries` content (deterministic ordering), though
  `generatedAt` always reflects the current run.

## Consumers

- **Search widget**: loads the document once, matches `name` (and
  optionally `filePath`) against the user's query, navigates to the
  matching entry's `pageUrl` on selection.
- **Chat panel**: for each `citedSymbolIds`/`citedFilePaths` value in a
  014 `AskQuestionResponse`, looks up a matching entry by `symbolId` first,
  then by `filePath`, and renders a link to `pageUrl` when found — see
  `research.md` Decision 5 and `spec.md` Edge Cases for the no-match case
  (label shown without a link).

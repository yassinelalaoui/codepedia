# UI Mount Points Contract

## Purpose

Define how the vendored `WikiUiBundle` attaches to every generated page via
the shared HTML layout, and what it is guaranteed to find there.

## Layout additions

`layout.html.jinja` (013's existing shared layout, already loading the
vendored Mermaid script) gains:

- `<link rel="stylesheet" href="{{ ui_style_href }}">` — page-relative path
  to the vendored `wiki-ui.css`, computed the same way
  `mermaid_script_href` already is.
- Two empty container elements, present on every page:
  - `<div id="wiki-search-root"></div>` — the search widget mounts here.
  - `<div id="wiki-chat-root"></div>` — the chat panel mounts here.
- `<script src="{{ ui_script_href }}"></script>` — page-relative,
  **classic** (no `type="module"`) script tag, loaded after the containers
  exist, per `research.md` Decision 2.

## Bundle responsibilities

On load, the bundle:

1. Looks for `#wiki-search-root` and `#wiki-chat-root` in the current page.
   Both are present on every page (home, module, diagram) since they live
   in the shared layout — the bundle does not need to special-case which
   kind of page it is running on.
2. Fetches `assets/search-index.json` (page-relative, per
   `contracts/search-index.md`) once.
3. Mounts the search widget into `#wiki-search-root` and the chat panel
   into `#wiki-chat-root`.
4. If the fetch for `search-index.json` fails (for example, the page was
   opened via `file://` rather than served by 015), both the search widget
   and the chat panel render a minimal, clearly-labeled unavailable state
   rather than silently doing nothing or throwing an unhandled error —
   consistent with `spec.md`'s edge cases requiring a clear message over a
   broken/blank state. The chat panel additionally surfaces this same
   unavailable state if a chat API request itself fails at the network
   level (as opposed to 014's own structured `404`/`422`/`503` error
   responses, which the chat panel renders using their existing `message`
   text).

## Non-collision with existing content

- The mount points are empty containers with reserved ids; `doc_generator`
  never emits content with those same ids elsewhere on a page, so there is
  no possibility of the bundle mounting into or clobbering existing
  Markdown-derived content.
- The bundle does not modify `pre.mermaid` elements or the Mermaid
  initialization script (013); the two vendored scripts coexist
  independently on the same page.

## Failure expectations

- If the vendored bundle files are missing from the `doc_generator`
  package itself (a packaging error), documentation generation must fail
  with a clear, local error rather than silently omitting the script tags —
  mirroring 013's equivalent failure expectation for the Mermaid asset.
- If `search-index.json` is missing or fails to parse at runtime (in the
  browser), the search widget and chat panel degrade to the clear
  unavailable state described above; this does not prevent the rest of the
  page (module/diagram content, the Mermaid diagram) from rendering and
  functioning normally.

# Quickstart: Wiki Web Interface

## Prerequisites

- Python 3.11 or later, local project dependencies installed
- Node.js/npm available **only** if rebuilding `frontend/`'s bundle; running
  the generated wiki itself needs nothing beyond the existing Python
  environment (the bundle ships pre-built and committed)
- A sample repository already indexed, with documentation generated via the
  existing `doc_generator` pipeline (012/013), including this feature's
  `search-index.json` and enhanced home page
- The combined local server (015) running, with a populated local
  `VectorIndex` and a running local embedding engine and local LLM (as
  required by the chat API, 014)
- A standard, modern web browser

## Validate the enhanced home page

1. Open the wiki's home page through the server (`http://127.0.0.1:8000/`).
2. Confirm it presents an overview of the project's overall architecture
   (not just a flat module list) understandable without prior context.
3. Confirm the home page links to at least one module's documentation page.

## Validate symbol search

1. On any wiki page, locate the search widget.
2. Search for a function or class name you know exists in the sample
   repository.
3. Confirm the results list shows enough context to identify the right
   match, and that selecting it opens that symbol's documentation page,
   scrolled to the right heading.
4. Search for a name that does not exist and confirm a clear "no results"
   message appears.

## Validate dependency diagram navigation still works

1. Open a module's documentation page and follow its link to the
   interactive dependency diagram (013, unchanged by this feature).
2. Click a node and confirm it navigates to that node's documentation page,
   exactly as `specs/013-interactive-dependency-diagram/quickstart.md`
   already validates.

## Validate the chat panel and citation links

1. Locate the chat panel, reachable from any wiki page.
2. Ask a question about the indexed repository.
3. Confirm the generated answer appears, with every cited file/symbol shown
   as a distinguishable, clickable link.
4. Click a citation link and confirm it opens the correct wiki page.
5. Stop the local LLM/embedding engine, ask another question, and confirm
   the chat panel shows a clear error message rather than an unexplained
   stuck or blank state.

## Validate no CDN reference and classic script loading

1. Inspect the generated HTML of any page.
2. Confirm no `http://`/`https://` reference to an external host appears
   anywhere, including for the new UI bundle and stylesheet.
3. Confirm the bundle's `<script>` tag carries no `type="module"`
   attribute.

## Validate the vendored bundle is self-contained and idempotent

1. After generating documentation, confirm `assets/wiki-ui.js` and
   `assets/wiki-ui.css` exist inside the documentation output folder.
2. Confirm re-running generation does not needlessly rewrite those files
   when they are already present and unchanged.

## Expected result

Opening the generated wiki through the local server presents a real
architecture overview on the home page; a user can search for any
documented symbol by name and land on its exact page location; dependency
diagrams remain fully click-navigable; and a user can ask the chat panel a
question and follow every citation link straight to the documented code it
references — all without any external network dependency, and without
needing Node.js/npm to simply run the already-built tool.

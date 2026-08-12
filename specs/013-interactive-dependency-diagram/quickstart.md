# Quickstart: Interactive Dependency Diagram

## Prerequisites

- Python 3.11 or later, local project dependencies installed
- A sample repository already indexed and documented via the existing
  `doc_generator` pipeline (feature 012), so at least one module has a
  generated diagram page
- A standard, modern web browser with JavaScript enabled

## Validate the diagram renders and is interactive

1. Generate documentation for a sample repository with at least two modules
   that depend on each other (the existing `alpha`/`beta`/`gamma` fixture
   used by 012's tests works well).
2. Open the generated diagram page's HTML output for one of the modules
   directly from the local filesystem (no local server), in a browser.
3. Confirm a rendered diagram (not just a code block or raw text) appears on
   the page, showing that module's real outgoing and incoming dependencies.
4. Confirm outgoing and incoming dependencies are visually distinguishable
   (e.g., arrow direction is clear for each edge).
5. Confirm no request to any external domain appears in the browser's
   network activity while the page loads and the diagram renders.

## Validate node navigation

1. On an open diagram page, click a node representing a related module.
2. Confirm the browser navigates to that module's documentation page.
3. Repeat for a different node and confirm it opens its own distinct,
   correct page rather than the previous target.

## Validate direct-dependency scoping

1. Generate documentation for a repository with many files/modules.
2. Open the diagram page for one module in that repository.
3. Confirm the diagram shows only that module's direct dependencies, not
   every module in the repository, and remains legible.

## Validate the no-JS fallback

1. Open a generated diagram page's HTML output with JavaScript disabled (or
   inspect the raw Markdown/HTML source directly).
2. Confirm the existing static "Related modules" links and "Edges" table
   (from 012) are still present and usable even though the interactive
   diagram itself did not render.

## Validate the local asset is self-contained

1. After generating documentation, confirm `assets/mermaid.min.js` exists
   inside the documentation output folder.
2. Confirm the generated HTML references that file with a page-relative
   path, not a CDN URL.
3. Confirm re-running generation does not needlessly rewrite the asset file
   when it is already present and unchanged.

## Expected result

Every module's documentation page links to a diagram that renders as an
interactive Mermaid diagram entirely in the browser, with no external
network dependency; every node in that diagram is clickable and opens the
correct documentation page; the diagram never attempts to show more than the
focused module's direct dependencies; and a static fallback remains available
when interactive rendering is not possible.
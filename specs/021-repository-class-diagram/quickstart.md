# Quickstart: Repository Class Diagram

## Prerequisites

- Python 3.11 or later, local project dependencies installed
- A sample repository already indexed and documented via the existing
  `doc_generator` pipeline, containing at least two classes across
  different modules, one inheriting from the other
- A standard, modern web browser with JavaScript enabled

## Validate the class diagram

1. Generate documentation for the sample repository.
2. Open the wiki's overview page and confirm it links to a single class
   diagram (not one per module).
3. Open that diagram and confirm it renders (not just a code block) showing
   the sample repository's classes, their methods, and the inheritance
   relationship between the two related classes — regardless of which
   modules they live in.
4. Against a repository with far more classes than the 40-class cap,
   confirm the diagram still renders as one legible diagram and states how
   many classes were omitted, rather than attempting to show everything.
5. Against a repository with zero classes, confirm no class-diagram page or
   link is produced (no broken link on the overview page).

## Validate the Mermaid parses (not just renders in a forgiving browser)

1. Include a fixture symbol whose name contains a literal `;`.
2. Confirm the generated Mermaid `classDiagram` source for that class does
   not contain an unescaped `;` — feed the generated ` ```mermaid ` block
   through a real Mermaid parser (e.g. `mermaid.parse` in Node, as used to
   diagnose the original bug in this repository's own hand-authored
   diagrams) and confirm it parses without error.

## Validate incremental regeneration

1. Generate documentation for the sample repository once (full run).
2. Make an edit far from any of the sample classes (e.g. add an unrelated
   new function to an unrelated module) and regenerate incrementally.
3. Confirm the class diagram page is still regenerated (it's a
   repository-wide view; Research Decision 3 always refreshes it on any
   change) and still reflects the edit's ripple effects correctly.
4. Confirm none of this required a full, non-incremental reindex.

## Expected result

The generated wiki's overview page links to exactly one class diagram,
repository-wide and kept legible by design (capped/curated content, not a
raw dump); it renders as valid, parseable Mermaid with zero external
network requests; and it stays correctly in sync with the repository
through the existing incremental regeneration pipeline.

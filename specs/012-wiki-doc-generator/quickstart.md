# Quickstart: Local Wiki Documentation Generator

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed (including Jinja2 and a Markdown
  renderer)
- A sample repository already indexed by `repository_metadata` and
  `dependency_graph`
- The sample repository's modules already summarized by
  `CodeSummaryPipeline` (010), so at least some symbols carry a
  `generatedSummary`

## Validate full documentation generation

1. Index a sample repository containing at least two modules with a
   dependency between them, and run the summary pipeline so at least one
   module/function has a generated summary.
2. Run `DocGenerator.generateRepositoryDocumentation` for the sample
   repository with `incremental=False`.
3. Open the generated home page (Markdown and HTML) and confirm it lists the
   sample repository's actual modules and their real dependency
   relationships.
4. Open a generated module page and confirm it lists the module's actual
   classes/functions along with their generated summaries.
5. Open a generated dependency diagram page and confirm it shows the
   module's real dependency edges and links back to the involved module
   pages.
6. Follow every link on the home page, each module page, and each diagram
   page, and confirm every link resolves to an existing generated page
   (zero broken links).

## Validate incremental regeneration

1. Note the current output paths and content of all generated pages.
2. Change one module's source in the sample repository and re-run the
   indexing/summary pipelines incrementally for that change.
3. Run `DocGenerator.generateRepositoryDocumentation` again with
   `incremental=True`, passing the changed paths/symbol ids.
4. Confirm only the pages impacted by that change (the changed module's
   page, its dependency diagram page, and any page linking to them; the home
   page only if the architecture overview changed) were rewritten.
5. Confirm every other previously generated page is unchanged.
6. Confirm all links across the full documentation set still resolve after
   the partial regeneration.

## Validate the documentation folder stays isolated and versionable

1. Confirm every generated file lives inside one dedicated documentation
   folder, separate from the analyzed repository's source folders.
2. Confirm no file outside that folder was created, modified, or deleted by
   the generation run.
3. Add an unrelated manually created file inside the documentation folder,
   re-run generation, and confirm that file is left untouched.
4. Confirm the documentation folder can be reviewed and committed with
   standard version control tools (e.g., `git status`, `git add`) without
   any additional export or conversion step.

## Expected result

Running the generator against an indexed and summarized test repository
produces a home page that reflects the real project architecture, one page
per module listing its symbols with their generated summaries and valid
links to related pages, and one page per dependency diagram, all written as
plain Markdown/HTML files inside a separate, committable documentation
folder. A later incremental re-index regenerates only the pages impacted by
the change.

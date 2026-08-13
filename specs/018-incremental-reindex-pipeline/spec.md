# Feature Specification: Incremental Reindexing Pipeline

**Feature Branch**: `018-incremental-reindex-pipeline`

**Created**: 2026-08-13

**Status**: Draft

**Input**: User description: "Construire la logique de ré-indexation incrémentale déclenchée par le watcher de fichiers. Lorsqu'un ou plusieurs fichiers sont modifiés, le système doit ré-analyser uniquement ces fichiers (re-parsing, ré-extraction de symboles), identifier via le graphe de dépendances les symboles dont le résumé dépend directement des fichiers modifiés et les régénérer, mettre à jour uniquement les vecteurs d'embeddings et pages de documentation concernés, sans jamais relancer une analyse complète du dépôt. Le hash de contenu stocké en base (Partie 2.1) doit être utilisé pour confirmer qu'un fichier a réellement changé avant de déclencher un retraitement coûteux. Critère de succès : sur un dépôt volumineux déjà indexé, la modification d'un seul fichier entraîne une mise à jour de la documentation en un temps très inférieur à une ré-indexation complète, et le résultat final est identique à celui obtenu par une ré-indexation complète du dépôt."

## Overview

Orchestrate the actual reindexing work triggered by the repository change
watcher's (017) reindexing handoff. This feature ties together the
already-incremental-capable analysis stages — symbol re-extraction,
dependency-graph update, impacted-summary regeneration, embedding updates,
and documentation regeneration — into one selective pass that touches only
what a batch of file changes actually affects, and never re-analyzes the
whole repository.

## Goals

- Given a batch of changed files (created, modified, or deleted) from the
  watcher (017), update the repository's stored metadata, dependency
  graph, generated summaries, embeddings, and documentation to reflect
  exactly those changes.
- Confirm a "modified" file's content genuinely changed — via its stored
  content hash (005) — before doing any expensive reprocessing on it.
- Touch only the files, symbols, embeddings, and documentation pages
  actually impacted by a batch — never re-scan, re-parse, re-summarize,
  re-embed, or regenerate documentation for the entire repository.
- Produce a final indexed and documented state identical, for the
  affected scope, to what a full re-indexation of the repository would
  produce.

## Non-Goals

- Detecting file changes or debouncing bursts of changes; that is the
  watcher's (017) responsibility. This feature starts from an
  already-stabilized batch of impacted files.
- Re-implementing symbol extraction (002/003), the dependency graph
  (004), the code summary pipeline (010), embedding generation (009) or
  the vector index (006/007), or documentation generation (012); this
  feature composes their existing incremental capabilities rather than
  replacing them.
- Performing the initial, full, from-scratch indexation of a repository
  that has never been indexed; that remains a separate flow.
- A user-facing trigger or UI for manually requesting reindexing.

## User Stories

### US1 - Documentation reflects a single edited file quickly

As a developer, I want editing one file to update its documentation,
summary, and searchable content quickly, so that what I see always
matches the code I just changed, without waiting for a full repository
re-scan.

Acceptance criteria:

- Modifying one file results in that file's symbols being re-extracted.
- Only that file's summary, and any symbol whose summary directly depends
  on it, is regenerated.
- Only that file's embedded content is updated.
- Only the documentation pages affected by the change are regenerated.
- No unrelated file, symbol, embedding, or documentation page is
  reprocessed.

### US2 - Unreal changes are skipped

As a maintainer, I want a "file modified" signal that turns out not to
have changed the file's actual content to be skipped rather than
triggering reprocessing, so that noisy or redundant change signals don't
waste time or produce spurious documentation churn.

Acceptance criteria:

- Before reprocessing a file reported as modified, its current content
  hash is compared against the previously stored hash.
- If the hashes match, no re-parsing, re-summarization, re-embedding, or
  documentation regeneration happens for that file.
- If the hashes differ, the file is fully reprocessed.

### US3 - New and removed files stay in sync

As a developer, I want a newly created file to appear in the index and
documentation, and a deleted file's symbols, embeddings, and pages to
disappear, so that the documentation never shows stale entries for code
that no longer exists nor omits code that now does.

Acceptance criteria:

- A newly created file's symbols are extracted and added to the
  dependency graph, its summary is generated, its content is embedded,
  and a documentation page is created for it.
- A deleted file's symbols are removed from the dependency graph, its
  stored metadata and embeddings are removed, and any documentation page
  that existed only for it is removed.
- Documentation pages that referenced a now-deleted file's symbols are
  updated to no longer show them as available.

### US4 - Batches of changed files are processed together

As a maintainer, I want a batch containing several changed files (for
example, from a branch switch) to be reprocessed as a whole so that
cross-file impact (like a function that calls into another changed file)
is captured correctly in one pass, rather than requiring several separate
runs.

Acceptance criteria:

- All files in a single change batch are re-parsed and their impacted
  symbols and documentation pages computed together.
- A symbol whose summary depends on more than one changed file in the
  same batch is regenerated once, not once per changed dependency.
- The result of processing one multi-file batch matches the result of
  processing the same files individually and combining the outcomes.

### Edge Cases

- What happens when a "modified" file's content hash matches what's
  already stored? No reprocessing occurs for that file (US2).
- What happens when a changed file fails to re-parse (e.g., invalid
  syntax)? The failure is reported clearly for that file; other files in
  the same batch, and summaries/embeddings/pages unaffected by it, are
  still processed normally.
- What happens when the local summarization model is unavailable? Symbol
  re-extraction, dependency-graph updates, and embedding updates proceed
  since they don't require it; summary regeneration reports a clear
  failure instead of silently skipping or falling back to a remote
  service, consistent with the rest of the product.
- What happens when a change to one file invalidates a documentation page
  that itself links to another page (e.g., a home page listing all
  modules)? That referring page is also regenerated, not just the page
  for the changed file.
- What happens when the same file appears more than once in effect within
  a batch (e.g., modified then deleted before the pipeline runs)? The
  pipeline reacts to the batch's final, net change for that file, not to
  each intermediate state.
- What happens when a symbol is renamed inside an otherwise-unchanged
  file (so it gets a new identity but the file is genuinely modified)?
  The old symbol's summary, embedding, and any documentation state tied
  to its old identity are removed rather than left behind as a stale
  duplicate.

## Requirements *(mandatory)*

### Functional Requirements

#### Triggering and scope

- The pipeline MUST accept a batch of impacted files, each with its
  change kind (created, modified, or deleted), matching the shape the
  repository change watcher (017) produces.
- The pipeline MUST process every file in a batch together, so that
  cross-file impact within the same batch is captured in a single pass.
- The pipeline MUST NOT re-scan, re-parse, re-summarize, re-embed, or
  regenerate documentation for any file outside the batch's impact,
  regardless of repository size.

#### Change confirmation

- Before reprocessing a file reported as modified, the pipeline MUST
  compare its current content hash against the previously stored content
  hash (005) for that file.
- If the current and stored content hashes match, the pipeline MUST skip
  re-parsing, re-summarization, re-embedding, and documentation
  regeneration for that file.
- If the hashes differ, or no previous hash exists for the file, the
  pipeline MUST fully reprocess it.

#### Symbol and dependency-graph update

- For each file that requires reprocessing, the pipeline MUST re-parse it
  and re-extract its symbols.
- The pipeline MUST update the dependency graph so that the file's
  current symbols and relations replace whatever was previously recorded
  for that file, leaving no stale entries from the file's prior content.
- For a deleted file, the pipeline MUST remove its symbols and relations
  from the dependency graph and from stored metadata.

#### Impacted summary regeneration

- The pipeline MUST use the dependency graph to identify which symbols'
  summaries directly depend on a changed file's symbols.
- The pipeline MUST regenerate summaries only for the changed symbols and
  the symbols identified as directly depending on them.
- The pipeline MUST leave summaries for unrelated symbols unchanged.

#### Embedding updates

- The pipeline MUST update the embedded, searchable content for each
  reprocessed file so it reflects the file's current content.
- The pipeline MUST remove embedded content for a deleted file.
- The pipeline MUST NOT regenerate embedded content for files outside the
  batch's impact.

#### Documentation updates

- The pipeline MUST regenerate only the documentation pages impacted by
  the batch, including pages that directly document a changed file and
  pages that reference a page that was added or removed as a result of
  the batch.
- The pipeline MUST remove documentation pages that exist only for a file
  that was deleted.
- The pipeline MUST leave documentation pages unaffected by the batch
  unchanged.

#### Consistency with a full re-index

- The pipeline's resulting stored metadata, dependency graph, summaries,
  embeddings, and documentation for the affected scope MUST match what a
  full re-indexation of the repository would produce for that same scope.

### Key Entities

- **ReindexBatch**: The set of impacted files, each with its change kind
  (created, modified, or deleted), handed to the pipeline for one
  processing pass, matching the watcher's (017) reindexing handoff shape.
- **ChangeConfirmation**: The outcome of comparing a file's current
  content hash against its previously stored hash, determining whether
  the file is genuinely changed and needs reprocessing.
- **ImpactedSymbolSet**: The set of symbols, drawn from the dependency
  graph, whose summaries must be regenerated because they changed
  directly or depend directly on something that changed.
- **ImpactedDocumentationSet**: The set of documentation pages that must
  be regenerated or removed as a result of a batch, including pages for
  changed files and pages that reference them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a large, already-indexed repository, modifying a single
  file results in updated documentation in a time far shorter than a
  full re-indexation of the repository takes.
- **SC-002**: The stored metadata, summaries, embeddings, and
  documentation produced after an incremental update are identical, for
  the affected scope, to what a full re-indexation of the same
  repository state would produce.
- **SC-003**: A "modified" signal for a file whose content hash is
  unchanged results in zero re-parsing, re-summarization, re-embedding,
  or documentation regeneration work for that file.
- **SC-004**: A batch touching a small number of files out of a large
  repository leaves every unrelated file's stored symbols, summary,
  embedding, and documentation page untouched.
- **SC-005**: A newly created file becomes fully documented, and a
  deleted file's documentation fully disappears, without any other file
  being reprocessed.

## Assumptions

- The pipeline is invoked with the impacted-file batch already produced
  by the repository change watcher (017); this feature does not detect
  changes or perform debouncing itself.
- Each of the underlying stages this pipeline orchestrates — symbol
  extraction (002/003), the dependency graph (004), the code summary
  pipeline (010), embeddings (009) and the vector index (006/007), and
  documentation generation (012) — already exists and already supports
  processing a single file or a small set of impacted symbols/pages;
  this feature is responsible for the confirm-then-reprocess sequencing
  and impact propagation across them, not for building those
  capabilities from scratch.
- When the local summarization model is unavailable, symbol,
  dependency-graph, and embedding updates still proceed, since they don't
  require it, while summary regeneration reports a clear failure rather
  than silently skipping it or using a remote fallback, consistent with
  the rest of the product's local-first behavior.
- "Identical to a full re-indexation" means the same stored symbols,
  relations, summaries, embeddings, and documentation content for the
  affected files — not necessarily identical file timestamps or internal
  processing order.
- A file's content hash, as already stored per Part 2.1 (005), is the
  authoritative signal for whether a file actually changed.

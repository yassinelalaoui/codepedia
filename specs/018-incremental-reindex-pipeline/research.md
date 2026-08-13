# Phase 0 Research: Incremental Reindexing Pipeline

## 0. Interpreting "Parties 1, 2, 3.3 et 4.1 en mode ciblé"

**Decision**: Reuse, in "targeted" (explicit file-list) mode rather than whole-repository mode:

| Part (user's numbering) | Component | Existing "targeted" capability found |
|---|---|---|
| 1 | Scanner (`repo_scanner`, 001) | None — `scan_repository()` always walks the full tree. Must be used per-path instead (§1). |
| 2 | Parsing / symbol extraction / metadata persistence (`parser_engine` 002/003, `repository_metadata` 005) | Already per-file: `extract_symbols(SourceFile)`, `RepositoryMetadataStore.store_inventory(...)`. |
| 3.3 | Local vector index (`vector_index`, 006/007, built on `embedding_engine` 009) | Already per-file: `VectorIndex.reindexFile(path, chunks)` / `removeChunksForFile(path)`. |
| 4.1 | Code summary pipeline (`repository_metadata.summary_pipeline`, 010) | Already targeted: `CodeSummaryPipeline.summarizeRepository(..., changed_paths=...)` / `summarizeSourceFile(...)`. |

**Rationale**: Matching each `changed_paths`/per-file parameter already present on `store_inventory`, `reindexFile`, and `summarizeRepository(changed_paths=...)` to the batch's file list is what "mode ciblé" means operationally in this codebase — feed these functions the batch's paths, never the whole repository. The scanner (Part 1) is the one component with no targeted entry point yet (§1 below covers the fix). `doc_generator` (012) is reused too, even though not explicitly named in the user's instruction — it already accepts `changedPaths`/`changedSymbolIds` (`generateRepositoryDocumentation`) and is required by the spec's documentation-update requirements.

**Alternatives considered**: Re-deriving the "Parties" numbering from a source document — none is present in this repository; the mapping above is inferred from content (matching each part's description to the sibling feature whose existing API already matches "mode ciblé"), not from an external doc.

## 1. Classifying changed paths without a full scan

**Decision**: For each path in the batch, classify it directly using the scanner's (001) existing primitives — `repo_scanner.ignore.load_ignore_matcher(root).ignores(path)`, `repo_scanner.binary.is_binary_path(root / path)`, and `repo_scanner.language.LanguageDetector().detect(root / path)` — instead of calling `scan_repository()`.

**Rationale**:
- `scan_repository()` walks the entire repository tree, which is exactly the full-repository cost this feature must avoid (spec: "sans jamais relancer une analyse complète du dépôt").
- The watcher (017) already filters exclusions before a path ever reaches a `ChangeBatch`, so re-checking `IgnoreMatcher` here is a cheap defensive re-confirmation, not new work — a file the watcher already excluded is never handed to this pipeline in the first place.
- A batch path that is binary, or whose language `LanguageDetector` cannot determine, is skipped from parsing/symbols/summaries/embeddings exactly as the scanner would skip it during a full scan — this is what keeps an incremental run's output identical to what a full re-index would produce for that file (spec's consistency requirement).

**Alternatives considered**: Calling `scan_repository()` and filtering its result down to the batch's paths — rejected; it performs the exact full-tree walk this feature exists to avoid, only to throw away everything except a handful of entries.

## 2. Re-parsing and metadata persistence

**Decision**: Reuse `parser_engine.extract_symbols(SourceFile(path=.., language=..))` and `RepositoryMetadataStore.store_inventory(...)` (005) unchanged for every created/modified file that needs reprocessing (§3 gates this).

**Rationale**: Both already operate on a single file. `store_inventory` already deletes and replaces exactly that file's prior symbol/edge rows before inserting the fresh ones (`sqlite_store._delete_source_file_records`), so no stale symbol rows survive a modified file's reprocessing.

**Gap found — deleted files**: `RepositoryMetadataStore` has no public method to remove a file's metadata without replacing it with a new inventory. The underlying SQL (`_delete_source_file_records`) already exists privately. **Decision**: add a small public method, `RepositoryMetadataStore.delete_source_file(repository_root, path)`, that resolves the file's stable id and calls the existing private deletion helper. This is a compatible extension (new method, no behavior change to existing callers), not a reimplementation of 005.

## 3. Change confirmation via stored content hash

**Decision**: Reuse `repository_metadata.fingerprints.compute_content_hash` and `RepositoryMetadataStore.has_file_changed(repository_root=..., path=..., current_hash=...)` (005, "Partie 2.1") unchanged. For every file the batch reports as `MODIFIED`, compute its current hash and skip re-parsing/re-summarizing/re-embedding/doc-regeneration entirely when `has_file_changed` returns `False`.

**Rationale**: This is exactly the confirmation the spec requires before "tout retraitement coûteux." `CREATED` files have no prior hash by definition (`has_file_changed` already returns `True` when `stored_hash` is `None`), so the same check works for them without a special case. `DELETED` files skip the hash check entirely — there is nothing to compare, only removal.

**Alternatives considered**: Trusting the watcher's `ChangeType` at face value — rejected; the spec explicitly requires the hash check to guard against a "modified" signal that isn't a real content change (017's own debounce/dedup already avoids most noise, but a hash check is the deterministic, storage-level confirmation the spec asks for and is cheap relative to re-parsing).

## 4. Dependency graph: incremental update without stale entries

**Decision**: Load the full persisted graph once per batch (`DependencyGraph.load(db_path, graph_id=<stable repository id>)`), mutate it in memory for the batch's files, then save the whole graph back (`DependencyGraph.save(db_path)`). Because the graph is loaded before mutation, the pipeline can diff `edges.keys()` before and after — the resulting added/removed `EdgeId` set is what §7 requires as `changedDependencyEdgeIds` for `DocGenerator.generateRepositoryDocumentation`, so this diffing must happen as part of this step, not be recomputed later.

**Gap found**: `DependencyGraph` has `ingest_inventory()` (adds a file's nodes/edges) but no method to remove a file's *previous* nodes/edges before re-ingesting its new version, or to remove them for a deleted file — calling `ingest_inventory` again on a changed file would leave the old symbol nodes/edges (keyed by content-hash-derived ids that change on any edit) behind forever, violating the spec's "no stale entries" requirement and its "identical to a full re-index" success criterion. **Decision**: add `DependencyGraph.remove_source_file(source_file: str)`, which drops every node whose `sourceFile` matches and every edge touching a dropped node, before `ingest_inventory` runs for a modified file (and as the only step, for a deleted one).

**Graph identity pitfall found**: `DependencyGraph.build_from_inventories(...)` derives a *content-based* graph id (`_stable_graph_id`, a hash of the sorted input file list) when no `id` is given. Building a fresh graph from only the batch's few changed inventories would produce a graph id unrelated to the already-persisted, full-repository graph's id, so `DependencyGraph.load(db_path, graph_id=...)` would never find it again. **Decision**: this pipeline always loads the existing graph by a *stable, repository-root-derived* id (`repository_metadata.sqlite_store.stable_repository_id(repository_root)` — the same id already used as `repositoryId` elsewhere, e.g. `doc_generator`), never rebuilds it from scratch via `build_from_inventories`, and saves back under that same id.

**Rationale for a full-graph save despite "never re-analyze the whole repository"**: The expensive work this feature must avoid is re-*analysis* — re-parsing, re-summarizing (LLM calls), and re-embedding. Rewriting the graph's node/edge rows via `save()` (a bulk `DELETE`+`INSERT` computed from an already-updated in-memory graph, per `dependency_graph/persistence.py`) is a local, non-LLM, non-parsing SQLite operation whose cost scales with total repository symbol count, not with reprocessing cost — the same trade-off `doc_generator`'s existing incremental path (`generateRepositoryDocumentation`, §6) already accepts by loading the full `RepositoryBundle` before selecting which pages to (re)write.

**Alternatives considered**: Extending `dependency_graph/persistence.py` with true incremental (delta) node/edge writes — rejected as unnecessary scope for this feature; the bulk rewrite is already fast relative to re-analysis, and 004's persistence contract would need a broader redesign to support it safely.

**Bug found during implementation — cross-file callers losing their edge on a callee's identity change**: Symbol ids are content-hash-derived, so re-ingesting a changed file's inventory gives every symbol in it a *new* id, even for symbols whose code didn't move. `remove_source_file` correctly drops edges pointing at the old ids — but an edge from an *unchanged* file elsewhere in the repository (e.g., `alpha.py` calling `beta.py`'s `beta_helper`) also gets dropped, and nothing re-creates it, because `alpha.py` is not being re-ingested this batch. Left unfixed, `dependents()` would silently undercount after the very first incremental update to a function with external callers — directly breaking the "regenerate direct dependents" requirement (US1) tested against a real cross-file fixture, not a hypothetical case. **Decision**: `graph_sync.py` captures every incoming edge from a node *outside* the batch's changed files into a node *inside* them before removal, then — once the changed files are re-ingested — re-links each captured edge by exact `(name, symbolType)` match against the freshly-ingested nodes (skipping ambiguous or now-missing matches, mirroring `_resolve_symbol_target`'s own single-candidate rule). This is what makes `docs/quickstart.md`'s cross-file scenarios pass against a graph built incrementally, not just one built fresh via `build_from_inventories`.

## 5. Impacted-symbol identification and summary regeneration

**Decision**: Reuse `CodeSummaryPipeline.summarizeRepository(repository_root, incremental=True, changed_paths=<files confirmed changed in §3>)` (010, "Partie 4.1") unchanged.

**Rationale**: It already does exactly what the spec asks — walks the dependency graph's `dependents(symbol_id)` for each changed symbol to compute the direct-dependent set, then regenerates only those symbols' summaries, leaving everything else untouched. Running it after §4's graph update ensures the impact computation sees the *current* dependency edges (including new callers/importers introduced by this batch), not stale ones.

**Failure handling**: Per the spec's edge case and existing `CodeSummaryPipeline` contract (010), if the local LLM is unavailable, summary regeneration raises `LocalLLMUnavailableError` immediately. The pipeline runs summary regeneration *after* the metadata/graph/embedding steps (§2, §4, §6) precisely so those updates — which do not need the LLM — are not lost or skipped because the model happens to be down.

## 6. Embedding updates

**Decision**: For each file confirmed changed (§3) or newly created, build one `CodeChunk` per in-scope symbol (module plus public, non-nested functions/classes — the same selection `CodeSummaryPipeline._summarizable_symbols` already uses, reused here for consistency) from that **symbol's own source text**, embed it via the configured `EmbeddingEngine`, and call `VectorIndex.reindexFile(path, chunks)` (which already removes the file's old chunks before adding the new ones). For a deleted file, call `VectorIndex.removeChunksForFile(path)`.

**Rationale**:
- No existing code in the repository currently populates the vector index (`reindexFile`/`build_code_chunk`/`addChunks` have no production caller yet — only `chat_api/server.py` *reads* an already-populated index for search). This pipeline is the first feature that must decide the chunk-content convention.
- Chunking by *source text* rather than by the LLM-generated summary keeps embedding freshness independent of local-LLM availability, matching §5's failure-handling requirement (embeddings must update even when summarization fails) and the spec's edge case.
- Reusing the same symbol selection as the summary pipeline keeps `CodeChunk.sourceSymbolId` aligned with the symbols that actually have (or will have) a generated summary, which the existing RAG citation contract (011, `citedSymbolIds`) already depends on — a chunk without a matching summarized symbol would produce a citation with nothing to cite.
- `VectorIndex.reindexFile` and `removeChunksForFile` already exist and already operate per file (§0), so no new vector-index code is needed beyond this chunk-building step.

**Alternatives considered**: Chunking by generated summary text — rejected; couples embedding freshness to LLM availability, contradicting the edge case that embeddings must still update when the model is down.

## 7. Documentation updates

**Decision**: Reuse `DocGenerator.generateRepositoryDocumentation(repositoryRoot, incremental=True, changedPaths=<batch paths>, changedSymbolIds=<§5's impacted symbol ids>, changedDependencyEdgeIds=<edges added/removed by §4>)` (012) unchanged.

**Rationale**: It already computes exactly the impacted/removed page set the spec requires (`compute_regeneration_impact`, including propagation to pages that link to a removed page, e.g. a home page listing all modules) and already calls `DocumentationWriter.remove_page(...)` for deleted-file pages. Passing `changedDependencyEdgeIds` (tracked while §4 mutates the graph) ensures dependency-diagram pages affected by a changed relation are also regenerated, not just pages that directly document a changed file.

**Alternatives considered**: Recomputing impacted pages independently inside this feature — rejected; `doc_generator`'s existing impact computation already handles the page-reference-propagation edge case the spec calls out, and duplicating it would risk drifting out of sync with 012/016's page-linking logic.

## 8. Processing order within one batch

**Decision**: Within one `ReindexBatch`, process in this order: (a) classify + hash-confirm every path (§1, §3); (b) for each file needing reprocessing, update dependency-graph + metadata together, file by file (§2, §4); (c) once every file's graph/metadata update has landed, compute impacted symbols and regenerate summaries for the whole batch in one call (§5); (d) update embeddings per confirmed-changed/created file, and remove embeddings for deleted files (§6); (e) regenerate/remove impacted documentation for the whole batch in one call (§7).

**Rationale**: Steps (b) must complete for every file in the batch before (c)/(e) run, so that cross-file impact within the same batch (spec US4 — e.g., a function in file A that calls into changed file B) is computed against the batch's *final* graph state in one pass, not file-by-file in isolation (which could miss impact from a file processed later in the same batch).

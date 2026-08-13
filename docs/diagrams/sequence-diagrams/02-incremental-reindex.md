# Major Function: Incremental Reindexing (Watcher-Triggered)

**Specs**: 017, 018

The self-updating flow: a saved edit reaches the browsable wiki in seconds, touching
only what actually changed — never a full repository re-analysis.

```mermaid
sequenceDiagram
    actor Developer
    participant FileSystem
    participant RepositoryWatcher as "Repository Watcher (017)"
    participant Pipeline as "Incremental Reindex\nPipeline (018)"
    participant RepositoryMetadataStore as "Metadata Store (005)"
    participant ParserEngine as "Parser & Symbol\nExtractor (002/003)"
    participant DependencyGraph as "Dependency Graph (004)"
    participant CodeSummaryPipeline as "Summary Pipeline (010)"
    participant VectorIndex as "Vector Index (006/007/009)"
    participant DocGenerator as "Doc Generator (012)"

    Developer->>FileSystem: save one file
    FileSystem->>RepositoryWatcher: raw filesystem event
    RepositoryWatcher->>RepositoryWatcher: ignore-rule filter + debounce\n(stabilization delay)
    RepositoryWatcher->>Pipeline: on_batch(ChangeBatch([FileChange(path, MODIFIED)]))

    Pipeline->>RepositoryMetadataStore: has_file_changed(path, currentHash)
    alt hash unchanged (false alarm)
        RepositoryMetadataStore-->>Pipeline: False
        Pipeline-->>Pipeline: skip — no reprocessing at all
    else content genuinely changed
        RepositoryMetadataStore-->>Pipeline: True
        Pipeline->>ParserEngine: extract_symbols(file)
        ParserEngine-->>Pipeline: FileSymbolInventory
        Pipeline->>RepositoryMetadataStore: store_inventory(...)
        Pipeline->>DependencyGraph: remove_source_file(old) + ingest_inventory(new)
        Note over DependencyGraph: also re-links any edge from an unchanged\ncaller elsewhere in the repo, by name, so\ndependents() stays correct across edits
        DependencyGraph-->>Pipeline: changed EdgeId set

        Pipeline->>CodeSummaryPipeline: summarizeRepository(changed_paths=[file])
        CodeSummaryPipeline-->>Pipeline: regenerated summaries\n(changed symbol + direct dependents only)

        Pipeline->>VectorIndex: reindexFile(path, chunks)

        Pipeline->>DocGenerator: generateRepositoryDocumentation(\nchangedPaths, changedSymbolIds, changedDependencyEdgeIds)
        DocGenerator-->>Pipeline: only the impacted pages regenerated
    end
    Pipeline-->>RepositoryWatcher: ReindexOutcome
```

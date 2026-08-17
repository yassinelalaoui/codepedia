# Major Function: Full Repository Indexing

**Specs**: 001, 002/003, 004, 005, 009/010, 006/007, 012, 019

The from-scratch flow: `repo-scanner index <path>` (019) points the tool at a
repository once, and it becomes a fully analyzed, summarized, embedded, and
documented wiki — staged into a temporary directory and swapped in only on
full success (research.md §10 of 019), so a failed run never corrupts a
previously-successful index.

```mermaid
sequenceDiagram
    actor Operator
    participant cli as "cli (019)\nindex_command.run_index"
    participant scan_repository as "Scanner (001)"
    participant extract_symbols as "Parser & Symbol\nExtractor (002/003)"
    participant DependencyGraph as "Dependency Graph (004)"
    participant RepositoryMetadataStore as "Metadata Store (005)"
    participant DocGenerator as "Doc Generator (012)"
    participant CodeSummaryPipeline as "Summary Pipeline (010)"
    participant LocalLLMEngine as "Local LLM (008)"
    participant EmbeddingEngine as "Embedding Engine (009)"
    participant VectorIndex as "Vector Index (006/007)"

    Operator->>cli: repo-scanner index <path>
    cli->>LocalLLMEngine: checkAvailability()
    cli->>EmbeddingEngine: checkAvailability()
    alt either unavailable
        cli-->>Operator: actionable error (stop, no scanning/parsing/AI work done)
    end

    cli->>scan_repository: scan_repository(request)
    scan_repository-->>cli: ScanResult (relevant source files)

    loop for each file in ScanResult
        cli->>extract_symbols: extract_symbols(source_file)
        extract_symbols-->>cli: FileSymbolInventory
        cli->>RepositoryMetadataStore: store_inventory(root, file, inventory, hash)
    end
    cli->>DependencyGraph: build_from_inventories(inventories).save(...)

    cli->>DocGenerator: generateRepositoryDocumentation(incremental=False)\n(structure pass, no summaries yet)

    cli->>CodeSummaryPipeline: summarizeRepository(root, incremental=False)
    CodeSummaryPipeline->>LocalLLMEngine: checkAvailability()
    alt local model unavailable
        LocalLLMEngine-->>CodeSummaryPipeline: unavailable
        CodeSummaryPipeline-->>cli: raise LocalLLMUnavailableError (stop, no cloud fallback)
    else model ready
        loop for each in-scope symbol
            CodeSummaryPipeline->>DependencyGraph: dependents(), imports (context)
            CodeSummaryPipeline->>LocalLLMEngine: generate(prompt)
            LocalLLMEngine-->>CodeSummaryPipeline: summary text
            CodeSummaryPipeline->>RepositoryMetadataStore: update_symbol_generated_summary(id, summary)
        end
    end

    cli->>DocGenerator: generateRepositoryDocumentation(incremental=False)\n(content pass, reflects the summaries just generated)
    DocGenerator-->>cli: DocumentationSet (home + module + diagram pages written)

    loop for each file in ScanResult
        cli->>EmbeddingEngine: embed(symbol source text) (via update_embeddings)
        EmbeddingEngine-->>cli: vector
        cli->>VectorIndex: reindexFile(path, chunks)
    end

    cli->>cli: staging directory swapped in\n(prior successful state, if any, replaced atomically)
    cli-->>Operator: local URL printed, wiki now served
```

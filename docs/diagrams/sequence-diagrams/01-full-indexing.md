# Major Function: Full Repository Indexing

**Specs**: 001, 002/003, 004, 005, 009/010, 006/007, 012

The from-scratch flow: point the tool at a repository once, and it becomes a fully
analyzed, summarized, embedded, and documented wiki.

```mermaid
sequenceDiagram
    actor Operator
    participant scan_repository as "Scanner (001)"
    participant extract_symbols as "Parser & Symbol\nExtractor (002/003)"
    participant DependencyGraph as "Dependency Graph (004)"
    participant RepositoryMetadataStore as "Metadata Store (005)"
    participant CodeSummaryPipeline as "Summary Pipeline (010)"
    participant LocalLLMEngine as "Local LLM (008)"
    participant EmbeddingEngine as "Embedding Engine (009)"
    participant VectorIndex as "Vector Index (006/007)"
    participant DocGenerator as "Doc Generator (012)"

    Operator->>scan_repository: scan_repository(request)
    scan_repository-->>Operator: ScanResult (relevant source files)

    loop for each file in ScanResult
        Operator->>extract_symbols: extract_symbols(source_file)
        extract_symbols-->>Operator: FileSymbolInventory
        Operator->>DependencyGraph: ingest_inventory(inventory)
        Operator->>RepositoryMetadataStore: store_inventory(root, file, inventory, hash)
    end

    Operator->>CodeSummaryPipeline: summarizeRepository(root, incremental=False)
    CodeSummaryPipeline->>LocalLLMEngine: checkAvailability()
    alt local model unavailable
        LocalLLMEngine-->>CodeSummaryPipeline: unavailable
        CodeSummaryPipeline-->>Operator: raise LocalLLMUnavailableError (stop; no cloud fallback)
    else model ready
        loop for each in-scope symbol
            CodeSummaryPipeline->>DependencyGraph: dependents(), imports (context)
            CodeSummaryPipeline->>LocalLLMEngine: generate(prompt)
            LocalLLMEngine-->>CodeSummaryPipeline: summary text
            CodeSummaryPipeline->>RepositoryMetadataStore: update_symbol_generated_summary(id, summary)
        end
    end

    loop for each in-scope symbol
        Operator->>EmbeddingEngine: embed(symbol source text)
        EmbeddingEngine-->>Operator: vector
        Operator->>VectorIndex: addChunks([chunk])
    end

    Operator->>DocGenerator: generateRepositoryDocumentation(root, incremental=False)
    DocGenerator-->>Operator: DocumentationSet (home + module + diagram pages written)
```

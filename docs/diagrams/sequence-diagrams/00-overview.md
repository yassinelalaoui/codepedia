# Project Sequence Diagram — Overview

**Scope**: the whole system's lifecycle, one diagram — from pointing the tool at a
repository, through indexing, serving, everyday use, and self-updating on edits. Each
participant here is a whole subsystem (not a class); see the per-function diagrams in
this folder for the detail behind each block.

> Maintenance: update this diagram whenever a major phase of the system's lifecycle
> changes. See `README.md` in this folder.

```mermaid
sequenceDiagram
    actor Operator
    actor Developer
    actor Reader as "Team member"
    participant Scanner as "Scanner + Parser +\nDependency Graph + Metadata"
    participant AI as "Summary Pipeline +\nEmbeddings + Local LLM"
    participant Docs as "Doc Generator"
    participant Server as "Web Server + Chat API"
    participant Watcher as "Repository Watcher"
    participant Reindex as "Incremental Reindex\nPipeline"

    Operator->>Scanner: index repository
    Scanner->>Scanner: scan, parse, build dependency graph,\npersist metadata
    Scanner->>AI: analyzed symbols
    AI->>AI: generate summaries, build embeddings
    AI->>Docs: summaries + graph + metadata
    Docs->>Docs: generate wiki pages + diagrams
    Operator->>Server: start local server (127.0.0.1)
    Server-->>Operator: wiki + chat API available

    Reader->>Server: browse wiki / search / ask a question
    Server-->>Reader: pages, search results, cited answers

    Developer->>Watcher: edits a file
    Watcher->>Watcher: debounce, confirm stabilized change
    Watcher->>Reindex: hand off changed-file batch
    Reindex->>Scanner: re-parse + update graph/metadata\n(just the changed files)
    Reindex->>AI: regenerate impacted summaries + embeddings
    Reindex->>Docs: regenerate impacted pages only
    Note over Server: next request already reflects\nthe update — no restart needed

    Reader->>Server: browse again
    Server-->>Reader: up-to-date pages, no full re-index needed
```

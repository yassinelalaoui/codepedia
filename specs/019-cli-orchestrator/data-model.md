# Phase 1 Data Model: Command-Line Interface Orchestrator

This feature introduces one new orchestration package (`cli`) plus two small,
compatible extensions to existing components (research.md §5). It reuses
every domain type already owned by the packages it orchestrates rather than
redefining them.

## Reused types (not redefined here)

| Type | Source | Role in this feature |
|---|---|---|
| `ScanResult`, `SourceFileEntry` | `repo_scanner` (001) | `index`'s candidate file list. |
| `SourceFile`, `FileSymbolInventory` | `parser_engine` (002/003) | Per-file parse input/output during `index`. |
| `RepositoryMetadataStore`, `RepositoryBundle` | `repository_metadata` (005) | Persisted per-file metadata; also how `serve` detects "no prior index" (data flow below). |
| `DependencyGraph` | `dependency_graph` (004) | Built fresh by `index`, loaded by `serve`. |
| `CodeSummaryPipeline`, `SummaryResult` | `repository_metadata.summary_pipeline` (010) | Summary generation, shared by `index` and `serve`'s reindex pipeline. |
| `VectorIndex`, `CodeChunk` | `vector_index` (006/007) | Embedded-chunk storage, built by `index`, read by `serve`. |
| `DocGenerator`, `DocumentationSet`, `DocPageManifestStore` | `doc_generator` (012) | Wiki rendering, shared by `index` and `serve`'s reindex pipeline. `generateRepositoryDocumentation`'s own output already includes feature 013's interactive dependency-diagram pages (013 was implemented as part of 012's rendering, not a separate pipeline step), so the single call this feature makes is sufficient — no separate diagram-generation call exists to make. |
| `RepositoryWatcher`, `ChangeBatch` | `repo_watcher` (017) | `serve`'s change-detection source. |
| `IncrementalReindexPipeline`, `ReindexOutcome` | `reindex_pipeline` (018) | `serve`'s watcher-triggered update logic. |
| `LocalLLMEngine`, `AvailabilityStatus` | `local_llm` (008) | LLM access + availability, shared by `index`/`serve`/`config`. |
| `EmbeddingEngine`, `EmbeddingAvailabilityStatus` | `embedding_engine` (009) | Embedding access + availability, shared by `index`/`serve`/`config`. |
| FastAPI app from `create_app` | `chat_api` (014) | The web server both `index` and `serve` start. |

`LocalModelAvailability`, the spec's own Key Entity, is **not** a new type —
it is `AvailabilityStatus` (008) and `EmbeddingAvailabilityStatus` (009),
already carrying `available`/`serviceReachable`/`modelInstalled`/`message`.
The CLI reads these directly rather than wrapping them in a third shape.

## CLIConfiguration

The developer's persisted choice of local models, read by `index`/`serve`
and written by `config` (spec's Key Entity of the same name).

| Field | Type | Notes |
|---|---|---|
| `llmModel` | `str` | Defaults to a documented constant (research.md §4) when no config file exists yet. |
| `llmEndpointUrl` | `str` | Defaults to `local_llm.models.DEFAULT_ENDPOINT_URL` (`http://localhost:11434`). |
| `embeddingModel` | `str` | Defaults to `embedding_engine.models.DEFAULT_MODEL_NAME` (`"nomic-embed-text"`). |
| `embeddingEndpointUrl` | `str` | Defaults to `embedding_engine.models.DEFAULT_ENDPOINT_URL` (`http://localhost:11434`). |

Storage: one JSON file at `~/.codepedia/config.json` (research.md §4).
Validation rules:
- All four fields are non-empty strings; endpoint URLs must pass
  `local_llm.models.normalize_endpoint_url`/
  `embedding_engine.models.normalize_endpoint_url` (already-enforced
  local-only validation, 008/009) before being saved.
- A missing config file is not an error — `load_config()` returns a
  `CLIConfiguration` built entirely from the defaults above.
- Saving a model name that is not among `listInstalledModels()`'s current
  result (research.md §5) is allowed; `config` reports it as a warning,
  not a validation failure (spec US3 acceptance criteria).

## RepositoryState (on-disk layout, not a Python type)

The per-repository directory `index` creates and `serve` reads, keyed by
`state_id = sha256(stable_repository_id(root)).hexdigest()[:16]`
(research.md §4):

| Path (under `~/.codepedia/repos/<state_id>/`) | Owner | Written by |
|---|---|---|
| `repository-metadata.sqlite` | `RepositoryMetadataStore` (005) | `index`, then `serve`'s reindex pipeline |
| `dependency-graph.sqlite` | `DependencyGraph.save`/`.load` (004) | `index`, then `serve`'s reindex pipeline |
| `vector-index.sqlite` + `vector-metadata.sqlite` | `VectorIndex` (006/007) | `index`, then `serve`'s reindex pipeline |
| `doc-manifest.sqlite` | `DocPageManifestStore` (012) | `index`, then `serve`'s reindex pipeline |
| `docs/` | `DocGenerator` `outputRoot` (012) | `index`, then `serve`'s reindex pipeline; served as static files by `chat_api.create_app` |

`serve` treats the **absence of `repository-metadata.sqlite`, or the
absence of a stored repository record inside it** (`RepositoryMetadataStore
.load_repository_record(root)` finding nothing), as "never indexed" — the
trigger for the spec's "no prior index" error (US2, FR "Server-start
command"). No separate marker file is introduced for this check.

## CLICommand (conceptual, spec's Key Entity)

Not a Python class — the four Typer commands themselves. Documented here
for traceability back to the spec, fully specified in
`contracts/cli-interface.md`:

| Command | Accepts | Triggers |
|---|---|---|
| `index` | repository path (default `.`), `--host`, `--port` | Full pipeline (research.md §6) + starts the web server. |
| `serve` | repository path (default `.`), `--host`, `--port` | `RepositoryWatcher` + `IncrementalReindexPipeline` (research.md §8) + starts the web server. |
| `config` | `--llm-model`, `--llm-endpoint`, `--embedding-model`, `--embedding-endpoint`, `--show` | Reads/writes `CLIConfiguration`. |
| `scan` | repository path | Unchanged passthrough to `repo_scanner.scanner.scan_repository` (research.md §3). |

## PipelineRun (in-memory only, spec's Key Entity)

Not persisted — the `index` command's own progress state while it runs,
printed to the terminal as each stage starts (spec FR: "MUST report which
stage is currently running").

| Field | Type | Notes |
|---|---|---|
| `stage` | `Stage` (enum) | One of `VALIDATING`, `CHECKING_MODELS`, `SCANNING`, `PARSING`, `BUILDING_GRAPH`, `GENERATING_DOCS_STRUCTURE`, `SUMMARIZING`, `GENERATING_DOCS_CONTENT`, `EMBEDDING`, `STARTING_SERVER` — two distinct documentation-generation stages, since research.md §6's pipeline runs `DocGenerator.generateRepositoryDocumentation` once *before* `SUMMARIZING` (structure pass) and once *after* (content pass), with `EMBEDDING` last, not immediately after `SUMMARIZING`. |
| `repositoryRoot` | `Path` | The repository being indexed. |
| `fileCount` | `int` | Set once scanning completes; used to report parse/embedding progress against a known total. |

State transitions: strictly linear, in the `Stage` order above (matching
research.md §6's fixed pipeline order and the "State flow: `index`" diagram
below) — `index` never revisits an earlier stage within one run.

## IndexRunResult (in-memory only)

Not persisted — the bundle `run_index`/`run_serve` return to their Typer
command caller (`cli.main`) so it can hand the right objects to
`start_local_server` without that caller needing to know the pipeline's
internal construction order.

| Field | Type | Notes |
|---|---|---|
| `docsRoot` | `Path` | `RepositoryState`'s `docs/` directory (research.md §4) — the directory `start_local_server` mounts as static files. |
| `vectorIndex` | `VectorIndex` | The (freshly built, `index`, or freshly loaded, `serve`) `VectorIndex` (006/007) instance `start_local_server` passes to `chat_api.create_app`. |
| `embeddingEngine` | `EmbeddingEngine` | The configured embedding engine (009), passed through to `chat_api.create_app` unchanged. |
| `llmEngine` | `LocalLLMEngine` | The configured LLM engine (008), passed through to `chat_api.create_app` unchanged. |
| `watcher` | `RepositoryWatcher \| None` | `None` for `run_index`'s result; the started `RepositoryWatcher` (017) for `run_serve`'s result, so `cli.main`'s `serve` command can call `.stop()` in its `finally` block (research.md §8). |

## Extension: `LocalLLMEngine.listInstalledModels` (008)

- **Input**: none (uses the engine's own `endpointUrl`).
- **Output**: `tuple[str, ...]` — installed model names, via the existing
  `LocalLLMTransport.list_models()` (`local_llm/transport.py:73`).
- **Contract addition**: used by `config` to show installed LLM models
  (research.md §5); raises nothing new — network/parse failures surface
  the same way `checkAvailability()` already reports them (empty tuple on
  an unreachable service, since `config` calls `checkAvailability()`
  first and only lists models when the service is reachable).

## Extension: `EmbeddingEngine.listInstalledModels` (009)

- **Input**: none.
- **Output**: `tuple[str, ...]` — installed model names, via a new
  `LocalEmbeddingTransport.list_models()` that factors the `/api/tags`
  call + name extraction already inlined in `availability()`
  (`embedding_engine/transport.py:94-111`) into its own method.
- **Contract addition**: used by `config` to show installed embedding
  models (research.md §5), mirroring the `LocalLLMEngine` extension above.

## State flow: `index`

```
CLI arg: repository path (default ".")
      │
      ▼
validate path exists and is a directory ──▶ [invalid] ──▶ RepositoryNotFoundError (exit 1)
      │
      ▼
load CLIConfiguration (defaults if none saved)
      │
      ▼
LocalLLMEngine.isAvailableLocally() + EmbeddingEngine.isAvailableLocally()
      │
      ├── [either false] ──▶ actionable error naming which one, and why
      │                      (service unreachable vs. model not installed) (exit 1)
      ▼
scan_repository(root)                                              (001)
      │
      ▼
per file: extract_symbols + store_inventory(content_hash=...)      (002/003, 005)
      │
      ▼
DependencyGraph.build_from_inventories(...).save(...)               (004)
      │
      ▼
DocGenerator.generateRepositoryDocumentation(incremental=False)     (012, pass 1)
      │
      ▼
CodeSummaryPipeline.summarizeRepository(incremental=False)          (010)
      │
      ▼
DocGenerator.generateRepositoryDocumentation(incremental=False)     (012, pass 2)
      │
      ▼
per file: update_embeddings(...)                                    (018 helper, 006/007/009)
      │
      ▼
chat_api.create_app(...) + print local URL + uvicorn.run(...)       (014/015, blocks)
```

## State flow: `serve`

```
CLI arg: repository path (default ".")
      │
      ▼
validate path exists and is a directory ──▶ [invalid] ──▶ RepositoryNotFoundError (exit 1)
      │
      ▼
load CLIConfiguration; check LLM + embedding availability ──▶ [unavailable] ──▶ actionable error (exit 1)
      │
      ▼
RepositoryMetadataStore.load_repository_record(root) ──▶ [not found] ──▶ "run `index` first" error (exit 1)
      │
      ▼
load DependencyGraph, VectorIndex, DocGenerator, CodeSummaryPipeline
      │
      ▼
IncrementalReindexPipeline(...)                                     (018)
      │
      ▼
RepositoryWatcher(..., on_batch=pipeline.run).start()                (017 — runs catch-up batch synchronously)
      │
      ▼
chat_api.create_app(...) + print local URL + uvicorn.run(...)       (014/015, blocks)
      │
      ▼ (on shutdown)
RepositoryWatcher.stop()
```

## State flow: `config`

```
CLI flags supplied? ──▶ [--show only, or no flags] ──▶ print current CLIConfiguration
      │                                                  (+ live availability of the
      │ [model flags given]                               configured models)
      ▼
validate endpoint URLs; save CLIConfiguration to ~/.codepedia/config.json
      │
      ▼
for each of the newly set llmModel/embeddingModel: check against
listInstalledModels() ──▶ [not found] ──▶ print warning (not a failure)
```

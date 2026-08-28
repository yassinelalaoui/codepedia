# Indexing Contract — Concurrency and Embedding Reuse Delta

## Purpose

Indexing was entirely sequential while being almost entirely network wait. On
this repository's own `src/` (127 files, 787 summarizable symbols) the
`SUMMARIZING` stage issued 787 blocking LLM calls one after another and
`EMBEDDING` 1 574 blocking embedding calls, each waiting out a full round trip
before the next began.

This feature changes three things about how those two stages execute. It
changes nothing about *what* they produce: the same symbols are summarized,
the same chunks are built with the same ids, and the same rows are written.

It depends on `provider-routing-backoff-delta.md`, which is not optional:
concurrent calls against one API key produce HTTP 429s, and without waiting
them out the failover chain would exhaust itself in seconds.

## 1. `CodeSummaryPipeline` — symbols summarized concurrently

`__init__` gains `maxWorkers: int = 4` (rejects values below 1). Every
`summarize*` method now dispatches its symbols to a
`ThreadPoolExecutor(max_workers=min(maxWorkers, len(pending)))`.

Preserved exactly:

- **Result order.** Futures are collected in submission order, so the returned
  `list[SummaryResult]` is ordered identically to the sequential pass.
- **Work selection.** The impacted-symbol computation is untouched.
- **Failure.** The first exception propagates to the caller, as before.
  `LocalLLMUnavailableError` still surfaces from `_ensure_ready` before any
  work is dispatched, so `reindex_pipeline`'s handler is unaffected.

Newly true, and the one observable difference:

- **Some calls may already be in flight when another fails.** Those may
  complete and persist their summary before the pool shuts down. This is
  harmless — a summary is idempotent per symbol, and the caller that aborts
  (`run_index`) discards the whole staging directory anyway.

### `SummaryProgressCallback` — changed meaning, unchanged signature

Still `(completed, total, symbol)`. It now fires when a symbol's summary has
**finished**, where it previously fired just before that symbol's call
started. Under a pool, "about to start" has no countable order; completion
does. The count is still gap-free `1..n`, each value delivered exactly once,
and the pipeline serializes the callback under its own lock — a callback needs
no lock of its own.

### Safety of the shared collaborators

Neither collaborator needed a change:

- `RepositoryMetadataStore` opens a connection per call. Its `connect` now
  sets `PRAGMA busy_timeout = 30000`, because every call also replays
  `ensure_schema` (DDL, which takes the write lock) and sqlite's 5s default is
  thin for a burst of writers. WAL is deliberately *not* enabled with it: WAL
  leaves `-wal`/`-shm` files beside the database, and `run_index` renames the
  whole state directory into place on Windows.
- `FailoverExecutor` carries mutable `providerUsed`/`attempts` attributes that
  concurrent calls do overwrite. The summarization path reads the provider
  from the `FailoverResult` it was handed, never from those attributes, so the
  race is unobservable here. `chat/session.py` does read `providerUsed`, and
  runs nowhere near these loops.

## 2. `cli/index_command.py` — files embedded concurrently

The `Stage.EMBEDDING` loop dispatches one `update_embeddings` per scanned file
to a `ThreadPoolExecutor`, sized by `CLIConfiguration.embeddingConcurrency`.
Each file is an independent unit: `update_embeddings` reads one file's symbols
and replaces exactly that file's chunks, so two workers never contend for the
same rows. `VectorIndex` already serialized its writes behind a reentrant lock
and held its connection with `check_same_thread=False`; nothing there changes.

Progress output is counted and printed under one lock, so `[7/9]` can never be
printed before `[6/9]`. The first failure propagates and aborts the run, as it
did when this was a plain loop.

Every stage now also prints what it cost (`Generating summaries finished in
812.4s`), so a change in indexing time is attributable to one stage rather
than visible only in the total.

## 3. Embedding reuse

### `EmbeddingCache` — new (`reindex_pipeline.embedding_cache`)

A thread-safe store of vectors already computed, consulted before any
embedding call. Two keys:

- **the chunk id** (`build_chunk_id`), which catches the same symbol
  re-embedded with unchanged content;
- **`(chunkType, normalized content)`**, which catches byte-identical bodies
  under *different* symbols. `build_chunk_id` seeds on `sourceSymbolId`, so it
  is blind to these by construction — two identical one-line functions in two
  modules have different chunk ids.

`normalize_chunk_content` is `vector_index.chunking`'s existing normalization,
promoted from `_normalize_content` to a public name so the content key matches
what the chunk id hashes.

**A vector is reused only when its `embeddingModelId` equals the expected
model.** A chunk id does not encode the model, so an id match alone is not
licence to reuse: two models produce vectors of different dimensionalities,
and mixing them into one index is precisely how `search` ends up returning
nothing. The expected model is the head of the embedding chain
(`expected_embedding_model_id`), mirroring the preference
`VectorIndex._embed_query_preferring_indexed_provider` already applies at
query time. Entries with an empty `embeddingModelId` — written before that
field existed — are never stored and never served.

### `update_embeddings` — new optional parameter

`embedding_cache: EmbeddingCache | None = None`. Omitted, behaviour is exactly
as before: every fragment is embedded for real. Supplied, the cache is
consulted before each call and fed after each real one.

A reused vector is stored with `embeddingModelId` set to the model that
produced it. `build_code_chunk` gains an `embedding_model_id` parameter for
this; without it a cached chunk would land with an empty model id and stop
matching the filter `search` applies by default — indexed but unfindable.

### Seeding from the previous index

`run_index` builds into a fresh `staging-<pid>` directory, so the vector index
is empty when `EMBEDDING` begins. An un-seeded cache would therefore hit
nothing on a full `index`, and would only ever help the watcher's incremental
path.

Before `EMBEDDING`, `run_index` therefore opens the *previous* successful
state's `vector-metadata.sqlite`, seeds the cache from its entries, and closes
it immediately — it is about to be replaced, and a lingering connection would
block that replace on Windows. A missing or unreadable prior index is not an
error; it yields an empty cache.

What this does and does not save on a full re-index of an unchanged
repository: `code` chunks hit, because a file's text is unchanged. `summary`
chunks generally miss, because their text embeds an LLM-generated summary that
a full run regenerates and which is not reproducible verbatim.

## 4. `CLIConfiguration` — two new fields

| Field | Default | Applies to |
|---|---|---|
| `summaryConcurrency` | 4 | `CodeSummaryPipeline.maxWorkers` in `index` and `serve` |
| `embeddingConcurrency` | 8 | the `Stage.EMBEDDING` pool |

Both must be integers of at least 1; `save_config` rejects anything else
before writing. Absent from `config.json`, both fall back to their defaults,
so an existing configuration file keeps working untouched.

The two numbers differ because the ceiling is the provider's rate limit on one
API key, not local CPU: summarization talks to Groq, whose free tier limits
requests per minute tightly, while embeddings talk to OpenAI, which is far
more permissive per key.

Both are deliberately **excluded** from `disclosure_signature`. That signature
exists to re-show the constitution 2.1 disclosure whenever the set of
providers that may see the user's code changes. A concurrency number changes
no such thing, and making it re-prompt would train the user to dismiss the
disclosure.

## 5. `GroqLLMEngine` — availability probe cached

`generateStream` pre-flighted `GET /models` before every `generate`, so
summarizing a repository cost two HTTP round trips per symbol — one of them
pure overhead, and one more request counted against the very rate limit it was
checking for.

`checkAvailability` now caches an **available** verdict for 60 seconds
(`availabilityTtlSeconds`, per instance, under a lock since the pool shares
one engine). An unavailable verdict is never cached, and a failing
`generate_stream` invalidates the cache, so recovery — or a key revoked
mid-run — is noticed on the next call rather than up to a TTL later.

`OpenAIEmbeddingProvider.embed` never had this pre-flight and is unchanged.

## 6. `vector_index` — an index is now found by repository, not by path

Not a concurrency change, but a prerequisite discovered while measuring this
one: the embedding cache reported zero reuse on a re-index even though the
previous run's chunks were sitting in the file.

`stable_index_id` derives an index id from the repository root **and** the
metadata file's path. `run_index` always builds into
`<state>.staging-<pid>/` and renames that directory into place on success, so
the id changed the instant an index was published. The chunks stayed in the
file under the staging-derived id, while opening the same file at its final
path minted a second, empty `indexes` row and reported zero chunks.

That affected far more than the cache: the `VectorIndex` `run_index` hands to
the server, and the one `run_serve` opens, both use the final path. Every
indexed repository therefore served an index that appeared empty, so chat
retrieval had nothing to retrieve.

`ensure_index_record` now looks for an existing row whose `repository_root`
matches before deriving a new id, and adopts it. One metadata file only ever
holds one repository's index, so an existing row for that repository *is* this
index, whatever path it was built under. Two different repositories sharing
one metadata file still get separate ids. Indexes already written in the
orphaned state are adopted on next open rather than needing a re-index.

Regression coverage: `tests/unit/test_vector_index.py` -
`test_an_index_survives_the_directory_rename_that_publishes_it` and
`test_two_repositories_in_one_metadata_file_keep_separate_indexes`.

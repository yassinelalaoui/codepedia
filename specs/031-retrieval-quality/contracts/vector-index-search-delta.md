# Vector Index Contract — Hybrid Search Delta

## Purpose

This feature changes how `VectorIndex.search` ranks results, relative to
`specs/007-local-vector-index/contracts/vector-index-interface.md`. It changes
nothing else — `addChunk`, `addChunks`, `removeChunksForFile`, `reindexFile`,
`save`, `close`, the `CodeChunk`/`VectorEntry`/`SearchResult` shapes, and the
`embeddingModelId` filtering and dimensionality-exclusion rules from 029 are all
unaffected and unchanged.

The method signature is unchanged: `search(query: str, k: int)` positionally, or
a `SearchQuery`, optionally with `filters`. Several test doubles implement that
exact shape, and callers see no difference in the call.

## What changed

Ranking was a single cosine ordering. It is now the fusion of two rankings:

1. **Vector** — cosine similarity, as before.
2. **Lexical** — SQLite FTS5 BM25 over chunk content.

Both sides are sampled to `k * VectorIndex.HYBRID_OVERSAMPLE` (4) before fusion,
then truncated to `k`. Over-sampling happens **inside** the index, so the chat
layer still asks for exactly `k` and its call shape is untouched.

Fusion is Reciprocal Rank Fusion with the standard damping constant of 60. Ties
break on chunk id, preserving the determinism 007 guarantees.

## `SearchResult.score` is unchanged in meaning

**Fusion sets the order. It never sets the score.**

`score` remains the raw cosine similarity: higher is better, range ~[-1, 1].
This is load-bearing, not incidental. `chat/retrieval.py` compares it against
absolute thresholds — below `0.15` means "not enough evidence", within `0.05` of
the top means "ambiguous" — and an RRF score, which is ~0.016 at rank 1, would
fire both banners on every single answer.

A result found only by the lexical side has no cosine from the ranking pass, so
one is computed on demand from its stored vector and the query vector. It must
clear the same filter and dimensionality gates the vector side applies; if it
cannot, it is discarded rather than surfaced unscored.

## Failure and absence

| Situation | Behavior |
|---|---|
| FTS5 table missing, or SQLite built without FTS5 | Lexical side returns nothing; search degrades to pure vector ranking. Never raises. |
| Query contains FTS5 operators (quotes, parens, hyphens) | Tokenized and quoted into a safe MATCH expression. Worst case is no lexical match, never an `OperationalError` mid-question. |
| Query has no word characters at all | No lexical side; pure vector ranking. |
| Index empty | `[]`, before any embedding or SQL work — the existing fast-path is unchanged. |

## Schema delta

A standalone FTS5 virtual table `chunks_fts(content, chunk_id UNINDEXED,
index_id UNINDEXED)`, synchronized at the only two write points, `upsert_chunk`
and `delete_chunks_for_file`.

Standalone rather than external-content: `chunks.id` is TEXT, while
external-content FTS5 requires an INTEGER rowid that survives a `VACUUM`.
Duplicating `content` costs disk and buys independent correctness.

Creation and backfill follow the project's only migration precedent —
`_ensure_chunks_embedding_model_id_column` and
`specs/029-provider-fallback-chains/contracts/sqlite-schema-deltas.md`: additive,
idempotent, introspection-guarded, invoked from `ensure_schema()` on every
`connect()`. There is still no schema-version column. Backfill for a database
indexed before this table existed runs once, guarded by an empty-table check, so
reopening a populated index on `serve` does not repeat it.

## Threading delta

`storage.connect` now opens with `check_same_thread=False`, and `VectorIndex`
serializes every connection touch behind a `threading.RLock` (reentrant, because
`reindexFile` nests into `removeChunksForFile` and `_store_entry` into
`_persist_record`).

This fixes a pre-existing defect rather than only enabling the above: `serve`
opens the index on the main thread but writes from the watcher's debounce timer
thread, so every incremental batch raised `sqlite3.ProgrammingError`, swallowed
into the watcher's `on_error`. Search became SQL-touching in this feature, which
would have extended the same fault to the chat path.

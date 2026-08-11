# Research: Local Vector Index

## Decision 1: FAISS as the similarity backend

Decision: Use FAISS for local vector similarity search.

Rationale: The feature needs fast top-k semantic retrieval in an embedded,
file-based setup. FAISS is a natural fit for local similarity search and keeps
the retrieval path focused on ranking rather than on server management.

Alternatives considered: Chroma embedded mode was considered because it can
persist locally and carries metadata, but FAISS offers a simpler retrieval core
for this repository's library-style architecture.

## Decision 2: Separate persistent metadata alongside the vector index

Decision: Store vector metadata separately from the similarity index payload.

Rationale: The index must support file-scoped deletion, incremental additions,
and source-symbol attribution. A sidecar metadata store makes it easier to
rebuild or compact the vector index while preserving searchable identity and
ownership data.

Alternatives considered: Packing all metadata into the vector engine alone was
rejected because it makes selective file updates and attribution queries harder
to manage.

## Decision 3: CodeChunk as the atomic searchable unit

Decision: Represent each searchable item as a `CodeChunk`.

Rationale: The feature needs a durable unit that can carry the chunk text, its
embedding, and the originating symbol identity. A single chunk abstraction also
keeps code and generated-summary fragments aligned in one search model.

Alternatives considered: Storing only whole files was rejected because the
feature needs fragment-level recall. Storing only symbols was rejected because
generated summaries must also be searchable.

## Decision 4: File-scoped replace/remove workflow

Decision: Treat the source file as the unit for replacing or removing vectors.

Rationale: The spec requires removing vectors for changed or deleted files
without rebuilding the entire index. File-scoped lifecycle operations are the
most direct way to keep the persisted index accurate and incremental.

Alternatives considered: Global rebuild after every change was rejected because
it conflicts with the incremental-update requirement and would harm interactive
search responsiveness.

## Decision 5: Ranked similarity search with source attribution

Decision: Return top-k results with a score and source symbol identifier for
each match.

Rationale: The primary user value is getting relevant fragments fast enough for
chat-style use while still knowing which symbol produced each fragment. The
result shape must support both retrieval and traceability.

Alternatives considered: Returning only embeddings or only raw fragments was
rejected because the user needs actionable context, not just vector matches.

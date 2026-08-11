# Feature Specification: Local Embedding Engine

## Overview

Build a local embedding engine that transforms a code fragment or a natural
language text, such as a generated summary, into a numeric vector. The engine
must operate entirely on the local machine and must not rely on any external
API or remote service.

The same embedding capability is used in two product flows:

- vectorizing code fragments during indexing
- vectorizing a user question or search query during semantic search and
  retrieval

If the local embedding model is not available, not started, or cannot be
reached, the system must report that situation explicitly instead of failing
silently or attempting any remote fallback.

## Goals

- Provide a single local-only text-to-vector capability for the product.
- Support both code-oriented text and natural-language text.
- Make the embedding step reusable for indexing and interactive search.
- Fail fast and clearly when the local embedding model is unavailable.
- Ensure the embedding workflow remains fully offline.

## Non-Goals

- Training or fine-tuning embedding models.
- Selecting or bundling a specific embedding model.
- Building the full vector store or similarity search logic.
- Implementing cloud-based embedding fallback.
- Translating embeddings into user-facing explanations or summaries.

## User Stories

### US1 - Embed code fragments locally

As a user, I want the tool to convert a code fragment into a vector so that
code content can be indexed and compared locally.

Acceptance criteria:

- A code fragment can be converted into a numeric vector.
- The output is suitable for similarity comparison with other code fragments.
- The operation does not require any external service.

### US2 - Embed search queries locally

As a user, I want my search question to be converted into a vector so that the
tool can find relevant code fragments using semantic similarity during search.

Acceptance criteria:

- A text query can be converted into a numeric vector.
- The same embedding capability is used for search and indexing.
- The operation remains local and offline.

### US3 - Detect missing local embedding availability

As a user, I want the tool to tell me clearly when the local embedding model is
not available so that I know I must start or install it before continuing.

Acceptance criteria:

- The engine exposes an explicit availability check.
- If the local model is unavailable, the check fails clearly.
- No silent fallback to a remote service is allowed.

## Functional Requirements

### Embedding generation

- The engine must accept a single text input and return a numeric vector.
- The engine must support both code fragments and natural-language text.
- The engine must produce outputs that can be compared using semantic
  similarity.
- The same text under the same local model state must produce a consistent
  embedding result.

### Reuse across product flows

- The same embedding capability must be usable when indexing code fragments.
- The same embedding capability must be usable when embedding a user query at
  retrieval time.
- The interface must remain simple enough to be called from both automated and
  interactive workflows.

### Availability and failure handling

- The system must expose a direct way to verify that the local embedding model
  is available before attempting generation.
- If the model is missing, stopped, or unreachable, the system must return an
  explicit error.
- The error message must guide the user toward starting or installing the local
  embedding model.
- The system must not silently switch to any remote or cloud provider.

### Offline operation

- The embedding workflow must operate without contacting any external service.
- The system must not depend on internet access for normal embedding use.
- The offline failure mode must be obvious to the user.

## Edge Cases

- Empty or whitespace-only text should be handled deterministically and should
  not produce ambiguous behavior.
- Very short fragments, such as a single identifier or import path, should still
  be embeddable.
- Different text types, such as code and prose, should be supported through the
  same public embedding capability.

## Assumptions

- The product already has a local retrieval flow that needs query vectorization.
- The embedding model is expected to run on the user's machine.
- The caller is responsible for deciding when to embed code fragments versus
  user queries.
- Exact model selection and deployment details are handled outside this
  specification.

## Success Criteria

- Two semantically close code fragments produce vectors that are more similar
  to each other than either fragment is to an unrelated fragment.
- A user query can be embedded locally and used for retrieval without any
  external network dependency.
- When the local embedding model is unavailable, the system reports the problem
  before attempting to generate a vector.
- No outbound network request is emitted during normal embedding operations.

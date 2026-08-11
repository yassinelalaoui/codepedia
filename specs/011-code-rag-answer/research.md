# Research: Local Code RAG Answering

## Decision 1: Reuse `EmbeddingEngine` for question vectorization

Decision: Convert each natural-language question into a vector using the
existing local embedding engine.

Rationale: The feature must remain local and should query the same semantic
space as the indexed code fragments. Reusing the existing embedding layer keeps
question encoding aligned with how the codebase was indexed.

Alternatives considered: String matching or keyword-only search was rejected
because it would not satisfy the semantic retrieval goal.

## Decision 2: Reuse `VectorIndex.search` for evidence retrieval

Decision: Retrieve evidence with the existing local vector index search API.

Rationale: The index already stores chunk content, similarity scores, source
symbol ids, and source file paths, which are the core ingredients needed for
grounded answers and citations.

Alternatives considered: Building a separate retrieval layer on top of raw
SQLite storage was rejected because it would duplicate ranking logic already
present in the index.

## Decision 3: Assemble prompts from ranked local evidence

Decision: Build the final LLM prompt from the top-ranked fragments and, when
available, supporting summaries from the same local repository data.

Rationale: A focused prompt keeps the generation step grounded and avoids
overloading the model with unrelated repository content.

Alternatives considered: Sending the entire repository context was rejected
because it would be noisy, slower, and harder to cite accurately.

## Decision 4: Keep session state in memory

Decision: Model `ChatSession` as an in-memory ordered conversation history that
stores user and assistant messages for the current session.

Rationale: The feature spec requires a session object and a question-answer
method, but not durable chat storage. Keeping the session state in memory keeps
the design simple and local.

Alternatives considered: Persistent chat history storage was considered, but it
adds scope without being required by the user stories.

## Decision 5: Use explicit citation ids in the answer payload

Decision: Store the evidence symbol ids used to justify the response in
`ChatMessage.citedSymbolIds` and include file references in the message text.

Rationale: The spec requires explicit citations to files and symbols. A message
payload that preserves the evidence ids makes the answer auditable and easy to
render in a UI.

Alternatives considered: A free-form citation string alone was rejected because
it would be harder to validate and to map back to the retrieval results.

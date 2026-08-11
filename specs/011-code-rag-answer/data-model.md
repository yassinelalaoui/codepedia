# Data Model: Local Code RAG Answering

## ChatSession

Represents one local question-answering conversation over the indexed
repository.

Fields:
- `id`
- `messages`

Methods:
- `ask(question): ChatMessage`

Relationships:
- Uses `EmbeddingEngine` to vectorize the question
- Uses `VectorIndex` to retrieve relevant code fragments and summaries
- Uses `LocalLLMEngine` to generate the final answer

Validation:
- `id` must be non-empty
- `messages` must preserve chronological order
- `ask(question)` must append the user turn and the generated assistant turn to
  the session history
- A session must not answer without first retrieving local evidence

## ChatMessage

Represents one message in a chat session, including the generated answer and
its citations.

Fields:
- `role`
- `content`
- `citedSymbolIds`
- `citedFilePaths`
- `timestamp`

Relationships:
- Stored inside `ChatSession.messages`
- Returned from `ChatSession.ask(question)`

Validation:
- `role` must be a recognized chat role such as `user` or `assistant`
- `content` must not be empty for assistant answers
- `citedSymbolIds` must contain the evidence symbol ids used for a grounded
  answer, when evidence exists
- `citedFilePaths` must contain the file paths used to justify the answer when
  file-level evidence exists
- `timestamp` must identify when the message was created

## RetrievedEvidence

Represents the local fragments selected from the vector index for a question.

Fields:
- `chunkId`
- `content`
- `score`
- `sourceSymbolId`
- `sourceFilePath`
- `chunkType`

Relationships:
- Produced by the local retrieval step
- Consumed by prompt assembly

Validation:
- Evidence entries must come from the local index
- Scores must preserve the ranking order used for answer context

## RAGContext

Represents the assembled prompt context sent to the local LLM.

Fields:
- `question`
- `conversationHistory`
- `retrievedEvidence`
- `citationMap`

Relationships:
- Built from the current session state and local retrieval results
- Consumed by `LocalLLMEngine`

Validation:
- The question must be included verbatim
- The context must only include locally retrieved evidence
- The citation map must preserve the file and symbol identities used in the
  final answer

## Citation

Represents a traceable reference to a repository file or symbol.

Fields:
- `symbolId`
- `filePath`
- `chunkId`

Relationships:
- Derived from `RetrievedEvidence`
- Referenced by `ChatMessage.citedSymbolIds`

Validation:
- Citations must point to evidence that was actually retrieved
- A citation must never reference external or synthetic repository content

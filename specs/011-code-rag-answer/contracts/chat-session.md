# Chat Session Contract

## Purpose

Define the local question-answering interface used to ask questions about the
indexed repository and receive grounded, cited answers.

## Core types

### `ChatSession`

Fields:

- `id`
- `messages`

Required method:

- `ask(question): ChatMessage`

Expected behavior:

- Vectorizes the question with the local embedding engine
- Retrieves the most relevant local evidence from the vector index
- Builds a prompt from the retrieved evidence
- Uses the local LLM to generate a natural-language answer
- Appends the user message and assistant message to session history
- Returns the assistant `ChatMessage`

### `ChatMessage`

Fields:

- `role`
- `content`
- `citedSymbolIds`
- `timestamp`

Expected behavior:

- Stores the content of a user or assistant turn
- Preserves the symbol ids that justify an assistant answer
- Remains serializable for later rendering or inspection

## Retrieval expectations

- The pipeline must use local evidence already present in the vector index
- Retrieval results must include the source file path and source symbol id
- Retrieved evidence should be ranked by relevance to the question

## Generation expectations

- The prompt must be assembled only from local repository data
- The local LLM must be checked for availability before any generation begins
- If the embedding engine or local LLM is unavailable, the session must fail
  explicitly and locally

## Citation expectations

- A valid answer must cite the files and symbols that support it
- `citedSymbolIds` and the cited file paths must reflect the evidence used for
  the answer
- Citations must be traceable back to the retrieved evidence without external
  lookup

## Failure expectations

- The session must not silently fall back to a cloud service
- The session must not return an answer that is detached from the retrieved
  local evidence
- When insufficient evidence exists, the session should say so explicitly and
  still surface the nearest relevant local evidence

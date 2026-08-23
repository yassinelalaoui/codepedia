# Major Function: Ask a Question (Chat / RAG)

**Specs**: 011, 014, 025

A user asks a natural-language question and gets back an answer grounded in the
actual codebase, with clickable citations — never an unsourced or hallucinated claim.
The exchange is persisted as it happens (025), so it survives a server restart or a
wiki page reload — see `01-full-indexing.md`'s storage note and
`docs/architecture.md`'s "Storage architecture" for where `chat_sessions`/
`chat_messages` live.

```mermaid
sequenceDiagram
    actor Reader as "Team member (browser)"
    participant ChatApiApp as "Chat API (014)"
    participant ChatSession as "Chat / RAG Session (011)"
    participant VectorIndex as "Vector Index (006/007)"
    participant LocalLLMEngine as "Local LLM (008)"
    participant ChatStore as "Chat Persistence (025)"

    Reader->>ChatApiApp: POST /sessions
    ChatApiApp->>ChatStore: create_session(id)
    ChatApiApp-->>Reader: sessionId

    Reader->>ChatApiApp: POST /sessions/{session_id}/messages { question }
    ChatApiApp->>ChatSession: ask(question)
    ChatSession->>ChatSession: ensure local embedding + LLM are available
    alt either is unavailable
        ChatSession-->>ChatApiApp: raise LocalDependencyUnavailableError
        ChatApiApp-->>Reader: clear error (no cloud fallback)
    else both available
        ChatSession->>VectorIndex: search(question, k)
        VectorIndex-->>ChatSession: top-k similar chunks
        alt no relevant evidence found
            ChatSession-->>ChatApiApp: "insufficient evidence" answer, no citations
        else evidence found
            ChatSession->>ChatSession: build RAGContext (question + history + evidence)
            ChatSession->>LocalLLMEngine: generate(promptEnvelope)
            LocalLLMEngine-->>ChatSession: raw answer text
            ChatSession->>ChatSession: render answer + attach citations\n(cited symbol ids + file paths)
        end
        ChatSession->>ChatStore: append_message(question), append_message(answer)
        ChatSession-->>ChatApiApp: ChatMessage
        ChatApiApp-->>Reader: AskQuestionResponse (answer, citedSymbolIds, citedFilePaths)
        Reader->>Reader: render answer, each citation resolved\nto a clickable wiki page link
    end

    Reader->>ChatApiApp: (restart, or page reload) GET /sessions/{session_id}/messages
    ChatApiApp->>ChatStore: load_session(id) + load_messages(id)
    ChatStore-->>ChatApiApp: full history, in order
    ChatApiApp-->>Reader: SessionHistoryResponse
```

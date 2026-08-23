# Major Function: Ask a Question (Chat / RAG)

**Specs**: 011, 014, 025, 026

A user asks a natural-language question and gets back an answer grounded in the
actual codebase, with clickable citations — never an unsourced or hallucinated claim.
The answer streams back fragment by fragment as it's generated (026), rather than
arriving as one block once generation finishes, and a follow-up question's search is
enriched with recent conversation context (026, local text/citation concatenation
only — no LLM call for this step). The exchange is persisted once, at completion
(025), so it survives a server restart or a wiki page reload — see
`01-full-indexing.md`'s storage note and `docs/architecture.md`'s "Storage
architecture" for where `chat_sessions`/`chat_messages` live.

```mermaid
sequenceDiagram
    actor Reader as "Team member (browser)"
    participant ChatApiApp as "Chat API (014/026)"
    participant ChatSession as "Chat / RAG Session (011/026)"
    participant VectorIndex as "Vector Index (006/007)"
    participant LLMEngine as "LLMEngine: local (008) or\nexplicitly-configured remote (026)"
    participant ChatStore as "Chat Persistence (025)"

    Reader->>ChatApiApp: POST /sessions
    ChatApiApp->>ChatStore: create_session(id)
    ChatApiApp-->>Reader: sessionId

    Reader->>ChatApiApp: POST /sessions/{session_id}/messages { question }
    ChatApiApp->>ChatSession: ensure embedding + configured LLM engine are available
    alt either is unavailable
        ChatApiApp-->>Reader: 503, clear error (no automatic switch to another engine)
    else both available
        ChatApiApp->>ChatSession: askStream(question)
        ChatSession->>ChatStore: append_message(question) — persisted immediately
        ChatSession->>ChatSession: build enriched query from question +\nrecent history (local only, no LLM call)
        ChatSession->>VectorIndex: search(enrichedQuery, k)
        VectorIndex-->>ChatSession: top-k similar chunks
        alt no relevant evidence found
            ChatSession-->>ChatApiApp: "insufficient evidence" answer (single fragment), no citations
        else evidence found
            ChatSession->>ChatSession: build RAGContext (question + history + evidence)
            loop as the answer is generated
                ChatSession->>LLMEngine: generateStream(promptEnvelope)
                LLMEngine-->>ChatSession: next fragment
                ChatSession-->>ChatApiApp: fragment
                ChatApiApp-->>Reader: SSE "data: {fragment}"
            end
            ChatSession->>ChatSession: assemble full answer + attach citations\n(cited symbol ids + file paths)
        end
        ChatSession->>ChatStore: append_message(answer) — persisted once, at completion
        ChatSession-->>ChatApiApp: final ChatMessage
        ChatApiApp-->>Reader: SSE "event: done" (answer, citedSymbolIds, citedFilePaths)
        Reader->>Reader: render the streamed answer, each citation resolved\nto a clickable wiki page link
    end

    Reader->>ChatApiApp: (restart, or page reload) GET /sessions/{session_id}/messages
    ChatApiApp->>ChatStore: load_session(id) + load_messages(id)
    ChatStore-->>ChatApiApp: full history, in order
    ChatApiApp-->>Reader: SessionHistoryResponse
```

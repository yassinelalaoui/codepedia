# Major Function: Ask a Question (Chat / RAG)

**Specs**: 011, 014

A user asks a natural-language question and gets back an answer grounded in the
actual codebase, with clickable citations — never an unsourced or hallucinated claim.

```mermaid
sequenceDiagram
    actor Reader as "Team member (browser)"
    participant ChatApiApp as "Chat API (014)"
    participant ChatSession as "Chat / RAG Session (011)"
    participant VectorIndex as "Vector Index (006/007)"
    participant LocalLLMEngine as "Local LLM (008)"

    Reader->>ChatApiApp: POST /sessions
    ChatApiApp-->>Reader: sessionId

    Reader->>ChatApiApp: POST /sessions/{id}/messages { question }
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
        ChatSession-->>ChatApiApp: ChatMessage
        ChatApiApp-->>Reader: AskQuestionResponse (answer, citedSymbolIds, citedFilePaths)
        Reader->>Reader: render answer; each citation resolved\nto a clickable wiki page link
    end
```

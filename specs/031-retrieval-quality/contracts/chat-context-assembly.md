# Contract: Chat Context Assembly

**Status**: New contract covering two additions to the answer path — graph-based
reranking and an explicit prompt budget. The chat API surface
(`specs/014-local-chat-api/contracts/chat-api.md` and its later deltas) is
unaffected: no endpoint, request or response shape changes.

## Ordering within `askStream`

The order of these steps is contractual, not incidental:

1. `retrieve_evidence(...)` — evidence in similarity order.
2. `is_insufficient_evidence` / `detect_ambiguous_evidence` — computed **here**,
   while the list is still ordered by score.
3. `rerank_by_graph_proximity(...)` — reorders for the prompt and citations.
4. `build_prompt_envelope(...)` — applies the budget.

Step 2 must precede step 3. Both banners read `evidence[0].score` against
absolute thresholds, so reranking first would let a graph-adjacent but
lower-scoring chunk trip the "not enough evidence" banner on an otherwise good
answer — the same hazard the hybrid-search delta avoids by keeping `score` raw.

## Reranking by dependency-graph proximity

A candidate is promoted when its symbol is a **direct** neighbour — caller,
callee, or inheritance relation, in either direction — of a symbol cited by one
of the last three assistant turns.

Reranking is a **stable partition**: adjacent candidates move ahead, relative
order is otherwise preserved, and `score` is never modified. Only the retrieved
candidates are considered; the index is never rescanned.

### Resolution rules

| Symbol kind | Resolution |
|---|---|
| Class, function, method | The parser's symbol id **is** the graph node id. Direct lookup. |
| Module | No node exists at the module symbol id. The graph stores a module as a `file::<path>` node carrying `metadata["moduleId"]`, and resolution goes through a `{moduleId: node.id}` index built once per rerank. |

Going through `moduleId` rather than the file path is deliberate: chunks carry a
repository-relative path while graph nodes are built from absolute ones, so a
path-based match would silently fail. Every indexed file produces a module chunk,
so that failure would affect a large share of candidates.

Nodes prefixed `unresolved::` or `file::external::` are synthesized by the graph
for calls and imports it could not resolve. They have no indexed chunk and never
contribute adjacency.

### Absence is not an error

`dependencies`/`dependents` fail open, returning `[]` for an unknown id. Combined
with an optional graph, this means reranking silently does nothing when: no
graph is configured, the conversation has no prior citations, nothing among the
candidates is adjacent, or every candidate is. In all of those the evidence tuple
is returned unchanged.

### Locality

Reranking makes **no network calls and no model calls**. It reads an in-memory
graph loaded from the local snapshot. `tests/unit/test_chat_retrieval.py`
neutralizes `httpx` and fails if retrieval touches the network; reranking runs
inside that boundary and is separately asserted against it.

### Wiring

`ChatSession.dependencyGraph` is optional and defaults to `None`. Like
`vectorIndex`, `embeddingEngine` and `llmEngine`, it is a **runtime collaborator,
not persisted state**: `chat/sqlite_store.py` reconstructs a session from stored
metadata only (id, timestamps, messages) and deliberately attaches none of them.

It must therefore be supplied in three places: `SessionRegistry.__init__`,
`create_session`, and the `get_session` rehydration path that rebuilds a session
after a restart. That last one is the one that fails silently — a resumed
conversation would keep answering normally, just without reranking, and no test
that only exercises a freshly created session would notice.

## Prompt budget

`build_prompt_envelope` trims the assembled context to a token budget
(`DEFAULT_CONTEXT_TOKEN_BUDGET`, 8000, covering the context sections only).

Applied here, never on `PromptEnvelope`: that type is frozen and shared with
`repository_metadata/summary_prompts.py` and `doc_generator/section_narrator.py`,
so budgeting there would silently reshape wiki generation.

### Estimation

Token counts are **approximated** at `CHARS_PER_TOKEN = 3.0`, deliberately below
the ~4.0 typical of English prose because code, paths and symbol ids tokenize
denser. The estimate therefore over-counts and errs toward sending less than the
budget.

Exact counting is not achievable: the default chat chain is Groq's
`openai/gpt-oss-20b` and the full-local alternative is an Ollama model with a
different tokenizer. Neither is available offline, and a dependency matching one
would be wrong for the other. This mirrors the posture already taken by
`retrieval.py`'s README cap ("a generous cap, not a token-accurate budget").

### Order of sacrifice

| Order | What | Rule |
|---|---|---|
| 1 | Conversation history | Oldest messages dropped first. The fastest-growing part — every prior assistant answer is replayed in full. |
| 2 | README | Truncated with a visible marker. Background context, not the answer's evidence. |
| 3 | Evidence bodies | Shortened worst-ranked first. The top-ranked chunk always keeps some content. |

The current question is never trimmed — it is `promptText`, not a context
section.

**Evidence is truncated, never dropped.** `chat/session.py` derives the persisted
`citedSymbolIds`/`citedFilePaths` from this same tuple, so removing an entry
would leave the answer citing a source the model was never shown — a violation of
constitution §2.4 (traçabilité). Truncating keeps every citation honest: the
chunk was shown, if only in part.

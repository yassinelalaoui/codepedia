# Quickstart: Chat Streaming & Conversational Context Retrieval

## Prerequisites

- A repository already indexed and served (`codepedia serve /path/to/repo`),
  with a local embedding engine and local LLM reachable on `localhost`.
- `curl` with `--no-buffer` (or an equivalent client that doesn't wait for
  the connection to close before showing output) to observe SSE events as
  they arrive rather than all at once.
- For the remote-engine scenarios only: a Groq API key exported as
  `GROQ_API_KEY`, and network access to `api.groq.com`.

This validates spec.md's User Stories 1-3 and Success Criteria SC-001-005.

## Validate: streamed answer delivery (US1 / SC-002 / SC-003)

1. Create a session and ask a question, watching the stream arrive
   incrementally:

   ```sh
   SESSION_ID=$(curl -s -X POST http://127.0.0.1:8000/sessions | jq -r .sessionId)
   curl -s -N -X POST http://127.0.0.1:8000/sessions/$SESSION_ID/messages \
     -H "Content-Type: application/json" \
     -d '{"question": "where is authentication handled?"}'
   ```

2. Confirm you see multiple `data: {"fragment": ...}` lines arrive one at a
   time (not all at once), followed by one `event: done` line whose `answer`
   field, when you concatenate every fragment's text in order, matches
   exactly.
3. Time the delay to the *first* `fragment` event for a short question
   versus a question you know produces a long answer. Confirm the two
   delays are comparable (SC-002) — unlike before this feature, where the
   delay to see anything at all scaled with the full answer's length.
4. Confirm the `done` event's `citedSymbolIds`/`citedFilePaths` match real
   locations in the indexed repository, same as before this feature
   (FR-004).

## Validate: follow-up questions retrieve the right evidence (US2 / SC-001)

1. Ask an initial question that surfaces a known symbol/file:

   ```sh
   curl -s -N -X POST http://127.0.0.1:8000/sessions/$SESSION_ID/messages \
     -H "Content-Type: application/json" \
     -d '{"question": "where is authentication handled?"}'
   ```

2. Ask a deliberately elliptical follow-up in the **same** session:

   ```sh
   curl -s -N -X POST http://127.0.0.1:8000/sessions/$SESSION_ID/messages \
     -H "Content-Type: application/json" \
     -d '{"question": "and what about the fallback path?"}'
   ```

3. Confirm the follow-up's `citedSymbolIds`/`citedFilePaths` are relevant to
   what the *first* answer actually discussed (e.g. an OAuth fallback the
   first answer mentioned), not unrelated/generic results.
4. Repeat with a brand-new session (`POST /sessions` again) and confirm the
   very first question in it retrieves exactly as it did before this
   feature — no enrichment applied (SC-004).

## Validate: opting into a remote engine (US3 / SC-005)

1. With no remote engine configured, confirm chat behaves exactly as in the
   two sections above — this is the default for every operator who does
   nothing.
2. Configure Groq explicitly:

   ```sh
   export GROQ_API_KEY=...
   codepedia config --llm-provider groq --remote-llm-model llama-3.3-70b-versatile
   ```

3. Confirm the command prints an explicit disclosure that questions and
   cited code context will be sent to Groq before it saves.
4. Restart the server (`codepedia serve`) and ask a question. Confirm
   the answer now streams from the configured Groq model (same SSE shape
   as the local case — streaming is engine-agnostic).
5. Unset `GROQ_API_KEY` (or otherwise make the endpoint unreachable) and ask
   another question. Confirm the response is a clear "unavailable" error —
   never a silent switch back to the local model.
6. Revert with `codepedia config --llm-provider local` and confirm chat
   returns to local-only behavior with no remaining Groq usage.

## Automated coverage

These scenarios are exercised directly by the feature's tests (see
plan.md's Project Structure): `tests/unit/test_local_llm.py` and a new
`tests/unit/test_groq_llm_engine.py` cover `generateStream`/`generate`
against fake async transports; `tests/unit/test_chat_retrieval.py` covers
`build_enriched_query`/`retrieve_evidence` deterministically (no real model
calls needed, since enrichment is pure local text/citation concatenation);
`tests/integration/test_chat_session.py` and `tests/integration/test_chat_api.py`
cover the end-to-end streamed/enriched flow with fake engines, including the
SSE contract and the mid-stream-failure no-history-side-effect case (FR-011).

# Quickstart: Validating Chat Interface Polish

Prerequisites: the local server (spec 015) running against an already
indexed repository, so the chat API (spec 014/025/026/027) and generated
wiki pages (spec 016) are both reachable; a chat-capable engine configured
(constitution 2.1) so `POST /sessions/{id}/messages` can actually generate
an answer rather than reporting `local_dependency_unavailable`.

```bash
# from repo root, after building the frontend bundle
cd frontend && npm install && npm run build
# start the local server per the project's existing CLI/run instructions
```

Open the generated wiki's home page in a browser at `http://127.0.0.1:<port>/`.

## Scenario 1 — Immediate activity feedback, then progressive answer (User Story 1)

1. Type any question about the indexed repository into the chat input and
   submit it.
2. **Expect**: a visible "working" indicator appears immediately — well
   under a second, with no perceptible delay (SC-001) — replacing nothing
   yet since no answer content exists.
3. **Expect**: as soon as the first fragment of the answer is generated, the
   indicator is replaced by that fragment, and the rest of the answer keeps
   growing in place until it completes (SC-002) — at no point between
   submission and completion does the input sit disabled with no visible
   activity.
4. Repeat with the chat-capable engine turned off or made unreachable.
   **Expect**: the indicator (or partial answer, if generation failed
   mid-stream) is replaced by a clear error message, not an indefinite
   spinner (FR-004).

## Scenario 2 — Structured rendering with clickable symbol references (User Story 2)

1. Ask a question likely to produce a code snippet and at least one
   symbol/file reference, e.g. "show me the function that handles
   authentication and explain it."
2. **Expect**: any fenced code in the answer renders visually distinct from
   prose — monospaced, set apart, syntax-colored (SC-004).
3. **Expect**: an inline reference in the established
   `` `path/to/file.ext :: Symbol.name` `` format (contracts/inline-symbol-reference-rendering.md)
   that the system can resolve renders as a clickable link; clicking it
   opens that symbol's documentation page (SC-003) — the same page the
   existing separate citation list beneath the answer already links to for
   the same symbol.
4. If the answer references something the system cannot resolve, **expect**
   it still renders as plain, readable inline code — never a broken link,
   never dropped or garbled text (FR-007).

## Scenario 3 — Reload/share mid-conversation (User Story 3)

1. Start a fresh conversation on a wiki page (no `chatSession` parameter
   yet) and ask at least one question through to completion.
2. **Expect**: the page's address now includes a `chatSession=<id>` query
   parameter (contracts/session-url-parameter.md), added without a
   navigation or reload.
3. Reload the page. **Expect**: the complete prior exchange (every question
   and answer, in order) reappears before the input becomes usable for a
   new question (SC-005).
4. Copy the page's address (including `chatSession=<id>`) and open it in a
   different browser or a private/incognito window. **Expect**: the same
   conversation history is restored there too (SC-006).
5. Manually edit the `chatSession` value in the address bar to a value that
   doesn't exist and load the page. **Expect**: no error is shown; a fresh,
   empty conversation starts, and the invalid id is dropped from the
   address (FR-011).
6. Load a wiki page with no `chatSession` parameter at all. **Expect**: a
   fresh, empty conversation starts immediately, no history fetch is
   attempted.

## Automated coverage

- `frontend/tests/ChatPanel.test.tsx` — activity-indicator lifecycle,
  progressive Markdown/code/reference rendering (resolved and unresolved),
  URL-parameter session resumption (success and 404 fallback), input gated
  until history hydration completes.
- `frontend/tests/chatApiClient.test.ts` — unchanged transport-level SSE
  parsing coverage (no contract change here).

Run with:

```bash
cd frontend && npm run test
```

# Research: Local Chat API

## Decision 1: Use FastAPI (Python), not Express (Node.js)

Decision: Build the HTTP layer with FastAPI and Pydantic request/response
models, run via uvicorn.

Rationale: Every component this feature composes — `chat.ChatSession`,
`vector_index.VectorIndex`, `embedding_engine.EmbeddingEngine`,
`local_llm.LocalLLMEngine` — is already Python, in the same process, with no
existing IPC boundary between them. FastAPI lets the API layer call
`ChatSession.ask` directly as an in-process function call, with Pydantic
giving free request validation (e.g. rejecting an empty question) and a
typed response schema. Express would require a second language runtime and
either a subprocess/socket bridge to the Python pipeline or a full port of
the RAG pipeline to Node, both of which contradict reusing the existing
pipeline as-is (spec Non-Goal: "Changing how the underlying RAG pipeline
retrieves evidence or generates answers").

Alternatives considered: Express (Node.js) was the explicit alternative
offered and was rejected for the cross-language boundary reason above. A
bare `http.server`-based hand-rolled router was considered and rejected
because it would reimplement request validation, JSON (de)serialization, and
routing that FastAPI already provides, for no benefit in a single-repo tool.

## Decision 2: Default bind address is `127.0.0.1`; binding elsewhere requires an explicit flag

Decision: `chat_api/server.py` calls `uvicorn.run(app, host="127.0.0.1",
port=<default>)` when no `--host` is given. An explicit `--host` argument is
required to bind to any other address (including a private LAN address).
There is no "auto-detect and bind to all interfaces" default.

Rationale: The spec requires the API to never be exposed publicly by
default, and constitution 2.2 requires every web server in the project to
bind to `127.0.0.1` by default with no network exposure without an explicit
user action. Making the safe default the *only* default (rather than, say,
defaulting to the machine's LAN IP) means a user who never touches `--host`
can never accidentally expose the service.

Alternatives considered: Defaulting to `0.0.0.0` (all interfaces) with a
warning was rejected — a warning that can be missed is not the same
guarantee as a bind address that is safe by construction. Requiring a config
file for any bind address was rejected as unnecessary ceremony for a single
CLI flag.

## Decision 3: Sessions are an in-memory registry scoped to the running process

Decision: `chat_api/session_store.py` holds a plain `dict[str, ChatSession]`
inside the FastAPI app's state, created empty at startup and discarded when
the process exits. No session data is written to disk by this feature.

Rationale: The spec's Assumption is that sessions live for the lifetime of
the running service, with no new cross-restart persistence guarantee
required. An in-memory dict is the simplest structure that satisfies every
functional requirement (create, ask, read history) without adding a new
database table, file format, or migration path — keeping this feature
aligned with the constitution's "infrastructure minimale" principle, which
already restricts the project to SQLite-and-files for the storage it does
have.

Alternatives considered: Persisting sessions to a new SQLite table was
considered (mirroring `repository_metadata`'s pattern) and rejected as
scope creep beyond what the spec asks for; it can be added later as a
backward-compatible addition if a real need for cross-restart history
emerges.

## Decision 4: Session identifiers are random UUID4 hex strings

Decision: Generate each session id as `uuid.uuid4().hex` at creation time.

Rationale: Unguessable, collision-resistant identifiers with zero
coordination needed across requests; matches the stable-id conventions
already used elsewhere in the project (e.g. `repository_metadata`'s
content-hash-derived ids) in spirit — an opaque, stable token rather than a
sequential counter a client could enumerate.

Alternatives considered: Sequential integer ids were rejected because they
are guessable and would let one local client enumerate other sessions on a
shared local-network deployment (the spec explicitly allows local-network,
not just single-machine, access).

## Decision 5: One shared `VectorIndex` / `EmbeddingEngine` / `LocalLLMEngine` per running server, constructed once at startup

Decision: `chat_api/server.py` constructs exactly one `VectorIndex` (via the
existing constructor), one `EmbeddingEngine` (via
`embedding_engine.create_embedding_engine`), and one `LocalLLMEngine` (via
`local_llm.create_local_llm_engine`) at process startup, pointed at one
repository's already-built local index. Every `ChatSession` created by
`POST /sessions` during that process's lifetime shares those same three
instances.

Rationale: The spec's Assumption is a single local user operating against
one indexed repository per running instance. Sharing one set of engines
avoids repeatedly opening the same SQLite-backed vector index or
re-resolving local model endpoints per session, and matches how
`test_chat_session.py` already exercises `ChatSession` — one engine/index
pair backing many `ask()` calls.

Alternatives considered: Constructing a fresh `VectorIndex`/engine set per
session was rejected as wasteful (repeated SQLite connections for the same
underlying data) with no isolation benefit, since all sessions in one
process already trust the same local repository.

## Decision 6: Map pipeline failures to explicit HTTP status codes, never a fabricated answer

Decision:
- `chat.LocalDependencyUnavailableError` → `503`, JSON body includes a
  stable `code: "local_dependency_unavailable"` field.
- Unknown `sessionId` on ask-question or get-history → `404`.
- Empty/whitespace-only question → `422` (FastAPI/Pydantic's standard
  validation-error shape, via a Pydantic field validator).

In every case, the error is raised and returned before `ChatSession.ask`
mutates session history, matching `ChatSession.ask`'s existing behavior
(`ensure_local_dependencies_available` raises before any message is
appended).

Rationale: The spec requires an explicit, structured error instead of a
partial or fabricated answer whenever the local model/embedding engine is
unavailable, and requires that nothing be silently recorded as if answered.
Using distinct, conventional HTTP status codes (rather than always `200`
with an error field) lets a client branch on status code alone without
parsing the body, while the `code` field gives it a stable string to key UI
behavior off of without depending on English error prose.

Alternatives considered: Returning `200` with an `{"error": ...}` body for
every failure case was rejected as making failure detection require parsing
response bodies instead of using standard HTTP semantics.

## Decision 7: API-facing Pydantic schemas are distinct from `chat`'s internal dataclasses

Decision: Define `chat_api/schemas.py` with its own
`AskQuestionResponse`/`ChatMessageView`/etc. Pydantic models, each populated
by copying the relevant fields off the corresponding `chat` dataclass
(`ChatMessage.citedSymbolIds` → `ChatMessageView.citedSymbolIds`, etc.),
rather than serializing `chat` dataclasses directly.

Rationale: `chat`'s dataclasses are the internal representation for the RAG
pipeline (011); they were not designed as a wire contract and are free to
gain internal-only fields over time. A dedicated schema layer keeps the HTTP
contract documented and stable in `contracts/chat-api.md` independent of
`chat`'s internals, at the cost of a small, explicit mapping step in
`chat_api/app.py`.

Alternatives considered: Returning `chat.ChatMessage.to_dict()` directly
from the endpoint was rejected because it would make the HTTP contract an
accidental byproduct of `chat`'s internal dataclass shape rather than a
deliberately designed one.

## Decision 8: No application-level authentication; rely on the network bind boundary

Decision: The API has no login flow, API key, or token check. Access control
is entirely the bind-address restriction from Decision 2.

Rationale: The spec's Non-Goals explicitly exclude multi-user
authentication/authorization beyond local-machine/network trust, and the
Assumptions state a single local user operates the API at a time. Adding
credential storage or a token scheme would itself be a piece of
infrastructure the constitution's "infrastructure minimale" principle would
require justifying, for a threat model (other local processes/users on the
same trusted machine or LAN) the spec does not ask this feature to defend
against.

Alternatives considered: A static shared-secret header was considered and
rejected as adding a secret-management concern (where is it stored,
rotated, shown to the user) that is disproportionate to the local-trust
threat model the spec defines.
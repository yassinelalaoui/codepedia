# Phase 0 Research: Remote-Default AI Provider Chains with Explicit Fallback

**Input**: [spec.md](./spec.md) · the `/speckit-plan` invocation's own detailed
technical direction (interfaces, table/column names, CLI subcommands) ·
direct inspection of the current codebase (`src/local_llm`,
`src/embedding_engine`, `src/vector_index`, `src/chat`, `src/chat_api`,
`src/repository_metadata`, `src/cli`).

All unknowns below are resolved; no `NEEDS CLARIFICATION` markers remain.

## 0. Correcting two premises in the plan input against the actual codebase

Before designing anything, two claims in the `/speckit-plan` prompt turned
out not to match what exists today — calling this out explicitly so the
design below isn't read as "extending" something that must first be built:

- **"extension du champ `generatedBy` déjà introduit"** — no `generatedBy`
  (or `generated_by`) field exists anywhere in the codebase today (`chat/models.py`'s
  `ChatMessage`, `chat_api/schemas.py`'s `ChatMessageView`/`AskQuestionResponse`,
  and `repository_metadata`'s stored summaries all lack any engine/provider
  attribution field). This feature **introduces** `generatedBy`, it does not
  extend a pre-existing one.
- **Provider fan-out is a deliberate anti-goal today, being reversed here** —
  `local_llm.create_llm_engine()`'s own docstring states it builds *"exactly
  one engine for the given provider - never a composite that tries another
  provider on failure (research.md Decision 2, constitution 2.3 v2.0.0)"*.
  That was correct under constitution v2.0.0. Constitution v3.0.0 (2.1/2.3)
  explicitly reverses this, and this feature is exactly the "deferred"
  implementation work the v3.0.0 Sync Impact Report named. The plan below
  intentionally replaces single-engine injection with a chain-aware router
  in the two pipelines (`chat`, `repository_metadata.summary_pipeline`) that
  currently hard-fail on one engine.

## 1. Where the new chain/router abstraction lives

**Decision**: A new top-level package, `src/provider_routing/`, sitting
alongside `local_llm` and `embedding_engine` (not inside either — it
depends on both). Contains: `chain.py` (`ProviderRef`, `ProviderChain`),
`router.py` (`FailoverExecutor`), `errors.py` (`FailoverExhaustedError`),
`classify.py` (maps an engine exception to a failover reason), `factory.py`
(resolves a `ProviderChain` + `CLIConfiguration` into concrete, ready-to-call
engine instances), and `failover_log.py` (the SQLite read/write functions
for `engine_failover_log`, executed against the same DB connection as
`repository_metadata`).

**Rationale**: `local_llm` and `embedding_engine` are established,
independently-testable leaf packages (per `docs/architecture.md`'s layering
note) with their own protocols/errors; neither should depend on the other
just to host a router that orchestrates both. `cli`, `chat`, and
`repository_metadata` (the three consumers) already sit "above" both engine
packages in the dependency order, so a new package at the same level as
`local_llm`/`embedding_engine` — depended on by `cli`/`chat`/`repository_metadata`,
depending only on the two engine packages — preserves the existing layering
instead of creating a new cross-dependency between sibling leaf packages.

**Alternatives considered**: Putting the router inside `local_llm` and
duplicating it for embeddings inside `embedding_engine` — rejected, it
would duplicate the entire retry/classification/logging logic twice for no
benefit, when a single stage-agnostic executor (operating on whatever
callable + engine list it's given) works for both. Putting it inside `cli`
— rejected, `chat_api`/`chat` need the chat-stage router at request time,
not just at CLI-invocation time, so it can't live in a CLI-only package.

## 2. The `isAvailable()` unification the plan input asks for

**Decision**: Add a new `isAvailable(self) -> bool` method to
`LocalLLMEngine`, `GroqLLMEngine`, the local embedding engine, and the new
`OpenAIEmbeddingProvider` — each simply delegating to the engine's existing
availability check (`return self.isAvailableLocally()`, or the remote
equivalent already computed by `checkAvailability()`). `isAvailableLocally()`
itself is **kept, unchanged**, since it's already called directly by
`chat/session.py`, `repository_metadata/summary_pipeline.py`, and every
existing test — renaming it everywhere would be a large, purely cosmetic
diff with no behavioral benefit. `FailoverExecutor` and the new
`EmbeddingProvider` protocol are the only things that call `isAvailable()`;
everything else keeps calling `isAvailableLocally()` exactly as today.

**Rationale**: The plan input explicitly asks for a uniform `isAvailable()`
across all four provider kinds (`RemoteLLMProvider`/`LocalLLMProvider`/
`RemoteEmbeddingProvider`/`LocalEmbeddingProvider`), which is exactly what a
stage-agnostic router needs to treat an LLM engine and an embedding provider
interchangeably for the one thing it actually needs from both (`is this one
usable right now?`). Adding one small delegating method per class is the
minimal change that satisfies this without touching the many existing call
sites of `isAvailableLocally()`.

**Alternatives considered**: Renaming `isAvailableLocally` to `isAvailable`
everywhere — rejected as unnecessarily invasive (touches `chat/session.py`,
`repository_metadata/summary_pipeline.py`, `cli/config_command.py`, and
every existing unit/contract test for zero behavioral change) for a purely
naming-level goal the router doesn't actually require.

## 3. A parallel `EmbeddingProvider` protocol, without renaming today's `EmbeddingEngine`

**Decision**: Introduce `EmbeddingProvider` as a new `@runtime_checkable
Protocol` in `embedding_engine/protocol.py`, mirroring `local_llm.LLMEngine`
(`isAvailable`, `checkAvailability`, `embed`). The existing concrete
`EmbeddingEngine` dataclass (local/Ollama-backed) is left named exactly as
it is today and gains the protocol's methods; a new `OpenAIEmbeddingProvider`
dataclass (`embedding_engine/openai_provider.py` + `openai_transport.py`,
structured exactly like `groq_engine.py`/`groq_transport.py`) is the second
implementation.

**Rationale**: The plan input's own naming (`RemoteEmbeddingProvider`,
`LocalEmbeddingProvider`) suggests a fully symmetric rename, but
`EmbeddingEngine` is imported by name in `vector_index/index.py`,
`vector_index/chunking.py`, `reindex_pipeline/embeddings.py`, `cli/index_command.py`,
`cli/config_command.py`, and their tests. Renaming it purely for naming
symmetry (the actual requirement — one interface, two implementations,
`isAvailable()` on both — doesn't need matching class names) would be a
wide, purely-cosmetic diff. `local_llm` already accepts this exact
asymmetry (protocol `LLMEngine`, concrete `LocalLLMEngine`); the same shape
here (protocol `EmbeddingProvider`, concrete `EmbeddingEngine` for local)
is consistent with that precedent, not a new pattern.

**Alternatives considered**: Renaming `EmbeddingEngine` → `LocalEmbeddingEngine`
for full symmetry — rejected per the simplification above; nothing in
spec.md's functional requirements depends on the class's name, only on the
protocol existing and both implementations satisfying it.

## 4. New default remote embedding provider: OpenAI `text-embedding-3-small`

**Decision**: `OpenAIEmbeddingProvider` calls `POST
https://api.openai.com/v1/embeddings` with `{"model": "text-embedding-3-small",
"input": text}`, authenticated via an `OPENAI_API_KEY` environment variable
(never read from or written to any config file — same posture as
`GROQ_API_KEY` in `groq_transport.py`). `text-embedding-3-small` produces
1536-dimensional vectors; `CodeChunk`/`VectorEntry`'s existing
`dimensionality` field already accommodates any vector length without
change.

**Rationale**: No remote embedding implementation exists anywhere in the
codebase today (confirmed by inspection) — Groq itself offers no embeddings
API (noted directly in the constitution's Sync Impact Report), which is
exactly why the spec names OpenAI specifically for this one stage. Modeling
its transport after `groq_transport.py` keeps error handling (network/auth/
rate-limit classification) consistent across every remote provider this
feature adds.

**Alternatives considered**: None seriously — the spec input names this
exact provider/model explicitly; the only real decision here was "does an
existing implementation already exist" (it doesn't).

## 5. Default remote model names

**Decision**: `llama-3.3-70b-versatile` for both the summary and chat
stages' default Groq entry (`groq:llama-3.3-70b-versatile`); `nomic-embed-text`
and `qwen2.5-coder` remain the local-mode default embedding/LLM model names
(unchanged), used when `provider mode full-local` writes `local:nomic-embed-text`
/ `local:qwen2.5-coder` chain entries.

**Rationale**: `llama-3.3-70b-versatile` is already the model used
throughout the existing Groq test suite (`tests/unit/test_groq_llm_engine.py`)
and is the example given in `README.md` for `--remote-llm-model`; reusing it
keeps one canonical default model name across the codebase rather than
introducing a second, arbitrary one. `nomic-embed-text`/`qwen2.5-coder` are
already `embedding_engine`/`cli.config`'s existing local defaults
(`DEFAULT_MODEL_NAME`, `DEFAULT_LLM_MODEL`) — exactly the models the plan
input names for local mode.

## 6. New error kind: rate limiting

**Decision**: Add `RateLimitedError` to both `local_llm/errors.py` (subclass
of `RemoteLLMError`, `kind="rate_limited"`) and `embedding_engine/errors.py`
(subclass of `EmbeddingError`, same `kind`). `groq_transport.py`'s
`availability()` and `generate_stream()` are extended to detect HTTP 429
specifically and raise/report this new kind instead of falling into the
generic `RemoteGenerationFailedError`/"≥400" branch; `OpenAIEmbeddingProvider`'s
transport does the same for its own 429s.

**Rationale**: Spec FR-005 requires failover to trigger specifically on
"network error, rate/quota limit, or authentication failure" — three
*distinguishable* reasons, both for `FailoverExecutor`'s retry-vs-give-up
decision (all three are always retryable within a chain — the difference
matters for what gets logged as `reason` (FR-008/`engine_failover_log`), not
for whether to fail over) and for the failover log to be genuinely
informative rather than a single generic "error" reason on every row.
Rate-limit detection did not exist before this feature — confirmed by
reading `groq_transport.py`'s actual branches, which map HTTP 429 into the
same bucket as any other 4xx/5xx today.

**Alternatives considered**: Inferring the reason categories purely from
generic exception types (`httpx.TransportError` vs `httpx.HTTPStatusError`)
without a dedicated error kind — rejected; `_error_code_for` (`chat_api/app.py`)
and the CLI's error reporting already key off a `.kind` string attribute
uniformly across every existing error class, so adding one more `kind`
value is a one-line, wholly consistent extension rather than a special case.

## 7. Failover semantics for a *streaming* chat call

**Decision**: `FailoverExecutor` only fails over to the next provider in
the chain for a `generateStream` call if the failure happens **before any
fragment has been yielded** to the caller (i.e., at connection/auth/initial
request time). Once at least one fragment has been successfully yielded
from a provider's stream, a later failure from that same stream is **not**
retried against the next provider — it propagates exactly as it does today
(caught by `chat_api/app.py`'s existing SSE `event: error` handling).

**Rationale**: This directly resolves spec.md's own Edge Case ("What happens
when a remote provider fails partway through producing a chat answer that
had already started streaming a partial response?") the way the spec
already commits to: *"this feature governs which provider is chosen...not
how a partially-streamed answer itself is displayed."* Restarting generation
from a second provider mid-stream would mean either silently discarding
already-sent fragments (the client already rendered them - 028) or
splicing two providers' output together into one answer, both worse than
today's existing partial-failure behavior. Failing over only pre-first-fragment
keeps the new chain-aware `chat` stage a strict superset of today's
single-engine behavior for the case that already has defined behavior.

**Alternatives considered**: Retrying the whole operation against the next
provider even after fragments were yielded, discarding the partial answer
client-side — rejected, requires a client-visible "actually, restart" signal
that doesn't exist and would be a regression for User Story 1 (028)'s
progressive-answer guarantee. Buffering the entire answer server-side before
sending anything (removing the mid-stream failure case entirely) — rejected,
directly regresses spec 026/027/028's progressive-streaming guarantees for
every request, not just ones that eventually fail over.

## 8. Vector index: per-vector model tag and same-model search filtering

**Decision**: Add one new column, `embedding_model_id TEXT NOT NULL DEFAULT
''`, to `vector_index/storage.py`'s `chunks` table via `ALTER TABLE chunks
ADD COLUMN ...` inside `ensure_schema()`, guarded by a `PRAGMA table_info(chunks)`
check (no migration framework exists in this codebase — `ensure_schema`'s
existing statements are all idempotent `CREATE TABLE/INDEX IF NOT EXISTS`,
so this is the one new statement that needs its own idempotency guard rather
than relying on `IF NOT EXISTS`, which `ALTER TABLE ADD COLUMN` has no
equivalent for). `CodeChunk`/`VectorEntry` (`vector_index/models.py`) each
gain an `embeddingModelId: str = ""` field, threaded through `upsert_chunk`/
`load_entries`/`load_chunks_for_file`. `_matches_filters` (`vector_index/search.py`)
gains one more recognized filter key, `embeddingModelId`, checked **before**
the existing dimensionality assertion in `rank_entries` — so a mismatched
vector is silently excluded from ranking, not compared and never reached by
the dimensionality check at all. `VectorIndex.search()` passes the id of
whichever provider/model the `FailoverExecutor` actually used to embed the
query text as this filter automatically (the caller never has to specify it).

**Rationale**: This is the direct, minimal fix for a real bug found by
inspection, not just new functionality: `VectorIndex.search()` today
computes `dimension` from one arbitrary stored entry
(`next(iter(self._entries.values()))`) and `rank_entries` then **raises
`ValueError`** the moment it iterates to any entry whose `dimensionality`
differs — meaning a repository with mixed-model vectors (this feature's own
User Story 4 scenario) would make search **crash outright** today, not
"silently blend" as spec.md's Edge Cases worried about. Filtering by
`embeddingModelId` before the dimensionality check both implements FR-010
correctly (never compare incompatible vectors) and incidentally eliminates
that crash, since every vector that survives the filter is guaranteed to
share the querying provider's dimensionality by construction.

**Alternatives considered**: Keying compatibility purely off `dimensionality`
(no explicit model id) — rejected; two different embedding models can
coincidentally share a dimensionality (e.g. a future local model that also
outputs 1536-dim vectors) while still being semantically incompatible, so
the spec's own "different, incompatible embedding models" language requires
tracking model identity, not just vector length. A separate migration
tool/versioned schema framework — rejected as disproportionate; one
column, added the same idempotent way the rest of this codebase already
extends SQLite schemas (`chat_sessions`/`chat_messages` were added to
`repository_metadata`'s schema the same incremental way, just without
needing `ALTER TABLE` since those were whole new tables).

## 9. Where `engine_failover_log` lives

**Decision**: In `repository_metadata.sqlite_store.SCHEMA_STATEMENTS` — the
same per-repository SQLite file that already hosts `chat_sessions`/
`chat_messages` (spec 025), despite those being conceptually owned by the
`chat` package, not `repository_metadata` itself.

**Rationale**: Direct precedent already exists and is documented
(`docs/architecture.md`: *"the schema still stays [in repository_metadata]...
only the row↔object mapping lives in the later layer"*). `engine_failover_log`
is populated by all three stages (embeddings and summary during `index`/
`serve`, chat during a live session) — it is even more cross-cutting than
`chat_sessions`/`chat_messages`, so it belongs in the one already-shared,
per-repository local database rather than forcing a new SQLite file (which
would violate constitution 2.6's "infrastructure minimale" more than
reusing the one that already exists for exactly this kind of adjacent,
non-`symbols`/`dependency_edges` data).

**Alternatives considered**: `vector_index`'s own SQLite file — rejected,
that file is scoped to one specific vector index/repository pairing and has
no natural home for summary/chat stage events. A dedicated new SQLite file
— rejected as an unnecessary second local database for one small log table
when an established, shared one already exists for this exact kind of data.

## 10. Provider-chain configuration shape

**Decision**: Extend `cli.config.CLIConfiguration` (still one flat,
JSON-persisted dataclass, `load_config`/`save_config`'s existing
load-with-defaults / validate-then-write shape unchanged) with three new
fields: `embeddingChain: tuple[str, ...]`, `summaryChain: tuple[str, ...]`,
`chatChain: tuple[str, ...]`, each an ordered tuple of `"<provider>:<model>"`
strings (`ProviderRef.__str__`/`.parse()` round-trip, e.g.
`"groq:llama-3.3-70b-versatile"`, `"local:nomic-embed-text"`). The existing
`llmProvider`/`remoteLlmModel` fields (the old single-provider selector) are
**removed** — chains supersede them entirely, there is no dual-mode to keep
in sync. `llmModel`/`llmEndpointUrl`/`llmGenerateTimeout` and
`embeddingModel`/`embeddingEndpointUrl`/`embeddingGenerateTimeout` are
**kept**, but their meaning narrows to "connection settings for *any* `local:`
chain entry" (Ollama endpoint/timeout) rather than "the LLM/embedding model
in use" — the actual model name for a local entry now lives in that entry's
`ProviderRef.model` (e.g. `local:qwen2.5-coder`), consistent with how a
`groq:`/`openai:` entry already carries its own model name.

One more field, `disclosureAcknowledgedSignature: str = ""`, records a
stable signature (a hash) of the three chains as they stood the last time
the user explicitly acknowledged the disclosure (FR-013) — an empty string
means "never acknowledged" (fresh install). Each run recomputes the current
three chains' signature and compares; a mismatch (including the empty
fresh-install case) means the blocking disclosure must be shown and
acknowledged again before the signature is updated and the run proceeds.

**Rationale**: Keeps the existing, already-tested config load/save/validate
shape (`CLIConfiguration`, `load_config`, `save_config`, JSON at
`paths.config_path()`) rather than introducing a second config file/format
purely for chains — one configuration surface stays the single source of
truth. Storing an acknowledgment *signature* rather than a boolean
"acknowledged: true" flag is what makes FR-013's "re-show on any actual
change, skip on unchanged re-runs" requirement correct without extra
bookkeeping: any edit to any of the three chains changes the signature,
which alone is sufficient to force the gate again.

**Alternatives considered**: A separate `provider-chains.json` file —
rejected, splits configuration across two files/load paths for no benefit
over adding fields to the one dataclass already used this way. A boolean
"first run only" disclosure flag instead of a signature — rejected, it
satisfies "at first launch" but not FR-012/FR-013's "at every point a
stage's provider-chain configuration actually changes."

## 11. CLI surface

**Decision**: A new Typer sub-application, `provider_app = typer.Typer()`,
mounted as `app.add_typer(provider_app, name="provider")` in `cli/main.py`
(the first nested command group in this codebase — every existing command
is currently flat — but an idiomatic, supported Typer pattern). Two
commands, matching the plan input exactly:
- `codepedia provider chain set <stage> <provider:model> [<provider:model> ...]`
  — `stage` restricted to `embeddings|summary|chat`; the ordered positional
  arguments become that stage's new chain, validated (non-empty, each entry
  parses, no chain-breaking values) and saved the same way `run_config`
  validates-then-`save_config`s today.
- `codepedia provider mode full-local` — atomically sets all three chains
  to `("local:nomic-embed-text",)` / `("local:qwen2.5-coder",)` /
  `("local:qwen2.5-coder",)` in one `save_config` call (one write, not three
  sequential ones, so a crash mid-way can't leave only some chains switched).

The mandatory disclosure (FR-012/FR-013) is enforced once, centrally, in
`cli/main.py`'s Typer callback (`main()`, which already runs before every
command per Typer's callback semantics) rather than duplicated into each
command — computed/compared/shown/`typer.confirm()`-gated there for every
invocation of every command that would touch a provider-consuming stage.

**Rationale**: Matches the plan input's exact command shapes. A Typer
callback is the one place already guaranteed to run before any subcommand’s
body, so it's the natural, single enforcement point for a cross-cutting gate
— avoids duplicating the disclosure-and-acknowledge logic into `index`,
`serve`, and every `provider` subcommand separately.

**Alternatives considered**: A flat `provider-chain-set`/`provider-mode-full-local`
command naming (matching the existing flat style) — rejected in favor of
the nested `provider chain set` / `provider mode full-local` grouping the
plan input explicitly specifies, which also reads better as the command
surface grows (chain get/list could follow later without new top-level
command names).

## 12. Exposing `generatedBy` and the failover log through `chat_api`

**Decision**: `ChatMessage` (`chat/models.py`) gains a `generatedBy: str = ""`
field (a `ProviderRef` string); `chat_messages` (repository_metadata's
schema) gains a matching `generated_by TEXT NOT NULL DEFAULT ''` column
(same `ALTER TABLE` + guard pattern as the vector index change).
`ChatMessageView`/`AskQuestionResponse` (`chat_api/schemas.py`) both gain a
`generatedBy: str` field, populated from whichever `ProviderRef` the
chat-stage `FailoverExecutor` actually used. A new read-only route,
`GET /providers/failover-log`, returns every `engine_failover_log` row
(optionally filtered by `?stage=`), via a new `FailoverLogEntryView`/
`FailoverLogResponse` pair following the exact same
route-in-`create_app`/schema-in-`schemas.py` pattern every other
`chat_api` route already uses.

**Rationale**: Directly implements spec FR-008's "indiquée clairement dans
l'interface" for the chat stage (the interface that already exists for
that stage, per spec.md's own Assumption) and gives the CLI/wiki a
documented HTTP contract to read the log from, matching the plan input's
"consultable depuis l'API (4.3)" requirement. Whether the bundled wiki UI
visually renders `generatedBy`/the failover log is **out of scope for this
backend feature** — exactly like spec 026 explicitly deferred its own
frontend consumption to a later spec (027); the HTTP/data contract this
feature adds is what a future UI feature would consume, following the same
staging this codebase already uses repeatedly.

**Alternatives considered**: Only logging failover events, without also
tagging every chat message with `generatedBy` — rejected; FR-008 requires
visibility for *every* switch, and a chat answer produced by provider B
after A failed is exactly the moment a user is looking at the answer itself,
so the message-level tag is the most direct "indication... in the
interface," with the full log as the secondary, complete audit trail.

## 13. Post-analysis fixes (2026-08-25 `/speckit-analyze` findings)

A pre-implementation analysis, driven by tracing every current call site of
the functions/fields this plan changes (not just cross-referencing spec/plan/tasks
against each other), found four concrete breakages the original tasks list
didn't cover, plus one real design ambiguity. All five are resolved here so
`tasks.md` reflects the fix, not just the finding.

**C1/C2 (`cli/availability.check_ai_dependencies` and
`chat/session.ensure_local_dependencies_available` would break)**:
Both existing pre-flight functions call a single engine's availability
method directly (`.checkAvailability()`/`.isAvailableLocally()`) — neither
works once the object they're handed is a `FailoverExecutor` instead of a
raw engine, and `ensure_local_dependencies_available` is called from *two*
places (`chat/session.py`'s own `askStream()` *and*, separately,
`chat_api/app.py`'s `ask_question` route, for its own pre-`StreamingResponse`
503 check) — a second call site easy to miss when only looking at
`askStream()`. **Decision**: give `FailoverExecutor` its own `isAvailable()`
aggregate method (True if any chain entry is available — contracts/provider-protocols.md),
then change `ensure_local_dependencies_available`'s two internal checks and
`check_ai_dependencies`'s two internal checks from
`.isAvailableLocally()`/`.checkAvailability().available` to `.isAvailable()`.
Because `isAvailable()` already exists on every single engine too
(research.md §2), this is a small, localized fix to the two shared
functions themselves — every one of their four call sites (`askStream`,
`chat_api/app.py`, `cli/index_command.py`, `cli/serve_command.py`) keeps
working unchanged, whether handed a raw engine or a chain. `check_ai_dependencies`'s
error message narrows from `AvailabilityStatus.message` (single engine's
specific reason) to a generic "no provider in the `<stage>` chain is
currently available" (a multi-provider aggregate has no one status message
to surface faithfully) — acceptable since the specific reason still surfaces
in full once `FailoverExecutor.run`/`.stream` is actually attempted and
raises `FailoverExhaustedError`.

**C4 (`chat_api/server.py` unaddressed)**: This standalone entrypoint
builds a single local `llm_engine`/`embedding_engine` directly and passes
them to `create_app(...)`. Once `ChatSession.askStream()` calls
`self.llmEngine.stream(...)` (a `FailoverExecutor` method — T035/T047), a
raw engine passed here would fail with `AttributeError` (`generateStream`
exists, `stream` doesn't). **Decision**: wrap this entrypoint's engines in
single-provider `FailoverExecutor`s (via `provider_routing.factory` or
directly) before constructing `VectorIndex`/`create_app`, rather than
leaving it structurally incompatible with the rest of this feature or
declaring it silently out of scope.

**M1 (disclosure-timing ambiguity for `provider chain set`/`mode full-local`)**:
A Typer app callback alone only ever sees the configuration *before* the
current command's own body runs, so `provider chain set`/`mode full-local`
would never show the disclosure for the change they themselves just made —
only some later, unrelated command would notice the stale signature.
**Decision**: extract the gate into `cli/disclosure.py`'s
`ensure_disclosure_acknowledged(config) -> config`, called both from
`cli/main.py`'s callback (for `index`/`serve`, using the config as loaded)
*and* a second time, immediately, from `run_provider_chain_set`/
`run_provider_mode_full_local` themselves, against the configuration they
just wrote — so the disclosure a user sees right after changing a chain
already names the providers they just configured, and the signature is
updated immediately rather than left stale for whatever command happens to
run next (contracts/cli-provider-commands.md).

**M3 (disclosure content accuracy after a change)**: Once M1's fix is in
place, the disclosure's content is trivially correct by construction (it's
generated from whatever `config` it's actually handed) — the remaining gap
was purely in test coverage, closed by making the `provider chain set`/
`mode full-local` integration tests assert the printed disclosure names the
newly-configured providers, not just that a prompt appeared.

**M2 (FR-011/FR-014/FR-015 regression risk)**: None of these three
requirements gets a dedicated implementation task (each is satisfied by
*not* adding code that would violate it), so none had a task naming it
either — the same "implicit-only coverage" pattern flagged in this
project's 028 analysis. Resolved by adding one explicit Polish-phase
regression-check task naming the existing tests that back all three.

**L1 (`ProviderRef` local-model validation scope)**: `ProviderRef.parse`
validates only `kind` (one of the three known values) and that `model` is
non-empty — it does not validate that a named local model is actually
installed/pullable, which stays exactly where that check already lives
today (the engine's own `checkAvailability()`, called lazily when the chain
is actually used) rather than being duplicated at parse time.

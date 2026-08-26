# Quickstart: Validating Provider Fallback Chains

Prerequisites: a fresh checkout with no `~/.codepedia` (or equivalent
`paths.config_path()`) config file yet, so defaults genuinely apply; a
`GROQ_API_KEY` and `OPENAI_API_KEY` in the environment for Scenarios 1 and
3; Ollama running locally with `nomic-embed-text` and `qwen2.5-coder`
pulled, for Scenarios 2 and 4.

```bash
pip install -e .
```

## Scenario 1 — Zero-config install routes to the named remote defaults (User Story 1)

1. With no prior configuration, run: `codepedia index <a small test repo>`.
2. **Expect**: the blocking disclosure appears first, naming
   `openai:text-embedding-3-small` (embeddings), `groq:llama-3.3-70b-versatile`
   (summary and chat), and the exact `provider mode full-local` command to
   opt out — and the run does not proceed until it's acknowledged
   (`y`/confirm at the prompt) (FR-012/FR-013).
3. **Expect**: after acknowledging, indexing actually produces summaries via
   Groq and embeddings via OpenAI — confirm via `codepedia config --show`-equivalent
   status output showing both chains, and via the produced wiki's rendered
   summaries.
4. Run `codepedia index` again on the same repo, unchanged configuration.
   **Expect**: the disclosure does NOT block again (SC-006 — only shown "at
   meaningful configuration moments," per an unchanged signature).

## Scenario 2 — One action switches everything to fully local (User Story 2)

1. `codepedia provider mode full-local`.
2. **Expect**: the disclosure/config-change gate fires once for this change
   (a chain changed, so the signature is stale) — acknowledge it.
3. **Expect**: `codepedia config`-equivalent status output now shows all
   three chains as `local:...` entries only.
4. Run `codepedia index` on a repository. **Expect**: zero outbound
   network calls to Groq or OpenAI (verify via a network monitor or by
   unsetting `GROQ_API_KEY`/`OPENAI_API_KEY` beforehand and confirming the
   run still succeeds, proving neither was contacted) — indexing completes
   using the local engines instead (SC-002).

## Scenario 3 — Automatic failover within a two-provider chain (User Story 3)

1. `codepedia provider chain set chat groq:llama-3.3-70b-versatile local:qwen2.5-coder`
   (acknowledge the resulting disclosure).
2. Simulate Groq unavailability: temporarily unset `GROQ_API_KEY` (or point
   `GROQ_API_KEY` at an invalid value to force an auth failure), with Ollama
   running locally.
3. Ask a chat question against an indexed repository (`codepedia serve`
   + a chat request, or the equivalent contract test).
4. **Expect**: the answer is still produced (via the local engine); the
   response's `generatedBy` field reads `local:qwen2.5-coder`; a
   `GET /providers/failover-log` request shows one new row —
   `attemptedProvider=groq:llama-3.3-70b-versatile`,
   `resultProvider=local:qwen2.5-coder`, `reason=auth_failed` — with a
   fresh timestamp (SC-003).
5. Restore `GROQ_API_KEY` and repeat with a chain of two *remote* providers
   instead, to confirm a network/rate-limit-classified reason is recorded
   the same way when neither side is local.

## Scenario 4 — Mixed-model embeddings never blend in search (User Story 4)

1. With the default remote embedding chain, index a repository (embeddings
   via OpenAI `text-embedding-3-small`).
2. Switch to local embeddings only:
   `codepedia provider chain set embeddings local:nomic-embed-text`
   (acknowledge the gate), then modify and re-index one file so at least
   one new chunk is embedded via the local engine while the rest of the
   repository's chunks remain OpenAI-embedded.
3. Run a similarity search (via the chat API or a direct `VectorIndex.search`
   contract test).
4. **Expect**: the search never raises (no dimensionality crash — the
   pre-existing bug this feature also fixes, research.md §8) and every
   result comes from vectors sharing the same `embeddingModelId` as the
   provider that just embedded the query text — i.e., switching back and
   forth between the two embedding providers and searching each time
   produces two internally-consistent result sets, never one mixing both
   (SC-004).

## Automated coverage

- `tests/contract/test_provider_router_interface.py` — `FailoverExecutor`
  contract: retries only on classified-unavailable errors, never attempts a
  provider outside the given chain, raises `FailoverExhaustedError` when
  every provider fails, mid-stream failures after the first fragment are
  not retried.
- `tests/unit/test_provider_chain.py` — `ProviderRef`/`ProviderChain`
  parsing/validation, default chains, `provider mode full-local`'s exact
  resulting chains.
- `tests/unit/test_failover_log.py` — `engine_failover_log` append/list
  behavior, including the `NULL` `result_provider` (exhausted) case.
- `tests/unit/test_vector_index.py` (extended) — same-model search
  filtering, mixed-dimensionality entries no longer raising.
- `tests/integration/test_cli_provider_commands.py` — `provider chain set`,
  `provider mode full-local`, and the blocking disclosure gate (shown on
  change, skipped when unchanged).
- `tests/integration/test_chat_api.py` (extended) — `generatedBy` on
  `AskQuestionResponse`/`ChatMessageView`, `GET /providers/failover-log`.

Run with:

```bash
pytest tests/contract tests/unit tests/integration
```

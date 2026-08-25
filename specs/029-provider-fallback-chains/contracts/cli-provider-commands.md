# Contract: CLI `provider` Commands and the Disclosure Gate

**Status**: New Typer sub-app (`cli/provider_command.py`, mounted in
`cli/main.py`); new blocking disclosure enforced in `cli/main.py`'s Typer
callback.

## `repo-scanner provider chain set <stage> <providerRef> [<providerRef> ...]`

- `stage`: one of `embeddings`, `summary`, `chat` (exact match, case-sensitive
  — same validation style as `LLM_PROVIDERS` today). Any other value exits
  non-zero via the existing `report_and_exit`/`ValueError` path.
- `<providerRef>...`: one or more `"<kind>:<model>"` strings
  (`ProviderRef.parse`), in the order they should be tried. At least one is
  required — an empty chain is rejected before anything is written
  (spec Edge Cases).
- On success: that one stage's chain in `CLIConfiguration` is replaced
  (the other two chains are untouched); the command then immediately calls
  the same shared disclosure gate used by the callback (`cli/disclosure.py`'s
  `ensure_disclosure_acknowledged`, research.md §13) against the
  just-saved configuration — so the disclosure shown names the providers
  that were just set, not stale ones, and `disclosureAcknowledgedSignature`
  is updated right away rather than left stale for some later, unrelated
  command to trigger (post-analysis fix — see M1 in the 2026-08-25 analysis).
- Prints the new chain back, mirroring `run_config`'s existing
  "Configuration saved."-then-status-echo pattern.

## `repo-scanner provider mode full-local`

- No arguments. Atomically sets all three chains in one `save_config` call:
  `embeddingChain=("local:nomic-embed-text",)`,
  `summaryChain=("local:qwen2.5-coder",)`, `chatChain=("local:qwen2.5-coder",)`
  (spec FR-004 — a single action, not three separate ones a user could
  interrupt partway through), then immediately runs the same shared
  disclosure gate as `chain set` above, against the freshly-saved
  all-local configuration.
- Prints the resulting three chains, same status-echo pattern as above.

## Mandatory disclosure gate (spec FR-012/FR-013)

Implemented once as `ensure_disclosure_acknowledged(config: CLIConfiguration)
-> CLIConfiguration` in a new `src/cli/disclosure.py` (not inlined into
`cli/main.py`'s callback directly, so the exact same logic can also be
invoked from `provider chain set`/`provider mode full-local` themselves —
see below and M1 in the 2026-08-25 analysis, which found the
callback-only design would defer showing an updated disclosure to some
later, unrelated command instead of the command that actually changed the
configuration):

1. Compute `sign(config.embeddingChain, config.summaryChain, config.chatChain)`.
2. If it equals `config.disclosureAcknowledgedSignature`: return `config`
   unchanged — already disclosed and acknowledged for this exact
   configuration.
3. Otherwise: print the disclosure — naming the exact current provider for
   each of the three chains (not just "some remote service"), and the exact
   command (`provider mode full-local`) to switch to fully local — then
   call `typer.confirm(...)`. A decline aborts (raises, caught by the
   caller as a clean exit: nothing written, no engine called). An
   acknowledgment persists the new signature via `save_config` and returns
   the updated `config`.

**Two call sites**:
- `cli/main.py`'s Typer app callback calls it (with the config as currently
  loaded) before **every** subcommand that touches a chain-consuming stage
  (`index`, `serve`, `provider chain set`, `provider mode full-local`;
  `scan` and `config --show` are read-only/static-analysis-only and are not
  gated, per spec FR-014's "static analysis... unaffected").
- `run_provider_chain_set`/`run_provider_mode_full_local` (see above) each
  call it *again*, immediately after their own `save_config`, against the
  configuration they just wrote — so the disclosure shown at the moment a
  chain actually changes names the providers just set, not stale ones, and
  the signature is updated right then rather than deferred to whatever
  command happens to run next.

This is the one and only place the gate is implemented; no subcommand
duplicates this logic.

## `GET /providers/failover-log` (new `chat_api` route)

| | |
|---|---|
| Method/path | `GET /providers/failover-log` |
| Query params | `stage` (optional, one of `embeddings`\|`summary`\|`chat`); `limit` (optional, default 100) |
| Response | `FailoverLogResponse { events: FailoverLogEntryView[] }` |
| `FailoverLogEntryView` | `{ id, timestamp, stage, attemptedProvider, resultProvider: string \| null, reason }` |
| Errors | None beyond the app's existing generic error handling — this is a read-only, always-available route (no engine/session dependency). |

Ordered most-recent-first (matches `GET /sessions`' existing
most-recently-active-first convention). Registered inside `create_app`
exactly like every other route (`app.py`), with the new schema classes
added to `chat_api/schemas.py`.

## `ChatMessageView` / `AskQuestionResponse` (extended)

Both gain `generatedBy: str` — the `ProviderRef` string of whichever
provider in the chat chain actually produced that message/answer
(spec FR-008, "indiquée clairement dans l'interface" for the chat stage).
Populated from the chat-stage `FailoverExecutor`'s `FailoverResult.providerUsed`
once streaming completes; unchanged (empty string) for any message
persisted before this feature shipped.

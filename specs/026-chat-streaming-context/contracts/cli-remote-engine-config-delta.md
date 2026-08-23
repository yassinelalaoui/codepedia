# CLI Contract — Remote Engine Configuration Delta

## Purpose

This feature adds configuration surface to the existing `repo-scanner
config` command (`specs/019-cli-orchestrator/contracts/cli-interface.md`).
It adds no new command. This document records the delta.

## `repo-scanner config` — new flags

- `--llm-provider {local,groq}` — selects which engine `index`/`serve` use
  for chat answer generation. Defaults to `local` when never set (existing
  behavior, unchanged, for every operator who doesn't touch this).
- `--remote-llm-model <name>` — the model name to use when
  `--llm-provider groq` is selected (e.g. `llama-3.3-70b-versatile`).
  Required (validated at save time) whenever the provider is `groq`.

The Groq API key is **not** a CLI flag or config field — it is read from the
`GROQ_API_KEY` environment variable at the moment a `GroqLLMEngine` is
actually constructed (index/serve startup, or `config`'s own availability
check). `repo-scanner config` never prints, stores, or otherwise handles
the key's value.

## Behavior

- Setting `--llm-provider groq` prints an explicit disclosure before saving:
  that questions asked in chat and the code context cited in their answers
  will be sent to Groq's API. This mirrors this project's existing
  "warn, never silently proceed" style (`_warn_if_not_installed`) but is
  mandatory here, not just a warning — it always prints when switching to a
  remote provider, not only when something looks wrong.
- Setting `--llm-provider local` (or simply never setting `--llm-provider`)
  leaves chat behavior exactly as before this feature — the local engine,
  unchanged validation (`normalize_endpoint_url`'s local-only hostname
  check still applies to `--llm-endpoint`, completely unaffected by this
  feature).
- `repo-scanner config` (no flags, status display) now also reports which
  provider is active and, for `groq`, whether `GROQ_API_KEY` is set and the
  configured model is reachable — using the same `checkAvailability()`-based
  status reporting already used for the local engine and the embedding
  engine.
- `index`/`serve` build whichever engine is configured via
  `local_llm.create_llm_engine(config)` (contracts/llm-engine-interface.md)
  — no behavior change to `index`/`serve`'s own CLI flags.

## Non-goals

- No per-invocation override (e.g. `repo-scanner serve --llm-provider groq`)
  — provider selection is a persisted configuration choice, consistent with
  how model/endpoint selection already works via `repo-scanner config`, not
  a per-command flag.
- No support for a second remote provider in this feature — `llm-provider`
  accepts exactly `local` or `groq` today; adding another provider is a
  future extension, not blocked by this design (research.md Decision 5).

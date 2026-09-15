# T036 verification round, 2026-09-15 (owner-approved)

Groq-first `summaryChain` (`groq:openai/gpt-oss-120b` first). The config was
hash-checked against `%USERPROFILE%\.codepedia\config.backup-038.json` before
the round and restored byte for byte after it (SHA-256 `5434E0916BAF…CE769`
both times).

## Runs

| | Sample | Nextgen |
| --- | --- | --- |
| Index time | 18 s | 27 s |
| Summaries and embeddings | 276 carried forward, 552 reused, 0 computed | 1,013 carried forward, 1,000 reused, 0 computed |
| Model calls | the planner (cache key changed) and the Overview narrative (features changed) | same |
| Terminal `overview:` line | none | `6 of 8 subsystem paragraphs not written` (narrative variance, as in 038 Decision 19 run 1) |
| Traceback | none | none |
| Plan cached under the current grouping's key | yes, 8 features | yes, 13 named, 8 after repair |

A second run would make no planner call: the probe finds the saved plan under
the key of the current grouping, which is exactly what a second run reads
(owner-approved stand-in for a second paid re-index).

## Old addresses (SC-008)

All 19 feature addresses published before the round still open. Lists:
`t036-old-features-*.txt`; results: `t036-old-addresses-*.txt`.

- Sample: 12 addresses, 3 live, 9 redirect to a live page, 0 broken.
- Nextgen: 7 addresses, 0 live, 7 redirect to a live page, 0 broken.

## Largest feature with the model (recorded, not enforced; clarification Q5)

- Sample: "Public API Endpoints", 18 of 51 modules (35%), merging the two route groups.
- Nextgen: "Wallet Management", 38 of 109 modules (35%), merging backend and
  frontend wallet groups. "Authentication and Authorization" also spans both halves.

## Findings for the owner

- **Anchor ties after model merges.** A merged feature's two seeds often hold
  the same number of entry points, and the tie goes to the module name. So
  "Lending Management Service" is anchored at `email_gateway.py` and "Catalog
  Management Service" at `book.py`, not `lending_service` and
  `catalog_service`. SC-005's first sentence holds (both anchors are seeds);
  its sample example does not with the model. A tie-break by reach (the seed
  whose entry points reach the most modules) gives `lending_service` and
  `catalog_service`, and moves "Wallet Management" to `WalletServiceImpl.java`
  and "Client Management" to `clients.component.ts`. Computed by
  `tiebreak_probe.py` in the session scratchpad; nothing changed.
- **Owner decision:** adopt the reach tie-break (FR-010), then run a second
  round before T037.
- **Round 2** (after the reach tie-break), same swap and restore:
  - Model calls: one Overview narrative per repository. The plans were reused
    (`generated_at` unchanged).
  - No `overview:` line on either repository; nextgen's narrative now has
    every subsystem paragraph.
  - Model-merged anchors: `lending_service.py`, `catalog_service.py`,
    `WalletServiceImpl.java` and `clients.component.ts`.
  - **Defect exposed:** the second full re-index lost every redirect stub the
    first had written (9 sample, 7 nextgen), and aliases whose target had moved
    again led nowhere. Fixed as T036a (`DocGenerator._restore_redirects`).
- **Round 3** (repair after T036a), same swap and restore:
  - Model calls: none. Neither the plan nor the narrative row was rewritten.
  - All addresses resolve. The pre-039 list: sample 12 of 12, nextgen 7 of 7.
    The round-1 list: sample 17 of 17, nextgen 15 of 15. No alias is missing
    its stub (sample 11, nextgen 30).
  - Outputs: `t036a-check-*.txt`.
- **The CLI is filed as tooling.** The model put the CLI with the web API
  client under "Developer Tools" (kind `tooling`). 038 gives tooling features
  no subsystem paragraph.
- Probe outputs: `probe-sample.t036.txt`, `probe-nextgen.t036.txt`.

# Data Model: Narrative Overview Page

**Feature**: 038-narrative-overview-page | **Date**: 2026-09-10

All types are frozen, slotted dataclasses, matching `features/`. None holds an
engine. Only `OverviewNarrator` (contracts §2) touches one.

## In-memory types

### `FeatureBrief` — `overview/evidence.py`

One subsystem as described to the model.

| Field | Type | Rule |
| --- | --- | --- |
| `handle` | `str` | `f0`, `f1`, … in navigation order, assigned per call (as `planner.assign_handles`). Never part of a page id; persisted only inside the narrative cache's `handle_map_json` |
| `featureKey` | `str` | `Feature.key`, the page address. Never shown to the model |
| `title` | `str` | `Feature.title`, ≤ 60 chars (already guaranteed by `validate.MAX_TITLE_CHARACTERS`) |
| `description` | `str` | `Feature.description`, whitespace-collapsed, cut at a word boundary within 160 chars |
| `kind` | `str` | `Feature.kind` |
| `anchorName` | `str` | Anchor module's `display_label` |
| `anchorPath` | `str` | Anchor module's repo-relative POSIX path |
| `anchorSummary` | `str` | First sentence of the anchor's docstring, else of its generated summary, ≤ 120 chars; `""` if neither |
| `memberNames` | `tuple[str, ...]` | ≤ 3 member labels other than the anchor, in `Feature.members` order, each ≤ 50 chars |
| `entryPointCount` | `int` | `Feature.exposedEntryPointCount` |

### `EntryFlow` — `overview/evidence.py`

How one entry point moves through subsystems.

| Field | Type | Rule |
| --- | --- | --- |
| `qualifiedName` | `str` | `Class.name` or `name`, from `EntryPoint` |
| `kind` | `str` | `EntryPoint.kind`: `cli-command`, `api-route` or `function` |
| `modulePath` | `str` | Repo-relative path of `EntryPoint.moduleKey`'s module |
| `featureHandle` | `str` | Handle of the feature owning that module, or `""` if not among the prompted features |
| `reachedHandles` | `tuple[str, ...]` | Features reached, ordered by the minimum call depth at which any member is first reached (ties by handle), excluding its own feature, ≤ 5 |

Selection: entry points ranked by the number of distinct modules reached
(descending), then by `stableKey`. The first `MAX_PROMPTED_ENTRY_FLOWS` are kept.
The BFS is bounded by `features.evidence.MAX_EVIDENCE_CALL_DEPTH`.

### `OverviewEvidence` — `overview/evidence.py`

| Field | Type | Rule |
| --- | --- | --- |
| `repositoryName` | `str` | `Path(repository.rootPath).name` |
| `languages` | `tuple[str, ...]` | `repository.detectedLanguages`, sorted |
| `readmeLead` | `str` | First prose paragraph after the README's title, via `plain_text.excerpt`, ≤ `MAX_README_LEAD_CHARS`. The README's bullet list is deliberately **not** carried (research Decision 14) |
| `features` | `tuple[FeatureBrief, ...]` | First `MAX_PROMPTED_FEATURES` features in navigation order |
| `omittedFeatureCount` | `int` | `len(all features) - len(features)` |
| `entryFlows` | `tuple[EntryFlow, ...]` | ≤ `MAX_PROMPTED_ENTRY_FLOWS` |
| `majorFeatureKeys` | `tuple[str, ...]` | First ≤ `MAX_SUBSYSTEM_PARAGRAPHS` (8) features in navigation order whose `kind != "tooling"`. The subsystems that may receive a paragraph (User Story 2) |
| `featureTitles` | `tuple[tuple[str, str], ...]` | Every current feature as `(key, title)`, prompted or not, in navigation order. Grounding uses it to confirm a handle's feature still exists and to title its link |

`build_overview_evidence(features, bundle, graph, *, repository_root) ->
OverviewEvidence` is deterministic. Every collection is
sorted or taken in a defined order, and it performs no I/O except the README
read.

### `NarrativeReply` — `overview/narrator.py`

The model's answer, parsed but untrusted.

| Field | Type | Rule |
| --- | --- | --- |
| `lead` | `tuple[str, ...]` | From JSON `"lead"`, a list of strings. Non-strings are ignored |
| `subsystems` | `Mapping[str, str]` | From JSON `"subsystems"`, handle → string. Non-string values are ignored. Empty until User Story 2 asks for it |

`parse_narrative_reply(text) -> NarrativeReply | None`: extracts the first
`{…}` block (DOTALL), `json.loads`, and requires an object. `None` for
anything else. A reply with neither key, or with both empty, is `None`.

### `Segment` / `GroundedParagraph` — `overview/grounding.py`

| Type | Fields |
| --- | --- |
| `Segment` | `kind: Literal["text", "code", "feature"]`, `value: str`, `featureKey: str = ""` |
| `GroundedParagraph` | `segments: tuple[Segment, ...]`, `wordCount: int`, `sentenceCount: int` |

### `GroundedNarrative` — `overview/grounding.py`

| Field | Type | Rule |
| --- | --- | --- |
| `lead` | `tuple[GroundedParagraph, ...]` | ≤ 4 (G9) |
| `subsystems` | `tuple[tuple[str, GroundedParagraph], ...]` | `(featureKey, paragraph)` in navigation order, ≤ 8, keys ⊆ `majorFeatureKeys` |
| `rejected` | `tuple[Rejection, ...]` | Every dropped paragraph, with the first rule it failed (`G2`…`G10`) and the offending token. For the notice and for tests; never rendered |
| `leadWithheld` | `bool` | True when G10 withheld the lead because its opening paragraph failed |
| `isStale` | `bool` | True when grounded from an earlier-version reply (`NarrationOutcome.status == "stale"`); drives the `.summary-stale` caveat |

`ground(reply, evidence, lookup, *, handle_map, is_stale=False) ->
GroundedNarrative` is pure. `handle_map` resolves each `[[fN]]` to a feature
key. G3 then also requires that key to be among the current evidence's
features, so a stale reply's link to a subsystem that no longer exists rejects
its paragraph. An empty
`GroundedNarrative` (no lead, no subsystems) is the same value `ground(None, …)`
returns. So "no provider", "all paragraphs rejected" and "unparseable" converge
on one value before rendering, as `repair(None, …)` does for features.

`accept_description(text, evidence, lookup) -> str | None` applies G2, G4, G5
and G6 to one planned subsystem description (User Story 2 table). It returns
the description as a cell-safe string (whitespace collapsed, `mdesc`-escaped,
backticked names kept), or `None`, which the template renders as "—".

`render_paragraph(paragraph, feature_links) -> str` returns one Markdown line:
text segments are `mdesc`-escaped, code segments backticked, feature segments
rendered as `[mdesc(title)](relativePath)`. No `{: .ai-generated }`; the
template adds that.

### `NarrationOutcome` — `overview/narrator.py`

| Field | Type | Values |
| --- | --- | --- |
| `status` | `Literal[...]` | `cached` (a key hit, no call); `generated` (call succeeded and parsed); `stale` (no answer for the current key, so the repository's earlier reply is used, spec FR-017a); `unavailable` (`isAvailable()` false and no earlier reply); `failed` (`RuntimeError` from the chain and no earlier reply); `unparseable` (and no earlier reply); `skipped` (`narrateOverview=False`, silent; or no features, which gets a notice — spec edge case "no subsystems at all") |
| `skipReason` | `str` | For `skipped` only: `"structure-pass"` or `"no-features"`, which selects the notice (contract §7) |
| `reply` | `NarrativeReply \| None` | Present for `cached`, `generated` and `stale` |
| `handleMap` | `Mapping[str, str]` | Handle → feature key for the prompt that produced `reply`: the current evidence's for `cached`/`generated`, the stored map for `stale` |
| `staleReason` | `str` | For `stale` only: which of `unavailable`, `failed` or `unparseable` triggered it, for the notice |

## Persistent state

### `doc_overview_narratives` — new table in `doc-manifest.sqlite`

Added to `manifest_store.SCHEMA_STATEMENTS`. It needs no migration because
`_connect` replays the statements.

```sql
CREATE TABLE IF NOT EXISTS doc_overview_narratives (
    repository_id TEXT NOT NULL,
    narrative_key TEXT NOT NULL,
    reply_text TEXT NOT NULL,
    handle_map_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (repository_id)
)
```

| Rule | Why |
| --- | --- |
| One row per repository; a save overwrites | As `doc_feature_plans`. `load` matches `narrative_key`, so a key hit is always the answer to *this* prompt. Only `load_latest`, the FR-017a fallback, ignores the key, and its result is always shown as earlier-version |
| `handle_map_json` stores `{handle: featureKey}` for the prompt that produced the reply | A stale reply's `[[fN]]` handles must be mapped through the numbering *it* was given, not the current evidence's (research Decision 13) |
| `reply_text` is the raw model reply, not the grounded result | Grounding is re-run on every load against the current lookup, so a changed rule or a removed symbol takes effect with no new call (research Decision 6) |
| Saved only when the reply parses | An unparseable reply is retried next run; a parseable one is final for its key, which is what makes reruns identical (research Decision 7) |
| `generated_at` is never read back into a page | Timestamps stay out of `index.md` |
| Carried into a fresh `index` by `_carry_forward_doc_manifest` | Already copies the whole database, so no code change |

`DocPageManifestStore` gains three methods:

- `load_overview_narrative(repository_id, narrative_key) -> tuple[str, dict] | None`
- `load_latest_overview_narrative(repository_id) -> tuple[str, dict] | None`
- `save_overview_narrative(repository_id, narrative_key, reply_text, handle_map) -> None`

A load that raises, or finds unreadable JSON, is treated as a miss and never
causes a crash, as in `planner._load_cached`.

### Unchanged identities

`links.HOME_PAGE_ID == "home"`, `HOME_OUTPUT_MARKDOWN == "index.md"`, and
`HOME_OUTPUT_HTML == "index.html"`. The home `DocPage` keeps `kind="home"`,
`relatedSymbols` and `contentSymbolIds` as today. `links` gains every feature
link used in the prose, which is a subset of the feature links it already
carries. So `manifest_store`, `search_index`, `cross_references` and
`impact._add_referrers_of` see no new page kinds or ids.

## Constants

| Constant | Value | Module | Reason |
| --- | --- | --- | --- |
| `PROVIDER_TOKEN_BUDGET`, `CHARS_PER_TOKEN` | 8000, 4 | `features/__init__` (re-exported) | Single source; the test must not import the module that could move them |
| `SYSTEM_PROMPT_CHARS` | 1400 | `overview/narrator.py` | Asserted ≥ `len(SYSTEM_PROMPT)` |
| `HEADER_CHARS` | 300 | `overview/narrator.py` | Repository name, languages, subsystem count, how to read entry lines (200 in the plan; research Decision 14) |
| `MAX_README_LEAD_CHARS` | 600 | `overview/evidence.py` | ~150 tok |
| `MAX_PROMPTED_FEATURES` | 12 | `overview/evidence.py` | 12 × 710 = 8,520 chars |
| `FEATURE_BLOCK_CHARS` | 710 | `overview/narrator.py` | 80 + 160 + 160 + 120 + 3 × 50 + 40 |
| `MAX_PROMPTED_ENTRY_FLOWS` | 6 | `overview/evidence.py` | |
| `ENTRY_FLOW_CHARS` | 240 | `overview/narrator.py` | |
| `MAX_NARRATIVE_RESPONSE_TOKENS` | 1400 | `overview/narrator.py` | 600 words ≈ 800 tok + JSON/handles ≈ 150, with margin |
| `NARRATIVE_FORMAT_VERSION` | `"1"` | `overview/narrator.py` | Bumped by User Story 2's schema change |
| `MAX_LEAD_PARAGRAPHS` | 4 | `overview/grounding.py` | FR-005 |
| `MAX_SUBSYSTEM_PARAGRAPHS` | 8 | `overview/grounding.py` | FR-025 |
| `MAX_SUBSYSTEM_SENTENCES` | 3 | `overview/grounding.py` | FR-025 |
| `MAX_NARRATIVE_WORDS` | 600 (exclusive) | `overview/grounding.py` | FR-005a |
| `BANNED_PROMOTIONAL_TERMS` | frozenset | `overview/grounding.py` | FR-013; the maintained list the spec's Assumptions refer to |
| `MAX_MODULE_DESCRIPTION_CHARS` | 160 | `plain_text.py` | User Story 4 row length |

## State transitions

The narrative for one repository, per generation pass:

```text
                ┌── narrateOverview=False or no features ─────────────► skipped
evidence ─► key ┤
                ├── cache hit (key matches) ──────────────────────────► cached
                └── miss ─► isAvailable? ── no ──┐
                                │ yes            │
                                ▼                │
                             run(...) ─ RuntimeError ──┤
                                │ value          │
                                ▼                │
                             parse ── None ──────┤
                                │ reply          ▼
                                │         load_latest(repo)?
                                │           │ row        │ none
                                │           ▼            ▼
                                │         stale     unavailable | failed | unparseable
                                ▼
                     save(key, raw, handles) ─► generated

cached | generated | stale ─► ground(reply, handle_map, is_stale) ─► render
unavailable | failed | unparseable | skipped ─► ground(None) ─► render (no prose)
```

Every path ends at `ground(...)`, and every path yields a page. Only `stale`
renders the earlier-version caveat, and only if at least one paragraph survived
grounding. A stale reply that grounds to nothing renders exactly as no prose,
with no caveat.

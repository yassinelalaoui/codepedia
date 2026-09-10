# Implementation Plan: Narrative Overview Page

**Branch**: `038-narrative-overview-page` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/038-narrative-overview-page/spec.md`

## Summary

The Overview page is `home.md.jinja`, 57 lines of counts, a table of module
tallies, an unreadable inline class diagram, and two lists. This feature puts
explanation above it. The Overview gains:

- up to four paragraphs saying what the repository is, which subsystems make it
  up, and how work moves through them;
- from User Story 2, a subsystems table with a responsibility and a starting
  module for each subsystem;
- from User Story 4, a module list that reads cleanly.

The narrative follows the `features/` package's shape exactly: **one bounded
call, a deterministic model-free acceptance pass, and failure that costs prose
and never structure**. It lives in a new `src/doc_generator/overview/` package,
where only `narrator.py` accepts an engine. `evidence.py` and `grounding.py`
refuse one by signature.

Four findings from Phase 0 shape the design. Each is argued in
[research.md](./research.md):

1. **The planner's call cannot carry the narrative** (Decision 1). It runs
   *before* repair, so it names features that may not survive. Folded in, it
   would cost **8,055 tokens, over the 8,000 budget**. One unreadable answer
   would also lose the navigation along with the prose.
2. **One call for the page, not one per section** (Decision 2). The worst case,
   computed from constants, is **4,465 tokens (44.2% headroom)**, revised from
   the planned 4,815 when the README bullets left the prompt (Decision 14). Nine
   per-section calls would be about 13,500 tokens, 1.7× the per-minute window.
   Grounding already accepts or rejects each paragraph independently, which is
   the degradation per-section calls would have bought.
3. **The narrative's cache key is a hash of the exact prompt**, and grounding is
   **re-run on every render** against the current symbol lookup (Decisions 6
   and 7). An unchanged repository hits the cache and regenerates identical
   Markdown. An edit that removes a cited symbol drops that paragraph on the
   next pass, with no new call. This requires computing the home page on every
   incremental pass and writing it only when its content hash changes. Today it
   only regenerates on navigation changes, which would leave prose naming
   deleted code.
4. **"Byte-identical" was impossible before this feature** (Decision 9). The
   Overview prints `lastIndexedAt`, which is reset to `now()` every run, and
   every page's footer stamps `generated_at`. The `Last indexed` line leaves the
   page's content (the footer already shows the time), and identity is
   specified on content. The spec was amended for this and for every other
   contradiction or gap found during planning and the narrative checklist. Each
   is listed in research, Spec amendments, and the degraded-page behaviour is
   argued in research Decision 13.

**Release scope**: User Stories 1, 2 and 4. User Story 3 (getting started) is
deferred, but its design is fixed now. It is fully deterministic and involves no
model (research Decision 5).

## Technical Context

**Language/Version**: Python 3.13. The venv must be 3.11–3.13, because 3.14
hangs in Pydantic schema generation. Jinja2 templates. One CSS rule in
`frontend/src/styles.css`, rebuilt into `src/doc_generator/assets/wiki-ui.css`
with `npm run build` (vite).

**Primary Dependencies**: None added. The narrator reuses
`local_llm.PromptEnvelope` and the `provider_routing.FailoverExecutor` the CLI
already hands `FeaturePlanner`. Grounding reuses
`cross_references.resolve_reference`. User Story 3, when it ships, uses stdlib
`tomllib` and `json`.

**Storage**: SQLite, the existing `doc-manifest.sqlite`. One new table,
`doc_overview_narratives`, one row per repository and shaped like
`doc_feature_plans`. It needs no migration, because `_connect` replays
`SCHEMA_STATEMENTS`. `_carry_forward_doc_manifest` already copies it into a
fresh `index`.

**Testing**: pytest, run as `pytest --basetemp=<scratchpad> -p no:cacheprovider`.
Every new module except `overview/narrator.py` is tested with no engine at all.
The narrator is tested with fake engines covering available, unavailable,
`RuntimeError`, empty and unparseable replies. The budget ceiling is computed
from constants, as in `test_feature_planner.py`.

**Target Platform**: A local CLI generating a static wiki, read over `file://`
or the local server. The generated page makes no runtime requests.

**Project Type**: A single-project Python CLI with a vendored frontend bundle.

**Performance Goals**:

- At most one model call per narrative cache miss, and zero on an unchanged
  repository.
- Recomputing the home page on every incremental pass stays in-memory: markdown
  and HTML render for one page, plus a cache lookup.

**Constraints**:

- Each call must fit an 8,000-token window, using `CHARS_PER_TOKEN = 4`.
- Degradation is never fatal and never partial.
- An unchanged repository produces identical `index.md`.
- Page identity (`home`, `index.md`, `index.html`) is fixed.
- Nothing reaches beyond `127.0.0.1` except through `provider_routing`.

**Scale/Scope**:

- The prompt is bounded by construction at 12 features, 6 entry flows, a
  600-char README lead and 1,500 chars of README bullets, whatever the
  repository's size.
- Reference repositories: `codepedia-sample-repo` (43 Python files, 8 of them
  `__init__.py`, plus JS/TS and three Markdown documents) and this repository
  (about 135 modules under `src/`, 033 research).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Applies? | Assessment |
| --- | --- | --- |
| **2.1** Remote engine by default, local mode explicit | **Yes** | The narrator consumes a model through **the executor already built for the summary chain**, the same one `FeaturePlanner` receives. It adds no configuration surface and no new default. The set of stages that reach a model is unchanged, so disclosure is unchanged. Local-only mode works exactly as it does for summaries. |
| **2.2** Zero network exposure by default | **Yes — neutral** | No server, port or runtime request. The page stays static. |
| **2.3** Failover only within the configured chain, never silent | **Yes** | The call goes through `FailoverExecutor.run`, which logs every switch to `engine_failover_log`. It catches `RuntimeError` only, so a wiring bug stays loud. An omitted or reduced narrative prints one `overview:` line (contract §7), and is never silent. |
| **2.4** Traceability of AI answers | **Yes — central** | **Every generated paragraph must cite at least one file, module or symbol that resolves (G7, spec FR-007)**; a subsystem link alone does not count. Every backticked name in the prose must resolve through `resolve_reference` to exactly one symbol (G4), which renders as a link to it. Identifier-shaped names outside backticks must resolve too (G5). Subsystems are referenced by handles and rendered as links (G3). Every generated paragraph is marked `.ai-generated`, and a generated table column is labelled. |
| **2.5** Exact incremental reindexing | **Yes — central** | The key is the hash of the exact prompt. Grounding re-runs on every render. The home page is always recomputed incrementally but written only when its content hash changes. No summary re-computation and no whole-wiki rebuild are added. The narrator runs only in passes where summaries exist, so an `index` spends at most one call rather than one per pass. |
| **2.6** Minimal infrastructure | **Yes** | One table in an existing SQLite file. No new dependency, file or service. |
| **2.7** Analysed repository read-only | **Yes** | The README is *read* (already done by `features.evidence`). User Story 3 reads `pyproject.toml`, `package.json` and `Makefile`. Nothing is written outside the state directory. |

**Gate result, pre-research**: PASS. No violations, so Complexity Tracking stays
empty.

**Gate result, post-design**: PASS. The design adds exactly what the table
describes. Decisions 7 and 9 strengthen 2.5 beyond today's behaviour: the home
page now tracks content changes, and `serve` no longer rewrites an unchanged
page.

## Project Structure

### Documentation (this feature)

```text
specs/038-narrative-overview-page/
├── spec.md                       # amended during planning (research: Spec amendments)
├── plan.md                       # this file
├── research.md                   # Decisions 0–12
├── data-model.md                 # types, table, constants, state machine
├── quickstart.md                 # manual + automated validation
├── contracts/
│   └── overview-narrative.md     # package API, prompt/reply, page outline, notice
├── checklists/
│   └── requirements.md
└── tasks.md                      # /speckit-tasks
```

### Source Code (repository root)

```text
src/doc_generator/
├── overview/                     # NEW package — User Stories 1, 2
│   ├── __init__.py               # invariant docstring; re-exports PROVIDER_TOKEN_BUDGET, CHARS_PER_TOKEN
│   ├── evidence.py               # build_overview_evidence, read_readme_lead — NO engine
│   ├── narrator.py               # OverviewNarrator, prompt, key, parse, budget — the ONLY engine-taker
│   └── grounding.py              # ground, render_paragraph, G1–G9, BANNED_PROMOTIONAL_TERMS — NO engine
├── features/evidence.py          # + find_readme() (pure refactor of _README_CANDIDATES lookup)
├── plain_text.py                 # NEW — excerpt(): markdown → plain text, sentence/word cut (User Story 4, README lead)
├── prose.py                      # + disambiguated_labels() (User Story 4)
├── generator.py                  # keep RepositoryEvidence; narrate; always-compute-home; narrateOverview flag;
│                                 #   drop classDiagramSource from home; onNotice; module-list label/description
├── manifest_store.py             # + doc_overview_narratives table, load/save_overview_narrative
├── templates/home.md.jinja       # lead block; drop Last indexed + inline mermaid; row shape (User Story 4); table (User Story 2)
├── __init__.py                   # export OverviewNarrator
└── __pycache__/section_narrator.*.pyc   # DELETE (stale, sourceless)

src/cli/
├── index_command.py              # wire OverviewNarrator + onNotice; narrateOverview=False on the structure pass
└── serve_command.py              # wire OverviewNarrator + onNotice

frontend/src/styles.css           # adjacent .ai-generated siblings join into one block → npm run build
src/doc_generator/assets/wiki-ui.css   # rebuilt output

tests/unit/
├── test_overview_package.py      # engine-free invariant by inspection
├── test_overview_evidence.py     # bounds, ordering, flows, README lead, determinism
├── test_overview_narrator.py     # budget from constants; cache-before-availability; all failure outcomes; key stability
├── test_overview_grounding.py    # one test per G-rule; fabricated symbol; structural-injection reply
├── test_plain_text.py            # excerpt rules (User Story 4)
├── test_prose_labels.py          # disambiguated_labels (User Story 4)
└── test_doc_generator_home_overview.py   # updated: no inline mermaid, no Last indexed
tests/integration/
└── test_overview_page.py         # no-engine outline identity (4 modes); byte-identical rerun;
                                  #   removed symbol drops paragraph; serve does not rewrite; CLI wiring

docs/architecture.md              # overview/ package, new table (its "> Maintenance:" rule)
docs/diagrams/class-diagram.md    # OverviewNarrator & friends (its "> Maintenance:" rule)
README.md                         # what the Overview page now contains
```

**Structure Decision**: a single project. The new package sits beside
`features/` because it is the same kind of component, and deliberately not
inside it (research Decision 1). The User Story 4 repairs live outside
`overview/` in `plain_text.py`, `prose.py` and the template, so they ship with
no dependency on the narrator.

### How the stories map to the code

| Story | Needs | Independent of |
| --- | --- | --- |
| **US1** lead | `overview/*`, manifest table (with `handle_map_json`), generator wiring, `home.md.jinja` lead block, **opening-paragraph rule G10 (FR-010a)**, **earlier-version fallback and `.summary-stale` caveat (FR-017a)**, the `Last indexed` and inline-Mermaid removals, **Features list reduced to titles (FR-012a)**, CSS rule, CLI wiring, `plain_text.excerpt` (for the README lead only) | US2, US4 |
| **US2** subsystems | US1's narrator and grounding, extended: `"subsystems"` key, `NARRATIVE_FORMAT_VERSION` → `"2"`, table rows replacing the Features list, per-subsystem paragraphs published one at a time in table order (G11, FR-025a), header-labelled generated column filled through `grounding.accept_description` (FR-009, FR-021). The table alone needs no narrator | US4 |
| **US4** module list | `plain_text.excerpt`, `prose.disambiguated_labels`, template row shape | US1, US2 (no model, no narrator import) |
| **US3** getting started | `getting_started.py` (deterministic) + template section | deferred |

`plain_text.excerpt` is shared by US1 (README lead) and US4. It is a
dependency-free leaf, so whichever story lands first adds it.

## Complexity Tracking

No constitution violations to justify.

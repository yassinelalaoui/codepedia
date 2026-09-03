# Implementation Plan: Feature Navigation in the Generated Wiki

**Branch**: `033-feature-navigation` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/033-feature-navigation/spec.md`

## Summary

The wiki's navigation is directory clustering wearing an LLM-supplied name.
`sections.py` groups modules by repository-relative directory, absorbs small
directories, splits large ones by label propagation, and `section_narrator.py`
spends one model call per group to name it. It answers "where does this code
live" and never "what does this repository do".

The replacement is a four-stage pipeline in a new `src/doc_generator/features/`
package, of which **only the third stage may fail**:

1. **evidence** — per module: which entry points reach it, what it exports, its
   summary, its path. Plus the README's stated capabilities. No model.
2. **candidates** — provisional groups seeded from entry-point modules and grown
   by bounded reachability, then consolidated. Every module lands in exactly one.
   No model.
3. **planner** — **one** call that organises the candidates into named features.
   Exchanges short ordinal handles, assigns candidates rather than modules.
4. **validate** — deterministic repair of the answer. No model.

With no model reachable the wiki builds and navigates identically, with plainer
titles: stages 1, 2 and 4 are the whole structure, and stage 3 only supplies
names. Feature pages replace section pages outright — `kind="section"` disappears.

Three Phase 0 measurements shape the design, two of them corrections to the
approved technical input:

1. **Reachability saturates at depth 2, not 4.** Average module degree is 8.99;
   at depth 2 a seed reaches 132 of 135 modules, at depth 3 all of them. Run at
   the input's `MAX_ATTACH_DISTANCE = 4`, the candidate stage produces one
   64-module candidate and 41 singletons — worse than what it replaces. The bound
   is **2** (research Decision 2).
2. **The traversal-cost argument for avoiding `build_entry_point_call_sequence`
   was wrong** — it runs in 8 ms over all 167 entry points, not "millions of
   steps". The decision stands on the correct reason: it has no visited set by
   design, so it answers the wrong shape of question (research Decision 1).
3. **Anchor drift is the common case, not an edge case.** Six of eleven measured
   groups are one import edge away from a different anchor, one an exact tie.
   Since a feature's key *is* its anchor module key, the alias table and redirect
   stubs are load-bearing, and they must land before anything renders a feature
   page (research Decision 6).

## Technical Context

**Language/Version**: Python 3.13 (venv must be 3.11–3.13; 3.14 hangs in Pydantic
schema generation). Jinja2 templates. No frontend change at all — the sidebar
markup simplifies, but `frontend/src` and the built `wiki-ui.{js,css}` are
untouched.

**Primary Dependencies**: None added. The planner reuses `local_llm.PromptEnvelope`
and the `provider_routing.FailoverExecutor` the CLI already hands the generator.

**Storage**: SQLite, via the existing `doc-manifest.sqlite`. Two new tables
(`doc_page_aliases`, `doc_feature_plans` + `doc_features`) added to
`SCHEMA_STATEMENTS`; `doc_section_narrations` is dropped. No migration step —
`_connect` replays the schema on every connection (research Decision 7).

**Testing**: pytest. `pytest --basetemp=<scratchpad> -p no:cacheprovider` — a bare
run reports ~17 spurious `PermissionError`s on this machine. Every new module
except `planner.py` is tested with no model available at all, enforced by
signature rather than by convention (research Decision 10).

**Target Platform**: Local CLI generating a static wiki read over `file://` or the
local server. Offline throughout.

**Project Type**: Single Python project — a documentation generator with a CLI.

**Performance Goals**: One model call per distinct repository structure, cached;
zero on an unchanged regeneration. The deterministic stages are in-memory graph
work: measured at 8 ms for the reachability walk over 167 entry points.

**Constraints**: The single planning call must fit inside 8000 TPM with headroom —
measured worst case 6,145 tokens, 23.2% spare (research Decision 5). Incremental
regeneration preserved. The analysed repository stays read-only.

**Scale/Scope**: Probe subject is this repository: 135 modules, 2416 graph nodes,
4801 edges, 167 entry points across 52 modules, 15 sections today. New package of
five modules; ~12 existing source files touched by the A4 rename; 5 test files
reworked, 7 added.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Assessed against constitution v3.0.0.

| Principle | Applies? | Assessment |
| --- | --- | --- |
| **2.1** Remote engine by default, local mode explicit | **Yes** | The planner consumes a model. It introduces no new configuration surface and no new default: it takes whatever executor the CLI already built for the summary chain, exactly as `SectionNarrator` does today. Disclosure is unchanged because the set of stages that reach a model is unchanged — one navigation-naming call replaces N of them. |
| **2.2** Zero network exposure by default | **Yes — neutral** | No server, no port, no new asset. The redirect stub is a static local file; a `<meta http-equiv="refresh">` to a relative path makes no network request. |
| **2.3** Automatic fallback within a configured chain | **Yes — preserved** | The call goes through `llmEngine.run(...)`, which *is* the configured chain, so failover and its visibility come for free. No second route to a model is created — FR-033, pinned by a test that the planner has exactly one call site. |
| **2.4** Traceability of AI answers | **Yes — preserved and narrowed** | A feature's title and description are AI-written and must be marked as such, as section descriptions are today (`{: .ai-generated }`). The *membership* they describe is deterministic and not AI-derived, which is a stronger traceability position than today's, where the model named a group it also could not have justified. |
| **2.5** Incremental re-indexing | **Yes — preserved** | `impact.py` keeps driving regeneration; its five section reads become feature reads. One deliberate exception: detecting a manifest from the previous scheme forces a single full rebuild (FR-023), which is the same escape hatch the template-fingerprint fix uses and for the same reason. |
| **2.6** Minimal infrastructure, local storage | **Yes — neutral** | Two new SQLite tables in the database that already exists. No new store, no new file format. |
| **2.7** Analysed repository read-only | **Yes — neutral** | `evidence.py` reads `README.{md,rst,txt}` from the analysed repository. A read, which 2.7 permits; it forbids writes. Output still goes only to the separate docs directory. |

**Initial gate: PASS.** No violations, so the Complexity Tracking section is
removed rather than left empty.

### Post-Design Re-check (after Phase 1)

- **2.3 confirmed.** The contract's § 3 fixes the planner's single call site
  verbatim from `section_narrator.py:151`, including catching `RuntimeError` and
  not `Exception` — an `AttributeError` there is a wiring bug that must stay
  loud, not masquerade as an unreachable provider.
- **2.5 confirmed, and strengthened.** `data-model.md` records that the plan cache
  key is the repository *structure* (sorted module keys + sorted entry-point
  stable keys), not a content hash — so summaries landing between the two
  regenerations per index do not invalidate it. Without that, the incremental
  guarantee would hold for pages but not for model calls.
- **2.4 confirmed.** The contract requires `isPlanned` on a feature to gate the
  `{: .ai-generated }` marker, mirroring `isNarrated` today. A feature that fell
  back to its deterministic title must not be marked AI-generated.
- **2.7 re-checked against the new README read.** The contract states the read is
  best-effort and never raises: an unreadable README degrades the prompt, never
  the run.
- **No new gate triggered.** The design added no provider, no port, no store.

**Post-design gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/033-feature-navigation/
├── plan.md              # This file
├── spec.md              # 5 user stories, 34 FRs, 10 SCs
├── research.md          # Phase 0 — 10 decisions, each with a named probe
├── data-model.md        # Phase 1 — entities, constants, storage, page identity
├── quickstart.md        # Phase 1 — unit / generated-wiki / manual, in that order
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
├── contracts/
│   └── feature-navigation.md   # Phase 1 — the five module boundaries + unchanged surfaces
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/doc_generator/
├── features/                 # NEW package
│   ├── __init__.py
│   ├── evidence.py           # A1  no model
│   ├── candidates.py         # A1  no model
│   ├── fallback.py           # A1  no model — today's clustering, moved
│   ├── planner.py            # A3  the one call
│   └── validate.py           # A3  no model
├── sections.py               # DELETED — split into features/fallback.py + candidates.py
├── section_narrator.py       # DELETED — replaced by features/planner.py + validate.py
├── links.py                  # A2  feature_page_id / feature_slug / feature_output_paths
├── manifest_store.py         # A2/A3  alias table, feature-plan tables
├── writer.py                 # A2  write_redirect_stub
├── generator.py              # A2/A4  identity, alias recording, rename, flat nav
├── impact.py                 # A4  five section reads become feature reads
├── html_render.py            # A4  NavSection/NavModule collapse to NavFeature
├── mermaid_diagram.py        # A4  build_feature_diagram_mermaid_source
├── models.py                 # A4  PageKind "section" -> "feature"
└── templates/
    ├── section.md.jinja      # A4  -> feature.md.jinja
    └── layout.html.jinja     # A4  <details> tree -> flat list

src/cli/index_command.py      # A4  SectionNarrator -> FeaturePlanner
src/cli/serve_command.py      # A4  same
src/doc_generator/__init__.py # A4  exports

tests/
├── unit/
│   ├── test_feature_evidence.py      # NEW  A1
│   ├── test_feature_candidates.py    # NEW  A1
│   ├── test_feature_fallback.py      # from test_sections.py, A1
│   ├── test_page_aliases.py          # NEW  A2
│   ├── test_feature_planner.py       # NEW  A3
│   ├── test_feature_validate.py      # NEW  A3
│   ├── test_sections.py              # DELETED
│   ├── test_section_narrator.py      # DELETED
│   ├── test_impact.py                # A4
│   ├── test_mermaid_diagram.py       # A4
│   └── test_doc_generator_home_overview.py   # A4
└── integration/
    ├── test_feature_page_identity.py       # NEW  A2
    ├── test_section_manifest_migration.py  # NEW  A4
    ├── test_feature_pages.py               # from test_section_pages.py, A4
    ├── test_feature_navigation.py          # from test_section_navigation.py, A4
    ├── test_doc_generator_export.py        # A4
    └── test_doc_generator_links.py         # A4
```

**Structure Decision**: A new `features/` sub-package rather than five more
modules at `doc_generator/` top level. The four stages have a strict dependency
order and exactly one of them may fail; a package boundary is what lets the
"no module here except `planner.py` may take an engine" rule be checked by
reading one directory. `fallback.py` receives `_build_import_adjacency`,
`_absorb_small_directories` and `_label_propagation` from `sections.py`
**unchanged**, so the diff shows a move rather than a rewrite and the clustering
tests that still describe live behaviour keep their assertions.

## Phase order and why

`A1 → A2 → A3 → A4`, and the ordering is not arbitrary:

- **A1 first** because navigation is LLM-free and verifiable at the end of it.
  Everything after is naming and rendering.
- **A2 second, before anything renders a feature page.** This is the measured
  consequence of research Decision 6: with six of eleven anchors one edge from
  moving, publishing a feature URL before the alias table exists means shipping
  URLs that the first refactor breaks. Never publish an unstable URL.
- **A3 third**, wired to its fallback from the first line rather than bolted on.
- **A4 last**, because it is a ~12-file rename whose missed call sites fail at
  runtime rather than at import. `grep -rn "section" src/ tests/` is the
  completeness check, and the CLI/serve wiring is the easiest site to miss.

# Feature Navigation Contract

## Purpose

Define the boundaries this feature introduces and the ones it deletes. Five new
modules under `src/doc_generator/features/`, three changed existing modules with
new public functions (`links.py`, `manifest_store.py`, `writer.py`), and one wide
rename across the rendering path.

The single most important clause in this document is § 6, **Unchanged surfaces**.
This feature removes the sidebar's module tree, so a module's only remaining doors
are the feature page and the search index — both of which already work today and
must be *pinned*, not modified.

---

## 1. `features/evidence.py`

### `build_repository_evidence(bundle, graph, *, repository_root) -> RepositoryEvidence`

**Takes no engine argument.** Not an optional one defaulting to `None` — none at
all. A module that cannot accept an engine cannot have a hidden model dependency
(research Decision 10). This applies to every function in §§ 1, 2 and 5.

Expected behaviour:

- Emits **exactly one** `FeatureEvidence` per entry in `bundle.files`, including
  modules with no entry points, no exports and no summary. `candidates.py` must
  be able to place every module (FR-001); a missing evidence row would make that
  impossible and would fail silently as a module absent from the navigation.
- `reachingEntryPointKeys` is computed by BFS over `graph.functions_called_by`
  **with its own visited set**, bounded at `MAX_EVIDENCE_CALL_DEPTH`.
  - MUST NOT call `build_entry_point_call_sequence`. That walk has no visited set
    on purpose ([entry_point_diagram.py:147](../../../src/doc_generator/entry_point_diagram.py#L147))
    because a sequence diagram must draw a repeated call twice.
  - `identify_entry_points` **is** reused, unchanged.
- Returns sorted tuples throughout, so two runs over an unchanged repository
  produce equal values (FR-002).

### README reading

- Reads `repository_root/README.md`, `.rst`, then `.txt` — first match wins.
- **Never raises.** A missing, unreadable, non-UTF-8 or empty README yields `()`.
  An unreadable README degrades the prompt, never the run.
- Truncates to `MAX_README_PROMPT_CHARS` at a line boundary.
- MUST NOT call `chat.retrieval.read_readme_content`: its candidate list omits
  `.md` deliberately ([retrieval.py:25](../../../src/chat/retrieval.py#L25)), and
  `.md` is the case that matters here (research Decision 8).
- Read only. No write to the analysed repository, ever (constitution 2.7).

---

## 2. `features/candidates.py`

### `build_candidates(evidence, graph, *, repository_root) -> tuple[Candidate, ...]`

**The partition invariant is this module's entire contract**: the union of all
`memberKeys` equals the set of every module key in the repository, and the
intersection of any two candidates is empty (FR-001). Every downstream guarantee
rests on it — the repair table in § 5 is safe *only* because a candidate is
indivisible and total.

Expected behaviour:

- One seed per distinct entry-point module; entry points sharing a module share
  a seed (FR-005).
- Attach by `1 / (1 + distance)` over the undirected import adjacency, BFS-bounded
  at `MAX_ATTACH_DISTANCE = 2`. Ties break on `(-score, seedModuleKey)`.
  - **The bound is 2, not 4.** At 4 the relation saturates — every seed reaches
    every module — and the stage degenerates to one 64-module candidate plus 41
    singletons (research Decision 2). A test pins the constant; the A1
    verification script re-measures the size distribution.
- Consolidate: candidates below `MIN_CANDIDATE_MODULES` fold into the
  highest-scoring candidate that reaches their modules; survivors capped at
  `MAX_PROMPTED_CANDIDATES`, ranked `(-len(memberKeys), seedModuleKey)`, remainder
  folded the same way (FR-007).
- Modules reached by no seed go to `features/fallback.py` (§ 3), and each cluster
  becomes a candidate (FR-008).
- **Deterministic.** No `set` iteration order reaches the output; every ordering
  is an explicit `sorted(...)`.

### Handles

`handle` is assigned by position **at prompt-construction time**, in
`planner.py`, not here. It is not part of a candidate's identity, never reaches
storage, and never appears in a page id. A candidate built by this module has an
empty handle until the planner numbers it.

---

## 3. `features/fallback.py`

Receives `_build_import_adjacency`, `_absorb_small_directories`,
`_label_propagation`, `_lead_member`, `_split_group` and their constants from
`sections.py` **unchanged**. This is a move, not a rewrite: the diff should show
relocated code, and `tests/unit/test_feature_fallback.py` should keep
`test_sections.py`'s assertions that still describe live behaviour.

- `build_fallback_groups(evidence, graph, *, repository_root)` returns clusters
  for the modules handed to it — not for the whole repository.
- On a real indexing run this path handles **every prose file**, because
  `identify_entry_points` skips prose outright
  ([entry_point_diagram.py:80-86](../../../src/doc_generator/entry_point_diagram.py#L80-L86)).
  It is not a rare branch (research Decision 9). Its test fixture must contain
  prose; this repository's `src/` tree has none and would not exercise it.

---

## 4. `features/planner.py` — the only module that touches a model

### `class FeaturePlanner`

Constructor mirrors `SectionNarrator` exactly: `(llmEngine, *, cache=None,
repositoryId="")`. `llmEngine` is duck-typed as `Any` for the reason
`CodeSummaryPipeline` does the same — the CLI hands over a
`provider_routing.FailoverExecutor`, and `doc_generator` sits below
`provider_routing` in the dependency graph.

### `plan(candidates, evidence) -> tuple[Feature, ...]`

- Consults the cache first, keyed on `sha1(sorted moduleKeys + sorted entry-point
  stableKeys)`. A cache hit makes **zero** calls (FR-016).
- Makes **at most one** call, ever. Not one per candidate, not a retry, not a
  repair call (FR-009). Pinned by a test counting invocations on a recording
  engine.
- The call is verbatim in shape:

  ```python
  failover_result = self.llmEngine.run(lambda engine: engine.generate(prompt))
  ```

  through `run`, never `generate` — the executor exposes the chain
  (`isAvailable`, `run`, `stream`, `result`), not the engine's methods
  ([section_narrator.py:151](../../../src/doc_generator/section_narrator.py#L151)).

- Catches `RuntimeError` **only**, and returns the deterministic fallback.
  Deliberately not `Exception`: `FailoverExhaustedError`, `LocalLLMError` and
  `RemoteLLMError` are all `RuntimeError`s, while an `AttributeError` means the
  engine was called with a method it does not have — a wiring bug that must stay
  loud rather than masquerade as an unreachable provider.
- `isReady()` returning `False`, an exception, an empty answer and an unparseable
  answer are **all the same outcome**: the deterministic candidates, one feature
  per candidate under its `seedTitle`, `isPlanned=False` (FR-017, FR-030).

### Prompt shape

- Carries: candidate lines (handle, seed title, member count, up to
  `MAX_MEMBERS_PER_CANDIDATE` members each with a summary truncated to
  `MAX_MEMBER_SUMMARY_CHARS`), README bullets, and `TARGET_FEATURE_COUNT`.
- **Never carries a `moduleKey`.** Measured at mean 116.6 chars ≈ 29 tokens;
  135 of them is 3,936 tokens of identifiers before a word of prose
  (research Decision 4). A test asserts no module key appears in the rendered
  prompt text — the cheapest possible guard against this regressing.
- Requests strict JSON: `[{title, description, kind, memberCandidateIds}]`.

### The budget assertion

`test_feature_planner.py` MUST compute the worst-case prompt size **from the
constants** and fail if it exceeds the budget. It must not hard-code 6,145 — a
test that restates the answer cannot catch a constant being raised. Concretely:

```
MAX_PROMPTED_CANDIDATES * (HEADER + MAX_MEMBERS_PER_CANDIDATE * (MEMBER + MAX_MEMBER_SUMMARY_CHARS))
  + MAX_README_PROMPT_CHARS + SYSTEM_PROMPT_CHARS
  ) / CHARS_PER_TOKEN + MAX_PLAN_RESPONSE_TOKENS  <=  PROVIDER_TOKEN_BUDGET
```

`CHARS_PER_TOKEN = 4` is deliberately pessimistic (real English ≈ 4.5, and member
lines are mostly identifiers, which tokenise worse), so the assertion fails early
rather than in production.

---

## 5. `features/validate.py` — deterministic repair, no model

### `repair(plan, candidates) -> tuple[Feature, ...]`

Takes no engine. Every rule below is exercised on hand-written input, so every
row of the table has its own test.

| Anomaly | Treatment | FR |
| --- | --- | --- |
| handle names no known candidate | ignored silently | FR-013 |
| candidate named by no feature | becomes its own feature under `seedTitle`, `isPlanned=False` | FR-013 |
| candidate named by 2+ features | kept in the **first**, removed from the rest | FR-013 |
| feature empty after repair | dropped | FR-013 |
| title empty, `> MAX_TITLE_CHARACTERS`, or duplicate | feature rejected, its candidates reassigned | FR-013 |
| `kind` outside the vocabulary | **defaulted to `"subsystem"`**, feature kept | FR-013 |
| candidate still unplaced after all of the above | terminal `Support & Utilities` feature, `kind="tooling"` | FR-014 |
| fewer than `MIN_PLANNED_FEATURES` survive | whole plan discarded → one feature per candidate | FR-015 |

**Why a bad `kind` defaults rather than rejects**: kind only affects sidebar
ordering. Discarding a good title and description over a misspelled enum is a
worse outcome for the reader than a misplaced entry.

**The terminal feature is constructed explicitly**, not left to emerge from the
"candidate named by no feature" rule. Two rules that could both produce the
last-resort bucket is how one of them silently stops running.

**Post-condition, asserted**: after `repair`, the union of every feature's
`moduleKeys` equals the union of every candidate's `memberKeys`. Because
assignment is per candidate and candidates partition the repository, a module
cannot be orphaned mid-feature — that failure mode is designed out rather than
repaired, and this assertion is what proves the design held.

---

## 6. Unchanged surfaces (pinned, not modified)

**This section is the contract.** Removing the sidebar's module tree leaves a
module exactly two doors. Both already work today. Both get a test, and **neither
gets a change**.

### `search_index.py` — no change, one new test

`build_search_index` already emits one entry per `bundle.files` entry
unconditionally ([search_index.py:49-53](../../../src/doc_generator/search_index.py#L49-L53)).
The new test asserts `len([e for e in entries if e.kind in ("module","document")])
== len(bundle.files)` (FR-026). If implementing this feature requires editing
`search_index.py`, the approach has drifted.

### `feature.md.jinja` member list — renamed from `section.md.jinja`, logic unchanged

The template already loops the **full** `member_entries`; only the *diagram* is
capped by `MAX_SECTION_DIAGRAM_MODULES`, and the template already prints
"N less-connected modules omitted; every module is listed above". The rename must
preserve this. The new test asserts
`len(rendered member links) == len(feature.members)` for a feature larger than
the diagram cap (FR-025, SC-008).

### Diagram click targets

Only two diagram surfaces emit `click … href` — module dependency
([mermaid_diagram.py:75](../../../src/doc_generator/mermaid_diagram.py#L75)) and
the section/feature internal-dependency diagram
([mermaid_diagram.py:315](../../../src/doc_generator/mermaid_diagram.py#L315)).
Class, sequence and use-case emit none. The rename of
`build_section_diagram_mermaid_source` → `build_feature_diagram_mermaid_source`
must keep line 315's directive byte-identical in shape (FR-028).

### Untouched entirely

- **`frontend/` and `src/doc_generator/assets/wiki-ui.{js,css}`** — no change, no
  rebuild, nothing to commit. This feature is Python and Jinja only. A task
  asking for `npm run build` means the approach has drifted.
- `module.md.jinja`, `home.md.jinja`, every diagram template's source text.
- `class_diagram.py`, `use_case_diagram.py`, `entry_point_diagram.py` —
  `identify_entry_points` is *called*, not modified.
- `cross_references.py`, `html_sanitizer.py`, `markdown_render.py`, `prose.py`.

---

## 7. Deleted surfaces

Removed outright, not deprecated (FR-031). A grep for each must return nothing
under `src/` when A4 is complete:

| Removed | Replaced by |
| --- | --- |
| `sections.py` (module) | `features/candidates.py` + `features/fallback.py` |
| `section_narrator.py` (module) | `features/planner.py` + `features/validate.py` |
| `Section`, `SectionMember`, `SectionSelection` | `Feature`, `FeatureMember`, `tuple[Feature, ...]` |
| `SectionNarrator`, `SectionNarration`, `apply_section_narrations` | `FeaturePlanner` |
| `links.section_page_id/section_slug/section_output_paths` | `feature_page_id/feature_slug/feature_output_paths` |
| `links.SECTION_PAGE_ID_PREFIX` | `FEATURE_PAGE_ID_PREFIX` |
| `PageKind` member `"section"` | `"feature"` |
| `manifest_store.load_section_narration/save_section_narration/list_section_titles` | `load_feature_plan/save_feature_plan/list_feature_titles` |
| `doc_section_narrations` table | `doc_feature_plans` + `doc_features` |
| `html_render.NavSection`, `NavModule`, `active_module_key` | `NavFeature` |
| `generator.generateSectionPage/_section_identity/_ensure_sections/_nav_sections` | `generateFeaturePage/_feature_identity/_ensure_features/_nav_features` |
| `mermaid_diagram.build_section_diagram_mermaid_source`, `SectionDiagramSource` | `build_feature_diagram_mermaid_source`, `FeatureDiagramSource` |
| `DocGenerator(sectionNarrator=…)` | `DocGenerator(featurePlanner=…)` |

**Completeness check**: `grep -rn "[Ss]ection" src/ tests/` must return only
matches that genuinely mean a *document* section — the page TOC rail
(`_build_page_toc`, `page_toc`), `search_index`'s `"section"` kind for a prose
heading, and `_TEMPLATE_HEADING_ANCHORS`. Those are a different concept sharing a
word and must **not** be renamed. The CLI and serve wiring are the easiest sites
to miss because they fail at runtime, not at import.

---

## 8. New public surfaces on existing modules

### `links.py`

```python
FEATURE_PAGE_ID_PREFIX = "feature:"
def feature_page_id(anchor_module_key: str) -> str
def feature_slug(anchor_module_key: str) -> str          # one argument, not two
def feature_output_paths(slug: str) -> tuple[str, str]   # features/<slug>.{md,html}
```

`feature_slug` takes one argument because a feature's key *is* a module key,
whose readable half is the module's own name. `section_slug` needed two only
because a section key was `directory#leadName`.

### `manifest_store.py`

```python
def record_alias(repository_id, old_page_id, new_page_id, old_md, old_html) -> None
def list_aliases(repository_id) -> tuple[PageAlias, ...]
def load_feature_plan(repository_id, plan_key) -> tuple[Feature, ...] | None
def save_feature_plan(repository_id, plan_key, features) -> None
def list_feature_titles(repository_id) -> dict[str, str]
def drop_section_narrations(repository_id) -> None
```

New tables go in `SCHEMA_STATEMENTS` as `CREATE TABLE IF NOT EXISTS`. No
migration step: `_connect` replays every statement on every connection
([manifest_store.py:59-71](../../../src/doc_generator/manifest_store.py#L59-L71)).

### `writer.py`

```python
def write_redirect_stub(self, *, old_paths, new_paths, title) -> None
```

Writes `.html` (meta refresh + `<link rel="canonical">` + a **visible** link) and
`.md` (one line). The refresh URL is relative, so it works over `file://` and
makes no network request (constitution 2.2).

### `generator.py` — the removal-pass clause

The loop at
[generator.py:773-774](../../../src/doc_generator/generator.py#L773-L774)
MUST consult `list_aliases` before unlinking and skip any path an alias points
through (FR-021).

This is not defensive: six of eleven measured anchors are one import edge from
moving (research Decision 6), so "anchor moved, then an incremental run" is the
ordinary case. Without the clause, that run deletes the exact file the redirect
points at, and the alias table becomes a record of broken links.

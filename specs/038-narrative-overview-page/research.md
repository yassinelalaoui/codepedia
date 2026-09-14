# Phase 0 Research: Narrative Overview Page

**Feature**: 038-narrative-overview-page | **Date**: 2026-09-10

Everything below was read from the current tree (`038-narrative-overview-page`
branched from `main` at `cc9afc4`), not recalled. Where a number is derived, the
arithmetic is shown so a test can assert it rather than restate it.

**Sources read**: constitution §2.1–2.7; `templates/home.md.jinja` (57 lines);
`generator.py` `generateOverviewPage` (80–188), `_generate_repository_documentation`
(724–928), `_ensure_features` (969–994), `_build_architecture_summary` (1215–1238);
`features/{__init__,evidence,candidates,planner,validate,fallback}.py`;
`templates/module.md.jinja` 30/65, `feature.md.jinja` 12; `frontend/src/styles.css`
239–278 (built into `assets/wiki-ui.css`); `summary_pipeline.py` 380–430,
`summary_prompts.py`, `summary_context.py`; `cross_references.py`; `impact.py`;
`manifest_store.py`; `writer.py`; `provider_routing/router.py` 142–256;
`cli/index_command.py` 353–520; `git show 84069c9^:src/doc_generator/section_narrator.py`,
commits `74e0385` and `a345ffb`; `specs/033-feature-navigation/{plan,research}.md`.

---

## Decision 0: What `section_narrator` was, and why it is not coming back

**What it did** (`84069c9^`, 223 lines): one model call **per directory
section**, answering `Title:` / `Description:` in two lines. It never decided
membership, which lived in `sections.py`. Each answer was cached per
`(section_key, membership_hash)`. Failure left the deterministic title in
place. It had no grounding pass. The system prompt asked the model to backtick
names "so the wiki can link it", but nothing checked that a backticked name
existed.

**Why it went away** (033 plan, Summary): it named *where code lives*, never
*what the repository does*. It also spent N calls per run, one per group,
against an 8000-token-per-minute window. `features/planner.py` replaced it with
**one** repository-wide call and `validate.py` with deterministic repair.

**What this feature keeps from it**: the call shape
(`llmEngine.run(lambda engine: engine.generate(prompt))`, catching `RuntimeError`
only), the cache-by-inputs posture, and "failure degrades the page, never the
run".

**What it deliberately does not repeat**:

1. Per-group calls (see Decision 2).
2. Trusting backticks without resolving them (see Decision 6).
3. Letting model text reach the page as raw Markdown. `section_narrator`'s
   description was rendered verbatim, so a heading or a table in the answer
   would have become page structure (see Decision 10).

The stale `src/doc_generator/__pycache__/section_narrator.*.pyc` has no source
beside it and is imported by nothing. It is deleted as a housekeeping task, not
revived.

---

## Decision 1: Narration lives in a new `src/doc_generator/overview/` package

**Decision**: a package that mirrors `features/`, in which **exactly one module
accepts an LLM engine**:

| Module | Takes an engine? | Role |
| --- | --- | --- |
| `overview/__init__.py` | — | Package docstring stating the invariant; re-exports the budget constants from `features` |
| `overview/evidence.py` | **No** | Builds the bounded `OverviewEvidence` bundle from the repaired features, `RepositoryEvidence`, the bundle and the graph |
| `overview/narrator.py` | **Yes, the only one** | Builds the prompt, makes the one call, parses the reply, caches the raw answer |
| `overview/grounding.py` | **No** | Deterministic, model-free acceptance of each paragraph; renders accepted paragraphs to escaped Markdown |

**Alternatives considered**:

- **A single `doc_generator/overview_narrator.py`** (the runbook's first
  option). Rejected. Grounding would sit in the same module as the engine call,
  so "grounding needs no model" would again be a claim in a comment. The
  separation is what makes it checkable from the imports (033 research
  Decision 10).
- **A fifth stage inside `features/`**. Rejected. That package's docstring
  states its contract as "four stages, of which only the planner may fail", and
  `planner.py` calls itself "the only module in this package that takes an LLM
  engine". A second engine-taker there breaks both. `features/` also produces
  the navigation, which every page's sidebar renders. Narration affects exactly
  one page and has a different impact domain (Decision 7).
- **Extending `planner.py`'s existing call.** Rejected, and the **second call is
  not redundant**. The planner does already have README text and candidate
  evidence in scope, but four facts rule out folding the narrative into it:
  1. **It runs before repair.** The planner names *candidates* by handle.
     `repair()` then drops, merges or renames features: an empty feature is
     dropped, a duplicate title is rejected, and fewer than
     `MIN_PLANNED_FEATURES` means the whole plan is discarded. A narrative
     written in the same answer would describe features that may not survive.
     The narrator runs after `_ensure_features()` and sees the final
     `Feature` tuple, with keys that *are* page addresses.
  2. **Budget.** The planner's worst-case call is 4,945 prompt + 1,200 response
     = **6,145 tokens** (033 research Decision 5). Adding the narrative's
     response cap (1,400) and the evidence the planner lacks (entry flows 1,440
     chars, README lead 600 chars ≈ 510 tokens) gives 4,945 + 510 + 1,200 +
     1,400 = **8,055 tokens, over the 8,000 budget** before any margin.
  3. **Coupled failure.** One unparseable answer would cost the navigation
     *and* the prose. Today a bad narrative can only cost prose, which is the
     spec's central degradation property (FR-014).
  4. **The wrong cache key.** The planner's cache is keyed on structure only
     (`plan_cache_key`: module keys + entry-point keys). The narrative also
     depends on README content and anchor summaries, so under that key it would
     go stale silently (Decision 7).

---

## Decision 2: One call for the whole page

**Decision**: one call returns the lead and, from User Story 2 onward, the
per-subsystem paragraphs, as a single JSON object. That is at most one call per
narrative cache miss, and zero on a hit.

**Worst case, computed from the constants** (asserted by
`tests/unit/test_overview_narrator.py`, not restated):

| Item | Constant | Chars |
| --- | --- | --- |
| System prompt | `SYSTEM_PROMPT_CHARS` | 1,400 |
| Header (repository name, languages, how to read entry lines; no counts — see Decision 3) | `HEADER_CHARS` | 300 |
| README lead paragraph | `MAX_README_LEAD_CHARS` | 600 |
| Features | `MAX_PROMPTED_FEATURES` (12) × `FEATURE_BLOCK_CHARS` (710) | 8,520 |
| Entry flows | `MAX_PROMPTED_ENTRY_FLOWS` (6) × `ENTRY_FLOW_CHARS` (240) | 1,440 |
| **Prompt total** | | **12,260 chars ≈ 3,065 tok** |
| Response cap | `MAX_NARRATIVE_RESPONSE_TOKENS` | 1,400 tok |
| **Per call** | | **≈ 4,465 tok — 44.2% headroom under 8,000** |

*Revised during implementation.* The plan's figures (13,660 chars, 4,815
tokens, 39.8% headroom) included the README bullet list at 1,500 chars and a
200-char header. Measured against real replies, the bullets were removed from
the prompt (Decision 14) and the header grew by 100 chars to explain the entry
lines.

`FEATURE_BLOCK_CHARS` = handle + title 80, description 160, anchor name and path
160, anchor summary 120, three member names × 50, overhead 40.

`CHARS_PER_TOKEN = 4` is imported from `features`, and deliberately pessimistic
for the reasons 033 Decision 5 gives.

**The response cap is sized, not guessed.** 600 words (the clarified total) is
about 800 tokens of English. JSON keys, quotes, `[[fN]]` handles and backticked
names add roughly 150 more. A cap of 1,400 leaves room, so a `finish_reason:
length` truncation, which parses as nothing, stays unlikely. `reasoning_effort:
low` is set for the same reason the planner sets it (planner.py 181–195): an
unsuppressed reasoning channel consumed the whole budget in 033's measurement.

**Why not one call per section**:

- **Cost.** 1 lead + up to 8 subsystem calls is 9 calls. Each repeats the
  repository context, since a subsystem paragraph has to say how its subsystem
  relates to its neighbours. At ~1,500 tokens each that is ~13,500 tokens, 1.7×
  the per-minute window, so every cache miss would sit in `FailoverExecutor`'s
  rate-limit backoff for over a minute.
- **Coherence.** Separate calls cannot see each other's answers. The lead and
  the paragraphs could name a subsystem's role differently.
- **Their one advantage is already captured.** Per-section calls degrade more
  gracefully *per paragraph*. But grounding (Decision 6) accepts or rejects
  **each paragraph independently**, so a single call with one bad paragraph
  still publishes the others. What one call gives up is surviving a transport
  failure partway through, and in that case the spec's answer is "prose
  absent, structure intact" (FR-014) — which one call provides.

**Interaction with the planner's call.** A planner miss and a narrator miss can
occur in the same run. Their worst cases sum to 10,960 tokens, above the
per-minute window. That is safe for two reasons:

1. The narrator does not run in the same pass as the planner (Decision 8). It
   runs after summarization, minutes later.
2. `FailoverExecutor.run` already waits and retries the same provider on a 429,
   honouring `Retry-After` (router.py 209–256).

The hard constraint is per call. No single call can exceed the window, and the
test enforces that.

---

## Decision 3: The evidence bundle — `RepositoryEvidence` plus three bounded additions

**Reused as-is**: `features.evidence.RepositoryEvidence`, built once per run in
`_ensure_features()`. That includes `readmeBullets` (capped at 1,500 chars),
`entryPointKeysByModuleKey`, and per-module `docstring`, `generatedSummary` and
`exportedSymbolNames`. The evidence object is kept on the generator instead of
being discarded after `repair()`, which costs nothing.

**Added**:

| Addition | Why the planner's evidence is not enough | Cost |
| --- | --- | --- |
| **Features after repair** — handle `fN`, title, description, kind, anchor module name and repo-relative path, anchor summary's first sentence, up to 3 member names, entry-point count. Navigation order, first 12 | The narrative must name *final* features and link their pages | ≤ 8,520 chars ≈ 2,130 tok |
| **Entry flows** — for the 6 entry points reaching the most modules: qualified name, module path, owning feature handle, and the features reached in order of first contact (≤ 5), by a depth-tracking BFS bounded by `MAX_EVIDENCE_CALL_DEPTH = 6` | "Where work enters and where it ends up" (FR-005) needs order, and `RepositoryEvidence` only records reachability sets | ≤ 1,440 chars ≈ 360 tok |
| **README lead** — the first prose paragraph after the document's title, as plain text, capped at a sentence boundary within 600 chars | `read_readme_bullets` deliberately skips prose paragraphs, and the opening paragraph is where a repository says what it is | ≤ 600 chars ≈ 150 tok |

The README lookup order `_README_CANDIDATES` becomes a public
`features.evidence.find_readme(repository_root)`, so both readers resolve the
same file. It is a pure refactor with no behaviour change for the planner.

**Anchor summary** means the anchor module's docstring, else its generated
summary, first sentence, capped at 120 chars. Summaries are available because
the narrator only runs in passes where they have landed (Decision 8).

**Deliberately excluded**:

- Symbol counts. They change whenever any function is added, which would miss
  the cache on edits the narrative does not depend on (Decision 7).
- Full module lists and member summaries beyond the anchor. The planner already
  showed that a capped handful characterises a group.
- Anything outside the repository.

---

## Decision 4: The repository class diagram is reduced to its existing link

Settled in clarification (spec FR-003b). `generateOverviewPage` stops receiving
`classDiagramSource`, and `home.md.jinja` drops the fenced Mermaid block.
`class_diagram_link` and `use_case_diagram_link` are unchanged. The class
diagram's own page (`diagrams/class-overview.*`, zoomable since 034) is still
generated every run and still linked.

Alternatives, recorded because the runbook asked:

- **Demote below the prose.** Still illegible at full width, just lower down.
- **Replace with a subsystem diagram from the feature plan.** Most informative,
  but it is a new diagram to design, bound and test. A reasonable follow-up
  once the narrative exists, since it would need the same "features + entry
  flows" evidence this feature builds.

`_class_diagram_source()` is still called for the class-diagram page itself.
Only the home page's use of it goes away.

---

## Decision 5: "Getting started" is derived, never generated — and deferred

User Story 3 is out of the first release (clarification Q4). The design is fixed
now so that release has a bar to meet.

**Decision**: the section has **no model involvement at all**. Every line is a
`(source file, declared name, verbatim value)` triple read from the analysed
repository:

| Source | What is read | Classified as |
| --- | --- | --- |
| `pyproject.toml` (stdlib `tomllib`) | `[project.scripts]`, `[tool.poetry.scripts]` names → "installs the command `<name>`" | run |
| `package.json` (stdlib `json`) | `scripts.<name>` → shown as the name and its verbatim command | by name: `build`/`compile`/`bundle` → build; `start`/`serve`/`dev` → run; `test*` → test |
| `Makefile` | top-level `target:` lines whose target name classifies as above | as above |
| README | fenced blocks tagged `sh`, `bash`, `console` or `shell` under a heading matching `install`, `build`, `run`, `usage`, `test`, `getting started` or `quick start` (case-insensitive) | by the heading |

**Render condition, exactly**: the section renders **if and only if at least
one triple is found**. Within it, each of build, run and test renders only if
it has at least one triple. Conflicting triples, such as two test commands, are
all shown, each with its source. Nothing is inferred, completed or paraphrased.
This matches FR-027's "appears in the attributed file as shown" literally, and
needs no new dependency (`tomllib` has been stdlib since 3.11).

---

## Decision 6: Grounding — deterministic, model-free, per paragraph

`overview/grounding.py` takes no engine. Each paragraph from the reply is
accepted or rejected **whole**, since a paragraph with one false name is not
repaired by deleting the name. The rules, in order:

| # | Rule | On failure |
| --- | --- | --- |
| G1 | Collapse whitespace. An empty paragraph is dropped | drop |
| G2 | Tokenise into text, `` `code` ``, and `[[fN]]` segments. An unbalanced backtick or bracket rejects the paragraph | reject |
| G3 | Every `[[fN]]` must be a handle issued in *this* prompt's evidence | reject |
| G4 | Every `` `code` `` span must resolve through `cross_references.resolve_reference(lookup, text)` to **exactly one** entry | reject |
| G5 | Identifier-shaped tokens *outside* backticks must also resolve through G4's lookup: paths (contain `/`), file names with a known extension, `snake_case`, dotted lowercase module paths, `name()` calls, and inner-capital `CamelCase` (see below) | reject |
| G6 | No second-person pronoun (`you`, `your`, `yours`, `yourself`, `yourselves`, word-bounded, case-insensitive); no term from `BANNED_PROMOTIONAL_TERMS` | reject |
| G7 | **Every** paragraph, lead or subsystem, must contain at least one G4 span: a backticked file, module or symbol that resolves. A `[[fN]]` handle alone does not count; it names a page, not a source fragment (constitution §2.4, spec FR-007). A resolved span renders as a link, so a lead paragraph that passes G7 also routes onward. A subsystem paragraph additionally gets its closing link from the renderer (FR-025) | reject |
| G8 | A subsystem paragraph must have ≤ 3 sentences | reject |
| G9 | Keep at most 4 lead paragraphs and 8 subsystem paragraphs. While total words ≥ 600, drop subsystem paragraphs from the last, then lead paragraphs from the last | trim |
| G10 | If the reply's **first** lead paragraph failed any of G1–G8, or was trimmed by G9, withhold the whole lead. Subsystem paragraphs are unaffected (spec FR-010a) | withhold lead |
| G11 | Order the surviving subsystem paragraphs by navigation (table) order, not reply order. A withheld one leaves no trace (spec FR-025a) | reorder |

**Why G4 reuses `resolve_reference`**: it is the same resolver the page's
treeprocessor uses to turn a backticked name into a link. So "grounded" and
"will render as a working link" are the same predicate, and neither can drift
from the other. It also refuses ambiguous bare names, so `__init__` alone is
rejected rather than linked to the wrong module. The prompt asks for
repo-relative paths for modules for exactly that reason.

**The one allow-list, and its limit**: an inner-capital `CamelCase` token
outside backticks passes G5 if it is one of the detected languages, the
repository name, or a word in a feature title. Without this, "TypeScript" or
"GitHub" in an otherwise true sentence would reject it. The residual risk is an
un-backticked, fabricated class name that coincides with one of those words.
That is judged acceptable: the prompt requires backticks for every code name,
and SC-002's fabricated-reply tests exercise the rule.

**Tense** is not mechanically checkable with useful precision. It is required by
the prompt and verified by review. The spec's FR-013 was amended to say so
(see Spec amendments).

**Descriptions carried onto the Overview get the same checks** (spec FR-009, as
amended). A planned subsystem description (`Feature.isPlanned`) is placed in the
User Story 2 table only if it passes G2, G4, G5 and G6 through
`grounding.accept_description(text, evidence, lookup) -> str | None`. G3, G7, G8
and G9 are shape rules for narrative paragraphs and do not apply to a one-line
cell. A failing description renders as "—", the same as an unplanned subsystem.
The feature page keeps its description, because other pages are out of scope.
Unplanned descriptions are always empty, so there is nothing to check.

**Grounding runs on every render, including from cache.** The raw reply is what
is cached (Decision 7). Grounding is re-run against the *current* symbol lookup
each time, so an edit that removes a cited symbol drops that paragraph on the
next pass without a new call. This is FR-017, delivered by construction, and
the same posture as `doc_feature_plans`, which stores the raw plan and re-runs
repair on load.

---

## Decision 7: Cache key, invalidation, and exact incremental regeneration (§2.5)

**Key**: `narrative_key = sha1(NARRATIVE_FORMAT_VERSION ‖ envelope.systemPrompt ‖
envelope.to_prompt_text() ‖ max_tokens)`. That is a hash of **exactly what the
model is shown**. It is the same principle as the summary ledger's
`context_hash` (summary_pipeline.py 391–400): if the input is identical, the
answer is reusable.

**Therefore invalidated by**:

- the set, order, titles, descriptions or kinds of features;
- a change of anchor module, or its first-sentence summary;
- the first 3 member names;
- the entry flows;
- the README lead and bullets, within their caps;
- the repository name and languages;
- any prompt or format change, via `NARRATIVE_FORMAT_VERSION` and the prompt
  text itself.

**Not invalidated by**:

- function bodies;
- symbols outside the evidence;
- symbol counts, which are deliberately excluded (Decision 3);
- summaries of non-anchor modules.

Those still reach the page through grounding against the current lookup.

**Storage**: a new `doc_overview_narratives` table in the existing
`doc-manifest.sqlite`, one row per repository, following `doc_feature_plans`:
`(repository_id PK, narrative_key, reply_text, handle_map_json, generated_at)`.
`handle_map_json` records which feature key each `fN` handle meant in the prompt
that produced the reply. A key hit never needs it, because the same prompt
assigns the same handles. The earlier-version fallback (Decision 13) does need
it, because the current evidence may number features differently. No
migration is needed, because `_connect` replays `SCHEMA_STATEMENTS` (033
Decision 7). `_carry_forward_doc_manifest` already copies the whole database
into a fresh `index`, so the cache survives a full re-index with no extra code.

**What is saved**: any reply that *parses*, even one whose paragraphs all fail
grounding. If a parseable reply were not saved, every run over the same
repository would re-ask, and each answer would differ, which breaks FR-015 and
spends a call for nothing. An *unparseable* reply is not saved, as with the
planner, so a later run can retry.

**Byte-identical output**: same repository, therefore same evidence, same
prompt, same key, a cache hit on the same raw reply, deterministic grounding
against the same lookup, and the same Markdown. No clock, no randomness and no
set iteration reaches `index.md`. Dict and set iteration in evidence building is
sorted explicitly.

**The home page must be recomputed on every incremental pass.** Today
`impact.requiresHomePageRegeneration` fires only when the module set, feature
set or a feature title changes. With a narrative that is no longer enough: an
edit renaming a cited function leaves prose naming something that no longer
exists (an FR-017 violation), and the page is not rebuilt. Decision: on an
incremental run, `generateOverviewPage` always runs, which is in-memory and
cheap because there is no class-diagram render any more (Decision 4). Its
`contentMarkdown` hash is compared with the manifest's stored `content_hash`
for `home`, and **the page is written only if they differ**. So `serve` on an
unchanged repository never touches `index.md` or `index.html`, which is exactly
"codepedia serve must not quietly produce a different page". As a side effect,
this also fixes the home page's pre-existing staleness of counts and docstrings
between tree changes.

---

## Decision 8: Narrate only in passes where summaries have landed

`index` runs two generation passes: `GENERATING_DOCS_STRUCTURE`, before
summaries, and `GENERATING_DOCS_CONTENT`, after (index_command.py 482–497).

**Decision**: `generateRepositoryDocumentation` gains
`narrateOverview: bool = True`. `index` passes `False` for the structure pass.
When it is false, the home page renders with no lead, which is the same
structure as a no-provider page. That output is overwritten by the content pass
inside the staging directory and is never published.

**Why**:

1. The anchor summary (Decision 3) needs summaries to exist. With no
   docstrings, 122 of 135 modules on this repository (033 Decision 5) would
   otherwise reach the model with a bare name.
2. A structure-pass call would be keyed on summary-less evidence and missed
   again on the content pass. That is two calls per index, the exact waste the
   planner's structural key was designed to avoid.
3. The narrator runs minutes after the planner, not seconds, so their worst
   cases never share a rate-limit window (Decision 2).

`serve`'s incremental passes and `_refresh_wiki_shell` use the default `True`.
`ReindexPipeline` summarizes (pipeline.py 137) before it regenerates
documentation (169), so summaries are current whenever the narrator reads them.

---

## Decision 9: The determinism boundary — run time moves out of the Overview's content

`home.md.jinja` line 5 prints `repository.lastIndexedAt`, and `store.py` 85/136
reset it to `now()` on every run. A full re-index of an unchanged repository
therefore **cannot** produce an identical `index.md` today, before any narrative
exists. Separately, `layout.html.jinja` line 110 stamps every page's footer with
`generated_at = now()`, so no page's HTML is ever byte-identical across
regenerations.

**Decision**:

- Drop the `Last indexed` line from `home.md.jinja`. It describes the run, not
  the repository. The footer's "Generated locally … on …" stamp, present on
  every page, already shows it, and 037's hub shows `lastIndexedAt` under
  Properties. Root, languages and commit stay.
- The identity requirement applies to the page's **content** (`index.md`, and
  `index.html` outside the shared footer). The footer stamp is a wiki-wide shell
  property that this feature does not change for any page.

Spec FR-003, FR-015, SC-005 and US1 scenario 9 were amended accordingly (see
below). The alternative, keeping `lastIndexedAt` stable when nothing changed,
was rejected because it changes the meaning of a stored field the hub orders
its history by.

---

## Decision 10: Model text never reaches the page as Markdown

Grounded paragraphs are rendered **by construction**, not by trust:

- **Text segments** go through the existing `mdesc` escape. It escapes
  `` \`*_{}[]()#+-.!<>|~ `` (markdown_render.py 20), so no heading, table, list,
  link, HTML tag or `{: attr }` block can come from model text.
- **Code segments** are emitted as a backticked span of text that G4 already
  resolved. The page's `SymbolReferenceTreeprocessor` turns it into a link to
  the symbol's page.
- **`[[fN]]` handles** become `[<mdesc title>](<relative link>)` from the same
  `links.build_page_link` the feature list already uses. The model never writes
  a URL, so FR-011 holds by construction.
- Newlines inside a paragraph are collapsed. Each paragraph is emitted as one
  line followed by `{: .ai-generated }`, exactly as `module.md.jinja` 29–30
  does.

**Consecutive marked paragraphs**: four boxed paragraphs, each with its own
"AI-generated" badge, read as four separate notes. A small rule in
`frontend/src/styles.css` joins adjacent `.ai-generated` siblings into one
block, with the badge on the first only. It uses the existing tokens, so light
and dark contrast is unchanged. It needs `npm run build` in `frontend/` to
regenerate `assets/wiki-ui.css`. No other page has adjacent `.ai-generated`
paragraphs, since a heading or stale note always sits between them.

**Table cells cannot carry `{: .ai-generated }`** (attr_list does not reach
cells). The User Story 2 table's Responsibility column shows the planner's
feature descriptions, which are model-written when `Feature.isPlanned`. Its
header reads "Responsibility (AI-generated)" when any row's description is
planned. Unplanned features have empty descriptions and show "—", so the
header's claim is exact. Spec FR-012 was amended to allow this.

**The Features list loses its descriptions in User Story 1** (spec FR-012a).
Today `home.md.jinja` 41 renders `title — description` for every feature. For a
planned feature that description is model-written, and it is unmarked on the
Overview. A marker cannot be attached to half of a list item: attr_list on a
`<li>` would box the whole row, and the list's trailing `{: .module-list }`
already claims the last one. So from User Story 1 the list shows titles only.
The descriptions return in User Story 2's table, under a labelled column and
checked by `accept_description`, and that table then replaces the list outright.

---

## Decision 11: Reporting an omitted narrative (§2.3, FR-018)

`OverviewNarrator.narrate()` returns a `NarrationOutcome` whose status is one of
`cached`, `generated`, `unavailable`, `failed`, `unparseable` or `skipped`, with
a count of paragraphs dropped by grounding. `DocGenerator` gains an optional
`onNotice: Callable[[str], None]`. When the outcome is not `cached` or
`generated`, or when grounding dropped anything, it sends a single line:

```text
  overview: narrative omitted (no provider could answer)
  overview: 2 of 4 narrative paragraphs dropped (named something not in the repository)
```

`index` and `serve` pass `typer.echo`. It is a plain line, not a
`progress_stream` event. The hub folds only the event types it knows
(`hub_server/runs.py` 105–107), so 037's progress display is unaffected, and
037 FR-016 (terminal output only grows) holds. Provider *switches* are already
visible through `FailoverExecutor`'s failover log (router.py 188–196). The
narrator adds nothing there, because it calls through the same executor.

---

## Decision 12: The User Story 4 module-list repairs are markup and data, not CSS

- **Stray parenthesis.** `home.md.jinja` 52 wraps the dependency link as
  `([dependencies](…))`. Each row is a flex box, and `a:last-child` carries
  `margin-left: auto` (styles.css 252), so the literal `(` and `)` become loose
  anonymous flex items at opposite ends. Fix: drop the wrapper. The row becomes
  `[label](module) — description [dependencies](diagram)`, or just the two
  links. **No CSS change.**
- **Identical labels.** `prose.display_label` disambiguates prose files only.
  A new `prose.disambiguated_labels(modules, repository_root) -> dict[moduleKey,
  label]` starts from `display_label`. For every label shared by more than one
  module, it uses the shortest segment-aligned repo-relative path tail that is
  unique, without the extension; for the sample repository that gives
  `api/__init__`, `core/__init__` and so on. It is display-only, like
  `display_label`: slugs, page ids and stored links still derive from
  `module.name`. It applies to the Overview's module list only (spec Out of
  Scope: other pages unchanged).
- **Raw Markdown descriptions.** A prose module's `docstring` holds the
  document's leading text, heading marker included; see the
  `nextgen-wealth-ledger` Overview's README row. A new deterministic
  `doc_generator/plain_text.py::excerpt(text, max_chars=160)` does the
  following:
  - strips a leading ATX heading;
  - removes emphasis, inline-code and HTML markers;
  - reduces `[text](url)` to `text`;
  - collapses whitespace;
  - ends at the last sentence boundary within the cap, otherwise at the last
    word boundary followed by `…`.

  It is applied to every module-list description, code docstrings included.
  `mdesc` is still applied after it.

None of these touch the narrator. They ship independently.

---

## Decision 13: What the reader sees when prose is partial or out of date

Three states that the grounding and cache design can produce, but the first
draft of the spec never described (`checklists/narrative.md` CHK034, CHK035,
CHK037):

**A lead whose opening paragraph is withheld → withhold the lead** (G10, spec
FR-010a). The first paragraph says what the repository is, and the others are
written on top of it ("its storage layer…", "requests then reach…"). Publishing
paragraphs two to four without it gives a page that begins mid-explanation,
which reads worse than a page with no lead. The alternatives were:

- **Promote the second paragraph.** Rejected: nothing makes it an opening.
- **Ask the model again.** Rejected: that breaks "one call, never a retry".

Subsystem paragraphs are self-contained, one per subsystem, so they survive
without the lead.

**Uneven subsystem coverage → allowed, in table order** (G11, spec FR-025a).
All-or-nothing would let one bad paragraph withhold seven good ones, against
"a shorter true page beats a longer plausible one" in the other direction.
Ordering by the table rather than the reply keeps the paragraphs in step with
the rows above them. The notice (contract §7) reports how many were withheld.

**Changed repository, no provider → the last narrative, re-checked and marked
earlier-version** (spec FR-017a). This is the one behavioural choice among the
three. The alternatives are:

| Option | Reader sees on a flaky or absent provider after an edit | Verdict |
| --- | --- | --- |
| **(a) Last narrative, re-grounded, marked stale** | The previous prose, minus anything that no longer resolves, with the same "describes an earlier version" caveat module pages already use for stale summaries (`.summary-stale`, `module.md.jinja` 32–34) | **Chosen** |
| (b) No prose until a provider answers | The lead vanishes on the next edit and reappears when a call succeeds. Under `serve`, with a rate-limited key, it flickers | Rejected |

Why (a):

- **The wiki already made this choice for summaries.** The summary freshness
  ledger keeps an earlier summary visible with a stale caveat, rather than
  blanking it (`summary_pipeline.restoreSummariesFromLedger`,
  `summaryIsStale`). An Overview that blanked where module pages caveat would
  be the inconsistent one.
- **What (a) risks is bounded.** Every name is still re-resolved against the
  current lookup (G4, G5), and every subsystem link must still map to an
  existing feature key through the stored `handle_map_json` (G3). What can be
  out of date is a relational claim, which is exactly what the caveat says.
- **(b)'s cost lands on the constitution's default configuration**: remote
  providers on a free tier, where rate limits are routine (constitution §2.1;
  `features.PROVIDER_TOKEN_BUDGET` is sized to Groq's 8000-token-per-minute free
  tier).

**Mechanics**:

1. On `unavailable`, `failed` or `unparseable`, `narrate()` loads the
   repository's single cache row **regardless of key**.
2. If there is one, it returns `stale` with that reply and its handle map.
   Grounding maps handles through the stored map, drops any whose feature key
   no longer exists (G3), and re-checks every other rule against current
   evidence.
3. The template emits the stale caveat
   `{: .summary-stale }` directly under the last lead paragraph, reusing the
   existing class and CSS. It adds no heading and no link, so the outline
   identity checks (contract §6) hold.
4. The row is overwritten as soon as a call for the current key parses.

On an unchanged repository in the stale state, the same inputs give the same
page, so FR-015 holds.

**Clarification Q2 is respected.** Q2 fixed what stands *in place of absent*
prose: nothing. FR-017a concerns prose that is *present*, from an earlier
analysis. The caveat qualifies it; it never replaces missing prose. A
repository that has never been narrated still shows nothing at all.

---

## Decision 14: What real replies changed during implementation

User Story 1 was run end to end against `codepedia-sample-repo`, and every
provider in the configured summary chain was probed with the same prompt
(scratchpad `probe_models.py`). Six changes came out of reading real replies,
none of them visible in unit tests:

1. **The README bullet list left the prompt.** On the sample repository it is
   headings ("Layout", "Running") and directory names, with a stray trailing
   backtick from `features.evidence._extract_bullets`. Every model copied the
   directory names into backticks, and G4 rejected them, since a directory is
   not a module. The README's opening paragraph carries the purpose on its own.
   `OverviewEvidence.readmeBullets` and `build_overview_evidence`'s
   `repository_evidence` parameter went with it. `plain_text.to_plain` now also
   drops an unpaired backtick.
2. **The system prompt became a paragraph plan.** Paragraph 1 is what the
   repository is plus its entry file. Paragraph 2 follows one entry line.
   Paragraph 3 is written only if a subsystem's own text says it stores, sends
   or returns results. The plan adds four rules: "never f2 alone", "files, never
   directories", "full sentences; no arrows", and a one-line example. The first
   draft let models treat the deepest subsystem a call reached as "where results
   end up". The entry lines are call-depth order, not data flow, and the prompt
   now says so.
3. **G5's CamelCase allow-list covers the evidence text.** "FastAPI" appears in
   an anchor summary, where the repository describes its own stack. Rejecting it
   withheld otherwise correct leads from both Groq models. The allow-list now
   takes every word of the subsystem titles and descriptions, the anchor
   summaries and the README lead. An unbackticked CamelCase name the evidence
   never mentions still rejects.
4. **The repository's own name is accepted in backticks.** It is real, rendered
   as code, and not counted as a citation for G7.
5. **Blank-line-separated paragraphs in one reply string are split.** One model
   returned three paragraphs in a single `lead` item. Each is now grounded on
   its own.
6. **A latent `cross_references` bug was fixed.** `build_symbol_lookup` indexed
   paths only for entries of kind `"module"`, but Markdown files are indexed as
   kind `"document"`. So no page anywhere could resolve or link `README.md` or
   `docs/architecture.md`, and G4 rejected real documentation paths. It is a
   one-line fix with its own test, and it also makes document mentions link on
   module and feature pages.

`EntryFlow` also gained `kind` (`cli-command`, `api-route`, `function`), which
tells the model what kind of entry it is looking at.

**What the probe showed about models.** On the same prompt, `gpt-oss-20b` and
`gpt-oss-120b` produced fully grounded leads. The local `qwen2.5-coder:1.5b`,
first in this machine's configured summary chain, did not: its opening
paragraph cites nothing (G7), so G10 withholds the lead. That is the design
working, a shorter true page. But it means narrative quality is bounded by
whichever model the user's chain reaches first.

**An open question for the owner.** A reply that grounds to *nothing* is still
cached (Decision 7: any parseable reply is final for its key). So after
switching to a better provider, the Overview stays empty until the repository
changes. The alternative, discarding a reply that yields no prose, re-asks on
every pass while a weak model keeps failing, which costs one call per `serve`
pass. That trade-off is left to the owner rather than decided here.

## Decision 15: Only commands, routes and `main` are called entry points

**What the owner review found.** On `nextgen-wealth-ledger` (Spring + Angular),
the first lead paragraph said the repository's "primary code entry" is
`WalletServiceImpl.java`. That is false: the process starts in
`DigitalBankingApplication.main`, and requests enter through controllers. A
fresh reviewer given only the page rejected the claim.

**Why it happened.** Three layers:

1. **Prompt (038).** Paragraph 1 always asked for "the file its main entry point
   is in", so the model had to pick one even when no line was a real entry.
2. **Evidence ranking (038).** `identify_entry_points` has three kinds. The
   `function` kind means only "nothing in the repository calls it", which
   covers an interface implementation (controllers call the `WalletService`
   interface, so `WalletServiceImpl.credit` has no recorded caller), a framework
   callback, or a test. Flows were ranked by modules reached alone, and every
   line was labelled `entry (...)`. On the sample repository a test ranked fourth.
3. **Parser/graph (outside 038).** Java annotations are not recorded as
   decorators, so `@PostMapping` controllers are indistinguishable from other
   uncalled methods. Calls through an interface are not resolved, so each
   controller and `main` reaches one module and ranked out of the top six.

**Change** (owner chose "prompt + entry ranking"; the parser change is a
separate spec if wanted):

- `evidence.ENTRY_KINDS = ("cli-command", "api-route", "main")`. An uncalled
  function named `main` gets kind `main`. Flows rank by kind tier, then reach,
  then `stableKey`.
- Flows from test files are dropped (`is_test_path`: a `test`/`tests`/`__tests__`
  directory, or `test_*.py`, `*_test.py|go`, `conftest.py`, `*Test(s).java|kt|cs`,
  `*.spec|test.[cm][jt]s[x]`).
- A flow line reads `entry (<kind>): …` for `ENTRY_KINDS` and `uncalled: …`
  otherwise. The header calls them "call lines".
- The system prompt says paragraph 1 names where work enters only from a line
  marked `entry`, and otherwise claims no entry point and cites a subsystem's
  start file. Paragraph 2 may call only an `entry` line an entry point.
  `SYSTEM_PROMPT_CHARS` rises from 1,400 to 1,600: worst case 4,465 → 4,515
  tokens per call, 43.6% headroom.

**Re-verification** (2026-09-10; `gpt-oss-120b` temporarily first in the chain,
config restored; one call per repository):

| | Sample | Nextgen |
| --- | --- | --- |
| Entry lines | 6 × `entry` (4 routes, 2 CLI commands); the test is gone | `entry (main)` first, 5 × `uncalled` |
| Prompt / worst case | ~1,789 / 3,189 tokens | ~1,337 / 2,737 tokens |
| Lead | 3 paragraphs, all grounded, links 10/10 | 3 paragraphs, all grounded, links 7/7 |
| Paragraph 1 | "accessed through the entry point `routes_loans.py`": true, but one route file of three, and the CLI is missed | "Execution begins with `DigitalBankingApplication.main`": **correct**; the reviewer rated it "genuinely useful", confidence high |
| Stranger test (fresh subagent, one Read of `index.md`) | passes by the key; ¶2 and ¶3 misled | passes by the key; ¶1 helped, ¶2 and ¶3 misled |

The targeted defect is fixed. What still misleads, in order of cause:

- **The owner handle reads as a callee.** A line is `entry (main): X in file
  [[f3]]`, where `[[f3]]` is the subsystem X belongs to, not one it calls.
  Nextgen ¶2 says `main` "invokes the capabilities defined in [[f3]]". The old
  format had the same ambiguity. (038 scope.)
- **Paragraph 3's "where results end up"** invites a single-destination claim:
  "the in-memory store" on the sample (SQLite is omitted), and `ActiveWallet.java`
  as "storage" on nextgen. (038 scope.)
- **Spec 033 titles and grouping.** "Tests (Test Fines)", "Scripts", and a
  93-module "Data Transfer Objects" bucket. (Outside 038.)

## Decision 16: Call lines name their own subsystem apart; paragraph 3 lists every destination

The owner asked for both 038-scope defects left by Decision 15 to be fixed.
Dropping paragraph 3 was considered and rejected: the owner's own User Story 1
description, FR-005 and US1 #4 all require "where its results end up", so the
spec stands and the paragraph is made safer instead.

**Change:**

- **Call line format.** It was `…in <file> [[f3]] -> [[f5]] -> [[f1]]`; it is now
  `…in <file> (part of [[f3]]); its calls reach [[f5]], [[f1]]`. The reach
  clause is omitted when a function reaches no other listed subsystem. With no
  arrows in the evidence, the model has no chain to copy. The header now reads
  "a function, its file, the subsystem it is part of, then the subsystems its
  calls reach, nearest first."
- **Paragraph 2** lists what a line reaches "without then, next or finally".
- **Paragraph 3** is still written only when a subsystem's own text says it
  stores, sends or returns data. It now names **every** such subsystem as a
  place results can go, never a single file as the only destination.
- The example paragraph uses the new shape ("Work enters through the `run`
  command in `src/app/cli.py`, part of [[f0]]; its calls reach [[f1]] and
  [[f3]].") in place of one that modelled a data-flow chain.
- `SYSTEM_PROMPT` is 1,583 characters, within the 1,600 that Decision 15 set.
  The budget is unchanged: 4,515 tokens worst case.

**Re-verification** (`gpt-oss-120b` temporarily first in the chain, config
restored; one call per repository):

| | Sample | Nextgen |
| --- | --- | --- |
| Prompt / worst case | ~1,828 / 3,228 tokens | ~1,368 / 2,768 tokens |
| ¶1 | Work enters through `list_overdue` in `routes_loans.py`, "which belongs to [[f0]]" | Execution starts with `DigitalBankingApplication.main`, "part of [[f3]]": correct |
| ¶2 | The calls of `list_overdue` "reach" four subsystems, listed; no then/finally chain | `WalletServiceImpl.credit` "belongs to [[f3]] and its calls reach [[f6]]": true, and not called an entry point |
| ¶3 | Lists the memory store, SQLite store, email gateway and fine calculator, but cites no file, so **G7 dropped it** (`overview: 1 of 3 narrative paragraphs dropped`) | Entities of [[f4]] and repositories of [[f2]]: two places, not one file. One slip: it calls `ActiveWallet.java` "ledger data" |
| Published | 2 paragraphs, links 9/9 | 3 paragraphs, links 10/10 |
| Stranger test (fresh subagent, one Read) | Passes by the key. ¶1's domain clause helped, but "work enters through the `list_overdue` command" singles out one route (and calls it a command). ¶2 still lists "Tests" and "Scripts" as things a route reaches. Confidence medium / low | Passes by the key. `main` is named outright (confidence high). "Part of [Data Transfer Objects]" is now read correctly as membership, which exposes 033 putting the startup class and `WalletServiceImpl` in a DTO bucket anchored at `animations.ts`. The ¶3 "ledger data in `ActiveWallet`" slip was noticed. Confidence medium / high |

The owner-as-callee misreading is gone on both repositories. Paragraph 3 now
names several destinations. On the sample, grounding correctly withheld a
paragraph that forgot its citation: the page is shorter, not wrong.

What still misleads is now mostly outside 038: spec 033's grouping and titles.
Read as membership, "part of [[fN]]" makes a bad grouping *more* visible,
not less. Two 038-scope refinements remain possible, neither applied:

- When several lines are marked `entry`, ¶1 picks one. It could instead name
  the kinds, for example "HTTP routes in … and CLI commands in …".
- ¶3 could be told to cite one start file, so that G7 does not drop it.

## Decision 17: User Story 2 as built, and analyze finding I2

**I2 first: an earlier prompt is not an earlier version.** User Story 2 bumps
`NARRATIVE_FORMAT_VERSION` to `"2"`, and Decisions 15 and 16 reworded the prompt
twice. Each change misses the cache for a repository that did not change. With
no provider, the FR-017a fallback then showed the old narrative under "This
overview describes an earlier version of the repository", which is false: only
the question changed. The cache key cannot tell the two apart, because it
hashes the prompt, and the prompt covers both the repository and the wording.

- `OverviewEvidence.repositoryFingerprint` is SHA-1 of the README lead plus
  every file's `(repo-relative path, contentHash)`. It is deliberately not in the
  prompt. The README lead is included because the evidence reads it from disk,
  not from the index: the existing FR-017a test, whose Markdown is not indexed,
  caught a first version that left it out.
- Each saved reply stores it. `doc_overview_narratives.repository_fingerprint`
  is added in place (`ADDED_COLUMNS`) to databases from User Story 1.
- On fallback, an equal fingerprint gives the new status `previous-prompt`:
  the prose is shown with **no** caveat, and the terminal says `showing the
  narrative written for an earlier prompt (…)`, so a pending rewrite is never
  silent (FR-018). A different or unknown (`''`) fingerprint is `stale`, as
  before.

**User Story 2 as built:**

- **Grounding.** `ground` now grounds `reply.subsystems` too (`_ground_subsystems`):
  - G3: the handle maps to a live feature;
  - G9: only majors, one each, ≤ 8;
  - `_check`, which includes G7;
  - G8: ≤ 3 sentences;
  - G11: table order.

  The word budget trims subsystem paragraphs from the last before any lead
  paragraph. G10 never reaches subsystem paragraphs. Sentence counting masks
  code spans and does not count a full stop after e.g., i.e., etc., vs., cf.,
  approx., incl. or resp. `accept_description` applies G1, G2 (a `[[fN]]` handle
  rejects), G4, G5 and G6, and returns escaped Markdown.
- **Prompt.** The reply shape is `{"lead": [...], "subsystems": {"fN": "..."}}`,
  under 550 words in all. A major subsystem is marked `, paragraph` inside its
  own feature block rather than listed in the header, so asking costs a word
  and not a header line that `_fit` could drop. `SYSTEM_PROMPT_CHARS` goes from
  1,600 to 1,900: the worst case is 4,590 tokens per call, 42.6% headroom. The
  response cap (1,400) is unchanged, as T035 requires.
- **Generator.** The overview evidence is built on every pass, narrated or not,
  because the table checks descriptions against it and must be identical with
  and without a provider (FR-024). `RepositoryEvidence` is kept from feature
  derivation (`_repository_evidence`) for "Start with". Test files are passed
  over for "Start with" while the subsystem has other members (Decision 15's
  reasoning). Each subsystem paragraph ends in `[<title>](features/…)`.
- **Template.** `| Subsystem | Responsibility[ (AI-generated)] | Start with |`
  replaces `| Feature | Modules |`, and the `## Features` list is deleted. The
  paragraphs follow the table, each `{: .ai-generated }`. When the lead was
  withheld but stale subsystem paragraphs survive, the caveat sits under the
  last of them (contract §6).
- **Unrelated regression found and fixed.** The User Story 1 commit `2539226`
  had re-saved `generator.py` (and `tasks.md`) through a cp1252 round trip, so
  every Overview, dependency-diagram and call-sequence page title read
  "… â€” …". Both files were repaired by exact reverse decoding, and
  `tests/unit/test_source_encoding.py` now fails on any such sequence under
  `src/` or `frontend/src/`.

**Verification** (2026-09-14; `gpt-oss-120b` temporarily first in the chain,
config restored; one call per repository):

| | Sample | Nextgen |
| --- | --- | --- |
| Prompt / worst case | ~1,902 / 3,302 tokens | ~1,434 / 2,834 tokens (ceiling 4,590) |
| Table | 12 rows, navigation order, 12 accepted descriptions, header labelled, every "Start with" a member | 7 rows, likewise |
| Offered → kept | 10 → 5: lead 2 of 3 (¶3 cites no file, G7); subsystems 3 of 7 (4 written for **unmarked** subsystems, G9) | 7 → 2: lead 2 of 3 (¶3, G7); subsystems 0 of 4 (3 cite no file, G7; 1 unmarked, G9) |
| Lead ¶1 | **Regressed**: opens "Work enters through the `list_overdue` command…" and no longer says what the repository is | Says what it is and where work enters (correct) |
| Links / appearance | 28 links, 0 problems; the table scrolls within itself at 700 px; subsystem paragraphs form one marked block | 6 links, 0 problems |

The mechanics hold: grounding dropped exactly the paragraphs that broke a rule,
and the table is complete with or without prose. The prompt is followed poorly
for the new part:

- subsystem paragraphs omit the file citation (G7) and name subsystems by title
  instead of handle;
- the model writes for subsystems it judges important (Storage, Core) rather
  than the marked ones;
- the larger prompt diluted paragraph 1's "what it is".

The marked majors are the first eight non-tooling subsystems in navigation
order. 033's kind ranking puts "overview" and "capability" first, so on the
sample "Documentation" and "Tests (Test Fines)" are majors while both Storage
subsystems are not. That selection is evidence-side (`majorFeatureKeys`) and
worth revisiting. T042's stranger test is deferred until the prompt is fixed.

---

## Spec amendments made during planning

Four places where the spec as written could not be met or tested. Each was fixed
in `spec.md`, not worked around here:

| Spec item | Problem found | Amendment |
| --- | --- | --- |
| FR-003, FR-015, SC-005, US1 #9 | `lastIndexedAt` and the footer's `generated_at` are `now()` on every run, so "byte-identical" was impossible independent of this feature (Decision 9) | Identity applies to content; the run timestamp moves to the footer stamp every page has |
| FR-014, SC-004, edge case | The planner can **merge** candidates, not only rename them (`SYSTEM_PROMPT`: "Organise these N groups into about M features"), so a no-provider wiki can have a different feature *set*, not just titles | The comparison holds the grouping fixed; this feature adds no variation of its own |
| FR-012 | Table cells cannot carry the generated marker | A generated column is labelled in its heading |
| FR-013 | Tense cannot be filtered mechanically | Second person and banned terms are filtered; tense is prompt-required and review-verified |

Four more followed from the narrative checklist's **[Conflict]** items
(`checklists/narrative.md` CHK001, CHK011, CHK016, CHK030):

| Spec item | Conflict | Amendment |
| --- | --- | --- |
| FR-005, US1 #1, SC-007 | The story required two to four paragraphs; an edge case allowed one | 1–4 are published, 2–4 are asked for; fewer than two only with thin evidence or after grounding rejected paragraphs |
| FR-009, FR-021, SC-008 | Planner-written descriptions shown in the table escaped FR-009–FR-013 | Those FRs cover all model-written text on the Overview; a failing description shows "—" |
| FR-013, new SC-013 | Tense was assigned to SC-001's review, which does not measure it | A dedicated sentence-level review, recorded so it can be repeated |
| US1 text, new FR-012a | User Story 1 alone left unmarked planner descriptions in the Features list | Generated text never appears where it cannot be marked; the list shows titles only |

Three more closed the checklist's degraded-page **[Gap]** items (CHK034,
CHK035, CHK037), all argued in Decision 13:

| Spec item | Gap | Amendment |
| --- | --- | --- |
| New FR-010a, edge case | A lead could publish without its opening paragraph | The whole lead is withheld when its opening paragraph is |
| New FR-025a, edge case | Partial subsystem coverage was undescribed | Paragraphs are withheld one at a time, the survivors appear in table order, and nothing stands in for a withheld one |
| New FR-017a, FR-014, FR-018, US1 #10, edge case | A changed repository with no provider silently lost all prose | The last narrative is shown, re-checked against the current repository and marked as describing an earlier version; this is reported in the analysis output |

Five more came from `/speckit-analyze`'s high-severity findings (2026-09-10):

| Spec item | Finding | Amendment |
| --- | --- | --- |
| FR-007, FR-025, SC-003; rule G7 | K1: a lead paragraph citing only a subsystem page was not traceable to source "via des citations de symboles et de fichiers" (constitution §2.4) | Every generated paragraph cites at least one resolved file, module or symbol; a subsystem link alone no longer suffices |
| SC-007, US1 #1 | A2: the two-paragraph minimum depended on the model, and no rule enforced it | SC-007 bounds only maximums; the minimum is a prompt request, checked in review |
| Edge case "no subsystems" | I3: it promised a lead linking modules, while the design skips narration with no features | No subsystems means no lead, and the analysis output says so |
| FR-014 | U3: it read as if prose must vanish without a provider, but an already-narrated, unchanged repository keeps its cached narrative (FR-015/016) | Stated explicitly, with the two cases where prose is genuinely absent |
| SC-001 | A1: "a reviewer who has not worked on the repository" could not be met by the implementer | An answer key written from the code beforehand, by someone else; the reviewer is a person or a fresh AI session given only the page |

The two remaining high findings were in the design documents, not the spec: I1
(content hash algorithm, fixed in contract §5 and T020) and C1 (the missing
"no narrator configured" case, fixed in T011).

---

## Resolved unknowns

| Unknown | Resolution |
| --- | --- |
| Is the planner's call enough? | No: pre-repair, budget (8,055 > 8,000), coupled failure, wrong cache key (Decision 1) |
| One call or per section? | One, 4,815-token worst case, 39.8% headroom (Decision 2) |
| How is "no provider" reachable, given `index` refuses to start without a summary chain (`check_ai_dependencies`, index_command.py 358–365)? | At the narrator's own call: engine unavailable, chain exhausted (`RuntimeError`), refusal or empty reply, or unparseable reply. All four are covered by fake engines in tests; the manual check re-runs the real generator on a copy of an indexed state with a failing engine (quickstart §3) |
| Does a CSS change need a frontend rebuild? | Yes, `npm run build` in `frontend/` regenerates `assets/wiki-ui.css` (vite.config.ts). Only the adjacent `.ai-generated` rule needs it |
| New dependency? | None. `tomllib` and `json` are stdlib; everything else is already in the tree |
| New outbound destination? | None. The narrator calls the same `FailoverExecutor` the planner is handed |

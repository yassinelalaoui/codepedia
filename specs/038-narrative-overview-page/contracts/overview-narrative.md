# Contract: Overview Narrative

**Feature**: 038-narrative-overview-page

This contract covers the `doc_generator.overview` package API, the model
exchange, the Overview page's outline, and the terminal notice. Types are
defined in [data-model.md](../data-model.md), and each decision is argued in
[research.md](../research.md).

## §1 Package invariant

`src/doc_generator/overview/__init__.py`'s docstring states it, and a test
enforces it by import inspection:

> `evidence` and `grounding` take no LLM engine argument, not even an optional
> one defaulting to `None`. `narrator` is the only module in this package that
> accepts one.

`tests/unit/test_overview_package.py::test_only_the_narrator_accepts_an_engine`
walks every public function and constructor in `overview.evidence` and
`overview.grounding`, and asserts that no parameter is named `llmEngine`,
`engine` or `llm_engine`. It also asserts that neither module imports
`local_llm`.

## §2 `overview.narrator`

```python
class OverviewNarrator:
    def __init__(self, llmEngine: Any, *, cache: OverviewNarrativeCache | None = None,
                 repositoryId: str = "") -> None: ...
    def isReady(self) -> bool: ...
    def narrate(self, evidence: OverviewEvidence) -> NarrationOutcome: ...

def build_overview_prompt(evidence: OverviewEvidence) -> PromptEnvelope: ...
def narrative_cache_key(envelope: PromptEnvelope) -> str: ...
def parse_narrative_reply(text: str) -> NarrativeReply | None: ...
def worst_case_prompt_tokens() -> int: ...
def worst_case_call_tokens() -> int: ...
```

- **The constructor mirrors `FeaturePlanner`** exactly. `llmEngine` is
  duck-typed as `Any` because the CLI hands over a
  `provider_routing.FailoverExecutor`.
- **`narrate` makes one call, or none. Never two, and never a retry.** The order
  of operations:
  1. Build the prompt and compute its key.
  2. Load from the cache. On a hit, return `cached` **before** checking
     availability, so an already-narrated repository renders the same page with
     no provider reachable.
  3. If `isReady()` is false, the outcome is `unavailable`.
  4. Call `self.llmEngine.run(lambda engine: engine.generate(prompt))`.
  5. Catch `RuntimeError` **only**; the outcome is `failed`. An
     `AttributeError` is a wiring bug and propagates.
  6. Parse the reply. `None` means the outcome is `unparseable`.
  7. On success, save the raw reply **with the prompt's handle map**, and return
     `generated`.
  8. On any of `unavailable`, `failed` or `unparseable`, call
     `load_latest_overview_narrative`. If it finds a row, return `stale` with
     that reply, its stored handle map, and `staleReason`. Otherwise return the
     failure outcome itself. The earlier row is **never overwritten** by a
     failure.
- **`narrate` never raises for any provider behaviour.** It returns an outcome.
- **Budget**: `worst_case_call_tokens() <= PROVIDER_TOKEN_BUDGET`, computed from
  the constants (data-model.md § Constants), exactly like
  `planner.worst_case_call_tokens`.

### Prompt shape

The system prompt is at most `SYSTEM_PROMPT_CHARS` characters. It instructs the
model:

- **Reply format.** Reply with one JSON object only: `{"lead": [<string>, …]}`.
  From User Story 2 onward, a second key: `"subsystems": {"<handle>": <string>, …}`.
- **Length.** The lead is 2–4 paragraphs.
  - The first says what the repository is and does.
  - The second follows one call line: its function and file, then the
    subsystems its calls reach, listed without "then", "next" or "finally".
  - A third, only when a subsystem's own description or start-file summary says
    it stores, sends or returns data, names **every** such subsystem as a place
    results can go, never one file as the only destination (research
    Decision 16).
  - Each subsystem paragraph is at most 3 sentences.
  - All paragraphs together come to fewer than 600 words.
- **Subsystem references.** Refer to a subsystem **only** as `[[fN]]`, using the
  handles given. Never write a subsystem's title or any URL.
- **Code references.** Wrap every module, file, class or function name in
  backticks, exactly as written in the evidence. Prefer the repo-relative path
  for modules. Never name anything not listed. **Every paragraph names at least
  one of them**. The opening paragraph names a line's file as where work enters
  only if that line is marked `entry`; otherwise it claims no entry point and
  cites a subsystem's start file (research Decision 15).
- **Style.** Declarative present tense. No second person. No promotional
  adjectives. No headings, lists, tables or links.
- **When evidence is thin.** If the evidence does not support a claim, omit it.
  Fewer paragraphs are acceptable.

The prompt text consists of:

- a header (repository name, languages, subsystem count, and how to read the
  entry lines);
- the README's opening paragraph, if any. Not its bullet list (research
  Decision 14);
- one block per `FeatureBrief`: `fN: <title> (<kind>, <entryPointCount> entry points) — <description>`,
  then `  start: <anchorPath> — <anchorSummary>`, then `  also: <memberNames>`;
- `N more subsystems not listed`, if any were omitted;
- one line per `EntryFlow`:
  `entry (<kind>): <qualifiedName> in <modulePath> (part of [[fN]]); its calls reach [[fA]], [[fB]]`
  for a kind in `ENTRY_KINDS` (`cli-command`, `api-route`, `main`), and
  `uncalled: <qualifiedName> in …` for a function nothing calls. The owning
  subsystem is spelled "part of" and the reach clause is omitted when empty
  (research Decisions 15 and 16).

The options are `{"max_tokens": MAX_NARRATIVE_RESPONSE_TOKENS, "reasoning_effort": "low"}`.

## §3 `overview.grounding`

```python
def ground(reply: NarrativeReply | None, evidence: OverviewEvidence,
           lookup: SymbolLookup, *, handle_map: Mapping[str, str],
           is_stale: bool = False) -> GroundedNarrative: ...
def render_paragraph(paragraph: GroundedParagraph,
                     feature_links: Mapping[str, PageLink]) -> str: ...
def accept_description(text: str, evidence: OverviewEvidence,
                       lookup: SymbolLookup) -> str | None: ...
```

`accept_description` is used from User Story 2 onward, for planned subsystem
descriptions entering the table. It applies G2, G4, G5 and G6 only; `None`
renders as "—" (spec FR-021).

The rules are G1–G11 as listed in [research.md Decision 6](../research.md).
G10 withholds the whole lead when its opening paragraph fails (spec FR-010a).
G11 orders subsystem paragraphs by table order (spec FR-025a). G3 resolves
handles through `handle_map` and requires the resulting feature key to exist in
the current evidence. Each
rule has one test built from a hand-written reply, and none of those tests
involves a model. `ground(None, …)` returns an empty `GroundedNarrative`.
`render_paragraph` never emits `#`, `|`, `<`, `[`/`]` except through a
feature-link segment, or `{` unescaped. A test asserts this against a reply made
entirely of Markdown and HTML syntax.

## §4 `overview.evidence`

```python
def build_overview_evidence(features: Sequence[Feature], bundle: RepositoryBundle,
                            graph: DependencyGraph, *,
                            repository_root: str | Path) -> OverviewEvidence: ...
def read_readme_lead(repository_root: str | Path, *, max_chars: int = MAX_README_LEAD_CHARS) -> str: ...
```

`read_readme_lead` resolves the file through `features.evidence.find_readme`.
Like `read_readme_bullets`, it is best-effort: a missing, unreadable or empty
README yields `""`.

## §5 `DocGenerator` changes

```python
DocGenerator(..., featurePlanner=None, overviewNarrator: OverviewNarrator | None = None,
             onNotice: Callable[[str], None] | None = None)
generateRepositoryDocumentation(root, *, incremental=True, ..., narrateOverview: bool = True)
generateOverviewPage(repository, *, classDiagramPage=None, useCaseDiagramPage=None) -> DocPage
```

- `generateOverviewPage` loses its `classDiagramSource` parameter (research
  Decision 4).
- The narrative's evidence is built from the repaired features, the bundle and
  the graph. `RepositoryEvidence` is not carried into it (research Decision 14);
  User Story 2 may add it back for entry-point counts in the table.
- On an incremental run, the home page is **always computed**. It is written only
  when `writer._content_hash(contentMarkdown)` differs from the manifest's stored
  `contentHash` for `home` (research Decision 7). The stored hash is SHA-1
  (`writer.py` 202–203), so the comparison must use that same function. Any
  other digest never matches, and the page would be rewritten on every pass.
- **CLI wiring.** `cli/index_command.py` (next to `featurePlanner=`, line 479) and
  `cli/serve_command.py` (line 124) pass
  `overviewNarrator=OverviewNarrator(<the same engine as the planner>, cache=manifest_store)`
  and `onNotice=typer.echo`. `index_command` passes `narrateOverview=False` to its
  `GENERATING_DOCS_STRUCTURE` pass only.
- **The CLI wiring fails at runtime, not at import**, the same trap 033's T060
  recorded. The integration test runs both commands' wiring.

## §6 The Overview page outline

`home.md.jinja` context: `repository`, `repository_name`, `architecture_summary`,
`feature_entries`, `module_entries` (now carrying `label` and `description`),
`class_diagram_link`, `use_case_diagram_link`, and `lead_paragraphs:
list[str]`, which is already rendered Markdown and empty when there is no
narrative. From User Story 2 onward: `subsystem_rows` and
`subsystem_paragraphs`.

**After User Story 1**, the outline is the same with and without prose, except
for the lines marked *(prose)*:

```text
# <repository> — Documentation
<lead paragraph 1>                     (prose)  {: .ai-generated }
… up to 4                              (prose)  {: .ai-generated }
_This overview describes an earlier version of the repository and has not been regenerated yet._
                                       (stale only, FR-017a)  {: .summary-stale }
- Repository root / Detected languages / Commit      {: .repo-meta }
## Architecture overview
<counts sentence>
| Feature | Modules |                    (replaced in User Story 2)
[View the repository class diagram]    {: .diagram-link }
[View the repository use-case diagram] {: .diagram-link }
## Features
- [<title>](…)   (titles only — no descriptions, FR-012a)   {: .module-list }
## Modules
- [<label>](…) — <plain description> [dependencies](…)   {: .module-list }
```

- **No inline Mermaid.** It was removed from the Overview in User Story 1.
- **No model-written text outside `.ai-generated` paragraphs.** The Features
  list drops the `— description` suffix that `home.md.jinja` 41 renders today.
  User Story 2 replaces the list with the table, whose "Responsibility
  (AI-generated)" column carries descriptions that passed `accept_description`.
- **No `Last indexed` line** (research Decision 9).
- **The module-list row shape** belongs to User Story 4. Until then, the row is
  unchanged.
- **Identity checks** (test-enforced):
  - The heading sequence `[h.text for h in all headings]` is equal with and
    without prose.
  - The set of `href`s outside `.ai-generated` elements is equal with and
    without prose.
  - No `.ai-generated` element survives when the narrative is empty.
  - The `.summary-stale` caveat appears **if and only if** `isStale` is true and
    at least one lead paragraph survived grounding. It carries no heading and no
    link, so the two checks above hold for stale pages too. When the lead was
    withheld (G10) but stale subsystem paragraphs survive, from User Story 2
    onward, the caveat sits under the last of those paragraphs instead.

## §7 Terminal notice

`onNotice` receives at most one line per generation pass, and only when prose is
missing or reduced:

| Condition | Line |
| --- | --- |
| `unavailable` / `failed` | `  overview: narrative omitted (no provider could answer)` |
| `unparseable` | `  overview: narrative omitted (the reply could not be read)` |
| all paragraphs rejected | `  overview: narrative omitted (every paragraph named something not in the repository)` |
| some rejected | `  overview: <k> of <n> narrative paragraphs dropped (named something not in the repository)` |
| lead withheld (G10) | `  overview: narrative lead withheld (its opening paragraph named something not in the repository)` |
| `stale` | `  overview: showing the narrative from an earlier version (<staleReason>); <k> of <n> paragraphs still apply` |

| `skipped` because the wiki has no subsystems | `  overview: narrative skipped (no subsystems to describe)` |

When several conditions hold, the `stale` line takes precedence, then the lead
line, then the others. There is still at most one line per pass. `cached`,
`generated` with nothing rejected, and `skipped` because `narrateOverview=False`
(the structure pass) are silent. The line is
plain text, not a `progress_stream` event (research Decision 11).

## §8 Getting started (User Story 3 — deferred)

This section binds only the release that ships User Story 3.
`doc_generator/getting_started.py` takes no engine and returns
`tuple[Instruction, ...]`, where each `Instruction` is `(part: "build" | "run" |
"test", sourcePath, declaredName, verbatimValue)`. Sources and classification are
as in research Decision 5. The template renders `## Getting started` if and only
if the tuple is non-empty. Each part renders only if it has an instruction.

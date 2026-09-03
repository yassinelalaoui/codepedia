# Phase 1 Data Model: Feature Navigation

**Feature**: 033-feature-navigation | **Date**: 2026-09-02

Every entity below is an in-process frozen dataclass except where a storage
section says otherwise. Nothing here is a Pydantic model and nothing is
serialised to JSON on disk beyond what the manifest store already writes.

---

## 1. `FeatureEvidence` — `features/evidence.py`

What is known about one module before any grouping is decided. Derived with no
model call; the sole input to candidate formation.

```python
@dataclass(frozen=True, slots=True)
class FeatureEvidence:
    moduleKey: str            # module.sourceFileId — the same key a module page uses
    moduleName: str
    filePath: str
    directoryPath: str        # repository-relative, "." at the root
    reachingEntryPointKeys: tuple[str, ...]   # EntryPoint.stableKey, sorted
    exportedSymbolNames: tuple[str, ...]      # public, non-nested, sorted
    generatedSummary: str     # module.docstring or module.generatedSummary, "" when neither
```

**Invariants**

- One instance per module in `bundle.files`. Never fewer — a module with no
  entry points reaching it and no exports still gets an instance with empty
  tuples, because `candidates.py` must be able to place *every* module (FR-001).
- `reachingEntryPointKeys` is computed by a BFS over `graph.functions_called_by`
  **with a visited set**, bounded at `MAX_EVIDENCE_CALL_DEPTH`. Not by
  `build_entry_point_call_sequence`, which has no visited set by design
  (research Decision 1).
- Sorted tuples throughout, so two runs over an unchanged repository produce
  equal instances (FR-002).

## 2. `RepositoryEvidence` — `features/evidence.py`

```python
@dataclass(frozen=True, slots=True)
class RepositoryEvidence:
    modules: tuple[FeatureEvidence, ...]      # sorted by moduleKey
    readmeBullets: tuple[str, ...] = ()       # capability lines from the README
    entryPointsByModuleKey: Mapping[str, tuple[str, ...]] = ...
```

`readmeBullets` is read from `repository_root/README.{md,rst,txt}`, first match
wins, and is **best-effort**: a missing, unreadable or empty README yields `()`
and never raises. It is a read of the analysed repository, which constitution 2.7
permits (it forbids writes). `chat/retrieval.read_readme_content` is deliberately
not reused — it skips `.md` on purpose (research Decision 8).

The bullets are the README's list items and headings, joined and truncated to
`MAX_README_PROMPT_CHARS`. Truncation is by character, at a line boundary.

## 3. `Candidate` — `features/candidates.py`

A provisional group of modules. **This is the unit the model organises and the
unit repair operates on**, which is what makes an orphaned module structurally
impossible (FR-010).

```python
@dataclass(frozen=True, slots=True)
class Candidate:
    handle: str               # "c0", "c1", … assigned at prompt time, never stored
    seedModuleKey: str        # the entry-point module this group grew from
    seedTitle: str            # deterministic name: the seed module's display name
    memberKeys: tuple[str, ...]           # sorted, non-empty
    exposedEntryPointCount: int           # entry points whose module is in memberKeys
```

**Invariants**

- **Partition.** Every module in the repository belongs to exactly one
  `Candidate`. The union of all `memberKeys` equals the set of module keys, and
  the intersection of any two is empty (FR-001). This is the property that makes
  the repair table safe.
- `handle` is assigned by position at prompt-construction time and is *not* part
  of the candidate's identity — it never reaches storage and never appears in a
  page id. Two runs may assign the same handle to different candidates without
  any consequence, because a handle only ever lives inside one call.
- `seedTitle` is what the candidate is called when no model answers, and what a
  repaired-in candidate is called when it becomes its own feature (FR-013).

### Formation

1. **Seed** one candidate per distinct entry-point module. Entry points sharing a
   module share a seed (FR-005). Probe 1: 167 entry points over 52 modules.
2. **Attach** every module to the seed with the highest score
   `1 / (1 + distance)`, where distance is BFS hops over the undirected import
   adjacency, bounded at `MAX_ATTACH_DISTANCE`. Ties break on
   `(-score, seedModuleKey)` (FR-006).
3. **Consolidate**: candidates below `MIN_CANDIDATE_MODULES` fold into the
   highest-scoring candidate that reaches their modules; survivors are then
   capped at `MAX_PROMPTED_CANDIDATES`, ranked by `(-len(memberKeys),
   seedModuleKey)`, with the remainder folded the same way (FR-007).
4. **Fallback**: modules no seed reaches at all are grouped by
   `features/fallback.py` — today's clustering, moved unchanged — and each
   resulting cluster becomes a `Candidate` whose `seedModuleKey` is its lead
   member (FR-008). Research Decision 9: on a real run this path handles every
   prose file, so it is not a rare branch.

**`MAX_ATTACH_DISTANCE` is 2, not 4.** Measured: at depth 2 a seed already reaches
132 of 135 modules; at depth 3, all 135. Run at 4, step 2 degenerates into one
64-module candidate and 41 singletons (research Decision 2). The A1 verification
script re-measures the size distribution rather than trusting this number.

## 4. `Feature` — `features/validate.py`

A published capability. Replaces `sections.Section` entirely.

```python
FeatureKind = Literal["overview", "capability", "subsystem", "tooling"]

@dataclass(frozen=True, slots=True)
class Feature:
    key: str                  # == anchorModuleKey. One identifier, not a composite.
    title: str
    description: str
    kind: FeatureKind = "subsystem"
    members: tuple[FeatureMember, ...] = ()
    internalEdges: tuple[tuple[str, str], ...] = ()
    neighborKeys: tuple[str, ...] = ()
    isPlanned: bool = False   # gates the {: .ai-generated } marker (constitution 2.4)

    @property
    def anchorModuleKey(self) -> str: return self.key
    @property
    def moduleKeys(self) -> tuple[str, ...]: ...
```

`FeatureMember` is `sections.SectionMember` unchanged in shape
(`moduleKey`, `name`, `filePath`, `docstring`, `generatedSummary`) — the feature
page template consumes exactly what the section page template consumed.

**Invariants**

- `key` **is** the anchor module key (FR-018). Not a composite of directory and
  lead name, as `Section.key` was. One argument to `feature_slug`, not two.
- The **anchor** is the member with the highest internal degree, ties broken on
  `(name, moduleKey)` — the rule `sections._lead_member` already implements,
  reused verbatim.
- `title` never contributes to identity (FR-019). A re-titled feature keeps its
  URL, which is the property `test_feature_navigation.py` inherits from
  `test_section_navigation.py`.
- `isPlanned` is `False` whenever the title came from `seedTitle`, so a
  fallback-named feature is not marked AI-generated.

### `FeatureKind` ordering

`overview < capability < subsystem < tooling`, general to specific (FR-027). A
closed vocabulary: a plan naming anything else gets the **default**
`"subsystem"` rather than being rejected, because kind only affects ordering and
discarding a good title over it is the worse trade (FR-013, spec iteration-2
finding 2).

Navigation sort key: `(KIND_RANK[kind], -exposedEntryPointCount, title)`.
Today's alphabetical sort by `directoryPath` cannot express general → specific;
this can.

## 5. `FeaturePlan` — `features/planner.py`

One model answer covering the whole repository.

```python
@dataclass(frozen=True, slots=True)
class PlannedFeature:
    title: str
    description: str
    kind: str                 # raw, unvalidated — validate.py narrows it
    memberCandidateIds: tuple[str, ...]   # handles: "c0", "c3", …

@dataclass(frozen=True, slots=True)
class FeaturePlan:
    features: tuple[PlannedFeature, ...] = ()
```

**Wire shape** — the model returns strict JSON, a list of objects:

```json
[{"title": "…", "description": "…", "kind": "capability", "memberCandidateIds": ["c0","c3"]}]
```

Nothing else is accepted. A response that does not parse as this shape is a
rejected plan, which falls back to A1's candidates (FR-015).

### Cache key

`sha1(sorted moduleKeys + sorted entry-point stableKeys)`. Deliberately the
repository's **structure**, not a content hash: `doc_generator` regenerates twice
per index — once for structure, once after summaries land — and a content-keyed
cache would miss on the second pass and spend a second call every run
(FR-016, constitution 2.5).

## 6. `PageAlias` — `manifest_store.py`

A record that an address the wiki once published now belongs to a different page.

```python
@dataclass(frozen=True, slots=True)
class PageAlias:
    oldPageId: str
    newPageId: str
    oldOutputPathMarkdown: str
    oldOutputPathHtml: str
    recordedAt: str
```

**Invariant that makes it work**: the removal pass consults
`list_aliases(repository_id)` before unlinking, and skips any path an alias
points through (FR-021). Measured necessity: six of eleven anchors are one import
edge from moving (research Decision 6), so an anchor move followed by an
incremental run is the ordinary case, and without this the run deletes the file
the redirect points at.

---

## 7. Constants — one place each

| Constant | Value | Module | Why this value |
| --- | --- | --- | --- |
| `MAX_EVIDENCE_CALL_DEPTH` | 6 | `evidence.py` | Matches `entry_point_diagram.MAX_CALL_DEPTH`, so "reaches" means the same thing in the sequence diagram and in the evidence. |
| `MAX_ATTACH_DISTANCE` | **2** | `candidates.py` | Reachability saturates at 2 (132/135 modules); 3 reaches everything. Research Decision 2. |
| `MIN_CANDIDATE_MODULES` | 2 | `candidates.py` | A one-module group is navigation noise, not a capability. Same threshold `MIN_SECTION_MODULES` used. |
| `MAX_PROMPTED_CANDIDATES` | 32 | `candidates.py` | The token ceiling's dominant term. 32 × 540 chars = 17,280. |
| `MAX_MEMBERS_PER_CANDIDATE` | 3 | `planner.py` | Enough to characterise a group; the second-largest term. |
| `MAX_MEMBER_SUMMARY_CHARS` | 120 | `planner.py` | Load-bearing: 92% of the summaries that exist exceed it (probe 5). |
| `MAX_README_PROMPT_CHARS` | 1500 | `evidence.py` | ≈375 tokens. |
| `MAX_PLAN_RESPONSE_TOKENS` | 1200 | `planner.py` | 20 features × ~55 tok (title 8, description 35, 3 handles 6). |
| `MAX_TITLE_CHARACTERS` | 60 | `validate.py` | A sidebar entry must stay on one line. Same value `section_narrator` used. |
| `MIN_PLANNED_FEATURES` | 2 | `validate.py` | One feature holding everything is not navigation. |
| `TARGET_FEATURE_COUNT` | `clamp(len(modules) // 8, 8, 20)` | `planner.py` | Scales with repository size; 135 modules → 16. |

**The ceiling is asserted, not trusted.** `test_feature_planner.py` computes the
worst case *from these constants* and fails if it exceeds the budget:

| Item | Chars |
| --- | --- |
| Candidate header (handle + seed title + count) | ≤ 60 |
| Member line, summary capped at 120 | ≤ 160 |
| One candidate, 3 members | 540 |
| 32 candidates | 17,280 |
| README bullets | 1,500 |
| System prompt + instructions | 1,000 |
| **Prompt** | **19,780 ≈ 4,945 tok** |
| Response cap | 1,200 tok |
| **Total** | **6,145 tok — 23.2% under 8000** |

At 4 chars/token, deliberately conservative: real English runs nearer 4.5, and a
member line is mostly identifiers, which tokenise worse. A pessimistic divisor
makes the assertion fail early rather than in production.

---

## 8. Storage

### Added to `manifest_store.SCHEMA_STATEMENTS`

```sql
CREATE TABLE IF NOT EXISTS doc_page_aliases (
    repository_id            TEXT NOT NULL,
    old_page_id              TEXT NOT NULL,
    new_page_id              TEXT NOT NULL,
    old_output_path_markdown TEXT NOT NULL,
    old_output_path_html     TEXT NOT NULL,
    recorded_at              TEXT NOT NULL,
    PRIMARY KEY (repository_id, old_page_id)
);

CREATE TABLE IF NOT EXISTS doc_feature_plans (
    repository_id TEXT NOT NULL,
    plan_key      TEXT NOT NULL,
    generated_at  TEXT NOT NULL,
    PRIMARY KEY (repository_id)
);

CREATE TABLE IF NOT EXISTS doc_features (
    repository_id TEXT NOT NULL,
    plan_key      TEXT NOT NULL,
    feature_key   TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    kind          TEXT NOT NULL,
    member_keys   TEXT NOT NULL,   -- JSON array of moduleKeys
    PRIMARY KEY (repository_id, feature_key)
);
```

New tables appear on the next `_connect` with **no migration step** — every
statement is `CREATE TABLE IF NOT EXISTS` and `_connect` replays all of them on
every connection (research Decision 7). This is the route `doc_render_state` took
in commit 2c03afe.

### Removed

`doc_section_narrations` is dropped in the same pass that detects a
`kind="section"` manifest row (FR-023). Dropping it is what prevents an old
section title leaking into a feature's sidebar entry.

---

## 9. Page identity

```python
feature_page_id(anchor_module_key)  -> f"feature:{anchor_module_key}"
feature_slug(anchor_module_key)     -> f"{slugify(anchor_name)}-{sha1(key)[:8]}"
feature_output_paths(slug)          -> (f"features/{slug}.md", f"features/{slug}.html")
```

**One argument, not two.** `section_slug(directory_path, section_key)` needed both
because a section key was `directory#leadName` and the readable half lived in the
directory. A feature's key is a module key, whose readable half is the module's
own name, so the anchor name is derivable from the key alone.

`section_page_id`, `section_slug`, `section_output_paths` and
`SECTION_PAGE_ID_PREFIX` are **removed**, not deprecated (FR-031).

### Redirect stub

`writer.write_redirect_stub(old_paths, new_paths)` writes two files at the old
location:

- `.html`: `<meta http-equiv="refresh" content="0; url=…">`, a
  `<link rel="canonical">`, and a **visible link** — so a reader whose browser
  blocks the refresh still gets there, and can tell where they were sent
  (FR-020, spec acceptance 3.4).
- `.md`: a one-line `Moved to [title](relative.md).`

The refresh URL is relative, so it works over `file://` and makes no network
request (constitution 2.2).

---

## 10. Migration from `kind="section"`

A manifest row with `kind="section"` for this repository:

1. forces one full non-incremental rebuild (FR-023) — the same escape hatch the
   template fingerprint uses, and for the same reason: no per-page impact set can
   express "the whole navigation scheme changed";
2. for each old section page, reads its stored `sourceSymbolIds` — which for a
   section page **are its member module keys** (`generator.py` passes
   `contentSymbolIds=section.moduleKeys`) — and resolves the feature holding a
   **plurality** of them;
3. records an alias from the old page id to that feature and writes a redirect
   stub over the old file (FR-022);
4. drops the `doc_section_narrations` rows in the same pass.

Ties in step 2 break on the feature key, so the migration is deterministic. A
section page whose modules all vanished resolves to no feature; its alias is not
recorded and the page is removed normally.

---

## 11. What this feature does not touch

Named here because the existing suite is what proves it, and that suite must keep
passing unmodified:

- **`frontend/` and the built `wiki-ui.{js,css}`** — no change at all. The
  sidebar's *markup* simplifies in `layout.html.jinja`, but no bundle rebuild is
  required and none should be committed. If a task here asks for `npm run build`,
  the approach has drifted.
- **`search_index.py`** — already emits one entry per module unconditionally
  ([search_index.py:52-55](../../src/doc_generator/search_index.py#L52-L55)).
  It gets a **pinning test** (FR-026), not a change.
- **`module.md.jinja`, `home.md.jinja`** and every diagram template's Mermaid
  source text.
- **`class_diagram.py`, `use_case_diagram.py`, `entry_point_diagram.py`** —
  `identify_entry_points` is *called* by the new code, not modified.
- **`cross_references.py`, `html_sanitizer.py`, `markdown_render.py`,
  `prose.py`.**

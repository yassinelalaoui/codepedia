# Research: Repository Use Case Diagram

## Decision 1 — Reuse `entry_point_diagram.identify_entry_points()` unmodified as the sole source of entry points

**Decision**: This feature adds no new entry-point detection. It calls
`entry_point_diagram.identify_entry_points(bundle, graph)` (022) exactly as
022 already calls it — same candidate pool, same `"cli-command"`/
`"api-route"`/`"function"` classification, same deterministic ordering.

**Rationale**: Directly satisfies the brief's explicit framing ("Consomme la
même identification de points d'entrée que 8.2" — "8.2" being this
codebase's prior feature, `022-entry-point-sequence-diagram`, which
introduced that identification). `identify_entry_points()` already returns
everything this feature needs per entry point: `name`, `moduleName`,
`className`, `kind` (which doubles as the actor category — see Decision 3).
Duplicating or reimplementing any part of that logic here would create two
sources of truth for "what counts as an entry point" that could drift apart
silently.

**Alternatives considered**: Writing a second, parallel entry-point scan
scoped to this feature's needs — rejected outright; the brief is explicit
that this reuses 022's identification, and there is no technical reason two
diagrams derived from the same underlying concept should ever disagree about
which functions qualify.

## Decision 2 — Mermaid rendering: reuse the exact `flowchart` UML-use-case-diagram workaround already used in `docs/diagrams/use-case-diagram.md`

**Decision**: Render as a Mermaid `flowchart LR`: one oval actor node per
distinct actor kind present (`id(["label"])` syntax), one oval use-case node
per entry point, both grouped appropriately (use-case nodes inside a
system-boundary `subgraph`, mirroring the hand-authored diagram), and one
plain `-->` arrow from each actor to each of its use cases. No `<<include>>`/
`<<extend>>`-style labeled edges are generated (unlike the hand-authored
diagram's `-->|include|`/`-->|extend|` — see Alternatives) since this
feature's entry points have no notion of one use case including or extending
another; only actor-to-use-case associations exist.

**Rationale**: Mermaid has no native UML use-case-diagram grammar — confirmed
by inspecting Mermaid's supported diagram types (`flowchart`,
`sequenceDiagram`, `classDiagram`, `stateDiagram`, `erDiagram`, etc.; no
`usecaseDiagram`). This project already solved exactly this problem for its
own hand-authored project documentation
(`docs/diagrams/use-case-diagram.md`, see its own header comment: "Mermaid
has no native UML use-case diagram type, so this is a `flowchart` that
mimics one"). The brief explicitly names this file as the pattern to reuse.
Reusing the identical node-shape/subgraph/arrow conventions means the
generated diagram reads consistently with the one already maintained for
this project itself, and renders through the same already-vendored, offline
`mermaid.min.js` bundle every other diagram in this project uses (013/021/
022) — no new asset, no new dependency.

**Alternatives considered**:
- Generating `-->|include|`/`-->|extend|` labeled edges between use cases,
  matching every visual detail of the hand-authored diagram — rejected: the
  hand-authored diagram's include/extend edges exist because some of its use
  cases genuinely compose (e.g. `repo-scanner index` includes generating
  summaries, embeddings, and docs). An entry point identified by 022 has no
  such composition relationship with another entry point; inventing one here
  would misrepresent the data. Only actor-to-use-case associations are
  generated (spec FR-002/FR-003/FR-004 describe only that relationship).
- A `classDiagram`-style rendering (stereotyped classes) — rejected: less
  visually recognizable as a use-case diagram than the flowchart-oval
  convention already established and named by the brief.

## Decision 3 — Actor derivation: one shared actor per `EntryPointKind`, fixed canonical labels and order

**Decision**: `EntryPointKind` (022: `"cli-command" | "api-route" |
"function"`) *is* the actor category — no new enum. Each kind present among
the identified entry points gets exactly one shared actor node:
`"cli-command"` → an actor labeled `CLI`, `"api-route"` → an actor labeled
`API`, `"function"` → an actor labeled `External Caller` (the generic
fallback for an entry point whose exposure kind cannot be determined as CLI
or API, per spec FR-004). Actors are emitted in that fixed order
(CLI, API, generic) whenever present, never in encounter order, so repeated
generation runs produce byte-identical diagrams for the same entry-point
set.

**Rationale**: Directly satisfies FR-003/FR-004: "un acteur distinct pour les
commandes CLI, un acteur distinct pour les routes d'API HTTP, avec repli sur
un acteur générique unique". Reusing `EntryPointKind` as the actor key avoids
introducing a second classification scheme that would need to be kept in
sync with 022's; the two concepts (why an entry point is a sequence-diagram
subject vs. why it's a use-case's actor) are the same underlying fact about
how the entry point is exposed.

**Alternatives considered**: One actor per individual CLI command / API
route (e.g. a distinct actor per Typer command) — rejected: the spec's Key
Entities section and Assumptions are explicit that there is "one shared
actor instance per category, not one actor per individual entry point,
consistent with standard use-case-diagram convention" — matching how the
hand-authored diagram itself uses one `operator` actor for multiple CLI
use cases, not one actor per command.

## Decision 4 — Use-case label disambiguation: `Module[.Class].name`, synthetic Mermaid ids

**Decision**: Each use-case node's label is the entry point's
`Module[.Class].name` (module name, plus class name when the entry point is
a method, else omitted) — the exact same label convention 022's
`build_sequence_diagram_mermaid_source` already uses for its own participant
labels. Every actor and use-case node gets a short synthetic Mermaid id
(`a0`, `a1`, ... for actors; `u0`, `u1`, ... for use cases), mirroring
`build_class_diagram_mermaid_source`'s `c0`/`c1` convention and 022's `p0`/
`p1` convention. Labels are sanitized against a literal, unescaped `"` using
the existing `_escape_label` helper (`mermaid_diagram.py`), already used for
the flowchart-based dependency diagram.

**Rationale**: A bare function name (e.g. `run`) is not guaranteed unique
across modules, so both the label (for readability) and a synthetic id (for
a valid, collision-free Mermaid node identifier) are needed — exactly the
same reasoning `class_diagram.py`/`entry_point_diagram.py`'s rendering
functions already documented for their own node ids. Reusing 022's label
format keeps the generated wiki visually/textually consistent between the
two diagram types that both originate from the same entry-point list.

**Alternatives considered**: Using the entry point's bare name directly as
both label and Mermaid id — rejected for the same collision/validity reasons
021/022 already rejected it.

## Decision 5 — Page placement: one single, repository-wide page linked from the wiki's home page, following 021's pattern exactly (not 022's)

**Decision**: Add one new `PageKind` value, `"use-case-diagram"`. The page
id is a fixed constant (`links.use_case_diagram_page_id()` →
`"diagram:use-case-overview"`), and its output path is a fixed
`diagrams/use-case-overview.md`/`.html`, mirroring `CLASS_DIAGRAM_PAGE_ID`/
`CLASS_DIAGRAM_OUTPUT_MARKDOWN` exactly (021). `DocGenerator.
generateUseCaseDiagramPage()` returns `None` when `select_use_cases()`
produces zero use cases (i.e. the repository exposes no identifiable entry
point — spec FR-005), matching `generateClassDiagramPage()`'s
zero-classes-returns-`None` contract. The page, when present, is linked once
from the wiki's overview/home page (`generateOverviewPage`, mirroring the
existing `class_diagram_link`) — never from a per-module or per-entry-point
page.

**Rationale**: Directly satisfies spec FR-001 ("diagramme...unique, à
l'échelle du dépôt") and the brief's explicit "Une seule page, liée depuis la
page d'accueil du wiki généré." This is structurally identical to how 021's
class diagram is placed — a single, always-recomputed, sometimes-absent page
off the home page — not like 022's one-page-per-entry-point pattern, because
this diagram is inherently repository-wide (one diagram encompassing every
actor/use-case), not scoped to an individual entry point.

**Alternatives considered**: None seriously considered — the brief and spec
both explicitly call for a single page linked from the home page, matching
021's already-established precedent exactly.

## Decision 6 — Incremental regeneration: reuse 021's "always refresh on any qualifying change" rule, and reuse the entry-point list `impact.py` already computes for 022

**Decision**: Extend `compute_regeneration_impact` so the use-case-diagram
page id is added to `impactedPageIds` whenever the repository has at least
one identified entry point *and* there is any direct symbol change or
dependency-edge change in this run — the same condition already used for
021's class-diagram invalidation (`has_any_class and (direct_symbol_ids or
changed_edges)`), substituting "has any entry point" for "has any class".
The entry-point list itself is not recomputed a second time for this
purpose: `impact.py` already calls `identify_entry_points()` once per run to
invalidate 022's sequence-diagram pages (research.md Decision 8 of 022); this
feature's check reuses that same in-memory list. When the repository has zero
entry points, the use-case-diagram page id is excluded from
`current_page_ids`, so a previously generated page is removed via the
existing `removedPageIds` mechanism the same way 021's class diagram is
removed when a repository's last class is deleted.

**Rationale**: The use-case diagram's actor/use-case set depends on the same
repository-wide, cheaply-recomputed entry-point membership 022's diagrams
already depend on (which functions currently qualify, and as what kind) —
not on any individual symbol's content beyond what already triggers 022's
own invalidation. Reusing 021's established "repository-wide page, refresh
on any qualifying change" rule avoids inventing a third invalidation strategy
for what is structurally the same kind of page (021's class diagram) built
from what is structurally the same kind of input (022's entry-point list).
Reusing `impact.py`'s already-computed entry-point list (rather than calling
`identify_entry_points()` a second time) keeps the extension a small,
additive diff instead of duplicating a graph scan `impact.py` already pays
for.

**Alternatives considered**: A finer-grained rule that only invalidates the
page when an entry point is actually added/removed/reclassified (diffing the
current entry-point set against a previously recorded one) — rejected as
unnecessary complexity: 021 already established that a coarser,
always-refresh-on-any-qualifying-change rule is an acceptable, much simpler
trade-off for a single repository-wide selection page, and this feature's
selection is no more expensive to recompute than 021's.

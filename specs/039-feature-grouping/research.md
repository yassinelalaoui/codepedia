# Research: Feature Grouping That Follows the Code

Phase 0 for [plan.md](plan.md). Every measurement below is read-only, taken
on 2026-09-15 from the indexed state of the two reference repositories
(`codepedia-sample-repo`, 51 modules; `nextgen-wealth-ledger`, 109 modules)
with no provider. The prototype that produced the grouping numbers
re-implements the spec's rules outside `src/` (session scratchpad
`grouping_proto.py`, output `proto-run1.txt`).

---

## Decision 1: Every non-test module with an entry point stays a seed

The question deferred from `/speckit-clarify`: should a module whose only
entry points are uncalled public functions (not commands, routes or `main`)
still seed a group?

**Decision**: yes. The seeds are every non-test module with at least one entry
point (the spec's assumption). Entry modules are protected from folding
(FR-006a) but are not the only seeds.

**Measured** (the prototype applies every other 039 rule identically under both policies):

| | Sample, all seeds | Sample, entry modules only | Nextgen, all seeds | Nextgen, entry modules only |
| --- | --- | --- | --- | --- |
| Seeds | 21 | 5 | 60 | 1 (`main`) |
| Groups | 14 | 7 | 21 | 22 |
| Largest group | 9 modules, **18%** | 34 modules, **67%** | 17 modules, **16%** | 23 modules, 21% (the directory `dtos`) |
| One-module groups | 1 | 1 | 3 | 1 |

**Rationale**:

- With entry modules only, the sample's five route and CLI modules claim
  nearly the whole repository through coupling, recreating the catch-all
  group this spec removes.
- On `nextgen-wealth-ledger`, where Spring controllers are not recognised as
  routes (annotations are out of scope), there is only one entry module, so
  grouping degenerates to directories.
- With every non-test seed, both repositories stay well under the 30% ceiling
  (SC-001), and the groups read as parts of the application (Decision 7).

**Alternatives considered**: entry modules only, rejected on the numbers
above. "All seeds, but entry-module seeds win ties" adds a rule the numbers
do not ask for.

---

## Decision 2: Java and JS/TS imports are resolved from the graph's import nodes against a path index

**Finding**: for Java and TypeScript, `DependencyGraph` holds one import node
per imported name, and the names are clean. Examples from `nextgen-wealth-ledger`:

- `ma.yassine.digitalbanking.dtos.*`
- `jakarta.validation.Valid`
- `../../core/services/account.service`

But the node's `sourceFile` is **empty**. `features.fallback.build_import_adjacency`
maps a node to a module through `sourceFile`, so every such node maps to
nothing, before its name check even runs. Python nodes are resolved to a
file, which is why only Python has coupling.

> The spec's Background first attributed the loss to the name check. The
> effect is the same, but the first cause is the empty `sourceFile`. The
> wording was corrected with the owner's approval (Decision 12).

**Decision**: a new `features/imports.py` (no engine) turns a Java or JS/TS
module's import node names into repository module keys. It uses an index of
repository-relative paths built once per run. Python modules keep 033's
adjacency exactly (FR-005).

- **Java**:
  - A name `a.b.C` resolves to the module whose repository-relative path,
    without `.java`, ends with the whole of `a/b/C`, at a path-segment
    boundary. A partial match never counts: `org.other.dto.AccountDTO` does
    not match `…/dtos/AccountDTO`, nor `…/x/dto/AccountDTO` (FR-002). When
    several modules match (the same class under two source roots), the
    smaller path key wins.
  - A static or nested-class import (`a.b.C.method`, `a.b.C.Inner`) is
    retried with the last segment dropped, one at a time, down to two
    segments. The first, and so the longest, name that matches wins.
  - A wildcard `a.b.*` resolves to every Java module whose directory ends
    with `a/b`.
  - Names outside the repository (`java.util.List`, `org.springframework…`)
    resolve to nothing.
- **JS/TS**:
  - A name starting with `.` is joined to the importer's directory and
    normalised (`..` popped).
  - It is then tried as given, with each of `.ts .tsx .js .jsx .mjs .cjs`,
    and as `<dir>/index` with each extension. The first existing path wins.
  - Bare package names (`@angular/core`, `rxjs`) resolve to nothing. So do
    path aliases such as `@app/…` from `tsconfig`, which neither reference
    repository uses (Decision 11).

**Measured** (the prototype read the same names from the parsed import lines):

- **Java**: 59 direct imports and 7 wildcard imports resolved; 263
  external imports correctly resolved to nothing.
- **TypeScript**: 75 of 75 relative imports resolved; 196 package imports
  correctly resolved to nothing.
- **Coupled modules**: Java 0 → 63 of 64, TypeScript 2 → 42 of 43. The one
  uncoupled Java file is `DigitalBankingApplication`, and the one TypeScript
  file imports only packages. SC-002's 90% is met with room to spare.

**Alternatives considered**:

- **Setting `sourceFile` on these nodes inside `dependency_graph`.** Rejected
  for this spec. It changes a lower package that every stage reads, it touches
  graph persistence, and it would need 033's Python name check to be proven
  harmless for other languages. Resolving at the point of use keeps the change
  inside `features/`.
- **Parsing the raw `module.imports` lines**, as the prototype does. It works,
  but the graph already holds each name once, parsed. Using the nodes avoids a
  second, regex-based parser.

---

## Decision 3: Test recognition, entry kinds and the README lead move down into `features/evidence.py`

`features` must now recognise test files, entry kinds and the README's opening
paragraph. All three live in `overview/evidence.py` (spec 038), and `overview`
already imports from `features`. Importing the other way would create a cycle.

**Decision**: move `is_test_path` (with its patterns), `ENTRY_KINDS` and the
"`main` counts as kind `main`" rule, and `read_readme_lead` into
`features/evidence.py`. `overview/evidence.py` imports and re-exports them,
so 038's callers and tests are unchanged. The rule stays "one definition,
imported by both", as `prose.is_prose_file` already does.

**Alternatives considered**:

- A new `doc_generator/code_roles.py` module: one more module for three
  helpers, with no clear gain.
- Duplicating them: rejected because the two copies would drift, the bug
  `prose.py`'s docstring describes.

---

## Decision 4: Weights are exact fractions only where a wildcard splits; Python weights are untouched

FR-003 requires a wildcard import to couple no more strongly, in total, than
one direct import. Splitting weight 1 across *n* modules needs non-integer
weights.

**Decision**: adjacency values become `int | Fraction`. A direct import adds
1, as today. A wildcard import adds `Fraction(1, n)` to each of the *n*
package members. Python edges stay `int`, so a Python-only repository's
adjacency is value-for-value identical (FR-005). `Fraction` is exact, so sums
and comparisons are identical on every run.

The consumers are `fallback._label_propagation`,
`candidates._assign_by_coupling`, `candidates._best_absorption_target`
(replaced, Decision 6), `fallback.lead_module_key` and the internal-edge
listing in `validate`. They only add and compare, which `int` and `Fraction`
do together.

**Alternatives considered**:

- `float`: sums depend on addition order, which threatens determinism (033
  FR-002).
- Scaling every weight by a constant: changes Python's values, so FR-005 fails
  literally.
- Counting a wildcard as 1 to every member: measured on
  `nextgen-wealth-ledger`, one `import …dtos.*` would weigh 23 times a direct
  import, which is exactly what FR-003 forbids.

---

## Decision 5: Tests are excluded from grouping and placed afterwards

**Decision**:

1. Seeds are non-test modules only (FR-008).
2. Seeded propagation, fallback clustering and folding see production modules
   only. Test files are removed from the adjacency they read, so a test can
   never carry a label to a production module.
3. After production groups are final, each test file joins the group holding
   most of the production modules it is coupled to, measured by summed
   weight, with ties going to the smaller group seed key (FR-009).
4. A test coupled to no production module, such as a fixtures-only file, is
   placed by the directory walk of Decision 6 step 3, counting production
   modules only (tests already placed do not count). Tests still unplaced and
   sharing a directory then combine into one group for it (step 4), and one
   left alone goes to the terminal group (step 5). This never creates a group
   past the cap: once the cap is reached, such tests go to the terminal group.

**Measured** (sample): `test_fines.py` now sits with `fine_calculator.py` in
the loans slice, not the other way round. No group is seeded by a test
(SC-003). The sample's `tests/conftest.py` imports production code, so it is
placed by coupling (with `routes_members`), not by directory.

**Alternatives considered**: one "Tests" feature, or one per test directory
(options B and C at `/speckit-specify`; the owner chose A).

---

## Decision 6: Folding order, and what "its directory" means

FR-006 and FR-006a, made exact. **Directory** means the modules directly in a
directory, never its whole subtree. Measured, subtree semantics would send
every root-level file to the group with the most modules under `.`, which is
the largest group again.

**Order of operations**, all deterministic (ties on the group's seed key):

1. **Fold small non-entry groups by coupling.** A group below
   `MIN_CANDIDATE_MODULES` (2) that holds no entry module folds into the
   surviving group it is most coupled to, if that coupling is greater than 0.
2. **Protect entry modules.** A small group holding an entry module folds only
   into another group holding an entry module: the one it is most coupled to,
   or failing that the one found by step 3's directory walk over entry groups
   only. Otherwise it survives at any size. Entry groups of
   `MIN_CANDIDATE_MODULES` or more never combine here, only under the cap
   (step 6). Measured: the sample's one-module `routes_books.py` group folds
   into the `routes_loans.py` group, while the `routes_members.py` and
   `routes_loans.py` groups, both larger, stay apart although they share
   `api/`. `DigitalBankingApplication` (nextgen) survives alone, and `cli.py`
   (sample) stands with its package `__init__`.
3. **Place uncoupled small groups by directory.** A small group with no
   coupling to any survivor joins the surviving group holding the most
   modules directly in its own directory, then in its parent, and so on. The
   walk never climbs from a subdirectory into the repository root: it stops at
   the top-level directory, so a frontend orphan cannot join a backend group
   through a root-level module (spec edge case "Unconnected halves"). A group
   whose own directory is the root is still placed by the root's modules. On
   both reference repositories no group needed the root step, so the
   prototype's numbers are unchanged by this limit.
4. **Combine leftovers by directory.** Small groups still unplaced, and
   sharing a directory, combine into one group titled by that directory
   (033's `default_group_title`). One that reaches `MIN_CANDIDATE_MODULES`
   survives.
5. **Terminal group.** Anything still alone joins one explicitly built
   terminal candidate titled "Support & Utilities", of kind tooling. This is
   033 FR-014's bucket, built here rather than in repair. Repair
   (`validate._place_remainder`) still sends a candidate whose title is
   unusable or taken to a terminal bucket. From this feature on, that bucket
   joins the feature already titled `TERMINAL_FEATURE_TITLE` (the terminal
   candidate's, or a planned feature the model titled so) instead of building
   a second one. So at most one feature carries that title. The terminal
   group may hold a single module (the sample's `README.md`). It is still one
   explicit bucket, not one of many one-module groups.
6. **Cap.** Past `MAX_PROMPTED_CANDIDATES` (32), the smallest non-entry
   groups fold by steps 1 and 3 until the cap holds. Entry groups fold last,
   and only into entry groups, by coupling, then the directory walk. An entry
   group with neither joins the entry group whose directory shares the
   longest leading path with its own, ties to the smaller seed key. Neither
   reference repository reaches the cap.
7. **Counts.** Entry-point counts are recomputed from members (Decision 8),
   so no fold can drop them.

**Steps 1 to 3 run per group, not per step** (found at T020). One small group
at a time, smallest first: its coupling target, else its directory target.
The order is taken again after every fold, as the prototype does. The first
implementation ran every coupling fold before any directory placement. On the
sample, `scripts/seed_data.py` then absorbed the CLI and two route modules one
small group at a time. It is an entry module (`main`) that imports nearly
everything, and it made a 15-module group, the "Scripts" outcome this spec
removes. Per group, the package `__init__` reaches `cli.py` through its
directory first, and the groupings match the prototype's: all 14 on the
sample, and 19 of 20 on nextgen (`README.md` and `refactor.py` combine under
step 4). The outputs are in `measurements/proto-vs-impl.*.us2.txt`; the
discarded order's comparison is `proto-vs-impl.nextgen.us1.txt`.

**No survivor at all** (owner decision, 2026-09-15, found at T015): when no
group can stand alone, meaning none reaches `MIN_CANDIDATE_MODULES` and none
holds an entry module, steps 1 to 5 are skipped and the groups stay as they
are, as in 033. Only the cap applies. Applied literally, step 4 would combine
them all by directory. The shared test fixture (three coupled one-module
seeds, `alpha`/`beta`/`gamma`) then became one "Root" feature holding the
whole repository, which repair rejects as "not navigation"
(`MIN_PLANNED_FEATURES`), and 15 tests of the 033 and 038 suites failed on
that alone. The prototype kept the groups too. Neither reference repository
reaches this case.

**Fallback clustering** follows the same root limit (owner decision,
2026-09-15). 033's `fallback._ancestor_target` absorbed a directory too small
to stand alone into the root group when no nearer ancestor was a group. It no
longer climbs into the root. Measured, both reference groupings are identical
with and without the limit.

**Measured**:

- Sample: 14 groups; `README.md` is the only file left alone.
- Nextgen: 21 groups; `README.md` and `refactor.py` both sit at the root, so
  step 4 combines them into one "Root" group.
- Under step 5, the sample's lone `README.md` goes to the terminal group.

**Alternatives considered**:

- 033's "largest survivor" rule: it produced the 93-module group.
- Leaving isolated files as one-module groups: that contradicts FR-006's
  "MUST fold" and adds sidebar noise.
- Subtree directory semantics: rejected as measured above.

---

## Decision 7: Anchor order is entry module, then seed, then most connected

**Decision** (FR-010): a feature's anchor, and so its key and page address, is:

1. its entry module with the most entry points;
2. else its non-test seed with the most entry points;
3. else 033's `lead_module_key` (most internally connected member).

Ties go to the module name, then the key. Computed in `validate._build_features`
from `RepositoryEvidence`, so it holds after the model's merges.

**Measured anchors**:

- **Sample:** `cli.py`, `routes_loans.py`, `routes_members.py`,
  `lending_service.py`, `catalog_service.py`, `memory_store.py`,
  `sqlite_store.py`, `email_gateway.py`, `book.py`, `clock.py`, `app.py`,
  and `api-client.js` for the web client. `ids.py`, `errors.py`,
  `member.py` and `fine_calculator.py` are no longer anchors.
- **Nextgen:** `WalletService`, `WalletServiceImpl`, `AuthServiceImpl`,
  `AuthService`, `ChatbotService`, `ClientController`, `account.service.ts`,
  `auth.service.ts`, `navbar.component.ts`, `account-detail.component.ts`,
  among others. `animations.ts` is no longer an anchor.

**Consequence**: most feature keys change on the first run after upgrading,
and 033's plurality redirect (`_redirect_superseded_pages`) keeps every old
address resolving (FR-011). No new mechanism is needed.

**Alternatives considered**: keep 033's most-connected rule. It picked the
helper modules in every reported case.

---

## Decision 8: Entry-point counts come from members, excluding tests

`Candidate.exposedEntryPointCount` and `Feature.exposedEntryPointCount` are
recomputed as the number of entry points held by the non-test member modules,
after all folding and merging.

Measured on `nextgen-wealth-ledger`, the old candidate-sum rule dropped every
absorbed candidate's count, and every feature showed 0. The recomputed counts
sum to the repository's non-test entry points (SC-004).

---

## Decision 9: The plan cache key covers the grouping

`planner.plan_cache_key` hashes module keys and entry-point keys, the
repository's structure. The plan it stores refers to candidates by position
(`c0`, `c1`, …), so a cached plan is only right for the grouping that
numbered them.

**Finding**: this is a latent 033 defect, not only a 039 one. In Python, an
import edit already changes the grouping without changing the key, and the
old titles are then applied to whichever groups now hold those positions.

**Decision** (FR-018): the key also hashes, in handle order, each candidate's
sorted member keys, plus a `GROUPING_VERSION` constant. It is bumped whenever
the grouping rules or the planning prompt change, so the first run after this
feature ships misses the cache once per repository.

**Order of work**: the new key lands in the foundational phase, before any
grouping rule changes (tasks T006a and T006b). Otherwise every intermediate
state, the MVP stop after User Story 2 included, would apply the cached 033
plan's titles and merges to the new groups, the defect this Decision fixes.
It would also contaminate the no-model measurements of T016, T020 and T025,
because `planner_probe.py` applies the cached plan. `GROUPING_VERSION` starts
at `"2"` there and becomes `"3"` when User Story 4 changes what the model is
shown (T029). A plan cached from the MVP's prompt is then not reused.

**Cost**: an edit that reshapes the grouping now costs one planner call, where
it previously cost a silently wrong title. An edit that does not reshape costs
nothing. Grouping reads only imports and entry points, never summaries, so the
structure pass and content pass of one index run still share one call. The
`doc_feature_plans` table is unchanged: only the key's inputs change.

**Alternatives considered**: storing the plan by seed module rather than by
handle, so titles survive regrouping. That is better for incremental runs,
but it contradicts the spec's "exact grouping" wording and changes the stored
format. It is recorded as a possible follow-up.

---

## Decision 10: What the planner is shown

- **Members** (FR-012): up to `MAX_MEMBERS_PER_CANDIDATE` (3), in this order:
  the seed, when it is a member (the terminal group's placeholder seed is
  not); then non-test members by entry points, descending; then by summed
  coupling inside the group, descending; then by label.
- **Labels** (FR-013): `prose.disambiguated_labels` over the whole
  repository's modules (038 User Story 4), so two `__init__` files read
  `api/__init__` and `core/__init__`. A label is cut to its last path
  segments within a new `MAX_MEMBER_LABEL_CHARS` (40). The planner's
  worst-case arithmetic counts this cap, where today it counts an uncapped
  module name inside `MEMBER_LINE_OVERHEAD_CHARS`.
- **Repository description** (FR-014): `read_readme_lead` (Decision 3), the
  README's first prose paragraph, replaces `read_readme_bullets`.
  `MAX_README_PROMPT_CHARS` (1,500) still bounds it, and the lead itself is
  already capped at 600. The worst case can only fall.
- **Budget** (FR-015): `worst_case_call_tokens()` is recomputed from the
  constants, and the existing test asserts it stays ≤ 8,000.
  `test_feature_planner.py` gains the label cap in its arithmetic.

---

## Decision 11: Known limits, measured and accepted

- **No path aliases or tsconfig `paths`.** Neither reference repository uses
  them (75 of 75 relative imports resolved). An aliased import resolves to
  nothing and adds no coupling (FR-002). That costs grouping quality, never
  correctness.
- **Interfaces.** Java interface and implementation can land in separate
  groups (`WalletService` and `WalletServiceImpl` on nextgen), because both
  are seeds and calls through interfaces are not resolved (out of scope). The
  model may combine them. The Overview then names both.
- **Wildcard imports** couple a module to a whole package at 1/*n* each. A
  class used from a wildcard package is not singled out.

---

## Decision 12: Spec amendments this research asks for (approved by the owner and applied 2026-09-15)

1. **SC-006.** The measured grouping forms vertical slices: a controller joins
   the service and DTOs it uses (wallets, auth, chatbot, clients). There is no
   "controllers" feature to find. Proposed: replace "`nextgen-wealth-ledger`'s
   controllers, security and frontend" with "`nextgen-wealth-ledger`'s
   wallets, authentication and security, chatbot and frontend parts".
2. **FR-006.** Proposed: say "modules directly in its own directory" rather
   than "from its own directory", and add Decision 6 step 4 (leftovers
   sharing a directory combine before the terminal group).
3. **Background, first bullet.** Proposed: say Java and TypeScript import
   nodes carry no source file, so 033's adjacency maps them to no module.
   Drop the attribution to the name check (Decision 2).

### Addendum: `/speckit-analyze` remediation (owner-approved, applied 2026-09-15)

All 18 findings were applied to the spec, plan, research, data model,
contract, quickstart and tasks:

- **HIGH:**
  - I1: the cache key moves ahead of the grouping change (Decision 9, T006a/T006b).
  - I2: at most one terminal feature (Decision 6 step 5).
  - A1: FR-006a made exact, so only small entry groups combine (Decision 6 step 2).
- **MEDIUM:**
  - U1: no climbing into the root (step 3).
  - U2: test placement's directory fallback (Decision 5 step 4).
  - A2: SC-002 counted per import.
  - A3: the exact Java suffix rule (Decision 2).
  - C1: every old address is checked.
  - C2: a Java body-only edit keeps the grouping.
  - C3: the tests-only repository gets a test.
- **LOW:**
  - C4: a call without an import adds no coupling.
  - U3: entry groups beyond the cap (step 6).
  - U4: the terminal group's placeholder seed (Decision 10).
  - Cross-reference fixes I3 to I6 and T1.

**Where the prototype differs from these rules**, so T016, T020 and T025
explain rather than chase the differences:

- `grouping_proto.py` has no cap step, no leftover-combining step and no
  terminal group. A module left alone stays a one-module group.
- An uncoupled test whose directory walk reaches the root joins the
  *largest* group, a shortcut FR-006 forbids.
- Its directory walk may climb into the root. Neither reference repository
  exercised that path.

---

## Resolved unknowns

| Unknown | Resolution |
| --- | --- |
| Do non-entry modules stay seeds? | Yes (Decision 1, measured) |
| Where are Java and TS import targets available? | Graph import node names; `sourceFile` is empty (Decision 2) |
| How to weight a wildcard exactly? | `Fraction(1, n)`, Python ints untouched (Decision 4) |
| Import cycle between `features` and `overview`? | Move three helpers down into `features/evidence.py`, re-export (Decision 3) |
| What "directory" means when folding | Direct members of the directory, not its subtree (Decision 6) |
| Does the upgrade need new redirect code? | No. Plurality redirects plus `requiresNavigationRegeneration` already cover it (Decision 7) |
| Does the plan cache survive regrouping? | It must not. The key hashes the grouping (Decision 9) |
| New dependency? | None: `fractions`, `re`, `pathlib` are standard library |

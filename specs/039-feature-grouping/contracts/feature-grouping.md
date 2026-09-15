# Contract: The Feature-Grouping Stage

The internal contract of `src/doc_generator/features/` after spec 039: what
each function takes, returns and guarantees, and which test proves it. The
wiki's pages, the Overview (038) and the alias mechanism are consumers and are
not changed.

## §1 Package invariant (unchanged from 033)

`evidence`, `imports`, `fallback`, `candidates` and `validate` take **no LLM
engine**. `planner` is the only module that takes one, and it only names and
combines whole candidates. `tests/unit/test_feature_*` asserts that no model
is reachable from the grouping stages.

## §2 `features/imports.py` (new)

```python
def resolve_repository_imports(
    bundle: RepositoryBundle, graph: DependencyGraph, *, repository_root: str | Path
) -> dict[str, dict[str, int | Fraction]]: ...
```

- Reads, for each Java, JavaScript and TypeScript module, its import node
  names (`graph.dependencies(filePath, relation_type="import")`) and resolves
  them per research Decision 2. It never reads the analysed repository's
  files: the names are already in the graph.
- Returns only edges between two distinct repository modules, symmetric, with
  the weights in data-model.md § Adjacency. Python, Go, Rust and Markdown
  modules contribute nothing here.
- Deterministic: the path index and the resolution order are fixed. A Java
  name matches only a path ending with the whole name at a segment boundary,
  never a partial suffix. Retries drop trailing segments one at a time, and
  the first name that matches wins. Among several modules matching the same
  name, the smaller path wins.
- Coupling comes from import names only. A recorded call between two modules
  with no import between them adds nothing (FR-004).

**Tests** (`test_feature_imports.py`):

- a direct Java import, a static import, a nested-class import;
- a wildcard import weighted `1/n` (FR-003);
- an external Java import yields nothing, and neither does a same-named class
  in another package;
- a call without an import yields nothing (FR-004);
- JS/TS relative imports with and without an extension, `../` normalisation,
  `index.ts`;
- a package import yields nothing, and a missing relative target yields
  nothing;
- the same input gives equal output.

## §3 `features/fallback.build_import_adjacency` (extended)

Unchanged signature. It returns 033's Python adjacency merged with
`resolve_repository_imports`.

**Test**: on a Python-only fixture, the result equals 033's, value for value
(FR-005).

## §4 `features/evidence.build_repository_evidence` (extended)

Adds `readmeLead`, `testModuleKeys`, `entryModuleKeys`, `seedModuleKeys` and
`moduleLabels` (data-model.md). It also owns `ENTRY_KINDS`, `is_test_path` and
`read_readme_lead`, which `overview/evidence.py` re-exports unchanged.

**Test**: the spec 038 test suite passes untouched against the re-exports.

## §5 `features/candidates.build_candidates` (rules replaced)

Signature unchanged: `(evidence, adjacency) -> tuple[Candidate, ...]`.

1. Seeds are `evidence.seedModuleKeys`. Tests never seed (FR-008).
2. Propagation (033's seeded label propagation, `MAX_ATTACH_DISTANCE` sweeps)
   and fallback clustering read the adjacency **restricted to production
   modules**.
3. Folding follows research Decision 6 steps 1–6: coupling first, entry
   groups protected (only small ones combine, and only with entry groups),
   then the direct-directory ancestry walk, which never climbs from a
   subdirectory into the root, then leftovers combined per directory, then
   the terminal candidate, then the cap. When no group can stand alone,
   nothing folds and only the cap applies, as in 033. The fallback
   clustering's ancestor absorption never climbs into the root either.
4. Test files are placed after folding (research Decision 5, FR-009). A test
   coupled to no production module follows the directory walk counting
   production modules only, then combines with unplaced tests in its
   directory, then goes to the terminal candidate.
5. `exposedEntryPointCount` is recomputed from non-test members (FR-007).

**Post-conditions** (asserted, as in 033):

- the union of all `memberKeys` is every module;
- candidates are pairwise disjoint;
- no candidate is chosen as a fold target for being largest;
- no candidate without an entry module has absorbed one;
- output is identical for identical input.

**Tests** (`test_feature_candidates.py`, on hand-built evidence and adjacency):

- tests never seed;
- a production module coupled only to its test does not join a test group;
- a one-module command module survives (FR-006a);
- two small entry groups in one directory combine, and two entry groups of
  two or more modules in one directory stay apart;
- an uncoupled group joins the survivor with the most modules directly in its
  own directory, then in its parent, and never climbs from a subdirectory
  into the root;
- root-level leftovers combine;
- a truly isolated module lands in the terminal candidate;
- the cap folds non-entry groups first, and entry groups beyond it combine by
  coupling, then directory, then the longest shared leading path;
- entry-point counts add up to the non-test total;
- a test joins the group holding most of the code it exercises, and a
  fixtures-only test goes by directory, counting production modules only;
- a repository whose only entry points are in tests is grouped by directory,
  with no catch-all group.

## §6 `features/validate.repair` (anchor and counts)

Unchanged signature and repair table (033 FR-013 to FR-015), with one change:
`_place_remainder`'s terminal bucket joins the feature already titled
`TERMINAL_FEATURE_TITLE` (the terminal candidate's, or a planned one) instead
of building a second one. At most one feature carries that title.
`_build_features` chooses `key` per data-model.md § Feature and recomputes
`exposedEntryPointCount` from members.

**Tests** (`test_feature_validate.py`):

- the anchor is the entry module over a seed with more uncalled functions;
- the anchor is the seed over a better-connected helper;
- a feature with no seed keeps `lead_module_key`;
- a model merge of two candidates keeps the entry-module anchor;
- counts survive merges;
- at most one feature is titled `TERMINAL_FEATURE_TITLE`, with or without a
  plan.

## §7 `features/planner` (input and cache key)

- `build_feature_plan_prompt(candidates, evidence)` orders and labels members
  per data-model.md § Planning input, and uses `evidence.readmeLead` in place
  of the bullets.
- `plan_cache_key(evidence, candidates)` gains the `candidates` argument and
  hashes `GROUPING_VERSION` and the grouping (FR-018). `FeaturePlanner.plan`
  passes the candidates it was given. This lands before any grouping rule
  changes (research Decision 9, order of work).
- `worst_case_prompt_tokens()` counts `MAX_MEMBER_LABEL_CHARS`. The existing
  budget test asserts `worst_case_call_tokens() <= PROVIDER_TOKEN_BUDGET`.

**Tests** (`test_feature_planner.py`):

- the seed is the first member;
- the order is entry points, then coupling, then label;
- same-named members get distinct labels;
- the README lead is used and the bullets are absent;
- a changed grouping changes the key;
- an unchanged grouping keeps the key;
- a `GROUPING_VERSION` bump changes the key;
- the budget holds.

## §8 End to end

`tests/integration/test_feature_grouping_languages.py` uses a small fixture
repository with a Java backend (controller, service, DTO package imported by
wildcard, an exceptions package) and a TypeScript frontend (components and
services with relative imports, an `index.ts`). It asserts:

- every module is in exactly one feature;
- no feature holds more than 30% of the modules without a model;
- the controller, its service and the DTOs share a feature;
- the TypeScript components join their services;
- no feature holds both Java and TypeScript modules (edge case "Unconnected
  halves");
- anchors follow §6;
- a second run is identical;
- after an edit to one Java method body, touching no import or entry point,
  an incremental run keeps the candidates and the plan key, calls no model,
  and does not force a full regeneration (FR-019).

`tests/integration/test_feature_navigation.py` re-asserts 033's guarantees:

- the same modules and candidates with and without a model;
- one planner call per grouping, and zero on an unchanged rerun;
- redirects after a regroup.

# Data Model: Feature Grouping That Follows the Code

Phase 1 for [plan.md](plan.md). Only what changes is listed; every other 033
type keeps its fields and meaning. **No persistent schema changes.** The one
stored value affected is the plan cache key (see *Plan cache key* below).

## In-memory types

### `RepositoryEvidence`, `features/evidence.py` (extended)

| Field | Type | Rule |
| --- | --- | --- |
| `modules` | `tuple[FeatureEvidence, ...]` | Unchanged |
| `readmeBullets` | `tuple[str, ...]` | Unchanged; no longer read by the planner (Decision 10) |
| `readmeLead` | `str` | **New.** `read_readme_lead(root)`: the README's first prose paragraph, ≤ `MAX_README_LEAD_CHARS` (600) |
| `entryPointModuleKeys` | `tuple[str, ...]` | Unchanged: every module holding an entry point, tests included (033 callers rely on it) |
| `entryPointKeysByModuleKey` | `Mapping[str, tuple[str, ...]]` | Unchanged |
| `testModuleKeys` | `frozenset[str]` | **New.** Modules whose repository-relative path `is_test_path` accepts |
| `entryModuleKeys` | `tuple[str, ...]` | **New.** Non-test modules holding at least one entry point of a kind in `ENTRY_KINDS` (`cli-command`, `api-route`, `main`), sorted |
| `seedModuleKeys` | `tuple[str, ...]` | **New.** Non-test modules holding at least one entry point, sorted. These seed groups (spec FR-008; research Decision 1) |
| `moduleLabels` | `Mapping[str, str]` | **New.** `prose.disambiguated_labels` over every module, by module key, so same-named modules differ (FR-013). Computed here because only this stage holds the repository root |

`ENTRY_KINDS`, `is_test_path` and `read_readme_lead` are defined here from
this feature on and re-exported by `overview/evidence.py` (research Decision 3).
An entry point named `main` whose kind is `function` counts as kind `main`, as
in 038.

### Adjacency, `features/fallback.py` + `features/imports.py`

`dict[str, dict[str, int | Fraction]]`, keyed by `sourceFileId`, symmetric, no
self-loops.

| Source of an edge | Weight added (both directions) |
| --- | --- |
| Python import (033 rule, unchanged) | `1` per resolved import node (`int`) |
| Java direct import, including static and nested-class forms | `1` per distinct target module (`int`) |
| Java wildcard import of a package with *n* repository modules | `Fraction(1, n)` to each |
| JS/TS relative import resolving to a module | `1` per distinct target module (`int`) |
| Anything unresolved (standard library, third party, alias, missing file) | nothing |

For a repository with only Python modules, the adjacency is value-for-value
identical to 033's (FR-005, asserted by a test).

### `Candidate`, `features/candidates.py` (fields unchanged; rules changed)

| Field | Rule after 039 |
| --- | --- |
| `seedModuleKey` | The seed for a seeded group. The lead module (`lead_module_key`) for a directory or leftover group. A fixed sentinel for the terminal group, which is not a member key, so "seed first" (FR-012) skips it |
| `seedTitle` | For a group holding a seed, `default_group_title(anchor directory, anchor name, split=True)`, where the anchor follows FR-010 (owner decision, 2026-09-15). Directory and leftover groups keep `default_group_title(directory, lead, split=False)`. The terminal group uses `TERMINAL_FEATURE_TITLE` ("Support & Utilities") |
| `memberKeys` | Every module in exactly one candidate (033 FR-001). Test files are added after production grouping (research Decision 5). **Order carries relevance** (T027, FR-012): the seed, then production members by entry points (descending), by coupling to the rest of the group (descending), by label; test files last (owner decision, 2026-09-15). Feature pages still list members by name; the plan cache key sorts them |
| `exposedEntryPointCount` | **Recomputed from members**: the entry points of its non-test members (Decision 8) |

### `Feature`, `features/validate.py` (fields unchanged; rules changed)

| Field | Rule after 039 |
| --- | --- |
| `key` | Anchor (`candidates.anchor_for`), chosen in this order: the entry module with the most entry points, then the non-test seed with the most entry points, then `lead_module_key` among production members when there are any (a test never anchors; owner decision, 2026-09-15). A tie on entry points goes to the module whose entry points reach the most modules, then the module name, then the key (FR-010; Decision 7; owner decision after T036) |
| `exposedEntryPointCount` | The entry points of its non-test members, after merges (FR-007) |
| `title` | Unchanged, except that at most one feature carries `TERMINAL_FEATURE_TITLE`: repair's terminal bucket joins the feature already holding that title instead of building a second (FR-006; research Decision 6 step 5) |
| everything else | Unchanged |

### Planning input, `features/planner.py`

| Part | Rule |
| --- | --- |
| Group header | `c<i>: <seedTitle> (<n> modules)`, cut at `CANDIDATE_HEADER_CHARS`. Unchanged |
| Members | ≤ `MAX_MEMBERS_PER_CANDIDATE` (3): the seed when it is a member, then non-test entry points (descending), then internal coupling (descending), then label (FR-012) |
| Member label | `prose.disambiguated_labels` over all modules, cut to its trailing path segments within `MAX_MEMBER_LABEL_CHARS` (FR-013) |
| Member summary | First sentence of docstring or summary, ≤ `MAX_MEMBER_SUMMARY_CHARS` (120). Unchanged |
| Repository description | `readmeLead`, within `MAX_README_PROMPT_CHARS` (FR-014) |

### Plan cache key, `planner.plan_cache_key`

`sha1` over, in order:

1. `GROUPING_VERSION`;
2. the sorted module keys;
3. the sorted entry-point keys;
4. for each candidate in handle order, its sorted member keys.

The `doc_feature_plans` row format is unchanged. A key built from a different
grouping never matches (FR-018; Decision 9).

## Constants

| Constant | Value | Module | Note |
| --- | --- | --- | --- |
| `GROUPING_VERSION` | `"3"` | `features/planner.py` | New. `"2"` when the key starts hashing the grouping (T006b); `"3"` when User Story 4 changes the prompt (T029). Bump whenever the grouping rules or the planning prompt change; a bump makes one cache miss per repository |
| `MAX_MEMBER_LABEL_CHARS` | 40 | `features/planner.py` | New. Counted by `worst_case_prompt_tokens()` |
| `MEMBER_LINE_OVERHEAD_CHARS` | 10 (was 40) | `features/planner.py` | Now the bullet, separator and newline only; the name is bounded by `MAX_MEMBER_LABEL_CHARS`. Worst-case call 6,385 tokens (was 6,145) of 8,000 |
| `JS_RESOLVE_EXTENSIONS` | `(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")` | `features/imports.py` | New. The order is the resolution order |
| `MIN_CANDIDATE_MODULES` | 2 | `features/candidates.py` | Unchanged; entry groups are exempt (FR-006a) |
| `MAX_PROMPTED_CANDIDATES` | 32 | `features/candidates.py` | Unchanged |
| `MAX_ATTACH_DISTANCE` | 2 | `features/candidates.py` | Unchanged |
| `TERMINAL_FEATURE_TITLE` / `_KIND` | "Support & Utilities" / `tooling` | `features/validate.py` | Reused for the terminal candidate |

## State transitions

Grouping is recomputed in memory on every generation pass from stored state
(bundle, graph, README). It holds no state of its own between runs. The
observable transitions come from 033:

- **Grouping reshaped** (an upgrade, or an edit that changes imports or entry
  points): the feature list's shape changes, so `requiresNavigationRegeneration`
  forces a full pass. The old pages redirect to the feature holding most of
  their modules (`_redirect_superseded_pages`), and the plan cache misses once.
- **Grouping unchanged**: same candidates, same key, cached plan, identical
  pages (033 FR-002, FR-016).

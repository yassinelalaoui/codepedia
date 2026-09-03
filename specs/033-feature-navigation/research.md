# Phase 0 Research: Feature Navigation

**Feature**: 033-feature-navigation | **Date**: 2026-09-02

Every number below was measured against this repository, not recalled or
estimated. The probe is named for each decision so it can be re-run.

**The probe harness**: `<scratchpad>/probe_bundle.py` indexes this repository's
own `src/` tree (135 Python modules) into a throwaway SQLite and returns a real
`RepositoryBundle` + `DependencyGraph`. `<scratchpad>/probe_evidence.py` runs
probes 1-7 against it and prints every figure quoted here. Re-run:
`cd <scratchpad> && .venv/Scripts/python.exe probe_evidence.py`.

Baseline shape of the probe subject: **135 modules, 2416 graph nodes, 4801
edges, 167 entry points across 52 distinct entry-point modules, 15 sections
under today's clustering.**

---

## Decision 1: Reuse `identify_entry_points`, but not `build_entry_point_call_sequence`

**Decision**: `features/evidence.py` calls `identify_entry_points(bundle, graph)`
as-is, then walks `graph.functions_called_by` with **its own visited set**.

**Correction to the approved plan.** The plan justified avoiding
`build_entry_point_call_sequence` on cost: "at depth 6 with fan-out ~5 that is
~15k steps per entry point; over ~200 entry points it is millions". **Measured,
that is false on this repository.** Probe 2:

| Walk | Result |
| --- | --- |
| `build_entry_point_call_sequence` over 12 entry points | 256 steps, 0.001 s |
| projected over all 167 entry points | ~0.0 s |
| worst single entry point (`run`) | 117 steps |
| visited-set BFS over **all 167** entry points | 4001 symbols, 0.008 s |

The fan-out estimate was an order of magnitude too pessimistic, so cost is not
the argument. **The decision stands, on a different and better reason**: the
sequence walk deliberately has no visited set ([entry_point_diagram.py:147](../../src/doc_generator/entry_point_diagram.py#L147))
because a sequence diagram must draw a repeated call twice. Evidence asks "which
entry points reach this module", a set question, and answering it with a walk
that revisits by design means deduplicating its output anyway. It is also
unbounded in the worst case — a call cycle is bounded only by `MAX_CALL_DEPTH`,
so a pathological graph really can blow up, even though this one does not.

Recording the correction because the wrong reason would have been re-derived and
re-trusted the next time someone asked why there are two walks.

**Alternatives considered**: reuse the sequence walk and deduplicate (rejected:
pays for the repetition then discards it, and inherits the depth-6 cap that
belongs to diagrams, not to evidence); precompute one global reverse-reachability
map (rejected for now: the per-entry-point BFS is 8 ms total, so the shared
structure buys nothing and couples two modules).

---

## Decision 2: `MAX_ATTACH_DISTANCE = 2`, not 4

**Decision**: bound the attach BFS at **2**, and score by `1/(1+d)`.

**Correction to the approved plan**, and the most consequential finding in this
phase. The plan set the bound at 4, arguing "past d=4 successive scores differ by
less than 0.04 … depth 4 already reaches more nodes than the repo has modules, so
a larger bound buys reach that is already saturated". Probe 3 shows the
saturation arrives **two levels earlier than that**:

| Depth | Mean modules reached | Max | Score `1/(1+d)` |
| --- | --- | --- | --- |
| 1 | 10.4 / 135 | 100 | 0.500 |
| **2** | **132.0 / 135** | 134 | 0.333 |
| 3 | 135.0 / 135 | 135 | 0.250 |
| 4 | 135.0 / 135 | 135 | 0.200 |

Average module degree is **8.99**, not ~5, with a maximum of 127 — one module is
imported by nearly everything. At depth 2 the average seed already reaches 98% of
the repository; at depth 3 every seed reaches every module. A bound of 4 is
therefore not "conservatively generous", it is three levels past the point where
the relation `seed reaches module` carries any information at all.

**Why this matters beyond tidiness** — probe 4, run at the plan's bound of 4:

```
candidates after attach        : 52
modules claimed                : 135 / 135
candidate sizes (top 15)       : [64, 6, 4, 4, 3, 3, 2, 2, 2, 2, 2, 1, 1, 1, 1]
candidates below MIN=2         : 41
```

Total saturation means every seed reaches every module, so the assignment is
decided almost entirely by the `(-score, moduleKey)` tie-break rather than by
structure. The result is **one 64-module candidate and 41 singletons** — a
grouping that is worse than the directory clustering it replaces, and one that
consolidation would then fold into an even larger blob. This is not a tuning
detail; at depth 4 the candidate stage does not work.

**Rationale for 2 specifically**: depth 1 (mean reach 10.4) is the only level
with real discrimination, and depth 2 is where a seed picks up the modules its
direct imports pull in — the transitive closure of one capability's own
collaborators. Two is the largest bound at which the reachable sets still differ
between seeds on this repository.

**This constant must be re-verified against the candidate size distribution, not
just asserted.** The A1 hand-verification step (a script printing candidates for
this repository and for the alpha/beta/gamma fixture) is the check, and a unit
test pins the depth bound itself. If depth 2 still produces a dominant blob, the
scoring rule — not the bound — is what needs revisiting; see Decision 3.

**Alternatives considered**: keep 4 and rely on consolidation (rejected: the
measurement shows consolidation would be doing the grouping, not refining it);
depth 1 only (rejected: mean reach 10.4 with 52 seeds leaves too many modules
attached to nothing, pushing work onto the fallback path that is meant to be
exceptional); weight by edge count rather than hop distance (kept in reserve, see
Decision 3).

---

## Decision 3: Assign each module to its *nearest* seed, ties by seed locality

**Decision**: a module goes to the seed with the highest `1/(1+d)`; ties break on
`(-score, seedModuleKey)` as the plan specifies — but the depth bound from
Decision 2 is what makes the score meaningful enough for that tie-break to be a
tie-break rather than the whole rule.

**Rationale, from probe 4**: with a saturating bound, every module scores
identically against most seeds and the lexicographically smallest seed key wins
everything — which is exactly the 64-module candidate above. The rule is sound;
it was the bound that made it degenerate. Recorded as its own decision because
the failure looked like a bad tie-break and was actually a bad radius, and the
next person to see a dominant candidate will reach for the tie-break first.

**Open, to be settled in A1 by measurement rather than in prose**: whether
`1/(1+d)` alone is enough at depth 2, or whether the score needs an edge-weight
term (`adjacency[seed][module]`) to separate two seeds that both reach a module
in one hop. Probe 4 re-run at `MAX_ATTACH_DISTANCE = 2` answers this, and the
answer belongs in the A1 verification script's output, not here.

---

## Decision 4: Short ordinal handles — confirmed by measurement

**Decision**: the planner exchanges `c0`, `c1`, … and never a `moduleKey`.

**Probe 5**, measured on real keys:

| Quantity | Measured |
| --- | --- |
| `moduleKey` length | mean **116.6** chars, max 133 |
| example | `repo::C:/…/codepedia::file::C:/…/codepedia/src/chat/__init__.py` |
| 135 keys echoed in a response | 15,745 chars ≈ **3,936 tokens of identifiers alone** |
| 167 uncollapsed candidates in a prompt | ≈ **22,545 tokens** |

Against a Groq window of 8000 TPM, the module-keyed shape the original brief
described is nearly 3× over the ceiling in the prompt and burns half the
remaining budget on identifiers in the response. The decision was taken before
this was measured; the measurement confirms it with room to spare. Handles also
mirror the `n0`/`c0`/`p0`/`m0` convention `mermaid_diagram.py` already uses, for
the same reason.

---

## Decision 5: The prompt caps, and what the worst case actually costs

**Decision**: `MAX_PROMPTED_CANDIDATES = 32`, `MAX_MEMBERS_PER_CANDIDATE = 3`,
`MAX_MEMBER_SUMMARY_CHARS = 120`, README bullets capped at 1,500 chars, response
`max_tokens` 1,200.

**Worst case, computed from the constants** (probe 5, and this arithmetic is
what `test_feature_planner.py` asserts rather than trusts):

| Item | Size |
| --- | --- |
| Candidate header (handle + seed title + count) | ≤ 60 chars |
| Member line, summary capped at 120 | ≤ 160 chars |
| One candidate, 3 members | 540 chars |
| **32 candidates** | **17,280 chars** |
| README bullets | 1,500 chars |
| System prompt + instructions | 1,000 chars |
| **Prompt total** | **19,780 chars ≈ 4,945 tok** |
| Response cap | 1,200 tok |
| **Per call** | **≈ 6,145 tok** — **23.2% headroom** under 8000 |

**Two measured facts that make the real call much smaller than the worst case**,
worth recording so nobody "optimises" a cap that is already slack:

- Only **13 of 135 modules** carry a docstring or generated summary at all. The
  other 122 contribute a name (mean 9.2 chars) and nothing else.
- Of the 13 that do, the mean is **1,037 chars** and 92% exceed the 120-char cap —
  so the cap is load-bearing for exactly the members that have anything to say,
  and inert for the rest.

The worst case is therefore reached only by a repository where every prompted
member has a long summary. That is the case the constant exists for.

**On the 4 chars/token divisor**: deliberately conservative. Real English runs
closer to 4.5, and a member line is mostly identifiers, which tokenise worse than
prose. Keeping 4 means the assertion fails early rather than in production.

---

## Decision 6: A2 (alias + redirect) must land before anything renders — measured

**Decision**: the anchor/alias work is a prerequisite of the first feature page,
not a follow-up.

**Probe 6** measures how fragile the anchor actually is. For each candidate, the
margin between the highest-internal-degree member and the runner-up:

```
groups measured                : 11
anchor degree margin: min 0  median 1  max 16
groups where margin <= 1       : 6 / 11
```

**Six of eleven groups are one import edge away from a different anchor**, and at
least one is an exact tie decided only by the `(name, moduleKey)` tie-break.
Since a feature's key *is* its anchor module key, that is six of eleven feature
URLs that an ordinary refactor can move. The risk the plan flagged as theoretical
is the common case here.

Two consequences the measurement forces:

1. The alias table and redirect stubs are not defensive extras; without them the
   first real refactor after this ships breaks most saved links.
2. `impact.py`'s `removedPageIds` **must** consult the alias table before
   unlinking a file ([generator.py:773-774](../../src/doc_generator/generator.py#L773-L774)).
   With margins this tight, an anchor move plus an incremental run is not an edge
   case, and the removal pass would delete the very file the redirect points at.

---

## Decision 7: The alias table needs no migration step

**Decision**: add `doc_page_aliases` to `manifest_store.SCHEMA_STATEMENTS`.

**Verified** by reading `_connect` ([manifest_store.py:59-71](../../src/doc_generator/manifest_store.py#L59-L71)):
every connection replays every statement in `SCHEMA_STATEMENTS`, each written
`CREATE TABLE IF NOT EXISTS`. A new table therefore appears on the next
connection of an existing database with no migration code and no version column —
the same route `doc_render_state` took in commit 2c03afe.

---

## Decision 8: `chat/retrieval.read_readme_content` is not reusable here

**Verified**, not assumed: `_README_CANDIDATES` is
`("README", "README.rst", "README.txt", "Readme.rst", "readme.txt")`
([retrieval.py:25](../../src/chat/retrieval.py#L25)) — **`.md` is deliberately
absent**, because a `README.md` is indexed as an ordinary module and retrieval
returns the relevant parts of it, so returning it whole would put the same text
in the chat prompt twice.

`features/evidence.py` wants the opposite: the README's stated capabilities,
whatever its extension, and `.md` is the overwhelmingly common case. So it reads
`README.{md,rst,txt}` itself rather than calling the chat helper. Reading the
analysed repository is permitted by constitution 2.7, which forbids writes.

---

## Decision 9: Prose modules reach the fallback path, and `src/` alone does not exercise it

**Verified** by reading `identify_entry_points`
([entry_point_diagram.py:80-86](../../src/doc_generator/entry_point_diagram.py#L80-L86)):
it skips prose files outright, so a document module is reached by no entry point
and no candidate can be seeded from it.

**Probe 1 measured 0 prose modules under `src/`** — which means the repository's
own source tree does not exercise this path at all. A real indexing run includes
`README.md` and every file under `specs/`, all of which are prose. The fallback
in `features/fallback.py` is therefore not a rare branch on a real run; it is the
only thing that groups the documentation.

**Consequence for testing**: the no-entry-point fallback needs a fixture that
actually contains prose, not a subset of `src/`. `tests/unit/test_feature_fallback.py`
must construct one rather than relying on the sample repo.

---

## Decision 10: Everything except the planner is testable with no model

**Decision**: `evidence.py`, `candidates.py`, `fallback.py` and `validate.py`
take no engine argument at all — not an optional one defaulting to `None`.

**Rationale**: this session has already shipped a defect where a silently
rejected call and an unreachable service were indistinguishable, and the tests
passed either way. A module that *cannot* accept an engine cannot have a hidden
model dependency, so the property is enforced by the signature rather than
asserted by a test. `planner.py` is the single module that takes one, and
`validate.py` — the module that repairs its output — deliberately does not, so
every repair rule is exercised on hand-written input.

`planner.py` follows `section_narrator.py:151` exactly: one `PromptEnvelope`
through `llmEngine.run(lambda engine: engine.generate(prompt))`, catching
`RuntimeError` only, for the documented reason that every provider failure is a
`RuntimeError` while an `AttributeError` is a wiring bug that must stay loud.

---

## Decision 11: The import adjacency was substantially fictional — found in A1, now fixed

**Status: RESOLVED via Option B.** A pre-existing defect in `DependencyGraph`'s
import resolution that feature 033 surfaced. Fixed in `dependency_graph/graph.py`;
the A1 gate passes. The resolution is at the end of this decision.

**Probe**: `<scratchpad>/probe_candidates.py` (the A1 gate), plus the diagnostics
in this section. All figures are from this repository's own `src/` tree,
139 modules.

### What was found

The A1 gate failed: 109 of 139 modules landed in a single candidate named
`models`. The cause is not the attach rule. It is that
`_build_import_adjacency` — which `sections.py` has used since feature 030 — is
reading edges that do not exist.

`DependencyGraph` creates **one import node per imported name**, and an
unresolved import keeps the `sourceFile` of whichever repository file declared it
first. Two consequences, both measured:

1. **Stdlib imports become edges to an arbitrary module.** The node for
   `__future__` carries `sourceFile=src/chat/budget.py` purely because that file
   sorted first. Every module writing `from __future__ import annotations`
   therefore gained an import edge to `budget`. Measured: `budget` showed degree
   **131 of 139**, against a true internal degree of 4
   (`graph.dependencies(budget, "import")` returns 3, `dependents` returns 1).
   Of 869 `import` edges, **192 targeted `budget` and 158 `models`**.
2. **Same-named modules across packages collapse into one.** This repository has
   **11 files named `models.py`**. Every `from .models import …` anywhere in the
   tree resolves to `src/chat/models.py`. Measured after fixing (1):
   `src/chat/models.py` has degree **59**; the other ten `models.py` files have
   degree **0** — no incoming edges at all, because an impostor absorbed them.

Name ambiguity is not marginal here: **8 duplicated module names cover 45 of the
139 modules** (`__init__` ×18, `models` ×11, `errors` ×6, plus `sqlite_store`,
`server`, `engine`, `protocol`, `transport`).

### Partial fix applied

`fallback.build_import_adjacency` now requires an import node's `name` to equal
the target module's name before accepting the edge. This rejects every stdlib
edge. Effect on the graph:

| | before | after |
| --- | --- | --- |
| mean module degree | 9.01 | **3.48** |
| max module degree | 131 (`budget`) | 59 (`models`) |
| largest candidate | 109 / 139 (78%) | 97 / 139 (70%) |

The gate still fails, because the guard cannot separate eleven modules that share
a name.

### Why this was invisible until now

`sections.py` groups by **directory first** and uses adjacency only to absorb
small directories and split large ones. Both operations are robust to spurious
edges, so the corruption never surfaced — today's 15 sections look entirely
sensible. The candidate stage makes adjacency the **primary** grouping signal,
which is what exposed it.

That is worth stating plainly: this defect has been in the wiki's navigation
since feature 030, and the reason no test caught it is that no test asked the
adjacency a question whose answer it could get visibly wrong.


### Resolution — Option B, taken 2026-09-02

The user chose to fix import resolution properly rather than work around it.
Three changes in `src/dependency_graph/graph.py`, all in `_ingest_imports`'s
resolution path:

1. **Relative imports resolve against the importing file's own package.**
   `_resolve_relative_import` counts the leading dots, walks up from
   `Path(source_file).parent`, and matches only `<dir>/<name>.py` or
   `<dir>/<name>/__init__.py`. A relative import states its own location; the
   old code discarded that and matched on the last path segment.
2. **Dotted absolute imports must match the whole dotted tail.**
   `_resolve_dotted_import` requires `doc_generator/models`, not `models`, and
   returns nothing when several files match.
3. **A bare name resolves only when exactly one file in the repository carries
   it.** Ambiguity now yields an external node instead of "whichever node the
   iteration reached first". This is the rule that ends the arbitrary picking.

Plus the separate `sourceFile` defect: an unresolved import node is created
once and reused by every later importer, so `sourceFile=inventory.sourceFile`
permanently attributed `__future__` to `src/chat/budget.py`. It is now `""` —
an external import does not live in the repository.

**Measured effect on the import adjacency:**

| | before | partial guard | after Option B |
| --- | --- | --- | --- |
| mean module degree | 9.01 | 3.48 | **4.53** |
| max module degree | **131** (`budget`) | 59 (`models`) | **19** (`generator`) |
| `src/chat/models.py` degree | 102 | 59 | **7** |
| the other ten `models.py` | **0 each** | 0 each | **4-16 each** |
| import edges classed external | 0 | — | **568 of 892** |

Every one of the eleven `models.py` files now carries its own distinct degree.
`generator` at 19 is a plausible most-imported module; `budget` at degree 4
matches what the source actually says.

**Measured effect on the A1 gate** — it now passes:

```
candidates                 : 21
modules claimed            : 139 / 139   (0 duplicated, 0 missing)
sizes                      : [21,13,13,9,8,8,8,7,7,7,6,6,5,5,4,2,2,2,2,2,2]
largest candidate          : 21 modules = 15% of the repo   (was 78%)
singletons                 : 0 / 21
identical across two builds: True
GATE                       : PASS
```

**Regression cost: zero.** The full suite passes with no failures — including
the `test_cli.py` Groq flake, which happened to pass on this run. Five new tests
in `tests/unit/test_dependency_graph.py` pin the fix, and all three changes were
mutation-checked: reverting each one turns exactly the intended test red
(unresolved-path → 1 failure, ambiguous-bare → 1, relative-import → 2).

**One consequence worth stating.** This defect has shaped the wiki's navigation
since feature 030, and the reason no test caught it is that no test asked the
adjacency a question whose answer it could get visibly wrong — `sections.py`
groups by directory first and only uses adjacency to absorb and split, both of
which are robust to spurious edges. Regenerating any existing wiki after this
fix will produce different (better) section groupings even before 033 lands.

### The decision this needed

Three options, none of them free:

| Option | Effect | Cost |
| --- | --- | --- |
| **A. Drop edges to ambiguous names.** Accept an import edge only when the target name is unique among repository modules. | Honest: no wrong edges. | Loses all coupling for 45 of 139 modules, which then fall to the fallback path. |
| **B. Resolve imports properly** — use the importing file's package path to disambiguate `.models`. | Correct adjacency for the first time. | Changes `dependency_graph`, outside 033's scope, and affects every consumer of import edges. |
| **C. Fall back to directory-primary grouping** for this stage, as `sections.py` does. | No new risk. | Abandons the premise of 033 — the grouping would again answer "where does this code live". |

**Recommendation was B**, and B is what was taken — see the Resolution above. A
would have silently degraded a third of the repository; C would have given up
the feature.

---

## Resolved unknowns

| Question | Answer | How |
| --- | --- | --- |
| How many entry points does this repo have? | 167, across 52 modules | probe 1 |
| Is the sequence walk too slow to reuse? | **No** — 0.008 s for all of it | probe 2 (corrects the plan) |
| Where does reachability saturate? | **Depth 2**, not 4 | probe 3 (corrects the plan) |
| Does the plan's bound produce usable candidates? | **No** — one 64-module blob + 41 singletons | probe 4 |
| How long is a `moduleKey`? | mean 116.6 chars ≈ 29 tokens | probe 5 |
| Does the capped prompt fit 8000 TPM? | Yes, 6,145 tok, 23.2% headroom | probe 5 |
| How many modules carry a summary at all? | 13 of 135 | probe 5 |
| Is anchor drift real or theoretical? | **Real** — 6 of 11 groups have margin ≤ 1 | probe 6 |
| Does a new manifest table need a migration? | No — `_connect` replays the schema | source read, Decision 7 |
| Can the chat README helper be reused? | No — it skips `.md` on purpose | source read, Decision 8 |
| Do prose modules exercise the fallback in `src/`? | No — 0 prose modules there | probe 1, Decision 9 |

No `NEEDS CLARIFICATION` remains. **Decision 11**, the fictional import
adjacency, was opened and closed during A1: It was opened by measurement during A1, exactly as
Decision 3 anticipated, but the answer turned out to lie below this feature
rather than inside it.

Decision 3's own open question is now closed, with a negative answer: an
edge-weight term is *not* enough. Coupling-based seeded label propagation
replaced the `1/(1+d)` score (`candidates._assign_by_coupling`) and the dominant
candidate persisted, because the edges being weighted are themselves wrong.

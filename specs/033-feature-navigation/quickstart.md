# Quickstart: Verifying Feature Navigation

**Feature**: 033-feature-navigation | **Date**: 2026-09-02

Three levels, **in ascending order of authority**. Level 1 is fast and proves the
deterministic stages. Level 2 is what actually proves the feature, because it
runs the real generator over a real repository and reads the files it produced.
Level 3 is the small residue only a human can judge.

Where they disagree, the later one wins. This project has shipped four defects
that a fully green level 1 passed over.

---

## Level 1 — Unit and integration tests

```bash
.venv/Scripts/python.exe -m pytest \
    --basetemp="$SCRATCHPAD" -p no:cacheprovider
```

`--basetemp` into the scratchpad and `-p no:cacheprovider` are not optional on
this machine: a bare `pytest` reports ~17 spurious `PermissionError`s that have
nothing to do with the code under test.

**Expected**: 672 passing before this feature, plus the new tests. **One known
flake**, not a regression:
`tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`
makes a live Groq availability call, so it passes when Groq is unreachable and
fails when it answers. Identify it by failure text naming `groq:...: available`.
**Any other failure is real.**

### What level 1 can and cannot prove

| Proves | Does not prove |
| --- | --- |
| The candidate partition holds (every module in exactly one candidate) | That a reader can find a module |
| Every repair-table row behaves | That the model's real answers are repairable |
| The prompt budget fits, computed from the constants | That the provider accepts the call |
| The no-model path produces identical structure | That a saved URL still opens |
| An alias is recorded and a stub written | That the stub actually redirects a browser |

### Mutation-test the assertions that carry weight

Four of these are worth deliberately breaking to confirm the test goes red. This
caught two vacuous tests in feature 034.

1. Change `MAX_ATTACH_DISTANCE` from 2 to 4 → the candidate-distribution test
   must fail. If it passes, it is not measuring the distribution.
2. Raise `MAX_PROMPTED_CANDIDATES` to 64 → the budget assertion must fail. If it
   passes, the test hard-codes 6,145 instead of computing from the constants.
3. Delete the `list_aliases` check from the removal loop → the alias test must
   fail. If it passes, the test never wrote a page at the aliased path.
4. Make `repair` drop an unplaced candidate instead of putting it in
   `Support & Utilities` → the post-condition assertion must fail.

---

## Level 2 — Generate a real wiki and read what it produced

**This is the level that decides whether the feature works.** The probe harness
from Phase 0 is reused: `<scratchpad>/probe_bundle.py` builds a real
`RepositoryBundle` + `DependencyGraph` for this repository's own `src/` tree in
about 20 seconds, with no CLI, no config and no provider.

### 2.1 Candidate distribution — the A1 gate

```bash
cd "$SCRATCHPAD" && \
  /c/Users/ASUS/IdeaProjects/codepedia/.venv/Scripts/python.exe probe_evidence.py
```

Read probe 4's output. **Pass condition**: no candidate holds more than about a
third of the repository's modules, and fewer than half the candidates are
singletons. At `MAX_ATTACH_DISTANCE = 4` this produced `[64, 6, 4, 4, 3, …]` with
41 singletons out of 52 — the shape that must not reappear.

If a dominant candidate persists at depth 2, the **scoring rule** needs the
edge-weight term, not the bound (research Decision 3). That is the open question
A1 closes by measurement.

### 2.2 Generate the wiki with no model at all

```bash
.venv/Scripts/python.exe - <<'PY'
import sys; sys.path.insert(0, "src")
from pathlib import Path
from doc_generator import DocGenerator, open_doc_manifest_store
# featurePlanner deliberately omitted -> no model, anywhere
PY
```

Drive `generateRepositoryDocumentation(root, incremental=False)` with
`featurePlanner=None` into a scratch output directory, then check, **by reading
the generated files rather than the in-memory objects**:

1. `features/*.html` exists and `sections/` does not.
2. Every module page under `modules/` is linked from exactly one feature page.
   Count the member links across all feature pages; it must equal the number of
   module pages. **This is SC-003 and it is the assertion most worth getting
   right** — a mismatch means a module lost its last door.
3. `assets/search-index.json` contains one entry of kind `module` or `document`
   per module page (FR-026).
4. No page's sidebar contains a module link (FR-024).

### 2.3 The same repository *with* a model

Point `CODEPEDIA_*` at a live Groq key and regenerate. Then diff against 2.2:

- **The set of `features/*.html` filenames must be identical.** Different
  filenames mean the model influenced structure, which it must not (FR-002,
  SC-006).
- The module-to-feature assignment must be identical.
- Only titles and descriptions differ.

Then regenerate a **second** time without changing the repository and confirm the
provider log shows **zero** planning calls (FR-016, SC-004).

> **Watch for the 034 failure shape here.** An unreachable model and a silently
> rejected call look identical from the outside: both produce a wiki with plain
> titles. Do not conclude the model was consulted because the wiki built. Confirm
> it from the provider log or by asserting `isPlanned` is `True` on at least one
> feature.

### 2.4 Anchor move — the A2 gate

1. Generate; record a feature's `features/<slug>.html` path.
2. Add an import edge to make a different member the most internally connected
   one. Probe 6 says six of eleven groups need only **one edge** for this, and it
   names them.
3. Regenerate **incrementally** — this is the case that matters, because the
   removal pass runs on an incremental run.
4. Open the recorded path. It must still exist and must redirect.
5. Confirm the file was not deleted: `ls` the old path after the incremental run.
   If it is gone, the `list_aliases` clause in the removal loop is missing or
   ordered wrong.

### 2.5 Migration from an existing wiki — the A4 gate

1. `git stash` this feature's changes, generate a wiki with the current `main`
   code into a scratch directory, record a `sections/*.html` path.
2. Unstash, regenerate over the **same** output directory and the **same**
   manifest database.
3. The old `sections/*.html` must still resolve, and must land on the feature
   holding a plurality of that section's modules (FR-022).
4. The run must have been non-incremental — one full rebuild (FR-023).
5. `doc_section_narrations` must be empty afterwards.

This is the only step that needs a wiki built by the *previous* code, so it needs
the stash. Do it last, and do not commit anything in between.

---

## Level 3 — What only a human can judge

Four things, none of which a test can answer.

1. **Do the feature names describe what the software does?** (SC-001) Open the
   generated wiki's home page and read the sidebar. A newcomer should be able to
   name three things this repository does. "Doc Generator", "Chat", "CLI" is the
   failure mode — that is the directory tree with a model's blessing, which is the
   defect this feature exists to remove.
2. **Is the general-to-specific ordering readable?** (FR-027) Overview entries
   first, tooling last. If the ordering looks arbitrary, check whether every
   feature came back with the default `"subsystem"` kind — that would mean the
   plan's `kind` field is being defaulted for every feature, which the repair
   table permits and no test would flag.
3. **Is a module still findable?** Pick three modules you would look for and find
   each from the home page. This is US2 checked the way a reader checks it, not
   by counting links.
4. **Does the redirect stub explain itself?** Open one. A reader who landed there
   from a bookmark should be able to tell they were moved and where to.

---

## Order of work, and what each phase gates

| Phase | Gate before moving on |
| --- | --- |
| **A1** evidence + candidates | § 2.1 candidate distribution is not degenerate |
| **A2** anchor + alias | § 2.4 passes — **before any feature page is rendered** |
| **A3** planner + validate | § 2.3 with and without a model produce identical structure |
| **A4** rendering rename | § 2.2, § 2.5, and `grep -rn "[Ss]ection" src/` is clean |

**A2 before A4 is not negotiable.** Rendering a feature page publishes a URL, and
publishing a URL before the alias table exists ships links that the first
refactor breaks. With six of eleven anchors one edge from moving, that refactor
is not hypothetical.

---

## Environment notes

- Python venv must be **3.11–3.13**. 3.14 hangs in Pydantic schema generation.
- **No frontend build.** This feature touches no TypeScript and no CSS. If a step
  asks for `npm run build`, the approach has drifted — see contract § 6.
- Do not commit. Leave everything as uncommitted working-tree changes.
- `.specify/feature.json` is a machine-local pointer and is not part of any
  commit.

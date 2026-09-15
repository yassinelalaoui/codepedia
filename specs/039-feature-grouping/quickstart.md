# Quickstart: Verifying Spec 039

How to show the feature works end to end, on the two reference repositories.
The rules being verified are in [contracts/feature-grouping.md](contracts/feature-grouping.md),
the types in [data-model.md](data-model.md), and the measured baselines in
[research.md](research.md).

## Prerequisites

- The project `.venv` (Python 3.11–3.13). Run helpers with
  `$env:PYTHONPATH='src'; .venv\Scripts\python.exe <script> <repo-root>`.
- Both reference repositories indexed:
  - `C:\Users\ASUS\IdeaProjects\codepedia-sample-repo`, whose state is
    `%USERPROFILE%\.codepedia\repos\a47b5ea9c5a22795`;
  - `C:\Users\ASUS\IdeaProjects\nextgen-wealth-ledger`, whose state is
    `…\3d82e509c5da9263`.
- The read-only probes from the planning session, in the session scratchpad:
  - `planner_probe.py`: seeds, candidates, planner prompt, cached plan,
    features;
  - `majors_probe.py`: per-feature kind and member makeup;
  - `grouping_proto.py`: the prototype, now to be compared against the real
    code.

  Copy them somewhere durable if the scratchpad may be cleaned.

## §1 Tests, no model

```powershell
.venv\Scripts\python.exe -m pytest --basetemp=<scratchpad>\pytest-039 -p no:cacheprovider -q `
  tests/unit/test_feature_imports.py tests/unit/test_feature_candidates.py `
  tests/unit/test_feature_validate.py tests/unit/test_feature_planner.py `
  tests/unit/test_feature_fallback.py tests/unit/test_feature_evidence.py `
  tests/integration/test_feature_grouping_languages.py tests/integration/test_feature_navigation.py
```

**Expected**: all pass. Then run the full suite in the background (about 10
minutes). The only accepted failure is the known flaky
`test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`,
which fails whenever Groq answers.

The spec 038 suites must pass unchanged, because they read the moved helpers
through `overview/evidence.py`:
`tests/unit/test_overview_*.py` and `tests/integration/test_overview_*.py`.

## §2 The grouping with no model (SC-001 to SC-005)

Run `planner_probe.py` on both repositories. It builds evidence, adjacency,
candidates and repaired features from the indexed state with no provider.

| Check | Sample, expected | Nextgen, expected | Baseline (033) |
| --- | --- | --- | --- |
| Largest feature share (SC-001) | ≤ 30% (prototype: 18%) | ≤ 30% (prototype: 16%) | 23% / **85%** |
| In-repository Java and TS imports resolved, per import (SC-002) | n/a (3 of 3 JS) | ≥ 90% per language (prototype: TS 75 of 75 relative imports; Java 59 direct and 7 wildcard resolved, denominator per SC-002's definition) | 0 of 64 / 2 of 43 modules coupled |
| Coupled Java and TS modules (context) | n/a | prototype: Java 63 of 64, TS 42 of 43 | 0 of 64 / 2 of 43 |
| Test-seeded groups (SC-003) | 0 | 0 | 5 test seeds |
| Sum of feature entry-point counts = non-test entry points (SC-004) | equal | equal | nextgen: every feature 0 |
| Anchors (SC-005) | `cli`, route modules, `lending_service`, `catalog_service`, `memory_store`, `sqlite_store` | services, components and controllers, never `animations.ts` | `ids`, `errors`, `member`, `animations.ts` |
| CLI stands alone (FR-006a) | a feature anchored at `cli.py` | `DigitalBankingApplication` alone | CLI folded into "Scripts" |

Compare the real output with `grouping_proto.py`. Any difference is either a
prototype shortcut or an implementation bug, and it is explained in the
implementation report. The known shortcuts are listed in research.md,
Decision 12's addendum.

From T006b on, `planner_probe.py` calls `plan_cache_key(evidence,
candidates)`. The cached 033 plans no longer match, so the probe's repaired
features are the no-model features. Confirm it reports no cached plan.

## §3 Determinism and the no-model path (SC-008)

Run `planner_probe.py` twice on each repository. The outputs must be byte
identical.

With a planner stub that refuses, the modules and candidate grouping must be
identical to the no-planner run (033 SC-006). The integration test asserts
this; this step confirms it on real data.

## §4 Re-index with a model (verification round, owner approval required)

Each round costs about one planner call plus one Overview narrative call per
repository.

1. Hash-compare `%USERPROFILE%\.codepedia\config.json` with the backup.
2. Set the Groq-first `summaryChain`.
3. Before re-indexing, list every `features/*.html` in each wiki's
   `<state>\docs\` directory.
4. Re-index both repositories (the procedure in 038's HANDOFF §6).
5. Restore the config byte for byte, and hash-compare again.

**Expected**:

- The first run after upgrading misses the plan cache (the key hashes the
  grouping): one planner call per repository. A second run makes none.
- The terminal shows no `Traceback`.
- Every previously published feature address still opens (SC-008): each
  path listed in step 3 is a live page or a redirect stub to one, holding
  most of its modules. The check is scripted and covers every listed path.
- The largest feature's share *with* the model is recorded, not enforced
  (clarification Q5).

## §5 What a reader sees (SC-006, SC-007)

1. **SC-006.** Map the features against 038's answer keys (`sc001-key-*.md`).
   A feature corresponds to a key subsystem when most of its production
   modules belong to that subsystem.
   - Sample: at least 6 of 8, including the CLI.
   - Nextgen: at least 6 of 9, including the wallets, authentication and
     security, chatbot and frontend parts (spec SC-006).
2. **SC-007.** Repeat the stranger test with a fresh subagent per repository,
   told to use Read once, on `index.md`, and nothing else. Score it against
   the keys. Each reviewer names at least 3 key subsystems from the table or
   prose, and flags at most one subsystem as mislabelled.
3. **Screenshots** of each Overview at 700 px dark and full width light: the
   subsystems table lists the new features and the sidebar matches it.

## §6 Record

Add the results as a research Decision in this folder and tick the matching
tasks in `tasks.md`. Report to the owner. Do not commit.

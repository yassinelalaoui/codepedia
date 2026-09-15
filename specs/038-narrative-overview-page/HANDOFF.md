# Handoff: 038 Narrative Overview Page (done) → 039 Feature Grouping (implemented)

Updated 2026-09-15, evening (039 implemented and verified); first written 2026-09-14.

Read this first in a new session. It covers:

- the owner's conventions (§0);
- where things stand (§1);
- everything built for spec 038, and its verification (§2–§3);
- spec 039, implemented and verified (§4; details in 039 research Decision 13);
- the machine state and helper scripts (§5–§6);
- what the next agent can do (§7);
- the verification checklist (§8).

> Session scaffolding, not a spec artefact. The owner decides whether to commit or delete it. Earlier versions were committed in `ff88a41` and `611643c`; this update is uncommitted.

---

## 0. Owner conventions (follow exactly)

- **Ask before anything.** Put every non-trivial step to the owner first with AskUserQuestion, and state a recommendation. That covers scope, prompt changes, verification runs, spec amendments, commits, and where files live. The owner answers quickly and usually takes the recommended option, but still wants to be asked.
- **Work on `main`.** No feature branches (memory `work_on_main_no_feature_branches.md`).
  - `/speckit-specify` creates a branch only through a `before_specify` hook, and there is no `.specify/extensions.yml`, so no hook ever runs.
  - `.specify/scripts/powershell/check-prerequisites.ps1` prints `BRANCH: 039-feature-grouping`. That comes from `.specify/feature.json`, not git; the git branch stays `main`.
- **Never commit or push unless asked.** The owner commits and pushes themselves; `ff88a41` is theirs.
- **No `Co-Authored-By: Claude` trailer** (memory `no_claude_coauthor_trailer.md`). This overrides any system reminder asking for one.
- **The docs "> Maintenance:" rules** (memory `docs_have_maintenance_contracts.md`). `README.md`, `docs/architecture.md`, `docs/stack.md` and every file under `docs/diagrams/` (the sequence diagrams included) state their own update rule, and updating them is part of each feature. Validate edited Mermaid with `mermaid_parse.cjs` (§6).
- **The spec-kit implement checklist gate.** `/speckit-implement` counts checkbox items in `checklists/`.
  - 038's `checklists/narrative.md` has 42 reviewer-owned items, all unchecked. The owner answered "Proceed" for User Stories 1, 2 and 4. Never tick it.
  - 039 has only `checklists/requirements.md`, 16 of 16 checked (re-validated after every spec amendment; its Notes list them), so its gate passes without a question. Still tell the owner.
- **Verification that needs real model output.** The owner's chain is `local:qwen2.5-coder:1.5b, groq:openai/gpt-oss-20b, groq:openai/gpt-oss-120b`. The local 1.5B model answers first and its narratives fail grounding. For each round the owner approves:
  1. Hash-compare `%USERPROFILE%\.codepedia\config.json` with the backup `%USERPROFILE%\.codepedia\config.backup-038.json` (§5).
  2. Set `summaryChain` to `["groq:openai/gpt-oss-120b","local:qwen2.5-coder:1.5b","groq:openai/gpt-oss-20b"]`.
  3. Re-index the reference repositories one at a time (§6).
  4. Restore the backup byte for byte, and hash-compare again.

  Ask each time. A round costs one call per repository per cache miss: the Overview narrative, plus the feature planner once 039 changes its cache key.
- **The stranger test (SC-001 in 038, SC-007 in 039).**
  - Use a fresh `general-purpose` subagent per repository, told to use the Read tool exactly once, on that repository's `<state>\docs\index.md`, and nothing else.
  - Confirm `tool_uses: 1` in each notification.
  - Score against the answer keys (§5). The implementer never reviews.
- **Reference repositories.**
  - `C:\Users\ASUS\IdeaProjects\codepedia-sample-repo` (Python, 51 modules): state directory `%USERPROFILE%\.codepedia\repos\a47b5ea9c5a22795`.
  - `C:\Users\ASUS\IdeaProjects\nextgen-wealth-ledger` (Spring Boot Java and Angular TypeScript, 109 modules): state directory `%USERPROFILE%\.codepedia\repos\3d82e509c5da9263`.

  The owner chose nextgen instead of Codepedia itself, which was never indexed and would take hours of provider time.
- **Harness quirks seen this session.**
  - The Bash tool wraps commands in single quotes, so a heredoc whose text contains an apostrophe fails with "unexpected EOF while looking for matching `'`". Use the Write or Edit tool for such files.
  - PowerShell `Remove-Item` with a computed path was once blocked as a "system path"; overwriting instead works.
  - Foreground `sleep` is blocked; wait with a Bash `until` loop (§6).
- **Encoding.** Never re-save source through a cp1252 round trip; that is what caused 038's "â€”" mojibake. Use the Edit and Write tools, or `[IO.File]::ReadAllText(p,[Text.Encoding]::UTF8)` with `WriteAllText(p,t,(New-Object Text.UTF8Encoding($false)))`. `tests/unit/test_source_encoding.py` guards `src/` and `frontend/src/`.

---

## 1. Where things stand

| Item | State |
| --- | --- |
| **038** User Stories 1, 2 and 4, refinements R1–R5, the "not written" notice, polish T050–T052 | **Done, committed and pushed** (`ff88a41`, owner). All 038 tasks are `[X]` except **T053**. |
| 038 User Story 3 (getting started) | Deferred by clarification; there are no tasks. |
| **039** Feature Grouping | **Implemented and verified**: all 41 tasks `[X]` (T001–T038, plus T006a/T006b from analyze and T036a/T037a from verification). The MVP (through T020) was committed by the owner in `611643c`. User Stories 3 and 4, polish, the T036a alias fix and T037a are **uncommitted**. Results: 039 `research.md` Decision 13 and `measurements/`. |
| Next step | Owner review and commit. Then the follow-ups in §7 (none started). |
| Working tree | `main`, 1 commit ahead of `ff88a41` (`611643c`, owner). Uncommitted: 039 code, tests, docs and spec updates since `611643c`, plus this `HANDOFF.md` update. |
| Unmerged local branch `lot-11` | 3 commits from 2026-09-01, not on the remote (`8751377`, `067828d`, `ae0fc88`). **Owner answer (2026-09-15): parked, leave it.** |

---

## 2. Spec 038: what exists (design as built)

### 2.1 Commits on `main` (all pushed; none carries a Claude trailer)

| Commit | Content |
| --- | --- |
| `2539226` | User Story 1: tests, code, CSS, the spec folder. It introduced mojibake, repaired in `629e839`. |
| `f0e7f70` | Decisions 15 and 16: entry ranking, prompt labels, the owner label, paragraph 3 made safe. |
| `629e839` | The I2 fix; User Story 2 (table, subsystem paragraphs, grounding, template); the mojibake repair and its encoding guard. |
| `1b585b1` | Decision 18 prompt fix; research and tasks. |
| `ff88a41` | **This session:** R1–R5; the notice clause; User Story 4; the docs polish; Decision 19; contract and data-model updates; the handoff. 29 files. |

### 2.2 Package `src/doc_generator/overview/`

- `evidence.py` and `grounding.py` take no engine; `narrator.py` is the only module that does. `tests/unit/test_overview_package.py` enforces this.
- One LLM call per repository for the whole page, through the summary-chain `FailoverExecutor`.
- Cache: the table `doc_overview_narratives` in `<state>\doc-manifest.sqlite`, one row per repository.
  - The key is `sha1(format version + system prompt + prompt text + max_tokens)`.
  - A parseable reply is saved; an unparseable one is not.
  - The row stores the raw reply, the handle map and `repository_fingerprint`.
  - `load_latest_overview_narrative` returns `(reply, handle_map, fingerprint)`.

**Evidence** (`evidence.py`):
- A `FeatureBrief` per prompted feature (≤ 12, navigation order).
- `EntryFlow.kind` is in `ENTRY_KINDS = ("cli-command","api-route","main")`, or is `"function"` (uncalled). An uncalled function named `main` counts as kind `main`. Test files are dropped (`is_test_path`). At most 6 flows.
- `repositoryFingerprint` is the SHA-1 of the README lead and every file's `(path, contentHash)`. It is never part of the prompt.
- **R3 (this session): `majorFeatureKeys`** = the first ≤ 8 prompted features that are not `tooling` and not `_is_docs_or_tests_only`, meaning every member is a prose or test file. A member with no path counts as code. On the sample, Documentation is out and Storage (Memory Store) is in.
- **039 will move** `is_test_path`, `ENTRY_KINDS` and `read_readme_lead` into `features/evidence.py`, and re-export them here (039 T004).

**Narrator** (`narrator.py`):
- Constants: `NARRATIVE_FORMAT_VERSION = "2"`, `HEADER_CHARS = 300`, `FEATURE_BLOCK_CHARS = 710`, `ENTRY_FLOW_CHARS = 240`, `MAX_NARRATIVE_RESPONSE_TOKENS = 1400`.
- **`SYSTEM_PROMPT_CHARS = 2050`** (was 1900). The prompt is 2,040 characters, and the worst case is **4,627 tokens** (was 4,590) of the 8,000 budget.
- **R4 (this session):** paragraph 1 "names each kind of entry with its files as where work enters (api-route as routes, cli-command as commands, main as the main function)". The example now reads "Work enters through routes in `src/app/api.py` and commands in `src/app/cli.py`. The `run` command in `src/app/cli.py` is part of [[f0]]; its calls reach [[f1]] and [[f3]]."
- Other paragraph rules are unchanged (Decisions 15–18): paragraph 2 follows one call line, and paragraph 3 names every storing, sending or returning subsystem and cites a start file. `"subsystems"` holds one paragraph per subsystem marked `paragraph`, of at most 3 sentences, naming its start file.
- Statuses: `cached`, `generated`, `stale`, `previous-prompt`, `unavailable`, `failed`, `unparseable`, `skipped`.

**Grounding** (`grounding.py`):
- Rules G1–G11 are unchanged (research Decision 6).
- **R5 (this session):** a paragraph for a live subsystem not in `majorFeatureKeys` is skipped and counted in `unaskedCount`, never as offered or dropped. G3 (invented handle) and G9 (a second paragraph) still count.
- **This session:** `askedCount = len(majorFeatureKeys)`. `unwrittenCount` counts majors the reply wrote nothing for; a written but rejected paragraph is "dropped", not "unwritten".

### 2.3 Generator, template, CSS (038)

- `generator.py`:
  - **R1:** each subsystem paragraph ends ``… → [Title](features/…)``.
  - **The notice (this session):** a `generated` or `cached` pass appends `; <u> of <m> subsystem paragraphs not written`, or prints it alone (contract §7). There is still at most one line per pass.
  - The `stale` and `previous-prompt` lines are unchanged.
- **User Story 4 module list (this session):**
  - labels come from `prose.disambiguated_labels` (sorted by label), for example `api/__init__` and `core/__init__`;
  - descriptions come from `plain_text.marked_excerpt`, which always ends in ` …` when shortened, a sentence cut included (the owner's FR-032 decision);
  - the row is `- [label](modules/…)[ — description] [dependencies](diagrams/…)`, with no parentheses.
  - Known cosmetic leftover: the `docs/getting-started` row reads "…seed the sample data: Then start the API: Open …", because code blocks are removed between colons.
- `home.md.jinja`: the counts sentence carries `{: .architecture-counts }`.
- `frontend/src/styles.css` sets `.content-col .architecture-counts + table td:nth-child(2) { font-family: var(--wiki-font-ui) }`. It is built into `src/doc_generator/assets/wiki-ui.css` by `cd frontend; npm run build`.
- Test support: `tests/integration/_doc_generator_support.index_repo` parses `.md` as `markdown`, and everything else as Python. 039 T006 extends this to Java and TS.

### 2.4 038 spec documents

- `research.md`:
  - Decisions 14–18 (earlier);
  - **Decision 19** (this session): R1–R5, the "not written" notice, the variance finding, verification, and the stranger test;
  - a Decision 12 addendum on FR-032 marking and the same-extension case.
- `contracts/overview-narrative.md`: §2 (the paragraph-1 rule), §6 (the arrow, `.architecture-counts`, the majors rule, the module-list row) and §7 (the "not written" row, and unasked paragraphs excluded from `<n>`).
- `data-model.md`: the `majorFeatureKeys` rule; `offeredCount`, `unaskedCount`, `askedCount`, `unwrittenCount`; `SYSTEM_PROMPT_CHARS` 2050.
- `tasks.md`: T043a–T043h (refinements), T044–T052 `[X]`; T053 is open. Two "Â§" mojibake characters were fixed.

---

## 3. Spec 038: verification results (research Decision 19)

| | Sample | Nextgen |
| --- | --- | --- |
| Terminal `overview:` line | none. Run 1 wrote only 3 of 12 paragraphs (6 of 8 majors unwritten), which led to the notice clause; the re-ask wrote all 12. | none |
| Lead | 3 of 3. Paragraph 1: "Work enters through API routes in `routes_loans.py` and `routes_books.py`, and through CLI commands in `cli.py`". | 3 of 3. Paragraph 1 names `DigitalBankingApplication.main`. |
| Subsystem paragraphs | 8 of 8 majors; 4 unasked ignored | 5 of 5 majors; 2 unasked (tooling) ignored |
| Words / link problems | ~327 / 0 | ~230 / 0 |
| Tense (SC-013) | all declarative present | same |
| Full suite | only the known flaky Groq CLI test failed (twice) | |

**Stranger test** (fresh subagents, `tool_uses: 1` each):
- Both pass by the keys. Sample: 8 of 8 subsystems, with the CLI found from paragraph 1. Nextgen passes, but from module names.
- Both called the table and paragraphs misleading because of 033's grouping, titles and anchors. Examples: "Tests" starts at `fine_calculator.py`, "Catalog Service" at `core/errors.py`, and "Data Transfer Objects" is `animations.ts`.
- **That is why spec 039 exists.**

**Remaining 038 work** (none started):
- **T053:** re-run the whole of 038's `quickstart.md` §1–§6 on the final tree and attach the implementation report: files touched, where narration lives, tokens per run, and the sample `index.md`.
- **Analyze findings** not applied:
  - MEDIUM: U1 (FR-015's "settled" wording), U2 (write-if-changed compares Markdown only), A3 ("legibility" unquantified), A4 (no scripted SC-002 audit), I4 (no notice when a fallback provider wrote the narrative, which FR-018 asks for), C2 (no FR-002 assertion).
  - LOW: A5, C3, U5, D1, T1.
- **Open owner decisions:**
  - the chain order (the local 1.5B model first means no lead on this machine);
  - whether to re-ask each pass while a weak model's cached reply grounds to nothing;
  - the already-shipped `cross_references` document-path fix.
- **Outside 038:**
  - The Java parser records no annotations. That, and interface-call resolution, are also out of scope for 039.
  - The wiki shell has no narrow layout: at 400 px the sidebar clips content on every page.

---

## 4. Spec 039: Feature Grouping That Follows the Code (implemented)

### 4.0 As implemented (2026-09-15)

The full record is in 039 `research.md` Decision 13, `measurements/t036-round.md` and `measurements/t037-results.md`.

**Code** (`src/doc_generator/features/`):

| File | What changed |
| --- | --- |
| `imports.py` (new) | Java and JS/TS import names resolved to modules; a wildcard import split as `Fraction(1, n)` |
| `evidence.py` | Roles (tests, entry modules, seeds, labels, the README lead); the helpers moved from `overview.evidence` |
| `fallback.py` | Adjacency merge; the ancestor rule no longer climbs into the root |
| `candidates.py` | `_Folding` (Decision 6, per group; nothing folds with no survivor); test placement; `anchor_for` (entry module, then seed, ties by reach then name; a test never anchors); titles from the anchor; members by relevance |
| `validate.py` | Keys from `anchor_for`; counts from members; one terminal feature |
| `planner.py` | Key over the grouping; `GROUPING_VERSION = "3"`; labels and README lead; tests described last |

In `generator.py`: `_restore_redirects` (T036a), and "Start with" is the anchor (T037a).

**Results:**

- **Met:** SC-001 to SC-005 and SC-008 (every published address resolves).
- **SC-006:** nextgen 7 of 9, but the sample 3 of 8 with the model. The owner chose to record it as not met, explained.
- **SC-007:** half met. Reviewers name the subsystems from the table and prose, but still flag 5 (sample) and 8 (nextgen). The causes are 038's relation sentences, the model's names, and cross-stack anchors, because Spring controllers are not routes.

**Owner decisions taken during the implementation:** listed in Decision 13. The two rules approved at T015, the fold order, title-by-anchor, test-never-anchors, tests-last, the reach tie-break, T036a and T037a.

**The planning history below** is kept as written before implementation.

**Why:** 033's grouping (`src/doc_generator/features/`) misleads Overview readers. Measured causes, from the spec Background and research:

1. **Java and TS import nodes in `DependencyGraph` have an empty `sourceFile`**, so `features/fallback.build_import_adjacency` maps none of them to a module. Coupling exists for Python only: Java 0 of 64 modules, TS 2 of 43.
2. **Uncoupled groups fold into the largest survivor**, which is how nextgen got a 93-of-109-module "Data Transfer Objects". Folds also drop entry-point counts, so every nextgen feature shows 0.
3. **Tests seed groups:** 5 of the sample's 26 seeds, which produced "Tests (Test Fines)". The CLI was folded into "Scripts".
4. **The anchor is the best-connected member, not the seed:** `utils/ids.py`, `core/errors.py`, `domain/member.py`, `shared/animations.ts`.
5. **The planner sees the first 3 members alphabetically** (for example `README`, `__init__`, `__init__`) and the README's headings.

**Clarifications** (spec § Clarifications, 2026-09-15):
- Q1: tests join the feature holding most of the code they exercise; fixtures-only tests go by directory; tests are placed after production code.
- Q2: languages are Java and JS/TS, with Python unchanged. Go and Rust fall back to directory grouping.
- Q3: entry modules (commands, routes, `main`) are never absorbed by groups without one (FR-006a).
- Q4: coupling comes from imports only, never calls.
- Q5: the 30% ceiling applies to the grouping without a model; model merges are reported, not enforced.
- Q6: the anchor is the entry module, then the seed with the most entry points, then 033's most-connected rule.

Three owner-approved amendments were applied from research Decision 12: SC-006 wording (vertical slices, not a "controllers" feature), FR-006 (direct-directory rule and leftovers combining), and the Background's first bullet.

**Plan** (`plan.md`, `research.md` Decisions 1–12, `data-model.md`, `contracts/feature-grouping.md`, `quickstart.md`):
- A new `features/imports.py`, `resolve_repository_imports(bundle, graph, *, repository_root)`:
  - reads graph import node names;
  - Java: the longest suffix match, static and nested imports, a wildcard weighted `Fraction(1, n)`;
  - JS/TS: relative paths with extensions and `/index`;
  - selects modules by file suffix.
- `build_import_adjacency` merges it with 033's Python adjacency, which stays byte-for-byte. Weights become `int | Fraction`.
- `features/evidence.py` gains `readmeLead`, `testModuleKeys`, `entryModuleKeys`, `seedModuleKeys` and `moduleLabels`, and owns the moved helpers.
- `candidates.py`:
  - seeds are non-test modules with entry points (Decision 1, measured);
  - propagation and folding see production modules only;
  - folding follows Decision 6 steps 1–6: coupling, entry protection, the direct-directory walk, leftovers combining per directory, one terminal candidate, and the cap;
  - tests are placed afterwards;
  - counts are taken from members;
  - `memberKeys` are ordered by relevance.
- `validate.py`: the anchor order via `anchor_for`, and counts from members.
- `planner.py`: members by `evidence.moduleLabels`, cut to 40 characters; the README lead; `GROUPING_VERSION = "2"`; `plan_cache_key(evidence, candidates)` hashes the grouping. That fixes a latent 033 bug, where an import edit could put old titles on the wrong groups.
- The alias and redirect mechanism (`_redirect_superseded_pages`, plurality) and `requiresNavigationRegeneration` already handle regrouping. No new mechanism is needed.

**Prototype measurements** (`grouping_proto.py`, read-only, output `proto-run1.txt`):

| | Sample, all seeds | Sample, entry modules only | Nextgen, all seeds | Nextgen, entry modules only |
| --- | --- | --- | --- | --- |
| Groups | 14 | 7 | 21 | 22 |
| Largest | **18%** | 67% | **16%** | 21% |

- Java: 59 direct and 7 wildcard imports resolved; TS: 75 of 75 relative imports. Coupled modules: Java 63 of 64, TS 42 of 43.
- Anchors:
  - sample: `cli.py`, `routes_loans.py`, `routes_members.py`, `lending_service.py`, `catalog_service.py`, `memory_store.py`, `sqlite_store.py`;
  - nextgen: `WalletService`, `WalletServiceImpl`, `AuthServiceImpl`, `account.service.ts`, `auth.service.ts`, …; never `animations.ts`.

**Tasks** (`tasks.md`, 38 tasks, format validated):

| Phase | Tasks |
| --- | --- |
| Setup | T001 baseline suite; T002 preserve measurements (ask the owner where) |
| Foundational | T003–T006 |
| US1 (P1) | T007–T016 (10): imports, folding, entry protection, counts |
| US2 (P1) | T017–T020 (4): tests |
| US3 (P2) | T021–T025 (5): anchors and redirects |
| US4 (P3) | T026–T030 (5): planner input and cache key |
| Polish | T031–T038: suite, determinism, docs T033–T035, **owner-gated round T036**, SC-006 mapping and stranger test T037, record as Decision 13 (T038) |

The MVP is US1 plus US2, through T020.

---

## 5. Machine state (checked 2026-09-15, evening)

- **Config** `%USERPROFILE%\.codepedia\config.json` equals the backup (SHA-256 `5434E0916BAF…`) and holds the original chain. It was restored and hash-checked after each of the four 039 rounds.
- **Backup (durable, owner's choice):** `%USERPROFILE%\.codepedia\config.backup-038.json`, outside the repository. The Temp copies in the `67e7cc23` and `f07864a4` scratchpads are identical.
- **No `codepedia` process is running.**
- **Reference wikis:** regenerated at 039's final state (round 4, about 18:00 local). The plans are from round 1 (Groq 120b) and the narratives from round 2. Every published feature address resolves.
- **Answer keys** for the stranger test are in the `67e7cc23` scratchpad: `sc001-key-sample.md` and `sc001-key-nextgen.md`, written from the code. So are `us1-review.md` and `tense-review-*.md`.
- **039 measurements (durable):** `specs/039-feature-grouping/measurements/`. It holds the probes (`planner_probe.py` updated for 039, `grouping_proto.py`, `majors_probe.py`), the 033 baselines, every probe output, the prototype comparisons, the address lists and checks, `t036-round.md` and `t037-results.md`.

**Scratchpad directories** (Temp, may be cleaned):

- `…\456e97ec-df2f-47ea-8e7f-48b983dfff5c\scratchpad\` (the 039 implementation session):
  - `story-suites.ps1`, which runs the §7 suites;
  - `old_addresses.py <list> <docs>`, which checks that published addresses resolve;
  - `alias_audit.py <repo>`, which checks every alias's stub and target;
  - `proto_vs_impl.py <proto-dir> <repo>`, which compares groups with the prototype;
  - `tiebreak_probe.py`, `nomodel_anchors.py`, `feature_members.py`, `prompt_size.py`, `refusing_planner.py`, `trace_fold.py` and `where_tests.py`;
  - logs `r*-index-*.log`, `t036-index-*.log`, `full-suite-*.txt` and `baseline-039.txt`;
  - screenshots `t037-*.png`, and the pre-039 Overviews `index-*.before.md`.
- `…\67e7cc23-8892-4208-bfe9-a4fb46d55c2e\scratchpad\` (the 038 US1/US2 sessions): `config.backup.json`, the answer keys, `cost.py`, `why2.py`, `lead_links.py`, `shots.ps1`, `entry_probe.py`, `fixture_features.py`, `fix_mojibake.py`, `nopro_check.py`, `probe_models.py`, page snapshots, `full-suite*.txt`.
- `…\aeafd9e3-9c00-40fd-9211-3aacb5f77b43\scratchpad\` (this session):
  - `why3.py`, `majors_probe.py`, `module_rows_probe.py`, `planner_probe.py`, `grouping_proto.py`, `mermaid_parse.cjs`;
  - `probe-sample.txt` and `probe-nextgen.txt`: **033 baselines, needed by 039 T002**;
  - `proto-run1.txt`: **prototype output, cited by 039 research**;
  - `d19-stranger-test.md`, `sample-reply.d19-run1.json`, `sample-index.d19-run1.md`, the `*-d19-*.png` screenshots, `modules-preview\` (the trimmed-page trick), `index-*.log`, and `full-suite*.txt`.

---

## 6. Helper scripts and procedures

Run the Python helpers with `$env:PYTHONPATH='src'; .venv\Scripts\python.exe <script> <repo-root>`. Every one is read-only and needs no provider.

| Script (scratchpad) | Does |
| --- | --- |
| `planner_probe.py` (aeafd9e3) | Seeds, candidates, the planner prompt, the cached plan, repaired features and anchors. **039's main measuring tool.** |
| `grouping_proto.py <repo> [all\|entry] [--verbose]` (aeafd9e3) | 039's rules re-implemented outside `src/`; T016/T020/T025 compare against it. |
| `majors_probe.py` (aeafd9e3) | Per feature: kind, code, test and prose member counts, and MAJOR status. |
| `why3.py` (aeafd9e3) | The cached narrative reply, every rejection (section, index, rule, token), kept/offered/unasked counts, and majors. It supersedes `why2.py`. `why.py` (2-tuple) is broken. |
| `module_rows_probe.py` (aeafd9e3) | Module-list labels and descriptions as the page would show them. |
| `mermaid_parse.cjs` (aeafd9e3) | Parses the Mermaid blocks of Markdown files with the wiki's own `mermaid.min.js` in jsdom. Run from `frontend/` as `node <script> C:\Users\ASUS\IdeaProjects\codepedia docs/diagrams/class-diagram.md …`. It sets `dom.window.structuredClone`. |
| `cost.py` (67e7cc23) | Overview prompt, tokens and ceiling. |
| `lead_links.py <state>\docs\index.html` (67e7cc23) | Checks every link and code span in `.ai-generated` paragraphs; the expected result is 0 problems. |
| `shots.ps1 -Html <index.html> -OutPrefix <p>` (67e7cc23) | Headless Chrome screenshots, light and dark, at 400 px and wide. |

**Screenshots:**
- 700 px by hand: `& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --hide-scrollbars --window-size=700,3400 --screenshot=<png> --force-dark-mode --blink-settings=preferredColorScheme=0 file:///<index.html>`.
- A `#modules` anchor does not scroll in headless Chrome. To shoot the module list, copy `index.html` and `assets\wiki-ui.css`/`wiki-ui.js` into a scratchpad folder, cut the HTML from `<h1` to `<h2 id="modules"`, and shoot that. `modules-preview\` holds an example.

**Running the CLI** (`index` and `serve` both end by serving and blocking):

```powershell
$exe='C:\Users\ASUS\IdeaProjects\codepedia\.venv\Scripts\codepedia.exe'
Start-Process cmd -ArgumentList '/c',"echo y| $exe index <repo-root>" -RedirectStandardOutput <log> -RedirectStandardError <err> -WindowStyle Hidden -PassThru
```

Wait on the log with Bash:

```bash
n=0; until grep -qE 'Documentation wiki available|^Traceback|^Error:' "$LOG" "$ERR" 2>/dev/null || [ $n -ge 170 ]; do sleep 3; n=$((n+1)); done
```

Do not match a bare `Error`: class names such as `BibliothecaError` contain it. Then run `Get-Process codepedia | Stop-Process -Force`. Redact the `token=` in any log you quote.

**Config swap and restore:**
- **Swap**, after the hash-compare (Python):

  ```python
  import json
  d = json.load(open(p, encoding="utf-8"))
  d["summaryChain"] = ["groq:openai/gpt-oss-120b", "local:qwen2.5-coder:1.5b", "groq:openai/gpt-oss-20b"]
  json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
  ```

- **Restore:** `[IO.File]::WriteAllBytes($cfg,[IO.File]::ReadAllBytes($bak))`, then hash-compare again.

**Forcing a fresh narrative:** `DELETE FROM doc_overview_narratives` in `<state>\doc-manifest.sqlite`. Save the reply first if you want to compare. Any prompt change also misses the cache. Since 039, a grouping change or a `GROUPING_VERSION` bump misses the plan cache (`doc_feature_plans`) too.

**Did a round call a model?** Compare the `generated_at` of `doc_feature_plans` and `doc_overview_narratives` before and after the round: an unchanged timestamp means the cached row was reused.

**Published addresses:** before a re-index, list `<state>\docs\features\*.html`. After it, run `old_addresses.py <list> <state>\docs` and `alias_audit.py <repo>` (456e97ec scratchpad). The expected result is 0 broken, and no alias missing its stub.

**Full suite:** `.venv\Scripts\python.exe -m pytest --basetemp=<scratchpad>\pytest-x -p no:cacheprovider -q -rfE > <scratchpad>\full-suite.txt 2>&1`, in the background, about 10 minutes.
- The only accepted failure is `tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`, which makes a live Groq call and fails whenever Groq answers.
- With `-q`, the "N passed" line may not print. Judge by the exit code and the `FAILED`/`ERROR` lines.

---

## 7. What the next agent can do (ask before each non-trivial step)

**Step 0: orient.**
1. Read this file and 039 `research.md` Decision 13.
2. Run:
   - `git status --short`, `git log --oneline -3` and `git branch --show-current`. Expected: `main`; uncommitted 039 work since `611643c`, unless the owner has committed since.
   - Hash-compare the config with `%USERPROFILE%\.codepedia\config.backup-038.json`.
   - `Get-Process codepedia`: expect none.
3. Tell the owner anything that differs.

**Candidate follow-ups** (039 Decision 13, "Follow-ups"; none started). Ask the owner which, if any:

- **038's narrative relation sentences** ("calls", "stores results for", "integrates"): the largest remaining source of SC-007 flags. It needs a 038 prompt change and a model round.
- **Recognising Spring controllers as routes** (Java annotations). This would anchor nextgen's cross-stack features at their controllers. The parser records no annotations today.
- **The greeting-only README lead** (nextgen's "Welcome to …"), shared by the planner and the Overview.
- **SC-006 on the sample:** it scores layers while the grouping forms slices. This is an evaluation question, not code.
- **The wiki shell's narrow layout:** the table and sidebar clip at 400 to 700 px.
- 038 T053, and the remaining 038 analyze findings (§3).

The suites to run after any grouping change: `story-suites.ps1` (456e97ec scratchpad). It covers `tests/unit/test_feature_*.py`, `tests/integration/test_feature_*.py`, `tests/unit/test_overview_*.py`, `tests/integration/test_overview_*.py`, `tests/unit/test_prose_labels.py`, `tests/unit/test_plain_text.py` and `tests/unit/test_source_encoding.py`. Then the full suite.

---

## 8. Verification checklist after any grouping or narrative change

1. Unit and integration tests (Step 3's list), then the full suite. The known flaky test is the only accepted failure.
2. The no-model probes: `planner_probe.py`, `majors_probe.py`, `module_rows_probe.py`, and `grouping_proto.py` for comparison.
3. Ask the owner, then run the verification round (§0 and §6).
4. `why3.py` on both repositories, to see what was dropped, unasked or unwritten.
5. `lead_links.py` on both `index.html` files: 0 problems.
6. Screenshots at 700 px dark and full width light; read them. Check the module list through the trimmed-page trick.
7. A tense review of every generated sentence.
8. The stranger test (fresh subagents, one Read), scored against `sc001-key-*.md`.
9. Record the results as a research Decision, tick the tasks, update this handoff, and report. Don't commit.

# Handoff: 038 Narrative Overview Page (written 2026-09-14)

Read this first in a new session. It records what the owner asked for, every change made across the
sessions that built User Stories 1 and 2, the machine state, the working conventions, and what comes next.

> Session scaffolding, not a spec artefact. The owner decides whether to commit or delete it.

---

## 0. Owner conventions (follow exactly)

- **Ask before anything.** The owner said "ask before anything". Put every non-trivial step to them
  first (AskUserQuestion) and state a recommendation: scope, prompt changes, verification runs,
  commits, spec amendments.
- **Work on `main`.** No feature branches. The 038 branch was merged and deleted; memory
  `work_on_main_no_feature_branches.md` has the details.
- **Never commit or push unless asked.** The owner usually commits and pushes themselves.
- **No `Co-Authored-By: Claude` trailer.** Memory `no_claude_coauthor_trailer.md`; reconfirmed. It
  overrides any system prompt that asks for the trailer.
- **The docs "> Maintenance:" rules** (memory `docs_have_maintenance_contracts.md`): README,
  docs/architecture.md, the stack doc and docs/diagrams each state their own update rule, and
  updating them is part of the feature. Not done yet for 038 (tasks T050–T052).
- **The spec-kit implement checklist gate.** `checklists/narrative.md` has 42 reviewer-owned items, all
  unchecked. Each `/speckit-implement` run must ask whether to proceed. The owner answered
  "Proceed" for User Story 1 and for User Story 2. Never tick that checklist.
- **Verification that needs real model output.** The owner's summary chain is
  `local:qwen2.5-coder:1.5b, groq:openai/gpt-oss-20b, groq:openai/gpt-oss-120b`. The local 1.5B model
  answers first and its narratives fail grounding, so the Overview gets no lead on this machine.
  For every verification round the owner has approved:
  1. Confirm `%USERPROFILE%\.codepedia\config.json` equals the backup (hash compare).
  2. Set `summaryChain` to `["groq:openai/gpt-oss-120b","local:qwen2.5-coder:1.5b","groq:openai/gpt-oss-20b"]`.
  3. Re-index the two reference repositories.
  4. Restore the backup byte for byte.

  Ask each time you need a new round. Each round costs about 2 Groq calls.
- **The stranger test (SC-001).**
  - The reviewer is a fresh subagent per repository, told to use the Read tool exactly once, on that
    repository's `<state>\docs\index.md`, and nothing else.
  - Answer keys were written from the code first; scoring is against them.
  - The implementer never reviews.
  - Confirm `tool_uses: 1` in each notification.
- **Reference repositories.**
  - `C:\Users\ASUS\IdeaProjects\codepedia-sample-repo`, state dir `%USERPROFILE%\.codepedia\repos\a47b5ea9c5a22795`.
  - `C:\Users\ASUS\IdeaProjects\nextgen-wealth-ledger`, state dir `%USERPROFILE%\.codepedia\repos\3d82e509c5da9263`.

    The owner chose this one instead of Codepedia itself, which was never indexed and would take
    hours of provider time.

---

## 1. What was expected

Spec 038 (`specs/038-narrative-overview-page/`) turns the wiki's Overview page from a manifest into an
explanation, following the spec-kit runbook: specify → clarify → plan → checklist → tasks → analyze →
implement. The owner's instructions over the sessions:

1. Implement **User Story 1 (P1, the narrative lead)** only, then stop and report. Done, reported.
2. After the report: fix the false entry-point claim before User Story 2. Done (Decision 15). Then
   fix the owner-handle ambiguity and paragraph 3, keeping "where results end up". Done (Decision 16).
3. **User Story 2 (P2, the subsystems table plus per-subsystem paragraphs)**, after first fixing
   analyze finding **I2**. Done (Decision 17). Then the owner-approved prompt fix. Done (Decision 18).
4. User Story 3 (getting started) is **deferred** by clarification; there are no tasks.
   **User Story 4 (P4, module-list hygiene)** and **polish T050–T052** remain.

Spec facts to keep in mind:
- FR-005: the lead is 1–4 paragraphs published, 2–4 asked for. It says what the repository is and
  does, names the subsystems inline, and says where work enters and where its results end up. The
  owner explicitly kept "where results end up".
- Hard caps: lead ≤ 4 paragraphs; subsystem paragraphs ≤ 3 sentences and ≤ 8 of them; all generated
  prose < 600 words.
- Every generated paragraph must cite a resolved file, module or symbol (G7).
- With no provider, the page keeps the same structure and navigation, with nothing standing in for
  the missing prose.
- Reruns of an unchanged repository give byte-identical Markdown.
- Descriptions shown in the table appear only in a column whose header says "(AI-generated)".

---

## 2. Commits on `main` (all pushed; none carry a Claude trailer)

| Commit | Content |
| --- | --- |
| `2539226` | User Story 1 (tests plus code), CSS fixes, spec folder. **This commit introduced the mojibake fixed in `629e839`** |
| `f0e7f70` | Decisions 15 and 16: entry ranking, prompt labels, owner label, paragraph 3 made safe |
| `629e839` | I2 fix; User Story 2 (table, subsystem paragraphs, grounding, template); mojibake repair plus encoding guard test; spec docs |
| `1b585b1` | Decision 18 prompt fix (subsystem paragraphs cite their start file; ¶1 opens with what the repository is; ¶3 cites a file); research and tasks |

The working tree was clean at handoff (apart from this file).

---

## 3. What exists now (design as built)

### Package `src/doc_generator/overview/`
- `evidence.py` takes no engine; `narrator.py` is the **only** module that takes an engine;
  `grounding.py` takes no engine. `tests/unit/test_overview_package.py` enforces this.
- One LLM call per repository for the whole page, through the summary-chain `FailoverExecutor`.
- Cache: table `doc_overview_narratives` in `<state>\doc-manifest.sqlite`, one row per repository.
  - The key is `sha1(format version + system prompt + prompt text + max_tokens)`.
  - Any parseable reply is saved; an unparseable one is not.
  - The row stores the raw reply, the handle map, and (new) `repository_fingerprint`.

### Evidence (`evidence.py`)
- `FeatureBrief` per prompted feature (≤ 12, navigation order); `majorFeatureKeys` = the first ≤ 8
  features with kind ≠ tooling.
- `EntryFlow.kind` is one of `ENTRY_KINDS = ("cli-command","api-route","main")`, or `"function"` (an
  uncalled function).
  - An uncalled function named `main` becomes kind `main`.
  - Flows from test files are dropped (`is_test_path`: a `test`/`tests`/`__tests__` directory, or
    `test_*.py`, `*_test.py|go`, `conftest.py`, `*Test(s).java|kt|cs`, `*.spec|test.[cm][jt]s[x]`).
  - Ranking is by kind tier, then modules reached, then `stableKey`; at most 6 flows.
- `repositoryFingerprint` is SHA-1 of the README lead plus every file's `(relative path, contentHash)`.
  It is **never** in the prompt.

### Narrator (`narrator.py`)
- Constants: `NARRATIVE_FORMAT_VERSION = "2"`; `SYSTEM_PROMPT_CHARS = 1900` (the prompt is 1,896
  characters); `HEADER_CHARS = 300`; `FEATURE_BLOCK_CHARS = 710`; `ENTRY_FLOW_CHARS = 240`;
  `MAX_NARRATIVE_RESPONSE_TOKENS = 1400`.
- **Worst case: 4,590 tokens per call** of the 8,000 budget, computed from the constants.
- Reply shape: `{"lead": [...], "subsystems": {"fN": "..."}}`, under 550 words in all.
- Paragraph plan:
  - ¶1 **opens** with what the repository is and does. Then, only if a line is marked `entry`, it
    names that line's file as where work enters; otherwise it claims no entry point.
  - ¶2 follows one line, listing what it reaches without "then", "next" or "finally". Only an `entry`
    line is an entry point.
  - ¶3 is written only if a subsystem's own text says it stores, sends or returns data. It names
    **every** such subsystem, cites one of their start files, and never names a single file as the
    only destination.
  - `"subsystems"` holds one paragraph per subsystem marked `paragraph` and for no other: ≤ 3
    sentences, naming its start file in backticks, other subsystems as handles.
- Call line format:
  - ``entry (<kind>): `name` in `file` (part of [[fN]]); its calls reach [[fA]], [[fB]]``
  - ``uncalled: `name` in `file` …`` for a plain uncalled function.
- Feature block: `fN: Title (kind, K entry points[, paragraph]) - description`, then `start:` and
  `also:` lines. `, paragraph` marks a major subsystem.
- Statuses: `cached`, `generated`, `stale`, **`previous-prompt`**, `unavailable`, `failed`,
  `unparseable`, `skipped`.
  - On failure the narrator falls back to `load_latest`.
  - If the stored fingerprint equals the current one, the status is `previous-prompt`: the prose is
    shown with **no** stale caveat, and a terminal notice is printed.
  - A different or empty fingerprint gives `stale`: the prose is shown with the caveat.

### Grounding (`grounding.py`)
- Rules G1–G11 (research Decision 6):
  - G2: tokenise; unbalanced markup rejects.
  - G3: a handle must be issued by this prompt and live.
  - G4: a backticked name resolves to exactly one entry via `cross_references.resolve_reference`.
  - G5: identifier-shaped words outside backticks must resolve too. CamelCase is allowed if it
    appears in the evidence text, a language name or the repository name.
  - G6: no "you" and no banned promotional term.
  - G7: every paragraph cites a resolved name.
  - G8: ≤ 3 sentences. Code spans are masked and e.g./i.e./etc./vs./cf./approx./incl./resp. are not
    counted.
  - G9: ≤ 4 lead paragraphs; subsystem paragraphs only for majors, one each, ≤ 8. The word budget
    trims subsystem paragraphs (last first) before any lead paragraph.
  - G10: a failed opening paragraph withholds the whole lead; subsystem paragraphs are unaffected.
  - G11: subsystem paragraphs go in table order.
- `accept_description(text, evidence, lookup)` applies G1, G2 (a handle rejects), G4, G5 and G6, and
  returns escaped Markdown or `None`, which renders as "—".
- `render_paragraph` escapes everything; model text never reaches the page as raw Markdown.

### Generator (`generator.py`)
- The Overview is recomputed on every pass and written only when the SHA-1 of its Markdown changes.
- The overview evidence is built on every pass, narrated or not, because the table needs it
  (FR-024).
- `_repository_evidence` is kept from `_ensure_features`.
- `_subsystem_rows`: title link; responsibility = `accept_description(description)` for planned
  features, else a dash; "Start with" = `_start_with_member`.
  - That is the member with the most entry points, test files passed over while the subsystem has
    other members, ties by name, else the anchor.
  - It always belongs to the subsystem.
- Subsystem paragraphs are rendered with a trailing `[Title](features/…)` link.
- Notices go to `onNotice` (the CLI passes `typer.echo`); at most one line per pass (contract §7).
  - The `stale` wording is "showing the narrative from an earlier version (…)".
  - The `previous-prompt` wording is "showing the narrative written for an earlier prompt (…)".
- `index` passes `narrateOverview=False` on its structure pass.

### Template (`templates/home.md.jinja`) outline
1. `# <repo> — Documentation`.
2. Lead paragraphs, each followed by `{: .ai-generated }`.
3. The stale caveat, if the lead is stale.
4. The repo-meta list.
5. `## Architecture overview` with its counts sentence.
6. `| Subsystem | Responsibility[ (AI-generated)] | Start with |`. Every subsystem, navigation order; a
   dash when empty. "_No subsystems derived yet._" when there are none.
7. The subsystem paragraphs, each `{: .ai-generated }`.
8. The stale caveat here only when the lead was withheld but stale subsystem paragraphs survive.
9. The two diagram links.
10. `## Modules`, whose rows are unchanged; User Story 4 changes them.

The `## Features` list and the `| Feature | Modules |` table are gone. There is no inline Mermaid and
no "Last indexed" line.

### Manifest store (`manifest_store.py`)
- `ADDED_COLUMNS` migrates `repository_fingerprint` into existing tables (`PRAGMA table_info` plus
  `ALTER TABLE … ADD COLUMN`).
- `load_latest_overview_narrative` returns a **3-tuple** `(reply, handle_map, fingerprint)`.
- `save_overview_narrative(..., *, repository_fingerprint="")`.

### CSS (`frontend/src/styles.css`, built into `src/doc_generator/assets/wiki-ui.css` via `cd frontend; npm run build`)
- Adjacent `.ai-generated` paragraphs merge into one block with one badge.
- `.ai-generated { overflow-wrap: anywhere }`, so long Java paths wrap.
- The Features-list fix `ul:has(>li.module-list) a:last-child:not(:first-child)` stops a lone title
  link being right-aligned and greyed. It still matters for any list whose row has one link.
- Tables already scroll within themselves (`display:block; overflow-x:auto`).
- Tests: `tests/unit/test_wiki_stylesheet_overview.py`.

### Other fixes along the way
- `cross_references.build_symbol_lookup` now indexes kind `"document"`, so Markdown paths link
  everywhere. Shipped in `2539226`; the owner has not said whether it should have been split out.
- **Mojibake repaired.** `2539226` had re-saved `generator.py` and `tasks.md` through a cp1252 round
  trip, so every Overview, dependency-diagram and call-sequence page title read "… â€” …".
  - Repaired by exact reverse decoding (`<scratchpad>\fix_mojibake.py`, which keeps line endings).
  - Guard test: `tests/unit/test_source_encoding.py` scans `src/**/*.py|jinja` and
    `frontend/src/**/*.css|ts|tsx`.
  - **Watch for this when editing files through PowerShell.** Use UTF-8 explicitly
    (`[IO.File]::ReadAllText(p,[Text.Encoding]::UTF8)` with `WriteAllText(p,t,UTF8Encoding($false))`),
    or use the Edit tool.

### Spec documents updated
- `research.md`:
  - Decision 14: real replies during User Story 1.
  - Decision 15: entry kinds.
  - Decision 16: "part of" and paragraph 3.
  - Decision 17: I2 plus User Story 2 as built, with verification.
  - Decision 18: the subsystem prompt fix, the stranger test and the conclusion.
- `data-model.md`: `EntryFlow.kind`, `repositoryFingerprint`, the `previous-prompt` status, the table
  column plus migration, constants, and the state diagram.
- `contracts/overview-narrative.md`: prompt shape, call-line format, User Story 2 outline, and the
  `previous-prompt` notice row.
- `tasks.md`: T001–T043 and T033a–T033f marked `[X]`. The Decision 18 prompt round has no task row
  of its own; it is recorded in research Decision 18 and could be added as T043a.

---

## 4. Verification results (latest; details in research Decisions 15–18)

| | Sample | Nextgen |
| --- | --- | --- |
| Prompt / worst case for this repository | ~1,902 / 3,302 tokens | ~1,434 / 2,834 tokens (ceiling 4,590) |
| Lead kept | 3 of 3; ¶1 opens with what it is; ¶3 cites both stores | 3 of 3; ¶1 names `DigitalBankingApplication.main` as the entry (correct) |
| Subsystem paragraphs kept | 8 of 12: all marked majors; 4 unmarked dropped by G9 | 5 of 7: all marked; 2 unmarked tooling dropped |
| Generated words / links | ~289 words; 43 links, 0 problems | ~215 words; 28 links, 0 problems |
| Tense (SC-013) | all declarative present | all declarative present |
| Appearance | light/dark, 700 px and full width: one lead block, table scrolls inside, subsystem paragraphs one block | same |
| Full suite | only failure: the known flaky `tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing` (makes a live Groq call; fails whenever Groq answers) | |

**Stranger test (latest):** both repositories pass by the answer keys, but reviewers got the
subsystems mostly from module names.
- Lead: the first sentence helped.
- Table: mixed on the sample, partly helpful on nextgen.
- **Subsystem paragraphs: "mostly misleading"**, because they restate spec 033's mis-grouped features.
  - "Services (Lending Service) … generates stable identifiers … `utils/ids.py`".
  - The startup class and `animations.ts` sit under "Data Transfer Objects".
  - "Data Repositories supplies data to Persistent Entities" has the direction backwards.
- The sample reviewer still doubts `list_overdue` as *the* entry point; `bibliotheca serve` and the
  CLI are missed.

**Conclusion recorded in research Decision 18:** User Story 2 is complete and grounded. Its value is
capped by spec 033's grouping, titles and anchors. Improving the feature planner is the
highest-leverage next change.

---

## 5. Machine state

- **Config** `%USERPROFILE%\.codepedia\config.json` has been **restored** to the original chain; its hash
  equals the backup.
- **Backup:** `C:\Users\ASUS\AppData\Local\Temp\claude\c--Users-ASUS-IdeaProjects-codepedia\67e7cc23-8892-4208-bfe9-a4fb46d55c2e\scratchpad\config.backup.json`.
  An older copy is in the `f07864a4-…` scratchpad. Temp directories can be cleaned, so copy it
  somewhere durable if needed.
- **No `codepedia` process is running.**
- **Both reference wikis** reflect the Decision 18 prompt (last indexed 2026-09-14, Groq 120b).
- **Session scratchpad** (temporary): `...\67e7cc23-8892-4208-bfe9-a4fb46d55c2e\scratchpad\`. Run the
  Python helpers with `$env:PYTHONPATH='src'; .venv\Scripts\python.exe <script> <repo-root>`.
  - `cost.py <repo>` prints the prompt, its tokens and the ceiling.
  - `why2.py <repo>` prints the cached raw reply and each rejection (section #index: rule token). It
    handles the new 3-tuple. `why.py` is the old 2-tuple version and **breaks**.
  - `lead_links.py <state>\docs\index.html` checks every link and code span in `.ai-generated`
    paragraphs.
  - `shots.ps1 -Html <index.html> -OutPrefix <prefix>` takes headless Chrome screenshots, light and
    dark, at 400 px and full width. At 400 px the shell's sidebar never collapses on *any* page
    (pre-existing, not 038), so also shoot 700 px by hand with
    `chrome --headless=new --window-size=700,2200 --screenshot=...`.
  - `entry_probe.py <repo>` lists entry-point candidates with kind, decorators and reach.
  - `fixture_features.py <tmpdir>` prints the test fixture's features.
  - `fix_mojibake.py <file> [--write]`.
  - `nopro_check.py` is the User Story 1 no-provider check; it may need updating for the 3-tuple.
  - `probe_models.py` sends the prompt to each chain model.
  - Answer keys: `sc001-key-sample.md`, `sc001-key-nextgen.md`. Reviews: `us1-review.md`,
    `tense-review-*.md`. Also page snapshots `*-index.*.md`, logs, and `full-suite*.txt`.
- **Running the CLI:** `.venv\Scripts\codepedia.exe`. Both `index` and `serve` end by starting a
  server and blocking.
  - Launch detached, piping `y` for the disclosure prompt when the chain differs from the
    acknowledged one:
    `Start-Process cmd -ArgumentList '/c','echo y| C:\...\codepedia.exe index <repo>' -RedirectStandardOutput <log> -RedirectStandardError <err> -WindowStyle Hidden -PassThru`.
  - Wait on the log for "Documentation wiki available" with a Bash `until` loop matching
    `'Documentation wiki available|^Traceback|^Error:'`. Don't match bare `Error`: class names like
    `BibliothecaError` hit it.
  - Then `Get-Process codepedia | Stop-Process -Force`.
  - Foreground `sleep` is blocked in this harness.
- **Full suite:** `.venv\Scripts\python.exe -m pytest --basetemp=<scratchpad>\pytest-x -p no:cacheprovider -q`.
  A bare `pytest` shows about 17 spurious PermissionErrors. It takes about 10 minutes; run it in the
  background.
- **To force a fresh narrative:** `DELETE FROM doc_overview_narratives` in `<state>\doc-manifest.sqlite`.
  Any prompt change also misses the cache automatically.

---

## 6. Next steps (put them to the owner; they choose the order)

1. **A follow-up spec for 033's feature planner (recommended first).** The grouping, titles and
   anchors now cap the Overview's usefulness:
   - sample: "Tests (Test Fines)" anchored at `fine_calculator.py`; "Scripts" anchored at `member.py`
     with "Start with `policies`"; "Services (Lending Service)" anchored at `utils/ids.py`;
     "Services (Catalog Service)" anchored at `core/errors.py`;
   - nextgen: a 93-of-108-module "Data Transfer Objects" bucket anchored at `animations.ts`, and no
     features for controllers, security/JWT, clients, dashboard, chatbot or the Angular frontend.
2. **Small 038 presentation refinements**, each needing a verification round:
   - Separate each subsystem paragraph's closing link, for example " → [Title](…)". Today it reads
     like a stray fragment after the last sentence (`generator.py` subsystem paragraph render).
   - Use the UI font, not monospace, for the table's Responsibility column (`styles.css`, then
     `npm run build`). The whole table currently inherits the monospace font and gets tall when
     narrow.
   - Major selection (`evidence.majorFeatureKeys`): leave documentation-only and test-only
     subsystems out of the eight. 033's kind ranking puts "overview" and "capability" first, so on
     the sample "Documentation" and "Tests" get paragraphs while both Storage subsystems and Core
     do not.
   - When several lines are marked `entry`, ¶1 picks one (`list_overdue`). It could name the kinds
     ("HTTP routes in … and CLI commands in …").
   - Notice noise: paragraphs the model writes for unmarked subsystems count as "dropped" in every
     `overview:` notice (for example "4 of 15 narrative paragraphs dropped").
3. **User Story 4, T044–T049** (independent of the narrator; no model calls):
   - `prose.disambiguated_labels` for the eight identical `__init__` rows;
   - a module row without the stray `(`…`)` wrapper (the "(" at the right edge and the ")" after
     "dependencies" in screenshots);
   - `plain_text.excerpt` for descriptions (the README row dumps raw Markdown and ends mid-sentence).
   - Requirements FR-029 onward; SC-010.
4. **Polish T050–T052:** update `docs/architecture.md`, `docs/diagrams/class-diagram.md` and `README.md`
   under their "> Maintenance:" rules for everything 038 shipped:
   - the new `overview/` package;
   - the `doc_overview_narratives` table and its fingerprint column;
   - the Overview's new outline;
   - `previous-prompt`;
   - the CSS changes;
   - the encoding guard test.
5. **Remaining analyze findings, not applied** (from `/speckit-analyze`; I2 is fixed):
   - MEDIUM:
     - U1: FR-015's "settled" wording.
     - U2: write-if-changed compares the Markdown only, so an HTML-only link change is not written.
     - A3: "legibility" unquantified.
     - A4: no scripted SC-002 audit.
     - I4: no notice when a fallback provider wrote the narrative (FR-018 asks for one).
     - C2: no FR-002 assertion.
   - LOW: A5, C3, U5, D1, T1. See the analyze output or re-run `/speckit-analyze`.
6. **Open owner decisions carried from earlier reports:**
   - Chain order: the local 1.5B model first means no lead on this machine. Put a Groq model first,
     or accept it.
   - A cached reply that grounds to nothing stays until the repository changes, even after switching
     provider. Alternative: re-ask each pass while a weak model keeps failing.
   - The `cross_references` document-path fix changed links on other pages; it is already shipped.
7. **Outside 038** (would be separate specs):
   - The Java parser does not record annotations (`@PostMapping`), so Spring controllers look like
     plain uncalled methods.
   - Calls through interfaces are not resolved, so controllers and `main` reach one module.
   - The wiki shell has no narrow-viewport layout: at 400 px the sidebar stays and content is clipped
     on every page.

---

## 7. How to verify after any narrative change (checklist)

1. Unit and integration tests:
   `tests/unit/test_overview_{narrator,grounding,evidence,package}.py`,
   `tests/unit/test_manifest_overview_narratives.py`,
   `tests/integration/test_overview_{page,subsystems}.py`,
   `tests/integration/test_cli_overview_wiring.py`, `tests/unit/test_doc_generator_home_overview.py`,
   `tests/unit/test_source_encoding.py`, `tests/unit/test_wiki_stylesheet_overview.py`.
   Then the full suite.
2. Ask the owner. Then reorder the chain, re-index both repositories, read the terminal `overview:`
   line, restore the config, and hash-compare it with the backup.
3. `why2.py` on both repositories, to see what was dropped and why.
4. `lead_links.py` on both `index.html` files: 0 problems.
5. Screenshots at 700 px dark and full-width light; read them.
6. Tense review of every generated sentence.
7. Stranger test with fresh subagents (one Read each), scored against `sc001-key-*.md`.
8. Record the results in `research.md` (a new Decision) and `tasks.md`. Report to the owner. Don't commit.

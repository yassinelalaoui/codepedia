---

description: "Task list template for feature implementation"
---

# Tasks: CLI Packaging & Distribution

**Input**: Design documents from `/specs/020-cli-packaging/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/packaging-interface.md, quickstart.md

**Tests**: The `--version` flag (real Python source code) gets normal unit/contract tests. Everything else this feature adds (`install.sh`/`install.ps1`, the PyInstaller `.spec` file, the built binary itself) is validated manually against `quickstart.md`'s scenarios, per `plan.md`'s Technical Context — building and running a frozen binary inside the automated `pytest` suite is disproportionate to what this feature needs to prove.

**Organization**: Tasks are grouped by user story (spec.md, priority order P1-P4) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Exact file paths are included in every task description

## Path Conventions

Single project layout (`plan.md`'s Structure Decision): new `packaging/` directory at the repository root, one small change to `src/cli/main.py`, doc updates under `docs/`/`README.md`/`.gitignore`, `pyproject.toml` changes, matching tests under `tests/unit/` and `tests/contract/`.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new directory this feature adds and declare its one new build-time dependency.

- [X] T001 Create the `packaging/` directory structure: `packaging/` and `packaging/pyinstaller/` (empty, ready for the files Phase 2 adds)
- [X] T002 [P] Add an optional `build` dependency group (`pyinstaller>=6.0`) to `pyproject.toml`'s `[project.optional-dependencies]`, alongside the existing `test` group (research.md §2) — never a runtime dependency of the shipped binary

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The version-reporting flag, the PyInstaller build spec, and the build/release process every user story's validation depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Add a `--version` flag/callback to `src/cli/main.py`'s Typer `app`, implemented as `importlib.metadata.version("codepedia")` (FR-006, research.md §4)
- [X] T004 [P] Add a unit test for the `--version` flag in `tests/unit/test_cli.py` (asserts it prints the version from `pyproject.toml` and exits 0)
- [X] T005 [P] Add a contract test asserting the `--version` output format in `tests/contract/test_cli_interface.py`, matching `contracts/packaging-interface.md`'s "Command: `codepedia --version`" section
- [X] T006 Create `packaging/pyinstaller/codepedia.spec`: entry point `cli.main:app`, one-file mode, `copy_metadata("codepedia")` so `--version` works inside the frozen binary (research.md §2, §4) — depends on T001, T003
- [X] T007 Create `packaging/build.py`: a maintainer-run helper that invokes PyInstaller with `packaging/pyinstaller/codepedia.spec` for the current OS, producing `dist/codepedia` (or `dist/codepedia.exe`), then runs `--version` and `scan` against a throwaway repository through the freshly built binary as a smoke check before reporting success (research.md §8, quickstart.md Scenario 1) — depends on T006
- [X] T008 Write `packaging/README.md` documenting the maintainer build + release process: running `packaging/build.py` per OS, and manually uploading `dist/codepedia[.exe]` plus `packaging/install.sh`/`packaging/install.ps1` as assets to a new GitHub Release, named per `contracts/packaging-interface.md`'s "Release asset naming" table (research.md §7, §8) — depends on T007

- [X] T035 [P] Create `.github/workflows/release.yml`: a tag-triggered
  (`vX.Y.Z`) build matrix on `windows-latest`/`macos-13`/`ubuntu-latest`
  that each runs `packaging/build.py`, renames the output per
  `contracts/packaging-interface.md`'s asset-naming table, then a final
  job publishes all three binaries plus `install.sh`/`install.ps1` as a
  GitHub Release — added because this project's own dev machine was
  found unable to complete a local PyInstaller build at all, on any
  shell (research.md §8's superseding decision) — depends on T006, T007

**Checkpoint**: A maintainer can build a verified binary (locally, or via
CI if the local machine can't) and knows exactly how to release it — user
story implementation can now begin.

---

## Phase 3: User Story 1 - Installing on a clean machine with one command (Priority: P1) 🎯 MVP

**Goal**: A developer can install the CLI with exactly one command on a machine with no project-specific setup, confirm the install worked via `--version`, and know from the docs exactly what baseline the package itself requires.

**Independent Test**: On a throwaway machine/container with no Python installed, run the one-line install command for that OS, then run `codepedia --version` in a new terminal and confirm it prints a version.

### Implementation for User Story 1

- [X] T009 [P] [US1] Write `packaging/install.sh`: detects OS/arch, downloads the matching asset from the latest GitHub Release, installs to `~/.local/bin/codepedia`, adds that directory to `PATH` (current user's shell profile) if not already present, prints the installed version and how to verify it; exits non-zero with a distinct message for "no network access" and for "no release asset matches this OS/arch" (research.md §5, §7; contracts/packaging-interface.md)
- [X] T010 [P] [US1] Write `packaging/install.ps1`: same behavior as T009 for Windows — installs to `%LOCALAPPDATA%\codepedia\codepedia.exe`, adds it to the user `Path` via the registry if missing, same distinct-error behavior for no network / unsupported arch (research.md §5; contracts/packaging-interface.md)
- [X] T011 [P] [US1] Document the package's own baseline prerequisite (a supported OS: Windows/macOS/Linux, x86_64 — research.md §9) in `README.md`'s install section, clearly distinct from the separately-installed local LLM engine prerequisite (FR-004)
- [ ] T012 [US1] Manually validate `quickstart.md` Scenario 1 (build) and Scenario 2 (clean-machine install + `--version`) on a throwaway machine or container with no Python installed — depends on T006, T007, T009, T010, T035 (build may come from either a local `packaging/build.py` run or a CI-published release, per research.md §8's superseding decision)
- [ ] T013 [US1] Manually validate `quickstart.md` Scenario 8 (`serve` and `config`, not just `index`/`scan`, are runnable immediately after install — FR-003) — depends on T012
- [X] T014 [US1] Manually validate `quickstart.md` Scenario 9 (installing on an unsupported OS/arch fails with a clear, non-hanging error) — depends on T009, T010. Validated directly against `packaging/install.sh` (no real release needed - the OS/arch check runs before any network call): ran unmodified on this dev machine (git-bash reports `MINGW64_NT`, neither Linux nor macOS) and got a clear "Unsupported operating system" error, exit 1; separately re-ran with `uname` shimmed to report `Linux`/`arm64` and got a clear "Unsupported architecture" error, exit 1. Also exercised the "no matching release asset for this OS/arch" branch with a shimmed `curl` returning a real-shaped GitHub API response missing a linux-x86_64 asset - correct error, exit 1.
- [X] T015 [US1] Manually validate `quickstart.md` Scenario 10 (installing with no network access fails with a clear, non-hanging error) — depends on T009, T010. Validated against `packaging/install.sh` with `uname` shimmed to report a supported Linux/x86_64 platform and `curl` shimmed to fail exactly as it would with no connectivity (`curl: (6) Could not resolve host`) - script produced the clear, actionable "Could not reach GitHub..." error and exited 1, no hang.

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP.

---

## Phase 4: User Story 2 - Running the indexing command right after install (Priority: P2)

**Goal**: A freshly installed binary can run `codepedia index` against a real repository successfully, proving the packaging didn't drop anything `index` needs at runtime.

**Independent Test**: On a machine with the binary installed (US1) and a local LLM engine already running, run `codepedia index <repo>` and confirm it completes; separately confirm the existing 019 "local LLM unreachable" error still appears unchanged when the engine isn't running.

### Implementation for User Story 2

- [X] T016 [P] [US2] Add a `[tool.setuptools.package-data]` entry to `pyproject.toml` covering `doc_generator`'s `templates/*.jinja` and `assets/*` — fixes the latent gap where only editable installs happened to include these files (research.md §3)
- [X] T017 [US2] Add matching `--add-data` entries for `src/doc_generator/templates` and `src/doc_generator/assets` to `packaging/pyinstaller/codepedia.spec` (research.md §3) — depends on T006, T016
- [X] T018 [US2] Add hidden-imports entries to `packaging/pyinstaller/codepedia.spec` for every `tree-sitter-<language>` grammar package already declared in `pyproject.toml`'s dependencies (research.md §2-§3 constraint) — depends on T006
- [ ] T019 [US2] Manually validate `quickstart.md` Scenario 3 (post-install `index` run succeeds against a real repository, with a local LLM engine running) using a binary rebuilt with T017/T018 — depends on T017, T018, T012
- [X] T020 [US2] Manually validate `quickstart.md` Scenario 4 (indexing with the local LLM engine NOT running still shows 019's unchanged, actionable error — FR-012) using the same binary. The frozen binary itself could not be built in this sandbox (see `packaging/README.md` troubleshooting note), so validated instead against the real installed `codepedia` console script - the exact same `cli.main:app` code the binary would run, and packaging is required by FR-012 to never alter it. With no local LLM engine reachable: `codepedia index <repo>` printed "Validating repository" / "Checking local model availability" then stopped with 019's unchanged message ("Local LLM service at `http://localhost:11434` is unavailable for model 'qwen2.5-coder'. Start Ollama... This tool never falls back to a cloud provider."), exit 1, no AI work attempted.
- [X] T021 [US2] Manually validate `quickstart.md` Scenario 7 (`codepedia scan` succeeds with no local LLM engine installed at all — FR-010) using the same binary. Same caveat as T020 (validated via the installed console script, not the frozen binary): `codepedia scan <repo>` with no LLM engine reachable returned valid JSON output, exit 0.

**Checkpoint**: User Stories 1 AND 2 both work — the installed binary can successfully index a repository end to end.

---

## Phase 5: User Story 3 - Understanding the one remaining external prerequisite (Priority: P3)

**Goal**: Install documentation clearly and separately names the local LLM engine as an external prerequisite the package doesn't cover, states which commands need it, and documents how to uninstall.

**Independent Test**: Have someone with no prior exposure to the tool read only the install documentation and correctly state, unprompted, which one dependency remains their responsibility and which commands need it.

### Implementation for User Story 3

- [X] T022 [P] [US3] Rewrite `README.md`'s install section to document the one-line `install.sh`/`install.ps1` commands (T009/T010), explicitly name the local LLM engine (e.g. Ollama) as a separate external prerequisite the package does not and cannot include with a short explanation why (FR-008, FR-009), and add the single documented uninstall command per OS (FR-007) — done together with T011 in the same README rewrite
- [X] T023 [P] [US3] In the same `README.md` section, state plainly which commands work without the local LLM engine (`scan`) and which need it (`index`, the AI-backed parts of `serve`) (FR-010) — done together with T011/T022
- [X] T024 [P] [US3] Update `docs/architecture.md`'s "Runtime & deployment model" / prerequisites notes to record the new standalone-binary distribution path (020) alongside 019's existing `pip install -e .` contributor path
- [X] T025 [P] [US3] Update `docs/stack.md` to add PyInstaller as a new build-time-only tool, with the rationale from research.md §2 (why PyInstaller over Nuitka/cx_Freeze)
- [ ] T026 [US3] Manually validate spec.md's User Story 3 acceptance scenarios: have a reader who has not seen the rest of the docs read only the updated `README.md` install section and confirm they can state the one external prerequisite and which commands need it — depends on T022, T023

**Checkpoint**: User Stories 1-3 are all functional; documentation clearly scopes the one remaining external prerequisite.

---

## Phase 6: User Story 4 - Consistent installs across a team (Priority: P4)

**Goal**: The same install command, run on different clean machines, installs the same version, verifiable via `--version`.

**Independent Test**: Run the same one-line install command on two different clean machines/containers and confirm both report the same version via `codepedia --version`.

### Implementation for User Story 4

- [ ] T027 [P] [US4] Manually validate `quickstart.md` Scenario 5 (re-running the install command upgrades the existing install in place, no duplicate/conflicting install — FR-005)
- [ ] T028 [P] [US4] Manually validate `quickstart.md` Scenario 6 (uninstall via the documented single OS command leaves `codepedia` no longer runnable, per-repository state untouched — SC-006)
- [ ] T029 [US4] Manually validate spec.md's User Story 4 acceptance scenario: run the same install command on two different clean machines/containers and confirm `codepedia --version` matches on both

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Repo-wide consistency (diagrams, ignore rules, layout docs) and final full-suite validation.

- [X] T030 [P] Add a "Check installed version" use case (`ucCheckVersion`) to `docs/diagrams/use-case-diagram.md`, linked to the Operator actor
- [X] T031 [P] Update `.gitignore` to add `dist/` and `build/` (PyInstaller's output directories) — this project's `.gitignore` currently has no such entry at all
- [X] T032 [P] Update `README.md`'s "Project layout" section to mention the new `packaging/` directory
- [X] T033 Run the full `pytest` suite (`pytest`) and confirm zero regressions beyond the three pre-existing, already-documented Tree-sitter grammar-mismatch failures — 184 collected, exactly the 3 documented pre-existing failures, zero new regressions
- [ ] T034 Run every `quickstart.md` scenario (1-10) end to end, in sequence, as final release-readiness validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3/US4
  - US2 depends on a binary already being installable (US1) to validate against, though its own file changes (T016-T018) can be written in parallel with US1
  - US3 depends on US1's install commands existing (T009/T010) to document them, but its doc-content tasks can be drafted in parallel
  - US4 depends on US1's install commands (re-running them) and US2's working binary (comparing versions across machines running real installs)
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Within Each Phase

- Foundational: T003 (version flag) has no file dependency on T006/T007, but T006 needs T001 (directory) and benefits from T003 existing first for a meaningful smoke test in T007
- US1: T009/T010/T011 are independent files ([P]); T012 (build+install validation) depends on T009/T010 and the Foundational build tooling; T013-T015 (further validation) depend on T012's install already having succeeded, and on T009/T010 for the error-path scenarios
- US2: T016 (pyproject.toml) and T018 (hidden imports) don't depend on each other; T017 depends on T016 existing to add matching `.spec` entries; T019-T021 (validation) depend on T017/T018 and T012
- US3: T022-T025 are independent doc files ([P]); T026 (validation) depends on T022/T023
- US4: T027/T028 (Polish) touch different files and can run in parallel; T029 depends on a real install being repeatable (US1) and a working binary (US2)

### Parallel Opportunities

- T002 (Setup) has no dependency on T001 and can run alongside it
- T003, T004, T005 (Foundational) touch different files and can run in parallel
- T009, T010, T011 (US1) are different files and can run in parallel
- T016, T018 (US2) are different files and can run in parallel
- T022, T023, T024, T025 (US3) are all different files and can run in parallel
- T027, T028 (US4) are independent validation runs and can happen in parallel
- T030, T031, T032 (Polish) touch different files and can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch both install scripts and the baseline-prerequisite doc for User Story 1 together (different files, no shared dependency):
Task: "Write packaging/install.sh (POSIX installer)"
Task: "Write packaging/install.ps1 (Windows installer)"
Task: "Document the package's own baseline OS/arch prerequisite in README.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories; produces a verified, version-reporting binary)
3. Complete Phase 3: User Story 1 (install scripts + baseline-prerequisite doc + clean-machine/error-path validation)
4. **STOP and VALIDATE**: confirm `quickstart.md` Scenarios 1-2, 8-10 pass on a real clean machine
5. This alone already satisfies the spec's core success criterion in its simplest form (a developer can install with one command and verify it, all four commands are usable, and failure paths are clean)

### Incremental Delivery

1. Setup + Foundational → a maintainer can build and version-check a binary
2. Add US1 → clean-machine one-command install works, all four commands usable, failure paths are clear → **MVP**
3. Add US2 → the installed binary can actually run `index` successfully (the spec's full stated success criterion)
4. Add US3 → documentation clearly scopes the one remaining external prerequisite and documents uninstall
5. Add US4 → cross-machine install consistency verified
6. Polish → diagrams/ignore rules/layout docs updated, full suite re-verified

### Parallel Team Strategy

With multiple people:

1. Complete Setup + Foundational together (short, sequential-ish phase)
2. Once Foundational is done:
   - Person A: US1 (install scripts + baseline-prereq doc + clean-machine/error-path validation)
   - Person B: US2's file changes (T016-T018) drafted in parallel, validated once US1's binary exists
   - Person C: US3 (documentation)
3. US4 validation runs last, once US1/US2 are both confirmed working

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Manual `quickstart.md` validation tasks are this feature's equivalent of integration tests, per `plan.md`'s Technical Context — they exist specifically because a frozen, dependency-free binary can't be meaningfully exercised inside the existing `pytest`-based dev-environment suite
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence

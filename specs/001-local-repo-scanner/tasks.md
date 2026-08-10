# Tasks: Local Repository Scanner

## Implementation Strategy

Build the scanner in thin vertical slices. First establish the Python project
and package skeleton, then implement the core traversal and filtering pipeline,
then add language detection and structured output, and finish with end-to-end
validation on a real polyglot repository.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational model and output helpers must exist before the scanning pipeline.
3. User Story 1 delivers repository traversal and CLI entrypoints.
4. User Story 2 adds `.gitignore` and binary filtering on top of traversal.
5. User Story 3 adds language detection and the Parsing (1.2) output contract.
6. User Story 4 validates scale, determinism, and end-to-end correctness.

## Parallel Opportunities

- US1: CLI wiring, traversal implementation, and path validation can proceed in
  parallel once the package skeleton exists.
- US2: `.gitignore` handling and binary detection can be built in parallel,
  then wired into the scanner.
- US3: language registry, Tree-sitter fallback, and output serialization can be
  split across separate files.
- US4: fixtures, integration tests, and unit tests can be authored in parallel.

## Phase 1: Setup

- [X] T001 Create project metadata and dependencies in `pyproject.toml` for Typer, pathspec, tree-sitter, language packages, and pytest.
- [X] T002 Create the package scaffold in `src/repo_scanner/__init__.py`, `src/repo_scanner/__main__.py`, `src/repo_scanner/cli.py`, `src/repo_scanner/scanner.py`, `src/repo_scanner/ignore.py`, `src/repo_scanner/binary.py`, `src/repo_scanner/language.py`, `src/repo_scanner/models.py`, and `src/repo_scanner/output.py`.
- [X] T003 Add the top-level test scaffold in `tests/unit/`, `tests/integration/`, and `tests/fixtures/` with placeholder package files where needed.

## Phase 2: Foundational

- [X] T004 Define the core scan models in `src/repo_scanner/models.py` for repository requests, file candidates, retained source entries, summaries, and final scan results.
- [X] T005 Define the stable JSON output helpers in `src/repo_scanner/output.py` for the Parsing (1.2) consumer contract.
- [X] T006 Define repository traversal primitives and path normalization helpers in `src/repo_scanner/scanner.py`.

## Phase 3: User Story 1 - Scan a local repository path

Story goal: accept a local repository path, walk it recursively, and return a
streamed inventory of candidate files without materializing the entire tree.

Independent test criteria: a local repository path is resolved correctly, the
scan walks recursively, and the traversal remains streaming rather than loading
the full tree at once.

- [X] T007 [US1] Implement the CLI command and argument parsing in `src/repo_scanner/cli.py` so the user can invoke a repository scan from the command line.
- [X] T008 [P] [US1] Implement repository path validation and readable-path failure handling in `src/repo_scanner/scanner.py`.
- [X] T009 [P] [US1] Implement recursive directory walking and pruning of built-in irrelevant directories in `src/repo_scanner/scanner.py`.
- [X] T010 [US1] Connect the CLI to the scanning pipeline in `src/repo_scanner/cli.py` and `src/repo_scanner/scanner.py`.

## Phase 4: User Story 2 - Exclude ignored and binary content

Story goal: exclude files and directories ignored by the repository's
`.gitignore`, plus common non-source and binary content.

Independent test criteria: ignored paths never appear in the result, binary
files are excluded, and default exclusions remain pruned even when they are not
explicitly listed in `.gitignore`.

- [X] T011 [P] [US2] Implement `.gitignore` loading and path matching in `src/repo_scanner/ignore.py`.
- [X] T012 [P] [US2] Implement binary file detection heuristics in `src/repo_scanner/binary.py`.
- [X] T013 [US2] Wire ignore-rule evaluation and binary filtering into `src/repo_scanner/scanner.py`.

## Phase 5: User Story 3 - Detect language and emit structured output

Story goal: detect the language of each retained source file and emit a stable
structured list with relative path and detected language.

Independent test criteria: Python, JavaScript, and Java files are labeled
correctly, each retained file has a relative path, and the output matches the
Parsing (1.2) contract.

- [X] T014 [P] [US3] Implement the language registry and extension-based language mapping in `src/repo_scanner/language.py`.
- [X] T015 [P] [US3] Implement Tree-sitter fallback detection for ambiguous source files in `src/repo_scanner/language.py`.
- [X] T016 [US3] Serialize retained scan entries into the stable JSON shape in `src/repo_scanner/output.py`.
- [X] T017 [US3] Ensure the final output ordering is deterministic and compatible with the Parsing (1.2) consumer in `src/repo_scanner/output.py`.

## Phase 6: User Story 4 - Validate scale and correctness

Story goal: prove the scanner behaves correctly on a real polyglot repository
and stays practical for large repositories.

Independent test criteria: a polyglot fixture produces the exact expected file
set, ignored and binary files are absent, and the scanner handles a large file
set without an all-at-once memory load.

- [X] T018 [P] [US4] Create integration fixtures for a polyglot repository, ignored paths, binary files, and build outputs in `tests/fixtures/polyglot-repo/`.
- [X] T019 [P] [US4] Add end-to-end integration tests for inclusion, exclusion, and language labeling in `tests/integration/test_scanner.py`.
- [X] T020 [P] [US4] Add unit tests for binary detection and language detection edge cases in `tests/unit/test_binary.py` and `tests/unit/test_language.py`.
- [X] T021 [US4] Add a streaming or scaling smoke check for large repositories in `tests/integration/test_scaling.py`.

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 Update the CLI contract and quickstart validation steps in `specs/001-local-repo-scanner/contracts/cli.md` and `specs/001-local-repo-scanner/quickstart.md` to reflect the final command and output shape.
- [X] T023 Review the scan result schema in `specs/001-local-repo-scanner/contracts/scan-output.schema.json` against the implementation and adjust field names or constraints if needed.
- [X] T024 Perform a final pass for read-only repository handling, bounded-memory traversal, and consistent error messages across `src/repo_scanner/cli.py` and `src/repo_scanner/scanner.py`.

# Tasks: Multi-Language AST Parsing Engine

## Implementation Strategy

Build the parser in layered slices. First establish the Python project shape and
the shared Tree-sitter runtime. Then lock down the uniform parser contract and
AST envelope. After that, add one concrete parser per language family, and
finish with failure handling and batch-level validation so one bad file never
stops the run.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational models and runtime helpers must exist before parser classes.
3. User Story 1 establishes the shared parser contract and normalized AST
   shape.
4. User Story 2 adds language-specific parser implementations on top of the
   shared contract.
5. User Story 3 adds parse-failure handling, logging, and batch resilience.

## Parallel Opportunities

- US1: AST normalization, parser registry wiring, and contract tests can be
  developed in parallel once the package skeleton exists.
- US2: Python, JavaScript/TypeScript, and Java/Go/Rust parser implementations
  can be split across separate files and built in parallel.
- US3: failure diagnostics, batch orchestration, and malformed-input tests can
  be developed in parallel.

## Phase 1: Setup

- [X] T001 Create project metadata and dependencies in `pyproject.toml` for Tree-sitter, the official language grammar packages, and pytest.
- [X] T002 Create the package scaffold in `src/parser_engine/__init__.py`, `src/parser_engine/models.py`, `src/parser_engine/parser_base.py`, `src/parser_engine/parser_registry.py`, `src/parser_engine/treesitter_runtime.py`, `src/parser_engine/ast_builder.py`, `src/parser_engine/errors.py`, and `src/parser_engine/parsers/`.
- [X] T003 Create the test scaffold in `tests/unit/`, `tests/contract/`, and `tests/integration/` with fixture directories for valid and invalid source samples.

## Phase 2: Foundational

- [X] T004 Define the core parsing models in `src/parser_engine/models.py` for `SourceFile`, `ASTNode`, `AST`, `ParseResult`, and `ParseFailure`.
- [X] T005 Define the abstract parser contract in `src/parser_engine/parser_base.py` with the uniform `parse(SourceFile) -> AST` method.
- [X] T006 Define the Tree-sitter runtime adapter in `src/parser_engine/treesitter_runtime.py` for loading and caching grammar-specific parsers.
- [X] T007 Define the AST normalization helper in `src/parser_engine/ast_builder.py` so every parser emits the same node envelope shape.

## Phase 3: User Story 1 - Establish a uniform parser contract and AST envelope

Story goal: expose a single parser contract that downstream stages can use
without language-specific branches.

Independent test criteria: the base contract is stable, the AST envelope is
uniform, and parser dispatch can resolve a supported language to the matching
concrete parser.

- [X] T008 [US1] Implement parser registration and language-to-parser lookup in `src/parser_engine/parser_registry.py`.
- [X] T009 [P] [US1] Implement the top-level parser API exports in `src/parser_engine/__init__.py` so downstream code can construct and invoke parsers consistently.
- [X] T010 [P] [US1] Add contract tests for the normalized AST envelope in `tests/contract/test_ast_envelope.py`.
- [X] T011 [US1] Add contract tests for the shared parser interface in `tests/contract/test_parser_interface.py`.

## Phase 4: User Story 2 - Parse supported languages through concrete parser classes

Story goal: provide one concrete parser per supported language family using the
same `parse(SourceFile) -> AST` method.

Independent test criteria: Python, JavaScript, TypeScript, Java, Go, and Rust
files each produce a coherent AST through their dedicated parser class.

- [X] T012 [P] [US2] Implement `PythonParser` in `src/parser_engine/parsers/python_parser.py` using the shared runtime and AST builder.
- [X] T013 [P] [US2] Implement `JavaScriptParser` and `TypeScriptParser` in `src/parser_engine/parsers/javascript_parser.py` and `src/parser_engine/parsers/typescript_parser.py`.
- [X] T014 [P] [US2] Implement `JavaParser`, `GoParser`, and `RustParser` in `src/parser_engine/parsers/java_parser.py`, `src/parser_engine/parsers/go_parser.py`, and `src/parser_engine/parsers/rust_parser.py`.
- [X] T015 [US2] Wire the supported concrete parsers into `src/parser_engine/parser_registry.py` and ensure each parser resolves through the same dispatch path.
- [X] T016 [US2] Add language-specific unit tests in `tests/unit/test_python_parser.py`, `tests/unit/test_javascript_parser.py`, `tests/unit/test_typescript_parser.py`, `tests/unit/test_java_parser.py`, `tests/unit/test_go_parser.py`, and `tests/unit/test_rust_parser.py`.

## Phase 5: User Story 3 - Tolerate malformed syntax and continue batch parsing

Story goal: parse valid files, isolate malformed ones, and keep the batch moving
without crashing the full run.

Independent test criteria: a broken file is logged as a parse failure, valid
files still produce ASTs, and the batch continues after individual failures.

- [X] T017 [P] [US3] Define parse failure diagnostics and recoverable error types in `src/parser_engine/errors.py`.
- [X] T018 [P] [US3] Add batch parsing orchestration in `src/parser_engine/__init__.py` or `src/parser_engine/parser_registry.py` so per-file failures are isolated from the rest of the batch.
- [X] T019 [P] [US3] Add malformed-syntax fixtures in `tests/integration/fixtures/invalid/` and mixed-language fixtures in `tests/integration/fixtures/valid/`.
- [X] T020 [US3] Add integration tests for graceful failure handling and batch continuation in `tests/integration/test_parse_failures.py`.
- [X] T021 [US3] Add quickstart validation steps for valid, incomplete, and broken files in `specs/002-multi-lang-ast-parser/quickstart.md`.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T022 Review and align `specs/002-multi-lang-ast-parser/contracts/parser-interface.md`, `specs/002-multi-lang-ast-parser/contracts/ast-envelope.schema.json`, and `specs/002-multi-lang-ast-parser/data-model.md` with the implemented parser envelope and failure semantics.
- [X] T023 Add a final end-to-end regression test covering all supported languages plus one broken file in `tests/integration/test_multi_language_batch.py`.
- [X] T024 Tighten logging and error messages in `src/parser_engine/errors.py` and `src/parser_engine/__init__.py` so parse failures are easy to revisit later.

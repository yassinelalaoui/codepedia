# Tasks: AST Symbol Extractor

## Implementation Strategy

Build the feature in thin vertical slices. First establish the symbol model and
inventory types, then implement AST traversal for modules, classes, functions,
and nested declarations. After that, add raw relation extraction for imports,
calls, and inheritance, and finish with contract, integration, and quickstart
alignment.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational symbol and inventory types must exist before extraction logic.
3. User Story 1 establishes the abstract `Symbol` hierarchy and shared fields.
4. User Story 2 adds AST traversal for modules, classes, functions, and nested
   declarations on top of the shared model.
5. User Story 3 adds imports, call relations, inheritance relations, and the
   final file-level inventory contract.

## Parallel Opportunities

- US1: the base symbol model, inventory model, and contract tests can be
  developed in parallel once the package skeleton exists.
- US2: docstring extraction, parameter/return metadata, and nested declaration
  handling can be split across separate implementation passes.
- US3: import extraction, call relation extraction, inheritance extraction, and
  integration fixtures can be developed in parallel before wiring them together.

## Phase 1: Setup

- [X] T001 Create the feature package scaffold in `src/parser_engine/symbols.py`, `src/parser_engine/inventory.py`, `src/parser_engine/extractor.py`, `tests/unit/test_symbol_models.py`, `tests/unit/test_symbol_extractor.py`, `tests/contract/test_symbol_inventory.py`, and `tests/integration/test_symbol_inventory.py`.
- [X] T002 Create integration fixture directories and sample source files for modules, nested functions, imports, calls, and inheritance in `tests/integration/fixtures/symbol-extractor/`.
- [X] T003 Update the public package exports in `src/parser_engine/__init__.py` so the new symbol model and extractor entry points are importable from the package root.

## Phase 2: Foundational

- [X] T004 Define the abstract `Symbol` base type and shared fields in `src/parser_engine/symbols.py`, including `id`, `name`, `lineStart`, `lineEnd`, `docstring`, and `generatedSummary`.
- [X] T005 Define the concrete `ModuleSymbol`, `ClassSymbol`, and `FunctionSymbol` subtypes in `src/parser_engine/symbols.py` with the common inheritance shape requested by the feature.
- [X] T006 Define the file inventory and raw relation models in `src/parser_engine/inventory.py` for `FileSymbolInventory`, `ImportRecord`, `CallRelation`, and `InheritanceRelation`.

## Phase 3: User Story 1 - Establish the shared symbol hierarchy

Story goal: create the canonical symbol model so every extracted symbol shares a
common base structure and the summary field stays empty until Part 3.

Independent test criteria: each symbol subtype exposes the shared fields, the
abstract base is present, and `generatedSummary` is initialized empty.

- [X] T007 [P] [US1] Implement the abstract `Symbol` base class in `src/parser_engine/symbols.py` with validation or helper methods for common metadata.
- [X] T008 [P] [US1] Implement `ModuleSymbol`, `ClassSymbol`, and `FunctionSymbol` in `src/parser_engine/symbols.py` so each subtype inherits the common fields and keeps type-specific fields separate.
- [X] T009 [US1] Add unit tests for the shared symbol hierarchy and empty `generatedSummary` behavior in `tests/unit/test_symbol_models.py`.

## Phase 4: User Story 2 - Extract modules, classes, functions, and nesting

Story goal: walk each file AST and return the full symbol inventory for module,
class, function, method, and nested function declarations.

Independent test criteria: a test file with nested declarations returns every
symbol with correct names, positions, docstrings, parameters, and return type
data when available.

- [X] T010 [P] [US2] Implement AST traversal for top-level module, class, and function discovery in `src/parser_engine/extractor.py`.
- [X] T011 [P] [US2] Implement docstring, line-span, parameter, and return-type capture in `src/parser_engine/extractor.py` for each extracted symbol.
- [X] T012 [US2] Implement nested declaration preservation and ownership rules for methods and nested functions in `src/parser_engine/extractor.py`.
- [X] T013 [US2] Add unit tests for module, class, function, and nested symbol extraction in `tests/unit/test_symbol_extractor.py`.

## Phase 5: User Story 3 - Extract imports and raw relations

Story goal: return import statements, raw call relations, and raw inheritance
relations alongside the symbol inventory for each file.

Independent test criteria: a fixture file with imports, calls, and inheritance
produces explicit relation records that remain file-attributed and unassembled
into a graph.

- [X] T014 [P] [US3] Implement import statement extraction in `src/parser_engine/extractor.py` and attach the results to the file inventory.
- [X] T015 [P] [US3] Implement raw call relation extraction in `src/parser_engine/extractor.py`, including unresolved targets when the callee cannot be fully identified.
- [X] T016 [P] [US3] Implement raw inheritance relation extraction in `src/parser_engine/extractor.py` and attach those relations to `FileSymbolInventory`.
- [X] T017 [US3] Wire the extractor output into `src/parser_engine/inventory.py` so each file returns a complete `FileSymbolInventory`.
- [X] T018 [P] [US3] Add contract coverage for the inventory shape in `tests/contract/test_symbol_inventory.py`.
- [X] T019 [P] [US3] Add integration fixtures covering imports, calls, inheritance, and empty-module edge cases in `tests/integration/fixtures/symbol-extractor/`.
- [X] T020 [US3] Add end-to-end integration tests for complete symbol inventories in `tests/integration/test_symbol_inventory.py`.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T021 Align `specs/003-ast-symbol-extractor/contracts/symbol-extractor-interface.md`, `specs/003-ast-symbol-extractor/contracts/symbol-inventory.schema.json`, and `specs/003-ast-symbol-extractor/data-model.md` with the final field names and inventory shape.
- [X] T022 Update `specs/003-ast-symbol-extractor/quickstart.md` with runnable validation steps for hierarchy extraction, nesting, imports, calls, and inheritance.
- [X] T023 Perform a final consistency pass over `src/parser_engine/__init__.py`, `src/parser_engine/symbols.py`, `src/parser_engine/inventory.py`, and `src/parser_engine/extractor.py` to ensure the public API and feature contract line up.

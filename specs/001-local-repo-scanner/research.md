# Research: Local Repository Scanner

## Decision 1: Python + Typer

Decision: Implement the scanner as a Python CLI using Typer.

Rationale: The feature is a local command-line workflow with a structured output
contract. Python keeps the implementation compact, easy to test, and friendly to
filesystem streaming, while Typer gives a clean typed CLI surface.

Alternatives considered: Node.js with a CLI framework. Rejected for this feature
because the surrounding output contract is easier to validate in Python, and the
tree-scanning and content-classification pipeline benefits from Python's
straightforward packaging and test tooling.

## Decision 2: Gitignore handling

Decision: Use `pathspec` with GitIgnore semantics for repository-local ignore
rules.

Rationale: The scanner must match repository ignore behavior rather than invent
a custom approximation. `pathspec` is purpose-built for gitignore-style
matching, including edge cases and negation behavior.

Alternatives considered: Custom pattern parsing. Rejected because it would be
harder to keep behavior aligned with Git semantics and more expensive to test
thoroughly.

## Decision 3: Streaming traversal

Decision: Traverse with a streaming directory walk that prunes ignored
directories before descending and processes files one at a time.

Rationale: The spec requires enterprise-scale repositories without loading the
full tree into memory. A streaming walk keeps memory bounded and allows early
exclusion of `.git`, `node_modules`, build outputs, and other irrelevant paths.

Alternatives considered: Materializing the full file tree first. Rejected because
it scales poorly and conflicts with the memory constraint.

## Decision 4: Language detection

Decision: Prefer a deterministic extension-based mapping for the common source
languages in scope, then fall back to Tree-sitter-based content inspection for
ambiguous or extensionless files.

Rationale: The target scenario explicitly includes Python, JavaScript, and Java,
which are reliably distinguishable by extension in ordinary repositories. The
Tree-sitter fallback gives a principled path for edge cases without requiring
full-file parsing for every file.

Alternatives considered: Content-only parsing for every file. Rejected because it
is slower and unnecessary for the main success path.

## Decision 5: Output contract

Decision: Emit a JSON document with a stable top-level summary and an array of
file entries containing relative path and detected language.

Rationale: The Parsing module (1.2) needs a machine-readable, stable structure
that is easy to consume and validate.

Alternatives considered: Plain text output. Rejected because downstream parsing
would be brittle and less suitable for large-scale automation.

## Decision 6: No external infrastructure

Decision: Keep the scanner stateless with no database, broker, or remote
service.

Rationale: The constitution requires a local-only tool with no heavy
infrastructure dependency.

Alternatives considered: Persistent index store. Rejected for the scanner itself
because this feature only needs a local scan result, not a long-lived service.


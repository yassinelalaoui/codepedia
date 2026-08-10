# Research: Multi-Language AST Parsing Engine

## Decision 1: Python implementation

Decision: Implement the parsing engine in Python.

Rationale: The current repository already uses Python for local tooling, and the
Tree-sitter Python bindings provide a direct path to a uniform, testable parser
pipeline with a small amount of glue code.

Alternatives considered: Node.js and Go. Rejected because the surrounding
pipeline already has Python tooling, and the goal here is a library-style parser
with a compact contract rather than a separate runtime.

## Decision 2: Official Tree-sitter bindings and grammars

Decision: Use the official Tree-sitter Python bindings and official language
grammar packages for Python, JavaScript, TypeScript, Java, Go, and Rust.

Rationale: The feature explicitly requires Tree-sitter and the listed languages.
Official bindings and grammar packages keep the parser implementation aligned
with the upstream Tree-sitter ecosystem and reduce ambiguity around language
coverage.

Alternatives considered: Hand-rolled parsing or third-party parsers. Rejected
because they would weaken the guarantee of uniform syntax-tree handling across
languages.

## Decision 3: Abstract Parser contract

Decision: Introduce an abstract `Parser` base class with a single
`parse(SourceFile) -> AST` method, then implement one concrete parser class per
language.

Rationale: The user explicitly requires a uniform interface. A shared abstract
base class makes the dispatch layer simple and keeps downstream code from knowing
about language-specific parser details.

Alternatives considered: One monolithic parser with language conditionals.
Rejected because it would spread language-specific branching across the codebase
and make the contract harder to reason about.

## Decision 4: Structured failure handling

Decision: Return a parse result object that can represent either a successful
AST or a structured failure record.

Rationale: The feature must tolerate invalid or incomplete syntax and continue
processing other files. A structured failure keeps the batch observable without
raising an exception that stops the pipeline.

Alternatives considered: Raising on failure and catching at a higher layer.
Rejected because the API itself should make failure visible and easy to log.

## Decision 5: Uniform AST envelope

Decision: Normalize all Tree-sitter output into a common AST envelope with a
shared node shape and metadata fields.

Rationale: Downstream stages need to traverse one structure regardless of source
language. Normalization isolates Tree-sitter differences behind the parser
contract.

Alternatives considered: Exposing raw Tree-sitter nodes directly. Rejected
because the node shape and metadata differ in ways that would leak language
details into later pipeline stages.


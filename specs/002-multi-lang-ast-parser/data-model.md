# Data Model: Multi-Language AST Parsing Engine

## SourceFile

Represents one source file to parse.

Fields:
- `path`: repository-relative or absolute file path
- `language`: detected language label
- `content`: file contents as text or bytes source
- `encoding`: optional text encoding metadata

Validation:
- `path` must identify a readable file
- `language` must map to a supported parser implementation

## ParseRequest

Represents a single parse operation.

Fields:
- `source_file`
- `parser_key`

Relationships:
- Consumed by `Parser.parse`

Validation:
- The parser key must resolve to a registered parser

## ASTNode

Represents one node in the uniform AST envelope.

Fields:
- `type`
- `start_byte`
- `end_byte`
- `start_point`
- `end_point`
- `children`
- `fields`
- `named`
- `extra`
- `missing`

Relationships:
- Nodes form a tree rooted at an `AST`

Validation:
- Parent-child relationships must be preserved
- Node spans must be ordered and non-negative

## AST

Represents the normalized parse tree returned on success.

Fields:
- `language`
- `root`
- `source_path`
- `has_errors`
- `parser_name`

Relationships:
- Produced by a successful parse result

Validation:
- `root` must be present
- `language` must match the parser that produced it

## ParseFailure

Represents a structured parse error for one file.

Fields:
- `source_path`
- `language`
- `parser_name`
- `message`
- `recoverable`

Relationships:
- Produced when parsing fails or yields unusable output

Validation:
- Failure records must be emitted without aborting the batch

## ParseResult

Represents the outcome for one file.

Fields:
- `source_path`
- `language`
- `status` (`success` or `failure`)
- `ast`
- `failure`

Relationships:
- Returned by each parser invocation

Validation:
- Success results must contain an AST
- Failure results must contain a ParseFailure

## ParserRegistry

Maps a detected language to a concrete parser implementation.

Fields:
- `registered_parsers`
- `supported_languages`

Relationships:
- Used by the dispatch layer before parsing begins

Validation:
- Every supported language must resolve to exactly one parser implementation


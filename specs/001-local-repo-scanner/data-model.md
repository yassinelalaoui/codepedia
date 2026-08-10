# Data Model: Local Repository Scanner

## RepositoryScanRequest

Represents one scan invocation.

Fields:
- `root_path`: absolute local path provided by the user
- `resolved_root_path`: canonical local path used during traversal
- `output_format`: result format requested by the Parsing pipeline

Validation:
- `root_path` must exist
- `root_path` must be readable
- `resolved_root_path` must remain within the local filesystem

## PathRuleSet

Represents the ignore and exclusion logic applied during traversal.

Fields:
- `gitignore_patterns`: repository-local ignore patterns
- `default_excluded_dirs`: built-in directories such as `.git`, `node_modules`,
  `dist`, `build`, `out`, and `target`
- `binary_detection_rules`: heuristics for classifying a file as binary

Relationships:
- One repository scan uses one active rule set
- The rule set is consulted before descending into a directory or reading a
  file

Validation:
- Repository ignore rules must take precedence over inclusion
- Default excluded directories must be pruned before recursion continues

## FileCandidate

Represents a path discovered during traversal before classification.

Fields:
- `relative_path`
- `absolute_path`
- `entry_type` (`file`, `directory`, or `symlink`)

Relationships:
- Produced by the traversal stream
- Consumed by ignore, binary, and language classification steps

Validation:
- Relative paths must be stable and repository-root-relative

## SourceFileEntry

Represents one retained source file in the final result set.

Fields:
- `relative_path`
- `language`

Relationships:
- Derived from a `FileCandidate`
- Included in `ScanResult.entries`

Validation:
- `relative_path` must not be ignored or binary
- `language` must be one of the supported detected languages

## ScanSummary

Aggregated counters for the scan result.

Fields:
- `total_candidates`
- `included_files`
- `ignored_files`
- `binary_files`
- `unsupported_files`

Relationships:
- Attached to the final `ScanResult`

## ScanResult

Top-level output consumed by Parsing (1.2).

Fields:
- `root_path`
- `generated_at`
- `entries`
- `summary`

Validation:
- `entries` must be ordered deterministically
- `entries` must contain only retained source files
- `summary` counts must reconcile with the traversal outcome

## LanguageDefinition

Describes how a language is identified and labeled.

Fields:
- `name`
- `file_extensions`
- `tree_sitter_identifier`
- `ambiguity_rules`

Relationships:
- Used by the language detector

Validation:
- The registry must contain supported languages required by the success
  scenario, including Python, JavaScript, and Java


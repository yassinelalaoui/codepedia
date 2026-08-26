# CLI Contract: Local Repository Scanner

## Command

`codepedia scan <repo-path>`

## Purpose

Scan a local repository and emit a structured inventory of relevant source
files for downstream parsing.

## Inputs

- `repo-path`: absolute or relative path to a local repository

## Output

The command emits a JSON document on stdout that matches
[`scan-output.schema.json`](scan-output.schema.json).

## Expected behavior

- Traverses the repository recursively
- Applies repository `.gitignore` rules
- Skips built-in irrelevant directories
- Excludes binary files
- Detects a language for each retained source file
- Keeps the analyzed repository read-only

## Exit behavior

- `0`: scan completed successfully
- `1`: invalid path or unreadable repository
- `2`: scan failed due to a filesystem or classification error

## Downstream contract

The Parsing module (1.2) consumes the JSON result and should rely on the
stable top-level keys `root_path`, `generated_at`, `entries`, and `summary`.


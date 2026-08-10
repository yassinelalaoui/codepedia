# Quickstart: Local Repository Scanner

## Prerequisites

- Python 3.11 or later
- A local repository to scan
- The project dependencies installed in a virtual environment

## Validate the happy path

1. Install the project dependencies.
2. Run the scanner against a real polyglot repository containing Python,
   JavaScript, and Java files.
3. Confirm that the command exits successfully and emits a JSON document.
4. Confirm that each returned entry contains a repository-relative path and a
   detected language.

## Validate ignore behavior

1. Add a file or directory that is ignored by the repository's `.gitignore`.
2. Re-run the scanner.
3. Confirm that the ignored path is absent from `entries`.

## Validate binary filtering

1. Add a binary file under the repository tree.
2. Re-run the scanner.
3. Confirm that the binary file is absent from `entries` and counted in the
   summary as a binary exclusion.

## Validate scale and streaming behavior

1. Point the scanner at a large repository with tens of thousands of files.
2. Confirm that the command completes without requiring the entire tree to be
   materialized in memory.
3. Confirm that the output remains deterministic and suitable for the Parsing
   module (1.2).

## Expected result

The scanner returns only relevant source files, excludes `.gitignore` matches
and binary content, and labels each included file with the correct language.


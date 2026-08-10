# Feature Specification: Local Repository Scanner

## Overview

The product scans a developer-provided local source repository and returns a
structured inventory of relevant source files. It is intended for downstream
documentation generation and code understanding workflows that must stay fully
local.

The scanner must honor repository ignore rules, exclude non-source and binary
content, identify the programming language of each retained file, and scale to
large enterprise repositories without loading the full repository contents into
memory at once.

## User Scenarios & Testing

### Primary user scenario

A developer or lead technical user points the scanner at a local repository
path. The scanner traverses the repository, filters out ignored and irrelevant
paths, detects the language for each retained source file, and returns a
structured list containing each file's relative path and detected language.

### Acceptance scenarios

1. A repository containing Python, JavaScript, and Java source files produces a
   complete list of the relevant source files, with each file assigned the
   correct language.
2. Files excluded by `.gitignore` are absent from the result.
3. Standard non-source directories such as `.git`, `node_modules`, `dist`, and
   `build` are absent from the result.
4. Binary files are absent from the result, even when they appear under a source
   tree.
5. A repository with tens of thousands of files can be scanned without requiring
   the entire repository contents to be loaded into memory at once.

## Requirements

### Functional Requirements

1. The scanner must accept a path to an existing local repository.
2. The scanner must traverse the repository recursively from that root path.
3. The scanner must apply the repository's `.gitignore` rules when deciding
   whether to include a file or directory.
4. The scanner must exclude `.git` and other version-control metadata from the
   result set.
5. The scanner must exclude common dependency, build, and distribution
   directories, including `node_modules`, `.git`, `dist`, `build`, `out`, and
   `target`.
6. The scanner must exclude binary files from the result set.
7. The scanner must detect the programming language of each retained source
   file.
8. The scanner must produce a structured list where each entry contains at
   minimum the file's relative path and its detected language.
9. The scanner must preserve relative paths exactly as they appear within the
   repository structure.
10. The scanner must process large repositories incrementally so that it does
    not require loading the entire repository tree or all file contents into
    memory at once.
11. The scanner must fail clearly when the provided path does not resolve to a
    readable local repository.

### Non-Functional Requirements

1. The scanner must remain responsive on enterprise-scale repositories with
   several tens of thousands of files.
2. The scanner must be suitable for fully local execution.
3. The scanner must avoid writing into the analyzed repository.

## Assumptions

1. The scanner returns a machine-readable structured result that can be
   consumed by downstream tools.
2. The scanner treats common repository output directories such as `dist`,
   `build`, `out`, and `target` as excluded, even when they are not explicitly
   listed in `.gitignore`.
3. Language detection is based on file content and/or file metadata sufficient
   to distinguish the supported source languages in the repository.
4. The repository path points to a local filesystem location accessible to the
   user running the scanner.

## Success Criteria

1. On a real polyglot repository containing Python, JavaScript, and Java source
   files, the scanner returns the exact set of relevant source files.
2. The scanner returns zero files that are ignored by `.gitignore`.
3. The scanner returns zero binary files.
4. Every returned file has a detected language value that matches the file's
   actual source language.
5. The scanner can complete a scan of a repository with several tens of
   thousands of files without requiring an all-at-once in-memory load of the
   repository contents.
6. The scanner's output is stable enough to feed a downstream documentation
   pipeline without manual cleanup.

## Key Entities

### Repository

A local codebase provided by the user as the scan target.

### Source File

A retained, non-binary file that belongs in the scanner output because it is
part of the relevant codebase and not excluded by ignore or filtering rules.

### Ignore Rule

A repository-specific or default exclusion rule that prevents a path from being
included in the scan result.

### Language Detection Result

The programming language label associated with a retained source file.

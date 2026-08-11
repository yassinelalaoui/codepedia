# Feature Specification: Repository Metadata Persistence

## Overview

The product stores the analyzed repository metadata in a local, durable form so
that the indexed state can be reopened later without re-analyzing the code from
scratch. The stored metadata includes scanned source files, extracted symbols
for modules, classes, and functions, and the typed dependency relations between
them.

The persistence layer must support incremental updates for individual files,
fast retrieval of all metadata associated with a given file or module, and a
per-file content fingerprint that makes it easy to detect whether a file has
changed since the last indexing run.

## User Scenarios & Testing

### Primary user scenario

A developer indexes a repository, closes the tool, and later reopens it. The
tool restores the previously analyzed files, symbols, and dependency relations
exactly as they were, without requiring the code to be analyzed again.

### Acceptance scenarios

1. A repository index can be reopened later and still contains the same files,
   symbols, and dependency relations that were present before the tool was
   closed.
2. When a single source file changes, only that file and its associated
   metadata need to be updated in storage.
3. A user can retrieve all stored symbols for a given file or module without
   scanning the rest of the repository.
4. The stored content fingerprint for a file can be compared against a newly
   observed file to determine whether it has changed since the last index.
5. Dependency relations between symbols remain available after reopening the
   tool.
6. Metadata from unchanged files remains available even when other files in the
   repository are updated.

### Edge Cases

1. A file with no symbols still has a stored file record and a content
   fingerprint.
2. A file that was deleted since the last indexing run no longer appears as an
   active file record.
3. A file that changes multiple times in succession updates its stored
   fingerprint and symbol metadata each time.
4. Duplicate metadata for the same file does not create duplicate stored
   records.
5. A reopened repository with unchanged files returns the same stored metadata
   without requiring a fresh analysis pass.

## Requirements

### Functional Requirements

1. The system must persist scanned repository files in a local storage file
   that can be reopened later.
2. The system must persist extracted symbols for each scanned file, including
   modules, classes, and functions.
3. The system must persist the key attributes of each stored symbol, including
   name, position, documentation text when present, and symbol-specific
   metadata already produced by analysis.
4. The system must persist typed dependency relations between stored symbols,
   including import, call, and inheritance relations.
5. The system must support incremental updates for a single file without
   rewriting the entire repository index.
6. The system must allow a single file's stored metadata to be replaced or
   updated while leaving unrelated files intact.
7. The system must store a content fingerprint for each file so the tool can
   detect whether that file has changed since the last indexing run.
8. The system must allow retrieval of all stored metadata for a specific file.
9. The system must allow retrieval of all stored metadata for a specific
   module.
10. The system must restore the complete stored repository metadata after the
    tool is closed and reopened.
11. The system must preserve the relationships between files, symbols, and
    dependency edges across reopen operations.
12. The system must not require an external database server or any other
    separate storage service.
13. The system must not require re-analysis of unchanged files when reopening a
    previously indexed repository.
14. The system must keep file-level metadata and symbol-level metadata in sync
    when a file is updated.

### Non-Functional Requirements

1. The storage mechanism must remain fully local to the user's environment.
2. Retrieval of all metadata for a single file or module must remain efficient
   enough for interactive use on a previously indexed repository.
3. Incremental updates must preserve existing metadata for unchanged files.
4. Reopening the tool must produce the same stored repository view for the same
   indexed content.

## Assumptions

1. The repository has already been scanned at least once before the persistence
   layer is used for reopening or updating metadata.
2. File content fingerprints are derived from the full content of each source
   file.
3. The persistence layer stores repository metadata for local reuse rather than
   for multi-user synchronization.
4. The user expects unchanged files to be reused from storage rather than
   reprocessed.

## Success Criteria

1. After indexing a test repository and reopening the tool, all stored files,
   symbols, and dependency relations are available exactly as they were before
   closing.
2. Updating one file in a previously indexed repository changes only that
   file's stored metadata and leaves unrelated files untouched.
3. The tool can determine whether a file has changed by comparing stored and
   newly observed fingerprints without re-analyzing the rest of the repository.
4. A file-level or module-level lookup returns the complete stored metadata for
   that scope in one operation.
5. A repository with unchanged files can be reopened and queried without
   requiring a fresh full-repository analysis pass.

## Key Entities

### Repository Metadata Store

The persisted local record of the analyzed repository, including scanned files,
symbols, fingerprints, and dependency relations.

### Source File Record

The stored representation of one source file, including its identity, content
fingerprint, and associated symbols.

### Symbol Record

The stored representation of a module, class, or function extracted from a
source file.

### Dependency Relation

A stored typed relationship between two symbols, such as import, call, or
inheritance.

### File Fingerprint

A content hash used to determine whether a source file has changed since the
last indexing run.

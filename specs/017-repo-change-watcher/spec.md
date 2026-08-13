# Feature Specification: Repository Change Watcher

**Feature Branch**: `017-repo-change-watcher`

**Created**: 2026-08-13

**Status**: Draft

**Input**: User description: "Construire un watcher qui surveille en continu le dépôt de code local pour détecter les fichiers créés, modifiés ou supprimés depuis la dernière indexation. Le watcher doit fonctionner en arrière-plan sans bloquer l'utilisation normale du dépôt, ignorer les mêmes fichiers/dossiers exclus par le scanner (Partie 1.1), regrouper les changements survenant en rafale (ex. sauvegardes multiples rapprochées) pour éviter de déclencher une ré-indexation à chaque frappe, et transmettre la liste des fichiers impactés au pipeline de ré-indexation incrémentale. Critère de succès : la modification d'un seul fichier du dépôt déclenche, après un court délai de stabilisation, exactement un événement de ré-indexation contenant ce seul fichier, sans faux positifs sur les fichiers exclus."

## Overview

Build a background watcher that continuously monitors the local repository
already handled by the scanner (001) so that the documentation and index
stay current as the developer works. The watcher detects files created,
modified, or deleted since the last indexation, applies the same exclusion
rules as the scanner, and groups changes that happen in quick succession
(for example several saves a few seconds apart) into a single handoff
rather than reacting to every individual write. It then transmits the list
of impacted files to the incremental reindexing pipeline, which stays out
of scope for this feature.

## Goals

- Keep the index aligned with the repository's real state without the
  developer having to trigger a manual re-scan.
- Never interfere with or slow down normal repository usage (editing,
  building, running version control commands) while watching.
- Apply the exact same exclusion rules the scanner (001) already uses, so
  the watcher never reports changes on ignored, VCS, dependency/build, or
  binary paths.
- Collapse bursts of related changes (repeated saves, formatter rewrites,
  branch switches) into one reindexing handoff instead of one per raw
  filesystem event.
- Hand off a precise, deduplicated list of impacted files to the
  incremental reindexing pipeline for every batch of changes.

## Non-Goals

- Implementing or modifying the incremental reindexing pipeline itself;
  this feature only produces the impacted-file handoff it consumes.
- Providing a user interface to configure watch rules, exclusions, or
  stabilization timing.
- Watching any repository other than the one already configured for
  scanning and indexing.
- Guaranteeing change detection on storage that does not reliably deliver
  filesystem events (e.g., some network or removable drives); this is
  best-effort beyond local disks.

## User Stories

### US1 - Index stays current without a manual re-scan

As a developer working in the repository, I want the tool to notice when I
create, edit, or delete a file, so that the documentation and index
reflect my latest changes without me having to trigger anything manually.

Acceptance criteria:

- Creating a file in the repository is detected and eventually results in
  a reindexing handoff that includes that file.
- Modifying an existing file is detected and eventually results in a
  reindexing handoff that includes that file.
- Deleting a file is detected and eventually results in a reindexing
  handoff that identifies that file as removed.

### US2 - Uninterrupted normal repository usage

As a developer, I want the watcher to run in the background, so that
editing files, running builds, or using version control never feels
slower or gets blocked because the watcher is active.

Acceptance criteria:

- Normal file operations (save, build, checkout, branch switch) complete
  without perceptible delay caused by the watcher.
- The watcher does not lock, hold open, or otherwise prevent normal
  read/write access to repository files.

### US3 - Burst changes produce one handoff, not many

As a developer, I want a flurry of saves or a bulk operation (like an
autoformatter or a branch switch touching many files) to result in a
single, short-delayed reindexing handoff, so that the system doesn't
re-trigger indexing on every keystroke or intermediate write.

Acceptance criteria:

- Several rapid saves of the same file within a short window produce
  exactly one reindexing handoff for that file, not one per save.
- A bulk change touching many files at once (e.g., a branch switch)
  produces one handoff listing all impacted files once changes settle,
  rather than one handoff per file.

### US4 - No noise from excluded paths

As a developer, I want changes to ignored files and directories (VCS
metadata, dependency/build output, binaries) to never trigger a
reindexing handoff, so that the pipeline is never asked to process
irrelevant content.

Acceptance criteria:

- Changes confined to paths excluded by the scanner's rules (001) never
  produce a reindexing handoff.
- A handoff that also includes at least one non-excluded file lists only
  the non-excluded file(s), never the excluded ones.

### Edge Cases

- What happens when a file is created and then deleted again before the
  stabilization delay elapses? The net effect is no change, so no
  reindexing handoff is produced for that file.
- What happens when many files change at once (bulk operation)? All
  impacted files are grouped into a single handoff once changes stabilize,
  instead of one handoff per file.
- What happens when a file is renamed? It is reported as a deletion of the
  old path and a creation of the new path.
- What happens if the watcher temporarily loses access to the repository
  (e.g., the volume becomes unavailable)? The watcher surfaces a clear
  error rather than silently stopping or hanging.
- What happens to changes made while the watcher was not running (tool
  restarted, machine was off)? On startup, the watcher reconciles the
  repository's current state against the last known indexed state and
  issues a catch-up reindexing handoff covering everything that changed in
  the meantime.
- What happens when the watcher starts against a repository that has never
  been indexed before (no prior indexed state at all)? Reconciliation
  treats this as a diff against an empty baseline: every non-excluded,
  non-binary file currently present is reported as created, in a single
  catch-up handoff, exactly as any other startup reconciliation would
  report it.
- What happens when a change lands inside a directory that is itself
  excluded, but the changed file's name would otherwise look relevant
  (e.g., a source file copied into `node_modules`)? It is still excluded,
  because exclusion is evaluated on the full path, matching the scanner's
  behavior.

## Requirements *(mandatory)*

### Functional Requirements

#### Change detection

- The watcher MUST continuously monitor the local repository root for
  files created, modified, or deleted, starting from the point of the
  last completed indexation.
- On startup, the watcher MUST reconcile the repository's current state
  against the last known indexed state and produce a catch-up reindexing
  handoff for anything that changed while it was not running.
- If no indexed state exists yet for the repository (first run), the
  watcher MUST treat startup reconciliation as a diff against an empty
  baseline, so every non-excluded, non-binary file currently present is
  reported as created in a single catch-up handoff.
- A rename MUST be reported as a deletion of the old path and a creation
  of the new path.

#### Non-blocking background operation

- The watcher MUST run in the background and MUST NOT block, delay, or
  restrict normal developer operations on the repository (editing,
  building, version control commands).
- The watcher MUST NOT hold locks on repository files that would prevent
  normal read/write access to them.

#### Exclusion parity with the scanner

- The watcher MUST apply the same exclusion rules as the scanner (001),
  including `.gitignore` rules, VCS metadata (`.git`), and common
  dependency/build/distribution directories (`node_modules`, `dist`,
  `build`, `out`, `target`, and equivalents).
- The watcher MUST NOT produce a reindexing handoff for changes confined
  entirely to excluded paths.
- The watcher MUST evaluate exclusion on the full relative path of a
  changed file, so a relevant-looking file inside an excluded directory is
  still excluded.

#### Burst grouping (debouncing)

- The watcher MUST wait for a short stabilization delay after a file's
  last detected change before treating that file as ready to hand off, so
  that intermediate, in-progress writes are not each handed off
  separately.
- The watcher MUST group all files that changed and stabilized within the
  same burst window into a single reindexing handoff.
- A file that is created and then deleted again before the stabilization
  delay elapses MUST NOT appear in any reindexing handoff.

#### Handoff to the incremental reindexing pipeline

- For each stabilized batch of changes, the watcher MUST transmit to the
  incremental reindexing pipeline the list of impacted files, each with
  its change type (created, modified, or deleted).
- A reindexing handoff MUST include a file if and only if that file
  actually changed (net of any create/delete cancellation within the
  stabilization window); it MUST NOT include unrelated or excluded files.
- The watcher MUST continue watching and remain able to produce further
  handoffs after transmitting a batch, without requiring a restart.
- If the watcher loses access to the repository, it MUST surface a clear
  error rather than stopping silently or hanging indefinitely.

### Key Entities

- **WatchedRepository**: The local repository root being continuously
  monitored, together with the exclusion rules (shared with the scanner,
  001) applied to it.
- **FileChangeEvent**: A single raw creation, modification, or deletion
  detected for one file path at a point in time, before grouping.
- **ChangeBatch (Reindexing Handoff)**: The stabilized, deduplicated set
  of impacted files — each with its change type — transmitted together to
  the incremental reindexing pipeline after a burst of changes settles.
- **LastIndexedState**: The record of what the system considered indexed
  as of the previous run, used to compute the catch-up handoff on startup.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Modifying a single file in the repository results, after a
  short stabilization delay, in exactly one reindexing handoff that
  contains that one file and no others.
- **SC-002**: Saving the same file several times in quick succession (for
  example five saves within a couple of seconds) results in exactly one
  reindexing handoff for that file, not one per save.
- **SC-003**: A change confined to files or directories excluded by the
  scanner's rules never results in a reindexing handoff.
- **SC-004**: A developer can continue editing, building, and using
  version control on the repository while the watcher runs, with no
  perceptible slowdown attributable to the watcher.
- **SC-005**: Files changed while the watcher was not running are fully
  captured in a single catch-up handoff the next time the watcher starts,
  with no changes silently missed.
- **SC-006**: A bulk change touching many files at once produces one
  grouped handoff listing every impacted file, rather than a separate
  handoff per file.

## Assumptions

- "Since the last indexation" is tracked internally by the system (a
  persisted last-indexed state), not something the developer supplies
  manually.
- The stabilization ("burst") delay is short — on the order of a second or
  two — and is an internal implementation parameter rather than something
  exposed for the user to configure in this feature.
- The watcher runs as part of the same local tool/process lifecycle that
  performs scanning and indexing (001-016), not as a separate
  always-on operating-system service, consistent with the project's
  local-only, minimal-infrastructure principles.
- The incremental reindexing pipeline that consumes the impacted-file
  handoff already exists or is built separately; this feature is
  responsible only for detecting changes and producing the handoff, not
  for the reindexing logic itself.
- Exclusion rules are the same rule set defined and maintained by the
  scanner (001), reused rather than redefined here, so the two never
  diverge.

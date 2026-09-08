# Feature Specification: Launcher Homepage with Live Run Progress

**Feature Branch**: `037-launcher-homepage-progress`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Launcher homepage with live run progress. A new `codepedia home` hub server that gives Codepedia a homepage, so starting work no longer requires typing `codepedia index <path>` or `codepedia serve <path>` in a terminal. The existing CLI must keep behaving exactly as it does today — the homepage is an additional entry point, not a replacement, and the `serve` command is not modified. The homepage has two parts, which are one feature because neither works without the other: (1) An index bar: type a repository path, press go, and that repository gets indexed. Beneath it, an 'analyze history' listing repositories that have already been indexed, so the user can jump straight back into one. (2) A live progress display for a run, covering the whole pipeline — validating, checking models, scanning, parsing, building the graph, generating documentation structure, summarizing, generating documentation content, embedding, starting the server — so a long run never looks hung. The stages are wildly uneven: summarization dominates and can take many minutes, so progress must advance within a stage, not only when a stage changes. Decisions already made with the repository owner; treat these as settled requirements, not open questions: Opening a repository from the history launches a per-repository `codepedia serve` subprocess on its own port and links the user to it. The hub does not re-host wikis itself. A run that fails at a late stage keeps today's behaviour: the whole run is discarded, nothing is promoted. The homepage must show this as an explicit terminal failure that names the stage that failed and the provider error behind it, and offers a retry. It must never leave a bar spinning forever. Only one indexing run may be in progress at a time. A second request while one is live is rejected with a clear message naming the repository already running. The hub binds to 127.0.0.1 only, generates a fresh authentication token per run that is never persisted to disk, prints a URL carrying that token, and requires the token on every state-changing request. Triggering an index from a browser is a write action against an arbitrary filesystem path, so the submitted path is untrusted input and must be validated. Indexing must write only under the user's Codepedia state directory, never into the analyzed repository. Each history row offers, behind a three-dots menu: Properties (showing the repository path and when it was last indexed), Open (starts the server and opens the wiki), and Remove (a confirmed destructive action that deletes only the stored wiki, index and metadata for that repository, and never touches the repository itself). There is deliberately no re-index action: opening a repository already performs an automatic catch-up re-index of everything that changed while it was closed. Because opening a repository can trigger a catch-up re-index that takes minutes, the progress display must cover that catch-up too, not only fresh index runs. The history listing is reconstructed from already-persisted repository metadata; no new storage service is introduced. Leftover partial-run staging directories must be filtered out so they never appear as phantom repositories. The homepage should feel like part of the same product as the generated wiki, reusing its existing visual tokens and brand assets. Out of scope for this feature: any local/cloud provider switch or provider-chain editing (that is a later feature), and any change to the pipeline that would make earlier stages' output survive a late failure."

## Clarifications

### Session 2026-09-04

- Q: Can the user stop an analysis that is already running? → A: Yes — a visible
  Stop control, ending the run in a terminal "cancelled" state alongside
  succeeded and failed, discarding the partial work as a failure does and
  freeing the hub to accept the next analysis immediately.
- Q: While an analysis is running, where does the progress appear? → A: In place
  on the homepage, taking over the area the index control occupies, with the
  history still listed below it. One address, no separate run page — reloading
  or opening another tab lands on the live run automatically.
- Q: Once a run has ended, does its outcome stay on the homepage, and is any
  record of past runs kept? → A: A durable log of recent runs, kept across
  restarts of the hub and viewable on the homepage, in addition to the
  just-finished run staying visible where it ran. Stored locally alongside the
  tool's existing state, bounded and self-pruning.
- Q: What identifies a repository in the analyse history, and what happens when
  that folder is moved, renamed or deleted? → A: The path is its identity, as it
  already is in stored data. A row whose folder no longer exists stays listed
  and visibly marked unavailable — still readable, still removable, but not
  able to be brought up to date. Analysing the new location creates a separate
  entry; no attempt is made to detect a move.
- Q: Should the homepage carry the same System / Light / Dark control the
  generated wiki gained in 036, or simply follow the operating system? → A: The
  same three-state control, with the current state visible, the choice
  remembered for the homepage on this machine, and applied before first paint.
  Independent of any wiki's own choice, as the wikis are independent of each
  other.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyse a repository without opening a terminal (Priority: P1)

Someone wants to document a project on their machine. Today the only way in is
to remember a command name, a subcommand, and a path, and type all three
correctly into a terminal. They want to open one page, paste or type the folder
they care about, press a button, and watch it happen.

Watching it happen is not a nice-to-have here. A full analysis of a real
repository takes many minutes, and most of that time is spent in a single stage
that produces no visible sign of life. Without continuous feedback the only
honest interpretation of a still screen is that the tool has hung — so the
person kills it, and loses the work. The index control and the progress display
are one story because either alone is unusable.

**Why this priority**: It is the feature's reason to exist, and it is the only
part that cannot be approximated by anything shipping today. Everything else in
this specification either builds on the run it starts or navigates its results.

**Independent Test**: Start the hub, open the homepage, enter the path of a
repository, press the control that starts analysis, and confirm that the display
names the stage currently running and keeps changing while work continues —
without opening a terminal at any point.

**Acceptance Scenarios**:

1. **Given** the homepage is open and no analysis is running, **When** the user
   looks at the page, **Then** a field for a repository path and a control to
   start the analysis are visible and reachable by keyboard.
2. **Given** a valid path to a readable directory, **When** the user starts the
   analysis, **Then** the page shows an analysis in progress for that path
   within a few seconds, naming the stage currently running.
3. **Given** an analysis in progress, **When** the run moves from one stage to
   the next, **Then** the display marks the finished stage as complete and names
   the new one, preserving the order the pipeline actually runs them in.
4. **Given** an analysis in a stage that processes many items one by one,
   **When** each item finishes, **Then** the display advances — the person can
   see how many items are done, how many remain, and that the count is moving.
5. **Given** an analysis that completes successfully, **When** the last stage
   finishes, **Then** the page shows a clearly successful terminal state and
   offers to open the resulting documentation.
6. **Given** an analysis in progress, **When** the user reloads the page or
   opens the homepage in a second browser tab, **Then** the current state of
   that run is shown as it stands — not an empty display, and not a second run.
7. **Given** an analysis in progress that the user started by mistake, **When**
   they stop it, **Then** the run ends in a clearly cancelled state saying no
   documentation was kept, and a new analysis can be started immediately.

---

### User Story 2 - Go straight back to a repository already analysed (Priority: P2)

Someone analysed three projects last week. Today they want to look at one of
them again. They should not have to remember which paths they used, retype one,
or know that a different command exists for reopening versus creating.

Below the index control the homepage lists the repositories that have already
been analysed. Picking one takes them to its documentation. Because the code
has moved on since the last visit, opening it also brings the documentation up
to date with whatever changed while it was closed — and because that catch-up
can itself take minutes on an active project, it is shown with the same progress
display as a fresh analysis rather than leaving the person staring at a page
that has not loaded.

**Why this priority**: Without it the homepage is a one-shot form, and the
person is back in the terminal the moment they want to return to earlier work.
It is second only because it has nothing to list until User Story 1 has run at
least once.

**Independent Test**: With at least one repository already analysed, open the
homepage and confirm it is listed; choose to open it and confirm the browser
arrives at that repository's documentation without any command being typed.

**Acceptance Scenarios**:

1. **Given** repositories that have been analysed previously, **When** the user
   opens the homepage, **Then** each of them appears in a listing beneath the
   index control, most recently analysed first.
2. **Given** a state store that also contains the leftovers of runs that never
   finished, **When** the listing is shown, **Then** those leftovers do not
   appear as repositories.
3. **Given** a repository in the listing, **When** the user chooses to open it,
   **Then** a server is started for that repository and the browser arrives at
   its documentation.
4. **Given** a repository whose source code changed since it was last analysed,
   **When** the user opens it, **Then** the changed parts are brought up to date
   and that work is shown with the same progress display as a fresh analysis.
5. **Given** a repository whose source code did not change since it was last
   analysed, **When** the user opens it, **Then** they arrive at the
   documentation promptly and are not shown a progress display that has nothing
   to report.
6. **Given** one repository already open, **When** the user opens a second one,
   **Then** both remain reachable and independent of each other.
7. **Given** an analysis has just completed for a repository not previously
   listed, **When** the user returns to the homepage, **Then** that repository
   is in the listing without the page needing to be reloaded manually.

---

### User Story 3 - A failing run says so, and says why (Priority: P3)

An analysis reaches its last stage and cannot get there: every configured
provider for that stage is unreachable. Today the entire run is discarded — all
of it, including documentation that was generated correctly minutes earlier.
That behaviour is deliberate and is not being changed here.

What must change is that the person finds out. A display that shows nine ticked
stages and then stops forever is worse than no display at all, and a display
that shows nine ticked stages next to the word "failed" without saying that the
ticked work was thrown away is actively misleading. The run must end, visibly,
naming the stage that failed and the reason behind it, stating plainly that
nothing was kept, and offering to try again.

**Why this priority**: It is third by sequencing, not by importance. On any
machine where a provider is unavailable this is the path every run takes, so it
is not an edge case dressed as a story — but it can only be built once there is
a run and a display for it to terminate.

**Independent Test**: Start an analysis in an environment where a required
provider cannot be reached, and confirm the display reaches a stopped, clearly
failed state that names the stage and the cause, rather than continuing to
appear busy.

**Acceptance Scenarios**:

1. **Given** an analysis that fails at any stage, **When** the underlying work
   stops, **Then** the display reaches a terminal failed state — it never
   continues to present the run as in progress.
2. **Given** a run that failed, **When** the user reads the failure, **Then** it
   names the stage that failed and describes the cause in terms they can act on,
   including which providers were attempted when the cause was a provider.
3. **Given** a run that failed after some stages had completed, **When** the
   user reads the failure, **Then** it states plainly that no documentation was
   kept from the run, so the completed stages are not mistaken for saved work.
4. **Given** a run that failed, **When** the user chooses to try again,
   **Then** a fresh analysis of the same path is started without retyping it.
5. **Given** a run that failed because no provider could be reached, **When** the
   failure is shown, **Then** the system has not altered the user's provider
   configuration in any way.
6. **Given** a run that fails, **When** it has finished failing, **Then** the
   system is ready to accept a new analysis — a failed run does not leave the
   hub permanently unable to start another.

---

### User Story 4 - Inspect or forget a repository in the listing (Priority: P4)

A listing of repositories accumulates. Some entries the person no longer
recognises by name alone and wants to see the full path and when it was last
analysed. Others are finished with, and the disk space and clutter should go —
but only the analysis, never the code.

Each row carries an overflow menu holding exactly three things: Properties,
Open, and Remove. There is deliberately no re-analyse action, because opening a
repository already brings it up to date.

**Why this priority**: Housekeeping. Valuable, but the homepage is fully usable
without it, and it is the only part whose absence costs nothing but tidiness.

**Independent Test**: With at least two repositories listed, open a row's menu,
read its properties, and remove it; confirm the row disappears, its stored
analysis is gone, and the repository's own files are untouched.

**Acceptance Scenarios**:

1. **Given** a row in the listing, **When** the user opens its overflow menu,
   **Then** it offers Properties, Open and Remove, and offers no re-analyse
   action.
2. **Given** the overflow menu, **When** the user chooses Properties, **Then**
   the full path of the repository and when it was last analysed are shown.
3. **Given** the overflow menu, **When** the user chooses Remove, **Then** they
   must confirm an action that names the repository before anything is deleted.
4. **Given** a confirmed Remove, **When** it completes, **Then** the stored
   documentation, index and metadata for that repository are deleted, the row
   disappears from the listing, and every file in the analysed repository is
   byte-for-byte unchanged.
5. **Given** a Remove that the user declines to confirm, **When** they dismiss
   the confirmation, **Then** nothing is deleted and the row remains.

---

### Edge Cases

- **The path does not identify an analysable repository.** It does not exist, it
  names a file rather than a folder, the user has no permission to read it, or
  it is an empty folder with nothing to analyse. Each is refused before any work
  begins, with a message naming which of those is the problem.
- **The path is not a plain local folder path.** A path with spaces or
  non-ASCII characters, a trailing separator, a relative path, a path containing
  a parent-directory step, a network path, a symbolic link pointing outside
  itself, or a path long enough to strain the operating system. Each is either
  handled correctly or refused clearly; none may be silently mangled into a
  different location.
- **The path is somewhere the tool must not analyse into**, such as the tool's
  own state directory. Refused rather than allowed to nest analysis inside
  analysis.
- **A second analysis is requested while one is running.** Refused with a
  message naming the repository already being analysed; the running one is not
  disturbed and no second run starts.
- **A run is stopped by the user part-way through a stage.** It ends promptly in
  a cancelled state rather than running the current stage to completion first,
  and the partial work is discarded rather than left to surface later.
- **The browser is closed, or the machine sleeps, mid-run.** The run belongs to
  the hub, not to the tab. It continues, and reopening the homepage shows where
  it has got to.
- **The hub itself is stopped mid-run.** The partial work left behind must never
  surface as a repository in the listing on the next start, and the run whose
  record was never closed must be shown as interrupted rather than as still
  running.
- **The run record is missing, unreadable, or from an older version of the
  tool.** The homepage still works, showing no past runs rather than failing to
  load.
- **The listing is asked to read something it cannot.** One unreadable or
  damaged entry does not prevent the remaining repositories from being listed.
- **A repository is removed while it is open, or while it is being analysed.**
  The conflict is surfaced rather than half-performed.
- **A repository is opened whose stored analysis has been deleted from under the
  tool.** Reported clearly, with the option to analyse it fresh.
- **A repository is opened while no provider in a required chain is available.**
  The documentation exists and is complete, but serving it is refused because
  the server checks every chain before it starts. Reported as a provider
  problem naming the stage, not as a problem with the stored analysis.
- **A repository is opened whose source folder no longer exists.** The
  documentation is still readable; the fact that it can no longer be brought up
  to date is stated rather than hidden, and the row says so before it is opened.
- **A repository folder is moved or renamed.** The old row remains, marked
  unavailable, and analysing the new location produces a second, separate entry
  for the same code. This is accepted rather than solved.
- **A repository already in the listing is submitted to the index control
  again.** This performs a fresh full analysis and replaces the stored analysis
  for that repository, which is the deliberate escape hatch for an analysis that
  has become stale in a way that opening cannot repair.
- **Several repositories are opened at once**, until no free local port remains.
  Failure to start another server is reported, not silent.
- **A run switches automatically from one configured provider to the next**
  mid-stage. The switch is visible in the run display, not silent.
- **A stage runs for a very long time** — hours, on a large repository with a
  rate-limited provider. The display keeps advancing throughout; nothing about
  the elapsed duration causes the run to be presented as stalled or abandoned.

## Requirements *(mandatory)*

### Functional Requirements

#### The hub and its entry point

- **FR-001**: The system MUST provide a new command that starts a local hub
  serving the homepage, and MUST print the address to open.
- **FR-002**: Every command the tool offers today MUST behave exactly as it does
  now — same arguments, same output, same effects. The homepage is an additional
  entry point, not a replacement, and the command that serves a single
  repository MUST NOT change.
- **FR-003**: The hub MUST accept connections only from the local machine by
  default, and MUST require an explicit action by the user to do otherwise.
- **FR-004**: The hub MUST generate a fresh credential each time it starts, MUST
  NOT write that credential to disk, and MUST include it in the address it
  prints.
- **FR-005**: Every request that starts an analysis, opens a repository, or
  removes a stored analysis MUST be refused unless it carries the credential
  from FR-004.
- **FR-006**: The hub MUST refuse requests that claim to be addressed to a name
  other than the local names it is serving, so that a page on another origin
  cannot reach it by pointing a domain at this machine.
- **FR-007**: The hub MUST stop cleanly when asked, and MUST stop the
  per-repository servers it started as part of stopping.

#### Starting an analysis

- **FR-008**: The homepage MUST present a control for entering a repository path
  and a control for starting its analysis, both reachable and operable by
  keyboard alone.
- **FR-009**: The system MUST treat a submitted path as untrusted input and MUST
  validate it before any analysis work begins, confirming that it exists, is a
  directory, is readable, and is neither the tool's own state location nor
  contained within it.
- **FR-010**: A submitted path that fails validation MUST be refused with a
  message identifying what is wrong with it, and MUST NOT start a run.
- **FR-011**: An analysis started from the homepage MUST write only within the
  tool's own state location, and MUST NOT create, modify or delete any file
  inside the analysed repository.
- **FR-012**: The system MUST allow at most one analysis to be in progress at a
  time. A request to start another while one is running MUST be refused with a
  message naming the repository currently being analysed, and MUST NOT start,
  queue, cancel or disturb any run.
- **FR-012a**: The system MUST offer a visible control for stopping an analysis
  that is in progress. Stopping it MUST end the run in a terminal cancelled
  state, MUST discard its partial work exactly as a failure does, MUST state
  that no documentation was kept, and MUST leave the system ready to accept a
  new analysis.
- **FR-013**: Submitting a path that is already in the listing MUST perform a
  fresh full analysis that replaces the stored analysis for that repository.

#### Showing progress

- **FR-013a**: The progress display MUST appear on the homepage itself, in the
  area the index control occupies, with the analyse history still listed below
  it. The feature MUST NOT introduce a separate address for a run.
- **FR-014**: While a run is in progress the system MUST show every stage of the
  pipeline in the order it runs them, distinguishing stages that have finished,
  the stage currently running, and stages not yet reached.
- **FR-015**: For stages that process many items individually, the system MUST
  show how many items have finished out of how many there are, and MUST update
  that as each item finishes — progress MUST NOT only move when a stage changes.
- **FR-016**: Progress information reaching the homepage MUST NOT remove,
  reduce or reorder the progress information the existing terminal output
  already prints.
- **FR-017**: The run display MUST show when the system switches automatically
  from one configured provider to the next during a run, so no such switch is
  invisible to the person watching.
- **FR-018**: A run MUST continue if the browser showing it is closed, and
  reopening the homepage MUST show that run's current state rather than an empty
  display, an index control as though nothing were running, or a duplicate run.
- **FR-019**: The bringing-up-to-date that happens when a repository is opened
  MUST be shown with the same progress display as a fresh analysis.
- **FR-020**: When opening a repository requires no work to bring it up to date,
  no progress display MUST be shown at all, and the user MUST reach the
  documentation within 5 seconds of choosing to open it.

#### Ending a run

- **FR-021**: Every run MUST reach exactly one terminal state — succeeded,
  failed, or cancelled — and the display MUST NOT continue to present a run as
  in progress once the underlying work has stopped for any reason.
- **FR-022**: A failed run MUST name the stage at which it failed and describe
  the cause; when the cause is that no configured provider could be reached, the
  description MUST name the providers that were attempted.
- **FR-023**: A failed run MUST state explicitly that no documentation was kept
  from that run, so stages shown as completed are not mistaken for saved output.
- **FR-024**: A failed run MUST offer to start the same analysis again without
  the user re-entering the path.
- **FR-025**: The system MUST NOT modify the user's provider configuration in
  response to a failure; it may only report it.
- **FR-026**: After a run reaches a terminal state, the system MUST be ready to
  accept a new analysis. The outcome of the just-finished run MUST remain
  visible where the run was displayed until the user dismisses it or starts
  another analysis; it MUST NOT clear itself on a timer.
- **FR-026a**: The system MUST record every run that reaches a terminal state,
  holding the repository path, when the run started and ended, its outcome, and
  for a failure the stage that failed and the cause including every provider
  attempted. That record MUST survive the hub being stopped and started again.
- **FR-026b**: The homepage MUST make recorded run outcomes viewable, most
  recent first, without the user leaving the homepage.
- **FR-026c**: The run record MUST be held in local storage alongside the tool's
  existing state, MUST NOT introduce a separate service, broker or database
  server, MUST retain at least the 20 most recent runs, and MUST discard older
  ones automatically without the user having to clean up.
- **FR-026d**: A run whose record was never closed because the hub stopped while
  it was running MUST be shown as interrupted once the hub starts again, and
  MUST NOT be presented as still in progress or block a new analysis.
- **FR-026e**: A run record that is missing, unreadable, or written by an older
  version of the tool MUST NOT prevent the homepage from loading; the homepage
  MUST show no past runs rather than fail.
- **FR-027**: A successful run MUST offer to open the documentation it produced.

#### The analyse history

- **FR-028**: The homepage MUST list the repositories that have already been
  analysed, beneath the index control, ordered with the most recently analysed
  first.
- **FR-029**: The listing MUST be built from information the tool already
  persists about analysed repositories; the feature MUST NOT introduce a
  separate service, broker or database server to hold it.
- **FR-030**: The listing MUST exclude the residue of runs that did not
  complete, so an abandoned run never appears as a repository.
- **FR-031**: An entry that cannot be read MUST be skipped without preventing
  the remaining entries from being listed.
- **FR-031a**: A repository's path MUST be what identifies its entry. The system
  MUST NOT attempt to recognise that a repository has been moved or renamed;
  analysing it at its new location creates a separate entry.
- **FR-031b**: An entry whose repository folder no longer exists MUST remain in
  the listing, visibly marked as unavailable, and MUST remain openable and
  removable.
- **FR-032**: The listing MUST reflect a run that has just completed without the
  user having to reload the page manually.
- **FR-033**: Each row MUST offer an overflow menu containing exactly
  Properties, Open and Remove, and MUST NOT offer a re-analyse action.
- **FR-034**: Properties MUST show the repository's full path and when it was
  last analysed.
- **FR-035**: Open MUST start a server dedicated to that repository and take the
  user to that repository's documentation, without the user typing any command.
- **FR-036**: Opening a repository MUST bring its documentation up to date with
  the changes made since it was last analysed, reprocessing only what changed
  rather than re-analysing the whole repository.
- **FR-037**: More than one repository MUST be openable at the same time, each
  independent of the others; failure to start a further server MUST be reported
  rather than silent.
- **FR-038**: Open MUST report clearly, and offer to analyse the repository
  fresh, when the stored analysis for it is missing or unusable.
- **FR-038a**: Open MUST report clearly when the repository cannot be served
  because no provider in a required chain is available, naming the stage whose
  chain is unavailable. This is distinct from FR-038: the stored analysis is
  intact and the failure is external to it.
- **FR-039**: Open MUST still reach the stored documentation when the analysed
  repository's own folder no longer exists, and MUST say that it can no longer
  be brought up to date.
- **FR-040**: Remove MUST require an explicit confirmation that names the
  repository before anything is deleted.
- **FR-041**: A confirmed Remove MUST delete only the stored documentation,
  index and metadata for that repository, MUST leave every file in the analysed
  repository unchanged, and MUST remove the row from the listing.
- **FR-042**: Removing a repository that is currently open or currently being
  analysed MUST surface the conflict rather than perform the deletion partially.

#### Appearance

- **FR-043**: The homepage MUST use the same visual language as the generated
  documentation — the same colour and typography tokens, the same brand mark
  used according to its stated policy, and a browser tab icon.
- **FR-044**: The homepage MUST present correctly in both light and dark
  appearance, following the operating system's preference when the user has
  expressed none.
- **FR-044a**: The homepage MUST offer the same three-state appearance control
  the generated documentation offers — System, Light and Dark — with the current
  state identifiable without interacting with it, reachable by keyboard, and
  applied immediately on change without a reload.
- **FR-044b**: The homepage MUST remember the user's appearance choice on this
  machine and MUST apply it before the page first paints, so returning to the
  homepage never flashes the wrong appearance. That choice is the homepage's
  own and MUST NOT be expected to travel to or from any generated wiki.
- **FR-044c**: If the remembered choice cannot be stored or read, the homepage
  MUST fall back to the operating system's preference rather than failing.
- **FR-045**: This feature MUST NOT introduce any runtime network or server
  request into the generated documentation, which continues to be opened
  directly from the filesystem with nothing fetched.

### Key Entities

- **Hub session**: One running homepage server. Holds the credential generated
  for this run, the analysis currently in progress if any, and the
  per-repository servers it has started. Nothing about it survives its own
  process.
- **Analysis run**: One attempt to analyse one repository path. Has the path, an
  ordered set of stages, the stage currently running, item counts within that
  stage where the stage processes items, any provider switches observed, and
  exactly one terminal outcome — succeeded, failed with a stage and a cause, or
  cancelled by the user.
- **Run record**: What is kept about a run after it has ended — the repository
  path, when it started and ended, its outcome, and for a failure the stage and
  the cause including the providers attempted. Survives the hub. Bounded to a
  recent window and pruned automatically. Distinct from a history entry: a run
  record describes one attempt, including attempts that produced nothing, while
  a history entry describes a repository that currently has stored analysis.
- **Pipeline stage**: One named step of the analysis, in a fixed order shared
  with the existing terminal output. Some stages process a countable number of
  items; others do not.
- **History entry**: One repository that has been analysed, identified by its
  path. Has the repository's path, when it was last analysed, a reference to
  where its stored analysis lives, and whether that path still exists on this
  machine. Derived from what the tool already persists rather than separately
  recorded.
- **Repository server**: A server started by the hub for one repository, taking
  the user to that repository's documentation. Independent of every other one,
  and stopped when the hub stops.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person who has never used the command line for this tool can
  start analysing a repository within 60 seconds of the homepage opening,
  without typing any command.
- **SC-002**: During the stages that process items individually, the displayed
  count advances within 2 seconds of each item finishing, for at least 95% of
  items in a run.
- **SC-003**: 100% of runs reach a visible terminal state. Across a test set
  that includes success, provider failure, invalid input, user cancellation and
  the hub being interrupted, no run leaves the display presenting work as in
  progress after the underlying work has stopped.
- **SC-004**: For every failure mode exercised, the failure text names the stage
  that failed and, where a provider was the cause, every provider attempted —
  such that a person can name what to fix without opening a terminal or reading
  a log file.
- **SC-005**: Given a state store containing both completed analyses and the
  residue of at least three abandoned runs, the listing shows every completed
  repository and zero entries that do not correspond to one.
- **SC-006**: The homepage's listing is fully displayed within 2 seconds of the
  page opening, for a state store holding at least 20 analysed repositories.
- **SC-007**: A person can go from opening the homepage to reading a previously
  analysed repository's documentation using only pointer or keyboard input, with
  no command typed.
- **SC-008**: The existing command-line behaviour is unchanged: the full
  existing automated verification passes without modification, and the terminal
  output of an analysis is identical to what it produced before this feature.
- **SC-009**: A request that does not carry the credential printed when the hub
  started cannot start an analysis, open a repository, or remove a stored
  analysis — verified for every such operation.
- **SC-010**: Analysing, opening or removing a repository through the homepage
  leaves every file in that repository byte-for-byte unchanged, verified by
  comparing the repository's contents before and after.
- **SC-011**: A run whose longest stage takes at least 10 minutes shows a
  visible change in the display at least once per minute throughout that stage.
- **SC-013**: After a run ends and the hub is stopped and started again, that
  run's outcome — including the failing stage and providers attempted, where it
  failed — is still readable on the homepage, and no run is shown as still in
  progress.
- **SC-012**: The homepage is verified in a real browser, in both light and dark
  appearance, at both a narrow and a wide window, with zero horizontal page
  overflow and every piece of text at a contrast ratio of at least 4.5:1
  against its background in both appearances. Each of the three appearance
  states is reachable in one interaction from any of the others, and returning
  to the homepage in a chosen state shows no flash of the other appearance.

## Assumptions

- **One person, one machine.** The hub serves the person who started it on the
  machine it runs on. There is no notion of multiple accounts, roles or remote
  users, and none is introduced.
- **The homepage may rely on scripting and on talking to its own server.** It is
  served over the local loopback interface, unlike the generated documentation,
  which is opened from the filesystem and must continue to fetch nothing. That
  leniency applies to the homepage only and must not leak into generated output.
- **A current browser.** No support is planned for browsers that cannot maintain
  a live connection to a local server; the homepage is not required to be usable
  with scripting disabled.
- **The homepage carries its own appearance choice, not a shared one.** It
  offers the same three-state control the generated documentation gained in the
  previous feature (FR-044a), but the choice is the homepage's own: the homepage
  and each generated wiki are served from separate origins, and browsers keep
  their stored preferences apart, so no coordination between them is possible or
  attempted.
- **The history is derived, not recorded.** Repository paths and last-analysed
  times are already persisted per analysed repository, so the listing is a scan
  of what exists rather than a new file to keep in step. Whether that scan needs
  a cache in front of it is a performance question for planning, not a
  requirement here — SC-006 sets the bar it has to clear.
- **Opening a repository reuses the existing single-repository server exactly as
  it behaves today**, including the bringing-up-to-date it already performs on
  start. This feature makes that work visible; it does not change it.
- **Ports for per-repository servers are chosen automatically** from those free
  on the machine; the user is not asked to pick one.
- **The hub prints its address rather than opening a browser by itself.**
- **A run is owned by the hub process, but its outcome outlives it.** If the hub
  stops, its run stops and is not resumed across restarts — but what happened is
  recorded and still readable afterwards (FR-026a, FR-026d). Records are kept
  for a recent window rather than forever, and are pruned without asking.
- **The credential model matches the one the single-repository server already
  uses** — generated per run, never persisted, carried in the printed address.

## Out of Scope

- **Any provider switch or provider-chain editing.** Choosing between local and
  cloud engines, per stage or as one master toggle, is a separate later feature.
  This feature may report which providers were tried and that they failed; it
  may not change which providers are configured. The homepage must not be
  designed in a way that prevents that feature being added afterwards.
- **Changing what a failed run keeps.** That a late failure discards the whole
  run, including correct output from earlier stages, is existing deliberate
  behaviour. Making earlier output survive is a substantially larger change to
  how an analysis is committed and belongs in its own specification. This
  feature reports the loss honestly; it does not prevent it.
- **Re-hosting documentation inside the hub.** The hub links to per-repository
  servers; it does not serve documentation itself.
- **Queuing or parallelising analyses.** One at a time, refusing the second, is
  the decided behaviour.
- **A re-analyse action on a history row.** Deliberately omitted, because
  opening a repository already brings it up to date, and the index control
  already provides the full-rebuild escape hatch (FR-013).
- **Cleaning up the residue of previously abandoned runs.** The listing must not
  show it (FR-030); deleting it is not required by this feature.

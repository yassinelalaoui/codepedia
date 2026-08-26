# Feature Specification: CLI Packaging & Distribution

**Feature Branch**: `020-cli-packaging`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Construire le packaging permettant de distribuer l'outil sous une forme facilement installable pour un développeur ou une équipe technique, sans dépendance d'environnement complexe à mettre en place manuellement (ex. pas besoin d'installer manuellement un environnement de développement complet pour utiliser l'outil). Le packaging doit produire une forme d'installation autonome de l'outil en ligne de commande, et documenter clairement le prérequis externe restant à la charge de l'utilisateur (le moteur LLM local, ex. Ollama, à installer séparément) puisqu'il ne peut pas être embarqué dans le package. Critère de succès : un développeur sur une machine vierge (hors prérequis LLM local documenté) peut installer l'outil en une seule commande et exécuter la commande d'indexation avec succès."

## Overview

Package the existing `codepedia` CLI (019) so a developer or a technical
team can install it as a standalone command-line tool with a single command,
without first setting up the project's own development environment (cloning
the source repository, creating a build environment, installing the
project's source-level dependencies by hand). The one thing packaging
cannot provide — and must instead document clearly — is the local LLM
engine (for example Ollama) the CLI depends on for its AI-driven commands;
that remains an external prerequisite the user installs separately.

## Goals

- Produce a standalone, installable distribution of the CLI tool that a
  developer installs with exactly one command.
- Ensure that installing the tool never requires manually setting up the
  project's own development environment.
- Make every CLI command (`index`, `serve`, `config`, `scan`, from 019)
  directly runnable from a terminal immediately after install, with no
  further manual configuration.
- Clearly and separately document the one external prerequisite the
  packaging does not cover — the local LLM engine — including why it can't
  be embedded and what the user needs to do about it.
- Let a developer verify their install succeeded and go straight to running
  the indexing command against a real repository.

## Non-Goals

- Installing, bundling, or managing the local LLM engine (e.g. Ollama)
  itself; per the project's local-only/no-cloud-fallback principle, this
  remains an external prerequisite the developer installs and runs
  separately, unchanged from 019.
- Changing the CLI's existing commands, arguments, configuration, or
  error-messaging behavior (019); this feature only changes how the tool is
  obtained and installed.
- Distribution through OS-specific package managers (e.g. Homebrew, apt,
  Chocolatey); the single install command is the only distribution path
  this feature guarantees.
- An unattended, every-commit publishing pipeline; a maintainer must still
  deliberately push a version tag to produce a release. (Cross-platform
  *building* — as opposed to publishing — is delegated to CI; see
  research.md §8's superseding decision. This was added after the
  original non-goal was written, once local builds were found to be
  unusable on this project's own development machine.)
- Offline/air-gapped installation; a one-time network connection to fetch
  the package at install time is assumed to be available.
- Auto-updating the tool after install.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Installing on a clean machine with one command (Priority: P1)

As a developer who has never worked with this project's source code, I want
to install the CLI tool with a single command on a machine that has none of
the project's development tooling set up, so that I can start using it
without cloning the repository or configuring a development environment.

**Why this priority**: Without this, the tool is only usable by people
willing to clone the source and set up a full development environment,
which defeats the purpose of distributing it as a standalone tool.

**Independent Test**: Can be fully tested by taking a machine that has only
the tool's own documented minimal prerequisite present (no project source
checkout, no manually created build environment), running the single
install command, and confirming the CLI is runnable from the terminal
afterward.

**Acceptance Scenarios**:

1. **Given** a clean machine with only the CLI's documented minimal
   prerequisite present, **When** the developer runs the single documented
   install command, **Then** the CLI becomes runnable from the terminal
   without cloning the source repository, creating a build environment, or
   manually installing the project's own source-level dependencies.
2. **Given** the CLI was just installed, **When** the developer checks its
   version (e.g. a version flag/command), **Then** the tool reports a
   version, confirming a working install.
3. **Given** a machine that already has the tool installed, **When** the
   developer runs the same install command again for a newer version,
   **Then** the tool is updated to that version rather than the command
   failing or producing a broken duplicate install.

---

### User Story 2 - Running the indexing command right after install (Priority: P2)

As a developer who just installed the tool, I want to run the indexing
command against a repository right away, so that I can verify the install
actually works end to end.

**Why this priority**: Installing successfully is only valuable if the tool
actually works afterward; this is the concrete proof the packaging did its
job, and it is the project's own stated success criterion.

**Independent Test**: Can be fully tested by installing the tool on a clean
machine that already has the local LLM engine prerequisite installed and
running, then running the indexing command against a valid repository and
confirming it completes successfully.

**Acceptance Scenarios**:

1. **Given** a machine with the CLI freshly installed and the local LLM
   engine prerequisite already installed and running, **When** the
   developer runs the indexing command against a valid repository, **Then**
   it completes successfully with no additional packaging-related setup
   step required.
2. **Given** a machine with the CLI freshly installed but the local LLM
   engine prerequisite not installed or not running, **When** the developer
   runs the indexing command, **Then** the tool shows the same clear,
   actionable dependency-missing error already established in 019 —
   packaging does not suppress or alter it.

---

### User Story 3 - Understanding the one remaining external prerequisite (Priority: P3)

As a developer or technical team lead evaluating this tool, I want the
documentation to clearly state that a local LLM engine must be installed
separately and can't be bundled, so that I know exactly what else I need
before or after installing the CLI.

**Why this priority**: A developer who installs the CLI and then hits an
unexplained failure because they didn't know about the local LLM engine
requirement will conclude the tool is broken, not that a documented step
was skipped.

**Independent Test**: Can be fully tested by having a developer with no
prior exposure to the tool read only the install documentation and
correctly state, without guessing, which one dependency remains their
responsibility and which commands need it.

**Acceptance Scenarios**:

1. **Given** the tool's install documentation, **When** a developer new to
   the tool reads it, **Then** it explicitly names the local LLM engine
   (with an example such as Ollama) as an external prerequisite the package
   does not include, and explains why it can't be embedded.
2. **Given** the tool's install documentation, **When** a developer checks
   which commands need the local LLM engine, **Then** the documentation
   makes clear that some commands (e.g. `scan`) work without it while
   others (e.g. `index`, the AI-backed parts of `serve`) require it.

---

### User Story 4 - Consistent installs across a team (Priority: P4)

As a technical team lead, I want every team member to be able to install
the exact same tool version with the same single command, so that the whole
team runs a consistent version without each person following different
manual steps.

**Why this priority**: Useful for team adoption, but the tool is already
valuable to a single developer without this; lowest priority.

**Independent Test**: Can be fully tested by running the same documented
install command on two different clean machines and confirming both report
the same installed version.

**Acceptance Scenarios**:

1. **Given** two different clean machines each meeting the documented
   minimal prerequisite, **When** the same install command is run on both,
   **Then** both machines end up with the same installed CLI version,
   verifiable via the version check.

---

### Edge Cases

- What happens when the install command is run on a machine that doesn't
  even meet the tool's own minimal base prerequisite (e.g. no compatible
  runtime present at all)? The install fails with a clear message
  identifying the missing base prerequisite, rather than a cryptic
  low-level error.
- What happens when the indexing command is run right after install but
  before the local LLM engine prerequisite is installed? The existing 019
  availability-check error applies unchanged; packaging must not interfere
  with or suppress it.
- What happens when the install command is run again on a machine that
  already has the same version installed? The tool ends up installed and
  runnable, without erroring just because it's already present.
- What happens when a developer uninstalls the tool? A single documented
  command removes the installed CLI so it's no longer runnable from the
  terminal, while leaving any per-repository state or configuration the CLI
  previously wrote (per 019, under the user's home directory) untouched,
  since uninstalling the program is not the same as discarding the user's
  data.
- What happens when the install command is run without any network
  connectivity? It fails with a clear message indicating the package could
  not be fetched, rather than hanging or producing a misleading error.

## Requirements *(mandatory)*

### Functional Requirements

#### Packaging & distribution

- **FR-001**: The project MUST produce a distributable package of the CLI
  tool that a developer can install by running exactly one command.
- **FR-002**: The single install command MUST NOT require the developer to
  clone the project's source repository, manually create a build/development
  environment, or manually install the project's own source-level
  dependencies one by one.
- **FR-003**: The installed package MUST expose every existing CLI command
  (`index`, `serve`, `config`, `scan` — 019) as directly runnable from a
  terminal immediately after install, with no further manual configuration.
- **FR-004**: The distributed package MUST declare and document its own
  minimal prerequisite(s) (e.g. a compatible base runtime), kept clearly
  distinct from the local LLM engine prerequisite, so a developer knows
  what must already be present on a machine before running the install
  command.
- **FR-005**: Running the install command again on a machine that already
  has the tool installed MUST result in that version being installed
  (updating it if it differs), rather than failing or producing a broken
  duplicate install.
- **FR-006**: The installed tool MUST provide a way to check its currently
  installed version, so an install can be verified as successful without
  consulting source code.
- **FR-007**: The project MUST provide a single documented command to
  uninstall the tool, after which none of its commands remain runnable from
  the terminal.

#### Documenting the external local-model prerequisite

- **FR-008**: The documentation MUST clearly and separately identify the
  local LLM engine (e.g. Ollama) as an external prerequisite that the
  packaging does not and cannot install, distinct from the CLI tool itself.
- **FR-009**: The documentation MUST explain, in language a developer new
  to the tool can act on, where to obtain and how to start the local LLM
  engine prerequisite before using the CLI's AI-dependent commands.
- **FR-010**: The documentation MUST state which commands work without the
  local LLM engine prerequisite and which require it, consistent with the
  availability checks already established in 019.

#### Post-install behavior

- **FR-011**: Running the indexing command immediately after a fresh
  install, against a valid repository, with the local LLM engine
  prerequisite already installed and running, MUST succeed without any
  packaging-related additional setup step.
- **FR-012**: Packaging changes MUST NOT alter the CLI's existing commands,
  arguments, configuration, or error-messaging behavior established in 019;
  this feature only changes how the tool is obtained and installed.

### Key Entities

- **DistributionPackage**: The installable artifact this feature produces —
  what a developer's single install command fetches and installs; carries a
  version and the CLI's own code plus its declared dependencies.
- **InstallPrerequisite**: A precondition that must already be satisfied on
  the target machine — either the package's own minimal base prerequisite
  (covered by this feature's documentation) or the external local LLM
  engine (documented but never installed by this feature).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a machine with no prior project-specific setup other than
  the documented local LLM engine already installed and running, a
  developer can install the CLI tool by running exactly one command and
  then successfully complete an indexing run against a valid repository.
- **SC-002**: Installing the tool never requires a manual step involving
  the project's source repository or a hand-built development environment.
- **SC-003**: A developer can confirm their install succeeded (via a
  version check) in under a minute of finishing the install command.
- **SC-004**: A developer reading only the install documentation for the
  first time can correctly state, without guessing, which one external
  dependency (the local LLM engine) remains their responsibility.
- **SC-005**: Re-running the install command to upgrade an existing install
  always results in exactly one working, current version installed — never
  a duplicate or conflicting install.
- **SC-006**: Running the documented uninstall command always leaves the
  CLI no longer runnable from the terminal.

## Assumptions

- This feature reuses the CLI's already-established implementation
  language/runtime (019); the exact packaging mechanism and distribution
  channel are implementation details left to planning, as long as they
  satisfy the single-command, no-manual-dev-environment requirement.
- "Standalone install" means the single command handles fetching and
  installing all of the CLI's own code and its own dependencies
  automatically; it does not require the machine to already have the
  project's dependencies pre-installed. Having a compatible base runtime
  already present is treated as the one documented minimal prerequisite,
  which is far lighter than "a full development environment" and is itself
  covered by the install documentation.
- The local LLM engine (e.g. Ollama) prerequisite is unchanged from 019 and
  remains the developer's responsibility to install and run separately,
  consistent with the project's local-only, no-cloud-fallback principle;
  packaging must not attempt to silently install or manage it.
- The one-time network access needed to fetch the package at install time
  does not conflict with the project's local-only-at-runtime principles,
  which govern the tool's operation after install, not how it is obtained.
- Per-repository state and configuration the CLI writes (019, under the
  user's home directory) is left untouched by installing or uninstalling
  the tool itself.
- Team-wide consistent installs (User Story 4) are satisfied by the same
  single command installing the same published version on each machine;
  enforcing an organization-wide pinned-version policy is out of scope.
- "Local LLM engine," used throughout this spec, refers to the same thing
  019's spec calls the "local LLM service" / "local model" (e.g. Ollama) —
  one concept, two names across the two features; not a different
  dependency.

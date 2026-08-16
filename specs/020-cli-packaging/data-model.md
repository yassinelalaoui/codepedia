# Data Model: CLI Packaging & Distribution

This feature introduces no new persisted runtime data — it changes how the
already-existing `repo-scanner` CLI (019) is built and obtained, not what
it stores while running. The entities below (from spec.md's Key Entities)
are conceptual: they describe the shape of the release/install process
itself, not database rows.

## DistributionPackage

The installable artifact this feature produces — what a developer's
single install command fetches and installs.

| Field | Type | Notes |
| --- | --- | --- |
| `version` | string | The `repo-scanner` version being released; matches `pyproject.toml`'s `[project].version` (research.md §4) — the single source of truth `--version` reads at runtime via `importlib.metadata`. |
| `targetOs` | enum: `windows` \| `macos` \| `linux` | One binary per OS (research.md §8/§9); PyInstaller does not cross-compile. |
| `targetArch` | enum: `x86_64` | Fixed for this feature's scope (research.md §9). |
| `binaryPath` | string | The single executable file produced by `packaging/build.py` (`dist/repo-scanner` or `dist/repo-scanner.exe`). |
| `releaseUrl` | string | The GitHub Release asset URL an install script downloads from (research.md §7). |

Lifecycle: built manually by a maintainer per OS (`packaging/build.py`,
research.md §8) → uploaded as a GitHub Release asset alongside
`install.sh`/`install.ps1` → downloaded and installed by a developer's
one-line install command (research.md §5). There is no update/delete of an
existing `DistributionPackage`; a new version is a new release with new
assets.

## InstallPrerequisite

A precondition that must already be satisfied on the target machine before
a command succeeds. Two kinds exist, and this feature's core job is to keep
them clearly distinct (FR-004, FR-008-FR-010).

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | enum: `packageBaseline` \| `localLlmEngine` | Which of the two kinds this is. |
| `coveredByThisFeature` | boolean | `true` for `packageBaseline` (the install script/binary itself satisfies it); always `false` for `localLlmEngine` (spec Non-Goals — never installed or managed by this feature). |
| `description` | string | Human-readable statement of what's required, shown in install documentation (FR-008/FR-009). |
| `affectedCommands` | list of `CLICommand` (019) | Which of `index`/`serve`/`config`/`scan` need this prerequisite — used to satisfy FR-010 ("which commands work without it"). |

Concrete instances:

- `packageBaseline`: "A supported OS (Windows/macOS/Linux, x86_64)" —
  satisfied automatically by running the matching standalone binary;
  affects all commands equally (all of them run inside the same binary).
- `localLlmEngine`: "A local LLM/embedding engine (e.g. Ollama) installed
  and reachable" — never satisfied by this feature (research.md §1, spec
  Non-Goals); affects `index` and the AI-backed parts of `serve` (per
  019's existing `check_ai_dependencies`), does **not** affect `scan` or
  `config --show`.

## Relationship to existing 019 entities

Neither `DistributionPackage` nor `InstallPrerequisite` is read or written
by any of 019's existing entities (`CLICommand`, `CLIConfiguration`,
`PipelineRun`, `LocalModelAvailability`) at runtime — the relationship is
purely temporal: a `DistributionPackage` exists and is installed *before*
any `CLICommand` from 019 can run, and `InstallPrerequisite.localLlmEngine`
is exactly the same condition 019's `LocalModelAvailability` already checks
at runtime; this feature does not duplicate that check, only documents the
prerequisite it is checking (research.md §1).

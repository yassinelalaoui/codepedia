# Implementation Plan: CLI Packaging & Distribution

**Branch**: `020-cli-packaging` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-cli-packaging/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Produce a standalone, single-file `codepedia` executable per supported OS
(Windows/macOS/Linux) via PyInstaller — the Python-ecosystem equivalent of
the `pkg`/`Nexe` standalone-binary approach named in this plan's input,
since those two tools are Node.js-only and this project's CLI (019) is
already Python (research.md §1). Each binary is published as a GitHub
Release asset of this repository (research.md §7), built manually by a
maintainer (research.md §8, per spec's explicit non-goal excluding an
automated release pipeline) and installed with one platform-specific
one-line command (`curl | sh` on macOS/Linux, `irm | iex` on Windows,
research.md §5) that downloads the correct binary to a user-writable
location and puts it on `PATH` — no Python interpreter, virtual
environment, or source checkout required on the target machine. Adds a
`--version` flag to `cli.main.app` (FR-006, research.md §4) and fixes a
latent package-data gap (`doc_generator`'s Jinja templates and static
assets were never declared as package data, so only editable installs that
read the source tree directly happened to work — research.md §3) so the
binary — and any future built wheel — actually contains what `index` needs
at runtime. Documents the local LLM engine (Ollama) as the one remaining,
separately-installed external prerequisite. Packaging a VS Code extension
(this plan's other named option) is rejected — it contradicts 019's
explicit non-goal that this is a terminal-only CLI, and this feature's own
FR-003 requiring commands "directly runnable from a terminal" (research.md
§1).

## Technical Context

**Language/Version**: Python 3.11 (unchanged from 019; packaging wraps the
existing interpreter/codebase, it does not change the implementation
language)

**Primary Dependencies**: **PyInstaller** (new, build-time only — never a
runtime dependency of the shipped binary, since PyInstaller bundles the
interpreter itself; research.md §2), added as an optional `build` dependency
group in `pyproject.toml`. No new *runtime* dependency: the binary bundles
the same `typer`/`fastapi`/`uvicorn`/`tree-sitter*`/etc. already declared
for 001-019. The install scripts (`install.sh`/`install.ps1`) use only
tools already present on their target OS (`curl`/`tar` on macOS/Linux,
`Invoke-WebRequest`/`Expand-Archive` on Windows) — no new dependency there
either.

**Storage**: N/A for the feature's own behavior. The install scripts write
exactly one file to a fixed, user-writable location (`~/.local/bin/
codepedia` on macOS/Linux, `%LOCALAPPDATA%\codepedia\codepedia.exe`
on Windows — research.md §5); no other runtime state is introduced.
Per-repository state and configuration remain exactly as 019 defined them
(`~/.codepedia/`), unaffected by how the CLI itself was installed.

**Testing**: `pytest` is unaffected (no CLI *behavior* changes except the
new `--version` flag, which gets a normal unit/contract test). Verifying
the standalone binary itself (that a real, dependency-free machine can run
it) is a manual/maintainer-run smoke test documented in `quickstart.md`,
not a `pytest` test — building and executing a frozen binary as part of the
existing automated suite would require a PyInstaller build step in every
test run, which is disproportionate to what this feature needs to prove
(research.md §4 notes the same reasoning for why `--version` itself is
still unit-tested normally).

**Target Platform**: Windows, macOS, Linux — now also the set of target
platforms for a *compiled, distributed artifact*, not just where the dev
suite runs. PyInstaller does not cross-compile, so one binary must be built
on a machine of each target OS (research.md §8); this plan assumes x86_64
only for all three (research.md §9).

**Project Type**: Adds a packaging/release layer on top of the existing
single Python project — no new importable source package. Touches
`pyproject.toml` (package-data fix + new optional `build` dependency
group), adds a `packaging/` directory (PyInstaller spec file + install
scripts + a maintainer build helper), and one small source change
(`--version` in `src/cli/main.py`).

**Performance Goals**: No new functional performance target — this feature
does not change what any command computes. Soft goal: PyInstaller's
one-file bootstrap (which unpacks to a temp directory on each run) should
not make `codepedia --version`/`scan` feel unresponsive; kept as a
documented expectation, not a numeric spec requirement, since the spec
itself sets no performance criterion for packaging.

**Constraints**: The binary MUST run on a target machine with no
pre-existing Python installation (FR-002's core "standalone" guarantee);
MUST NOT require network access at runtime, only once at install time
(spec Non-Goals/Assumptions); MUST bundle `doc_generator`'s templates/
assets and every `tree-sitter-*` grammar already declared as a runtime
dependency, since PyInstaller only bundles what static analysis detects
unless explicitly declared (research.md §3) — a missing file here would
surface as an `index` failure, not an install failure, which is worse for
SC-001.

**Scale/Scope**: One binary build per supported OS per released version (3
build targets: Windows, macOS, Linux, all x86_64 — research.md §9); no
OS-specific package-manager integration and no automated release pipeline
(spec Non-Goals); this feature does not need to support multiple installed
versions side by side on the same machine.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
| --- | --- | --- |
| 2.1 Confidentialité absolue | The binary bundles and runs the same already-local components as 019; it makes no network call of its own at runtime. The install script's one-time download happens before the tool ever touches a repository, and fetches only the tool's own binary, never code/summaries/embeddings | PASS |
| 2.2 Zero exposition réseau | Unaffected — packaging does not change how `index`/`serve` bind their web server (019, unchanged by FR-012) | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | Unaffected — availability checks (019) are untouched; packaging only changes how the already-built CLI is obtained | PASS |
| 2.4 Traçabilité des réponses IA | Unaffected — no change to summary/chat citation behavior | PASS |
| 2.5 Ré-indexation incrémentale | Unaffected — no change to the watcher/incremental pipeline (017/018) | PASS |
| 2.6 Infrastructure minimale et stockage local | This principle governs the tool's own *runtime* storage/infrastructure (embedded SQLite + local file-based vector index, no external DB/broker/cloud component while `codepedia` is running) — unaffected here. GitHub Releases (research.md §7) is used only as a one-time, install-time distribution channel, not as infrastructure the running tool depends on; the install scripts write exactly one local file and the build process is a manual, maintainer-run script (research.md §8), adding no new hosted runtime infrastructure | PASS |
| 2.7 Dépôt analysé en lecture seule | Unaffected — the binary writes to the same `~/.codepedia/` location 019 established, never to the analyzed repository | PASS |

No violations identified; Complexity Tracking is not needed for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/020-cli-packaging/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
packaging/                             # New directory for this feature
├── pyinstaller/
│   └── codepedia.spec              # PyInstaller build spec: entry point
│                                      # (cli.main:app), hidden imports for every
│                                      # tree-sitter-* grammar, data files for
│                                      # doc_generator/templates and
│                                      # doc_generator/assets, copy_metadata
│                                      # ("codepedia") so --version works in
│                                      # the frozen binary (research.md §2-4)
├── build.py                           # Maintainer-run helper: invokes PyInstaller
│                                      # for the current OS, verifies the produced
│                                      # binary runs `--version`/`scan` against a
│                                      # throwaway repo before declaring success
│                                      # (research.md §8)
├── install.sh                         # POSIX one-line installer: detects OS/arch,
│                                      # downloads the matching asset from the
│                                      # latest GitHub Release, installs to
│                                      # ~/.local/bin/codepedia, adds it to PATH
│                                      # if missing (research.md §5)
└── install.ps1                        # Windows installer: same, installs to
                                       # %LOCALAPPDATA%\codepedia\codepedia.exe
                                       # and updates the user PATH via the registry
                                       # (research.md §5)

src/cli/main.py                        # + --version flag / version callback,
                                       # reading importlib.metadata.version(
                                       # "codepedia") (FR-006, research.md §4)

pyproject.toml                         # + [tool.setuptools.package-data] for
                                       # doc_generator (templates/*.jinja,
                                       # assets/*) - fixes the latent gap where
                                       # only editable installs happened to work
                                       # (research.md §3); + optional "build"
                                       # dependency group: pyinstaller>=6.0

README.md                              # + install section documenting the
                                       # one-line install commands, the
                                       # package's own baseline OS/arch
                                       # prerequisite (FR-004), the
                                       # separately-installed local LLM engine
                                       # prerequisite (FR-008/009/010), and
                                       # the single uninstall command (FR-007)

docs/architecture.md                   # + note on the standalone-binary
                                       # distribution path (020) alongside
                                       # 019's existing pip-install
                                       # contributor path

docs/stack.md                          # + PyInstaller as a new build-time-only
                                       # tool, with rationale (research.md §2)

docs/diagrams/use-case-diagram.md      # + "Check installed version"
                                       # (ucCheckVersion) use case

.gitignore                             # + dist/ and build/ (PyInstaller's
                                       # output directories - not previously
                                       # ignored)

tests/
├── unit/
│   └── test_cli.py                    # + test for the new --version flag
└── contract/
    └── test_cli_interface.py          # + --version output format assertion
```

**Structure Decision**: Single project layout, unchanged from every prior
feature. This is a packaging/release feature, not a new source package: it
adds one new top-level `packaging/` directory holding the PyInstaller spec,
the maintainer build helper, and the two OS install scripts (none of it
importable Python package code, so it lives outside `src/`, mirroring how
`specs/` and `.specify/` already sit outside `src/` for non-package
concerns). The only `src/` change is the new `--version` flag on the
existing `cli` package (019) — no new package, no change to `index`/
`serve`/`config`/`scan`'s behavior (FR-012). `doc_generator`'s directory
layout is unchanged; only its `pyproject.toml` package-data declaration is
added. `docs/architecture.md`, `docs/stack.md`, `docs/diagrams/
use-case-diagram.md`, and `.gitignore` all get small, focused updates
alongside the implementation, per this project's standing convention of
keeping those documents current with every feature.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is not applicable.

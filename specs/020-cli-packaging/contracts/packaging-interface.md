# Contract: Packaging & Distribution Interface

## Purpose

Define the external interface this feature adds: how a developer obtains
and installs `repo-scanner` (the single command from spec SC-001), how a
release's assets are named and shaped, and the one new CLI surface change
(`--version`, FR-006). This does not redefine `index`/`serve`/`config`/
`scan`, which stay exactly as `specs/019-cli-orchestrator/contracts/
cli-interface.md` already documents (FR-012).

## Install command: `curl -fsSL <release-url>/install.sh | sh` (macOS/Linux)

**Inputs**: none required. Reads the calling machine's OS/arch to select
the matching release asset.

**Expected behavior**:

- Resolves the **latest** GitHub Release of this repository.
- Downloads the release asset matching the running OS/arch (research.md
  §9: `x86_64` only for now).
- Installs the binary to `~/.local/bin/repo-scanner`, overwriting any
  existing file at that path (this is also how an upgrade happens —
  research.md §6).
- If `~/.local/bin` is not already on `PATH`, appends it to the current
  user's shell profile and prints what was changed.
- Prints a final confirmation line naming the installed version and the
  command to verify it (`repo-scanner --version`).

**Exit behavior**:

- `0`: binary installed (or upgraded) successfully.
- non-zero: no network access, no release asset matching the running
  OS/arch, or the download/write failed — each with a distinct, actionable
  message (no silent partial install).

## Install command: `irm <release-url>/install.ps1 | iex` (Windows)

Same contract as `install.sh` above, targeting Windows/x86_64 specifically:

- Installs to `%LOCALAPPDATA%\repo-scanner\repo-scanner.exe`.
- If that directory is not already on the user `Path`, adds it via the
  registry (equivalent of `setx PATH`) and prints what was changed.
- Same exit-behavior contract as `install.sh`.

## Uninstall (documented OS command, not a new CLI subcommand — research.md §6)

- macOS/Linux: `rm ~/.local/bin/repo-scanner`
- Windows: `Remove-Item "$env:LOCALAPPDATA\repo-scanner\repo-scanner.exe"`

**Expected behavior**: after either command, `repo-scanner` is no longer
found on `PATH` (SC-006). Any `~/.repo-scanner/` per-repository state
(019) is left untouched (spec Assumptions).

## Release asset naming

Each GitHub Release publishes exactly these assets, so `install.sh`/
`install.ps1` can resolve a match deterministically:

| Asset filename | Contents |
| --- | --- |
| `repo-scanner-<version>-windows-x86_64.exe` | Windows standalone binary |
| `repo-scanner-<version>-macos-x86_64` | macOS standalone binary |
| `repo-scanner-<version>-linux-x86_64` | Linux standalone binary |
| `install.sh` | POSIX install script (same for macOS/Linux) |
| `install.ps1` | Windows install script |

## Command: `repo-scanner --version`

**Inputs**: none (eager flag; short-circuits before any subcommand runs).

**Expected behavior**: prints the installed `repo-scanner` version (read
via `importlib.metadata.version("repo-scanner")`, research.md §4) and
exits — works identically whether installed via the standalone binary or
via `pip install -e .` (019's existing contributor path).

**Exit behavior**:

- `0`: version printed.

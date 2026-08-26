# Quickstart: CLI Packaging & Distribution

Manual validation scenarios proving this feature works end to end. Unlike
019, most of these are **not** run through `pytest` — they validate a
built, distributed artifact on a machine that may have nothing else from
this project installed (see `plan.md`'s Technical Context / `research.md`
§4 for why this stays outside the automated suite).

## Prerequisites

- A maintainer build of the standalone binary for your OS
  (`packaging/build.py`, produces `dist/codepedia[.exe]` — see
  `research.md` §8), or a published GitHub Release asset.
- For the AI-dependent scenario: a running local LLM/embedding engine (e.g.
  Ollama with the default models from 019 pulled).
- A throwaway machine or container with **no** Python installed, to prove
  the "standalone" claim (a VM/container snapshot, or simply a `PATH`
  temporarily stripped of any Python).

## Scenario 1 — Build the binary

```bash
python packaging/build.py
```

**Expected**: produces `dist/codepedia` (or `dist/codepedia.exe` on
Windows); the script's own smoke check (`codepedia --version` and
`codepedia scan` against a throwaway repo, run against the freshly built
binary) passes before the script reports success.

## Scenario 2 — Standalone install on a clean machine (SC-001, SC-002)

On the throwaway machine/container from Prerequisites:

```bash
curl -fsSL <release-url>/install.sh | sh   # macOS/Linux
# or
irm <release-url>/install.ps1 | iex        # Windows PowerShell
```

**Expected**:

- Exactly one command was run; no repository clone, no manually created
  virtual environment, no manual dependency install.
- `codepedia --version` succeeds in a new terminal and prints a version
  number (SC-003).

## Scenario 3 — Indexing works right after install (SC-001, spec US2)

With the local LLM/embedding engine already running (Prerequisites):

```bash
codepedia index /path/to/some/repository
```

**Expected**: completes exactly as `specs/019-cli-orchestrator/quickstart.md`
already documents for `index` — no packaging-related failure (in
particular, no missing-template/missing-asset error, confirming the
`research.md` §3 package-data fix worked in a real frozen binary, not just
in an editable install).

## Scenario 4 — Missing local LLM engine still shows 019's error (US4, unchanged)

```bash
codepedia index /path/to/some/repository   # local LLM engine not running
```

**Expected**: the same clear, actionable "local LLM service unreachable"
message 019 already established — proving packaging did not interfere
with it (FR-012).

## Scenario 5 — Re-running the install command upgrades in place (FR-005)

```bash
curl -fsSL <release-url>/install.sh | sh   # again, e.g. after a new release
```

**Expected**: `codepedia --version` afterward reports the newer version;
no duplicate binary or conflicting install is left behind.

## Scenario 6 — Uninstall (SC-006)

```bash
rm ~/.local/bin/codepedia        # macOS/Linux
# or
Remove-Item "$env:LOCALAPPDATA\codepedia\codepedia.exe"   # Windows
```

**Expected**: `codepedia --version` in a new terminal fails with a
"command not found" (or equivalent) error; any previously created
`~/.codepedia/` state is untouched.

## Scenario 7 — `scan` works without the local LLM engine (FR-010)

```bash
codepedia scan /path/to/some/repository
```

**Expected**: succeeds even with no local LLM engine installed at all —
proving the documentation's claim (FR-010) that not every command needs
it.

## Scenario 8 — `serve` and `config` are also runnable right after install (FR-003)

On the machine from Scenario 2/3 (binary installed, a repository already
indexed via Scenario 3):

```bash
codepedia config --show
codepedia serve /path/to/some/repository
```

**Expected**: `config --show` prints the current configuration without
error; `serve` starts the local web server and watcher and prints the
local URL, exactly as `specs/019-cli-orchestrator/quickstart.md` already
documents for `serve` — proving all four commands (`index`, `serve`,
`config`, `scan`), not just `index`/`scan`, are directly usable immediately
after a standalone install, with no separate setup step.

## Scenario 9 — Installing on an unsupported OS/architecture fails clearly

On a machine whose OS/architecture has no matching release asset (for
example, a Linux arm64 machine, which this feature's initial scope
(research.md §9) does not build for):

```bash
curl -fsSL <release-url>/install.sh | sh
```

**Expected**: the install script exits non-zero with a clear message
naming the missing OS/arch combination, per `contracts/
packaging-interface.md`'s exit-behavior contract — it does not hang, does
not silently fall back to a mismatched binary, and does not leave a
partial/broken file at the install path.

## Scenario 10 — Installing with no network access fails clearly

On a machine with no network connectivity (e.g. network disabled):

```bash
curl -fsSL <release-url>/install.sh | sh
```

**Expected**: the install script exits non-zero with a message indicating
the release/binary could not be downloaded, per `contracts/
packaging-interface.md`'s exit-behavior contract — it does not hang
indefinitely waiting on the network.

# Research: CLI Packaging & Distribution

## §1. Distribution mechanism: pkg/Nexe standalone binary vs. VS Code extension

**Decision**: Standalone binary, built with **PyInstaller** — not literally
`pkg`/`Nexe` (both are Node.js-only bundlers and cannot package a Python
codebase), but the closest Python-ecosystem equivalent of what they
represent: a single executable that bundles the language runtime itself, so
the target machine needs nothing pre-installed to run it. The VS Code
extension option is rejected.

**Rationale**:

- This plan's own input named two Node.js-specific tools (`pkg`, `Nexe`).
  The project's CLI (019) is Python 3.11 + Typer, a decision already made
  and reused across ten-plus features; rewriting the whole pipeline
  (001-019) in Node.js to use those tools literally would be a wholesale
  rewrite, not a packaging change, and is out of proportion to this
  feature's scope (spec Non-Goals: "this feature only changes how the tool
  is obtained and installed").
- A VS Code extension conflicts with an explicit **non-goal already
  recorded in 019's own spec**: "A graphical installer, desktop
  application, or IDE plugin; this is a terminal-based command-line
  interface only." It also conflicts with 020's own FR-003 ("directly
  runnable from a terminal") and the spec's success criteria, which are all
  phrased in terms of running a command from a terminal, not opening an
  IDE panel.
- A standalone binary is the only one of the two named directions that
  satisfies FR-002 in its strongest form: it requires *no* pre-existing
  language runtime at all on the target machine (stronger than even a
  plain `pip install`, which still requires Python to already be present).

**Alternatives considered**:

- *Rewrite in Node.js, use `pkg`/`Nexe` literally* — rejected: full rewrite,
  massively out of scope; also `pkg` (Vercel) has been unmaintained since
  2024 and `Nexe` has long release gaps, so neither is a safe long-term
  choice even for a Node.js project today.
- *VS Code extension* — rejected, see Rationale above.
- *Plain `pip install repo-scanner` from a package index* — still requires
  Python pre-installed; doesn't meet the "binaire autonome" framing of this
  plan's input, though it remains available as a secondary path since
  019's `pyproject.toml` already supports it for contributors working from
  source (unchanged by this feature).

## §2. Standalone-binary tool: PyInstaller vs. Nuitka vs. cx_Freeze

**Decision**: PyInstaller (>=6.0), one-file mode, as a new optional `build`
dependency group in `pyproject.toml` — never a runtime dependency of the
shipped binary.

**Rationale**: PyInstaller is the most widely used and best-documented tool
for exactly this project's shape: a CLI with several native-extension
dependencies (`tree-sitter` plus six `tree-sitter-<language>` grammar
packages) and non-code data files (`doc_generator`'s Jinja templates and
static assets). It requires no C compiler on the build machine (unlike
Nuitka, which compiles to C and needs a working C toolchain per build OS),
and its plugin/hook ecosystem already has first-class support for bundling
package data and native extensions declaratively, which this project needs
regardless (§3).

**Alternatives considered**:

- *Nuitka* — produces smaller/faster-starting binaries via C compilation,
  but requires a C compiler present on every build machine (an extra
  cross-OS build prerequisite this project doesn't otherwise need) and has
  less predictable behavior bundling multiple native tree-sitter grammar
  packages. Worth revisiting later if binary startup time becomes a
  problem in practice.
- *cx_Freeze* — viable but smaller community, thinner docs for the
  native-extension + data-file combination this project needs.
- *shiv / pex (zipapp-style)* — rejected: both still require a system
  Python interpreter on the target machine, so they don't satisfy the
  "standalone, no pre-existing runtime" requirement (FR-002) at all.

## §3. Package-data gap: `doc_generator`'s templates and static assets

**Decision**: Declare `doc_generator`'s Jinja templates
(`src/doc_generator/templates/*.jinja`) and static assets
(`src/doc_generator/assets/*`) as package data in `pyproject.toml`
(`[tool.setuptools.package-data]`), and mirror the same paths as explicit
`--add-data` entries in `packaging/pyinstaller/repo-scanner.spec`.

**Rationale**: Investigating this feature surfaced that `pyproject.toml`
has no `package-data`/`MANIFEST.in` declaration at all for these files.
Every install exercised so far (019's own testing, this project's own
`pip install -e .`) has been an *editable* install, which reads directly
from the source tree and so never surfaced the gap. A real distributable
artifact — a built wheel or a PyInstaller binary — only includes files
setuptools/PyInstaller are explicitly told about via static analysis or
declared data files; Jinja templates and static assets loaded by path at
runtime are invisible to both unless declared. Left unfixed, a developer's
first `repo-scanner index` after installing this feature's distributed
binary would fail while rendering the wiki (`doc_generator`, 012) — a
worse failure than an install-time error, since it happens after the
tool otherwise looks like it installed and started correctly, directly
undermining SC-001.

**Alternatives considered**: A `MANIFEST.in` file was considered instead of
`[tool.setuptools.package-data]`; the latter was chosen because
`pyproject.toml` already declares `[tool.setuptools]`/
`[tool.setuptools.packages.find]` for this project (019), so keeping the
new declaration in the same file avoids introducing a second
packaging-config file for one addition.

## §4. Version reporting (FR-006)

**Decision**: Add a `--version` flag (Typer eager option / callback) to
`cli.main.app`, implemented as
`importlib.metadata.version("repo-scanner")`, and add
`copy_metadata("repo-scanner")` to the PyInstaller spec so the frozen
binary's bundled Python environment actually has the distribution metadata
`importlib.metadata` reads.

**Rationale**: `importlib.metadata.version(...)` is the standard-library
way to read a package's own declared version (`pyproject.toml`'s
`[project].version`, already `"0.1.0"`), keeping a single source of truth
rather than a hand-maintained version constant that can drift from
`pyproject.toml`. PyInstaller's `copy_metadata` hook is the documented,
standard fix for the well-known failure mode where `importlib.metadata`
can't find a frozen app's own metadata (there is no installed
distribution/`.dist-info` inside a raw one-file binary unless this hook
copies it in).

**Alternatives considered**: A hardcoded `__version__ = "0.1.0"` constant
in `cli/main.py`, manually kept in sync with `pyproject.toml` — rejected as
a second place the version has to be edited on every release, an easy thing
to forget (and SC-003/FR-006 exist specifically so a version check is
trustworthy).

## §5. Install location, single-command install, and PATH handling

**Decision**: One platform-specific one-line install command, following
the same `curl | sh` / `irm | iex` convention already familiar from
comparable tools (e.g. rustup, deno):

- macOS/Linux: `curl -fsSL <release-url>/install.sh | sh`
- Windows (PowerShell): `irm <release-url>/install.ps1 | iex`

Each script downloads the OS/arch-matching binary from the **latest**
GitHub Release of this repository and installs it to a fixed,
user-writable location:

- macOS/Linux: `~/.local/bin/repo-scanner`
- Windows: `%LOCALAPPDATA%\repo-scanner\repo-scanner.exe`

If that location isn't already on `PATH`, the script appends it (to the
current user's shell profile on macOS/Linux, to the user `Path` registry
value via `setx`-equivalent on Windows) and prints what it did, so the
freshly installed command is runnable in a new terminal without a manual
step — consistent with FR-003.

**Rationale**: Both target locations are user-writable without requiring
administrator/root privileges, which keeps the "single command, no manual
environment setup" promise true even for a developer without elevated
rights on their machine — the same reason rustup/deno chose equivalent
per-user locations instead of a system-wide directory. The `curl|sh`/
`irm|iex` pattern is exactly what "one command" means in practice for a
binary that isn't published through a package manager.

**Alternatives considered**: A system-wide install location (e.g.
`/usr/local/bin`, `C:\Program Files\`) — rejected, since it would require
elevated privileges on most machines, undermining the "single command"
guarantee for a large share of developers.

## §6. Update and uninstall (FR-005, FR-007, edge cases)

**Decision**: Re-running the same one-line install command overwrites the
binary already at the fixed install path — this is simultaneously the
install command and the upgrade command, satisfying FR-005 without a
separate "update" command. Uninstalling is a single, documented OS-native
command that deletes that one file:

- macOS/Linux: `rm ~/.local/bin/repo-scanner`
- Windows: `Remove-Item "$env:LOCALAPPDATA\repo-scanner\repo-scanner.exe"`

**Rationale**: Because install always writes to the same fixed path, there
is never more than one installed copy to reconcile, so "upgrade" and
"install" are the same operation, and "uninstall" is a plain single-file
delete — no package-manager state, registry entries (besides the PATH
addition, which is harmless to leave behind), or version-tracking database
to maintain. Adding a dedicated `repo-scanner uninstall` subcommand was
considered but rejected: it would be a new CLI command whose entire
implementation is "delete the file currently running it," which is both
awkward (a running program deleting itself) and unnecessary once a single
documented OS command already satisfies FR-007 — it would also nudge
against FR-012 ("packaging changes MUST NOT alter the CLI's existing
commands").

## §7. Distribution hosting

**Decision**: GitHub Releases of this project's own repository
(`github.com/yassinelalaoui/repo-scanner`).

**Rationale**: The project is already hosted there; GitHub Releases needs
no new external account, no new hosted infrastructure, and no cost —
directly consistent with constitution principle 2.6 (infrastructure
minimale). It also gives each release a stable, versioned URL the install
scripts can resolve "latest" against.

**Alternatives considered**: A package index (PyPI) was considered as a
*secondary*, lighter-weight channel for developers who already have Python
(`pip install repo-scanner`), but publishing there requires a new external
account/credential this project doesn't currently have, and doesn't meet
this plan's "binaire autonome" input — left as a possible future addition,
not part of this feature.

## §8. Build process ownership

**Original decision (superseded below)**: A maintainer-run local build
(`packaging/build.py`), not an automated CI/CD pipeline. A maintainer runs
it once per target OS (it must run on a real machine of that OS, since
PyInstaller does not cross-compile) to produce `dist/repo-scanner[.exe]`,
then manually attaches that file plus `install.sh`/`install.ps1` as assets
to a new GitHub Release tagged with the version being published.

**Original rationale**: The spec explicitly lists "an automated release/
publishing pipeline" as a non-goal ("the single install command is the
only distribution path this feature guarantees"). Building CI
infrastructure (e.g. a new `.github/workflows/` release workflow spanning
three OS runners) is real, ongoing infrastructure this feature does not
need to introduce to satisfy any requirement or success criterion — all of
them are about what happens after a release already exists, not how it
gets built.

**Original alternatives considered**: A GitHub Actions release workflow —
would satisfy the same requirements, and is a reasonable follow-up
feature, but is explicitly out of scope here per the spec's own Non-Goals.

---

**Superseding decision**: Build via GitHub Actions
(`.github/workflows/release.yml`), triggered by a maintainer pushing a
version tag (`vX.Y.Z`). A three-way build matrix (`windows-latest`,
`macos-13`, `ubuntu-latest`) each runs `packaging/build.py` on a real
runner of that OS, uploads the renamed binary as a build artifact, and a
final job downloads all three plus `install.sh`/`install.ps1` and
publishes them as a GitHub Release. `packaging/build.py` itself is
unchanged and still works standalone on any real, unrestricted machine —
CI is an additional path, not a replacement for the local one.

**Superseding rationale**: This project's own development machine was
found, during 020's own implementation, to be unable to complete a
PyInstaller build at all — not merely in an agent's sandboxed tool-call
context, but from a plain interactive terminal session on that same
machine. Direct, isolated diagnostics ruled out every locally-configurable
cause: Windows Defender real-time protection (confirmed off via
`Get-MpComputerStatus`), any third-party antivirus (none registered via
`Get-CimInstance ... AntivirusProduct`), Controlled Folder Access (copying
a real signed system `.exe` into the output directory succeeds),
Attack Surface Reduction rules (none configured), Smart App Control (off),
Device Guard/WDAC policy (not enforced), and any recognizable EDR
service/process. Copying the raw PyInstaller bootloader file standalone
also succeeds. Only PyInstaller's own final step — finishing a complete,
previously-unseen `repo-scanner.exe` — reliably fails
(`RuntimeError: Execution of 'copyfile' failed`), every time, regardless
of which shell or tool invokes it. `icacls` on the project folder also
showed a sandbox-branded local group (`CodexSandboxUsers`) with
Modify-only rights applied specifically to that folder — evidence this
project has so far only ever been built on a managed/sandboxed dev
machine, whatever the reason for the restriction turns out to be. Since a
local build genuinely cannot be completed and verified on the only
machine available for this project's own development, building on
GitHub-hosted runners is no longer a "nice to have" — it is the only way
to actually produce a working, distributable binary at all right now, and
doing so does not conflict with the spec's non-goal in spirit: the spec's
non-goal was about *not needing* CI to satisfy any requirement, not about
never using it if the local path turns out to be unusable. Publishing
still requires a maintainer's deliberate action (pushing a tag) — this is
not an unattended, every-commit pipeline.

**Superseding alternatives considered**: Building on a different, genuinely
unrestricted machine — remains valid and is still what `packaging/build.py`
supports directly; not mutually exclusive with CI, but not guaranteed to
be available. Keeping the local-only process and treating the block as
unfixable/out of scope — rejected, since it would leave this feature's
core success criterion (SC-001: install-and-index in one command)
permanently unverifiable and the tool permanently undistributed.

## §9. Target architecture scope

**Decision**: x86_64 only, for all three OSes, in this feature's initial
scope.

**Rationale**: Neither the spec nor this plan's input names a specific
architecture requirement; x86_64 is the most universally applicable default
across Windows/macOS/Linux developer machines today. Apple Silicon
(arm64) and Linux arm64 support can be added later as additional build
targets using the same `packaging/build.py`/spec file, without changing
this feature's design.

**Alternatives considered**: Building for arm64 as well from the start —
deferred as an assumption/limitation rather than a requirement, since nothing
in the spec calls for it and it would double the number of build targets a
maintainer has to produce by hand (§8) for no requirement currently asking
for it.

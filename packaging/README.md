# Packaging & Release Process (maintainers)

How a maintainer builds and publishes a `codepedia` release.

See also: `specs/020-cli-packaging/research.md`,
`specs/020-cli-packaging/contracts/packaging-interface.md`, and
`specs/020-cli-packaging/quickstart.md`.

## 1. Bump the version

Update `[project].version` in `pyproject.toml` (the single source of truth
`codepedia --version` reads at runtime via `importlib.metadata`,
research.md section 4). Commit and push that change to `main` first.

## 2. Build and publish via GitHub Actions (primary path)

Push a version tag matching the version from step 1:

```bash
git tag v0.1.0
git push origin v0.1.0
```

This triggers `.github/workflows/release.yml`, which builds
`codepedia` on a real Windows runner (PyInstaller does not
cross-compile, so each OS genuinely builds its own binary — see
research.md §9 for the x86_64-only scope), renames it per the
release-asset naming contract, and then automatically creates a GitHub
Release on that tag with the binary plus `install.sh`/`install.ps1`
attached. Watch it run under the repository's **Actions** tab; nothing
further to do once it's green.

The matrix originally also built macOS (x86_64) and Linux legs in
parallel; both were dropped after repeatedly failing to fetch PyInstaller
on those hosted runners. Re-adding an `os: macos-latest` / `os:
ubuntu-latest` entry (mirroring the `windows-latest` one) is the way to
bring them back — tracked as future work rather than shipped as a
permanently-red job (see docs/pfa.tex's "Perspectives d'Évolution").

This path exists because building locally was found, during this
feature's own implementation, to be unusable on this project's actual
development machine — not merely inside an AI coding agent's own
sandboxed tool calls, but from a plain interactive terminal on that same
machine too (see Troubleshooting below). CI sidesteps whatever is causing
that entirely, so it is the recommended way to produce a real release
right now.

## 2b. Build locally instead (fallback, if your machine isn't blocked)

If you have a real, unrestricted machine for each target OS available,
you can still run the same build `.github/workflows/release.yml` runs,
by hand:

```bash
python -m pip install -e ".[build]"
python packaging/build.py
```

This produces `dist/codepedia` (`dist/codepedia.exe` on Windows) and
smoke-tests it (`--version` and `scan` against a throwaway repository)
before reporting success. Repeat on each OS, renaming each binary per
`specs/020-cli-packaging/contracts/packaging-interface.md`'s "Release
asset naming" table (`codepedia-<version>-<os>-x86_64[.exe]`), then
attach them plus `install.sh`/`install.ps1` to a GitHub Release yourself.

### Troubleshooting: `RuntimeError: Execution of 'copyfile'/'set_exe_build_timestamp' failed`

Two distinct causes produce this same PyInstaller error on Windows:

- **Real-time antivirus** briefly locking a freshly written `.exe` past
  PyInstaller's own ~3.5-second retry budget (20 attempts). Nothing is
  wrong with the build itself; retry, or temporarily exclude the
  repository's `build/`/`dist/` directories from real-time scanning for
  the duration of the build.
- **Something else entirely, confirmed on this project's own real dev
  machine** (not a sandboxed VM — confirmed directly with the machine's
  owner). The exact same `RuntimeError: Execution of 'copyfile' failed`
  happened both when the build ran through an AI coding agent's tool
  calls *and* from a plain interactive PowerShell session on that same
  real machine — not specific to any one tool or shell. Direct, isolated
  diagnostics on that machine ruled out every locally-configurable cause:
  Windows Defender real-time protection off (`Get-MpComputerStatus`), no
  third-party AV registered (`Get-CimInstance ... AntivirusProduct`),
  Controlled Folder Access not blocking (copying a real signed system
  `.exe` into `dist/` succeeds), no Attack Surface Reduction rules
  configured, Smart App Control off, no Device Guard/WDAC policy
  enforced, and no recognizable EDR service/process running. Copying the
  raw PyInstaller bootloader file standalone also succeeds. Only
  PyInstaller's own final step — finishing a complete, previously-unseen
  `codepedia.exe` — fails, consistently, every time. `icacls` on the
  project folder showed a local group named `CodexSandboxUsers` with
  Modify-only rights applied specifically to that folder, which is likely
  the actual cause: something related to AI-coding-agent tooling
  previously used on that machine appears to have applied a restrictive
  ACL to this project's own directory. If you hit this and want to keep
  building locally, check `icacls <project-root>` for a similar unexpected
  group/ACE and investigate what added it before assuming it's
  antivirus. Otherwise, use the GitHub Actions path above — it does not
  depend on this machine at all.

## 3. Verify

Follow `specs/020-cli-packaging/quickstart.md` Scenario 2 (and ideally
3-10) against the new release before announcing it — in particular, confirm
`curl -fsSL <release-url>/install.sh | sh` / `irm <release-url>/install.ps1
| iex` resolve to this release's assets and that `codepedia --version`
reports the version from step 1 afterward.

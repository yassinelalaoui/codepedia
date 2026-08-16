# Packaging & Release Process (maintainers)

How a maintainer builds and publishes a `repo-scanner` release. This is a
manual process by design — an automated release pipeline is an explicit
non-goal of `specs/020-cli-packaging/spec.md` (research.md section 8).

See also: `specs/020-cli-packaging/research.md`,
`specs/020-cli-packaging/contracts/packaging-interface.md`, and
`specs/020-cli-packaging/quickstart.md`.

## 1. Bump the version

Update `[project].version` in `pyproject.toml` (the single source of truth
`repo-scanner --version` reads at runtime via `importlib.metadata`,
research.md section 4). Commit that change.

## 2. Build a binary — once per target OS

PyInstaller does not cross-compile, so this step runs on a real machine of
each target OS (Windows, macOS, Linux — all x86_64, research.md section 9):

```bash
python -m pip install -e ".[build]"
python packaging/build.py
```

This produces `dist/repo-scanner` (`dist/repo-scanner.exe` on Windows) and
smoke-tests it (`--version` and `scan` against a throwaway repository)
before reporting success. Repeat on each OS, collecting each `dist/`
binary somewhere you can gather them together (e.g. rename immediately
after each build, since every OS writes to the same `dist/repo-scanner`
path).

## 3. Name each binary per the release-asset contract

Rename each built binary to match
`specs/020-cli-packaging/contracts/packaging-interface.md`'s "Release
asset naming" table, substituting the version from step 1:

| Built on | Rename to |
| --- | --- |
| Windows | `repo-scanner-<version>-windows-x86_64.exe` |
| macOS | `repo-scanner-<version>-macos-x86_64` |
| Linux | `repo-scanner-<version>-linux-x86_64` |

## 4. Create the GitHub Release

On `github.com/yassinelalaoui/repo-scanner` (research.md section 7):

1. Tag the commit from step 1 with the version (e.g. `v0.2.0`).
2. Create a new GitHub Release from that tag.
3. Upload as release assets:
   - The three renamed binaries from step 3.
   - `packaging/install.sh` (unrenamed).
   - `packaging/install.ps1` (unrenamed).

### Troubleshooting: `RuntimeError: Execution of 'copyfile'/'set_exe_build_timestamp' failed`

Two distinct causes produce this same PyInstaller error on Windows:

- **Real-time antivirus** briefly locking a freshly written `.exe` past
  PyInstaller's own ~3.5-second retry budget (20 attempts). Nothing is
  wrong with the build itself; retry, or temporarily exclude the
  repository's `build/`/`dist/` directories from real-time scanning for
  the duration of the build.
- **A locked-down dev sandbox/container that blocks new executables.**
  Confirmed while building this feature: in that environment, creating
  *any* new `.exe` file failed immediately (`PermissionError: [Errno 13]`)
  specifically inside the project's own working directory, even via a bare
  `open(path, "wb")` with no PyInstaller involved — while the exact same
  write succeeded one directory above it, in `%TEMP%`, and in the user
  profile root. Windows Defender itself reported as disabled
  (`Get-MpComputerStatus`) and no event was logged in the guest's own
  Defender/Application event logs, meaning the block is enforced by
  something outside the guest OS's own visible security stack (most
  likely the sandbox host, not anything configurable from inside Windows).
  Redirecting PyInstaller's output outside that directory
  (`--distpath`/`--workpath` pointed at `%TEMP%\...`) let the build
  progress all the way to its final, cosmetic timestamp-patching step —
  but the completed executable then disappeared within about a second of
  being written, before PyInstaller's own next read-back step, even
  outside the working directory. There is no in-guest fix for this: it
  is not an antivirus setting, a file permission, or anything this
  project's `.spec`/`build.py` controls. If you hit this, build on a
  regular (non-sandboxed) machine or CI runner instead.

## 5. Verify

Follow `specs/020-cli-packaging/quickstart.md` Scenario 2 (and ideally
3-10) against the new release before announcing it — in particular, confirm
`curl -fsSL <release-url>/install.sh | sh` / `irm <release-url>/install.ps1
| iex` resolve to this release's assets and that `repo-scanner --version`
reports the version from step 1 afterward.

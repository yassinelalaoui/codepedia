# Quickstart: Launcher Homepage with Live Run Progress

**Feature**: 037-launcher-homepage-progress

How to run and validate this feature. Scenarios are ordered so the ones that
work on a machine with no reachable providers come first — which, on the
machine this was written for, is all of them (research §11).

## Prerequisites

```powershell
# Python 3.11-3.13. NOT 3.14: Pydantic schema generation hangs there and it
# looks like a stall, not an error.
.venv\Scripts\python.exe --version
```

Frontend bundles must be current before any browser check — they are committed
artifacts and must not drift from source:

```powershell
cd frontend
npx vite build                          # wiki bundle -> src/doc_generator/assets/
npx vite build --config vite.hub.config.ts   # hub bundle -> src/hub_server/assets/
cd ..
```

## Run the suites

```powershell
# Pass --basetemp outside the repo: a bare run produces ~17 spurious
# PermissionErrors on this machine.
.venv\Scripts\python.exe -m pytest tests/ `
  --basetemp=$env:TEMP\cp-pytest -p no:cacheprovider

cd frontend; npx vitest run; cd ..
```

**Baselines to beat: 808 pytest, 142 vitest.** Both must stay green.

One known-flaky test is unrelated to this feature:
`tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`
makes a live Groq call and fails when Groq answers. Re-run before investigating.

## Start the hub

```powershell
.venv\Scripts\python.exe -m cli home
```

Expected:

```
Codepedia homepage available at http://127.0.0.1:8100/?token=<token>
Keep that URL private: the token authorizes starting and removing analyses on this machine.
```

Open that URL. See [contracts/home-command.md](./contracts/home-command.md).

---

## Scenario 1 — The CLI is unchanged (FR-002, SC-008)

The guarantee everything else rests on. Verify it first.

```powershell
# No sentinel lines without the environment variable.
.venv\Scripts\python.exe -m cli index <repo> 2>&1 | Select-String "@@CODEPEDIA_PROGRESS@@"
```

**Expect**: no matches. With `$env:CODEPEDIA_PROGRESS_STREAM = "1"` set, the
same command emits them. Automated equivalent lives in `tests/integration/`.

**Also expect**: the full pytest suite passes with no test modified. A test that
had to be edited to accommodate this feature is a failure of FR-002, not a test
that needed updating.

## Scenario 2 — A failing run ends clearly (US3, FR-021 to FR-024, SC-003, SC-004)

The path every run takes on this machine, so validate it early.

1. Homepage → enter a repository path → start.
2. Watch stages tick through: scanning, parsing, building the graph,
   summarizing…

**Expect**:

- Stage names and order match the terminal exactly.
- The run reaches a **stopped, failed** state. It never spins indefinitely.
- The failure names the stage (`EMBEDDING`) and every provider attempted
  (`local:nomic-embed-text:latest`, `openai:text-embedding-3-small`).
- It states plainly that **no documentation was kept**, so the ticked stages are
  not read as saved work.
- A retry control is offered and re-runs the same path without retyping it.
- `~/.codepedia/config.json` is **byte-identical** afterwards (FR-025). Check it.

## Scenario 3 — Progress advances inside a stage (FR-015, SC-002, SC-011)

During `SUMMARIZING`, the item counter must keep moving. That stage dominates
the wall clock, and the Groq key's 8000 TPM cap forces `summaryConcurrency: 1`,
so items complete slowly and individually — which is exactly the condition a
stage-only bar would fail.

**Expect**: the displayed count advances within ~2 s of each item, and the
display changes at least once a minute throughout.

## Scenario 4 — Cancelling (FR-012a, SC-003)

Start a run, then stop it.

**Expect**: a terminal **cancelled** state within a second or two — not a wait
for the current stage to finish. Then verify the cleanup:

```powershell
Get-ChildItem ~\.codepedia\repos\ | Where-Object Name -like "*.staging-*"
```

**Expect**: no new `.staging-<pid>` directory from the cancelled run. Existing
residue from before this feature is left alone by design.

A new analysis can be started immediately afterwards.

## Scenario 5 — One run at a time (FR-012)

With a run going, submit a second path.

**Expect**: a refusal naming the repository already being analysed. The running
analysis is undisturbed and no second process appears.

## Scenario 6 — The history lists only real repositories (FR-030, SC-005)

`~/.codepedia/repos/` currently holds 7 `.staging-<pid>` directories against 4
real ones.

**Expect**: exactly the real repositories, newest first. Zero phantom rows.

## Scenario 7 — Reattach (FR-018)

With a run going: reload the page; open a second tab; close the browser
entirely, wait, reopen.

**Expect** in every case: the live run's current state, not an empty display and
not an index bar as though nothing were happening. Exactly one run throughout.

## Scenario 8 — Run log survives a restart (FR-026a, FR-026d, SC-013)

Let a run finish (or fail). Stop the hub with `Ctrl-C`, start it again.

**Expect**: that run's outcome still readable, including its failing stage and
providers. No run shown as still in progress.

Then the interrupted case: start a run and kill the hub **while it is running**.
On restart, that run reads **interrupted** — never still-running — and a new
analysis can be started.

## Scenario 9 — Open a repository (FR-035, FR-038a)

Choose Open on a history row.

**On this machine, expect it to fail** — and to fail *correctly*.
`run_serve` checks all three provider chains before doing anything
(`serve_command.py:36`), so a complete wiki on disk still cannot be served while
embeddings are unreachable.

**Expect**: a message naming the unavailable **stage chain** (FR-038a) — not
"your analysis is unusable", which would be a false diagnosis.

With providers reachable, expect instead: a server starts, catch-up progress
appears if there is any (FR-019), and the browser arrives at the wiki. With
nothing to catch up, no progress display appears at all and the wiki is reached
within 5 seconds (FR-020).

## Scenario 10 — Remove is destructive but narrow (FR-040, FR-041, SC-010)

Record a repository's contents, Remove it from the homepage, compare.

```powershell
Get-FileHash -Algorithm SHA256 (Get-ChildItem <repo> -Recurse -File) |
  Sort-Object Path | Out-File before.txt
# ... Remove via the homepage, confirming when asked ...
Get-FileHash -Algorithm SHA256 (Get-ChildItem <repo> -Recurse -File) |
  Sort-Object Path | Out-File after.txt
Compare-Object (Get-Content before.txt) (Get-Content after.txt)
```

**Expect**: no differences. `~/.codepedia/repos/<stateId>/` is gone; the row is
gone; the repository is untouched. Declining the confirmation deletes nothing.

## Scenario 11 — Authentication (FR-005, SC-009)

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://127.0.0.1:8100/api/runs `
  -H "Content-Type: application/json" -d '{\"path\":\"C:/some/repo\"}'
```

**Expect `401`** with no token — and **no process started**. Repeat for
`POST /api/repositories/{id}/open` and `DELETE /api/repositories/{id}`.

Also confirm a forged `Host` header is rejected (FR-006).

## Scenario 12 — Rejected paths (FR-009, FR-010, constitution 2.7)

Submit each of: a path that does not exist; a file rather than a directory; a
directory with no read permission; `~/.codepedia` itself.

**Expect**: a distinct message naming what is wrong with each, no run started,
and nothing written anywhere.

---

## Browser verification (SC-012, FR-043, FR-044a)

There is no Playwright here. Chrome drives headless over CDP with no new
dependency — Node has global `WebSocket` and `fetch`.

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --headless=new --remote-debugging-port=9222 `
  --user-data-dir="$env:TEMP\cp-037-chrome" --no-first-run
```

Two details that cost time when skipped:

- **Set `Emulation.setDeviceMetricsOverride`.** The default window is too small
  for layout assertions to mean anything.
- **Let the page settle before reading geometry.** Reading mid-reflow once
  produced a convincing phantom "16px scroll drift" that did not exist.

Check, at a narrow and a wide viewport, in both appearances:

- Zero horizontal page overflow (`scrollWidth <= clientWidth` on the document).
- Every text node at ≥ 4.5:1 contrast against its background.
- All three appearance states (System / Light / Dark) reachable in one
  interaction from any other, and no flash of the wrong appearance on reload.
- The brand mark renders at a size where the wordmark is legible, and swaps with
  the appearance; the tab icon is present.

**Kill your Chrome processes when done, matching on your own `--user-data-dir`.**
The machine has the owner's normal Chrome running — a blanket
`Stop-Process -Name chrome` would close their windows.

---

## What must not regress

| Guarantee | How to check |
|---|---|
| Generated wikis fetch nothing (FR-045) | Load a generated wiki over `file://` and count network requests: zero |
| The analysed repository is read-only (2.7) | Scenario 10's hash comparison, and the same before/after an analysis |
| Provider config untouched (FR-025) | Hash `~/.codepedia/config.json` before and after a failing run |
| Committed bundles match source | Rebuild both bundles; `git status` shows no unexpected diff |

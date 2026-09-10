# Quickstart: Validating the Narrative Overview Page

**Feature**: 038-narrative-overview-page

Run from the repository root. `<scratch>` is the session scratchpad; never write
validation output inside the repo.

## §0 Prerequisites

- `.venv` on Python 3.11–3.13. Python 3.14 hangs in Pydantic schema generation.
- A working summary provider chain (`codepedia config`). `index` refuses to
  start without one; see research, Resolved unknowns.
- `frontend/` dependencies installed, only if the `.ai-generated` CSS rule
  changed: `cd frontend && npm run build`.

## §1 Automated

```powershell
.venv\Scripts\python.exe -m pytest --basetemp=<scratch>\pytest -p no:cacheprovider
```

A bare `pytest` reports about 17 spurious `PermissionError`s on this machine.
`test_cli_config` makes a live Groq call and is flaky; re-run it before
investigating a failure there.

Expected: all green, including these tests that map directly to spec
requirements:

| Test | Proves |
| --- | --- |
| `test_overview_narrator.py::test_worst_case_call_fits_the_provider_budget` | FR-020 / SC-012, computed from constants |
| `test_overview_grounding.py::test_a_fabricated_symbol_rejects_its_paragraph` | FR-009, FR-010 / SC-002 |
| `test_overview_page.py::test_no_engine_page_has_the_same_outline` (five cases: no narrator, unreachable, chain exhausted, refused, unusable; each on a fresh store) | FR-014 / SC-004 |
| `test_overview_page.py::test_unchanged_repository_regenerates_identical_markdown` | FR-015 / SC-005 |
| `test_overview_package.py::test_only_the_narrator_accepts_an_engine` | Contract §1 |
| `test_overview_grounding.py::test_a_rejected_opening_paragraph_withholds_the_lead` | FR-010a (G10) |
| `test_overview_page.py::test_changed_repository_without_provider_shows_the_earlier_narrative_marked_stale` | FR-017a / US1 #10 |

## §2 Index both reference repositories and read the pages

```powershell
codepedia index C:\Users\ASUS\IdeaProjects\codepedia-sample-repo
codepedia index C:\Users\ASUS\IdeaProjects\codepedia
```

Each prints its state directory. Open `<state>\docs\index.html` in a browser, and
`<state>\docs\index.md` in an editor.

Read each page **end to end** and check:

1. Two to four marked paragraphs sit directly under the title, before the
   repository facts. One paragraph is acceptable only if the `overview:` line
   reports dropped paragraphs, or the repository has a single subsystem
   (FR-005).
2. The first paragraph says what the repository is and does, with no counts.
3. The major subsystems are named inline as links, and each link opens that
   subsystem's page.
4. The prose says where work enters and where it ends up, naming a real file or
   symbol at each end.
5. Every backticked name in the prose renders as a link, and opening it lands on
   that symbol. Search the repository for any name that does not link; there
   should be none.
6. No "you", no promotional adjective, no heading, list or table inside the prose.
7. There is no inline class diagram, and the two diagram links still work. The
   Features list shows titles only, with no unmarked descriptions (FR-012a).
8. There is no `Last indexed` line. The page footer shows the generation time.
9. **The stranger test (SC-001)**. The implementer is never the reviewer.
   1. First write an answer key from the code: the main subsystems, and where
      operations begin.
   2. Give only `index.md` to a fresh AI session with no repository access, or
      to a person who has not seen the repository.
   3. Score their answers against the key (tasks T028).
10. **The tense review (SC-013)**: copy every generated sentence into
    `<scratch>\tense-review-<repo>.md`, one per line, and mark each one as
    declarative present or not. The expected count of "not" is zero. Keep the
    file, so the review can be repeated.

The terminal output of each `index` run shows at most one `overview:` line, and
only when prose was omitted or reduced.

## §3 No provider: same page, prose absent

`index` cannot run without a provider, so this re-runs the real generator on a
copy of an indexed state with a narrator whose engine fails. It uses no network
and does not touch the real state.

```powershell
Copy-Item -Recurse <sample-state> <scratch>\nopro
.venv\Scripts\python.exe <scratch>\nopro_check.py <scratch>\nopro C:\Users\ASUS\IdeaProjects\codepedia-sample-repo
```

`nopro_check.py`, kept in the scratchpad and never committed, does five things:

1. Opens the copied metadata store, graph and manifest.
2. Deletes the `doc_overview_narratives` row, so there is no cache to fall back
   on.
3. Builds a `DocGenerator` with
   `overviewNarrator=OverviewNarrator(<engine raising RuntimeError>)`, the same
   `featurePlanner` cache and `onNotice=print`.
4. Runs `generateRepositoryDocumentation(root, incremental=False)`.
5. Prints both outlines: the heading sequence and the set of `href`s outside
   `.ai-generated`, for the original page and the regenerated one.

Expected:

- It prints `overview: narrative omitted (no provider could answer)`.
- The two heading sequences are equal, and the two href sets are equal.
- The regenerated page has no `.ai-generated` element, and has no placeholder
  or banner text where the lead was.

Repeat with `overviewNarrator=None` (not configured), an engine returning `""`
(refused), and one returning `"not json"` (unparseable), deleting the narrative
row before each run.

**Earlier-version fallback (FR-017a)**: run `nopro_check.py --keep-cache`. It
skips step 2 and instead bumps `NARRATIVE_FORMAT_VERSION` in-process, so the
current key misses while the stored row remains. Expected:

- It prints `overview: showing the narrative from an earlier version (no provider could answer); <k> of <n> paragraphs still apply`.
- The earlier lead is present, with one `.summary-stale` caveat under it.
- The heading sequence and the href set outside `.ai-generated` are unchanged.

## §4 Rerun on an unchanged repository

```powershell
Copy-Item <sample-state>\docs\index.md <scratch>\index.1.md
Copy-Item <sample-state>\docs\index.html <scratch>\index.1.html
codepedia index C:\Users\ASUS\IdeaProjects\codepedia-sample-repo
git diff --no-index <scratch>\index.1.md <sample-state>\docs\index.md
```

Expected:

- The Markdown diff is **empty**.
- The HTML diff is the footer's `Generated locally … on <timestamp>` line and
  nothing else.
- The second run prints no `overview:` line, because the key hit means no call.

Then serve it:

```powershell
(Get-Item <sample-state>\docs\index.md).LastWriteTime
codepedia serve C:\Users\ASUS\IdeaProjects\codepedia-sample-repo   # stop once the URL prints
(Get-Item <sample-state>\docs\index.md).LastWriteTime
```

Expected: the timestamp is unchanged. On an unchanged repository, `serve` does
not rewrite the page.

## §5 Appearance

In the browser, open `index.html` for both repositories and check:

- light and dark (the theme control in the header);
- about 400 px wide and full width.

For each combination:

- The lead reads as one marked block with a single "AI-generated" badge.
- The page has no horizontal scroll.
- Module rows have no loose punctuation (User Story 4).
- The subsystems table scrolls inside itself when narrow (User Story 2).

## §6 What the narrative costs

```powershell
.venv\Scripts\python.exe <scratch>\cost.py <state> <repo>
```

`cost.py` rebuilds `OverviewEvidence` from the stored state, calls
`build_overview_prompt`, and prints:

- `len(prompt_text) // CHARS_PER_TOKEN`;
- `MAX_NARRATIVE_RESPONSE_TOKENS`;
- their sum;
- `worst_case_call_tokens()`.

Record the real per-run cost for both repositories in the implementation report.
The cost is one call on a cache miss and zero on a hit.

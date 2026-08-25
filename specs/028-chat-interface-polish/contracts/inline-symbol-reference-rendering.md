# Contract: Inline Symbol/File Reference Rendering

**Status**: New client-side rendering contract layered on an existing
server-side convention. No change to what the backend produces.

## Existing convention this reuses (unchanged)

`chat/prompting.py`'s system prompt already instructs the answer-generating
model to reference the file/symbol it relies on inline, in the form:

```text
`<filePath> :: <symbolId>`
```

e.g. `` `src/module.py :: ClassName.method` ``, using the exact
`sourceFilePath` / `sourceSymbolId` values shown to it in the retrieved
evidence block. This is free-form model output embedded in the answer's
Markdown text, not a structured field — `citedSymbolIds` / `citedFilePaths`
(the separate, already-existing citation list, spec 011/014) remain the
authoritative structured record of what was cited; this contract only
governs how a matching *inline* mention is decorated when rendered.

## Recognition rule

When rendering an assistant message's Markdown content, an **inline** code
span (backtick-delimited text with no block-level `language-*` fence around
it) is treated as a symbol/file reference candidate if its text matches:

```text
<non-empty text without " :: "> :: <non-empty text>
```

split on the first literal `" :: "`. The left side is treated as
`filePath`, the right side as `symbolId` (both trimmed of surrounding
whitespace).

## Resolution rule

A candidate resolves through the exact same lookup already used for the
separate citation list — `findByCitation(entries, { symbolId, filePath })`
in `frontend/src/lib/searchIndex.ts` (contract:
`specs/016-wiki-web-interface/contracts/search-index.md`) — symbol id match
first, file path (module-kind entry) fallback second. No new index, no new
matching heuristic, no fuzzy matching.

## Rendering outcomes

| Case | Rendering |
|------|-----------|
| Span matches the pattern **and** resolves | A link (`<a href="{pageUrl}">{label}</a>`) to the resolved documentation page, styled as an inline reference — matching FR-006. |
| Span matches the pattern but does **not** resolve | Plain inline code text (unchanged appearance from ordinary inline code) — matching FR-007; never a broken link, never dropped. |
| Span does not match the pattern at all | Ordinary inline code, untouched — this contract does not apply. |
| Pattern appears inside a fenced code **block** rather than inline code | Not treated as a reference — block code is rendered as syntax-highlighted code verbatim; only bare inline spans are candidates, so a reference quoted as part of a larger code example isn't mistakenly turned into a link. |

## Streaming/partial input

Because the source text is Markdown re-parsed from the accumulated string on
every fragment (not an incremental parser), a reference whose closing
backtick hasn't arrived yet simply isn't a complete inline code span yet and
renders as plain streaming text until it is — no crash, no partial/garbled
link (spec.md Edge Cases, User Story 2 Acceptance Scenario 4).

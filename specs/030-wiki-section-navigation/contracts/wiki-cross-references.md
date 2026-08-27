# Contract: Wiki Page Cross-References

**Status**: New **server-side** rendering contract, on a different surface from
the client-side chat rendering governed by
`specs/028-chat-interface-polish/contracts/inline-symbol-reference-rendering.md`.
It changes only `DocPage.renderedHtml`; nothing about what the backend stores or
what `doc_generator` writes as Markdown changes.

## Why this is a separate contract

028 governs how the **chat panel** decorates an inline mention the answering
model emitted, and it deliberately forbids widening the lookup: *"No new index,
no new matching heuristic, no fuzzy matching."* That constraint is scoped to
that surface, where the model is explicitly instructed to emit the
`path :: symbolId` form and any looser matching would silently rewrite text a
reader is watching stream in.

Generated wiki prose is a different surface with a different producer. A module
summary naturally writes `` `BaseThing` ``, not
`` `src/pkg/gamma.py :: cls-base` `` — demanding the verbose form would make the
prose unreadable. This contract therefore *does* define name-based resolution,
and pays for it with an explicit ambiguity rule (below) rather than by
inheriting 028's prohibition. 028 is unchanged and continues to govern the chat
panel.

## Existing conventions this reuses (unchanged)

- `repository_metadata/summary_prompts.py`'s system prompt instructs the
  summarizing model to wrap any class, function, method or file it names in
  backticks, exactly as it appears.
- The symbol manifest is the one `doc_generator/search_index.py` already
  produces (contract:
  `specs/016-wiki-web-interface/contracts/search-index.md`) — the same
  `{name, kind, symbolId, filePath, pageUrl}` entries the client-side search
  widget consumes. No second index is introduced.

## Recognition rule

Rewriting runs as a Python-Markdown `Treeprocessor`
(`doc_generator/cross_references.py`), so candidates are identified on the
element tree after inline processing, not by matching against rendered HTML.

A candidate is a `<code>` element whose parent is **not** `<pre>`. This makes
"inline code" a structural fact rather than a pattern guess: fenced blocks,
including Mermaid diagram sources and syntax-highlighted samples, are
unreachable by construction.

A candidate is abandoned without resolution if its text is empty, contains a
newline, or exceeds 120 characters — such a span is a code sample, not a
mention.

## Resolution rule

The first rule that yields a match wins:

| # | Form | Resolves to |
|---|------|-------------|
| 1 | `<filePath> :: <symbolId>` | The `symbolId` entry; failing that, the `kind == "module"` entry for `filePath`. Same order as 028's `findByCitation`. |
| 2 | A file path | The `kind == "module"` entry whose `filePath` matches exactly, or — since the scanner may have stored an absolute path while prose writes a repository-relative one — the single entry whose stored path ends with the mention on a path-segment boundary. |
| 3 | A qualified `Class.method` name | The entry of that `name`. `search_index.py` already stores methods under `"<class>.<method>"`, so this needs no special casing. |
| 4 | A bare name | See the ambiguity rule. |

### Ambiguity rule

A bare name resolves **only** when it is unambiguous:

- Exactly one entry in the repository carries that name → that entry.
- Several entries carry it → the one owned by the page's **own module**, if
  exactly one is.
- Otherwise → **no link**.

This is the load-bearing rule of the contract. A wrong link costs more reader
trust than a missing one, and a wiki that silently sends readers to the wrong
`Config` is worse than one that leaves `Config` as plain code. It is also the
posture `frontend/src/lib/markdownReferences.tsx` already takes on the chat
surface, which falls back to bare inline code rather than emit a link it cannot
justify.

## Link target

| Case | `href` |
|------|--------|
| Target lives on the page being rendered | A bare `#anchor` fragment. `relative_output_link` would return the page's own filename, which works but needlessly reloads the page. |
| Target lives on another page | `links.relative_output_link(...)`, so the link is correct from any output depth (diagram pages sit one directory below module pages). |
| Target's `pageUrl` carries no anchor and is the current page | No link — there is nothing to navigate to. |

## Rendering outcomes

| Case | Rendering |
|------|-----------|
| Inline code resolves | `<a class="symbol-ref" href="..."><code>…</code></a>`, styled distinctly from both ordinary inline code and prose links, so a reader can see at a glance which mentions are navigable. |
| Inline code does not resolve | Ordinary inline code, untouched — never a broken link, never dropped. |
| Ambiguous bare name | Ordinary inline code (see the ambiguity rule). |
| `<code>` inside a fenced `<pre>` block | Never a candidate. Block content is emitted byte-for-byte identically whether or not this pass runs. |

## Invariants

1. **`DocPage.contentMarkdown` is never modified.** Links exist only in
   `renderedHtml`. The `.md` artifacts on disk therefore do not churn when the
   symbol manifest moves, and the HTML stays *derived from* the Markdown rather
   than authored independently, as
   `specs/012-wiki-doc-generator/contracts/doc-generator.md` requires.
2. **Incremental regeneration is unaffected.** `doc_generator/impact.py` decides
   what to regenerate from page ids, kinds, source symbol ids and linked page
   ids — never from rendered HTML — so this pass cannot widen or narrow a
   regeneration set (constitution §2.5).
3. **Fenced blocks are byte-identical** with and without the pass. This is
   asserted directly in `tests/unit/test_cross_references.py`.
4. **The lookup is built once per run**, in `DocGenerator._ensure_bundle`,
   alongside the other derived indexes, and the same `SearchIndexDocument` is
   reused for the manifest written at the end of the run.

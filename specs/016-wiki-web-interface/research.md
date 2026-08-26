# Research: Wiki Web Interface

## Decision 1: React/TypeScript builds two small UI islands, not a full SPA

Decision: Build the search widget and chat panel as small, self-contained
React components, compiled into one bundle that mounts into two container
elements added to the existing shared HTML layout. `doc_generator`'s
server-rendered module/diagram/home pages (012/013) are unchanged and
remain the source of truth for wiki content.

Rationale: The spec's Non-Goals explicitly exclude regenerating wiki
content, and the user's own tech direction phrased React as consuming "les
pages générées (4.1)/diagrammes Mermaid (4.2)" — reading and working
alongside the existing generated output, not replacing it. A full SPA would
require a new data API (structured JSON for every module/symbol) that does
not exist and that nothing in the spec asks for, and would obsolete
`doc_generator`'s own HTML rendering (012) for no requirement in this
feature. Building two small islands, mounted the same way Mermaid already
is (013), keeps the blast radius limited to exactly what US1 (home page
copy), US2 (search), and US4 (chat) ask for.

Alternatives considered: A full React SPA fetching structured content from
new backend endpoints was rejected as a large, unrequested scope increase
that would also require re-solving link resolution, diagram rendering, and
Markdown rendering — all of which 012/013 already solve. A meta-framework
(Next.js, Remix) was rejected as unnecessary — there is no server-side
React rendering need here, and it would add a runtime Node dependency this
project has never had, unlike a build-only bundler.

## Decision 2: Vite emits a classic (non-module) script, not `type="module"`

Decision: Configure Vite's build (`build.lib` / IIFE output format) to
produce a single classic `<script>`-loadable bundle, the same convention
013 established for the vendored Mermaid script.

Rationale: Consistency with the one existing vendoring precedent in this
project outweighs the fact that these two new widgets already require HTTP
serving (015) and so are not strictly bound by 013's original
`file://`-CORS constraint. Keeping one script-loading convention across the
whole generated page avoids a second, different rule a future feature would
have to remember, and an IIFE bundle degrades identically well under both
`file://` and `http://` — there is no downside to keeping it classic.

Alternatives considered: An ES-module bundle (Vite's default) was
considered, since 015 always serves over HTTP where ES modules work fine.
Rejected for consistency with Decision in 013 and because it would make the
loading convention depend on which script tag you are looking at, which is
a needless source of confusion for anyone editing `layout.html.jinja` later.

## Decision 3: `search-index.json` is a static, generated manifest — no new backend search endpoint

Decision: `doc_generator.search_index` builds a flat JSON array of every
documented module, class, method, and function — name, kind, and its wiki
page URL (with an anchor for symbols on a shared module page) — written as
`search-index.json` by the documentation writer, and served by 015's
existing static mount. The search widget fetches it once and performs
substring/fuzzy matching entirely in the browser.

Rationale: Adding a new backend search endpoint to `chat_api`/015 would be
new runtime infrastructure the constitution's minimalism principle (2.6)
would have to justify, for a search space (hundreds to a few thousand
symbols for a typical repository) trivially small enough for client-side
matching to stay instant. A static JSON manifest is exactly the same kind
of artifact `doc_generator` already produces for everything else (pages,
the Mermaid asset) — no new serving mechanism, just a new generated file.

Alternatives considered: A dedicated `/search?q=...` backend endpoint was
rejected as unnecessary infrastructure for a problem this small, and would
also have made the search widget dependent on 015 specifically rather than
"any static file server," a portability property worth keeping. A
client-side full-text index library (e.g., a fuzzy-search package with its
own index format) was rejected as an unnecessary dependency for
straightforward name matching over a small list.

## Decision 4: The chat panel uses same-origin relative requests against 014's existing API

Decision: `lib/chatApiClient.ts` calls `POST /sessions`,
`POST /sessions/{sessionId}/messages`, and `GET /sessions/{sessionId}/messages`
as plain relative-URL `fetch` requests, with no configurable base URL.

Rationale: 015 already serves the wiki and the chat API from the same
origin and port, specifically so a single running server backs both (015's
own US2). A relative-URL client takes direct advantage of that: no CORS
headers to configure, no environment-specific API base URL to manage, and
no way for the bundle to accidentally be pointed at a different host.

Alternatives considered: An injected/configurable API base URL (e.g., via a
global set from the layout template) was considered for flexibility and
rejected as solving a problem that does not exist yet — this bundle is only
ever served by 015, which always co-locates both surfaces by design (015
Decision 1).

## Decision 5: Citation links reuse the search index, not a second lookup

Decision: The chat panel resolves each `citedSymbolIds`/`citedFilePaths`
entry from 014's response against the same in-memory `search-index.json`
data the search widget already loaded, producing a link when a match
exists and a plain, unlinked citation label otherwise (spec Edge Case).

Rationale: Both features need the identical mapping — "given a
symbol/file, what is its wiki page URL" — so building it twice would be
duplicated generation logic with a real risk of the two falling out of
sync. Sharing one fetch and one in-memory structure is simpler and
guarantees search results and citation links always agree.

Alternatives considered: A separate, purpose-built citation-resolution
endpoint or manifest was rejected as solving an already-solved problem a
second time for no behavioral difference.

## Decision 6: The home page's architecture overview is enhanced server-side, not with React

Decision: Extend `home.md.jinja` and `generateOverviewPage` (012) to
present a richer architecture summary — for example module/symbol counts
and simple grouping — as ordinary generated Markdown, with no client-side
component involved.

Rationale: This content is static at generation time (it does not change
per browser session, does not need interactivity, and has no data the
server doesn't already have while building the page). Rendering it
server-side keeps it visible even to a page opened via `file://` or with
JavaScript disabled, consistent with 012's "Markdown is canonical" design
and 013's no-JS-fallback precedent, and needs no new dependency at all.

Alternatives considered: A React-rendered architecture overview (e.g., an
interactive project-wide dependency graph) was considered and rejected as
solving more than the spec asks for — US1 only requires an overview a
first-time visitor can read, not an additional interactive visualization
distinct from the per-module diagrams 013 already provides.

## Decision 7: Explicit anchor ids via `attr_list`, not auto-generated TOC slugs

Decision: Give each function/class/method heading in `module.md.jinja` an
explicit `{: #<symbol-id-slug> }` attribute (python-markdown's built-in
`attr_list` extension, added to the existing `_MARKDOWN_EXTENSIONS` tuple),
computed from each symbol's already-existing stable id, rather than relying
on the `toc` extension's automatic heading-slug generation.

Rationale: `search_index.py` needs to compute the exact same anchor a
module page's heading will render with, so a symbol's search result or a
chat citation link lands on the right spot on the page. Reusing each
symbol's already-stable id (the same one used for `contentSymbolIds`)
guarantees the anchor `search_index.py` writes and the anchor the rendered
page actually has are always the same value, computed once, rather than two
independent implementations of a heading-to-slug algorithm that could
drift apart.

Alternatives considered: Replicating `toc`'s auto-slugify algorithm inside
`search_index.py` was rejected as fragile — any future change to how
python-markdown's `toc` extension slugifies headings would silently break
every existing search/citation anchor link without either side's tests
necessarily catching it.

## Decision 8: The compiled bundle is committed, vendored output — Node/npm stay build-time only

Decision: `frontend/`'s build output (`wiki-ui.js`, `wiki-ui.css`) is
committed into `src/doc_generator/assets/`, the same way `mermaid.min.js`
is vendored (013). Running `codepedia`, `chat_api.server`, or any test
requires only the existing Python environment — never Node.js or npm.

Rationale: This is the direct continuation of 013's own reasoning for
vendoring Mermaid rather than depending on a runtime or generation-time
Node process: the constitution's minimal-infrastructure principle (2.6)
governs what the *shipped tool* depends on, not what its own developers use
to build one specific static artifact. Committing the build output makes
that boundary explicit and enforceable — anyone running the tool never
needs Node installed.

Alternatives considered: Building the frontend bundle as part of
`doc_generator`'s own generation run (shelling out to `npm run build` at
documentation-generation time) was rejected — exactly the toolchain
dependency 013 already rejected for `mermaid-cli`, now for a different
asset. The bundle changes only when its own source changes, not per
documentation-generation run, so there is no reason to rebuild it that
often.

## Decision 9: Vitest + React Testing Library, no real-browser end-to-end test

Decision: Test `SearchWidget`/`ChatPanel` component logic with Vitest and
React Testing Library (jsdom-based, no real browser process). Python-side
tests cover `search-index.json`'s generated content and the presence/shape
of the vendored bundle references in rendered HTML. No headless-browser
automation is added.

Rationale: Directly continues 013's own stated precedent — "no
headless-browser rendering test (out of scope for this local Python
suite)" — for the same reason: a real-browser test harness (Playwright,
Selenium) is a heavier, slower dependency than this project has needed so
far, and jsdom-based component tests plus a manual quickstart pass already
give solid confidence in the pieces that matter (data correctness,
component logic, generated-artifact shape) without it.

Alternatives considered: Playwright-based end-to-end tests were considered
and rejected as disproportionate infrastructure for a single-developer
local tool's UI layer, matching the same tradeoff 013 already made.

# Implementation Plan: Chat Interface Polish — Activity Feedback, Rich Rendering & Shareable Sessions

**Branch**: `028-chat-interface-polish` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/028-chat-interface-polish/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Three frontend-only improvements to the already-shipped chat panel
(`frontend/src/components/ChatPanel.tsx`), none requiring a backend or API
change: (1) a visible activity indicator shown from the moment a question is
submitted until the first streamed fragment arrives — closing a gap where
the pending assistant bubble today renders as an empty paragraph while the
input is merely disabled; (2) rendering assistant answers as formatted
Markdown (`react-markdown` + `remark-gfm` + `rehype-highlight`) instead of a
plain paragraph, with a custom inline-code renderer that turns the
`` `path :: symbolId` `` references the system prompt (`chat/prompting.py`)
already asks the model to produce into clickable links, resolved through the
exact same `findByCitation` lookup the existing separate citation list
already uses; (3) replacing the current `localStorage`-based session-id
persistence (spec 025) with a URL query parameter (`?chatSession=<id>`) read
at `ChatPanel` mount, so a reload, a copied link, or a different
browser/device all restore the same conversation via the already-existing
`GET /sessions/{id}/messages` route (spec 025/027) — enforced to complete
before the input becomes usable for a new question (FR-010). Progressive,
fragment-by-fragment delivery over `fetch`/`ReadableStream` and
history-retrieval-by-id are both already implemented end-to-end (specs
026/027); this feature changes how the client visually surfaces activity,
formats content, and persists the id — it adds no new HTTP route, table, or
runtime dependency on the backend.

## Technical Context

**Language/Version**: TypeScript + React 18 (frontend, `frontend/src`) — no backend language/version change (Python 3.11 backend untouched by this feature)

**Primary Dependencies**: React 18 + Vite (existing, `frontend/`), plus three new frontend-only dependencies: `react-markdown` (Markdown rendering via component overrides, no `dangerouslySetInnerHTML`), `remark-gfm` (fenced/inline code plus table/strikethrough parsing), `rehype-highlight` + `lowlight` (syntax highlighting with a curated language subset). No new backend dependency.

**Storage**: SQLite, reusing the existing `chat_sessions` / `chat_messages` tables (spec 025) unchanged — no schema change. Session-id persistence location changes client-side only: URL query parameter replaces `localStorage` (research.md Decision 3); no new client storage mechanism introduced.

**Testing**: Vitest + Testing Library (frontend, `frontend/tests`, already configured) — extend `ChatPanel.test.tsx`, no new backend tests needed (no backend behavior changes).

**Target Platform**: Cross-platform local server (Windows/Linux/macOS) via the existing local web server (spec 015); consumed by the bundled documentation-wiki web UI (spec 016) served from the same origin.

**Project Type**: Web application (existing backend + frontend split: `src/chat_api`, `src/chat` for backend; `frontend/` for the bundled UI) — Option 2 structure, already established by specs 014–027. This feature touches `frontend/` only.

**Performance Goals**: Activity indicator appears with no perceptible delay (well under 1 second) after submission regardless of eventual answer length (SC-001) — a synchronous state update, not a network round trip. Markdown/syntax-highlight rendering re-parses the accumulated answer text on each fragment; kept fast enough for typical answer lengths by using a curated `lowlight` language subset rather than the full `highlight.js` registry (research.md Decision 2).

**Constraints**: No new backend route, schema, or dependency (constitution 2.6); no change to server network binding (constitution 2.2 — untouched, this feature adds no server-side surface at all). Existing callers of `POST /sessions`, `POST /sessions/{id}/messages`, `GET /sessions/{id}/messages` MUST see unchanged behavior — this feature is a pure consumer of those existing contracts. Client bundle must remain fully self-contained (built once via Vite, no runtime CDN fetch for Markdown/highlighting assets) consistent with the project's fully local, offline-capable posture.

**Scale/Scope**: Single local user/operator per session; conversation lengths bounded by what a chat UI reasonably displays (not a scale concern) — no pagination, virtualization, or answer-length limit introduced by this feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| 2.1 Moteur distant par defaut, mode local disponible sur choix explicite | Not implicated: this feature changes only how already-generated answers are displayed and how a session id is carried; it introduces no new call to any AI engine and no change to engine selection. PASS. |
| 2.2 Zero exposition reseau par defaut | Not implicated: no new route, no new server, no change to binding — this feature is entirely client-side rendering/persistence logic layered on existing routes. PASS. |
| 2.3 Repli automatique seulement au sein d'une chaine de moteurs explicitement configuree | Not implicated: no engine-selection or fallback logic touched. PASS. |
| 2.4 Tracabilite des reponses IA | Reinforced, not weakened: `citedSymbolIds`/`citedFilePaths` remain the authoritative citation record (unchanged); this feature additionally makes an in-text reference the model already produces (per the existing system prompt) clickable, using the same resolution as the existing citation list — strictly more traceability surfaced to the user, no new/duplicate citation source. PASS. |
| 2.5 Re-indexation incrementale | Not implicated: no indexing/analysis logic touched. PASS. |
| 2.6 Infrastructure minimale et stockage local | No new backend dependency, table, or external service. Three new *frontend build-time* dependencies (react-markdown, remark-gfm, rehype-highlight+lowlight) are bundled into the existing static client bundle by the existing Vite build — no runtime service, no CDN fetch, no new persistent storage (URL parameter and in-memory React state only; `localStorage` usage is removed, not added to). PASS. |
| 2.7 Depot analyse en lecture seule | Not implicated: no source-repository writes; this is UI/client code only. PASS. |

No violations. Complexity Tracking table intentionally omitted (nothing to justify).

**Post-Phase-1 re-check**: Phase 1 design (`data-model.md`, `contracts/`)
introduces one extended client-side view type (`DisplayMessage.deliveryState`),
one derived-at-render-time concept (`InlineSymbolReference`, resolved through
the existing `findByCitation` — no new resolution logic or data source), and
one new client-only contract (`chatSession` URL parameter, replacing
`localStorage`). None of this adds a network exposure surface, a remote
call, a new backend dependency, or a repository write. All gates above still
PASS unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/028-chat-interface-polish/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── session-url-parameter.md
│   └── inline-symbol-reference-rendering.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── package.json               # + react-markdown, remark-gfm, rehype-highlight, lowlight
├── src/
│   ├── components/
│   │   └── ChatPanel.tsx      # activity indicator; DisplayMessage.deliveryState;
│   │                          #   Markdown rendering; URL-param session id
│   │                          #   (replaces sessionIdRef + localStorage)
│   ├── lib/
│   │   ├── chatApiClient.ts   # unchanged (SSE parsing/askQuestion already correct, spec 027)
│   │   ├── searchIndex.ts     # unchanged (findByCitation reused as-is)
│   │   └── markdownReferences.tsx  # new: custom `code` renderer + `path :: symbolId`
│   │                          #   parsing, used by ChatPanel via react-markdown's
│   │                          #   `components` override
│   └── styles.css             # + activity-indicator, formatted-answer, code-block styles
└── tests/
    ├── ChatPanel.test.tsx           # extend: indicator lifecycle, Markdown/code/reference
    │                                #   rendering, URL-param session resume + 404 fallback,
    │                                #   input gated on history hydration
    └── markdownReferences.test.tsx  # new: reference-parsing/resolution unit coverage

src/                            # backend — untouched by this feature
└── chat_api/, chat/            # existing routes/pipeline consumed as-is (specs 014-027)

tests/                          # backend — untouched by this feature
```

**Structure Decision**: Extends the existing web-application split
(`src/chat*` backend packages + `frontend/`, established by specs 014-027)
with frontend-only changes — no new top-level directory or backend package.
All new code lands inside `frontend/`, in modules that already exist for
this exact concern (the chat panel component, its API client, and its
symbol-lookup helper) plus one new small frontend-only helper module for the
inline-reference rendering logic.

## Complexity Tracking

Not applicable — no constitution violations to justify.

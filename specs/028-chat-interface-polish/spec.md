# Feature Specification: Chat Interface Polish — Activity Feedback, Rich Rendering & Shareable Sessions

**Feature Branch**: `028-chat-interface-polish`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "Faire évoluer l'interface de chat (Partie 5.2) sur trois points liés à la qualité perçue de l'échange. Premièrement, dès l'envoi d'une question, l'interface doit afficher un indicateur visible d'activité (indicateur de frappe/génération en cours) qui reste affiché jusqu'à réception du premier fragment de réponse, puis consommer le flux de tokens exposé par l'API (Partie 4.3) pour afficher la réponse au fur et à mesure de sa génération plutôt que d'attendre le bloc complet ; l'entrée ne doit plus rester simplement désactivée sans retour visuel pendant potentiellement plusieurs dizaines de secondes. Deuxièmement, les réponses générées doivent être rendues comme du contenu structuré (blocs de code avec coloration syntaxique, mise en forme des références de symboles au format `chemin/fichier.py :: NomClasse.methode` déjà produites par le système), et non comme du texte brut dans un paragraphe simple ; chaque référence de symbole citée doit rester cliquable vers la page de documentation correspondante, conformément au système de citation déjà en place. Troisièmement, l'identifiant de la session en cours doit être conservé d'une manière qui survit à un rechargement de la page (ex. dans l'URL de la page wiki), et au chargement de l'interface, si un identifiant de session est présent, l'historique complet doit être récupéré via l'API (Partie 4.3) et affiché avant que l'utilisateur ne pose une nouvelle question, plutôt que de repartir d'une conversation vide. Critère de succès : un utilisateur voit un retour visuel immédiat dès l'envoi d'une question et voit la réponse apparaître progressivement ; une réponse contenant du code s'affiche formatée avec les références de symboles cliquables ; un rechargement de la page en plein milieu d'une conversation restaure l'intégralité de l'échange précédent sans action de l'utilisateur."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Know the assistant is working the instant a question is sent (Priority: P1)

A team member asks the chat a question. The moment they submit it, they see
a clear, active signal that the assistant is working on it — not a
frozen, disabled input with no explanation. As soon as the first part of
the answer is ready, that signal gives way to the answer itself building up
progressively, rather than an unexplained wait of many seconds followed by
everything appearing at once.

**Why this priority**: This is the single biggest perceived-quality gap
today — a question that takes tens of seconds to answer currently leaves
the user staring at a disabled input with no indication anything is
happening, which reads as broken rather than busy. This is independently
valuable and testable regardless of how the eventual answer is formatted or
how the session is remembered.

**Independent Test**: Submit a question and confirm a visible "working"
signal appears immediately, stays visible until the first piece of the
answer is ready, and is then replaced by the answer itself growing
progressively until it's complete.

**Acceptance Scenarios**:

1. **Given** a chat panel with no answer in progress, **When** a question is
   submitted, **Then** a visible activity indicator appears immediately
   (not after a delay), before any part of the answer has arrived.
2. **Given** the activity indicator is showing, **When** the first piece of
   the answer becomes available, **Then** the indicator is replaced by that
   piece of the answer, and the rest continues to build up progressively as
   it becomes available.
3. **Given** an answer is generating, **When** it fails partway through or
   the assistant is unavailable, **Then** the activity indicator gives way
   to a clear error message rather than spinning indefinitely.
4. **Given** an answer is very fast to start, **When** the first piece
   arrives almost immediately, **Then** the transition from indicator to
   answer still happens cleanly, without a jarring flash or leftover
   indicator artifact.

---

### User Story 2 - Read answers as formatted content, not an undifferentiated block of text (Priority: P2)

A team member receives an answer that includes a snippet of code and a
couple of references to specific functions or classes in the codebase.
Instead of seeing everything as one plain paragraph, they see the code
clearly set apart and readable, and each reference to a specific piece of
code as a clickable link straight to that code's documentation page.

**Why this priority**: Once an answer is visible (User Story 1), how
readable and useful it is becomes the next biggest factor in perceived
quality — a technical answer full of code and symbol references is
substantially harder to use as an unbroken paragraph of plain text. This is
independently testable against any already-received answer, regardless of
whether it arrived progressively or all at once.

**Independent Test**: Ask a question whose answer includes both a code
snippet and at least one reference to a documented symbol or file, and
confirm the code renders visually distinct from prose, and the symbol/file
reference renders as a working link to that item's documentation page.

**Acceptance Scenarios**:

1. **Given** an answer containing a fenced code snippet, **When** it is
   displayed, **Then** the code appears visually distinct from surrounding
   prose (e.g. monospaced, set apart, syntax-colored) rather than blending
   into a plain paragraph.
2. **Given** an answer containing a reference to a symbol the system has
   already indexed and documented, **When** it is displayed, **Then** that
   reference appears as a clickable link that opens the corresponding
   documentation page — the same resolution the existing citation list
   already performs, now also applied to references appearing within the
   answer's own text.
3. **Given** an answer containing a reference to a symbol or file the
   system cannot resolve to a documented page, **When** it is displayed,
   **Then** that reference still appears clearly as a reference (not
   silently dropped or garbled) but as plain, non-clickable text — matching
   how an unresolvable citation already behaves in the existing citation
   list.
4. **Given** an answer is still arriving progressively (User Story 1),
   **When** it contains a code block that has not finished streaming in
   yet, **Then** the completed portion of the message keeps rendering and
   the still-arriving tail is shown as plain text until it closes, without
   the panel crashing or its layout breaking — rather than requiring the
   full answer before showing anything.

---

### User Story 3 - Reload the page mid-conversation without losing it (Priority: P3)

A team member is in the middle of a conversation with the chat and reloads
the page — intentionally or not. When the page comes back, their entire
prior conversation is right there, exactly as they left it, before they've
done anything else. The address of the page itself is enough to get back to
that same conversation, so it can also be reopened later, or shared, and
still land on the same exchange.

**Why this priority**: This closes a real but less frequent gap than User
Story 1 or 2 — most sessions probably don't hit a mid-conversation reload,
but when they do today, the mechanism that recovers it isn't reflected in
anything the user can see, save, or hand to someone else. It's
independently testable against any existing conversation, regardless of how
that conversation's answers were formatted or delivered.

**Independent Test**: Start a conversation, ask at least one question,
reload the page, and confirm the complete prior exchange reappears before
any new question is asked — then copy the page's own address, open it
fresh, and confirm it lands on that same conversation.

**Acceptance Scenarios**:

1. **Given** an ongoing conversation with at least one question already
   answered, **When** the page is reloaded, **Then** the complete prior
   exchange (every question and answer, in order) is restored and visible
   before the user can submit a new question.
2. **Given** a conversation's page address has been copied, **When** it is
   opened again (same browser or a different one), **Then** it restores
   that same conversation's history rather than starting a new,
   unrelated one.
3. **Given** no conversation has been started yet, **When** the page loads,
   **Then** it starts a fresh, empty conversation rather than erroring.
4. **Given** a page address refers to a conversation that no longer exists
   (for example, after a fresh re-index), **When** the page loads,
   **Then** it starts a new conversation cleanly rather than showing an
   error or an empty, seemingly-broken state.

---

### Edge Cases

- What happens when a user submits a new question before a previous
  answer has finished arriving? The prior answer's in-progress display is
  not corrupted or overwritten mid-stream by the new one; each question's
  activity indicator and progressive answer are clearly its own.
- What happens when an answer's code block or symbol reference is malformed
  or incomplete (e.g. cut off mid-format)? It degrades to plain, readable
  text for the affected portion rather than breaking the rest of the
  answer's display.
- What happens when the same conversation address is opened in two tabs at
  once? Each tab independently restores and displays the same conversation
  history; this does not need to keep the two tabs live-synchronized with
  each other's new questions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The interface MUST display a visible activity indicator
  immediately upon a question being submitted, before any part of the
  answer is available.
- **FR-002**: The activity indicator MUST remain visible for as long as no
  part of the answer has arrived yet, and MUST be replaced by the answer's
  content as soon as the first part of it becomes available.
- **FR-003**: The interface MUST display the answer's content progressively
  as it becomes available, rather than withholding it until the complete
  answer is ready.
- **FR-004**: If answer generation fails or the assistant becomes
  unavailable while the activity indicator or a partial answer is showing,
  the interface MUST replace it with a clear error message rather than
  leaving an indefinite activity indicator or a silently stalled partial
  answer.
- **FR-005**: The interface MUST render a fenced code snippet within an
  answer as visually distinct, readable code (not as an unformatted part of
  a plain paragraph).
- **FR-006**: The interface MUST recognize a reference to a documented
  file/symbol appearing within an answer's own text and render it as a
  clickable link to that item's documentation page whenever the system can
  resolve it, using the same resolution already used for the existing
  citation list.
- **FR-007**: A file/symbol reference within an answer's text that cannot
  be resolved to a documented page MUST still render as clear, readable
  text, not as a broken link, raw markup, or dropped content.
- **FR-008**: The current conversation's identifier MUST be retained in a
  way that survives a reload of the page it appears on, without requiring
  the user to take any action to preserve it.
- **FR-009**: A conversation's page address, once obtained, MUST be able to
  restore that same conversation (its complete history) when opened again,
  including from a different browser or device than the one that started
  it.
- **FR-010**: On loading the interface, if the page's address identifies an
  existing conversation, the interface MUST retrieve and display that
  conversation's complete history before the user is able to submit a new
  question.
- **FR-011**: If the page's address identifies a conversation that no
  longer exists, the interface MUST start a new, empty conversation rather
  than showing an error or a broken state.
- **FR-012**: Existing chat behavior not covered by the above (answer
  accuracy, citation correctness in the existing separate citation list,
  the local-only reachability of the underlying service) MUST remain
  unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user sees a visible response to submitting a question
  (the activity indicator) with no perceptible delay — well under a second
  — regardless of how long the eventual complete answer takes to generate.
- **SC-002**: From the moment a question is submitted to the moment the
  answer is complete, a user always sees either an active indicator or
  growing answer content — never a static, unexplained disabled state.
- **SC-003**: Every generated answer containing a resolvable file/symbol
  reference displays that reference as a working link to its documentation
  page, with zero unresolvable-but-silently-dropped references observed in
  testing.
- **SC-004**: Every generated answer containing a code snippet displays it
  as visually distinct, readable code, verified across answers of varying
  length and content.
- **SC-005**: Reloading the page at any point during a conversation
  restores the complete prior exchange before any new question can be
  asked, 100% of the time the conversation still exists.
- **SC-006**: A conversation's page address, copied and reopened later or
  elsewhere, restores that exact conversation every time it still exists.

## Assumptions

- Progressive, fragment-by-fragment answer delivery over the underlying
  service is already available (delivered by prior features covering the
  chat pipeline and its streaming API) — this feature is about how the
  interface visually presents that already-streaming content and signals
  activity before it starts, not about building the underlying streaming
  transport itself.
- Recovering a conversation's history after a reload, given its
  identifier, is already available (delivered by prior features covering
  session persistence and history retrieval) — this feature changes what
  the identifier is retained in (the page's own address, so it is
  shareable/reopenable) rather than building history retrieval itself.
- "Structured content" rendering covers what generated answers actually
  produce today: prose text, fenced code snippets, inline code, and
  file/symbol references in the established `path/to/file.ext ::
  Symbol.name`-style format the system already generates — not a
  general-purpose document format with arbitrary formatting features
  (tables, headings, embedded images, etc.) beyond what real answers
  contain.
- This feature's session-address persistence is guaranteed for a reload of
  the same page. Whether the same conversation is also carried along when
  navigating to a different page within the wiki (for example, following a
  citation link to a module page and then continuing the conversation
  there) is not mandated by this feature; if it happens to work as a side
  effect of the chosen approach, that is a bonus, not a requirement.
- No new symbol-citation data is introduced by this feature — it reuses the
  exact file-path/symbol-id information the existing citation system
  already produces and resolves to documentation pages.
- Retaining the conversation identifier switches from an in-browser
  mechanism (surviving only a reload of the same browser profile) to the
  page's own address (surviving a reload, a copied link, or a different
  browser/device — User Story 3). A conversation an already-open browser
  tab was tracking only through the prior in-browser mechanism, from before
  this change took effect, is not carried forward by it — that one-time
  transition is an accepted consequence of moving to an address-based
  identifier, not a defect this feature needs to bridge.

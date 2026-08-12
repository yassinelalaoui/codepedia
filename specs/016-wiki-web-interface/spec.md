# Feature Specification: Wiki Web Interface

**Feature Branch**: `016-wiki-web-interface`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Construire l'interface web permettant à un développeur ou un nouveau membre de l'équipe de naviguer dans la documentation générée. L'interface doit offrir : une page d'accueil présentant l'architecture globale du projet, une navigation entre les pages de modules/symboles avec recherche de symbole/fonction par nom, l'affichage des diagrammes de dépendances interactifs avec navigation par clic, et une interface de chat permettant de poser une question en langage naturel et d'afficher la réponse avec des liens cliquables vers les pages du wiki correspondant aux fichiers/symboles cités. L'interface doit distinguer les deux profils d'usage : consultation ponctuelle d'une page précise pour un développeur expérimenté, et parcours exploratoire de bout en bout pour un nouveau membre de l'équipe en onboarding. Critère de succès : un nouveau membre de l'équipe peut, sans aide externe, ouvrir le wiki, comprendre l'architecture globale du projet, trouver une fonction précise par recherche, et poser une question au chat en obtenant une réponse avec des liens fonctionnels vers le code documenté."

## Overview

Build the browsable web interface a developer or new team member actually
uses on top of the already-generated documentation wiki and the already
existing chat capability. The interface presents a home page describing the
project's overall architecture, lets a user search for a symbol or function
by name, shows a module's interactive dependency diagram with click
navigation, and offers a chat panel that answers natural-language questions
with clickable links back to the wiki pages of the files and symbols it
cites. The interface must work equally well for a quick, single-page lookup
and for a full exploratory session starting from the home page.

## Goals

- Give a first-time visitor a clear picture of the project's overall
  architecture from the home page.
- Let any user search for a symbol or function by name and jump straight to
  its documentation page.
- Let any user view a module's interactive dependency diagram and navigate
  to related modules by clicking it.
- Let any user ask a natural-language question and follow clickable links
  from the answer's citations to the documented code they reference.
- Support both a quick, single-page lookup and a full exploratory
  onboarding session equally well.

## Non-Goals

- Generating the documentation wiki's content, diagrams, or symbol data;
  this feature only presents what the existing documentation-generation
  pipeline (012/013) has already produced.
- Changing how the chat API answers questions or what it cites; this
  feature only presents its existing responses (014).
- Serving the wiki's files or the chat API over HTTP; this feature is the
  browser-side interface consumed through the existing local server (015).
- Multi-user accounts, personalization, or saved search history.
- Editing documentation content or symbol data from the interface.

## User Stories

### US1 - Understand the project from the home page

As a new team member, I want to open the wiki's home page and see the
project's overall architecture, so that I can build a mental model of the
codebase before diving into specific files.

Acceptance criteria:

- Opening the wiki's home page presents an overview of the project's
  overall architecture.
- From the home page, a user can reach the documentation for any of the
  project's modules.
- The home page is useful to someone with no prior knowledge of the
  codebase.

### US2 - Find a specific symbol or function quickly

As an experienced developer, I want to search for a symbol or function by
name and jump straight to its documentation page, so that I can look
something up without browsing through the wiki's structure.

Acceptance criteria:

- A user can search for a symbol or function by name from anywhere in the
  wiki.
- Search results show enough context to tell apart similarly named
  matches.
- Selecting a search result opens that symbol's documentation page
  directly.
- Searching for a name with no match shows a clear "no results" message.

### US3 - Explore a module's dependencies visually

As a developer, I want to view a module's interactive dependency diagram
and click through to related modules, so that I can understand how the
code is connected without reading source files directly.

Acceptance criteria:

- A module's documentation page gives access to its interactive dependency
  diagram.
- Clicking a node in the diagram navigates to that node's documentation
  page.

### US4 - Ask the chat a question and follow links to the cited code

As a developer, I want to ask a natural-language question in a chat panel
and get an answer with clickable links to the wiki pages of the files and
symbols it cites, so that I can go from a question directly to the relevant
documented code.

Acceptance criteria:

- A user can type a natural-language question into a chat panel reachable
  from the wiki.
- The chat panel displays the generated answer.
- Every file or symbol the answer cites appears as a distinguishable,
  clickable link.
- Clicking a citation link opens the corresponding wiki page.
- If the chat cannot produce an answer (for example, the local model is
  unavailable), the panel shows a clear message instead of an unexplained
  failure.

### Edge Cases

- What happens when a search finds no matching symbol? A clear "no
  results" message is shown rather than a blank or broken state.
- What happens when the chat cannot produce an answer? A clear, specific
  message is shown in the chat panel rather than a silent failure or an
  unexplained stuck state.
- What happens when a chat answer cites a file or symbol that has no
  corresponding wiki page? The interface handles this gracefully — by
  omitting the link or clearly marking it unavailable — rather than
  offering a broken link.
- What happens when a user opens a specific module, diagram, or symbol
  page directly, without visiting the home page first? The page is
  understandable and navigable on its own.
- What happens when the wiki contains a very large number of modules and
  symbols? Search results stay usable and relevant rather than becoming an
  unfiltered, unreadable list.

## Requirements *(mandatory)*

### Functional Requirements

#### Home page and architecture overview

- The interface MUST present an overview of the project's overall
  architecture on the wiki's home page.
- The home page MUST provide navigable entry points to the project's
  modules.

#### Symbol search

- The interface MUST let a user search for a symbol or function by name
  from anywhere in the wiki.
- Search results MUST show enough context to distinguish between similarly
  named matches.
- Selecting a search result MUST open that symbol's documentation page.
- The interface MUST show a clear message when a search finds no matching
  symbol.

#### Dependency diagram navigation

- Each module's documentation page MUST provide access to its interactive
  dependency diagram.
- Clicking a node in a dependency diagram MUST navigate to that node's
  documentation page.

#### Chat panel

- The interface MUST let a user submit a natural-language question and see
  the generated answer.
- The interface MUST render every file or symbol the answer cites as a
  distinguishable, clickable link.
- Clicking a citation link MUST open the corresponding wiki page.
- The interface MUST show a clear message when the chat cannot produce an
  answer.

#### Supporting both usage profiles

- A user MUST be able to open any specific module, diagram, or symbol page
  directly and use it without first visiting the home page.
- A user MUST be able to move from the home page through modules, diagrams,
  and search results in one continuous exploratory path.

### Key Entities *(include if feature involves data)*

- **SymbolSearchIndex**: The searchable set of symbols and functions a user
  can query by name, drawn from the already-documented codebase.
- **SearchResult**: A single match returned for a search query, carrying
  enough context to distinguish it from similarly named matches and a link
  to its documentation page.
- **ChatPanel**: The interface surface where a user submits a question and
  views the generated answer.
- **CitationLink**: A clickable reference, shown alongside a chat answer,
  from a cited file or symbol to its wiki documentation page.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- A new team member can open the wiki and, from the home page alone,
  describe the project's overall architecture without external help.
- A user can find a specific function by name and reach its documentation
  page in under 30 seconds.
- A user can open a module's dependency diagram and reach a related
  module's documentation page by clicking a node, without leaving the
  browser.
- A user can ask a question in the chat panel and receive an answer where
  every citation link opens the correct documented page.
- A new team member can, unaided, complete the full path from opening the
  wiki to understanding the architecture, finding a specific function, and
  getting a cited chat answer.

## Assumptions

- The wiki's pages, diagrams, and chat capability already exist and are
  served by the existing local web server (012/013/014/015); this feature
  only adds the browsing, search, and chat presentation layer on top.
- The interface runs entirely in the browser against the already-local
  server; no new backend capability beyond what already exists is assumed
  necessary.
- Symbol and function search operates over symbols already extracted and
  documented by the existing pipeline; it does not introduce new symbol
  extraction or analysis.
- "Without external help" in the success criteria means the interface
  itself provides enough wayfinding (navigation, labeling, search) for a
  new team member — it does not require a guided tutorial or onboarding
  wizard.

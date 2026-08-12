# Feature Specification: Local Web Server

**Feature Branch**: `015-local-web-server`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Construire le serveur web local qui sert les pages de documentation générées et expose l'API de chat à l'interface utilisateur. Le serveur doit être lié à 127.0.0.1 par défaut (aucune exposition réseau externe sans configuration explicite de l'utilisateur), servir les pages du wiki généré ainsi que les ressources statiques nécessaires (diagrammes, styles), et exposer les routes de l'API de chat définie en Partie 4.3. Critère de succès : après lancement de la commande de démarrage du serveur, l'ensemble du wiki généré est consultable depuis un navigateur sur localhost, et aucune requête n'est acceptée depuis une adresse autre que localhost/réseau interne sans configuration explicite."

## Overview

Build the single local web server that serves the generated documentation
wiki's pages and static resources to a browser and, on that same running
instance, exposes the existing chat API's operations. The server must
remain reachable only from the local machine or the user's local network,
never exposed publicly by default.

## Goals

- Serve the generated documentation wiki's pages over HTTP so they are
  browsable from a standard web browser.
- Serve the static resources the wiki depends on (for example, interactive
  diagrams and styling) so pages render and function correctly through the
  server.
- Expose the existing chat API's operations from the same running server
  instance that serves the wiki.
- Restrict all access to the local machine or the user's local network by
  default, with no public exposure.
- Reuse the existing wiki output and chat API unchanged, rather than
  reimplementing either.

## Non-Goals

- Generating or regenerating the documentation wiki's content; this server
  only serves what the existing documentation-generation pipeline (012/013)
  has already produced.
- Building the web interface (browser-side UI/UX) that consumes the wiki and
  the chat API; this feature is the serving layer only.
- Changing the chat API's (014) request/response behavior or the wiki's
  page content/structure.
- Multi-user authentication or authorization beyond trusting the local
  machine/network.
- Serving more than one repository's generated wiki from a single running
  server instance.

## User Stories

### US1 - Browse the generated wiki from a browser

As a developer, I want to start the local server and browse the generated
documentation wiki in my browser, so that I can navigate module pages and
diagrams without manually opening files from disk.

Acceptance criteria:

- Starting the server makes the wiki's home page reachable at a localhost
  address in a standard browser.
- Following a link from one wiki page to another (a module or diagram page)
  continues to work when browsing through the server.
- A diagram page's interactive diagram and any other static resources it
  depends on load and function correctly when served by the server.

### US2 - Ask questions through the same local address

As a developer, I want the chat API to be reachable from the same local
server that serves the wiki, so that a single running server provides both
browsing and chat without starting a second process.

Acceptance criteria:

- With the server running, creating a session, asking a question, and
  reading history all work at the server's local address, behaving exactly
  as the existing chat API already defines.
- No additional server process or separate address is required to use the
  chat API alongside the wiki.

### US3 - Local-only access stays enforced by default

As the person running the tool, I want the combined server to remain
unreachable from outside my machine or local network unless I explicitly
configure otherwise, so that neither the documentation content nor the chat
capability is ever exposed to the public internet by accident.

Acceptance criteria:

- Starting the server with no extra configuration only accepts connections
  from the local machine by default.
- Allowing access from elsewhere on the user's local network requires an
  explicit, separate configuration step.
- No configuration path defaults to public-internet exposure.

### Edge Cases

- What happens when the server is started before a documentation wiki has
  been generated? The server should clearly indicate the wiki is not yet
  available rather than serving a blank or broken page.
- What happens when a requested wiki page or static resource does not
  exist? The server should return a clear not-found response rather than an
  unhandled error.
- What happens when a request path could be interpreted as either wiki
  content or a chat API operation? The server must resolve this
  unambiguously so a request always reaches exactly one of the two, never
  both or neither.
- What happens when a request arrives from outside the local machine or
  local network? The connection is not accepted, consistent with the
  default local-only binding.

## Requirements *(mandatory)*

### Functional Requirements

#### Serving the generated wiki

- The server MUST serve the generated documentation wiki's pages over HTTP
  so they are reachable from a standard web browser.
- The server MUST serve the static resources the wiki pages depend on (for
  example, interactive diagrams and styling) so pages render and function
  correctly when loaded through the server.
- The server MUST serve the wiki's home page as the entry point for
  browsing the generated documentation.
- Links between wiki pages MUST continue to work when the wiki is served by
  the server, not only when its files are opened directly from disk.

#### Exposing the chat API

- The server MUST expose the existing chat API's session-creation,
  question-asking, and history-reading operations under the same running
  server instance that serves the wiki.
- The server MUST NOT change the chat API's existing request or response
  behavior; it only makes those operations reachable alongside the wiki.

#### Local-only network access

- The server MUST bind only to the local machine (localhost) or addresses
  within the user's local/private network by default.
- The server MUST NOT be reachable from the public internet by default, and
  MUST require an explicit, separate action from the user to change that.
- The server MUST NOT require outbound access to the public internet to
  serve the wiki or the chat API.

#### Startup and operation

- A single startup action MUST make both the wiki and the chat API
  reachable.
- The server MUST clearly indicate the local address at which the wiki is
  reachable once it has started.

### Key Entities *(include if feature involves data)*

- **LocalWebServer**: The single running local process that serves the
  generated wiki's pages and static resources and exposes the chat API's
  operations, bound to a local-only address by default.
- **WikiStaticAsset**: A generated wiki page or a static resource it depends
  on (for example, a diagram or stylesheet) that the server serves as-is
  from the generated documentation output.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- After running the server's startup command, a user can open a browser at
  a localhost address and browse the entire generated wiki, including
  diagrams, without opening any file directly from disk.
- After that same startup command, the chat API's create-session,
  ask-question, and read-history operations are reachable from that same
  local address.
- No separate server process or additional startup command is needed to use
  both the wiki and the chat API.
- An attempt to reach the server from outside the local machine or local
  network fails to connect by default, without any additional configuration
  by the user.

## Assumptions

- The documentation wiki has already been generated by the existing
  documentation-generation pipeline (012/013) into a known output location
  before the server is started.
- The chat API's underlying local retrieval-and-generation pipeline (011)
  and its local model dependencies are configured the same way feature 014
  already requires.
- A single local user operates the server at a time, consistent with the
  chat API's existing assumption.
- "Local network" carries the same meaning already established for the chat
  API: the user's own private network, reachable without traversing the
  public internet.
- Regenerating the wiki when source content changes remains a separate,
  explicit step performed by the existing documentation-generation pipeline;
  this server only serves whatever has already been generated.

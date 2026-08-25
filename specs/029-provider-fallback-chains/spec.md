# Feature Specification: Remote-Default AI Provider Chains with Explicit Fallback

**Feature Branch**: `029-provider-fallback-chains`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "Mettre en oeuvre le pipeline IA distant par défaut avec repli automatique explicite, tel que défini par les principes 2.1 et 2.3 de la constitution v3.0.0. Pour chacune des trois étapes consommant un modèle d'IA — calcul des embeddings, génération des résumés de code à l'indexation, génération des réponses de chat — la configuration doit désormais reposer sur une chaîne ordonnée de fournisseurs par étape, et non plus sur un fournisseur unique. À l'installation, sans aucune configuration de la part de l'utilisateur, chaque chaîne doit déjà contenir un fournisseur distant par défaut : OpenAI text-embedding-3 pour les embeddings, un fournisseur distant (Groq) pour les résumés et pour le chat. Le mode entièrement local (Tree-sitter déjà local par nature, plus un moteur d'embeddings et un moteur d'inférence locaux type Ollama) doit rester pleinement supporté pour chacune des trois étapes, mais uniquement si l'utilisateur l'ajoute lui-même explicitement à la chaîne correspondante — jamais présent par défaut. Le système doit fournir une action de configuration unique permettant de basculer les trois chaînes vers le mode entièrement local en une seule fois, sans obliger l'utilisateur à reconfigurer chaque étape séparément.

Le repli automatique d'un fournisseur vers le suivant, au sein d'une même chaîne, doit être déclenché uniquement par une indisponibilité constatée du fournisseur courant (erreur réseau, quota/limite de taux, échec d'authentification) — jamais par préférence ou round-robin. Le système ne doit jamais basculer vers un fournisseur absent de la chaîne configurée pour cette étape, ni vers ou depuis le mode local si celui-ci n'en fait pas partie. Si tous les fournisseurs d'une chaîne sont indisponibles au moment d'une opération, le système doit le détecter explicitement (équivalent de isAvailableLocally pour un fournisseur distant) et guider l'utilisateur, sans jamais inventer de résultat de repli non consenti. Chaque bascule effective entre fournisseurs au sein d'une chaîne doit rester visible pour l'utilisateur — journalisée localement et indiquée clairement dans l'interface — sans nécessiter de confirmation à chaque occurrence.

Le système doit stocker localement le résultat de tout calcul d'embedding, qu'il ait été effectué par le fournisseur distant par défaut ou par le moteur local, en conservant l'information du modèle/fournisseur ayant produit chaque vecteur stocké, afin qu'une recherche par similarité ne mélange jamais des vecteurs issus de modèles d'embedding différents et incompatibles entre eux. Au premier lancement de l'outil, et à chaque changement de configuration des chaînes de fournisseurs, le système doit afficher de façon claire et proéminente — pas seulement lors d'une action inhabituelle — que le code source, les fragments cités et les questions de chat sont envoyés par défaut vers des services tiers, la liste précise des fournisseurs concernés par défaut, et la marche à suivre exacte pour repasser en mode entièrement local. L'analyse statique du dépôt (parsing, extraction de symboles, graphe de dépendances) et le caractère lecture seule du dépôt analysé ne sont affectés par aucun changement de cette feature. La traçabilité des réponses IA vers les symboles/fichiers sources cités reste inchangée quel que soit le fournisseur ayant effectivement traité la requête.

Critères de succès : (1) sur une installation neuve sans configuration, une commande d'indexation affiche d'abord la divulgation complète, puis route effectivement les résumés et le chat vers Groq et les embeddings vers OpenAI text-embedding-3, sans qu'aucune étape ne nécessite de configuration manuelle préalable ; (2) une seule commande de configuration bascule les trois chaînes vers le mode entièrement local, après quoi une nouvelle indexation ne produit plus aucun appel réseau sortant vers un fournisseur distant ; (3) une chaîne configurée avec deux fournisseurs distants pour une étape donnée, soumise à l'indisponibilité simulée du premier, bascule automatiquement vers le second et produit une entrée de journal horodatée et une indication visible de la bascule, sans jamais solliciter un fournisseur absent de la chaîne ; (4) des embeddings calculés via OpenAI puis via le moteur local sur le même dépôt sont retrouvables correctement chacun de leur côté, et une recherche par similarité ne retourne jamais un résultat mélangeant silencieusement des vecteurs de modèles différents."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get useful results on a fresh install with zero configuration (Priority: P1)

Someone installs the tool for the first time and, before touching any
configuration, runs the command that indexes a repository. They first see a
clear, prominent notice that their source code, cited fragments, and chat
questions will be sent to specific named third-party services by default,
plus exactly how to opt back into a fully local mode. After that notice,
indexing proceeds and actually produces summaries, embeddings, and (later)
chat answers using those default services — without the user having picked
a provider for anything.

**Why this priority**: This is the core value proposition of the whole
feature: a tool that works well out of the box on modest hardware, with
informed consent about where data goes, rather than requiring upfront
provider setup or silently defaulting to something slow and local. Every
other story in this feature builds on this default configuration existing.

**Independent Test**: On a machine with no prior configuration, run the
indexing command and confirm the disclosure appears first (naming the
default providers and the way back to local-only), and that summaries, chat
answers, and embeddings are all actually produced using their respective
default providers with no manual provider setup required beforehand.

**Acceptance Scenarios**:

1. **Given** a fresh installation with no prior configuration, **When** the
   user runs the indexing command, **Then** a clear, prominent disclosure
   appears before any data leaves the machine, naming the exact default
   provider for each of the three AI-consuming stages and explaining how to
   switch to fully local mode.
2. **Given** that disclosure has been shown, **When** indexing proceeds,
   **Then** code summaries and embeddings are actually produced through
   their respective default remote providers, with no provider selection
   step required from the user.
3. **Given** a freshly indexed repository with default configuration,
   **When** the user asks a chat question, **Then** the answer is generated
   through the default remote chat provider, again with no manual setup.
4. **Given** the same repository and configuration, **When** the indexing
   command is run again later, **Then** the disclosure is not required to
   block every run indefinitely — it is shown at first launch and again
   whenever the provider-chain configuration actually changes, not on every
   unchanged run.

---

### User Story 2 - Switch everything to fully local in one action (Priority: P2)

A user decides the default arrangement doesn't fit their needs (privacy,
offline work, no third-party accounts) and wants every AI-consuming stage —
embeddings, code summaries, and chat — to run entirely on their own machine.
They run a single configuration action, and from that point on, none of the
three stages calls out to a remote service anymore.

**Why this priority**: This is the safety valve that makes the new
remote-by-default posture acceptable: a user who wants the old all-local
guarantee back must be able to get it in one clearly documented step, not by
hunting through three separate settings. It's the second most important
story because it's the direct mitigation for the biggest risk the new
default introduces.

**Independent Test**: Starting from default (remote) configuration, run the
one local-mode configuration action, then run a full indexing pass and
confirm no outbound network call to any remote AI provider occurs for any
of the three stages, and that local equivalents (embeddings, summarization,
chat) are used successfully instead.

**Acceptance Scenarios**:

1. **Given** a repository configured with default (remote) provider chains,
   **When** the user runs the single "switch to fully local" configuration
   action, **Then** all three stages' provider chains are updated to use
   only the local engine, without the user touching each stage's
   configuration separately.
2. **Given** that switch has been made, **When** a new indexing run and a
   new chat question are performed, **Then** neither produces any outbound
   call to a remote AI provider, and both complete successfully using local
   engines.
3. **Given** the switch to fully local has been made, **When** the user
   inspects the current configuration, **Then** it clearly shows all three
   chains now contain only the local engine, with no default remote
   provider silently remaining.

---

### User Story 3 - Keep working automatically when a configured remote provider becomes unavailable (Priority: P2)

A user has deliberately configured a stage's chain with more than one
remote provider (for example, to avoid being stuck when a free-tier rate
limit is hit). During normal use, the first provider in that chain becomes
unavailable — a network error, an authentication failure, or a rate limit
being hit. Instead of the operation simply failing, the system automatically
tries the next provider in that same chain, the operation completes, and the
user can clearly see, afterward, that a switch happened and why.

**Why this priority**: Automatic continuity within a configuration the user
explicitly set up is what makes a multi-provider chain worth configuring at
all — without it, a chain is just a list nobody benefits from. It ranks
alongside the local-mode switch as a core trust-and-reliability mechanism,
just one layer more advanced than the zero-config default experience.

**Independent Test**: Configure a stage's chain with two remote providers,
simulate the first one being unavailable (network failure, rate limit, or
authentication failure), perform an operation for that stage, and confirm
the operation succeeds via the second provider, with a timestamped local log
entry and a clear, visible indication of the switch — without any
confirmation prompt being required.

**Acceptance Scenarios**:

1. **Given** a stage's chain configured with Provider A first and Provider B
   second, **When** Provider A is unavailable (network error, rate limit, or
   authentication failure) at the moment of an operation, **Then** the
   system automatically retries that operation against Provider B without
   failing the operation outright.
2. **Given** that automatic switch just happened, **When** the user checks
   afterward, **Then** a timestamped local log entry records the switch and
   its reason, and a clear indication of the switch is visible without
   requiring the user to have confirmed it in the moment.
3. **Given** a chain that does not include a given provider, **When** every
   provider actually in that chain is unavailable, **Then** the system never
   attempts that excluded provider and never silently switches to or from
   local mode unless local mode is itself part of the configured chain.
4. **Given** every provider in a stage's configured chain is unavailable at
   once, **When** an operation for that stage is attempted, **Then** the
   system explicitly detects that no provider in the chain can serve the
   request and clearly guides the user toward a resolution, rather than
   inventing or guessing a result.

---

### User Story 4 - Never let mismatched embeddings corrupt a search (Priority: P3)

A user has embeddings for the same repository computed at different times by
different providers — for example, some computed by the default remote
embedding provider, then more computed later by a local embedding engine
after switching modes. When they search the codebase by similarity, results
never blend vectors from incompatible embedding models together, even
though both sets of vectors live in the same local storage.

**Why this priority**: This is a correctness safeguard rather than a
day-to-day visible feature — it matters most as a consequence of stories 2
and 3 (switching providers, or failing over to a different provider that
also does embeddings) actually happening, so it's appropriately lower
priority, but a violation of it would silently degrade search quality in a
way a user might never notice without this guarantee.

**Independent Test**: Compute embeddings for a repository with one provider,
then compute more with a different provider (via a mode switch), then run a
similarity search and confirm every returned result is consistent — the
search never returns a set of results computed by mismatched embedding
models as if they were comparable.

**Acceptance Scenarios**:

1. **Given** embeddings already stored from one provider/model, **When**
   more embeddings are computed later using a different provider/model,
   **Then** each stored vector retains a record of exactly which
   provider/model produced it.
2. **Given** a repository with vectors from more than one embedding
   provider/model stored locally, **When** a similarity search is
   performed, **Then** the results are drawn consistently from one
   compatible embedding space, never a silent blend of incompatible models.
3. **Given** vectors from an earlier provider/model that are no longer the
   currently configured one, **When** they are not part of a given search's
   result set, **Then** they remain intact in storage rather than being
   silently discarded, so they stay available if that provider/model is
   configured again later.

---

### Edge Cases

- What happens when a user configures a chain with the local engine as the
  *only* entry (no remote provider at all) for one stage, while leaving
  another stage on defaults? Each of the three chains is configured
  independently outside the one-shot "switch everything to local" action;
  a partially-local configuration is valid and must work exactly as
  configured, without forcing the other stages to change.
- What happens if a user adds the same provider twice to one chain, or adds
  a provider immediately after itself? The chain still behaves predictably —
  duplicate/adjacent identical entries don't create infinite retry loops or
  ambiguous state; the system MUST validate that the local guard against
  unwanted engine switches actually matches configured chains.
- What happens when a remote provider fails partway through producing a
  chat answer that had already started streaming a partial response? The
  in-progress operation's failure/fallback behavior for that partial output
  is governed by the existing chat-streaming behavior; this feature governs
  which provider is chosen and how failover across the chain is decided and
  disclosed, not how a partially-streamed answer itself is displayed.
- What happens to embeddings already computed under the old, pre-existing
  single-provider configuration when this feature is first introduced?
  They remain valid, retrievable local data; they are treated as having been
  produced by whichever provider/model actually computed them, and are not
  silently discarded or force-migrated.
- What happens when a user manually edits stored configuration into an
  invalid state (e.g., an empty chain for a stage)? The system must detect
  this the same way as "every provider unavailable" — explicit detection
  and clear guidance — rather than crashing or guessing a provider.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For each of the three AI-consuming stages (embeddings, code
  summarization, chat answer generation), the system MUST support an
  ordered list ("chain") of providers for that stage, rather than a single
  configured provider.
- **FR-002**: On a fresh installation with no user configuration, each
  stage's chain MUST already contain exactly one default remote provider:
  a text-embedding-3-class OpenAI provider for embeddings, and a Groq
  provider for both code summarization and chat answer generation.
- **FR-003**: The fully local option (a local embedding engine and a local
  inference engine, alongside the already-local static analysis) MUST
  remain fully supported for each of the three stages, but MUST NOT appear
  in any stage's chain unless the user explicitly adds it.
- **FR-004**: The system MUST provide a single configuration action that
  switches all three stages' chains to contain only the local engine, so
  the user does not need to reconfigure each stage separately to achieve a
  fully local setup.
- **FR-005**: Within a stage's chain, the system MUST automatically retry
  an operation against the next provider in that same chain only when the
  current provider is confirmed unavailable (network error, rate/quota
  limit, or authentication failure) — never based on preference, load
  balancing, or round-robin selection.
- **FR-006**: The system MUST NEVER attempt a provider that is not present
  in the chain configured for that stage, and MUST NEVER switch to or from
  the local engine for a stage unless the local engine is itself part of
  that stage's configured chain.
- **FR-007**: When every provider in a stage's configured chain is
  unavailable at the moment of an operation, the system MUST explicitly
  detect that condition and guide the user toward a resolution, rather than
  producing a fabricated or guessed result.
- **FR-008**: Every actual switch from one provider to another within a
  chain MUST be recorded in a timestamped local log entry and MUST be
  clearly and visibly indicated to the user through the interface relevant
  to the operation that triggered it, without requiring the user to confirm
  the switch in the moment it happens.
- **FR-009**: Every embedding vector persisted locally MUST retain a record
  of exactly which provider and model produced it, regardless of whether
  that was the default remote provider, a fallback remote provider, or the
  local engine.
- **FR-010**: A similarity search MUST NEVER return a result set that
  blends vectors produced by different, incompatible embedding
  providers/models as if they were directly comparable; vectors from a
  provider/model other than the one currently relevant to the search MUST
  be excluded from that search's comparisons rather than compared anyway.
- **FR-011**: Embedding vectors produced by a provider/model that is no
  longer part of the current configuration MUST remain stored and intact,
  not deleted, so they remain available if that provider/model is
  reconfigured later.
- **FR-012**: At first launch, and at every point where a stage's
  provider-chain configuration actually changes, the system MUST display a
  clear and prominent disclosure — not only when the user picks an unusual
  option — stating that source code, cited fragments, and chat questions
  are sent to third-party services by default, naming the exact default
  providers involved, and explaining precisely how to switch to fully local
  mode.
- **FR-013**: The disclosure required by FR-012 MUST be shown before any
  data leaves the machine for the operation that triggered it, and MUST
  block that operation until the user explicitly acknowledges it — at first
  launch, and again at every point a stage's provider-chain configuration
  actually changes. Once acknowledged for the configuration currently in
  effect, a subsequent run with that same, unchanged configuration proceeds
  without re-showing the blocking gate.
- **FR-014**: Static analysis of the repository (parsing, symbol
  extraction, dependency graph construction) and the read-only treatment of
  the analyzed repository MUST remain entirely unaffected by this feature —
  neither is a provider-chain-consuming stage and neither changes behavior
  based on any of the configuration introduced here.
- **FR-015**: Traceability of an AI-generated answer or summary back to the
  specific source symbols/files that justify it MUST remain unchanged
  regardless of which provider in a chain actually produced that answer or
  summary.

### Key Entities

- **Provider Chain**: An ordered list of providers configured for exactly
  one AI-consuming stage (embeddings, code summarization, or chat answer
  generation). Defines the order in which providers are attempted for that
  stage's operations. Each of the three stages has its own independent
  chain.
- **Provider**: A named source of AI capability for a given stage — either
  a specific remote service (e.g., the default OpenAI embedding provider,
  the default Groq provider, or another remote provider a user adds) or the
  local engine for that stage. A provider belongs to zero or more stages'
  chains depending on what capability it offers.
- **Fallback Event**: A record of one actual switch from one provider to
  the next within a stage's chain during a real operation — capturing when
  it happened, which stage, which provider was left, which provider was
  used instead, and the detected reason (network error, rate/quota limit,
  or authentication failure).
- **Embedding Vector Record**: A locally stored embedding result for a
  piece of indexed content, tagged with exactly which provider and model
  produced it, so later similarity searches and future re-computation can
  tell compatible vectors apart from incompatible ones.
- **Provider Disclosure**: The notice shown at first launch and at every
  provider-chain configuration change, naming the default third-party
  providers in use and the exact steps to switch to fully local mode.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh installation with no configuration performed by
  the user, running the indexing command first displays the full
  disclosure, then actually routes code summaries and chat answers to the
  default remote provider and embeddings to the default remote embedding
  provider — with zero manual provider configuration steps required for any
  of the three stages.
- **SC-002**: A single configuration action switches all three stages to
  fully local mode, after which a subsequent indexing run produces zero
  outbound network calls to any remote AI provider.
- **SC-003**: When a stage's chain is configured with two remote providers
  and the first becomes unavailable, the system automatically completes the
  operation via the second provider, producing one timestamped log entry
  and one visible indication of the switch, and at no point attempts a
  provider absent from that chain.
- **SC-004**: Embeddings computed for the same repository via two different
  providers/models remain each independently retrievable, and a similarity
  search performed afterward never returns a result mixing vectors from
  different, incompatible embedding models.
- **SC-005**: 100% of actual provider switches across all three stages
  produce both a local log entry and a user-visible indication, with no
  observed case of a silent, undisclosed switch during testing.
- **SC-006**: Every configuration-change event for any of the three chains
  results in the disclosure notice being shown, and the notice always names
  the correct current default/configured providers at that time.

## Assumptions

- Supplying the credentials a chosen remote provider needs (for example, an
  API key) is a standard, expected setup step for using that remote
  provider at all, and is not itself considered "manual provider
  configuration" in the sense FR-002/SC-001 mean by zero-configuration
  defaults — the *choice* of default provider requires no configuration;
  authenticating to that provider's service does, the same way any
  third-party API integration does.
- Reverting from fully local mode back to the default remote chains is not
  required to be a single dedicated action by this feature; the existing
  per-stage configuration mechanism remains available for that direction.
  The one-shot action required by FR-004/SC-002 is specifically for
  switching *to* fully local, since that is the direction the constitution
  requires to remain a lightweight, one-step safety valve.
- Provider availability for the purpose of automatic failover (FR-005) is
  (re-)evaluated at the start of each individual operation, beginning again
  from the first provider in that stage's configured chain — a provider
  that failed on one operation is retried first on the next operation,
  rather than being persistently skipped until a manual reset. This matches
  the constitution's framing of an availability check performed per
  operation (`isAvailableLocally`/equivalent), not a sticky, session-level
  choice.
- The "interface" through which a fallback switch (FR-008) or the
  disclosure (FR-012) must be visible is whichever interface already
  surfaces that stage's operation: the command-line output for an indexing
  run (embeddings and code-summarization stages), and the chat interface's
  response/session for the chat stage. This feature does not introduce a
  new, separate interface solely for these notices.
- Switching a stage's chain to a different provider/model does not trigger
  an automatic, full re-computation of previously stored embeddings under
  the new model — consistent with the existing incremental re-indexing
  principle, existing vectors remain as valid historical data (FR-011) and
  are only replaced as content is naturally reprocessed going forward.
- The specific default Groq model (for summarization and chat) and the
  specific default OpenAI text-embedding-3 variant are implementation
  choices to be finalized during planning, not business-level decisions
  this specification needs to pin down beyond "a Groq-hosted provider" and
  "a text-embedding-3-class OpenAI provider."
- A "provider" for chain-configuration purposes is distinguished by both
  the service and the specific model used, since two different models from
  the same service can be as mutually incompatible for embeddings as models
  from two different services.

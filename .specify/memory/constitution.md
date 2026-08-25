<!--
Sync Impact Report
- Version change: 2.0.0 -> 3.0.0
- Modified principles:
  - 2.1 Confidentialite par defaut, moteur distant seulement sur choix
    explicite -> 2.1 Moteur distant par defaut, mode local disponible sur
    choix explicite (MAJOR, breaking: reverses the previous absolute
    guarantee that code summarization and embeddings always stay local
    "sans exception... non negociable... n'est concerne par aucune
    configuration". A configured remote provider is now the DEFAULT for
    all three AI-consuming stages - code summarization, embeddings, and
    chat answer generation - not only chat. Local-only (Ollama) remains
    fully supported but is now an explicit opt-in rather than the
    untouchable baseline. Static analysis (Tree-sitter parsing, symbol
    extraction, dependency graph construction) is unaffected either way:
    it never called any model and stays local by construction, not by
    policy choice.)
  - 2.3 Jamais de repli silencieux vers le cloud -> 2.3 Repli automatique
    seulement au sein d'une chaine de moteurs explicitement configuree
    (MAJOR: the previous version forbade ANY automatic switch between
    configured engines, with no exception. This version permits automatic
    failover, per AI-consuming stage, strictly within an explicit,
    user-ordered list of providers for that stage - e.g. Groq then a
    second configured provider if Groq rate-limits or errors. Falling
    back to a provider not on that list, or to/from local mode when local
    is not itself a member of the configured list, remains forbidden
    without the user changing configuration first. Every automatic
    failover MUST still be visible to the user, not silent in practice.)
- Added sections: none (2.1's disclosure requirement is strengthened
  in place, not split into a new principle)
- Removed sections: none
- Rationale: operator-reported hardware constraints (weak CPU/GPU) made
  local Ollama inference impractically slow for indexing and chat alike.
  Decided directly with the user on 2026-08-25, with explicit scope
  confirmation (all three stages move to remote-by-default; real
  automatic fallback across multiple remote providers is in scope) before
  this amendment was drafted.
- Deferred items: the actual pipeline/config/CLI implementation of this
  amendment (default provider wiring, the ordered-fallback-list
  mechanism, a remote embedding provider since Groq offers none, and the
  strengthened first-run/config-time disclosure UX) is intentionally NOT
  done by this amendment - it follows as a separate spec-kit feature.
-->

# Constitution du projet

## 1. Objectif

Ce projet est un outil local de generation automatique de documentation de code,
avec un pipeline d'indexation statique, d'embeddings, d'inference IA, et une
interface de chat en langage naturel sur le code analyse - les etapes qui
consomment un modele d'IA (embeddings, resume, chat) utilisent par defaut un
ou plusieurs moteurs distants configures, avec un mode entierement local
disponible sur choix explicite.

## 2. Principes

### 2.1 Moteur distant par defaut, mode local disponible sur choix explicite

L'analyse statique du depot (parsing Tree-sitter, extraction de symboles,
construction du graphe de dependances) ne fait appel a aucun modele d'IA et
reste locale dans tous les cas - ce n'est pas une politique configurable,
c'est simplement qu'aucune de ces etapes n'a jamais besoin d'un service
externe.

Pour les trois etapes qui consomment effectivement un modele d'IA - le calcul
des embeddings (Partie 3.2), le resume de code genere pendant l'indexation
(Partie 3.3), et la generation de reponses du chat (Partie 3.1, `LLMEngine`) -
un ou plusieurs moteurs distants (API cloud, par exemple Groq pour
l'inference; un autre fournisseur pour les embeddings, Groq n'en proposant
pas) sont utilises **par defaut**. Le code source, les fragments cites, les
questions posees et les embeddings calcules transitent donc vers ces services
tiers par defaut.

Un mode entierement local (Tree-sitter deja local par nature, plus un moteur
d'embeddings et un moteur d'inference locaux, par exemple via Ollama) reste
disponible et pleinement supporte pour chacune des trois etapes, mais doit
etre choisi explicitement par l'utilisateur - il n'est plus le comportement
par defaut.

Que ce soit au premier lancement ou a tout changement de configuration, le
systeme DOIT indiquer de maniere claire et proeminente - pas seulement quand
l'utilisateur choisit une option inhabituelle - que le code source, les
embeddings et le contenu du chat sont envoyes vers des services tiers par
defaut, et DOIT documenter clairement comment repasser en mode entierement
local pour l'utilisateur qui souhaite retrouver l'ancienne garantie de
confidentialite absolue.

Raison: le code analyse peut contenir des informations sensibles ou privees,
et cet arbitrage doit rester une decision eclairee de l'utilisateur - mais
sur du materiel modeste, l'inference et les embeddings locaux deviennent
impraticablement lents pour l'indexation comme pour le chat; le moteur
distant devient donc le chemin par defaut, a condition que la divulgation
reste claire et que le mode local reste toujours accessible en une
configuration explicite.

### 2.2 Zero exposition reseau par defaut

Tout serveur web du projet est lie a `127.0.0.1` par defaut. Aucune exposition
reseau externe n'est autorisee sans action explicite de l'utilisateur.

Raison: le projet doit rester isole localement tant que l'utilisateur n'a pas
choisi autrement. Ce principe concerne l'exposition entrante du serveur web
local; il est independant des appels sortants vers des moteurs distants
prevus par 2.1.

### 2.3 Repli automatique seulement au sein d'une chaine de moteurs explicitement configuree

Pour chaque etape consommant un modele d'IA (embeddings, resume, chat), le
systeme peut basculer automatiquement d'un moteur vers le suivant
**uniquement au sein d'une liste ordonnee de moteurs que l'utilisateur a
lui-meme configuree pour cette etape** (par exemple: Groq en premier, puis un
second fournisseur distant si Groq est indisponible ou limite en taux). Ce
repli automatique n'est jamais silencieux en pratique: chaque bascule DOIT
rester visible pour l'utilisateur (journalisation ou indication claire),
meme si elle ne requiert pas de confirmation a chaque occurrence.

Le systeme ne bascule jamais automatiquement vers un moteur absent de cette
liste configuree, ni vers ou depuis le mode local si celui-ci n'en fait pas
partie, sans que l'utilisateur ait lui-meme modifie la configuration au
prealable. Si tous les moteurs de la liste configuree sont indisponibles, le
systeme doit le detecter explicitement via `isAvailableLocally` /
l'equivalent pour un moteur distant, et guider l'utilisateur vers la
resolution plutot que d'inventer un repli non consenti.

Raison: sur du materiel modeste ou face aux limites de taux d'un fournisseur
gratuit, un repli automatique entre plusieurs moteurs distants preconfigures
est necessaire pour rester utilisable - mais la previsibilite reste
prioritaire: l'utilisateur doit toujours savoir, a l'avance, l'ensemble des
moteurs susceptibles de traiter ses donnees, jamais decouvrir apres coup
qu'un moteur non choisi a ete utilise.

### 2.4 Traçabilite des reponses IA

Toute reponse generee par IA, y compris un resume de module ou une reponse de
chat, doit pouvoir etre rattachee aux fragments de code source qui la justifient
via des citations de symboles et de fichiers.

Raison: la documentation doit etre verifiable et audit-able.

### 2.5 Re-indexation incrementale

Le systeme ne doit jamais re-analyser l'integralite du depot a chaque
modification. Seuls les fichiers ou symboles impactes sont retraités.

Raison: le pipeline doit rester rapide et economique en calcul local.

### 2.6 Infrastructure minimale et stockage local

Aucune dependance a une infrastructure lourde n'est admise: pas de serveur de
base de donnees externe, pas de broker de messages, pas de composant cloud
pour le stockage. Le stockage embarque uniquement est autorise, avec SQLite
et un index vectoriel local sur fichier - y compris pour des embeddings
calcules par un moteur distant (2.1): le resultat est toujours persiste
localement, seul le calcul peut avoir lieu a distance.

Raison: la portabilite et le fonctionnement hors ligne des donnees deja
indexees restent des objectifs structurants, independamment de l'endroit ou
l'inference ou le calcul d'embeddings a lieu.

### 2.7 Depot analyse en lecture seule

Le depot de code analyse reste en lecture seule. L'outil n'ecrit jamais dans le
code source du projet analyse. La seule ecriture autorisee concerne la
documentation generee, dans un dossier separe du depot source.

Raison: l'outil doit etre non invasif et ne pas modifier la base de code
observee.

## 3. Gouvernance

### 3.1 Procedure de modification

Toute modification de cette constitution passe par une mise a jour explicite du
fichier constitution. Chaque changement doit preciser la raison du changement
et l'impact sur les principes existants.

### 3.2 Versioning

La version suit le format SemVer `MAJOR.MINOR.PATCH`.

- MAJOR: changement incompatible avec un principe existant ou suppression d'un
  principe.
- MINOR: ajout d'un principe ou extension materielle d'un principe existant.
- PATCH: clarification, correction de forme, ou precision sans changement de
  politique.

### 3.3 Revue de conformite

Toute nouvelle fonctionnalite, tout nouveau flux d'indexation, toute nouvelle
integration de modele, et toute exposition de service doit etre verifie contre
les principes ci-dessus avant implementation.

### 3.4 Date de ratification

Date de ratification initiale: 2026-08-10.

Version 3.0.0 - derniere modification: 2026-08-25 (voir Sync Impact Report
en tete de fichier - le moteur distant devient le chemin par defaut pour
les embeddings, le resume de code, et le chat, avec repli automatique
possible au sein d'une chaine de moteurs distants explicitement configuree;
le mode entierement local reste disponible en choix explicite).


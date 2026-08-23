<!--
Sync Impact Report
- Version change: 1.0.0 -> 2.0.0
- Modified principles:
  - 2.1 Confidentialite absolue -> 2.1 Confidentialite par defaut, moteur
    distant seulement sur choix explicite (MAJOR: the previous version
    forbade any code/prompt/metadata leaving the machine with no exception;
    this version carves out a narrow, opt-in exception for a remote/cloud
    LLM engine used for chat answer generation only, never on by default)
  - 2.3 Jamais de repli silencieux vers le cloud -> reworded to cover
    switching between any configured engines (local<->remote), not just a
    local-only baseline; the "never silent, never automatic" guarantee
    itself is unchanged and still absolute
- Added sections: none
- Removed sections: none
- Rationale: feature 026 (chat streaming) explicitly requires an optional
  GroqLLMEngine alongside LocalLLMEngine, decided via /speckit-plan
  clarification on 2026-08-19 after the constitutional conflict was raised.
- Deferred items: none
-->

# Constitution du projet

## 1. Objectif

Ce projet est un outil local de generation automatique de documentation de code,
avec un pipeline d'indexation statique, d'embeddings locaux, d'inference IA
locale, et une interface de chat en langage naturel sur le code analyse.

## 2. Principes

### 2.1 Confidentialite par defaut, moteur distant seulement sur choix explicite

Par defaut, aucune ligne de code source, aucun resume genere, aucun embedding,
ni aucune metadonnee derivee du code analyse ne doit transiter vers un service
tiers ou une API cloud. L'analyse statique, la vectorisation et l'indexation
s'executent toujours localement, sans exception: Tree-sitter local et moteur
d'embeddings local uniquement - ceci n'est pas negociable et n'est concerne par
aucune configuration.

Pour la generation de reponses du chat uniquement (Partie 3.1, `LLMEngine`),
un moteur distant (par exemple une API cloud comme Groq) peut etre utilise en
plus du moteur local, mais seulement si l'utilisateur le configure
explicitement - jamais par defaut, jamais choisi automatiquement par le
systeme. Au moment ou l'utilisateur configure un moteur distant, le systeme
doit indiquer clairement que ce choix envoie le texte des questions posees et
le contexte de code cite dans les reponses vers un service tiers.

Raison: le code analyse peut contenir des informations sensibles ou privees;
l'analyse/l'indexation restent une garantie absolue, tandis que la generation
de reponses de chat est le seul point ou l'utilisateur peut choisir en
connaissance de cause d'echanger de la confidentialite contre l'usage d'un
modele distant.

### 2.2 Zero exposition reseau par defaut

Tout serveur web du projet est lie a `127.0.0.1` par defaut. Aucune exposition
reseau externe n'est autorisee sans action explicite de l'utilisateur.

Raison: le projet doit rester isole localement tant que l'utilisateur n'a pas
choisi autrement.

### 2.3 Jamais de repli silencieux vers le cloud

Si le moteur LLM configure (local, ou distant si explicitement choisi par
l'utilisateur - voir 2.1) est indisponible, le systeme doit le detecter
explicitement via `isAvailableLocally` et guider l'utilisateur vers la
resolution (demarrage du service local, ou verification de la configuration
du moteur distant selon le cas). Le systeme ne bascule jamais automatiquement
d'un moteur configure vers un autre - notamment jamais du moteur local vers
un moteur distant, ni l'inverse - sans que l'utilisateur ait lui-meme change
la configuration au prealable. Un moteur distant n'est jamais utilise comme
roue de secours silencieuse quand le moteur local est indisponible.

Raison: la confidentialite et le comportement previsible restent prioritaires;
autoriser un moteur distant explicite (2.1) ne doit jamais degenerer en repli
automatique non consenti.

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
base de donnees externe, pas de broker de messages, pas de composant cloud.
Le stockage embarque uniquement est autorise, avec SQLite et un index vectoriel
local sur fichier.

Raison: la portabilite et le fonctionnement hors ligne sont des objectifs
structurants.

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

Version 2.0.0 - derniere modification: 2026-08-19 (voir Sync Impact Report
en tete de fichier - ajout d'une exception explicite et opt-in pour un
moteur LLM distant, feature 026).


<!--
Sync Impact Report
- Version change: none -> 1.0.0
- Modified principles: none (new constitution)
- Added sections: Objective, Principles, Governance
- Removed sections: none
- Deferred items: none
-->

# Constitution du projet

## 1. Objectif

Ce projet est un outil local de generation automatique de documentation de code,
avec un pipeline d'indexation statique, d'embeddings locaux, d'inference IA
locale, et une interface de chat en langage naturel sur le code analyse.

## 2. Principes

### 2.1 Confidentialite absolue

Aucune ligne de code source, aucun resume genere, aucun embedding, ni aucune
metadonne derivee du code analyse ne doit transiter vers un service tiers ou une
API cloud. Toute l'analyse statique, la vectorisation, l'indexation et
l'inference LLM s'executent localement, avec Tree-sitter local, moteur
d'embeddings local, et LLM local expose sur `localhost` via Ollama ou
`llama.cpp`.

Raison: le code analyse peut contenir des informations sensibles ou privees.

### 2.2 Zero exposition reseau par defaut

Tout serveur web du projet est lie a `127.0.0.1` par defaut. Aucune exposition
reseau externe n'est autorisee sans action explicite de l'utilisateur.

Raison: le projet doit rester isole localement tant que l'utilisateur n'a pas
choisi autrement.

### 2.3 Jamais de repli silencieux vers le cloud

Si le modele LLM local est indisponible, le systeme doit le detecter
explicitement via `isAvailableLocally` et guider l'utilisateur vers
l'installation ou le demarrage du service local. Aucun repli vers un service
externe, meme temporaire, n'est autorise.

Raison: la confidentialite et le comportement previsibles sont prioritaires.

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


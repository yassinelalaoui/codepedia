<!--
Sync Impact Report
- Version change: 3.0.0 -> 4.0.0
- Modified principles:
  - 2.1 Moteur distant par defaut, mode local disponible sur choix
    explicite -> 2.1 Execution locale exclusive (MAJOR, breaking: reverses
    3.0.0 entirely. A remote engine is no longer the default, no longer an
    option, and no longer present in the code: the Groq inference transport,
    the OpenAI embedding transport, the provider chains and the API-key
    handling were all removed. The three AI-consuming stages - embeddings,
    code summarization, chat answer generation - run against a local runtime
    (Ollama) or do not run. The first-run disclosure required by 3.0.0 is
    removed with the thing it disclosed: no repository content leaves the
    machine, so there is nothing to disclose and no consent to record.)
  - 2.3 Repli automatique seulement au sein d'une chaine de moteurs
    explicitement configuree -> 2.3 Un seul moteur par etape, aucun repli
    (MAJOR: 3.0.0 permitted automatic failover within a user-ordered list of
    providers per stage. There are no lists any more. Each stage has exactly
    one engine; when it is unavailable the system says so and stops. The
    `engine_failover_log` table and the `/providers/failover-log` endpoint
    are removed, as is the `codepedia provider` command group.)
- Added sections: none
- Removed sections: none
- Rationale: decided directly with the operator on 2026-09-23, reversing the
  2026-08-25 amendment. The hardware argument that motivated 3.0.0 has not
  changed - local inference on this machine is still slow - but the operator
  chose privacy and simplicity over speed, and chose to remove the remote
  path outright rather than leave it configurable. The cost is accepted and
  recorded: indexing is slower, and the Overview narrative produced by a
  small local model may fail its grounding checks.
- Consequence for 2.5: changing the configured embedding model invalidates
  every stored vector for that repository, because vectors from two models
  are not comparable. This is a re-embedding, not a re-analysis: static
  analysis, code summaries and the Overview narrative all survive.
-->

# Constitution du projet

## 1. Objectif

Ce projet est un outil local de generation automatique de documentation de code,
avec un pipeline d'indexation statique, d'embeddings, d'inference IA, et une
interface de chat en langage naturel sur le code analyse - toutes les etapes,
y compris celles qui consomment un modele d'IA (embeddings, resume, chat),
s'executent sur la machine de l'utilisateur.

## 2. Principes

### 2.1 Execution locale exclusive

L'analyse statique du depot (parsing Tree-sitter, extraction de symboles,
construction du graphe de dependances) ne fait appel a aucun modele d'IA et
reste locale dans tous les cas - ce n'est pas une politique configurable,
c'est simplement qu'aucune de ces etapes n'a jamais besoin d'un service
externe.

Les trois etapes qui consomment effectivement un modele d'IA - le calcul des
embeddings (Partie 3.2), le resume de code genere pendant l'indexation
(Partie 3.3), et la generation de reponses du chat (Partie 3.1, `LLMEngine`) -
s'executent **exclusivement** sur un runtime local (Ollama). Aucun moteur
distant n'est configurable, et aucun code permettant d'en appeler un ne
subsiste dans le projet: le transport Groq, le transport d'embeddings OpenAI,
les chaines de fournisseurs et la lecture de cles d'API ont ete supprimes.

Le code source, les fragments cites, les questions posees et les embeddings
calcules ne quittent jamais la machine. Il n'y a donc aucune divulgation a
faire ni aucun consentement a recueillir: la garantie est structurelle, pas
configuree. Un ecran d'avertissement au premier lancement serait trompeur,
puisqu'il n'existe aucun reglage capable de l'invalider.

Raison: le code analyse peut contenir des informations sensibles ou privees.
La version 3.0.0 avait fait du moteur distant le chemin par defaut au nom de
la vitesse sur du materiel modeste; cet arbitrage est annule. La lenteur de
l'inference locale est acceptee et documentee comme le prix de la garantie.

### 2.2 Zero exposition reseau par defaut

Tout serveur web du projet est lie a `127.0.0.1` par defaut. Aucune exposition
reseau externe n'est autorisee sans action explicite de l'utilisateur.

Raison: le projet doit rester isole localement tant que l'utilisateur n'a pas
choisi autrement. Ce principe concerne l'exposition entrante du serveur web
local. Depuis 4.0.0 il n'existe plus d'appel sortant a couvrir: 2.1 a supprime
les moteurs distants, donc les deux sens du reseau sont fermes par defaut.

### 2.3 Un seul moteur par etape, aucun repli

Chaque etape consommant un modele d'IA (embeddings, resume, chat) utilise
exactement un moteur, designe par un nom de modele dans la configuration. Il
n'existe pas de liste ordonnee, pas de bascule automatique, pas de second
moteur a essayer.

Lorsque ce moteur est indisponible - runtime arrete, modele non installe -
le systeme le detecte explicitement via `isAvailable` / `checkAvailability`,
l'annonce, et s'arrete. Il n'invente aucun repli.

Changer de modele reste possible a tout moment via `codepedia config`, mais
c'est une action de l'utilisateur, jamais une decision du systeme. Changer le
modele d'embeddings invalide les vecteurs deja stockes pour un depot: des
vecteurs produits par deux modeles differents ne sont pas comparables, et une
recherche ne melange jamais les deux. Une re-indexation les recalcule.

Raison: la previsibilite. L'utilisateur doit toujours savoir, a l'avance, quel
modele traite ses donnees. Avec un seul moteur local par etape, la reponse est
donnee par la configuration elle-meme et ne depend d'aucun evenement
d'execution.

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
et un index vectoriel local sur fichier. Le calcul comme le stockage ont
lieu sur la machine (2.1).

Raison: la portabilite et le fonctionnement hors ligne restent des objectifs
structurants. Depuis 4.0.0 ils sont acquis de bout en bout: un depot deja
indexe se consulte sans reseau, et l'indexer n'en demandait pas davantage.

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

Version 4.0.0 - derniere modification: 2026-09-23 (voir Sync Impact Report
en tete de fichier - l'execution devient exclusivement locale pour les
embeddings, le resume de code et le chat; les moteurs distants, les chaines
de fournisseurs, le repli automatique et la divulgation de premier lancement
sont supprimes du projet).


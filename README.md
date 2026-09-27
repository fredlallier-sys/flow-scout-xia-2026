# Flow Scout — X-IA 2026

Flow Scout transforme un dossier client fictif en une cartographie de gouvernance
cognitive et des IA, reliée à ses preuves, puis prépare un chargement Flow Atlas
sans prendre seul une décision bloquante.

## Démonstration rapide

Sur macOS, double-cliquer sur `Lancer_Flow_Scout_Jury.command`. Le lanceur
exécute une première analyse, ouvre la console sur `127.0.0.1` et reste actif
tant que sa fenêtre Terminal reste ouverte. Le bouton **Exécuter l’agent
complet** relance ensuite toute la chaîne locale, reconstruit Atlas v3 et
actualise automatiquement le Jury Mode.

En ligne de commande :

```bash
./scripts/run_winner_demo.sh
```

Résultat attendu : `13/13 contrôles`, `5/5 passages cohérents`, `0 appel externe`.
L'interface hors ligne se trouve aussi dans
`outputs/jury-mode/latest/index.html` et la vidéo dans
`outputs/winner-demo/Flow_Scout_2min_sexy_pro.mp4`.

Dans le Jury Mode, le bouton **Rejouer l’agent (journal NDJSON)** charge
`outputs/jury-mode/latest/replay-events-agentic.ndjson`, puis rejoue en une
minute la séquence détecter → extraire → contrôler → questionner → valider →
charger Atlas. En ouverture locale hors ligne, le même journal vérifiable est
embarqué dans la page afin que la démonstration reste disponible sans réseau.

## Checklist X-IA

- [x] démonstration locale lançable en un clic ;
- [x] journal agentique rejouable et vérifiable ;
- [x] 13/13 contrôles et cinq passages cohérents ;
- [x] export Flow Atlas v3 et traçabilité jusqu’aux cellules sources ;
- [x] vidéo autonome de deux minutes dans les livrables ;
- [ ] vérifier les noms définitifs des trois membres de l’équipe ;
- [ ] effectuer la soumission officielle et conserver son reçu.

La [checklist complète de soumission](docs/jury/SUBMISSION-CHECKLIST.md) distingue
les livrables obligatoires, les contrôles techniques et la déclaration
d’antériorité. Une URL publique reste facultative.

## Ce que montre le prototype

- ingestion d'un classeur assureur entièrement fictif ;
- construction de sept cartes reliant travail, décisions, données, systèmes,
  usages IA, valeur et transformations possibles ;
- détection d'un contrôle humain manquant et d'un écart de compétences ;
- preuve jusqu'au fichier, à la feuille et à la cellule ;
- question maïeutique, refus d'une réponse ambiguë et validation humaine ;
- génération d'un fichier Flow Atlas v3 en statut `STAGED_BLOCKED` tant que les
  validations requises ne sont pas réunies ;
- méthode Pipelex MTHDS typée et exécution bornée documentée sans secret.

## Travail antérieur et travail du hackathon

Avant le hackathon existaient la vision The Flow Fabric, le concept Flow Atlas et
les grilles de gouvernance associées. Pendant le hackathon ont été réalisés le
moteur Flow Scout démontrable, le corpus Asteria fictif, les sept cartes, la
traçabilité cellule, la boucle maïeutique, le contrôle humain, Atlas Bridge v3,
le Jury Mode, la méthode Pipelex, les évaluations et la vidéo de démonstration.

Cette séparation est déclarée conformément au règlement X-IA : l'évaluation ne
doit porter que sur la partie effectivement construite pendant le hackathon.

## Architecture du dépôt

- `backend/app/flow_scout/` : moteur autonome du prototype ;
- `backend/tests/` : tests critiques Flow Scout ;
- `methods/flow-scout-governance/` : méthode Pipelex MTHDS ;
- `integrations/` : connecteurs ciblés Dust et Gradium, sans le reste du produit ;
- `docs/references/` : données de démonstration fictives ;
- `scripts/` : rejeu, contrôles et construction du Jury Mode ;
- `scripts/serve_jury_mode.py` : console HTTP limitée au Mac et bouton de relance ;
- `outputs/winner-demo/` : vidéo, résultats, scorecards et export Atlas v3 ;
- `assets/flow-scout/` : schéma visuel de l'agent.

## Limites assumées

Prototype de hackathon, pas produit de production. Aucun secret n'est livré.
Les appels Pipelex, Dust et Gradium sont désactivés par défaut. Les données sont
fictives. Les connecteurs SI profonds, le SSO et la reconstruction complète de
Flow Atlas restent hors périmètre.

## Périmètre de propriété intellectuelle

Ce dépôt ne contient que le prototype Flow Scout destiné à l'équipe Portaland et
à l'évaluation X-IA. Il ne contient pas le plan stratégique, la documentation
commerciale, les dossiers clients, la feuille de route produit ni le reste du
système The Flow Fabric.

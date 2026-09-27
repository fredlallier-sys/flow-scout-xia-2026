# Architecture Flow Scout Winner

## Chaîne fonctionnelle

```text
Dossier client
    ↓
Surveillance et empreinte SHA-256
    ↓
Lecture CSV/XLSX et provenance cellule
    ↓
Objets métier et sept cartes liées
    ↓
Règles déterministes, constats et confiance
    ↓
Questions maïeutiques et validation humaine
    ↓
Contrat Flow Atlas v3
    ↓
Atlas Bridge : contrôle, version, chargement, retour arrière
    ↓
Cockpit Atlas en statut bloqué ou en attente d'approbation
```

## Composants

| Composant | Responsabilité | Garde-fou |
|---|---|---|
| Ingestion | Reconnaître les tableaux et leurs cellules | Aucun contenu absent n'est créé |
| Cartographie | Relier travail, décisions, données, outils, IA, valeur et transformation | Chaque constat conserve ses preuves |
| Moteur de règles | Détecter écarts et opportunités | Règles visibles et testables |
| Maïeutique | Demander les informations manquantes | Une réponse reste une déclaration avant validation |
| Cycle humain | Répondre, valider, confirmer la remédiation | Aucun contrôle bloquant n'est levé automatiquement |
| Atlas Bridge | Contrôler et charger le contrat v3 | Import atomique, versions conservées, retour arrière |
| Supervision | Rejouer et expliquer le parcours | Scores bornés, refus visible, journal complet |

## Données et preuves

- Entrées : CSV et XLSX déposés localement.
- Identité des sources : nom, taille et SHA-256.
- Preuve : fichier, feuille, cellule, valeur et identifiant stable.
- Sorties : JSON Atlas v3, classeur XLSX, espace Atlas actif et événements NDJSON.
- Exécution hackathon : locale, sans service externe et sans dépense.

## Limites assumées

Le prototype ne fournit ni SSO, ni connecteurs SI profonds, ni chiffrement géré en
production, ni politique de rétention d'entreprise. Il ne constitue pas un avis
juridique et ne revendique aucune conformité automatique. Ces sujets appartiennent
à l'industrialisation après le pilote.

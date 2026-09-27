# Évaluation automatique de la démonstration

La commande `./scripts/run_winner_demo.sh` exécute cinq fois la collecte puis contrôle
les résultats suivants :

1. une seule empreinte sémantique pour les cinq exécutions ;
2. détection du dépassement de délégation AI-002 ;
3. qualification et validation de l'écart de compétences ACT-012 ;
4. séparation du temps libéré et de l'économie budgétaire ;
5. traçabilité AI-002 jusqu'aux cellules sources ;
6. maintien du blocage après une réponse ambiguë ;
7. recalcul seulement après validation humaine et remédiation confirmée ;
8. réponse « information insuffisante » pour AI-008 ;
9. 100 % des constats reliés à une preuve ;
10. scores compris entre 0 et 100 ;
11. aucune finalisation automatique ;
12. chargement d'un espace Atlas comportant sept cartes ;
13. exécution technique en moins de cinq minutes.

Le résultat exécutable se trouve dans
`outputs/winner-demo/evaluation-scorecard.json`. Un échec produit `passed: false` et
identifie le contrôle concerné. Le score ne masque pas les questions encore ouvertes.

Une seconde sortie, `outputs/winner-demo/xia-readiness-scorecard.json`, transforme
les cinq pondérations communiquées pour le hackathon en contrôles de présence de
preuves. Elle indique le principal manque pondéré et ne se présente jamais comme
une note officielle ou une prédiction du jury. La grille reste marquée comme à
confirmer tant que le règlement authentique n'a pas été relu dans le navigateur
connecté.

# Intégrations bornées

Ces fichiers documentent les trois rôles externes du prototype sans inclure le
reste de l'application The Flow Fabric.

## Dust — retrouver les preuves

`dust/asteria-dust-evidence.ts` contient le résultat normalisé d'une exécution
Dust effectivement réalisée sur le cas Asteria. Le Jury Mode rejoue cet
instantané sans nouvel appel et sans consommation de crédit. Le mode commercial
pourra remplacer cet instantané par une interrogation Dust autorisée du corpus
client.

## Gradium — écouter et parler

`gradium/` contient le contrôleur vocal et les routes serveur : contrôle du
solde, transcription d'une commande, interprétation Flow Scout et synthèse de la
réponse. La clé `GRADIUM_API_KEY` reste côté serveur. Un appel exige une
confirmation explicite d'utilisation des crédits existants et reste désactivé
dans le rejeu hors ligne.

## Pipelex — structurer et contrôler le raisonnement

La méthode typée se trouve dans `../methods/flow-scout-governance/`. Un reçu
expurgé d'une exécution bornée est conservé dans
`../outputs/winner-demo/external-orchestration-evidence.json`. Le moteur local
reste l'autorité sur les preuves et sur les validations humaines.

Ces intégrations n'autorisent ni achat de crédit, ni dépassement, ni publication
automatique dans Flow Atlas.


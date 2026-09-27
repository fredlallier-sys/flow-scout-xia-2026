# Flow Scout Jury Mode — diffusion de la vidéo

La présentation orale est remplacée par une vidéo autonome de deux minutes.

## Avant l’envoi ou la projection

1. Ouvrir `outputs/winner-demo/Flow_Scout_2min_sexy_pro.mp4`.
2. Vérifier que la durée affichée est `2:00` et que le son est actif.
3. Regarder le début, l’anomalie AI-002, l’écran ACT-012 et la conclusion Atlas.
4. Comparer rapidement avec `Flow_Scout_2min_contact_sheet.png`.
5. Conserver une copie du MP4 et du fichier `.srt` sur une clé USB.

## Reconstruction locale

Double-cliquer sur `Construire_Video_Flow_Scout.command`. Le script recrée la
bande-son, le master, le MP4 et la planche de contrôle. Il n’appelle aucun service
payant.

## Complément interactif

Si le jury souhaite explorer le prototype après le film :

1. lancer `Lancer_Flow_Scout_Jury.command` ;
2. attendre `13/13 contrôles · 5/5 passages · 0 appel payant` ;
3. ouvrir le scénario préchargé ou le dashboard d’alignement ;
4. utiliser `R` pour remettre la démonstration à zéro.

## Plans de secours

| Situation | Réaction immédiate |
|---|---|
| Le lecteur ne s’ouvre pas | Glisser le MP4 dans Chrome ou Safari. |
| Le son est indisponible | Charger `Flow_Scout_2min.srt` ; le texte essentiel est déjà dans l’image. |
| Le MP4 a été déplacé | Le reconstruire avec `Construire_Video_Flow_Scout.command`. |
| L’interface ne s’ouvre pas | Utiliser `outputs/jury-mode/latest/index.html`. |
| Internet est indisponible | Continuer normalement : le film et le Jury Mode sont locaux. |

## Promesse finale du film

Flow Scout transforme un dossier client dispersé en décisions prouvables. Il
relie travail, compétences, connaissances, systèmes et usages IA ; remonte aux
preuves ; reconnaît ce qu’il ne sait pas ; puis prépare l’arbitrage humain avant
d’alimenter Flow Atlas.

# Historique des versions

Les notes de chaque version publiée sur GitHub sont reprises de ce fichier.

## [2.7.2] - 2026-10-31

### Temps restants plus justes
- Le « reste » et le débit de lecture sont calculés sur les 20 dernières minutes, et non plus sur la
  moyenne depuis le début : quand le débit change (petites photos puis grosses vidéos), l'estimation
  ne traîne plus des heures derrière la réalité.
- Le temps restant tient compte du nombre de fichiers, pas seulement de leur taille : le programme
  mesure le temps fixe par fichier et la vitesse de lecture pure, puis les applique aux fichiers qui
  restent. L'estimation reste juste quand il ne reste que des petites photos après des vidéos (ou
  l'inverse).
- Les fichiers déjà traités lors d'une session précédente (reprise) ne faussent plus le débit.
- File de plusieurs disques : le temps restant pour l'ensemble = reste du disque en cours + disques
  suivants au même débit. Il ne peut plus être inférieur au reste du disque en cours.

## [2.7.1] - 2026-10-29

### Documents importants
- Le programme repère les papiers qui comptent : identité et état civil, travail et salaires, diplômes,
  impôts, santé, véhicules, logement, banque et assurances, famille et succession, factures. D'après un
  dictionnaire de mots appliqué au nom et aux dossiers de chaque fichier ; volontairement large.
- Bilan (étape 7 et commande `bilan`) : nombre de documents importants par catégorie.
- « Nos souvenirs » : nouvelle rubrique « Papiers importants », rangée par catégorie.

### Regrouper l'archive sur un plus grand disque
- Étape 1, « Regrouper sur un plus grand disque… » (commande `regrouper`) : toute l'archive est copiée
  sur un seul disque, chaque copie est relue, puis ce disque devient ARCHIVE-1. Les anciens disques
  sont libérés et peuvent être formatés. Pause et reprise possibles ; un fichier abîmé est signalé et
  bloque la fin jusqu'à ce qu'il soit réparé.

### Import plus rapide avec beaucoup de petits fichiers
- Lecture d'avance des fichiers suivants, mise en sûreté de plusieurs fichiers à la fois, catalogue
  enregistré moins souvent : environ 25 % de temps en moins sur des disques USB pour des photos.
- Un fichier laissé par une coupure de courant est remplacé, au lieu d'une copie « (2) ».
- Le journal indique, à la fin de chaque disque, ce qui a freiné (lecture, écriture ou catalogue).

### « Nos souvenirs » prêt sans attendre
- Les vignettes des photos sont faites pendant l'import, à partir des photos déjà lues, sur les cœurs
  libres du processeur.
- L'aperçu déjà rangé dans les photos de téléphone est utilisé tel quel quand il est assez grand.
- La page est utilisable tout de suite ; les vignettes qui manquent sont faites ensuite, plusieurs à la
  fois, et une pause n'en perd aucune.

## [2.6.0] - 2026-10-29

### « Nos souvenirs » : consulter l'archive sans le logiciel
- Sur chaque disque de l'archive et des sauvegardes, un fichier « ▶ Nos souvenirs.html » ouvre une
  visionneuse dans le navigateur, sans Internet ni installation (Windows et Mac).
- Accueil avec les chiffres clés et de grandes tuiles ; photos et vidéos par année puis par album,
  affichage en grand avec flèches, clavier et diaporama ; documents par type et par année ; musique à
  écouter ; recherche par nom, lieu ou année.
- Vignettes des photos fabriquées une fois pour toutes, pour un affichage rapide même depuis un
  disque USB.
- Mise à jour automatique à la fin de chaque série d'imports ; bouton à l'étape 7 ; commande
  `souvenirs`.

## [2.5.2] - 2026-10-29

### Mise en pause plus claire et plus rapide
- Pendant une mise en pause, la fenêtre est grisée et un message « Mise en pause en cours… » demande
  de patienter ; la main est rendue dès que l'opération est vraiment arrêtée.
- La pause est plus rapide : les copies de secours du catalogue et le calcul du contenu propre au
  disque, longs sur une grosse archive, sont faits à la reprise plutôt qu'à l'arrêt.

### Corrigé
- Après « Oui » aux notifications au démarrage de l'import, l'import attendait la fermeture de la
  fenêtre de réglage : il démarre maintenant tout de suite.

## [2.5.1] - 2026-10-29

### Notifications : seulement avec votre accord
- Les notifications sont désactivées par défaut : rien n'est envoyé à ntfy.sh tant que vous ne les
  avez pas activées vous-même (case « Activer les notifications », décochée au départ, comme le point
  d'avancement horaire).
- Au premier « Démarrer l'import », le programme propose de les activer. « Oui » coche les deux cases
  et ouvre la fenêtre pour abonner le téléphone ; « Non » n'est plus redemandé.
- Un réglage activé automatiquement par la 2.4.0 ou la 2.5.0 n'est plus pris en compte : il faut
  l'activer à nouveau, explicitement.

## [2.5.0] - 2026-10-29

### Le bilan : « qu'y avait-il dans tous ces disques ? »
- Nouvelle étape 7 « Bilan : ce que contient l'archive », ouverte automatiquement à la fin d'un
  import : nombre de photos, vidéos, musiques, textes, tableurs, présentations, PDF, e-mails et autres
  fichiers (doublons retirés), avec la période couverte par chacun, la place occupée, et ce que les
  doublons faisaient perdre.
- Frise des photos et vidéos année par année, avec le nombre sur chaque barre.
- L'estimation rapide donne le même aperçu pour des disques simplement branchés, sans rien copier.
- Commande `bilan` en ligne de commande.

### Divers
- Le bouton « Téléphone… » devient « Notifications… ».
- Corrigé : « Retirer de la liste » ne pouvait pas fonctionner, le tableau de l'étape 2 n'acceptait
  aucune sélection.

## [2.4.0] - 2026-10-29

### Import en deux temps
- Étape 2 : « Choisir les disques… » ajoute les disques à une liste d'attente, visible dans le
  tableau, avec une pré-analyse pour chacun (nouveau, déjà commencé, déjà terminé). « Démarrer
  l'import » les traite ensuite l'un après l'autre, en reprenant d'abord ceux déjà commencés.
  « Retirer de la liste » enlève un disque en attente.
- La carte du haut affiche l'opération en cours au lieu de rester sur « Reprendre l'import ».

### Notifications sur le téléphone
- Bouton « Téléphone… » : notifications gratuites avec l'application ntfy (Android et iPhone), avec
  un mode d'emploi pas à pas, un QR code pour s'abonner en un geste sur Android et un message d'essai.
- Messages envoyés : fin de chaque disque (avec le nombre de fichiers nouveaux et de doublons),
  archive pleine, fin de l'import, fin de toute opération de plus de 10 minutes, et un point
  d'avancement toutes les heures (désactivable).

### Moins de travail inutile
- Disque Windows : seuls les dossiers des utilisateurs sont lus. Les autres dossiers de la racine
  (programmes, jeux…) sont ignorés et listés ; les dossiers techniques des profils (`.vscode`…) aussi.
- « Estimer la place nécessaire… » : estimation rapide (noms et tailles des fichiers, quelques
  minutes), sans rien lire ni enregistrer, au lieu d'une relecture complète aussi longue qu'un import.
  Elle dit s'il faudra un disque d'archive de plus.
- Vérification de l'archive et des sauvegardes : seuls les fichiers jamais relus (ou relus il y a plus
  d'un an) sont relus ; les autres sont contrôlés en présence et en taille. Une vérification
  interrompue reprend où elle en était. `verifier --tout` relit tout.
- Une sauvegarde relit chaque fichier de l'archive qu'elle copie : il compte désormais comme vérifié.
- Un import terminé sans erreur vaut contrôle de l'ancien disque (étape 5).
- Refus d'importer un disque déjà importé sous un autre nom, ou deux dossiers l'un dans l'autre.
- Les simples estimations faites avec une version précédente ne bloquent plus les étapes 2 et 5.

### Affichage
- Les icônes (coches vertes, icône d'activité…) ne sont plus rognées sur la droite en plein écran.

## [2.3.1] - 2026-10-29

### Corrigé
- « Importer des disques » : les disques de l'archive et des sauvegardes sont grisés et ne peuvent
  plus être cochés, y compris quand l'archive est rangée dans un dossier `ArchiveFamiliale` du disque
  (le cas habituel). Seule exception : un disque accepté dès le départ à la fois comme ancien disque
  et comme disque de l'archive (grand disque interne d'un PC).

## [2.3.0] - 2026-10-29

### Importer plusieurs disques d'un coup
- Étape 2 : « Importer des disques… » permet de cocher plusieurs anciens disques (et des dossiers),
  chacun avec son nom et sa description. Ils sont importés l'un après l'autre, sans surveillance.
- Avant de lancer, le programme compare la taille à lire à la place libre sur l'archive et prévient
  si ça risque de ne pas tenir.
- Pendant l'import : position dans la file (« Disque 3 sur 7 ») et temps restant estimé pour
  l'ensemble.
- Un disque illisible ou débranché n'arrête pas les suivants. À la fin, un bilan indique pour chaque
  disque ✅, ⚠️ ou ❌.
- Archive pleine : la file se met en pause sur le disque en cours et prévient. Dès qu'un disque est
  ajouté à l'archive, l'import reprend tout seul là où il s'était arrêté, puis continue. Un arrêt
  manuel met aussi la file en pause (« Reprendre l'import »).
- Si la lettre d'un disque change pendant une pause, il est retrouvé par son numéro de série.

### Pause
- Le bouton « Arrêter » devient « Mettre en pause ».
- La file d'import est enregistrée : on peut fermer le programme, redémarrer ou déplacer l'ordinateur.
  Au lancement suivant, « Reprendre l'import » repart exactement là où on en était.

### Mises à jour
- Au démarrage, si une nouvelle version existe, le programme propose directement de l'installer.

## [2.2.0] - 2026-10-29

### Nouvelle interface
- Design entièrement revu, plus moderne et plus rassurant : cartes aux coins arrondis, palette bleue
  (actions) et verte (ce qui est fait), icônes Windows, textes plus lisibles (thème Sun Valley, style
  Windows 11), adapté à toutes les mises à l'échelle d'écran.
- Carte « Prochaine étape » en haut de la fenêtre : ce qu'il faut faire maintenant, avec un seul gros
  bouton pour le faire.
- Chiffres clés de l'archive : fichiers, taille totale, disques, sauvegardes à jour.
- Liste des étapes à gauche (coche verte, triangle orange), détail de l'étape choisie à droite.
- Pendant une opération, la carte « Activité » devient bleue, son icône pulse doucement et la barre de
  progression avance en douceur ; le résultat s'affiche ensuite en vert, orange ou rouge. Le détail
  s'ouvre tout seul en cas de problème.
- Fenêtre d'aide et fenêtres de dialogue harmonisées.

### Documentation
- README réécrit pour le grand public, avec des captures d'écran et une foire aux questions.
- Les détails techniques sont dans `docs/TECHNIQUE.md`.

## [2.1.0] - 2026-10-29

### Installation et mises à jour
- Installateur Windows `ArchiveFamiliale-Setup.exe` : installation sans droits administrateur,
  raccourcis dans le menu Démarrer et sur le bureau, désinstallation depuis les paramètres de Windows.
- Mise à jour automatique : au démarrage, le programme vérifie s'il existe une nouvelle version et
  propose de l'installer en un clic (téléchargement vérifié par empreinte SHA-256, puis redémarrage).
  Bouton « Mises à jour… » pour vérifier à la demande. Fonctionne aussi avec la version portable (zip).
- Le numéro de version est affiché en haut de la fenêtre.

### Import et sauvegardes beaucoup plus rapides
- Lecture et écriture en même temps (travail à la chaîne sur trois fils) au lieu de l'une après l'autre.
- Synchronisation du disque par lots, avant chaque enregistrement du catalogue, au lieu d'une
  synchronisation après chaque fichier. Un fichier n'est toujours inscrit au catalogue qu'une fois
  réellement écrit ; une écriture qui échoue est retirée du catalogue et refaite à la relance.
- Les petits fichiers (moins de 64 Mo) dont il faut l'empreinte avant de décider sont lus une seule fois.
- Les fichiers sont lus dans l'ordre où ils sont posés sur le disque source (moins d'allers-retours
  de la tête de lecture sur les disques mécaniques). Option `--ordre-dossiers` pour l'ancien ordre.
- Au début de chaque import de plus de 1 Go : mesure de la vitesse de l'ancien disque et du
  disque d'archive, durée estimée, et alerte si un disque semble branché en USB 2.
- Mesures sur SSD : 98 → 220 Mo/s sur un mélange photos/vidéos ; 5,3 → 2,3 ms par petit fichier.

## [2.0.0] - 2026-10-10

- Archive répartie sur plusieurs disques, jeux de sauvegarde, vérification, contrôle des anciens
  disques, classement par type et par date, restauration et réparation du catalogue.
- Interface graphique pas à pas et exécutable Windows (version portable).

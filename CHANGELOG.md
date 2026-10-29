# Historique des versions

Les notes de chaque version publiée sur GitHub sont reprises de ce fichier.

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

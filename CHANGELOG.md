# Historique des versions

Les notes de chaque version publiée sur GitHub sont reprises de ce fichier.

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

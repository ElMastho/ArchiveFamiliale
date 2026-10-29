# Archive Familiale : documentation technique

Pour l'informaticien de la famille, ou toute personne qui veut comprendre, dépanner ou faire évoluer
le programme. Le mode d'emploi grand public est dans le [README](../README.md).

- [Principes](#principes)
- [Fichiers du projet](#fichiers-du-projet)
- [Organisation sur les disques](#organisation-sur-les-disques)
- [Ligne de commande](#ligne-de-commande)
- [En cas de panne d'un disque](#en-cas-de-panne-dun-disque)
- [Performances](#performances)
- [Cas particuliers gérés](#cas-particuliers-gérés)
- [Classement : détails](#classement--détails)
- [Interface graphique](#interface-graphique)
- [Mise à jour automatique](#mise-à-jour-automatique)
- [Construire et publier](#construire-et-publier)
- [Tests](#tests)
- [Étapes suivantes possibles](#étapes-suivantes-possibles-hors-de-ce-programme)

---

## Principes

- Les anciens disques (les **sources**) ne sont **jamais modifiés** : ils sont seulement lus.
- Chaque fichier est identifié par une **empreinte** de son contenu (BLAKE2b-256). Deux fichiers
  identiques sont reconnus même avec des noms, des dossiers ou des dates différents ; le contenu
  n'est copié qu'une fois.
- L'archive peut occuper plusieurs disques (`ARCHIVE-1`, `ARCHIVE-2`…), remplis dans l'ordre. Chacun
  reste un disque normal, lisible seul sur n'importe quel PC.
- Un **catalogue** SQLite (sur `ARCHIVE-1`) garde chaque fichier vu, son emplacement dans l'archive,
  toutes ses origines et ses copies de sauvegarde. Une copie de secours est écrite sur chaque disque
  branché après chaque opération.
- Tout peut être interrompu et repris : relancer la même opération saute ce qui est déjà fait.
- Un fichier n'est inscrit au catalogue qu'une fois réellement écrit et synchronisé sur le disque.

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `archive.py` | Moteur et ligne de commande. Bibliothèque standard uniquement (Python 3.10+). |
| `archive_gui.py` | Interface graphique Tkinter (surcouche du moteur). |
| `theme.py` | Apparence : couleurs, polices, icônes, formes arrondies (thème Sun Valley si installé). |
| `classement.py` | Classement par type / date / événement (lecture EXIF, vidéo, Office, PDF sans dépendance). |
| `bilan.py` | Bilan : nombre de fichiers par famille (photos, vidéos, textes…), période couverte, répartition par année, place gagnée sur les doublons, documents importants. |
| `importants.py` | Documents importants : dictionnaire de mots (expressions régulières) par catégorie, appliqué au nom puis aux dossiers d'un fichier. |
| `souvenirs.py`, `souvenirs_site/` | « Nos souvenirs » : visionneuse web posée sur chaque disque (page, liste des fichiers du disque, vignettes). |
| `vignettes.py` | Vignettes des photos (Pillow) : aperçu intégré EXIF, décodage réduit, fabrication en tâche de fond pendant l'import. |
| `notif.py` | Notifications sur le téléphone (ntfy). |
| `maj.py` | Mise à jour automatique depuis les releases GitHub (installateur ou version portable). |
| `test_archive.py` | Tests de bout en bout : `python -m unittest -v test_archive` |
| `build_exe.bat` | Génère l'exe, le zip portable, l'installateur et leurs empreintes dans `dist\`. |
| `installer.iss` | Script de l'installateur Windows (Inno Setup 6). |
| `.github/workflows/build.yml` | CI : tests à chaque push, publication d'une release à chaque tag `v*`. |
| `CHANGELOG.md` | Historique des versions (sert aussi de notes de version). |

## Organisation sur les disques

```
F:\ArchiveFamiliale\              ← ARCHIVE-1 (disque principal)
├── Disque01-WD-bleu\              ← fichiers nouveaux trouvés sur ce disque, chemins d'origine conservés
│   └── Photos\2009\IMG_001.JPG
├── Disque02-Seagate\              ← seulement ce qui n'existait pas déjà ailleurs
└── _catalogue\
    ├── catalogue.sqlite            ← LE catalogue : chaque fichier vu, où il est rangé, ses sauvegardes
    ├── volume.json                 ← identité du disque (« je suis ARCHIVE-1 de telle archive »)
    ├── journal.log                 ← historique détaillé des opérations
    ├── sauvegardes\                ← 5 dernières copies du catalogue
    ├── exports\  verifications\    ← listes CSV et rapports
    └── outil\                      ← copie du programme (relançable depuis là, même sur un autre PC)

G:\ArchiveFamiliale\              ← ARCHIVE-2 (la suite, quand ARCHIVE-1 est plein)
├── Disque05-Toshiba\ …
└── _catalogue\  volume.json, catalogue-copie.sqlite (copie de secours), outil\

H:\ArchiveFamiliale\              ← Sauvegarde-A-1 (même arborescence, répartie à sa façon)
```

- Un fichier présent sur 6 disques sources n'est copié **qu'une fois**. Le catalogue garde la trace
  de **tous** ses emplacements d'origine (export `doublons.csv`).
- Les disques sont remplis **dans l'ordre**. Le contenu d'un même ancien disque reste sur un même
  disque d'archive tant qu'il y a de la place. En sauvegarde, chaque dossier de premier niveau va si
  possible en entier sur un même disque du jeu.
- Pour savoir si un fichier est un doublon, seul le catalogue est consulté : il faut `ARCHIVE-1`,
  plus un disque qui a de la place. Les autres disques de l'archive peuvent rester débranchés.
- Les disques sont reconnus par leur fichier `volume.json`, même si Windows leur donne une autre lettre.
- Les réglages de l'interface (dernière archive ouverte…) sont dans `%APPDATA%\ArchiveFamiliale\config.json`.

## Ligne de commande

```bat
python archive.py init           F:\ArchiveFamiliale
python archive.py ajouter-disque G:\ArchiveFamiliale -m F:\ArchiveFamiliale
python archive.py scanner   E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu" --note "bureau"
python archive.py importer  E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu"
python archive.py rapport        -m F:\ArchiveFamiliale
python archive.py exporter       -m F:\ArchiveFamiliale
python archive.py estimer   E:\ G:\ -m F:\ArchiveFamiliale
python archive.py bilan           -m F:\ArchiveFamiliale
python archive.py souvenirs       -m F:\ArchiveFamiliale [--titre "Les souvenirs des Martin"]
python archive.py verifier       -m F:\ArchiveFamiliale [--rapide | --tout]
python archive.py controler E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu" [--profond]
python archive.py ajouter-disque H:\ArchiveFamiliale -m F:\ArchiveFamiliale --jeu Sauvegarde-A
python archive.py sauvegarder    -m F:\ArchiveFamiliale --jeu Sauvegarde-A [--profond]
python archive.py verifier       -m F:\ArchiveFamiliale --jeu Sauvegarde-A
python archive.py classer        -m F:\ArchiveFamiliale --modele A [--appliquer]
python archive.py annuler-classement -m F:\ArchiveFamiliale
python archive.py restaurer      -m F:\ArchiveFamiliale --disque ARCHIVE-2 --vers K:\ArchiveFamiliale
python archive.py regrouper K:\ArchiveFamiliale -m F:\ArchiveFamiliale
python archive.py reparer-catalogue --copie G:\ArchiveFamiliale\_catalogue\catalogue-copie.sqlite --vers K:\ArchiveFamiliale
```

`-m` désigne toujours `ARCHIVE-1`. `set ARCHIVE_MAITRE=F:\ArchiveFamiliale` évite de le retaper.

| Commande | Effet |
|---|---|
| `init` | Crée l'archive et son disque `ARCHIVE-1`. |
| `option` | `--sauvegardes non` : pas de jeu de sauvegarde, par choix (l'interface n'y pousse plus). `--sauvegardes oui` pour revenir en arrière. Créer un jeu réactive aussi les sauvegardes. |
| `ajouter-disque` | Ajoute un disque à l'archive (`ARCHIVE-n`), ou à un jeu de sauvegarde avec `--jeu` (le jeu est créé s'il n'existe pas). Le dossier doit être vide. |
| `souvenirs` | Écrit sur chaque disque branché (archive et sauvegardes) la visionneuse « Nos souvenirs » : `_catalogue/souvenirs/` (index.html, app.js, style.css, donnees.js, vignettes `v/xx/<empreinte>.jpg`) et le lanceur « ▶ Nos souvenirs.html » à la racine du dossier de l'archive, et à la racine du disque s'il lui est dédié. Vignettes 360 px faites avec Pillow (facultatif) ; celles d'ARCHIVE-1 (`_catalogue/souvenirs/v`) servent de réserve et sont copiées sur les autres disques. La page est écrite d'abord avec les vignettes existantes (utilisable aussitôt), puis les vignettes manquantes sont faites sur plusieurs cœurs et la page réécrite. Chaque fichier porte sa catégorie de document important (`importants.py`), affichée dans la rubrique « Papiers importants ». La page fonctionne hors ligne, en `file://`, sans rien modifier. |
| `bilan` | Ce que contient l'archive : nombre de photos, vidéos, documents… (doublons retirés), période couverte et place gagnée sur les doublons. Une date vient du contenu (si un classement l'a lue), sinon du nom du fichier, sinon de sa date de modification. |
| `estimer` | Estimation **rapide** de ce que des disques apporteraient (noms et tailles des fichiers, comparés au catalogue et entre eux). Rien n'est lu ni enregistré ; utilisée par le bouton « Estimer la place nécessaire ». |
| `scanner` | Calcule les empreintes **sans rien copier** (relit tout : aussi long qu'un import). Un `importer` qui suit réutilise ces empreintes. |
| `importer` | Copie le contenu nouveau sur les disques de l'archive (voir [Performances](#performances)). `--ordre-dossiers` lit dossier par dossier au lieu de suivre l'emplacement physique des fichiers. |
| `rapport` | Disques de l'archive (branchés ou non, remplissage, vérification), sources, contenu exclusif à chaque source, total unique, taux de doublons, jeux de sauvegarde. |
| `exporter` | `inventaire.csv`, `stockage.csv` (avec le disque de chaque fichier), `doublons.csv`, `ignores_et_erreurs.csv`, `sauvegardes.csv`. Séparateur `;`, UTF-8 avec BOM pour Excel. |
| `verifier` | Relit les fichiers des disques branchés et compare leur empreinte : seulement ceux jamais relus, en défaut ou relus il y a plus d'un an (`--tout` : tous) ; les autres sont contrôlés en présence et en taille. Une vérification interrompue reprend où elle en était. Détecte les fichiers manquants, corrompus et non catalogués, et indique les disques non branchés (non vérifiés). `--jeu` vérifie un jeu de sauvegarde. |
| `controler` | « Puis-je me séparer de ce disque ? » Chaque fichier de la source doit être catalogué, inchangé, et sa copie saine. `--profond` relit et recompare. |
| `sauvegarder` | Copie dans un jeu ce qui lui manque, en répartissant sur ses disques branchés, et vérifie chaque copie par empreinte. Indique ce qui reste à faire : disque à brancher, ou place à ajouter. |
| `classer` | `--modele A\|B\|C` : calcule et affiche le plan de classement (simulation). Avec `--appliquer`, déplace réellement les fichiers. Tous les disques de l'archive doivent être branchés. |
| `annuler-classement` | Remet les fichiers à leur emplacement d'avant le dernier classement. |
| `restaurer` | Reconstruit un disque de l'archive (mort ou remplacé) à partir des jeux de sauvegarde branchés. Reprise possible. |
| `regrouper` | Copie toute l'archive (tous les disques `ARCHIVE-n`) sur un seul disque vide, plus grand, dans l'ordre physique de chaque disque et par le même travail à la chaîne que l'import ; vérifie chaque fichier lu par son empreinte (un fichier abîmé est signalé et non copié), puis relit chaque copie. Seulement quand TOUT est copié et relu : le catalogue est copié sur le nouveau disque et mis à jour (un seul disque d'archive, même identifiant qu'`ARCHIVE-1`), le reste de `_catalogue` suit, et les anciens disques sont libérés (`volume.json` et le catalogue renommés en `…-ancien`, lanceurs « Nos souvenirs » retirés, note « ANCIENNE ARCHIVE » posée). Reprise possible à tout moment (table `regroup`, fichier `_catalogue/regroupement.json` sur le disque cible). Les jeux de sauvegarde ne changent pas. |
| `reparer-catalogue` | `ARCHIVE-1` perdu : réinstalle le catalogue à partir d'une copie de secours, puis `restaurer --disque ARCHIVE-1`. |

Codes de sortie : `0` OK · `1` problèmes (détails affichés) · `2` erreur d'utilisation ·
`3` plus de place sur les disques de l'archive · `130` interrompu.

## En cas de panne d'un disque

| Disque perdu | Que faire |
|---|---|
| `ARCHIVE-2`, `ARCHIVE-3`… | Brancher un disque neuf et le ou les jeux de sauvegarde, puis `restaurer --disque ARCHIVE-2 --vers <nouveau dossier>`. Lancer ensuite `verifier`. |
| `ARCHIVE-1` | `reparer-catalogue --copie <un autre disque>\_catalogue\catalogue-copie.sqlite --vers <nouveau dossier>`, puis `restaurer -m <nouveau dossier> --disque ARCHIVE-1 --vers <nouveau dossier>`. Les imports faits après la date de la copie sont à relancer. |
| Un disque de sauvegarde | Ajouter un disque neuf au jeu (`ajouter-disque … --jeu …`), puis `sauvegarder`. Les fichiers qui étaient sur le disque perdu sont recopiés. |

Même sans le programme, les fichiers restent accessibles : chaque disque, d'archive ou de
sauvegarde, contient des dossiers et fichiers ordinaires. Fusionner le contenu de tous les disques
d'un jeu reconstitue l'archive complète.

**Disques abîmés** : si un disque produit beaucoup d'erreurs de lecture, ne le faites pas tourner
inutilement. Faites d'abord une image avec [`ddrescue`](https://www.gnu.org/software/ddrescue/)
(sous Linux, ou via un live USB), montez l'image, puis importez-la comme une source normale.

## Performances

Un disque dur lit environ 100 à 200 Mo/s, soit environ **2 h par To** (un disque portable 2,5 pouces
plutôt 100 Mo/s, soit environ 10 h pour 4 To). En USB 2, le débit plafonne vers 35 Mo/s.

**Import** : si aucun fichier de même taille n'est déjà stocké, le contenu est forcément nouveau :
copie directe en une seule lecture. Sinon l'empreinte est calculée d'abord, puis le fichier n'est
copié que s'il est nouveau (un fichier de moins de 64 Mo est gardé en mémoire pour ne pas être relu).
L'empreinte est recalculée pendant la copie et comparée à la première.

Ce qui rend l'import rapide :
- **Travail à la chaîne** (`Writer` dans `archive.py`) : un fil lit d'avance les fichiers de moins
  de 32 Mo (`Prefetcher`, 256 Mo au plus en mémoire, dans l'ordre de traitement), le fil principal
  calcule les empreintes et consulte le catalogue, un fil écrit sur l'archive, et 4 fils synchronisent
  (`fsync`), remettent les dates et renomment les fichiers de `.partial` en nom final. Synchroniser
  attend le disque : avec beaucoup de petits fichiers, c'était l'étape la plus lente ; plusieurs à la
  fois, le disque les regroupe. Au plus 128 Mo attendent d'être écrits ; ce volume est déduit de
  l'espace libre par l'allocateur de disques.
- **Synchronisation par lots** : le catalogue n'est enregistré (toutes les 30 s ou 2 000 fichiers)
  qu'après la fin des écritures en cours (`Archive.commit`), ce qui vide la chaîne : moins souvent,
  elle reste pleine. Une écriture qui échoue est retirée du catalogue et refaite à la relance. Un
  fichier écrit mais pas encore inscrit (coupure de courant) est remplacé à la relance, sans créer de
  copie « (2) ».
- **Vignettes au passage** : les photos lues d'avance sont aussi réduites en vignettes pour « Nos
  souvenirs » (`vignettes.Background`), sur les cœurs libres du processeur, sans relecture ; si elles
  prennent du retard, elles sont laissées pour plus tard plutôt que de ralentir l'import. Un aperçu
  intégré à la photo (EXIF, fréquent sur les téléphones) d'au moins 300 px est pris tel quel.
- **Où passe le temps** : à la fin de chaque import, le journal indique l'attente de la lecture, de
  l'écriture et des enregistrements du catalogue, pour savoir quel disque freine.
- **Ordre physique** : avant l'import, le programme demande à Windows où chaque fichier commence sur
  le disque (`FSCTL_GET_RETRIEVAL_POINTERS`, sans lire les fichiers) et les lit dans cet ordre.
  Sur un disque mécanique plein de photos, la tête de lecture avance au lieu de faire des allers-retours.
- **Mesure de vitesse** : au début de chaque import de plus de 1 Go, lecture du début du plus gros
  fichier de la source et écriture d'un fichier de test de 64 Mo (effacé aussitôt) sur le disque
  d'archive. Durée estimée affichée ; un disque sous 45 Mo/s est signalé (probablement en USB 2).

Mesures sur SSD (3,8 Go de photos et vidéos) : 98 Mo/s en 2.0.0, 220 Mo/s en 2.1.0 ; petits
fichiers : 5,3 ms puis 2,3 ms par fichier. En 2.7.0, sur des disques USB simulés (ouverture d'un
fichier 8 ms, lecture 100 Mo/s, synchronisation 20 ms), 1 800 photos de 1,5 Mo : 30 puis 38 fichiers/s
(+25 %) ; le temps restant est alors celui de la lecture de la source. Le catalogue pèse environ 300 octets par fichier vu
(environ 300 Mo pour un million de fichiers).

## Cas particuliers gérés

- **Bibliothèques Apple Photos, iPhoto, Aperture, Lightroom, iMovie**, et structures DVD ou caméscope
  (`VIDEO_TS`, `AVCHD`, `BDMV`…) : copiées **entières**, sans dédoublonnage interne, pour qu'elles
  restent ouvrables.
- **Disque contenant Windows** : seuls les profils de `Users\` sont lus (sans AppData, sans les
  dossiers techniques commençant par un point, sans les profils système). Tout le reste de la racine
  (Windows, Program Files, jeux, outils…) est ignoré ; les dossiers non système ainsi écartés sont
  listés à l'inventaire, pour être importés à part si besoin (`--inclure-systeme` pour tout prendre). Le contenu de `Windows.old\Users` est conservé. **Disque macOS** : même principe
  (System, Applications, Library, `~/Library`).
- **OneDrive, iCloud…** : les fichiers « en ligne uniquement » sont ignorés (sinon leur lecture
  déclencherait le téléchargement de tout le cloud) et listés dans `ignores_et_erreurs.csv`.
- **Disque interne qui porte aussi l'archive** : le dossier `ArchiveFamiliale` est ignoré à l'analyse.
- **Fichiers ignorés** : `Thumbs.db`, `desktop.ini`, `.DS_Store`, `._*`, dossiers système et
  **corbeilles** (`--inclure-corbeille` pour les inclure).
- **Noms invalides sous Windows** (`:` `?` `*`…, venant d'un Mac ou de Linux) : remplacés par `_`.
  **Chemins de plus de 260 caractères** : pris en charge.
- **Dates** de modification et de création conservées. **Liens symboliques et jonctions** : non suivis.
- **Disque plein** : on passe au disque suivant. S'il n'y a plus de place nulle part, arrêt propre avec
  instructions. 2 Go sont toujours laissés libres, et 10 Go sur `ARCHIVE-1` pour le catalogue.
- **Copie interrompue** : aucun fichier tronqué (écriture dans `.partial`, puis renommage).
- **Garde-fous** : le programme refuse d'importer un disque de l'archive, de mettre deux disques de
  l'archive ou de sauvegarde sur le même disque physique, et d'utiliser un ancien disque source comme
  disque d'archive (sauf confirmation explicite).
- Sur un PC encore utilisé, des fichiers changent : `controler` signale « modifié depuis l'import ».
  Relancer `importer` ajoute les nouvelles versions.

## Classement : détails

- **La date** est lue dans le fichier : EXIF des photos (JPEG, HEIC, RAW), date de la vidéo
  (MP4/MOV/AVI), propriétés des documents Office et PDF. À défaut, elle vient du nom du fichier
  (`IMG_20090812`, WhatsApp…), puis du nom du dossier (« Noël 2004 »), puis de la date du fichier
  (signalée comme incertaine). Une photo sans date connue va dans `Date inconnue\`.
- **Les noms de dossiers d'origine** servent de noms d'événements. Les noms sans intérêt (`DCIM`,
  `100CANON`, `Mes images`…) sont ignorés. Un événement de moins d'un mois reste groupé.
- **Les fichiers compagnons** (`.xmp`, `.thm`, `.aae`…) suivent leur photo ou leur vidéo.
- La musique va dans `Musique\<album>\`, les courriels dans `Courriels\`, et les logiciels, archives
  zip et autres dans `Autres fichiers\`, avec leur rangement d'origine.
- Les fichiers sont **déplacés** sur leur disque, sans copie. Les doublons, vérifications et contrôles
  continuent de fonctionner. Les disques de sauvegarde sont renommés de la même façon, sans recopie :
  immédiatement s'ils sont branchés, sinon à leur prochaine mise à jour.
- Le plan complet est enregistré en CSV avant validation. Les nouveaux imports arrivent dans le
  dossier de leur disque source ; relancer le classement ne range que ceux-là.

## Interface graphique

- `archive_gui.py` appelle les commandes du moteur dans un fil de travail (`run_jobs`) ; la sortie
  texte alimente la zone « Activité » et la barre de progression (`Progress.hook`).
- **Liste d'attente** : « Choisir les disques » (`SourcesDialog` → `plan_disks`) ajoute les disques
  à la liste sans rien lancer ; le tableau de l'étape 2 donne leur pré-analyse (`_plan_state` :
  nouveau, déjà commencé, déjà terminé). « Démarrer l'import » (`start_import`) trie la liste (déjà
  commencés d'abord, déjà terminés à la fin) puis importe les disques un par un, chacun par une
  commande `importer` distincte. Codes de retour : 0 ✅, 1 ⚠️ (fichiers illisibles),
  2/99 ❌ (disque suivant) ; 3 (archive pleine) et 130 (arrêt) mettent la file en **pause** sur le
  disque en cours. « Reprendre l'import », ou l'ajout d'un disque à l'archive pendant une pause
  « plein », relance ce disque (le moteur saute ce qui est déjà fait) puis les suivants. Chaque disque
  est retrouvé par son numéro de série de volume avant son tour, au cas où sa lettre aurait changé. La
  file est enregistrée dans `config.json` (clé `file_import`) à chaque changement : après une
  fermeture ou un redémarrage, elle est rechargée en pause et « Reprendre l'import » la relance.
- Refus des doubles lectures dans `SourcesDialog` : le même disque (numéro de série) sous un autre nom,
  deux chemins cochés l'un dans l'autre ; avertissement pour un dossier d'un disque déjà importé en
  entier. Les disques de l'archive et des sauvegardes sont grisés.
- **Notifications** (`notif.py`) : désactivées par défaut. Rien n'est envoyé sans accord explicite
  (`ntfy_accord`) : case cochée dans la fenêtre « Notifications », ou « Oui » à la question posée une
  seule fois au premier « Démarrer l'import » (`ntfy_propose`). Publication JSON sur `https://ntfy.sh` (configurable :
  `ntfy_serveur`), sujet secret aléatoire `archive-xxxxxxxxxxxx` (`ntfy_sujet`), en arrière-plan,
  sans jamais bloquer. Envoyées : fin de chaque disque de la file (bilan chiffré `LAST_RUN`), archive
  pleine (priorité 5), fin de la file, fin de toute opération de plus de 10 minutes, point
  d'avancement horaire (`ntfy_avancement`). Abonnement Android par lien `ntfy://ntfy.sh/<sujet>`
  affiché en QR code (bibliothèque `qrcode`, facultative) ; iPhone : saisie du sujet.
- Le temps restant pour l'ensemble de la file est extrapolé de la vitesse moyenne observée et de
  l'espace occupé sur chaque disque (approximatif : les doublons vont plus vite).
- `theme.py` s'appuie sur [Sun Valley](https://github.com/rdbende/Sun-Valley-ttk-theme) (`sv-ttk`,
  style Windows 11) quand il est installé, sinon sur le thème `clam`. Les cartes, pastilles et lignes
  sélectionnées sont des images arrondies anticrénelées générées au démarrage, à la taille de l'écran
  (mise à l'échelle Windows 100 % à 200 %). Icônes : police *Segoe Fluent Icons* (Windows 11) ou
  *Segoe MDL2 Assets* (Windows 10).
- Couleurs : bleu `#005FB8` pour les actions, vert `#107C41` pour ce qui est fait, ambre `#9D5D00`
  pour ce qui attend. Animations volontairement discrètes : barre de progression qui glisse, icône
  d'activité qui pulse lentement pendant une opération.

## Mise à jour automatique

`maj.py` interroge `https://api.github.com/repos/ElMastho/ArchiveFamiliale/releases/latest` au
démarrage (désactivable : `"verifier_maj": false` dans `config.json`).

1. Si la version publiée est plus récente que `VERSION`, le programme propose aussitôt de
   l'installer ; en cas de refus, un bouton « Installer la version … » reste dans l'en-tête.
2. Le programme télécharge `ArchiveFamiliale-Setup.exe` (programme installé, reconnu à la présence de
   `unins000.exe`) ou `ArchiveFamiliale.zip` (version portable), et vérifie son empreinte SHA-256
   publiée à côté (`*.sha256`). Les chemins du zip sont contrôlés avant extraction.
3. Un script PowerShell attend la fermeture du programme, puis :
   - installé : relance l'installateur en mode silencieux, qui rouvre le programme ;
   - portable : remplace l'exe et `_internal` ; l'ancienne version est remise en place si la copie échoue.

L'archive, le catalogue et les réglages ne sont jamais touchés.

## Construire et publier

```bat
build_exe.bat
```

Le script crée un environnement virtuel `.build-venv`, installe PyInstaller et `sv-ttk`, lance les
tests, puis produit dans `dist\` :
- `ArchiveFamiliale\ArchiveFamiliale.exe` (le programme, mode dossier) ;
- `ArchiveFamiliale.zip` (version portable) ;
- `ArchiveFamiliale-Setup.exe` (installateur), si [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  est installé (`winget install JRSoftware.InnoSetup`) ;
- un fichier `.sha256` à côté de chacun, vérifié par la mise à jour automatique.

L'installateur installe pour l'utilisateur seul (`%LOCALAPPDATA%\Programs\ArchiveFamiliale`), sans
droits administrateur : le programme peut ainsi se mettre à jour lui-même.

Pourquoi un dossier plutôt qu'un exe unique : en mode « fichier unique », l'exe se décompresse à
chaque lancement dans un dossier temporaire. L'antivirus peut alors verrouiller les fichiers
fraîchement écrits, ce qui provoque une erreur intermittente (« Failed to import encodings module »).

**Publier une nouvelle version :**
1. Mettre à jour `VERSION` dans `archive.py` et ajouter une section `## [x.y.z]` dans `CHANGELOG.md`.
2. Commit, puis :
   ```bat
   git tag vx.y.z
   git push origin main vx.y.z
   ```
3. La CI (`.github/workflows/build.yml`) lance les tests, vérifie que le tag correspond à `VERSION`,
   construit l'exe, le zip et l'installateur, puis crée la release avec les notes du CHANGELOG. Les
   programmes déjà installés la proposent au démarrage suivant.

## Tests

```bat
python -m unittest -v test_archive
```

Tests de bout en bout sur des disques simulés (dossiers temporaires, capacité fictive) : import,
doublons, reprise, multi-disques, sauvegardes, vérification, restauration, classement, échecs
d'écriture, ordre physique, mesure de vitesse, mise à jour (téléchargement, empreinte, zip piégé)
et ouverture de l'interface.

## Étapes suivantes possibles (hors de ce programme)

- **Quasi-doublons** (même photo redimensionnée ou recompressée) :
  [Czkawka](https://github.com/qarmin/czkawka) ou digiKam, avec validation humaine.
- **Consultation confortable en famille** : [Immich](https://immich.app) sur un NAS, pointé en
  lecture seule sur l'archive.
- **Copie dans le cloud**, en plus des disques : Backblaze B2, ou `rclone`/`restic` vers un stockage objet.

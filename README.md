# Archive Familiale

Rassembler les photos, vidéos et documents éparpillés sur de nombreux disques durs en **une seule
archive sans doublons**, répartie si besoin sur **plusieurs disques**, puis en faire des **copies
de sauvegarde vérifiées**.

- Les anciens disques ne sont **jamais modifiés** : ils sont seulement lus.
- Chaque fichier est identifié par une empreinte de son contenu (BLAKE2b-256). Deux fichiers
  identiques sont reconnus même avec des noms, des dossiers ou des dates différents.
- L'archive peut occuper plusieurs disques (`ARCHIVE-1`, `ARCHIVE-2`…), remplis dans l'ordre.
  Chacun reste un disque normal, lisible seul sur n'importe quel PC.
- Tout peut être interrompu et repris : rien n'est perdu.

---

## Pour la famille : mode d'emploi

### Installer le programme

1. Ouvrez la page des versions : **https://github.com/ElMastho/ArchiveFamiliale/releases/latest**
2. Téléchargez **`ArchiveFamiliale-Setup.exe`** et lancez-le. L'installation ne demande pas de droits
   administrateur : le programme va dans `%LOCALAPPDATA%\Programs\ArchiveFamiliale`, avec un raccourci
   dans le menu Démarrer (et sur le bureau si vous cochez la case).
3. Au premier lancement, Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » :
   cliquez sur « Informations complémentaires », puis « Exécuter quand même » (le programme n'est pas
   signé numériquement).

Installez le programme **sur l'ordinateur**, pas sur les disques de l'archive : c'est le programme
qui prépare ces disques. Il se recopie de lui-même dans `_catalogue\outil` de chaque disque, pour
que l'archive reste utilisable sur n'importe quel PC.

*Version portable* : `ArchiveFamiliale.zip`, sur la même page. Décompressez-le (clic droit,
« Extraire tout… ») et lancez `ArchiveFamiliale.exe`. Gardez le dossier entier : l'exe a besoin du
sous-dossier `_internal` placé à côté de lui.

### Mises à jour

Au démarrage, le programme vérifie s'il existe une version plus récente. Si oui, un bouton
**« ⬆ Installer la version … »** apparaît en haut de la fenêtre. Un clic télécharge la nouvelle
version, vérifie qu'elle est intacte, ferme le programme, l'installe et le rouvre. L'archive, le
catalogue et les réglages ne sont pas touchés. Le bouton **« Mises à jour… »** fait la même
vérification à la demande. Une mise à jour ne s'installe jamais pendant une opération en cours.

### Utilisation

La fenêtre montre les 5 étapes, avec un ✔ vert pour celles qui sont faites et une ligne orange
« À faire maintenant ». Le bouton **« Aide »** donne le mode d'emploi détaillé.

| Étape | Ce qu'il faut faire |
|---|---|
| **1. Disques de l'archive** | Brancher un disque **neuf**, puis « Créer l'archive… » : il devient `ARCHIVE-1`. S'il ne suffit pas, « Ajouter un disque à l'archive… » pour créer `ARCHIVE-2`, etc. |
| **2. Importer les anciens disques** | Brancher **un** ancien disque, puis « Importer un disque… ». Recommencer pour chaque disque. Si l'archive est pleine, ajouter un disque (étape 1) et relancer : l'import reprend où il en était. |
| **3. Vérifier l'archive** | Une fois tous les disques importés : brancher tous les disques `ARCHIVE-…`, puis « Vérifier maintenant ». |
| **4. Jeux de sauvegarde** *(conseillé, facultatif)* | « Créer un jeu de sauvegarde… » avec un disque neuf. S'il manque de place : « Ajouter un disque à un jeu… ». Faire **2 jeux** et en garder un **hors de la maison**. Si vous ne voulez pas de sauvegarde : « Je ne veux pas de sauvegarde… ». L'archive est alors la seule copie. |
| **5. Contrôler les anciens disques** | Rebrancher chaque ancien disque, puis « Contrôler un ancien disque… ». Si la réponse est OUI, son contenu est en sécurité. |
| **6. Classer l'archive** *(facultatif)* | « Classer l'archive… » : choisir un modèle, voir l'aperçu, valider. Les fichiers sont rangés par type et par date. Annulable. |

> ⚠️ Ne jetez et n'effacez **aucun** ancien disque avant que l'étape 5 dise OUI pour ce disque **et**
> que les sauvegardes de l'étape 4 soient à jour.

**Une étiquette sur chaque disque.** Le programme donne un nom à chaque disque : `ARCHIVE-2`,
`Sauvegarde-A-1`, `Disque07-WD-bleu`… Écrivez-le sur une étiquette collée sur le disque. Quand il a
besoin d'un disque précis, le programme le demande par ce nom.

Conseils :
- Le plus simple est de laisser tous les disques `ARCHIVE-…` branchés pendant les imports (un hub
  USB **alimenté** aide beaucoup). `ARCHIVE-1` doit toujours être branché, car il contient le catalogue.
- Laissez un ordinateur portable branché sur secteur. Le programme empêche la mise en veille.
- Ne débranchez jamais un disque pendant une opération : cliquez d'abord sur « Arrêter ».
- Un disque qui cliquette ou qui est très lent est peut-être en train de lâcher. Importez-le en
  priorité (voir aussi « Disques abîmés » plus bas).
- Une fois par an : branchez tout et lancez les vérifications de l'archive et des sauvegardes.

### Étape 6 (facultative) : classer l'archive

Une fois tout importé, « Classer l'archive… » range les fichiers par type et par date. Trois modèles
sont proposés :

| Modèle | Exemple |
|---|---|
| **A. Par type, puis date et événement** *(recommandé)* | `Photos et vidéos\2009\2009-08 Vacances Bretagne\` · `Documents\Tableurs\2012\Impôts\` |
| **B. Tout chronologique** | `2009\2009-08 Vacances Bretagne\` (photos et documents ensemble) |
| **C. Par type, puis date seule** | `Photos\2009\2009-08\` · `Vidéos\2009\2009-08\` · `Documents\Tableurs\2012\` |

Dans les trois modèles, la musique va dans `Musique\<album>\`, les courriels dans `Courriels\`, et
les logiciels, archives zip et autres dans `Autres fichiers\`, avec leur rangement d'origine. Les
bibliothèques Photos/iPhoto et les DVD restent entiers.

- **Aperçu d'abord.** Le programme montre l'arborescence obtenue, d'où viennent les dates, et des
  exemples. Le plan complet est enregistré en CSV. Rien ne bouge avant validation.
- **La date** est lue dans le fichier : EXIF des photos (JPEG, HEIC, RAW), date de la vidéo
  (MP4/MOV/AVI), propriétés des documents Office et PDF. À défaut, elle vient du nom du fichier
  (`IMG_20090812`, WhatsApp…), puis du nom du dossier (« Noël 2004 »), puis de la date du fichier
  (signalée comme incertaine). Une photo sans date connue va dans `Date inconnue\`.
- **Les noms de dossiers d'origine** servent de noms d'événements. Les noms sans intérêt (`DCIM`,
  `100CANON`, `Mes images`…) sont ignorés. Un événement de moins d'un mois reste groupé dans un
  seul dossier.
- **Les fichiers compagnons** (`.xmp`, `.thm`, `.aae`…) suivent leur photo ou leur vidéo.
- **Les fichiers sont déplacés** sur leur disque, sans copie ni place supplémentaire. Les doublons,
  les vérifications et les contrôles continuent de fonctionner. Les disques de sauvegarde sont
  renommés de la même façon, sans recopie : immédiatement s'ils sont branchés, sinon à leur
  prochaine mise à jour.
- **Annulable** : « Annuler le dernier classement » remet tout en place. On peut aussi changer de
  modèle directement.
- **Nouveaux imports** : les fichiers arrivent dans le dossier de leur disque source. Relancer le
  classement ne range que ceux-là.

### Sur un PC tour avec des disques internes

Les disques internes apparaissent dans la liste comme les disques USB, et s'importent de la même façon.

- **Disque contenant Windows** (le C: du PC, ou l'ancien disque système d'un autre ordinateur) : seuls
  les fichiers des utilisateurs sont analysés. Windows, Program Files, ProgramData, les dossiers
  AppData et les profils système sont ignorés. Le contenu de `Windows.old\Users` est conservé.
- **Disque macOS** : même principe. System, Applications, Library et les dossiers `~/Library` sont
  ignorés.
- **OneDrive, iCloud…** : les fichiers « en ligne uniquement » ne sont pas sur le disque. Ils sont
  ignorés (sinon leur lecture déclencherait le téléchargement de tout le cloud) et listés dans
  `ignores_et_erreurs.csv`.
- **Disque interne qui porte aussi l'archive** : on peut l'analyser, le dossier `ArchiveFamiliale`
  est ignoré. On peut aussi ranger l'archive sur un ancien disque déjà analysé, après confirmation.
  Il ne faudra alors jamais formater ce disque.
- Sur un PC encore utilisé, des fichiers changent : `controler` signale « modifié depuis l'import ».
  Relancer `importer` ajoute les nouvelles versions.

---

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
  disque d'archive tant qu'il y a de la place. En sauvegarde, chaque dossier de premier niveau va
  si possible en entier sur un même disque du jeu.
- Pour savoir si un fichier est un doublon, seul le catalogue est consulté. Il n'est donc pas
  nécessaire que tous les disques de l'archive soient branchés : il faut `ARCHIVE-1`, plus un disque
  qui a de la place.
- Les disques sont reconnus par leur fichier `volume.json`, même si Windows leur donne une autre
  lettre.
- Après chaque opération, une copie de secours du catalogue est écrite sur chaque disque branché.

**Cas particuliers gérés :**
- **Bibliothèques Apple Photos, iPhoto, Aperture, Lightroom, iMovie**, et structures DVD ou
  caméscope (`VIDEO_TS`, `AVCHD`, `BDMV`…) : copiées **entières**, sans dédoublonnage interne,
  pour qu'elles restent ouvrables.
- **Fichiers ignorés** : `Thumbs.db`, `desktop.ini`, `.DS_Store`, `._*`, dossiers système et
  **corbeilles** (option `--inclure-corbeille` pour les inclure).
- **Noms invalides sous Windows** (`:` `?` `*`…, venant d'un Mac ou de Linux) : remplacés par `_`.
  **Chemins de plus de 260 caractères** : pris en charge.
- **Dates** de modification et de création conservées.
- **Liens symboliques et jonctions** : non suivis.
- **Disque plein** : on passe au disque suivant. S'il n'y a plus de place nulle part, arrêt propre
  avec instructions. 2 Go sont toujours laissés libres, et 10 Go sur `ARCHIVE-1` pour le catalogue.
- **Copie interrompue** : aucun fichier tronqué (écriture dans `.partial`, puis renommage).
- **Garde-fous** : le programme refuse d'importer un disque de l'archive, de mettre deux disques de
  l'archive ou de sauvegarde sur le même disque physique, et d'utiliser un ancien disque source
  comme disque d'archive.

---

## Pour l'informaticien de la famille

### Fichiers

| Fichier | Rôle |
|---|---|
| `archive.py` | Moteur et ligne de commande. Bibliothèque standard uniquement (Python 3.10+). |
| `archive_gui.py` | Interface graphique Tkinter (surcouche du moteur). |
| `classement.py` | Classement par type / date / événement (lecture EXIF, vidéo, Office, PDF sans dépendance). |
| `test_archive.py` | Tests de bout en bout, dont le multi-disques simulé : `python -m unittest -v test_archive` |
| `maj.py` | Mise à jour automatique depuis les releases GitHub (installateur ou version portable). |
| `build_exe.bat` | Génère l'exe, le zip portable, l'installateur et leurs empreintes dans `dist\`. |
| `installer.iss` | Script de l'installateur Windows (Inno Setup 6). |
| `.github/workflows/build.yml` | CI : tests à chaque push, publication d'une release à chaque tag `v*`. |
| `CHANGELOG.md` | Historique des versions (sert aussi de notes de version). |

### Ligne de commande

```bat
python archive.py init           F:\ArchiveFamiliale
python archive.py ajouter-disque G:\ArchiveFamiliale -m F:\ArchiveFamiliale
python archive.py scanner   E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu" --note "bureau"
python archive.py importer  E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu"
python archive.py rapport        -m F:\ArchiveFamiliale
python archive.py exporter       -m F:\ArchiveFamiliale
python archive.py verifier       -m F:\ArchiveFamiliale [--rapide]
python archive.py controler E:\  -m F:\ArchiveFamiliale -l "Disque01-WD-bleu" [--profond]
python archive.py ajouter-disque H:\ArchiveFamiliale -m F:\ArchiveFamiliale --jeu Sauvegarde-A
python archive.py sauvegarder    -m F:\ArchiveFamiliale --jeu Sauvegarde-A [--profond]
python archive.py verifier       -m F:\ArchiveFamiliale --jeu Sauvegarde-A
python archive.py classer        -m F:\ArchiveFamiliale --modele A [--appliquer]
python archive.py annuler-classement -m F:\ArchiveFamiliale
python archive.py restaurer      -m F:\ArchiveFamiliale --disque ARCHIVE-2 --vers K:\ArchiveFamiliale
python archive.py reparer-catalogue --copie G:\ArchiveFamiliale\_catalogue\catalogue-copie.sqlite --vers K:\ArchiveFamiliale
```

`-m` désigne toujours `ARCHIVE-1`. `set ARCHIVE_MAITRE=F:\ArchiveFamiliale` évite de le retaper.

| Commande | Effet |
|---|---|
| `init` | Crée l'archive et son disque `ARCHIVE-1`. |
| `option` | `--sauvegardes non` : pas de jeu de sauvegarde, par choix (l'interface n'y pousse plus). `--sauvegardes oui` pour revenir en arrière. Créer un jeu réactive aussi les sauvegardes. |
| `ajouter-disque` | Ajoute un disque à l'archive (`ARCHIVE-n`), ou à un jeu de sauvegarde avec `--jeu` (le jeu est créé s'il n'existe pas). Le dossier doit être vide. |
| `scanner` | Calcule les empreintes **sans rien copier**. Sert à estimer la taille réelle avant d'acheter les disques. Un `importer` qui suit réutilise ces empreintes. |
| `importer` | Copie le contenu nouveau sur les disques de l'archive. Si aucun fichier de même taille n'est déjà stocké, le contenu est forcément nouveau : copie directe en une seule lecture. Sinon, hash d'abord, puis copie seulement si nécessaire (un fichier de moins de 64 Mo est gardé en mémoire pour ne pas être relu). Les fichiers sont lus dans l'ordre où ils sont posés sur le disque ; `--ordre-dossiers` revient à l'ordre des dossiers. |
| `rapport` | Disques de l'archive (branchés ou non, remplissage, vérification), sources, contenu exclusif à chaque source, total unique, taux de doublons, jeux de sauvegarde. |
| `exporter` | `inventaire.csv`, `stockage.csv` (avec le disque de chaque fichier), `doublons.csv`, `ignores_et_erreurs.csv`, `sauvegardes.csv`. Séparateur `;`, UTF-8 avec BOM pour Excel. |
| `verifier` | Relit chaque fichier des disques branchés et compare son empreinte. Détecte les fichiers manquants, corrompus et non catalogués, et indique les disques non branchés (non vérifiés). `--jeu` vérifie un jeu de sauvegarde. |
| `controler` | « Puis-je me séparer de ce disque ? » Chaque fichier de la source doit être catalogué, inchangé, et sa copie saine. `--profond` relit et recompare. |
| `sauvegarder` | Copie dans un jeu ce qui lui manque, en répartissant sur ses disques branchés, et vérifie chaque copie par empreinte. Indique ce qui reste à faire : disque à brancher, ou place à ajouter. |
| `classer` | `--modele A\|B\|C` : calcule et affiche le plan de classement (simulation). Avec `--appliquer`, déplace réellement les fichiers. Tous les disques de l'archive doivent être branchés. |
| `annuler-classement` | Remet les fichiers à leur emplacement d'avant le dernier classement. |
| `restaurer` | Reconstruit un disque de l'archive (mort ou remplacé) à partir des jeux de sauvegarde branchés. Reprise possible. |
| `reparer-catalogue` | `ARCHIVE-1` perdu : réinstalle le catalogue à partir d'une copie de secours, puis `restaurer --disque ARCHIVE-1`. |

Codes de sortie : `0` OK · `1` problèmes (détails affichés) · `2` erreur d'utilisation ·
`3` plus de place sur les disques de l'archive · `130` interrompu.

### En cas de panne d'un disque

| Disque perdu | Que faire |
|---|---|
| `ARCHIVE-2`, `ARCHIVE-3`… | Brancher un disque neuf et le ou les jeux de sauvegarde, puis `restaurer --disque ARCHIVE-2 --vers <nouveau dossier>`. Lancer ensuite `verifier`. |
| `ARCHIVE-1` | `reparer-catalogue --copie <un autre disque>\_catalogue\catalogue-copie.sqlite --vers <nouveau dossier>`, puis `restaurer -m <nouveau dossier> --disque ARCHIVE-1 --vers <nouveau dossier>`. Les imports faits après la date de la copie sont à relancer. |
| Un disque de sauvegarde | Ajouter un disque neuf au jeu (`ajouter-disque … --jeu …`), puis `sauvegarder`. Les fichiers qui étaient sur le disque perdu sont recopiés. |

Même sans le programme, les fichiers restent accessibles : chaque disque, d'archive ou de
sauvegarde, contient des dossiers et fichiers ordinaires. Fusionner le contenu de tous les disques
d'un jeu reconstitue l'archive complète.

### Taille et durée

Un disque dur lit environ 100 à 200 Mo/s, soit environ **2 h par To** lu (un disque portable
2,5 pouces plutôt 100 Mo/s, soit environ 10 h pour 4 To). Branchez les disques sur des ports
**USB 3** (bleus, ou marqués « SS ») : en USB 2, le débit plafonne vers 35 Mo/s. Au début de
chaque import de plus de 1 Go, le programme mesure la lecture de l'ancien disque (sur le début du
plus gros fichier) et l'écriture sur le disque d'archive (fichier de test de 64 Mo, effacé
aussitôt), annonce une durée estimée et signale tout disque en dessous de 45 Mo/s : il est alors
probablement branché en USB 2. On peut arrêter, changer de port et relancer sans rien perdre.

Ce qui rend l'import rapide :
- **Travail à la chaîne** : un fil lit l'ancien disque et calcule les empreintes, un deuxième écrit
  sur l'archive, un troisième synchronise le disque et renomme les fichiers terminés. Lecture et
  écriture avancent en même temps.
- **Synchronisation par lots** : le catalogue n'est enregistré (toutes les 5 s ou 500 fichiers)
  qu'une fois les fichiers correspondants réellement écrits sur le disque. Un fichier n'est donc
  jamais déclaré archivé s'il ne l'est pas, même en cas de coupure de courant.
- **Ordre physique** : avant l'import, le programme demande à Windows où chaque fichier est posé
  sur le disque (`FSCTL_GET_RETRIEVAL_POINTERS`, sans lire les fichiers) et les lit dans cet ordre.
  Sur un disque mécanique plein de photos, la tête de lecture avance au lieu de faire des
  allers-retours. Sans effet (ni coût notable) sur SSD ou carte mémoire.
- **Une seule lecture** pour les petits fichiers dont il faut l'empreinte avant de décider.

Mesuré sur SSD (3,8 Go, photos et vidéos) : 98 Mo/s en 2.0.0, 220 Mo/s en 2.1.0.
Petits fichiers : 5,3 ms puis 2,3 ms par fichier. Pour 40 To de sources,
comptez quelques jours de lecture cumulée, réparties disque par disque. La reprise est automatique :
relancer la même commande saute ce qui est déjà fait. Le catalogue pèse environ 300 octets par
fichier vu (environ 300 Mo pour un million de fichiers).

### Disques abîmés

Si un disque produit beaucoup d'erreurs de lecture, ne le faites pas tourner inutilement. Faites
d'abord une image avec [`ddrescue`](https://www.gnu.org/software/ddrescue/) (sous Linux, ou via un
live USB), montez l'image, puis importez-la comme une source normale.

### Générer l'exécutable

```bat
build_exe.bat
```

Le script crée un environnement virtuel `.build-venv`, installe PyInstaller, lance les tests, puis
produit dans `dist\` :
- `ArchiveFamiliale\ArchiveFamiliale.exe` (le programme) ;
- `ArchiveFamiliale.zip` (version portable, environ 14 Mo) ;
- `ArchiveFamiliale-Setup.exe` (installateur), si [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  est installé (`winget install JRSoftware.InnoSetup`) ;
- un fichier `.sha256` à côté de chacun, vérifié par la mise à jour automatique.

### Publier une nouvelle version

1. Mettre à jour `VERSION` dans `archive.py` et ajouter une section `## [x.y.z]` dans `CHANGELOG.md`.
2. Commit, puis :
   ```bat
   git tag vx.y.z
   git push origin main vx.y.z
   ```
3. La CI GitHub (`.github/workflows/build.yml`) lance les tests, vérifie que le tag correspond à
   `VERSION`, construit l'exe, le zip et l'installateur, puis crée la release avec les notes du
   CHANGELOG. Les programmes déjà installés la proposent au démarrage suivant.

Pourquoi un dossier plutôt qu'un exe unique : en mode « fichier unique », l'exe se décompresse à chaque
lancement dans un dossier temporaire. L'antivirus peut alors verrouiller les fichiers fraîchement
écrits, ce qui provoque une erreur intermittente (« Failed to import encodings module »). Le mode
dossier n'a pas ce problème.


### Étapes suivantes possibles (hors de ce programme)

- **Quasi-doublons** (même photo redimensionnée ou recompressée) :
  [Czkawka](https://github.com/qarmin/czkawka) ou digiKam, avec validation humaine.
- **Tri par date de prise de vue** (EXIF) : `exiftool`, digiKam.
- **Consultation confortable en famille** : [Immich](https://immich.app) sur un NAS, pointé en
  lecture seule sur l'archive.
- **Copie dans le cloud**, en plus des disques : Backblaze B2, ou `rclone`/`restic` vers un stockage
  objet.

## Licence

Logiciel libre sous [licence MIT](LICENSE) : chacun peut l'utiliser, le modifier et le redistribuer,
à condition de conserver la mention de copyright. Il est fourni sans aucune garantie : gardez
toujours au moins une copie de sauvegarde de vos fichiers.

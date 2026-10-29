# Archive Familiale

**Toutes les photos, vidéos et documents de la famille, réunis au même endroit, sans doublons, et en sécurité.**

Vous avez des vieux disques durs, des clés USB, d'anciens ordinateurs pleins de souvenirs ?
Archive Familiale les rassemble en **une seule archive**, ne garde **qu'un exemplaire** de chaque
fichier, puis vous aide à en faire des **copies de sauvegarde**. Tout est vérifié, rien n'est jamais
effacé sur vos anciens disques.

[![Télécharger](https://img.shields.io/github/v/release/ElMastho/ArchiveFamiliale?label=T%C3%A9l%C3%A9charger&style=for-the-badge&color=005FB8)](https://github.com/ElMastho/ArchiveFamiliale/releases/latest)

![La fenêtre d'Archive Familiale](docs/images/accueil.png)

---

## Pourquoi vous pouvez lui faire confiance

- 🔒 **Vos anciens disques ne sont jamais modifiés.** Le programme se contente de les lire.
- 🧬 **Chaque fichier est vérifié.** Le programme calcule une « empreinte » de chaque fichier
  (comme une empreinte digitale) et s'en sert pour vérifier que les copies sont parfaites.
- ♻️ **Pas de doublons.** Une même photo présente sur cinq disques n'est gardée qu'une fois, même
  si elle a changé de nom.
- ⏸️ **On peut tout arrêter et reprendre.** Coupure de courant, disque débranché, ordinateur éteint :
  relancez simplement, le programme reprend là où il en était.
- 📂 **Pas de format secret.** L'archive est faite de dossiers et de fichiers ordinaires, lisibles sur
  n'importe quel ordinateur, même sans ce programme.

---

## Installer le programme

1. Cliquez sur le bouton **Télécharger** ci-dessus (ou ouvrez
   [la page des versions](https://github.com/ElMastho/ArchiveFamiliale/releases/latest)).
2. Téléchargez **`ArchiveFamiliale-Setup.exe`**, puis double-cliquez dessus.
   L'installation ne demande pas de mot de passe administrateur.
3. Windows peut afficher « Windows a protégé votre ordinateur » : cliquez sur
   **Informations complémentaires**, puis **Exécuter quand même**. Ce message apparaît pour les
   programmes qui ne sont pas vendus dans le commerce ; il est normal.

Le programme s'ouvre depuis le menu Démarrer : **Archive Familiale**.

> 💡 Installez le programme **sur l'ordinateur**, pas sur les disques de l'archive.

**Mises à jour** : quand une nouvelle version existe, un bouton **« Installer la version … »**
apparaît en haut de la fenêtre. Un clic suffit : le programme se ferme, se met à jour et se rouvre.
Vos fichiers et vos réglages ne sont pas touchés.

---

## Comment ça marche, en 5 étapes

Vous n'avez rien à retenir : en haut de la fenêtre, une carte bleue **« Prochaine étape »** vous dit
toujours quoi faire, avec un gros bouton pour le faire. À gauche, les étapes se cochent en vert au fur
et à mesure.

![Premier lancement : la carte « Prochaine étape » indique quoi faire](docs/images/premier-lancement.png)

### Ce qu'il vous faut

- Un ou plusieurs **disques durs neufs** pour l'archive (assez grands pour tout contenir ; le
  programme vous aide à estimer la place nécessaire) ;
- idéalement **deux autres disques** pour les sauvegardes ;
- vos **anciens disques**, clés USB, cartes mémoire…
- des **étiquettes** (ou un feutre) pour noter le nom de chaque disque.

### Les étapes

| | Étape | Ce que vous faites |
|---|---|---|
| 1️⃣ | **Créer l'archive** | Branchez un disque **neuf** et cliquez sur « Créer l'archive ». Il devient `ARCHIVE-1`. S'il n'y a plus de place un jour, ajoutez un deuxième disque : `ARCHIVE-2`. |
| 2️⃣ | **Importer les anciens disques** | Branchez **un** ancien disque, cliquez sur « Importer un disque » et donnez-lui un nom (par exemple `Disque-noir-du-bureau`). Recommencez pour chaque disque. |
| 3️⃣ | **Vérifier l'archive** | Quand tout est importé, cliquez sur « Vérifier maintenant ». Le programme relit tout et confirme que rien n'est abîmé. |
| 4️⃣ | **Faire des sauvegardes** | Branchez un autre disque neuf et cliquez sur « Créer un jeu de sauvegarde ». Faites-en **deux**, et rangez-en un **hors de la maison** (chez un proche, au travail…). |
| 5️⃣ | **Contrôler les anciens disques** | Avant de ranger ou de donner un ancien disque, rebranchez-le et cliquez sur « Contrôler un ancien disque ». Si la réponse est **OUI**, tout son contenu est dans l'archive. |
| ✨ | *Classer (facultatif)* | Rangez tout par type et par date : `Photos et vidéos / 2009 / 2009-08 Vacances Bretagne`. Vous voyez un aperçu avant de valider, et vous pouvez annuler. |

> ⚠️ **Ne jetez et n'effacez aucun ancien disque** avant que l'étape 5 ait dit OUI pour ce disque
> **et** que vos sauvegardes soient à jour.

### Pendant une opération

Une carte bleue en bas de la fenêtre montre ce qui se passe : la progression, la vitesse et le temps
restant. Vous pouvez cliquer sur **Arrêter** à tout moment : rien n'est perdu.

![Un import en cours, avec la progression et le temps restant](docs/images/import-en-cours.png)

---

## Les bons réflexes

- 🏷️ **Une étiquette sur chaque disque.** Le programme donne un nom à chaque disque (`ARCHIVE-1`,
  `Sauvegarde-A-1`, `Disque-noir-du-bureau`…). Écrivez-le sur le disque : quand il en a besoin, le
  programme vous le demande par ce nom.
- 🔌 **Branchez les disques sur un port USB 3** (souvent bleu, ou marqué « SS »). En USB 2, tout est
  trois fois plus lent ; le programme vous prévient s'il détecte un disque lent.
- 🔋 **Ordinateur portable : laissez-le sur secteur.** Le programme l'empêche de se mettre en veille.
- ✋ **Ne débranchez jamais un disque pendant une opération.** Cliquez d'abord sur « Arrêter ».
- 🩺 **Un disque qui cliquette ou qui est très lent** est peut-être en train de lâcher : importez-le
  en priorité.
- 📅 **Une fois par an**, branchez tout et lancez les vérifications de l'archive et des sauvegardes.

---

## Questions fréquentes

<details>
<summary><b>Combien de temps ça prend ?</b></summary>

Comptez environ **2 à 3 heures par téraoctet** (1 To = 1 000 Go) avec un disque branché en USB 3.
Au début de chaque import, le programme mesure la vitesse de vos disques et annonce une durée
estimée. Vous pouvez arrêter et reprendre plus tard autant de fois que vous voulez.
</details>

<details>
<summary><b>Est-ce que mes anciens disques risquent quelque chose ?</b></summary>

Non. Le programme ne fait que les **lire** : il n'y écrit rien, n'y efface rien, n'y déplace rien.
</details>

<details>
<summary><b>Et si le courant coupe en plein milieu ?</b></summary>

Rien n'est perdu. Un fichier n'est noté comme « archivé » qu'une fois réellement écrit sur le disque.
Relancez la même opération : elle reprend là où elle s'était arrêtée.
</details>

<details>
<summary><b>Comment le programme reconnaît-il les doublons ?</b></summary>

Par le **contenu** du fichier, pas par son nom. Deux photos identiques sont reconnues même si l'une
s'appelle `IMG_0042.JPG` et l'autre `Noël mamie.jpg`. Le programme garde la liste de tous les endroits
où chaque fichier a été trouvé.
</details>

<details>
<summary><b>Le disque de l'archive est plein, que faire ?</b></summary>

Branchez un nouveau disque neuf et cliquez sur « Ajouter un disque à l'archive » (étape 1). Relancez
l'import : il continue sur le nouveau disque.
</details>

<details>
<summary><b>Puis-je regarder mes photos sans le programme ?</b></summary>

Oui. Ouvrez le disque dans l'explorateur Windows : ce sont des dossiers et des fichiers normaux.
Le programme est aussi copié sur chaque disque d'archive (dossier `_catalogue\outil`), pour pouvoir
le relancer sur n'importe quel ordinateur.
</details>

<details>
<summary><b>Puis-je importer le disque interne d'un ordinateur ?</b></summary>

Oui. Sur un disque qui contient Windows (ou macOS), seuls les fichiers des utilisateurs sont pris :
Windows, les programmes et les fichiers système sont ignorés. Les fichiers OneDrive « en ligne
uniquement » sont ignorés aussi (ils ne sont pas vraiment sur le disque).
</details>

<details>
<summary><b>Un disque de l'archive est tombé en panne !</b></summary>

Si vous avez fait vos sauvegardes (étape 4), rien n'est perdu : le contenu peut être reconstruit sur
un disque neuf à partir d'une sauvegarde. La marche à suivre est dans la
[documentation technique](docs/TECHNIQUE.md#en-cas-de-panne-dun-disque) ; demandez de l'aide à
l'informaticien de la famille.
</details>

<details>
<summary><b>Comment désinstaller le programme ?</b></summary>

Paramètres de Windows → Applications → **Archive Familiale** → Désinstaller. Votre archive, sur vos
disques, n'est pas touchée.
</details>

---

## Pour aller un peu plus loin

- **Le bouton « Aide »** dans le programme donne le mode d'emploi complet, étape par étape.
- **« Rapport détaillé »** et **« Exporter les listes (Excel) »**, en bas de la fenêtre, donnent la
  liste de tous les fichiers, des doublons trouvés et des éventuelles erreurs.
- **Version portable**, sans installation : téléchargez `ArchiveFamiliale.zip` sur la
  [page des versions](https://github.com/ElMastho/ArchiveFamiliale/releases/latest), faites un clic
  droit → « Extraire tout… », puis lancez `ArchiveFamiliale.exe` (gardez tout le dossier).
- **Sans sauvegarde ?** C'est possible (« Je ne veux pas de sauvegarde… » à l'étape 4), mais l'archive
  est alors la seule copie : si un de ses disques tombe en panne, son contenu est perdu.

### Documentation technique

Ligne de commande, organisation des disques, procédure de réparation, performances, construction et
publication des versions : tout est dans la **[documentation technique](docs/TECHNIQUE.md)**.

L'historique des versions est dans le [CHANGELOG](CHANGELOG.md).

---

## Licence

Logiciel libre sous [licence MIT](LICENSE) : chacun peut l'utiliser, le modifier et le redistribuer,
à condition de conserver la mention de copyright. Il est fourni sans aucune garantie : gardez
toujours au moins une copie de sauvegarde de vos fichiers.

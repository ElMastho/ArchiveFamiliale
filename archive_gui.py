"""
archive_gui.py - Interface graphique d'Archive Familiale.

Guide pas à pas, pensé pour des personnes peu à l'aise avec l'informatique :
  1. Disques de l'archive      (créer l'archive, lui ajouter des disques)
  2. Importer les anciens disques
  3. Vérifier l'archive
  4. Jeux de sauvegarde
  5. Contrôler les anciens disques avant de les ranger

Toute la logique est dans archive.py ; ce fichier ne fait que l'interface.
Lancement : python archive_gui.py   (ou l'exécutable ArchiveFamiliale.exe)
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import queue
import re
import sqlite3
import string
import sys
import threading
import time
import traceback
import unicodedata
from collections import Counter
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog, simpledialog

import archive as core
import classement
import bilan
import maj
import notif
import souvenirs
import theme

APP_TITLE = "Archive Familiale"
ARCHIVE_FOLDER = core.ARCHIVE_FOLDER
RECOMMENDED_BACKUPS = 2
LOW_SPACE = 50 * 1024 ** 3     # en dessous : conseiller d'ajouter un disque
LONG_JOB = 600                 # secondes : au-delà, la fin d'une opération est signalée sur le téléphone


HELP_TEXT = """\
À QUOI SERT CE PROGRAMME ?
Rassembler les photos, vidéos et documents éparpillés sur de nombreux disques durs,
en ne gardant qu'UN exemplaire de chaque fichier, puis en faire des copies de sauvegarde.
Les anciens disques ne sont JAMAIS modifiés : le programme ne fait que les lire.

L'archive peut occuper PLUSIEURS disques (ARCHIVE-1, ARCHIVE-2, …) : quand l'un est plein,
le programme continue sur le suivant. Collez une étiquette avec son nom sur chaque disque.
ARCHIVE-1 est le disque principal : il contient le catalogue et doit être branché à chaque fois.

LA PROCÉDURE, ÉTAPE PAR ÉTAPE

Pas besoin de tout retenir : la carte bleue « Prochaine étape », en haut de la fenêtre, indique
toujours quoi faire, avec un bouton pour le faire. À gauche, la liste des étapes : un rond vert
coché quand une étape est faite, un triangle orange quand elle attend. Cliquez sur une étape pour
voir son détail et ses boutons.

1. Disques de l'archive
   Branchez un disque NEUF (vide) et cliquez sur « Créer l'archive… » : il devient ARCHIVE-1.
   S'il n'est pas assez grand, branchez un autre disque neuf et cliquez sur
   « Ajouter un disque à l'archive… » : il devient ARCHIVE-2, et ainsi de suite.
   Le plus simple : laisser tous les disques de l'archive branchés pendant les imports
   (un hub USB alimenté aide beaucoup).
   Plus tard, avec un disque plus grand : « Regrouper sur un plus grand disque… » copie toute
   l'archive (ARCHIVE-1, ARCHIVE-2…) sur ce disque, relit chaque copie, puis en fait le nouvel
   ARCHIVE-1. Les anciens disques sont alors libérés : vous pouvez les formater. Le regroupement
   peut être mis en pause et repris ; les anciens disques ne sont jamais modifiés pendant la copie.

2. Importer les anciens disques — un ou plusieurs à la fois
   • Branchez un ou plusieurs anciens disques (un hub USB alimenté aide beaucoup).
   • Cliquez sur « Choisir les disques… », cochez ceux à importer, vérifiez leur nom
     (à écrire sur une étiquette) et ajoutez une description si vous voulez
     (ex. : « disque noir du bureau ») : ils s'ajoutent au tableau, « en attente ».
     Le tableau indique pour chacun s'il est nouveau, déjà commencé ou déjà terminé.
   • Cliquez sur « Démarrer l'import ». Les disques déjà commencés passent en premier.
   • Les disques sont importés l'un après l'autre : vous pouvez partir, l'ordinateur
     travaille seul (il ne se met pas en veille). Comptez plusieurs heures par disque.
     Un disque qui pose problème n'arrête pas les suivants ; à la fin, un bilan
     indique pour chaque disque si tout s'est bien passé.
   • Si l'archive se remplit : l'import se met en pause et attend. Branchez un disque
     neuf et cliquez sur « Ajouter un disque… » : l'import reprend tout seul, là où il
     s'était arrêté. Pour ne pas être bloqué, ajoutez ce disque dès le départ.
   • « Mettre en pause » arrête proprement : vous pouvez même éteindre l'ordinateur.
     Au prochain lancement, la liste d'attente est toujours là : « Démarrer l'import »
     repart où ça en était.
   • Un import terminé sans erreur vaut contrôle (étape 5) : inutile de rebrancher le disque.
   • « Estimer la place nécessaire… » dit en quelques minutes, sans rien copier, si
     l'archive aura assez de place (d'après le nom et la taille des fichiers).
   • À la fin, éjectez les disques proprement (icône USB en bas à droite de Windows).

3. Vérifier l'archive
   Quand tous les disques sont importés, branchez tous les disques ARCHIVE-… et cliquez
   sur « Vérifier maintenant ». Le programme relit les fichiers et s'assure que rien n'est
   abîmé. Il ne relit que ce qui ne l'a pas encore été (ou l'a été il y a plus d'un an) :
   après de nouveaux imports, seuls les nouveaux fichiers sont relus, et une vérification
   interrompue reprend là où elle en était.

4. Jeux de sauvegarde (fortement conseillé, mais facultatif)
   Un « jeu » est une copie complète de l'archive, sur un ou plusieurs disques.
   Si vous ne voulez pas de sauvegarde, cliquez sur « Je ne veux pas de sauvegarde… » :
   l'archive sera alors la seule copie de vos données.
   Cliquez sur « Créer un jeu de sauvegarde… » et branchez un disque neuf. Si le jeu
   manque de place, « Ajouter un disque à un jeu… ». Faites 2 jeux, et gardez-en un
   AILLEURS (chez un autre membre de la famille).
   Après de nouveaux imports, branchez l'archive et les disques du jeu puis
   « Mettre à jour les sauvegardes ».

5. Contrôler les anciens disques avant de les ranger
   Rebranchez un ancien disque et cliquez sur « Contrôler un ancien disque… ».
   Si le programme répond OUI, tout son contenu est en sécurité dans l'archive.
   Ne jetez ou n'effacez un ancien disque QUE s'il a été contrôlé ET que les
   sauvegardes de l'étape 4 sont à jour.

6. Classer l'archive (facultatif)
   Une fois tout importé, « Classer l'archive… » range les fichiers par type et par date, par exemple :
   Photos et vidéos\\2009\\2009-08 Vacances Bretagne\\  ou  Documents\\Tableurs\\2012\\.
   Vous choisissez parmi 3 modèles, vous voyez un aperçu, puis vous validez. Annulable.
   Après de nouveaux imports, relancez-le : seuls les nouveaux fichiers seront rangés.

7. Bilan : ce que contient l'archive
   Combien de photos, de vidéos, de musiques, de documents… sur quelle période, et combien de
   place prenaient les doublons, avec une frise des photos et vidéos année par année. Il
   s'affiche tout seul à la fin d'un import. L'estimation rapide (étape 2) donne le même
   aperçu pour des disques simplement branchés, sans rien copier.
   « ★ Documents importants » : papiers d'identité, fiches de paie, diplômes, impôts,
   logement, santé… repérés d'après leur nom et leur dossier. Il peut y avoir des intrus :
   mieux vaut un document de trop qu'un papier important oublié.
   « Nos souvenirs » : sur chaque disque, un fichier « ▶ Nos souvenirs.html » ouvre l'archive
   dans le navigateur (photos par année, diaporama, papiers importants, documents, musique,
   recherche), pour la
   famille qui recevra le disque. Mis à jour à la fin de chaque import, ou avec le bouton
   « Créer « Nos souvenirs » sur les disques ».

DISQUES INTERNES D'UN PC (TOUR)
• Les disques internes apparaissent dans la liste comme les disques USB : on peut les importer.
• Sur un disque qui contient Windows (C:, ou l'ancien disque d'un autre PC), seuls les dossiers
  des utilisateurs (Documents, Images, Bureau, Vidéos…) sont lus. Windows, les programmes, les jeux,
  AppData et les autres dossiers de la racine sont ignorés ; ces derniers sont listés à la fin de
  l'inventaire. S'il y a des fichiers personnels dans l'un d'eux, ajoutez-le avec
  « Ajouter un dossier précis… ».
• Les fichiers OneDrive « en ligne uniquement » sont ignorés (ils ne sont pas sur le disque).
• Si un disque interne porte aussi l'archive (dossier ArchiveFamiliale), ce dossier est ignoré
  lors de l'analyse. Ne formatez alors jamais ce disque.

CONSEILS
• Ordinateur portable : laissez-le branché sur secteur. Le programme empêche la mise en veille.
• Ne débranchez jamais un disque pendant une opération (cliquez d'abord sur « Mettre en pause »).
• Un disque qui fait des bruits de cliquetis ou qui est très lent est peut-être en train de
  mourir : importez-le en priorité, sans l'allumer inutilement.
• Une fois par an : branchez tout et lancez les vérifications (archive et sauvegardes).
• Le programme est copié sur chaque disque (dossier _catalogue\\outil) : on peut
  toujours le relancer depuis là, même sur un autre ordinateur.
• Branchez les disques sur des ports USB 3 (bleus, ou marqués « SS ») : en USB 2, tout est
  trois fois plus lent. Au début de chaque gros import, le programme mesure la vitesse des
  disques, annonce une durée estimée et prévient si un disque semble branché en USB 2.

ÊTRE PRÉVENU SUR SON TÉLÉPHONE
• Bouton « Notifications… » en haut : installez l'application gratuite ntfy, visez le code avec
  l'appareil photo (Android) ou recopiez le nom affiché (iPhone), puis envoyez un message d'essai.
• Cochez « Activer les notifications » : rien n'est envoyé sans votre accord. Le programme vous
  le propose aussi au premier « Démarrer l'import ».
• Vous êtes prévenu à la fin de chaque disque, quand l'archive est pleine, à la fin de tout, et
  (si vous le voulez) toutes les heures avec l'avancement.

MISES À JOUR DU PROGRAMME
• Au démarrage, le programme vérifie s'il existe une nouvelle version et propose de l'installer :
  un clic suffit, le programme se ferme, se met à jour et se rouvre. L'archive et les réglages
  ne sont pas touchés.
• Le bouton « Mises à jour… » fait la même vérification quand vous voulez.
"""


# --------------------------------------------------------------------------- #
# Configuration et état
# --------------------------------------------------------------------------- #

def config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ArchiveFamiliale", "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict):
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def has_catalog(path: str) -> bool:
    return bool(path) and os.path.exists(os.path.join(path, core.CATALOG_DIR, core.DB_NAME))


def find_master(cfg: dict):
    """Retrouve ARCHIVE-1 même si Windows a changé la lettre du disque."""
    p = cfg.get("master")
    if has_catalog(p):
        return p
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    while True:   # programme lancé depuis <archive>\_catalogue\outil\… ?
        parent = os.path.dirname(here)
        if os.path.basename(here).lower() == core.CATALOG_DIR and has_catalog(parent):
            return parent
        if parent == here:
            break
        here = parent
    serial, sub = cfg.get("master_serial"), cfg.get("master_subpath")
    for d in core.list_drives():
        if serial and sub and d.serial == serial and has_catalog(d.root[:2] + sub):
            return d.root[:2] + sub
    return None


def load_state(master: str) -> dict:
    con = sqlite3.connect(os.path.join(master, core.CATALOG_DIR, core.DB_NAME), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        st = {
            "sources": [dict(r) for r in con.execute(
                """SELECT s.*, COUNT(o.relpath) AS n, COALESCE(SUM(o.size),0) AS sz,
                          COALESCE(SUM(o.status='copied'),0) AS nc,
                          COALESCE(SUM(CASE WHEN o.status='copied' THEN o.size END),0) AS szc,
                          COALESCE(SUM(o.status='error'),0) AS ne
                   FROM sources s LEFT JOIN occurrences o ON o.label=s.label
                   GROUP BY s.label ORDER BY s.first_seen""")],
            "volumes": [dict(r) for r in con.execute("SELECT * FROM volumes ORDER BY set_id, number")],
            "sets": [dict(r) for r in con.execute("SELECT * FROM backup_sets ORDER BY created_at")],
            "meta": dict(con.execute("SELECT key, value FROM meta").fetchall()),
        }
        main_stats = {r[0]: r[1:] for r in con.execute(
            "SELECT volume, COUNT(*), COALESCE(SUM(size),0), MAX(added_at) FROM stored GROUP BY volume")}
        bk_stats = {r[0]: r[1:] for r in con.execute(
            "SELECT volume, COUNT(*), COALESCE(SUM(size),0), MAX(copied_at) FROM backup_copies GROUP BY volume")}
        for v in st["volumes"]:
            n, b, last = (main_stats if v["set_id"] == core.MAIN_SET else bk_stats).get(v["id"], (0, 0, None))
            v.update(files=n, bytes=b, last_added=last)
        for s in st["sets"]:
            s["backlog_n"], s["backlog_b"] = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(size),0) FROM stored x WHERE NOT EXISTS "
                "(SELECT 1 FROM backup_copies b WHERE b.set_id=? AND b.path=x.path)", (s["id"],)).fetchone()
        st["unclassified"] = con.execute("SELECT COUNT(*) FROM stored WHERE class_batch IS NULL").fetchone()[0]
        lastc = con.execute("SELECT kind, model, created_at FROM classifications WHERE status IN "
                            "('terminé','interrompu') AND undone_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        st["can_undo"] = bool(lastc and lastc["kind"] == "classement")
        n, b, last = con.execute("SELECT COUNT(*), COALESCE(SUM(size),0), MAX(added_at) FROM stored").fetchone()
        st.update(stored_n=n, stored_b=b, last_change=last)
    finally:
        con.close()
    # Disques actuellement branchés
    drives = core.list_drives()
    for v in st["volumes"]:
        v["path"] = master if (v["set_id"] == core.MAIN_SET and v["number"] == 1) else core.locate_volume(v, drives)
        try:
            v["free"] = core.volume_free(v["path"]) if v["path"] else None
        except OSError:
            v["free"] = None
    st["main_vols"] = [v for v in st["volumes"] if v["set_id"] == core.MAIN_SET]
    for s in st["sets"]:
        s["vols"] = [v for v in st["volumes"] if v["set_id"] == s["id"]]
    return st


def to_ascii_label(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 _.\-]", "", t).strip().replace(" ", "-")
    return t[:30]


def suggest_label(base_name: str, existing: set[str]) -> str:
    n = len(existing) + 1
    while True:
        nm = to_ascii_label(base_name)
        label = f"Disque{n:02d}-{nm}" if nm else f"Disque{n:02d}"
        if label not in existing:
            return label
        n += 1


def autowrap(label):
    """Le texte se replie selon la largeur réellement disponible (écrans 100 % à 200 %). On ne réagit
    qu'aux vrais changements de largeur : sinon, repli et largeur peuvent se relancer sans fin."""
    def on_configure(e):
        new = max(e.width - 4, 200)
        if abs(new - int(str(label.cget("wraplength") or 0))) > 12:
            label.configure(wraplength=new)
    label.bind("<Configure>", on_configure)


def short_date(iso) -> str:
    return (iso or "")[:16].replace("T", " ")


# --------------------------------------------------------------------------- #
# Fenêtres de dialogue
# --------------------------------------------------------------------------- #

class DriveDialog(tk.Toplevel):
    """mode : 'create' | 'addvol' | 'backup' | 'regroup' | 'source' | 'scan' | 'check'"""

    def __init__(self, app: "App", mode: str, title: str, intro: str):
        super().__init__(app)
        self.app, self.mode, self.result = app, mode, None
        self.path = None
        self.drive = None
        st = app.st or {"sources": [], "volumes": [], "meta": {}}
        self.volume_by_serial = {v["volume_serial"]: v for v in st["volumes"] if v["volume_serial"]}
        self.sources = st["sources"]
        self.source_by_serial = {}
        for s in self.sources:
            if s["volume_serial"] and s["root"] and core.drive_root_of(s["root"]) == s["root"]:
                self.source_by_serial[s["volume_serial"]] = s

        self.title(title)
        self.transient(app)
        self.resizable(True, False)
        self.configure(background=theme.BG)
        frm = ttk.Frame(self, padding=theme.px(20))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=intro, wraplength=760, justify="left").pack(anchor="w")

        cols = ("lecteur", "nom", "taille", "libre", "type", "remarque")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=7, selectmode="browse",
                                 style="Data.Treeview")
        for c, label, w in (("lecteur", "Lecteur", 70), ("nom", "Nom du disque", 170),
                            ("taille", "Taille", 90), ("libre", "Libre", 90),
                            ("type", "Type", 90), ("remarque", "Remarque", 260)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="x", pady=(10, 4))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._ok())

        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="↻ Actualiser la liste", command=self._refresh).pack(side="left")
        if mode in ("source", "scan", "check"):
            ttk.Button(row, text="Choisir plutôt un dossier précis…",
                       command=self._pick_folder).pack(side="left", padx=8)
        self.chosen = ttk.Label(frm, text="Aucun disque sélectionné.", style="Muted.TLabel")
        self.chosen.pack(anchor="w", pady=(8, 4))

        self.var_label = tk.StringVar()
        self.var_note = tk.StringVar()
        self.var_deep = tk.BooleanVar(value=False)
        if mode in ("source", "scan"):
            g = ttk.Frame(frm)
            g.pack(fill="x", pady=4)
            ttk.Label(g, text="Nom à donner à ce disque :").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=self.var_label, width=40).grid(row=0, column=1, sticky="w", padx=8)
            ttk.Label(g, text="(écrivez ce nom sur une étiquette collée sur le disque)",
                      style="Muted.TLabel").grid(row=0, column=2, sticky="w")
            ttk.Label(g, text="Description :").grid(row=1, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=self.var_note, width=60).grid(row=1, column=1, columnspan=2,
                                                                   sticky="w", padx=8)
            ttk.Label(g, text="ex. : disque noir du bureau, étiquette « photos 2005 »",
                      style="Muted.TLabel").grid(row=2, column=1, columnspan=2, sticky="w", padx=8)
        if mode == "check":
            g = ttk.Frame(frm)
            g.pack(fill="x", pady=4)
            ttk.Label(g, text="Ce disque est :").grid(row=0, column=0, sticky="w")
            ttk.Combobox(g, textvariable=self.var_label, state="readonly", width=40,
                         values=[s["label"] for s in self.sources]).grid(row=0, column=1, sticky="w", padx=8)
            ttk.Checkbutton(g, text="Contrôle approfondi (relit tout le disque : plus long, plus sûr)",
                            variable=self.var_deep).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)

        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(12, 0))
        ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(b, text="OK", command=self._ok, style="Accent.TButton").pack(side="right", padx=8)

        self._drives = {}
        self._refresh()
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def _remark(self, d: core.Drive) -> str:
        v = self.volume_by_serial.get(d.serial)
        if v:
            return f"★ Archive : {v['name']}" if v["set_id"] == core.MAIN_SET else f"Sauvegarde : {v['name']}"
        if d.serial in self.source_by_serial:
            return f"Ancien disque déjà vu : {self.source_by_serial[d.serial]['label']}"
        if d.root.upper().startswith(os.environ.get("SystemDrive", "C:").upper()):
            return "Disque de cet ordinateur (Windows) — seuls les fichiers des utilisateurs seront analysés"
        if core.is_windows_root(d.root):
            return "Contient Windows — seuls les fichiers des utilisateurs seront analysés"
        return ""

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._drives = {}
        for d in core.list_drives():
            self._drives[d.root] = d
            self.tree.insert("", "end", iid=d.root, values=(
                d.root, d.name or "(sans nom)", core.fmt_size(d.total), core.fmt_size(d.free),
                d.kind, self._remark(d)))

    def _on_select(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        d = self._drives[sel[0]]
        self.drive, self.path = d, d.root
        self.chosen.config(text=f"Sélection : {d.describe()}")
        known = self.source_by_serial.get(d.serial)
        if self.mode in ("source", "scan"):
            if known:
                self.var_label.set(known["label"])
                self.var_note.set(known["note"] or "")
            else:
                self.var_label.set(suggest_label(d.name, {s["label"] for s in self.sources}))
                self.var_note.set("")
        elif self.mode == "check" and known:
            self.var_label.set(known["label"])

    def _pick_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Choisir un dossier")
        if not folder:
            return
        self.tree.selection_remove(self.tree.selection())
        self.drive, self.path = None, os.path.normpath(folder)
        self.chosen.config(text=f"Sélection : dossier {self.path}")
        if self.mode in ("source", "scan"):
            self.var_label.set(suggest_label(os.path.basename(self.path), {s["label"] for s in self.sources}))

    def _ok(self):
        if not self.path:
            messagebox.showwarning(APP_TITLE, "Sélectionnez d'abord un disque dans la liste.", parent=self)
            return
        d = self.drive
        known_vol = self.volume_by_serial.get(d.serial) if d else None
        if self.mode in ("source", "scan", "check"):
            if core.read_marker(self.path):
                messagebox.showerror(APP_TITLE, "Ce dossier est un disque de l'archive. Choisissez un ANCIEN "
                                     "disque.", parent=self)
                return
            if known_vol and not messagebox.askyesno(
                    APP_TITLE, f"Ce disque contient aussi « {known_vol['name']} » (dossier ArchiveFamiliale). "
                    "Ce dossier sera ignoré ; seul le reste du disque sera analysé.\n\nContinuer ?", parent=self):
                return
            label = self.var_label.get().strip()
            if not core.LABEL_RE.match(label):
                messagebox.showerror(APP_TITLE, "Le nom doit contenir seulement des lettres sans accents, "
                                     "des chiffres, des tirets ou des espaces (60 caractères maximum).\n"
                                     "Exemple : Disque07-WD-bleu", parent=self)
                return
            self.result = {"path": self.path, "label": label, "note": self.var_note.get().strip(),
                           "deep": self.var_deep.get()}
        else:   # create / addvol / backup : un disque qui va recevoir l'archive
            if known_vol:
                messagebox.showerror(APP_TITLE, f"Ce disque est déjà « {known_vol['name']} ». Chaque disque ne "
                                     "peut servir qu'une fois : choisissez un autre disque.", parent=self)
                return
            accept_source = False
            if d and d.serial in self.source_by_serial:
                lab = self.source_by_serial[d.serial]["label"]
                if not messagebox.askyesno(
                        APP_TITLE, f"Ce disque est aussi l'ancien disque « {lab} », déjà analysé.\n\n"
                        "C'est possible (par exemple un grand disque interne d'un PC) : l'archive sera rangée dans "
                        "un dossier « ArchiveFamiliale » à part, ignoré lors des analyses.\n\n"
                        "ATTENTION : il ne faudra alors JAMAIS effacer ni formater ce disque, puisqu'il "
                        "contiendra l'archive. Un disque neuf reste préférable.\n\nUtiliser ce disque quand même ?",
                        icon="warning", parent=self):
                    return
                accept_source = True
            if d and self._remark(d).startswith("Disque de cet ordinateur"):
                if not messagebox.askyesno(APP_TITLE, "C'est le disque interne de l'ordinateur. Il est "
                                           "fortement conseillé d'utiliser un disque externe.\n\n"
                                           "Continuer quand même ?", parent=self):
                    return
            path = os.path.join(self.path, ARCHIVE_FOLDER)
            if os.path.isdir(path) and os.listdir(path) and not has_catalog(path):
                messagebox.showerror(APP_TITLE, f"{path} existe déjà et n'est pas vide.", parent=self)
                return
            self.result = {"path": path, "drive": d, "accept_source": accept_source}
        self.destroy()


class SourcesDialog(tk.Toplevel):
    """Choix d'un ou de PLUSIEURS anciens disques à importer (ou estimer) à la suite.
    result : liste de {path, label, note, serial, size} dans l'ordre d'exécution."""

    def __init__(self, app: "App", copy: bool, title: str, intro: str):
        super().__init__(app)
        self.app, self.copy, self.result = app, copy, None
        st = app.st or {"sources": [], "volumes": [], "main_vols": []}
        self.sources = st["sources"]
        self.source_by_serial = {s["volume_serial"]: s for s in self.sources
                                 if s["volume_serial"] and s["root"] and core.drive_root_of(s["root"]) == s["root"]}
        self.volume_by_serial = {v["volume_serial"]: v for v in st["volumes"] if v["volume_serial"]}
        self.archive_free = sum(v["free"] or 0 for v in st["main_vols"] if v["path"])
        self.rows: dict[str, dict] = {}   # chemin -> {var, label, note, drive, size, widgets}
        self.folders: list[str] = []

        self.title(title)
        self.transient(app)
        self.resizable(True, True)
        self.configure(background=theme.BG)
        P = theme.px
        frm = ttk.Frame(self, padding=P(20))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=intro, wraplength=P(820), justify="left").pack(anchor="w")

        self.grid_frm = ttk.Frame(frm)
        self.grid_frm.pack(fill="x", pady=(P(14), P(6)))

        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="↻ Actualiser la liste", command=self._refresh).pack(side="left")
        ttk.Button(row, text="Ajouter un dossier précis…", command=self._pick_folder).pack(side="left", padx=P(8))
        ttk.Button(row, text="Tout cocher", command=lambda: self._check_all(True)).pack(side="left")
        ttk.Button(row, text="Tout décocher", command=lambda: self._check_all(False)).pack(side="left", padx=P(8))

        self.summary = ttk.Label(frm, text="", style="Strong.TLabel")
        self.summary.pack(anchor="w", pady=(P(14), 0))
        self.space = ttk.Label(frm, text="", style="Muted.TLabel", wraplength=P(820), justify="left")
        self.space.pack(anchor="w", pady=(P(4), 0))

        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(P(14), 0))
        ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right")
        self.btn_ok = ttk.Button(b, text="Lancer", command=self._ok, style="Accent.TButton")
        self.btn_ok.pack(side="right", padx=P(8))

        self._refresh()
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def _remark(self, d) -> tuple[str, bool]:
        """(remarque, sélectionnable)"""
        # Un disque de l'archive ou d'une sauvegarde n'est jamais une source, sauf s'il a été accepté
        # comme tel à sa création (grand disque interne qui porte aussi l'archive dans un dossier à part).
        v = self.volume_by_serial.get(d.serial)
        marker = core.read_marker(d.root) or core.read_marker(os.path.join(d.root, ARCHIVE_FOLDER))
        if v or marker:
            name = v["name"] if v else marker.get("name", "?")
            if d.serial in self.source_by_serial and not core.read_marker(d.root):
                return f"Contient aussi « {name} » : ce dossier sera ignoré, seul le reste sera lu", True
            return f"Disque « {name} » de l'archive : il ne peut pas être importé", False
        if d.serial in self.source_by_serial:
            s = self.source_by_serial[d.serial]
            return ("Déjà importé entièrement" if s["completed"] else "Déjà vu : l'import reprendra où il en était"), True
        if d.root.upper().startswith(os.environ.get("SystemDrive", "C:").upper()):
            return "Disque de cet ordinateur : seuls les fichiers des utilisateurs seront lus", True
        if core.is_windows_root(d.root):
            return "Contient Windows : seuls les fichiers des utilisateurs seront lus", True
        return "", True

    def _used_labels(self, but=None) -> set[str]:
        used = {s["label"] for s in self.sources}
        return used | {r["label"].get().strip() for p, r in self.rows.items() if p != but}

    def _refresh(self):
        old = {p: (r["var"].get(), r["label"].get(), r["note"].get()) for p, r in self.rows.items()}
        for w in self.grid_frm.winfo_children():
            w.destroy()
        self.rows = {}
        P = theme.px
        g = self.grid_frm
        g.columnconfigure(1, weight=1)
        heads = ((1, "Disque"), (2, "Nom à lui donner (à écrire sur une étiquette)"), (3, "Description"))
        for c, text in heads if self.copy else heads[:1]:
            ttk.Label(g, text=text, style="Muted.TLabel").grid(row=0, column=c, sticky="w", padx=(0, P(10)))
        items = [(d.root, d) for d in core.list_drives()] + [(f, None) for f in self.folders]
        for i, (path, d) in enumerate(items):
            r = 1 + 2 * i
            if d:
                remark, ok = self._remark(d)
                text = f"{d.root[:2]}  {d.name or '(sans nom)'}  ·  {core.fmt_size(d.used)} utilisés  ·  {d.kind}"
                size = d.used
                known = self.source_by_serial.get(d.serial)
                base = d.name
            else:
                remark, ok = "Dossier choisi à la main", True
                text, size, known, base = f"Dossier {path}", None, None, os.path.basename(path)
            checked, lab, note = old.get(path, (path in self.folders, None, None))
            row = {"var": tk.BooleanVar(value=checked and ok), "label": tk.StringVar(), "note": tk.StringVar(),
                   "drive": d, "size": size}
            self.rows[path] = row
            if lab is None:
                lab = known["label"] if known else suggest_label(base, self._used_labels(but=path))
                note = (known["note"] or "") if known else ""
            row["label"].set(lab)
            row["note"].set(note or "")
            cb = ttk.Checkbutton(g, variable=row["var"], command=self._update_summary,
                                 state="normal" if ok else "disabled")
            cb.grid(row=r, column=0, sticky="w", padx=(0, P(6)), pady=(P(6), 0))
            ttk.Label(g, text=text, style="Strong.TLabel" if ok else "Muted.TLabel").grid(
                row=r, column=1, sticky="w", padx=(0, P(10)), pady=(P(6), 0))
            if ok and self.copy:
                ttk.Entry(g, textvariable=row["label"], width=28).grid(row=r, column=2, sticky="w",
                                                                       padx=(0, P(10)), pady=(P(6), 0))
                ttk.Entry(g, textvariable=row["note"], width=32).grid(row=r, column=3, sticky="we",
                                                                      pady=(P(6), 0))
            if remark:
                ttk.Label(g, text=remark, style="Muted.TLabel").grid(row=r + 1, column=1, columnspan=3, sticky="w")
        if not items:
            ttk.Label(g, text="Aucun disque trouvé. Branchez-les puis cliquez sur « Actualiser la liste ».",
                      style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        self._update_summary()

    def _pick_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Choisir un dossier à importer")
        if folder and os.path.normpath(folder) not in self.folders:
            self.folders.append(os.path.normpath(folder))
            self._refresh()

    def _check_all(self, on):
        for path, r in self.rows.items():
            if not r["drive"] or self._remark(r["drive"])[1]:
                r["var"].set(on)
        self._update_summary()

    def _chosen(self):
        return [(p, r) for p, r in self.rows.items() if r["var"].get()]

    def _update_summary(self):
        chosen = self._chosen()
        self.btn_ok.configure(state="normal" if chosen else "disabled",
                              text=f"{'Importer' if self.copy else 'Estimer'} "
                                   f"{len(chosen) if len(chosen) > 1 else 'ce'} disque{'s' if len(chosen) > 1 else ''}"
                              if chosen else "Lancer")
        if not chosen:
            self.summary.configure(text="Cochez les disques à traiter.")
            self.space.configure(text="", style="Muted.TLabel")
            return
        total = sum(r["size"] or 0 for _, r in chosen)
        unknown = any(r["size"] is None for _, r in chosen)
        self.summary.configure(text=f"{len(chosen)} disque(s) sélectionné(s), traités l'un après l'autre"
                                    f" · environ {core.fmt_size(total)}{' + dossiers' if unknown else ''} à lire")
        if not self.copy:
            self.space.configure(text="Estimation rapide (quelques minutes) : le programme regarde seulement le nom "
                                      "et la taille des fichiers. Rien n'est copié ni enregistré.",
                                 style="Muted.TLabel")
        elif total > self.archive_free:
            self.space.configure(
                text=f"⚠ Place libre sur l'archive : {core.fmt_size(self.archive_free)}. Cela peut suffire grâce aux "
                     "doublons, mais ce n'est pas certain. Si l'archive se remplit, l'import se met en pause et attend "
                     "un nouveau disque. Pour ne pas être bloqué : ajoutez dès maintenant un disque à l'archive "
                     "(étape 1).", style="Warn.TLabel")
        else:
            self.space.configure(text=f"Place libre sur l'archive : {core.fmt_size(self.archive_free)}, c'est "
                                      "suffisant. Vous pouvez laisser l'ordinateur travailler seul.",
                                 style="Muted.TLabel")

    def _ok(self):
        chosen = self._chosen()
        if not chosen:
            return
        if not self.copy:
            self.result = [{"path": p, "size": r["size"]} for p, r in chosen]
            self.destroy()
            return
        seen = {}
        by_label = {s["label"]: s for s in self.sources}
        for path, r in chosen:
            label = r["label"].get().strip()
            if not core.LABEL_RE.match(label):
                messagebox.showerror(APP_TITLE, f"Nom invalide pour {path} : « {label} ».\n\nLe nom doit contenir "
                                     "seulement des lettres sans accents, des chiffres, des tirets ou des espaces "
                                     "(60 caractères maximum).\nExemple : Disque07-WD-bleu", parent=self)
                return
            if label.lower() in seen:
                messagebox.showerror(APP_TITLE, f"Le nom « {label} » est donné à deux disques ({seen[label.lower()]} "
                                     f"et {path}). Chaque disque doit avoir son propre nom.", parent=self)
                return
            seen[label.lower()] = path
            d, known = r["drive"], by_label.get(label)
            if known and d and known["volume_serial"] and d.serial and known["volume_serial"] != d.serial:
                messagebox.showerror(APP_TITLE, f"Le nom « {label} » est déjà celui d'un autre disque. "
                                     f"Choisissez un autre nom pour {path}.", parent=self)
                return
            # Le même disque sous un autre nom serait relu en entier, pour ne trouver que des doublons
            same = self.source_by_serial.get(d.serial) if d else None
            if same and same["label"] != label:
                messagebox.showerror(APP_TITLE, f"Ce disque ({path}) a déjà été importé sous le nom "
                                     f"« {same['label']} ». Gardez ce nom : l'import reprendra là où il en était, "
                                     "sans tout relire.", parent=self)
                r["label"].set(same["label"])
                return
        paths = [p for p, _ in chosen]
        for a in paths:
            for b in paths:
                if a != b and core.is_inside(a, b):
                    messagebox.showerror(APP_TITLE, f"{a} se trouve dans {b}, déjà coché : il serait lu deux "
                                         "fois. Décochez-en un.", parent=self)
                    return
        # Un dossier d'un disque déjà importé en entier : tout y serait déjà
        for p, r in chosen:
            if r["drive"]:
                continue
            for s in self.sources:
                if s["completed"] and s["root"] and core.is_inside(p, s["root"]) and \
                        core.volume_info(p)[1] == s["volume_serial"]:
                    if not messagebox.askyesno(APP_TITLE, f"{p} fait partie du disque « {s['label']} », déjà "
                                               "importé entièrement : tout ce qu'il contient est sans doute déjà "
                                               "dans l'archive. L'importer quand même ?", parent=self):
                        return
                    break
        self.result = [{"path": p, "label": r["label"].get().strip(), "note": r["note"].get().strip(),
                        "serial": r["drive"].serial if r["drive"] else None, "size": r["size"]}
                       for p, r in chosen]
        self.destroy()


class NotifyDialog(tk.Toplevel):
    """Réglage des notifications sur le téléphone (ntfy), avec un mode d'emploi pas à pas."""

    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        cfg = app.cfg
        if not cfg.get("ntfy_sujet"):   # nom tiré au hasard ; rien n'est envoyé tant qu'on n'a pas activé
            cfg["ntfy_sujet"] = notif.new_topic()
            save_config(cfg)
        self.title("Notifications sur votre téléphone")
        self.transient(app)
        self.resizable(False, False)
        self.configure(background=theme.BG)
        P = theme.px
        frm = ttk.Frame(self, padding=P(22))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Être prévenu sur son téléphone", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Un message arrive sur votre téléphone quand un disque est terminé, quand il faut "
                            "brancher un nouveau disque, et quand tout est fini. Vous pouvez donc laisser "
                            "l'ordinateur travailler seul. C'est gratuit et sans compte, avec l'application ntfy.",
                  style="Muted.TLabel", wraplength=P(700), justify="left").pack(anchor="w", pady=(P(4), P(14)))

        def card(title):
            c = ttk.Frame(frm, style="Card.TFrame", padding=(P(18), P(14)))
            c.pack(fill="x", pady=(0, P(10)))
            ttk.Label(c, text=title, style="CardStrong.TLabel").pack(anchor="w")
            return c

        c1 = card("1.  Installez l'application « ntfy » sur votre téléphone")
        ttk.Label(c1, text="Ouvrez le Play Store (Android) ou l'App Store (iPhone), cherchez « ntfy », puis "
                           "installez l'application gratuite. À la première ouverture, acceptez qu'elle "
                           "envoie des notifications.", style="CardMuted.TLabel",
                  wraplength=P(660), justify="left").pack(anchor="w", pady=(P(4), 0))

        c2 = card("2.  Abonnez-vous à votre archive")
        row = ttk.Frame(c2, style="CardFlat.TFrame")
        row.pack(fill="x", pady=(P(8), 0))
        self.qr_img = self._qr(app.notifier.app_link())
        if self.qr_img:
            ttk.Label(row, image=self.qr_img, style="Card.TLabel").pack(side="left", padx=(0, P(18)))
        right = ttk.Frame(row, style="CardFlat.TFrame")
        right.pack(side="left", fill="both", expand=True)
        if self.qr_img:
            ttk.Label(right, text="Android", style="CardStrong.TLabel").pack(anchor="w")
            ttk.Label(right, text="Visez ce code avec l'appareil photo du téléphone, puis touchez le lien qui "
                                  "apparaît : ntfy s'ouvre et s'abonne tout seul.", style="CardMuted.TLabel",
                      wraplength=P(430), justify="left").pack(anchor="w", pady=(0, P(10)))
        ttk.Label(right, text="iPhone (ou si le code ne marche pas)", style="CardStrong.TLabel").pack(anchor="w")
        ttk.Label(right, text="Dans ntfy, touchez « + », recopiez ce nom, puis touchez « S'abonner » :",
                  style="CardMuted.TLabel", wraplength=P(430), justify="left").pack(anchor="w")
        self.var_topic = tk.StringVar(value=app.notifier.topic)
        e = ttk.Entry(right, textvariable=self.var_topic, state="readonly", font="AFSubtitle", width=24)
        e.pack(anchor="w", pady=(P(6), 0))

        c3 = card("3.  Vérifiez que ça marche")
        r3 = ttk.Frame(c3, style="CardFlat.TFrame")
        r3.pack(fill="x", pady=(P(8), 0))
        ttk.Button(r3, text="Envoyer un message d'essai", style="Accent.TButton",
                   command=self._test).pack(side="left")
        self.test_lbl = ttk.Label(r3, text="", style="CardMuted.TLabel", wraplength=P(420), justify="left")
        self.test_lbl.pack(side="left", padx=(P(12), 0))

        self.var_on = tk.BooleanVar(value=bool(cfg.get("ntfy_accord")))
        self.var_hourly = tk.BooleanVar(value=bool(cfg.get("ntfy_avancement")))
        ttk.Checkbutton(frm, text="Activer les notifications (rien n'est envoyé tant que cette case n'est pas "
                                  "cochée)", variable=self.var_on,
                        command=self._save).pack(anchor="w", pady=(P(6), 0))
        ttk.Checkbutton(frm, text="Recevoir aussi un point d'avancement toutes les heures",
                        variable=self.var_hourly, command=self._save).pack(anchor="w", pady=(P(4), 0))
        ttk.Label(frm, text=f"Les messages passent par le service gratuit {app.notifier.server}. Ils contiennent "
                            "seulement des noms de disques et des chiffres, jamais vos fichiers. Toute personne "
                            "qui connaît ce nom peut lire les messages : ne le donnez qu'à la famille.",
                  style="Muted.TLabel", wraplength=P(700), justify="left").pack(anchor="w", pady=(P(12), 0))
        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(P(14), 0))
        ttk.Button(b, text="Fermer", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Changer de nom…", command=self._new_topic).pack(side="left")
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def _qr(self, text):
        m = notif.qr_matrix(text)
        if not m:
            return None
        k = max(3, theme.px(200) // len(m))
        rows = []
        for line in m:
            row = "{" + " ".join(("#000000" if v else "#FFFFFF") for v in line for _ in range(k)) + "}"
            rows.extend([row] * k)
        img = tk.PhotoImage(master=self, width=len(m) * k, height=len(m) * k)
        img.put(" ".join(rows))
        return img

    def _save(self):
        self.app.cfg.update(ntfy_accord=self.var_on.get(), ntfy_avancement=self.var_hourly.get())
        save_config(self.app.cfg)

    def _test(self):
        if not self.var_on.get():   # rien ne part sans accord explicite
            self.test_lbl.configure(text="Cochez d'abord « Activer les notifications », ci-dessous.")
            return
        self.test_lbl.configure(text="Envoi…")
        self.update_idletasks()
        err = self.app.notifier.send("Archive Familiale", "Message d'essai : les notifications fonctionnent. "
                                     "Vous serez prévenu ici.", tags=("white_check_mark",), wait=True)
        if err:
            self.test_lbl.configure(text=f"Échec de l'envoi : vérifiez la connexion Internet de l'ordinateur ({err}).")
        else:
            self.test_lbl.configure(text="Envoyé ! Le message doit arriver sur le téléphone dans quelques secondes. "
                                         "Sinon, reprenez l'étape 2.")

    def _new_topic(self):
        if not messagebox.askyesno(APP_TITLE, "Créer un nouveau nom ?\n\nLes téléphones déjà abonnés ne recevront "
                                   "plus rien : il faudra les réabonner (étape 2).", parent=self):
            return
        self.app.cfg["ntfy_sujet"] = notif.new_topic()
        save_config(self.app.cfg)
        self.destroy()
        NotifyDialog(self.app)


class PauseOverlay:
    """Pendant une mise en pause : la fenêtre est grisée et un message demande de patienter, le temps
    que le fichier en cours soit terminé proprement. La main est rendue quand l'opération s'est
    vraiment arrêtée (App._job_done)."""

    def __init__(self, app: "App", closing=False):
        self.app = app
        P = theme.px
        self.shade = tk.Toplevel(app)
        self.shade.overrideredirect(True)
        self.shade.configure(background="#18212F")
        try:
            self.shade.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        self.card = tk.Toplevel(app)
        self.card.overrideredirect(True)
        self.card.configure(background=theme.BORDER)
        box = ttk.Frame(self.card, style="Card.TFrame", padding=(P(28), P(22)))
        box.pack(fill="both", expand=True, padx=1, pady=1)
        ttk.Label(box, text="Mise en pause en cours…" if not closing else "Mise en pause, puis fermeture…",
                  style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(box, text="Le programme termine proprement le fichier en cours et note où il en est. Cela "
                            "peut prendre jusqu'à une minute sur un gros fichier.\n\nPatientez, et ne débranchez "
                            "aucun disque pour l'instant.", style="CardMuted.TLabel", wraplength=P(420),
                  justify="left").pack(anchor="w", pady=(P(8), P(14)))
        self.bar = ttk.Progressbar(box, mode="indeterminate", length=P(420))
        self.bar.pack(fill="x")
        self.bar.start(12)
        top = app.attributes("-topmost")
        for w in (self.shade, self.card):
            w.protocol("WM_DELETE_WINDOW", lambda: None)
            w.attributes("-topmost", top)   # au-dessus de la fenêtre principale, même si elle l'est
        self._follow()
        self.card.grab_set()
        self._bind = app.bind("<Configure>", lambda e: self._follow(), add="+")

    def _follow(self):
        app = self.app
        app.update_idletasks()
        x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        self.shade.lift()   # avant de placer : sous Windows, lift() remet une fenêtre sans bordure en 0,0
        self.card.lift()
        self.shade.geometry(f"{w}x{h}+{x}+{y}")
        self.card.update_idletasks()
        cw, ch = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        self.card.geometry(f"{cw}x{ch}+{x + (w - cw) // 2}+{y + (h - ch) // 2}")

    def close(self):
        try:
            self.app.unbind("<Configure>", self._bind)
            self.card.grab_release()
            self.shade.destroy()
            self.card.destroy()
        except tk.TclError:
            pass


class ChoiceDialog(tk.Toplevel):
    def __init__(self, app, title, text, options):
        super().__init__(app)
        self.result = None
        self.title(title)
        self.transient(app)
        self.configure(background=theme.BG)
        frm = ttk.Frame(self, padding=theme.px(20))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=text, wraplength=480, justify="left").pack(anchor="w")
        self.var = tk.StringVar(value=options[0])
        ttk.Combobox(frm, textvariable=self.var, values=options, state="readonly", width=40).pack(anchor="w", pady=10)
        b = ttk.Frame(frm)
        b.pack(fill="x")
        ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(b, text="OK", style="Accent.TButton",
                   command=lambda: (setattr(self, "result", self.var.get()), self.destroy())).pack(side="right", padx=8)
        self.wait_visibility()
        self.grab_set()


# --------------------------------------------------------------------------- #
# Fenêtre principale
# --------------------------------------------------------------------------- #

class ClassifyDialog(tk.Toplevel):
    def __init__(self, app, current=None):
        super().__init__(app)
        self.result = None
        self.title("Classer l'archive")
        self.transient(app)
        self.configure(background=theme.BG)
        frm = ttk.Frame(self, padding=theme.px(20))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, justify="left", wraplength=760, text=(
            "Les fichiers vont être rangés par type et par date. La date est lue dans les photos, les vidéos et "
            "les documents eux-mêmes ; à défaut, dans leur nom ou celui de leur dossier. Les noms de dossiers "
            "d'origine (« Vacances Bretagne »…) sont conservés comme noms d'événements.\n\n"
            "Rien ne sera déplacé avant que vous ayez vu l'aperçu et validé. Les fichiers sont déplacés sur leur "
            "disque (instantané, sans place supplémentaire) et le classement peut être annulé.\n"
            "Tous les disques de l'archive doivent être branchés.")).pack(anchor="w")
        self.var = tk.StringVar(value=current or "A")
        for key, title in classement.MODELS.items():
            box = ttk.Frame(frm, padding=(0, 10, 0, 0))
            box.pack(fill="x")
            ttk.Radiobutton(box, text=f"{key}. {title}" + ("   (recommandé)" if key == "A" else ""),
                            variable=self.var, value=key, style="StepTitle.TRadiobutton").pack(anchor="w")
            ttk.Label(box, text=classement.MODEL_EXAMPLES[key], font="AFMono", style="Muted.TLabel",
                      justify="left").pack(anchor="w", padx=(28, 0))
        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(16, 0))
        ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Voir l'aperçu (rien n'est déplacé)", style="Accent.TButton",
                   command=lambda: (setattr(self, "result", self.var.get()), self.destroy())).pack(side="right", padx=8)
        self.wait_visibility()
        self.grab_set()


class SmoothProgress(ttk.Progressbar):
    """Barre de progression qui glisse vers sa nouvelle valeur au lieu de sauter."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._target = 0.0
        self._shown = 0.0
        self._job = None

    def __setitem__(self, key, value):
        if key != "value":
            return super().__setitem__(key, value)
        self._target = float(value)
        if self._target < self._shown:   # nouvelle opération : on repart de zéro sans animation
            self._shown = self._target
            super().__setitem__("value", self._shown)
        elif self._job is None:
            self._step()

    def _step(self):
        self._job = None
        gap = self._target - self._shown
        self._shown = self._target if abs(gap) < 1 else self._shown + gap * 0.2
        super().__setitem__("value", self._shown)
        if self._shown != self._target:
            self._job = self.after(16, self._step)


class QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(("log", s))
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.cfg = load_config()
        self.master_path = None
        self.st = None
        self.busy = False
        self.closing = False
        self.iq = None   # liste d'attente des disques à importer (en attente, en cours ou en pause)
        self.notifier = notif.Notifier(self.cfg)
        self.job_t0 = 0.0
        self.job_title = ""
        self.pause_overlay = None
        self.notified_at = 0.0   # dernier point d'avancement envoyé sur le téléphone
        self.q: queue.Queue = queue.Queue()
        self.action_buttons: list[ttk.Button] = []
        core.Progress.hook = lambda frac, text, rate=None, eta=None: self.q.put(("progress", frac, text, rate, eta))

        theme.apply(self)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self.set_master(find_master(self.cfg), save=False)
        self._restore_queue()
        self._fit_to_screen()
        self.update_release = None
        if self.cfg.get("verifier_maj", True):
            self.after(2000, lambda: self.check_update(silent=True))

    def _fit_to_screen(self):
        """Taille de fenêtre adaptée à l'écran et à sa mise à l'échelle."""
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        k = float(self.tk.call("tk", "scaling")) / (96 / 72)   # 1.0 à 100 %, 2.0 à 200 %
        w, h = int(1240 * k), max(self.winfo_reqheight(), int(900 * k))
        if w > sw * 0.95 or h > sh * 0.90:
            try:
                self.state("zoomed")   # plein écran sur les petits écrans
                return
            except tk.TclError:
                w, h = int(sw * 0.95), int(sh * 0.88)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max((sh - h) // 3, 0)}")
        self.minsize(min(w, int(1080 * k)), min(h, int(780 * k)))

    # ---------- construction ----------
    STEP_ICONS = {1: "drive", 2: "import", 3: "verify", 4: "backup", 5: "check", 6: "sort", 7: "chart"}

    def _tree(self, parent, cols, height):
        t = ttk.Treeview(parent, columns=[c for c, _, _ in cols], show="headings", height=height,
                         style="Data.Treeview", selectmode="none")
        for c, label, w in cols:
            t.heading(c, text=label, anchor="w")
            t.column(c, width=theme.px(w * 0.6), minwidth=theme.px(40), anchor="w", stretch=True)
        t.tag_configure("odd", background=theme.STRIPE)
        t.pack(fill="x", pady=(theme.px(12), 0))
        return t

    def _icon_label(self, parent, name, style, fallback=""):
        return ttk.Label(parent, text=theme.icon(name, fallback), style=style)

    def _build(self):
        P = theme.px
        outer = ttk.Frame(self, padding=(P(22), P(16), P(22), P(14)))
        outer.pack(fill="both", expand=True)

        # En-tête : logo, nom, version, mises à jour, aide
        head = ttk.Frame(outer)
        head.pack(fill="x")
        ttk.Label(head, text=theme.icon("shield", "AF"), style="Logo.TLabel").pack(side="left")
        names = ttk.Frame(head)
        names.pack(side="left", padx=(P(12), 0))
        ttk.Label(names, text="Archive Familiale", style="Title.TLabel").pack(anchor="w")
        ttk.Label(names, text=f"Vos photos, vidéos et documents réunis, sans doublons, en sécurité  ·  "
                              f"version {core.VERSION}", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(head, text="Aide", command=self.show_help).pack(side="right")
        ttk.Button(head, text="Mises à jour…", command=self.check_update).pack(side="right", padx=(0, P(8)))
        ttk.Button(head, text="Notifications…", command=lambda: NotifyDialog(self)).pack(side="right", padx=(0, P(8)))
        self.btn_update = ttk.Button(head, text="", style="Accent.TButton", command=self.install_update)

        # Prochaine étape : une seule action conseillée, bien visible
        self.hero = ttk.Frame(outer, style="Hero.TFrame", padding=(P(20), P(16), P(20), P(16)))
        self.hero.pack(fill="x", pady=(P(16), 0))
        self.hero.columnconfigure(1, weight=1)
        self.hero_icon = ttk.Label(self.hero, text="", style="HeroIconBig.TLabel")
        self.hero_icon.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, P(16)))
        self.hero_kicker = ttk.Label(self.hero, text="PROCHAINE ÉTAPE", style="HeroKicker.TLabel")
        self.hero_kicker.grid(row=0, column=1, sticky="w")
        self.hero_title = ttk.Label(self.hero, text="", style="HeroTitle.TLabel")
        self.hero_title.grid(row=1, column=1, sticky="w")
        self.hero_text = ttk.Label(self.hero, text="", style="HeroMuted.TLabel", justify="left")
        self.hero_text.grid(row=2, column=1, sticky="ew", pady=(P(2), 0))
        autowrap(self.hero_text)
        self.hero_btn = ttk.Button(self.hero, text="", style="Big.Accent.TButton")
        self.hero_btn.grid(row=0, column=2, rowspan=3, sticky="e", padx=(P(16), 0))
        self.hero_btn._needs_master = False
        self.hero_btn._only_without_master = False
        self.action_buttons.append(self.hero_btn)

        # Chiffres clés de l'archive
        stats = ttk.Frame(outer, style="Card.TFrame", padding=(P(8), P(12), P(8), P(12)))
        stats.pack(fill="x", pady=(P(12), 0))
        self.stat = {}
        for i, (key, ico, caption) in enumerate((("files", "files", "fichiers archivés"),
                                                 ("size", "size", "au total"),
                                                 ("disks", "drive", "disques d'archive"),
                                                 ("backups", "backup", "sauvegardes à jour"))):
            stats.columnconfigure(i * 2, weight=1, uniform="stat")
            if i:
                ttk.Separator(stats, orient="vertical").grid(row=0, column=i * 2 - 1, sticky="ns", pady=P(4))
            tile = ttk.Frame(stats, style="CardFlat.TFrame", padding=(P(14), 0))
            tile.grid(row=0, column=i * 2, sticky="ew")
            self._icon_label(tile, ico, "CardIcon.TLabel").pack(side="left", padx=(0, P(12)))
            box = ttk.Frame(tile, style="CardFlat.TFrame", padding=0)
            box.pack(side="left", fill="x")
            value = ttk.Label(box, text="—", style="CardBig.TLabel")
            value.pack(anchor="w")
            sub = ttk.Label(box, text=caption, style="CardMuted.TLabel")
            sub.pack(anchor="w")
            self.stat[key] = (value, sub)

        # Étapes (à gauche) et détail de l'étape choisie (à droite)
        main = ttk.Frame(outer)   # placé en dernier (plus bas) : l'activité garde toujours sa place
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        nav = ttk.Frame(main, style="Card.TFrame", padding=P(8))
        nav.grid(row=0, column=0, sticky="nsw", padx=(0, P(12)))
        ttk.Label(nav, text="LES ÉTAPES", style="CardKicker.TLabel", padding=(P(10), P(6), 0, P(6))).pack(anchor="w")
        self.detail = ttk.Frame(main, style="Card.TFrame", padding=(P(24), P(20), P(24), P(20)))
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.columnconfigure(0, weight=1)
        self.detail.rowconfigure(0, weight=1)
        self.nav = nav
        self.steps = {}
        self.selected_step = None

        s1 = self._step(1, "Disques de l'archive",
                        "Les disques neufs qui contiennent l'archive. ARCHIVE-1 garde le catalogue : "
                        "il doit être branché à chaque fois.",
                        [("Créer l'archive…", self.create_archive, True, True),
                         ("Ajouter un disque à l'archive…", self.add_main_disk, True, False),
                         ("Ouvrir une archive existante…", self.open_archive, False, True),
                         ("Regrouper sur un plus grand disque…", self.regroup, False, False)])
        self.tree_vol = self._tree(s1, [("disque", "Disque", 130), ("branche", "Branché ?", 170),
                                        ("fichiers", "Fichiers", 90), ("donnees", "Données", 100),
                                        ("libre", "Libre", 100), ("verif", "Vérification", 200)], 3)

        s2 = self._step(2, "Importer les anciens disques",
                        "Choisissez les disques à importer (ils s'ajoutent à la liste), puis démarrez : ils sont "
                        "importés l'un après l'autre, sans surveillance, et ne sont jamais modifiés.",
                        [("Choisir les disques…", lambda: self.add_source(copy=True), True, False),
                         ("Démarrer l'import", self.start_import, True, False),
                         ("Retirer de la liste", self.remove_planned, False, False),
                         ("Estimer la place nécessaire…", lambda: self.add_source(copy=False), False, False)])
        self.btn_start, self.btn_remove = self.action_buttons[-3], self.action_buttons[-2]
        self.tree_src = self._tree(s2, [("nom", "Nom", 160), ("desc", "Description", 190),
                                        ("fichiers", "Fichiers", 80), ("taille", "Taille", 85),
                                        ("copies", "Nouveaux copiés", 130), ("etat", "Import", 210),
                                        ("controle", "Contrôle", 120)], 5)
        self.tree_src.configure(selectmode="extended")

        self._step(3, "Vérifier l'archive",
                   "Relit chaque fichier de l'archive et le compare à son empreinte : on sait ainsi que "
                   "rien n'est abîmé. À faire une fois tous les anciens disques importés, puis une fois par an.",
                   [("Vérifier maintenant", self.verify_master, True, False)])

        s4 = self._step(4, "Sauvegardes",
                        f"Des copies complètes de l'archive sur d'autres disques. Au moins {RECOMMENDED_BACKUPS} jeux "
                        "conseillés, dont un rangé hors de la maison.",
                        [("Créer un jeu de sauvegarde…", self.create_set, True, False),
                         ("Mettre à jour les sauvegardes", self.update_backups, True, False),
                         ("Ajouter un disque à un jeu…", self.add_set_disk, False, False),
                         ("Vérifier une sauvegarde…", self.verify_backups, False, False),
                         ("Je ne veux pas de sauvegarde…", self.toggle_backups, False, False)])
        self.btn_toggle_backups = self.action_buttons[-1]
        self.tree_set = self._tree(s4, [("jeu", "Jeu", 120), ("disques", "Disques (✓ = branché)", 300),
                                        ("etat", "État", 170), ("maj", "Dernière mise à jour", 150),
                                        ("verif", "Dernière vérification", 150)], 3)

        self._step(5, "Contrôler les anciens disques",
                   "Avant de ranger ou de donner un ancien disque : le programme confirme que tout son contenu "
                   "est bien dans l'archive.",
                   [("Contrôler un ancien disque…", self.check_source, True, False)])
        self._step(6, "Classer par type et par date",
                   "Facultatif. Range les fichiers en « Photos et vidéos / 2009 / 2009-08 Vacances Bretagne »… "
                   "Aperçu avant de valider, et annulable.",
                   [("Classer l'archive…", self.classify, True, False),
                    ("Annuler le dernier classement", self.undo_classify, False, False)])

        s7 = self._step(7, "Bilan : ce que contient l'archive",
                        "Tout ce qui a été trouvé sur les anciens disques, doublons retirés : combien de photos, "
                        "de vidéos, de documents… et sur quelle période.",
                        [("Créer « Nos souvenirs » sur les disques", self.make_souvenirs, True, False),
                         ("Ouvrir « Nos souvenirs »", self.open_souvenirs, True, False),
                         ("Actualiser le bilan", lambda: self.refresh_summary(force=True), False, False)])
        both = ttk.Frame(s7, style="CardFlat.TFrame")   # tableau par type à gauche, frise à droite
        both.pack(fill="both", expand=True)
        both.columnconfigure(0, weight=5, uniform="bilan")
        both.columnconfigure(1, weight=4, uniform="bilan")
        left = ttk.Frame(both, style="CardFlat.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, P(16)))
        self.tree_kind = self._tree(left, [("type", "Type", 230), ("nombre", "Nombre", 100),
                                           ("taille", "Taille", 100), ("periode", "Période", 120)], 9)
        right = ttk.Frame(both, style="CardFlat.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="PHOTOS ET VIDÉOS PAR ANNÉE", style="CardKicker.TLabel").pack(anchor="w", pady=(P(12), 0))
        self.chart = tk.Canvas(right, height=P(170), background=theme.CARD, highlightthickness=0)
        self.chart.pack(fill="x", pady=(P(4), 0))
        self.chart.bind("<Configure>", lambda e: self._draw_chart())
        self.summary = None        # dernier bilan calculé
        self.summary_key = None    # état de l'archive au moment du calcul

        # Activité : opération en cours, progression, détail repliable
        self.act = ttk.Frame(outer, style="Card.TFrame", padding=(P(18), P(12), P(18), P(12)))
        self.act.columnconfigure(1, weight=1)
        self.act_icon = ttk.Label(self.act, text=theme.icon("info", "•"), style="CardIcon.TLabel")
        self.act_icon.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, P(12)))
        self.lbl_status = ttk.Label(self.act, text="Prêt.", style="CardStrong.TLabel")
        self.lbl_status.grid(row=0, column=1, sticky="w")
        self.progress = SmoothProgress(self.act, mode="determinate", maximum=1000)
        self.progress.grid(row=1, column=1, sticky="ew", pady=(P(6), 0))
        self.btn_log = ttk.Button(self.act, text="Afficher le détail", style="Toolbutton", command=self.toggle_log)
        self.btn_log.grid(row=0, column=2, rowspan=2, padx=(P(12), 0))
        self.btn_stop = ttk.Button(self.act, text="Mettre en pause", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=3, rowspan=2, padx=(P(8), 0))
        self.logf = ttk.Frame(self.act, style="CardFlat.TFrame", padding=0)
        self.txt = tk.Text(self.logf, height=8, wrap="word", font="AFMono", state="disabled", relief="flat",
                           background=theme.STRIPE, foreground=theme.TEXT, padx=P(10), pady=P(8),
                           highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(self.logf, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_visible = False

        # Liens utiles
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", side="bottom", pady=(P(10), 0))
        self.act.pack(fill="x", side="bottom", pady=(P(12), 0))
        main.pack(fill="both", expand=True, pady=(P(12), 0))
        for text, cmd in (("Rapport détaillé", self.show_report),
                          ("Exporter les listes (Excel)", self.export_csv),
                          ("Ouvrir le dossier de l'archive", self.open_folder),
                          ("Ouvrir le journal", self.open_log)):
            b = ttk.Button(bottom, text=text, command=cmd, style="Toolbutton")
            b.pack(side="left", padx=(0, P(4)))
            b._needs_master = True
            b._only_without_master = False
            self.action_buttons.append(b)
        ttk.Label(bottom, text="Les anciens disques ne sont jamais modifiés : ils sont seulement lus.",
                  style="Muted.TLabel").pack(side="right")

    def _step(self, n, title, intro, buttons):
        """Une ligne dans la liste des étapes, et son panneau de détail.
        buttons : (texte, action, principal, sans_archive) ; sans_archive = utilisable sans archive."""
        P = theme.px
        # Ligne de la liste (cliquable)
        row = ttk.Frame(self.nav, style="Row.TFrame", padding=(P(10), P(6), P(12), P(6)), cursor="hand2")
        row.pack(fill="x", pady=P(1))
        row.columnconfigure(1, weight=1)
        glyph = ttk.Label(row, text=theme.kind_glyph("todo"), style="RowIcon.TLabel", anchor="center")
        glyph.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, P(8)))
        row.columnconfigure(0, minsize=P(30))   # textes alignés quelle que soit l'icône
        name = ttk.Label(row, text=f"{n}. {title}", style="RowStrong.TLabel")
        name.grid(row=0, column=1, sticky="w")
        short = ttk.Label(row, text="", style="RowMuted.TLabel")
        short.grid(row=1, column=1, sticky="w")
        chevron = ttk.Label(row, text=theme.icon("chevron", "›"), style="RowFaint.TLabel")
        chevron.grid(row=0, column=2, rowspan=2, sticky="e", padx=(P(10), 0))
        parts = (row, glyph, name, short, chevron)
        for w in parts:
            w.bind("<Button-1>", lambda e, k=n: self.select_step(k))
            w.bind("<Enter>", lambda e, k=n: self._hover_step(k, True))
            w.bind("<Leave>", lambda e, k=n: self._hover_step(k, False))

        # Panneau de détail
        f = ttk.Frame(self.detail, style="CardFlat.TFrame", padding=0)
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(1, weight=1)
        head = ttk.Frame(f, style="CardFlat.TFrame", padding=0)
        head.pack(fill="x")
        self._icon_label(head, self.STEP_ICONS[n], "CardIconBig.TLabel").pack(side="left", padx=(0, P(14)))
        names = ttk.Frame(head, style="CardFlat.TFrame", padding=0)
        names.pack(side="left", fill="x", expand=True)
        ttk.Label(names, text=f"ÉTAPE {n}", style="CardKicker.TLabel").pack(anchor="w")
        ttk.Label(names, text=title, style="CardTitle.TLabel").pack(anchor="w")
        pill = ttk.Label(head, text="", style="Pilltodo.TLabel")
        pill.pack(side="right", anchor="n")
        intro_lbl = ttk.Label(f, text=intro, style="CardMuted.TLabel", justify="left")
        intro_lbl.pack(anchor="w", fill="x", pady=(P(12), 0))
        autowrap(intro_lbl)
        status = ttk.Label(f, text="", style="Card.TLabel", justify="left")
        status.pack(anchor="w", fill="x", pady=(P(10), 0))
        autowrap(status)
        bf = ttk.Frame(f, style="CardFlat.TFrame", padding=0)
        bf.pack(fill="x", side="bottom", pady=(P(16), 0))   # avant le tableau : jamais écrasés
        body = ttk.Frame(f, style="CardFlat.TFrame", padding=0)
        body.pack(fill="both", expand=True)
        rows = {True: ttk.Frame(bf, style="CardFlat.TFrame", padding=0),
                False: ttk.Frame(bf, style="CardFlat.TFrame", padding=0)}
        rows[True].pack(fill="x")
        rows[False].pack(fill="x")   # actions secondaires sur une 2e ligne : jamais coupées
        for text, cmd, primary, without in buttons:
            b = ttk.Button(rows[primary], text=text, command=cmd, style="Accent.TButton" if primary else "TButton")
            b.pack(side="left", padx=(0, P(8)), pady=(0, P(6)))
            b._needs_master = not without
            b._only_without_master = (cmd == self.create_archive)
            self.action_buttons.append(b)
        self.steps[n] = {"row": parts, "glyph": glyph, "short": short, "pill": pill, "status": status,
                         "panel": f, "kind": "todo", "hover": False}
        return body

    def select_step(self, n):
        self.selected_step = n
        for k, s in self.steps.items():
            self._paint_row(k)
        self.steps[n]["panel"].tkraise()
        if n == 7:
            self.refresh_summary()

    # ---------- bilan (étape 7) ----------
    def refresh_summary(self, force=False):
        """Calcule le bilan en arrière-plan (il peut parcourir des millions de lignes du catalogue)."""
        st = self.st
        if not st or not st["stored_n"]:
            return
        key = (self.master_path, st["stored_n"], st["last_change"], len(st["sources"]))
        if (key == self.summary_key and not force) or getattr(self, "summary_busy", False):
            return
        self.summary_busy = True
        self.steps[7]["status"].configure(text="Calcul du bilan…")
        master = self.master_path

        def worker():
            try:
                con = sqlite3.connect(os.path.join(master, core.CATALOG_DIR, core.DB_NAME), timeout=30)
                try:
                    self.q.put(("bilan", key, bilan.from_catalog(con)))
                finally:
                    con.close()
            except sqlite3.Error as e:
                self.q.put(("bilan", key, e))
        threading.Thread(target=worker, daemon=True).start()

    def _show_summary(self, key, s):
        self.summary_busy = False
        if isinstance(s, Exception):
            self.steps[7]["status"].configure(text=f"Bilan impossible à calculer : {s}")
            return
        self.summary, self.summary_key = s, key
        t = self.tree_kind
        t.delete(*t.get_children())
        for _, label, n, b, per in s.rows():
            when = "—" if not per else (f"{per[0]} – {per[1]}" if per[0] != per[1] else str(per[0]))
            self._insert(t, (label[0].upper() + label[1:], core.fmt_int(n), core.fmt_size(b), when))
        imp = s.important_rows()
        if imp:   # en plus des familles : les papiers qui comptent (identité, paie, diplômes…)
            per = s.important_period()
            when = "—" if not per else (f"{per[0]} – {per[1]}" if per[0] != per[1] else str(per[0]))
            self._insert(t, ("★ Documents importants", core.fmt_int(sum(r[2] for r in imp)),
                             core.fmt_size(sum(r[3] for r in imp)), when))
            for _, label, n, b in imp:
                self._insert(t, (f"      {label}", core.fmt_int(n), core.fmt_size(b), ""))
        t.configure(height=max(9, min(len(t.get_children()), 16)))   # au-delà : la molette fait défiler
        self._draw_chart()
        self._update_steps()

    def _draw_chart(self):
        c = self.chart
        c.delete("all")
        mem = self.summary.memories_by_year() if self.summary else None
        w, h = c.winfo_width(), c.winfo_height()
        P = theme.px
        if not mem or w < 50:
            c.create_text(P(8), h // 2, anchor="w", fill=theme.MUTED, font="AFBody",
                          text="Aucune photo ni vidéo datée pour l'instant." if self.summary else "")
            return
        years = list(range(min(mem), max(mem) + 1))
        top = max(mem.values())
        font = tkfont.nametofont("AFCaption")
        text_h = font.metrics("linespace")
        base = h - P(20)
        # Axe vertical : 3 à 5 graduations « rondes » (1, 2 ou 5 × 10^n)
        raw = top / 4
        mag = 10 ** max(0, math.floor(math.log10(raw))) if raw >= 1 else 1
        tick = next(k * mag for k in (1, 2, 5, 10) if k * mag >= raw)
        axis_max = math.ceil(top / tick) * tick
        left = font.measure(core.fmt_int(axis_max)) + P(12)
        margin = P(18)   # les années aux deux bouts restent lisibles
        slot = (w - left - margin) / len(years)
        # Nombres à plat au-dessus des barres s'ils tiennent tous dans leur largeur ; sinon à la
        # verticale, dans la barre (en blanc), ou juste au-dessus pour une barre trop courte.
        flat = font.measure(core.fmt_int(top)) <= slot - P(2)
        room = base - (text_h + P(4) if flat else text_h // 2 + P(2))   # hauteur de la graduation la plus haute
        for k in range(0, axis_max + 1, tick):
            gy = base - room * k / axis_max
            c.create_line(left - P(4), gy, w - margin + P(4), gy, fill=theme.BORDER)
            c.create_text(left - P(8), gy, anchor="e", fill=theme.MUTED, font="AFCaption", text=core.fmt_int(k))
        c.create_line(left - P(4), base - room, left - P(4), base, fill=theme.FAINT)
        bar = max(1.0, slot * 0.7)
        step = next(k for k in (1, 2, 5, 10, 20, 50) if slot * k >= P(34))   # étiquettes lisibles
        for i, y in enumerate(years):
            x = left + i * slot + (slot - bar) / 2
            cx = x + bar / 2
            n = mem.get(y, 0)
            if n:
                hh = max(P(2), room * n / axis_max)
                c.create_rectangle(x, base - hh, x + bar, base, fill=theme.ACCENT, width=0)
                label = core.fmt_int(n)
                tw = font.measure(label)
                if flat:
                    c.create_text(cx, base - hh - P(2), anchor="s", fill=theme.TEXT, font="AFCaption", text=label)
                elif hh >= tw + P(8):
                    c.create_text(cx, base - P(4), anchor="w", angle=90, fill="#FFFFFF", font="AFCaption",
                                  text=label)
                else:
                    c.create_text(cx, base - hh - P(3), anchor="w", angle=90, fill=theme.TEXT, font="AFCaption",
                                  text=label)
            if (y - years[0]) % step == 0 or (y == years[-1] and (y - years[0]) % step >= step / 2):
                c.create_text(cx, base + P(3), anchor="n", fill=theme.MUTED, font="AFCaption", text=str(y))

    def _hover_step(self, n, on):
        self.steps[n]["hover"] = on
        self._paint_row(n)

    def _paint_row(self, n):
        s = self.steps[n]
        base = "RowSel" if n == self.selected_step else ("RowHover" if s["hover"] else "Row")
        row, glyph, name, short, chevron = s["row"]
        row.configure(style=f"{base}.TFrame")
        glyph.configure(style=f"{base}Icon.TLabel", foreground=theme.KINDS[s["kind"]][1])
        name.configure(style=f"{base}Strong.TLabel")
        short.configure(style=f"{base}Muted.TLabel")
        chevron.configure(style=f"{base}Faint.TLabel")

    def toggle_log(self, show=None):
        self.log_visible = (not self.log_visible) if show is None else show
        if self.log_visible:
            self.logf.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(theme.px(10), 0))
            self.txt.see("end")
        else:
            self.logf.grid_remove()
        self.btn_log.configure(text="Masquer le détail" if self.log_visible else "Afficher le détail")

    def _set_activity(self, state):
        """Carte « Activité » : bleue avec une icône qui pulse pendant une opération, puis le résultat."""
        busy = state == "busy"
        base = "Busy" if busy else "Card"
        self.act.configure(style=f"{base}.TFrame")
        self.lbl_status.configure(style=f"{base}Strong.TLabel")
        glyph, color = {"busy": ("sync", theme.ACCENT), "ok": ("done", theme.OK), "warn": ("warn", theme.WARN),
                        "error": ("warn", theme.DANGER), "idle": ("info", theme.ACCENT)}[state]
        self.act_icon.configure(text=theme.icon(glyph, "•"), style=f"{base}Icon.TLabel", foreground=color)
        if state in ("warn", "error"):
            self.toggle_log(True)
        if busy and not getattr(self, "_pulsing", False):
            self._pulsing = True
            self._pulse(0)

    def _pulse(self, i):
        """Pulsation lente de l'icône d'activité : on voit que le programme travaille, sans agitation."""
        if not self.busy:
            self._pulsing = False
            return
        self.act_icon.configure(foreground=(theme.ACCENT, theme.ACCENT_BORDER)[i % 2])
        self.after(700, self._pulse, i + 1)

    def _set_hero(self, kind, kicker, title, text, action=None, label=""):
        """kind : 'next' (bleu) | 'ok' (vert) | 'warn' (ambre)."""
        base = {"next": "Hero", "ok": "HeroOk", "warn": "HeroWarn"}[kind]
        icon = {"next": theme.icon("chevron", "➜"), "ok": theme.icon("done", "✔"),
                "warn": theme.icon("warn", "!")}[kind]
        self.hero.configure(style=f"{base}.TFrame")
        self.hero_icon.configure(text=icon, style=f"{base}IconBig.TLabel")
        self.hero_kicker.configure(text=kicker, style=f"{base}Kicker.TLabel")
        self.hero_title.configure(text=title, style=f"{base}Title.TLabel")
        self.hero_text.configure(text=text, style=f"{base}Muted.TLabel")
        self.hero_action = action
        if action:
            self.hero_btn.configure(text=label, command=action)
            self.hero_btn.grid()
        else:
            self.hero_btn.grid_remove()

    def _set_stats(self, st):
        if not st:
            for key, (value, _) in self.stat.items():
                value.configure(text="—")
            return
        vols = st["main_vols"]
        plugged = sum(1 for v in vols if v["path"])
        up = sum(1 for s in st["sets"] if s["backlog_n"] == 0 and st["stored_n"] > 0)
        self.stat["files"][0].configure(text=core.fmt_int(st["stored_n"]))
        self.stat["size"][0].configure(text=core.fmt_size(st["stored_b"]))
        self.stat["disks"][0].configure(text=str(len(vols)))
        self.stat["disks"][1].configure(text="disques, " + (
            "tous branchés" if plugged == len(vols) else f"{plugged} branché(s)"))
        self.stat["backups"][0].configure(text=f"{up} / {max(RECOMMENDED_BACKUPS, len(st['sets']))}")

    # ---------- état ----------
    def set_master(self, path, save=True):
        self.master_path = path if has_catalog(path or "") else None
        if self.master_path and save:
            _, serial, _ = core.volume_info(self.master_path)
            self.cfg.update(master=self.master_path, master_serial=serial,
                            master_subpath=core.subpath_of(self.master_path))
            save_config(self.cfg)
        self.refresh()

    def refresh(self):
        try:
            self.st = load_state(self.master_path) if self.master_path else None
        except sqlite3.Error as e:
            self.st = None
            self.log(f"Impossible de lire le catalogue : {e}\n")
        self._update_buttons()
        self._update_steps()

    def _set_step(self, n, kind, text, short=""):
        s = self.steps[n]
        s["kind"] = kind
        s["glyph"].configure(text=theme.kind_glyph(kind))
        s["short"].configure(text=short)
        s["pill"].configure(text=theme.KINDS[kind][4], style=f"Pill{kind}.TLabel")
        s["status"].configure(text=text)
        self._paint_row(n)

    def _insert(self, tree, values, iid=None):
        tree.insert("", "end", iid=iid, values=values, tags=("odd",) if len(tree.get_children()) % 2 else ())

    def _update_steps(self):
        st = self.st
        for t in (self.tree_vol, self.tree_src, self.tree_set):
            t.delete(*t.get_children())
        self._set_stats(st)
        if not st:
            self._set_step(1, "warn", "Aucune archive ouverte. Branchez un disque neuf puis cliquez sur « Créer "
                                      "l'archive… » (ou « Ouvrir… » si elle existe déjà).", "Aucune archive ouverte")
            for n in (2, 3, 4, 5, 6):
                self._set_step(n, "todo", "Disponible une fois l'archive créée (étape 1).", "Après l'étape 1")
            self._set_hero("next", "POUR COMMENCER", "Créer votre archive",
                           "Branchez un disque NEUF (vide) puis cliquez sur « Créer l'archive ». Il deviendra "
                           "ARCHIVE-1. Si l'archive existe déjà, ouvrez-la depuis l'étape 1.",
                           self.create_archive, "Créer l'archive…")
            self.title(APP_TITLE)
            if self.selected_step is None:
                self.select_step(1)
            return
        self.title(f"{APP_TITLE} — {self.master_path}")

        # Étape 1 : disques de l'archive
        free_plugged = 0
        for v in st["main_vols"]:
            plugged = v["path"] is not None
            free_plugged += v["free"] or 0
            if v["last_verify"] and v["last_verify_status"] == "ok" and v["last_verify"] >= (v["last_added"] or ""):
                ver = f"✔ {short_date(v['last_verify'])}"
            elif v["last_verify"]:
                ver = f"● à refaire ({v['last_verify_status']})" if v["last_verify_status"] != "ok" else "● à refaire"
            else:
                ver = "jamais"
            where = f"✓ {v['path'][:2]}" if plugged else "✗ non branché"
            if v["number"] == 1:
                where += " (principal)"
            self._insert(self.tree_vol, (v["name"], where, core.fmt_int(v["files"]), core.fmt_size(v["bytes"]),
                                         core.fmt_size(v["free"]) if plugged else "?", ver))
        unplugged = [v["name"] for v in st["main_vols"] if not v["path"]]
        txt = (f"{len(st['main_vols'])} disque(s) — {core.fmt_int(st['stored_n'])} fichiers, "
               f"{core.fmt_size(st['stored_b'])} — place libre sur les disques branchés : {core.fmt_size(free_plugged)}")
        if unplugged:
            txt += f". Non branché(s) : {', '.join(unplugged)}."
        low = free_plugged < LOW_SPACE
        if low:
            txt += "  ⚠ Peu de place : ajoutez un disque à l'archive avant le prochain import."
        self._set_step(1, "warn" if low else "done", txt,
                       "Peu de place libre" if low else f"{len(st['main_vols'])} disque(s), "
                                                        f"{core.fmt_size(free_plugged)} libres")

        # Étape 2 : sources
        srcs = st["sources"]
        pending = [s for s in srcs if not s["completed"] and s["last_mode"] != "scan"]
        srcs_done = [s for s in srcs if s["last_mode"] != "scan"]   # les simples estimations ne comptent pas
        planned = {it["label"]: it for it in self.iq["items"]} if self.iq else {}
        for s in srcs:
            if s["completed"]:
                etat = "✔ Terminé"
            elif s["last_mode"] == "scan":
                etat = "Estimé (pas copié)"
            else:
                etat = "● À reprendre" + (f" ({s['ne']} erreurs)" if s["ne"] else "")
            if s["last_check_status"] and s["last_check"] and s["last_check"] >= (s["last_seen"] or ""):
                ctrl = "✔ Rangeable" if s["last_check_status"].startswith("ok") else "● Problèmes"
            else:
                ctrl = "—"
            if s["label"] in planned:
                etat = {"commencé": "⏳ En attente (déjà commencé)", "terminé": "⏳ En attente (déjà fait)",
                        "nouveau": "⏳ En attente"}[self._plan_state(planned[s["label"]])]
            self._insert(self.tree_src, (s["label"], s["note"] or "", core.fmt_int(s["n"]), core.fmt_size(s["sz"]),
                                         f"{core.fmt_int(s['nc'])} ({core.fmt_size(s['szc'])})", etat, ctrl),
                         iid=s["label"])
        for label, it in planned.items():
            if label not in {s["label"] for s in srcs}:
                self._insert(self.tree_src, (label, it.get("note") or "", "—",
                                             core.fmt_size(it["size"]) if it.get("size") else "—", "—",
                                             "⏳ En attente (pas commencé)", "—"), iid=label)
        if planned and not self.busy:
            states = Counter(self._plan_state(it) for it in planned.values())
            detail = ", ".join(f"{n} {what}" for what, n in (("déjà commencé(s), repris en premier", states["commencé"]),
                                                               ("pas encore commencé(s)", states["nouveau"]),
                                                               ("déjà terminé(s), simplement revérifié(s)",
                                                                states["terminé"])) if n)
            self._set_step(2, "warn", f"{len(planned)} disque(s) en attente : {detail}. Laissez-les branchés et "
                                      "cliquez sur « Démarrer l'import ».", f"{len(planned)} disque(s) en attente")
        elif not srcs_done:
            self._set_step(2, "todo", "Aucun disque importé pour l'instant. Branchez des anciens disques puis "
                                      "cliquez sur « Choisir les disques… ».", "Aucun disque importé")
        elif pending:
            self._set_step(2, "warn", f"{len(srcs_done)} disque(s) connu(s), dont {len(pending)} à importer ou à "
                                      f"reprendre (rebranchez-le et choisissez-le à nouveau : il reprendra où il en était).",
                           f"{len(pending)} disque(s) à importer ou reprendre")
        else:
            self._set_step(2, "done", f"{len(srcs_done)} disque(s) importé(s). Importez les suivants, ou passez à "
                                      f"l'étape 3 quand TOUS les anciens disques sont faits.",
                           f"{len(srcs_done)} disque(s) importé(s)")

        # Étape 3 : vérification, disque par disque
        to_verify = [v for v in st["main_vols"] if v["files"] and not (
            v["last_verify"] and v["last_verify_status"] == "ok" and v["last_verify"] >= (v["last_added"] or ""))]
        if not st["stored_n"]:
            self._set_step(3, "todo", "Rien à vérifier pour l'instant.", "Rien à vérifier")
        elif not to_verify:
            self._set_step(3, "done", "Tous les disques de l'archive ont été vérifiés : tout est intact.",
                           "Tout est intact")
        else:
            names = ", ".join(v["name"] + ("" if v["path"] else " (non branché)") for v in to_verify)
            self._set_step(3, "warn" if any(v["last_verify"] for v in st["main_vols"]) else "todo",
                           f"À vérifier : {names}. Branchez ces disques puis « Vérifier maintenant » "
                           f"(relit tout : compter plusieurs heures).", f"{len(to_verify)} disque(s) à vérifier")

        # Étape 4 : jeux de sauvegarde
        n_ok = 0
        for s in st["sets"]:
            up = s["backlog_n"] == 0 and st["stored_n"] > 0
            n_ok += up
            disks = "  ".join(("✓ " if v["path"] else "✗ ") + v["name"] for v in s["vols"]) or "(aucun disque)"
            etat = "✔ À jour" if up else f"● {core.fmt_int(s['backlog_n'])} fichiers à copier ({core.fmt_size(s['backlog_b'])})"
            ver = short_date(s["last_verify"]) + (f" ({s['last_verify_status']})" if s["last_verify_status"] else "") \
                if s["last_verify"] else "jamais"
            self._insert(self.tree_set, (s["name"], disks, etat, short_date(s["last_sync"]) or "jamais", ver))
        no_backup = st["meta"].get("backup_policy") == "aucune" and not st["sets"]
        self.btn_toggle_backups.configure(text="Réactiver les sauvegardes" if no_backup
                                          else "Je ne veux pas de sauvegarde…")
        if no_backup:
            self._set_step(4, "off", "Pas de sauvegarde : c'est votre choix. ⚠ L'archive est alors la SEULE copie : "
                                     "si un de ses disques tombe en panne, son contenu est perdu. Vous pouvez "
                                     "changer d'avis à tout moment (« Créer un jeu de sauvegarde… »).",
                           "Désactivées (votre choix)")
        elif n_ok >= RECOMMENDED_BACKUPS:
            self._set_step(4, "done", f"{n_ok} jeux de sauvegarde à jour. Rangez-en un hors de la maison.",
                           f"{n_ok} jeux à jour")
        elif st["sets"]:
            self._set_step(4, "warn", f"{n_ok} jeu(x) à jour sur {RECOMMENDED_BACKUPS} recommandés. Branchez les disques "
                                      f"d'un jeu et cliquez « Mettre à jour les sauvegardes », ou créez un autre jeu.",
                           f"{n_ok} à jour sur {RECOMMENDED_BACKUPS} conseillés")
        else:
            self._set_step(4, "todo", "Aucune sauvegarde. Branchez un disque neuf et cliquez « Créer un jeu de "
                                      f"sauvegarde… » ({RECOMMENDED_BACKUPS} jeux conseillés).", "Aucune sauvegarde")

        # Étape 5 : contrôle des anciens disques
        checked = [s for s in srcs_done if s["last_check_status"] and s["last_check_status"].startswith("ok")
                   and s["last_check"] >= (s["last_seen"] or "")]
        if srcs_done and len(checked) == len(srcs_done):
            self._set_step(5, "done", f"Les {len(srcs_done)} anciens disques ont été contrôlés : leur contenu est "
                                      f"dans l'archive.", "Tous contrôlés")
        elif srcs_done:
            self._set_step(5, "warn" if checked else "todo",
                           f"{len(checked)}/{len(srcs_done)} anciens disques contrôlés. Ne vous séparez d'un ancien "
                           + ("disque qu'après contrôle. Sans sauvegarde, garder les anciens disques reste votre "
                              "seule copie de secours." if no_backup else
                              "disque qu'après contrôle ET sauvegardes à jour."),
                           f"{len(checked)} sur {len(srcs_done)} contrôlé(s)")
        else:
            self._set_step(5, "todo", "Rien à contrôler pour l'instant.", "Rien à contrôler")

        # Étape 6 : classement
        cm = st["meta"].get("classification_model")
        if not st["stored_n"]:
            self._set_step(6, "todo", "Disponible une fois des fichiers importés.", "Après les imports")
        elif not cm:
            self._set_step(6, "off", "Non classée : les fichiers sont rangés par ancien disque. Quand tous les disques "
                                     "sont importés, vous pouvez tout classer par type et par date (aperçu avant de "
                                     "valider, annulable).", "Facultatif")
        elif st["unclassified"]:
            self._set_step(6, "warn", f"Classée selon le modèle {cm} ({classement.MODELS.get(cm, '')}) le "
                                      f"{short_date(st['meta'].get('classification_at'))}. "
                                      f"{core.fmt_int(st['unclassified'])} fichiers importés depuis sont à classer : "
                                      f"relancez « Classer l'archive… ».", f"{core.fmt_int(st['unclassified'])} à classer")
        else:
            self._set_step(6, "done", f"Classée selon le modèle {cm} ({classement.MODELS.get(cm, '')}) le "
                                      f"{short_date(st['meta'].get('classification_at'))}.", f"Modèle {cm}")

        # Étape 7 : bilan
        s = self.summary if self.summary_key and self.summary_key[0] == self.master_path else None
        if not st["stored_n"]:
            self._set_step(7, "todo", "Disponible après le premier import.", "Après les imports")
        elif s:
            self._set_step(7, "done", "\n".join(s.highlights(core.fmt_int, core.fmt_size)),
                           f"{core.fmt_int(s.count['photo'])} photos, {core.fmt_int(s.count['video'])} vidéos")
        elif not getattr(self, "summary_busy", False):
            self._set_step(7, "done", "Ouvrez cette étape pour voir le bilan.", "Photos, vidéos, documents…")
        if self.selected_step == 7:
            self.refresh_summary()

        # Prochaine étape conseillée : une seule action, bien visible
        sets_late = any(s["backlog_n"] for s in st["sets"])
        iq = self.iq if self.iq and self.iq["paused"] and not self.busy else None
        if self.busy:
            n = 2 if self.iq else (self.selected_step or 1)
            left = len(self.iq["items"]) - 1 if self.iq else 0
            self._set_hero("next", "EN COURS", self.job_title or "Opération en cours",
                           "Vous pouvez laisser l'ordinateur travailler seul"
                           + (f" : encore {left} disque(s) après celui-ci." if left > 0 else ".")
                           + " Pour l'interrompre sans rien perdre : « Mettre en pause », en bas.")
        elif st["meta"].get("regroup_target"):
            n = 1
            self._set_hero("warn", "REGROUPEMENT EN PAUSE", "Regroupement de l'archive à reprendre",
                           "La copie de l'archive sur le nouveau disque n'est pas finie. Branchez tous les disques "
                           "de l'archive et le nouveau disque, puis reprenez : rien n'est refait.",
                           self.regroup, "Reprendre le regroupement")
        elif iq:
            n = 1 if iq["paused"] == "plein" and low else 2
            names = ", ".join(it["label"] for it in iq["items"][:4]) + ("…" if len(iq["items"]) > 4 else "")
            if iq["paused"] == "attente":
                self._set_hero("next", "PRÊT À DÉMARRER", f"{len(iq['items'])} disque(s) prêt(s) à importer",
                               f"{names}. Vérifiez qu'ils sont branchés, puis démarrez : ils seront importés l'un "
                               "après l'autre, même en votre absence.", self.start_import, "Démarrer l'import")
            elif iq["paused"] == "plein":
                self._set_hero("warn", "IMPORT EN PAUSE", "L'archive est pleine",
                               f"{len(iq['items'])} disque(s) attendent : {names}. Branchez un disque NEUF et "
                               f"ajoutez-le : l'import reprendra tout seul là où il s'était arrêté.",
                               *((self.add_main_disk, "Ajouter un disque…") if low else
                                 (self.resume_queue, "Reprendre l'import")))
            else:
                self._set_hero("warn", "IMPORT EN PAUSE", f"{len(iq['items'])} disque(s) en attente",
                               f"En attente : {names}. Rebranchez ces disques (peu importe le port ou la "
                               "lettre) puis reprenez : l'import repartira là où il s'était arrêté.",
                               self.resume_queue, "Reprendre l'import")
        elif low:
            n = 1
            self._set_hero("warn", "ATTENTION", "Il reste peu de place sur l'archive",
                           "Ajoutez un disque neuf à l'archive avant le prochain import : il deviendra "
                           f"ARCHIVE-{len(st['main_vols']) + 1}.", self.add_main_disk, "Ajouter un disque…")
        elif not srcs_done or pending:
            n = 2
            self._set_hero("next", "PROCHAINE ÉTAPE", "Importer les anciens disques",
                           (f"{len(pending)} disque(s) à reprendre : rebranchez-le et relancez l'import, il reprend "
                            "là où il s'était arrêté." if pending and any(s["last_mode"] != "scan" for s in pending)
                            else "Branchez vos anciens disques (plusieurs à la fois si vous voulez) et choisissez "
                                 "ceux à importer. Vous démarrerez ensuite l'import : ils passeront l'un après "
                                 "l'autre, même en votre absence."),
                           lambda: self.add_source(copy=True), "Choisir les disques…")
        elif to_verify:
            n = 3
            self._set_hero("next", "PROCHAINE ÉTAPE", "Vérifier l'archive",
                           "Une fois TOUS les anciens disques importés : branchez les disques de l'archive et "
                           "lancez la vérification. Elle relit tout et peut durer plusieurs heures.",
                           self.verify_master, "Vérifier maintenant")
        elif n_ok < RECOMMENDED_BACKUPS and not no_backup:
            n = 4
            if sets_late:
                self._set_hero("next", "PROCHAINE ÉTAPE", "Mettre à jour les sauvegardes",
                               "Branchez les disques d'un jeu de sauvegarde : les fichiers ajoutés depuis la dernière "
                               "fois y seront copiés et vérifiés.", self.update_backups, "Mettre à jour")
            else:
                self._set_hero("next", "PROCHAINE ÉTAPE", "Créer une sauvegarde",
                               f"Une copie complète de l'archive sur un disque neuf. {RECOMMENDED_BACKUPS} jeux "
                               "conseillés, dont un rangé hors de la maison.", self.create_set,
                               "Créer un jeu de sauvegarde…")
        elif len(checked) < len(srcs_done):
            n = 5
            self._set_hero("next", "PROCHAINE ÉTAPE", "Contrôler les anciens disques",
                           "Avant de ranger un ancien disque, rebranchez-le : le programme confirme que tout son "
                           "contenu est bien dans l'archive.", self.check_source, "Contrôler un disque…")
        else:
            n = 6 if not cm else 3
            self._set_hero("ok", "TOUT EST EN ORDRE", "Votre archive est complète et protégée",
                           ("Sans sauvegarde, par votre choix. " if no_backup else "") +
                           "Pensez à vérifier l'archive" + ("" if no_backup else " et les sauvegardes") +
                           " une fois par an." + ("  Facultatif : classer l'archive par type et par date "
                                                  "(étape 6)." if not cm else ""),
                           lambda: self.select_step(7), "Voir le bilan")
        if self.selected_step is None:
            self.select_step(n)

    def _update_buttons(self):
        for b in self.action_buttons:
            enabled = not self.busy and (self.master_path or not b._needs_master)
            if b._only_without_master and self.master_path:
                enabled = False
            if b in (self.btn_start, self.btn_remove):
                enabled = enabled and bool(self.iq and self.iq["items"])
            b.configure(state="normal" if enabled else "disabled")
        self.btn_stop.configure(state="normal" if self.busy else "disabled")

    # ---------- exécution des tâches en arrière-plan ----------
    def log(self, text):
        self.txt.configure(state="normal")
        self.txt.insert("end", text)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def run_jobs(self, jobs, on_all_done=None, on_finish=None):
        """jobs : liste de (titre, argv). Exécutées l'une après l'autre dans un thread.
        on_finish(results), s'il est donné, remplace les messages de fin habituels (file d'import)."""
        if self.busy:
            return
        self.busy = True
        self.usb2_warned = False
        self.job_t0 = time.monotonic()
        if not self.iq:
            self.notified_at = self.job_t0
        self.job_title = jobs[0][0] if jobs else ""
        self._update_steps()   # la carte « Prochaine étape » montre l'opération en cours
        core.CANCEL.clear()
        self._update_buttons()
        self._set_activity("busy")

        def worker():
            results = []
            for title, argv in jobs:
                self.q.put(("start", title))
                rc, err = None, None
                writer = QueueWriter(self.q)
                try:
                    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                        args = core.build_parser().parse_args(argv)
                        rc = args.func(args)
                except core.UserError as e:
                    rc, err = 2, str(e)
                except KeyboardInterrupt:
                    rc = 130
                except SystemExit as e:
                    rc, err = 2, f"Paramètres invalides ({e})"
                except Exception:
                    rc, err = 99, traceback.format_exc()
                results.append((title, rc, err))
                if err:
                    self.q.put(("log", f"\n{err}\n"))
                if rc in (2, 3, 99, 130) or core.CANCEL.is_set():
                    break
            self.q.put(("done", results, on_all_done, on_finish))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log(msg[1])
                    if "USB 2" in msg[1] and not self.usb2_warned:
                        self.usb2_warned = True
                        self.after(50, lambda t=msg[1]: messagebox.showwarning(
                            APP_TITLE, "Un disque est lent : il est sans doute branché en USB 2.\n\n"
                            + next((l.strip(" ⚠") for l in t.splitlines() if "USB 2" in l), "")))
                elif kind == "progress":
                    _, frac, text, rate, eta = msg
                    if frac is None:
                        if str(self.progress["mode"]) != "indeterminate":
                            self.progress.configure(mode="indeterminate")
                            self.progress.start(15)
                    else:
                        if str(self.progress["mode"]) != "determinate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate")
                        self.progress["value"] = frac * 1000
                    self.lbl_status.configure(text=self._queue_status(frac, text, rate, eta))
                    if (self.busy and self.cfg.get("ntfy_avancement")
                            and time.monotonic() - self.notified_at > 3600):
                        self.notified_at = time.monotonic()
                        self.notifier.send("Toujours en cours", self.lbl_status.cget("text"), priority=2,
                                           tags=("hourglass_flowing_sand",))
                elif kind == "start":
                    self.log(f"\n━━━ {msg[1]} ━━━\n")
                    self.lbl_status.configure(text=msg[1] + "…")
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress["value"] = 0
                elif kind == "done":
                    self._job_done(*msg[1:])
                elif kind == "bilan":
                    self._show_summary(*msg[1:])
                elif kind.startswith("maj_"):
                    self._on_update_msg(kind, msg[1:])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _show_pause_overlay(self, closing=False):
        if self.busy and not self.pause_overlay:
            self.btn_stop.configure(state="disabled")
            self.pause_overlay = PauseOverlay(self, closing)

    def _job_done(self, results, on_all_done, on_finish=None):
        if self.pause_overlay:   # l'opération est vraiment arrêtée : on rend la main
            self.pause_overlay.close()
            self.pause_overlay = None
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if self.closing:
            self.destroy()
            return
        self.refresh()
        if on_finish:
            on_finish(results)
            return
        worst = max((rc for _, rc, _ in results), default=0)
        if results and time.monotonic() - self.job_t0 > LONG_JOB:   # longue opération : on prévient
            self.notifier.send(f"« {results[-1][0]} » terminé" if worst == 0 else
                               f"« {results[-1][0]} » : " + ("mis en pause" if worst == 130 else "problèmes"),
                               "Tout s'est bien passé." if worst == 0 else
                               "Ouvrez Archive Familiale pour voir le détail.",
                               priority=3 if worst in (0, 130) else 4,
                               tags=("white_check_mark" if worst == 0 else "warning",))
        last_title = results[-1][0] if results else ""
        if worst == 0:
            self.progress["value"] = 1000
            self._set_activity("ok")
            self.lbl_status.configure(text="Terminé, tout s'est bien passé.")
            if on_all_done:
                on_all_done(results)
        elif worst == 130:
            self._set_activity("idle")
            self.lbl_status.configure(text="En pause. Rien n'est perdu : relancez plus tard pour reprendre.")
            messagebox.showinfo(APP_TITLE, "Opération mise en pause.\n\nRien n'est perdu : relancez la même "
                                "action plus tard, elle reprendra là où elle s'était arrêtée.")
        elif worst == 1:
            self._set_activity("warn")
            self.lbl_status.configure(text="Terminé avec des problèmes : voir le détail.")
            messagebox.showwarning(APP_TITLE, f"« {last_title} » s'est terminé, mais avec des problèmes.\n\n"
                                   "Le détail est affiché dans la zone « Activité ». Relancer l'opération "
                                   "règle souvent le souci ; sinon, le disque est peut-être abîmé.")
        elif worst == 3:
            self._set_activity("warn")
            self.lbl_status.configure(text="Arrêté : plus de place sur les disques de l'archive.")
            messagebox.showwarning(APP_TITLE, "Les disques de l'archive branchés sont PLEINS.\n\n"
                                   "• Branchez un disque de l'archive qui a encore de la place, ou\n"
                                   "• ajoutez un nouveau disque (étape 1 → « Ajouter un disque à l'archive… »).\n\n"
                                   "Puis relancez l'import : il reprendra là où il s'est arrêté.")
        else:
            err = next((e for _, rc, e in results if e), None)
            self._set_activity("error")
            self.lbl_status.configure(text="Erreur : voir le détail.")
            messagebox.showerror(APP_TITLE, (err or "Une erreur est survenue. Voir la zone « Activité ».")[:1500])

    def stop(self):
        if self.iq:
            text = ("Mettre l'import en pause ?\n\nVous pourrez ensuite fermer le programme, et même éteindre ou "
                    "déplacer l'ordinateur. Au prochain lancement, cliquez sur « Reprendre l'import » : il "
                    "repartira là où il s'était arrêté.")
        else:
            text = "Mettre l'opération en cours en pause ?\n\nVous pourrez la reprendre plus tard sans rien perdre."
        if self.busy and messagebox.askyesno(APP_TITLE, text):
            core.CANCEL.set()
            self.lbl_status.configure(text="Mise en pause…")
            self._show_pause_overlay()

    def _on_close(self):
        if not self.busy:
            self.destroy()
            return
        text = ("Un import est en cours. Le mettre en pause et quitter ?\n\nAu prochain lancement, « Reprendre "
                "l'import » le fera repartir là où il s'était arrêté." if self.iq else
                "Une opération est en cours. La mettre en pause et quitter ?\n\nElle pourra être reprise plus tard.")
        if messagebox.askyesno(APP_TITLE, text):
            self.closing = True
            core.CANCEL.set()
            self._show_pause_overlay(closing=True)

    # ---------- actions : disques de l'archive ----------
    def _m(self):
        return ["-m", self.master_path]

    def create_archive(self):
        dlg = DriveDialog(self, "create", "Créer l'archive",
                          "Branchez un disque NEUF qui contiendra l'archive, puis sélectionnez-le ci-dessous.\n"
                          "Il deviendra « ARCHIVE-1 », le disque principal (il contient le catalogue). Si un seul "
                          "disque ne suffit pas, vous pourrez en ajouter d'autres ensuite.")
        self.wait_window(dlg)
        if not dlg.result:
            return
        path = dlg.result["path"]
        if has_catalog(path):
            if messagebox.askyesno(APP_TITLE, f"Une archive existe déjà dans {path}.\nL'ouvrir ?"):
                self.set_master(path)
            return
        self.run_jobs([("Création de l'archive", ["init", path])],
                      lambda _: (self.set_master(path),
                                 messagebox.showinfo(APP_TITLE, f"Archive créée dans {path}.\n\n"
                                                     "Collez une étiquette « ARCHIVE-1 » sur ce disque.\n\n"
                                                     "Étape suivante : branchez des anciens disques et cliquez "
                                                     "sur « Choisir les disques… ».")))

    def open_archive(self):
        folder = filedialog.askdirectory(title="Choisir le dossier ArchiveFamiliale du disque ARCHIVE-1")
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not has_catalog(folder) and (has_catalog(os.path.join(folder, ARCHIVE_FOLDER)) or
                                        core.read_marker(os.path.join(folder, ARCHIVE_FOLDER))):
            folder = os.path.join(folder, ARCHIVE_FOLDER)
        m = core.read_marker(folder)
        if not has_catalog(folder):
            if m:
                messagebox.showerror(APP_TITLE, f"Ce dossier est le disque « {m.get('name')} ». Ouvrez plutôt "
                                     "le disque ARCHIVE-1 : c'est lui qui contient le catalogue.")
            else:
                messagebox.showerror(APP_TITLE, "Ce dossier ne contient pas d'archive.")
            return
        self.set_master(folder)

    def add_main_disk(self):
        n = len(self.st["main_vols"]) + 1
        dlg = DriveDialog(self, "addvol", "Ajouter un disque à l'archive",
                          f"Branchez un disque NEUF (ou vide) et sélectionnez-le. Il deviendra « ARCHIVE-{n} » : "
                          f"les prochains imports continueront dessus quand les autres seront pleins.")
        self.wait_window(dlg)
        if not dlg.result:
            return
        path = dlg.result["path"]
        extra = ["--accepter-disque-source"] if dlg.result.get("accept_source") else []
        def done(_):
            if self.iq and self.iq["paused"] == "plein":   # l'import attendait ce disque : il repart seul
                self.log(f"\nDisque « ARCHIVE-{n} » ajouté : l'import reprend.\n")
                self.resume_queue()
            else:
                messagebox.showinfo(APP_TITLE, f"Disque ajouté : il s'appelle « ARCHIVE-{n} ».\n\n"
                                    f"Collez-lui une étiquette « ARCHIVE-{n} ».")
        self.run_jobs([("Ajout d'un disque à l'archive", ["ajouter-disque", path, *self._m(), *extra])], done)

    # ---------- actions : sources ----------
    # ---------- regrouper l'archive sur un seul disque, plus grand ----------
    def regroup(self):
        st = self.st
        if not st:
            return
        if st["meta"].get("regroup_target"):
            target = core.find_regroup_target(st["meta"]["regroup_target"], st["meta"].get("archive_id"))
            if not target:
                messagebox.showinfo(APP_TITLE, "Un regroupement est en cours, mais son nouveau disque n'est pas "
                                    f"branché (il était en {st['meta']['regroup_target']}).\n\nBranchez-le, puis "
                                    "cliquez à nouveau sur « Reprendre le regroupement ».")
                return
            if messagebox.askyesno(APP_TITLE, f"Reprendre le regroupement de l'archive sur {target} ?\n\n"
                                   "Ce qui est déjà copié et vérifié n'est pas refait."):
                self._run_regroup(target)
            return
        vols = st["main_vols"]
        need = st["stored_b"]
        names = ", ".join(v["name"] for v in vols)
        dlg = DriveDialog(self, "regroup", "Regrouper l'archive sur un plus grand disque",
                          f"Vos {len(vols)} disques d'archive ({names}, {core.fmt_size(need)} en tout) vont être "
                          "copiés sur UN seul disque, plus grand. Branchez ce disque neuf (ou vide) et "
                          "sélectionnez-le. Il faut au moins " + core.fmt_size(need + 10 * 1024 ** 3) + " libres.")
        self.wait_window(dlg)
        if not dlg.result:
            return
        path = dlg.result["path"]
        d = dlg.result.get("drive")
        if d and d.free < need + core.FREE_SPACE_MARGIN + core.PRIMARY_EXTRA_MARGIN:
            messagebox.showerror(APP_TITLE, f"Ce disque est trop petit : {core.fmt_size(d.free)} libres, il faut "
                                 f"au moins {core.fmt_size(need + core.FREE_SPACE_MARGIN + core.PRIMARY_EXTRA_MARGIN)}.")
            return
        unplugged = [v["name"] for v in vols if not v["path"]]
        hours = max(1, round(2 * need / (120 * 1024 ** 2) / 3600))   # copie puis relecture, ~120 Mo/s
        if not messagebox.askyesno(
                APP_TITLE, f"Regrouper toute l'archive sur {path} ?\n\n"
                "1. Chaque fichier est copié sur le nouveau disque,\n"
                "2. puis relu et comparé à son empreinte,\n"
                "3. et seulement quand TOUT est vérifié, le nouveau disque devient « ARCHIVE-1 ».\n\n"
                f"Comptez environ {hours} heure(s). Vous pouvez mettre en pause et reprendre plus tard. Les anciens "
                "disques ne sont jamais modifiés pendant la copie ; à la fin, ils sont simplement « libérés » : "
                "vous pourrez les formater."
                + (f"\n\nNon branchés pour l'instant : {', '.join(unplugged)}. Branchez-les avant, ou après : "
                   "le regroupement les attendra." if unplugged else "")):
            return
        self._run_regroup(path)

    def _run_regroup(self, path):
        def done(_):
            r = dict(core.LAST_REGROUP)
            if not r:
                return
            self.set_master(r["master"])
            freed = "\n".join(f"  • {name}  ({where})" for name, where in r["freed"])
            messagebox.showinfo(APP_TITLE, f"Regroupement terminé : toute l'archive est maintenant sur {r['master']}, "
                                "qui devient « ARCHIVE-1 ». Collez-lui cette étiquette.\n\n"
                                f"Ces anciens disques ne font plus partie de l'archive :\n{freed}\n\n"
                                "Vous pouvez les formater pour vous en resservir : dans l'Explorateur, clic droit "
                                "sur le disque → « Formater… ». Les sauvegardes, elles, ne changent pas.")
            self.run_jobs([("Mise à jour de « Nos souvenirs »", ["souvenirs", *self._m()])])
        self.run_jobs([("Regroupement de l'archive", ["regrouper", path, *self._m()])], done)

    def add_source(self, copy: bool):
        intro = ("Branchez les anciens disques (autant que vous voulez), cochez-les, puis lancez : ils seront "
                 "traités l'un après l'autre, sans que vous ayez besoin d'être là. Ils sont seulement LUS : "
                 "rien n'y est modifié ni effacé.")
        if copy:
            unplugged = [v["name"] for v in self.st["main_vols"] if not v["path"]]
            if unplugged:
                intro += (f"\n\nRemarque : {', '.join(unplugged)} n'est pas branché. Ce n'est pas grave tant que "
                          "les disques branchés ont de la place.")
        else:
            intro = ("Branchez les anciens disques et cochez-les : le programme estime en quelques minutes ce "
                     "qu'ils apporteraient de nouveau à l'archive, et s'il y aura assez de place. Rien n'est "
                     "copié ni enregistré.")
        dlg = SourcesDialog(self, copy, "Importer des disques" if copy else "Estimer des disques", intro)
        self.wait_window(dlg)
        if not dlg.result:
            return
        if copy:
            self.plan_disks(dlg.result)
            return

        def done(_):
            e = core.LAST_ESTIMATE
            if not e:
                return
            lines = "\n".join(f"• {r['source']} : " + (r["error"] if "error" in r else
                               f"{core.fmt_size(r['total'])}, dont environ {core.fmt_size(r['new'])} de nouveau")
                               for r in e["rows"])
            verdict = (f"La place libre sur l'archive ({core.fmt_size(e['free'])}) devrait suffire."
                       if e["new"] <= e["free"] else
                       f"Il manquera sans doute environ {core.fmt_size(e['new'] - e['free'])} : prévoyez un "
                       f"disque d'archive de plus (étape 1).")
            content = e["summary"].text(core.fmt_int, core.fmt_size)
            messagebox.showinfo(APP_TITLE, f"Estimation rapide\n\n{lines}\n\nAu total : environ "
                                f"{core.fmt_size(e['new'])} de nouveau à copier.\n{verdict}\n\n"
                                f"Ce que contiennent ces disques :\n{content}\n\n"
                                "C'est une estimation d'après le nom et la taille des fichiers ; l'import, qui "
                                "compare leur contenu exact, trouvera souvent un peu plus de doublons.")
        self.run_jobs([("Estimation rapide", ["estimer", *(r["path"] for r in dlg.result), *self._m()])], done)

    # ---------- file d'import : plusieurs disques à la suite ----------
    def start_queue(self, items, copy):
        """items : [{path, label, note, serial, size}], traités l'un après l'autre. Archive pleine ou arrêt :
        la file se met en pause et reprend sur le disque en cours (Reprendre, ou ajout d'un disque)."""
        q = self.iq
        if q and q["paused"] and q["copy"] == copy:   # file en pause : les nouveaux disques passent après
            known = {it["label"] for it in q["items"]}
            new = [it for it in items if it["label"] not in known]
            q["items"] += new
            q["n"] += len(new)
            return self._queue_next()
        self.iq = {"items": list(items), "copy": copy, "n": len(items), "results": [], "paused": None,
                   "done_bytes": 0, "active": 0.0, "t0": None, "current": None}
        self._queue_next()

    def _queue_next(self):
        q = self.iq
        if not q["items"]:
            return self._queue_end()
        item = q["items"][0]
        # Les lettres de lecteur peuvent changer (disque rebranché pendant une pause) : on retrouve le
        # disque par son numéro de série. Un mauvais disque serait de toute façon refusé par le moteur.
        if item["serial"] and core.drive_root_of(item["path"]) == item["path"]:
            for d in core.list_drives():
                if d.serial == item["serial"]:
                    item["path"] = d.root
        argv = ["importer" if q["copy"] else "scanner", item["path"], *self._m(), "-l", item["label"]]
        if item["note"]:
            argv += ["--note", item["note"]]
        pos = q["n"] - len(q["items"]) + 1
        q["paused"], q["current"], q["t0"] = None, item, time.monotonic()
        self._save_queue()
        verb = "Import" if q["copy"] else "Estimation"
        title = f"{verb} de « {item['label']} »" + (f" — disque {pos} sur {q['n']}" if q["n"] > 1 else "")
        self.run_jobs([(title, argv)], on_finish=self._queue_step_done)

    def _queue_status(self, frac, text, rate=None, eta=None):
        """Texte de progression, précédé de la position dans la file et du temps restant pour l'ensemble.

        Le temps restant pour l'ensemble = reste du disque en cours + disques suivants, au débit récent
        du disque en cours (leur nombre de fichiers n'est pas connu d'avance) : il ne peut donc jamais
        être inférieur au « reste » du disque en cours."""
        q = self.iq
        if not q or not q["current"] or q["n"] < 2:
            return text
        pos = q["n"] - len(q["items"]) + 1
        head = f"Disque {pos} sur {q['n']}"
        sizes = [it["size"] for it in q["items"]]
        if frac is not None and rate and eta is not None and None not in sizes[1:]:
            left = eta + sum(sizes[1:]) / rate
            head += f" (ensemble : encore ≈ {core.fmt_duration(left)})"
        return f"{head} · {text}"

    def _queue_step_done(self, results):
        q = self.iq
        _, rc, err = results[-1] if results else ("", 99, "Rien n'a été exécuté.")
        item = q["items"][0]
        q["active"] += time.monotonic() - q["t0"]
        q["current"] = None
        if rc in (3, 130):   # archive pleine, ou arrêt demandé : en pause, rien n'est perdu
            q["paused"] = "plein" if rc == 3 else "arrêt"
            left = len(q["items"])
            self.refresh()
            self._set_activity("warn")
            if rc == 3:
                self.lbl_status.configure(text=f"En pause : l'archive est pleine. {left} disque(s) en attente.")
                self.deiconify()
                self.lift()
                self.bell()
                self.notifier.send("Archive pleine : import en pause",
                                   f"Branchez un disque neuf et ajoutez-le à l'archive (étape 1) : l'import "
                                   f"reprendra tout seul. {left} disque(s) en attente.", priority=5,
                                   tags=("warning",))
                messagebox.showwarning(APP_TITLE, "L'archive est PLEINE : l'import est en pause.\n\n"
                                       f"Disque en cours : « {item['label']} » ({left} disque(s) en attente).\n\n"
                                       "Branchez un disque NEUF et cliquez sur « Ajouter un disque… » : l'import "
                                       "reprendra tout seul, là où il s'est arrêté.\n\nSi vous branchez plutôt un "
                                       "disque de l'archive qui a encore de la place, cliquez sur « Reprendre "
                                       "l'import ».")
            else:
                self.lbl_status.configure(text=f"En pause. {left} disque(s) en attente : « Reprendre l'import » "
                                               "pour continuer.")
            return
        q["done_bytes"] += item["size"] or 0
        q["items"].pop(0)
        pos = len(q["results"]) + 1
        if rc == 0:
            q["results"].append(("ok", item["label"], "entièrement importé" if q["copy"] else "estimé"))
        elif rc == 1:
            q["results"].append(("warn", item["label"], "importé, mais des fichiers n'ont pas pu être lus"))
        else:
            first = (err or "erreur inattendue").strip().splitlines()[0][:200]
            q["results"].append(("error", item["label"], first))
        kind, _, text = q["results"][-1]
        r = core.LAST_RUN if rc in (0, 1) else {}
        stats = (f"\n{core.fmt_int(r['copied'])} nouveaux fichiers ({core.fmt_size(r['copied_bytes'])}), "
                 f"{core.fmt_int(r['duplicates'])} doublons, en {core.fmt_duration(r['elapsed'])}.") if r else ""
        nxt = f"\nSuivant : « {q['items'][0]['label']} »." if q["items"] else ""
        self.notifier.send(f"Disque {pos} sur {q['n']} : « {item['label']} »", f"{text.capitalize()}.{stats}{nxt}",
                           priority=3 if kind == "ok" else 4,
                           tags=({"ok": "white_check_mark", "warn": "warning", "error": "x"}[kind],))
        self._save_queue()
        self._queue_next()

    def _save_queue(self):
        """La file est enregistrée dans config.json : elle survit à la fermeture du programme et à un
        redémarrage de l'ordinateur."""
        q = self.iq
        if q and q["items"]:
            self.cfg["file_import"] = {"master": self.master_path, "copy": q["copy"], "n": q["n"],
                                       "items": q["items"], "results": q["results"]}
        else:
            self.cfg.pop("file_import", None)
        save_config(self.cfg)

    def _restore_queue(self):
        saved = self.cfg.get("file_import")
        if not saved or not self.master_path or not core.same_path(saved["master"], self.master_path):
            return
        self.iq = {"items": saved["items"], "copy": saved["copy"], "n": saved["n"],
                   "results": [tuple(r) for r in saved["results"]], "paused": "attente",
                   "done_bytes": 0, "active": 0.0, "t0": None, "current": None}
        self._update_buttons()
        self._update_steps()
        self.lbl_status.configure(text=f"{len(self.iq['items'])} disque(s) en attente d'import : "
                                       "« Démarrer l'import » pour continuer.")

    def plan_disks(self, items):
        """Ajoute des disques à la liste d'attente, sans rien lancer."""
        q = self.iq
        if not q:
            self.iq = q = {"items": [], "copy": True, "n": 0, "results": [], "paused": "attente",
                           "done_bytes": 0, "active": 0.0, "t0": None, "current": None}
        known = {it["label"] for it in q["items"]}
        for it in items:
            if it["label"] not in known:
                q["items"].append(it)
                q["n"] += 1
        self._save_queue()
        self.refresh()
        self.select_step(2)
        self.lbl_status.configure(text=f"{len(q['items'])} disque(s) en attente d'import : vérifiez la liste, "
                                       "puis « Démarrer l'import ».")

    def _plan_state(self, it):
        """Pré-analyse d'un disque de la liste : 'commencé', 'terminé' ou 'nouveau'."""
        s = next((s for s in (self.st or {}).get("sources", []) if s["label"] == it["label"]), None)
        if s and s["completed"] and s["last_mode"] != "scan":
            return "terminé"
        if s and s["last_mode"] != "scan" and s["n"]:
            return "commencé"
        return "nouveau"

    def start_import(self):
        q = self.iq
        if not q or not q["items"] or self.busy:
            return
        if q["paused"] == "attente" and not self._offer_notifications():
            return
        if q["paused"] == "attente":   # les disques déjà commencés d'abord, ceux déjà terminés à la fin
            order = {"commencé": 0, "nouveau": 1, "terminé": 2}
            q["items"].sort(key=lambda it: order[self._plan_state(it)])
            self.notified_at = time.monotonic()
        q["n"] = len(q["results"]) + len(q["items"])
        self._queue_next()

    def resume_queue(self):
        self.start_import()

    def _offer_notifications(self) -> bool:
        """Au premier « Démarrer l'import », propose d'être prévenu sur le téléphone. Rien n'est envoyé
        sans un « Oui » explicite ; un « Non » n'est plus redemandé (bouton « Notifications… » pour
        changer d'avis). Renvoie False si l'utilisateur annule le démarrage."""
        if self.notifier.enabled or self.cfg.get("ntfy_propose"):
            return True
        answer = messagebox.askyesnocancel(
            APP_TITLE, "L'import va durer longtemps. Voulez-vous être prévenu sur votre téléphone (fin de "
            "chaque disque, archive pleine, fin de l'import) ?\n\nIl faut l'application gratuite « ntfy ». "
            "Les messages contiennent seulement des noms de disques et des chiffres, et passent par le "
            "service ntfy.sh.\n\nOui : je règle le téléphone maintenant.\nNon : sans notifications (vous "
            "pourrez changer d'avis avec le bouton « Notifications… »).")
        if answer is None:
            return False
        self.cfg["ntfy_propose"] = True
        if answer:
            self.cfg.update(ntfy_accord=True, ntfy_avancement=True)
            self.cfg.setdefault("ntfy_sujet", notif.new_topic())
            save_config(self.cfg)
            NotifyDialog(self)   # l'import démarre tout de suite ; on règle le téléphone pendant ce temps
        else:
            save_config(self.cfg)
        return True

    def remove_planned(self):
        q = self.iq
        if not q or self.busy:
            return
        sel = set(self.tree_src.selection()) & {it["label"] for it in q["items"]}
        if not sel:
            messagebox.showinfo(APP_TITLE, "Sélectionnez dans le tableau un disque « en attente », puis cliquez "
                                "sur « Retirer de la liste ».")
            return
        q["items"] = [it for it in q["items"] if it["label"] not in sel]
        q["n"] -= len(sel)
        if not q["items"]:
            self.iq = None
        self._save_queue()
        self.refresh()

    def _queue_end(self):
        q = self.iq
        # Avant le bilan final : la page « Nos souvenirs » des disques est mise à jour, sans attendre
        # que quelqu'un soit là pour fermer un message.
        if q["copy"] and not q.get("souvenirs") and any(k != "error" for k, _, _ in q["results"]):
            q["souvenirs"] = True
            self.run_jobs([("Mise à jour de « Nos souvenirs »", ["souvenirs", *self._m()])],
                          on_finish=lambda results: self._queue_end())
            return
        self.iq = None
        self._save_queue()
        self.refresh()
        icons = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        lines = "\n".join(f"{icons[k]}  {label} : {text}" for k, label, text in q["results"])
        self.log(f"\n━━━ Bilan ━━━\n{lines}\n")
        bad = [k for k, _, _ in q["results"] if k != "ok"]
        self.notifier.send("Import terminé" + (" (avec des problèmes)" if bad else ""), lines,
                           priority=4 if bad else 3, tags=("warning" if bad else "tada",))
        self.progress["value"] = 1000
        self._set_activity("warn" if bad else "ok")
        if bad:
            self.lbl_status.configure(text=f"Terminé, avec des problèmes sur {len(bad)} disque(s) : voir le bilan.")
            self.toggle_log(True)
            messagebox.showwarning(APP_TITLE, f"Terminé, mais pas sans problèmes :\n\n{lines}\n\n"
                                   "Pour un disque en ⚠️ ou ❌ : rebranchez-le et relancez l'import ; les fichiers "
                                   "déjà traités sont sautés. Si le problème persiste, le disque est peut-être abîmé.")
        elif q["copy"]:
            self.select_step(7)   # « qu'y avait-il dans tous ces disques ? »
            self.lbl_status.configure(text=f"Terminé : {q['n']} disque(s) importé(s), tout s'est bien passé.")
            messagebox.showinfo(APP_TITLE, f"Terminé, tout s'est bien passé :\n\n{lines}\n\n"
                                "Vous pouvez éjecter ces disques (icône USB de Windows).")
        else:
            self.lbl_status.configure(text="Estimation terminée.")
            messagebox.showinfo(APP_TITLE, f"Estimation terminée :\n\n{lines}\n\n"
                                "Voir « Rapport détaillé » pour le total.")

    def verify_master(self):
        unplugged = [v["name"] for v in self.st["main_vols"] if not v["path"] and v["files"]]
        msg = ("La vérification relit TOUTE l'archive pour s'assurer que rien n'est abîmé. Cela peut prendre "
               "plusieurs heures.")
        if unplugged:
            msg += f"\n\nNon branché(s) : {', '.join(unplugged)} — ces disques ne seront pas vérifiés cette fois."
        if not messagebox.askyesno(APP_TITLE, msg + "\n\nLancer maintenant ?"):
            return
        self.run_jobs([("Vérification de l'archive", ["verifier", *self._m()])],
                      lambda _: messagebox.showinfo(APP_TITLE, "Vérification terminée : les fichiers des disques "
                                                    "branchés sont présents et intacts. ✔"))

    def check_source(self):
        if not self.st["sources"]:
            messagebox.showinfo(APP_TITLE, "Aucun disque n'a encore été importé.")
            return
        dlg = DriveDialog(self, "check", "Contrôler un ancien disque",
                          "Branchez l'ancien disque à contrôler et sélectionnez-le. Le programme vérifie que "
                          "TOUT son contenu se trouve bien dans l'archive (les disques de l'archive n'ont pas "
                          "besoin d'être branchés, sauf ARCHIVE-1).")
        self.wait_window(dlg)
        r = dlg.result
        if not r:
            return
        argv = ["controler", r["path"], *self._m(), "-l", r["label"]] + (["--profond"] if r["deep"] else [])
        self.run_jobs([(f"Contrôle de « {r['label']} »", argv)], lambda _: messagebox.showinfo(
            APP_TITLE, f"OUI ✔ : tout le contenu de « {r['label']} » est dans l'archive.\n\n"
                       "Ce disque pourra être rangé (ou réutilisé) une fois les sauvegardes à jour."))

    # ---------- actions : sauvegardes ----------
    def _next_set_name(self):
        names = {s["name"].lower() for s in self.st["sets"]}
        for letter in string.ascii_uppercase:
            if f"sauvegarde-{letter}".lower() not in names:
                return f"Sauvegarde-{letter}"
        return "Sauvegarde"

    def _choose_set(self, title, text, sets=None):
        sets = sets if sets is not None else self.st["sets"]
        if not sets:
            messagebox.showinfo(APP_TITLE, "Aucun jeu de sauvegarde. Commencez par « Créer un jeu de sauvegarde… ».")
            return None
        if len(sets) == 1:
            return sets[0]
        dlg = ChoiceDialog(self, title, text, [s["name"] for s in sets])
        self.wait_window(dlg)
        return next((s for s in sets if s["name"] == dlg.result), None)

    def _after_backup(self, set_names):
        def done(_):
            self.refresh()
            lines = []
            for s in self.st["sets"]:
                if s["name"] in set_names:
                    if s["backlog_n"] == 0:
                        lines.append(f"✔ {s['name']} : à jour.")
                    else:
                        lines.append(f"● {s['name']} : il reste {core.fmt_int(s['backlog_n'])} fichiers "
                                     f"({core.fmt_size(s['backlog_b'])}) à copier — voir le détail dans "
                                     f"« Activité » (disque à brancher ou place à ajouter).")
            messagebox.showinfo(APP_TITLE, "\n\n".join(lines) or "Terminé.")
        return done

    def create_set(self):
        default = self._next_set_name()
        name = simpledialog.askstring(APP_TITLE, "Nom du nouveau jeu de sauvegarde\n(lettres sans accents, chiffres, "
                                      "tirets) :", initialvalue=default, parent=self)
        if not name:
            return
        name = name.strip()
        if not core.LABEL_RE.match(name):
            messagebox.showerror(APP_TITLE, "Nom invalide. Exemple : Sauvegarde-A")
            return
        if name.lower() in {s["name"].lower() for s in self.st["sets"]}:
            messagebox.showerror(APP_TITLE, "Ce jeu existe déjà : utilisez « Ajouter un disque à un jeu… ».")
            return
        dlg = DriveDialog(self, "backup", f"Premier disque du jeu « {name} »",
                          f"Branchez un disque NEUF pour la sauvegarde et sélectionnez-le. Il deviendra "
                          f"« {name}-1 ». Si l'archive ne tient pas dessus, le programme vous proposera d'ajouter "
                          f"un autre disque au jeu.")
        self.wait_window(dlg)
        if not dlg.result:
            return
        path = dlg.result["path"]
        extra = ["--accepter-disque-source"] if dlg.result.get("accept_source") else []
        self.run_jobs([(f"Création du jeu « {name} »", ["ajouter-disque", path, *self._m(), "--jeu", name, *extra]),
                       (f"Sauvegarde vers « {name} »", ["sauvegarder", *self._m(), "--jeu", name])],
                      self._after_backup({name}))

    def add_set_disk(self):
        s = self._choose_set("Ajouter un disque à un jeu", "À quel jeu de sauvegarde ajouter un disque ?")
        if not s:
            return
        n = len(s["vols"]) + 1
        dlg = DriveDialog(self, "backup", f"Ajouter un disque au jeu « {s['name']} »",
                          f"Branchez un disque NEUF et sélectionnez-le. Il deviendra « {s['name']}-{n} ».\n"
                          f"Branchez aussi les disques de l'archive pour que la copie puisse continuer.")
        self.wait_window(dlg)
        if not dlg.result:
            return
        path = dlg.result["path"]
        self.run_jobs([(f"Ajout d'un disque au jeu « {s['name']} »",
                        ["ajouter-disque", path, *self._m(), "--jeu", s["name"],
                         *(["--accepter-disque-source"] if dlg.result.get("accept_source") else [])]),
                       (f"Sauvegarde vers « {s['name']} »", ["sauvegarder", *self._m(), "--jeu", s["name"]])],
                      self._after_backup({s["name"]}))

    def toggle_backups(self):
        if self.st["meta"].get("backup_policy") == "aucune":
            self.run_jobs([("Réactivation des sauvegardes", ["option", *self._m(), "--sauvegardes", "oui"])])
            return
        if self.st["sets"]:
            messagebox.showinfo(APP_TITLE, "Des jeux de sauvegarde existent déjà. Vous pouvez simplement ne plus "
                                "les mettre à jour, mais ils restent une protection précieuse.")
            return
        if not messagebox.askyesno(
                APP_TITLE, "Ne PAS faire de sauvegarde ?\n\n"
                "Les données seront uniquement sur les disques de l'archive. Si l'un d'eux tombe en panne, est "
                "volé ou détruit, son contenu sera perdu définitivement.\n\n"
                "C'est votre choix ; vous pourrez changer d'avis à tout moment.\n\nConfirmer « pas de sauvegarde » ?",
                icon="warning"):
            return
        self.run_jobs([("Choix : pas de sauvegarde", ["option", *self._m(), "--sauvegardes", "non"])])

    def update_backups(self):
        ready = [s for s in self.st["sets"] if any(v["path"] for v in s["vols"])]
        if not ready:
            if not self.st["sets"]:
                messagebox.showinfo(APP_TITLE, "Aucun jeu de sauvegarde. Commencez par « Créer un jeu de sauvegarde… ».")
            else:
                lines = [f"• {s['name']} : " + ", ".join(v["name"] for v in s["vols"]) for s in self.st["sets"]]
                messagebox.showinfo(APP_TITLE, "Aucun disque de sauvegarde n'est branché. Branchez les disques "
                                    "d'un jeu :\n\n" + "\n".join(lines))
            return
        jobs = [(f"Sauvegarde vers « {s['name']} »", ["sauvegarder", *self._m(), "--jeu", s["name"]]) for s in ready]
        self.run_jobs(jobs, self._after_backup({s["name"] for s in ready}))

    def verify_backups(self):
        ready = [s for s in self.st["sets"] if any(v["path"] for v in s["vols"])]
        if not ready:
            messagebox.showinfo(APP_TITLE, "Aucun disque de sauvegarde n'est branché.")
            return
        s = self._choose_set("Vérifier une sauvegarde", "Quel jeu de sauvegarde vérifier ?", ready)
        if not s:
            return
        if not messagebox.askyesno(APP_TITLE, f"Relire entièrement les disques branchés du jeu « {s['name']} » "
                                   "pour vérifier qu'ils sont intacts ? (plusieurs heures)"):
            return
        self.run_jobs([(f"Vérification de « {s['name']} »", ["verifier", *self._m(), "--jeu", s["name"]])],
                      lambda _: messagebox.showinfo(APP_TITLE, f"« {s['name']} » vérifié : les disques branchés "
                                                    "sont intacts ✔"))

    # ---------- divers ----------
    def classify(self):
        unplugged = [v["name"] for v in self.st["main_vols"] if not v["path"]]
        if unplugged:
            messagebox.showinfo(APP_TITLE, f"Branchez d'abord tous les disques de l'archive. Manquant(s) : "
                                f"{', '.join(unplugged)}.")
            return
        pending = [s["label"] for s in self.st["sources"] if not s["completed"]]
        if pending and not messagebox.askyesno(
                APP_TITLE, f"Des anciens disques ne sont pas entièrement importés ({', '.join(pending[:5])}…).\n"
                "Vous pourrez relancer le classement plus tard pour les nouveaux fichiers.\n\nContinuer ?"):
            return
        dlg = ClassifyDialog(self, self.st["meta"].get("classification_model"))
        self.wait_window(dlg)
        model = dlg.result
        if not model:
            return

        def after_preview(_):
            if messagebox.askyesno(
                    APP_TITLE, f"L'aperçu du modèle {model} est affiché dans la zone « Activité » (le plan complet, "
                    "fichier par fichier, est enregistré dans _catalogue\\classement).\n\n"
                    "Appliquer ce classement maintenant ?\n(Il pourra être annulé.)"):
                self.run_jobs([(f"Classement (modèle {model})", ["classer", *self._m(), "--modele", model,
                                                                  "--appliquer"])],
                              lambda _: messagebox.showinfo(
                                  APP_TITLE, "Classement terminé ✔\n\nOuvrez le dossier de l'archive pour voir le "
                                  "résultat. Les sauvegardes branchées ont été mises à jour ; les autres le seront à "
                                  "leur prochaine mise à jour (sans recopie)."))

        self.run_jobs([(f"Aperçu du classement (modèle {model})", ["classer", *self._m(), "--modele", model])],
                      after_preview)

    def undo_classify(self):
        if not self.st.get("can_undo"):
            messagebox.showinfo(APP_TITLE, "Aucun classement à annuler.")
            return
        if not messagebox.askyesno(APP_TITLE, "Remettre tous les fichiers là où ils étaient avant le dernier "
                                   "classement ?"):
            return
        self.run_jobs([("Annulation du classement", ["annuler-classement", *self._m()])],
                      lambda _: messagebox.showinfo(APP_TITLE, "Classement annulé : les fichiers sont revenus à leur "
                                                    "emplacement précédent."))

    def show_report(self):
        self.run_jobs([("Rapport détaillé", ["rapport", *self._m()])])

    def export_csv(self):
        out = os.path.join(self.master_path, core.CATALOG_DIR, "exports",
                           core.dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.run_jobs([("Export des listes", ["exporter", *self._m(), "--dossier", out])],
                      lambda _: self._open_path(out))

    # ---------- « Nos souvenirs » ----------
    def make_souvenirs(self):
        def done(_):
            if messagebox.askyesno(APP_TITLE, "« Nos souvenirs » est prêt sur les disques branchés.\n\nSur chaque "
                                   f"disque, un double-clic sur « {souvenirs.LAUNCHER} » ouvre l'archive dans le "
                                   "navigateur : photos par année, diaporama, documents, musique. Rien ne peut y "
                                   "être modifié.\n\nL'ouvrir maintenant ?"):
                self.open_souvenirs()
        self.run_jobs([("Création de « Nos souvenirs »", ["souvenirs", *self._m()])], done)

    def open_souvenirs(self):
        page = os.path.join(self.master_path or "", souvenirs.LAUNCHER)
        if not self.master_path or not os.path.exists(page):
            if messagebox.askyesno(APP_TITLE, "« Nos souvenirs » n'a pas encore été créé. Le créer maintenant ?"):
                self.make_souvenirs()
            return
        self._open_path(page)

    def open_folder(self):
        self._open_path(self.master_path)

    def open_log(self):
        self._open_path(os.path.join(self.master_path, core.CATALOG_DIR, "journal.log"))

    def _open_path(self, p):
        try:
            os.startfile(p)   # Windows
        except (AttributeError, OSError) as e:
            messagebox.showerror(APP_TITLE, f"Impossible d'ouvrir {p} : {e}")

    # ---------- mise à jour du programme ----------
    def check_update(self, silent=False):
        """Demande à GitHub s'il existe une version plus récente (en arrière-plan)."""
        def worker():
            try:
                self.q.put(("maj_info", maj.latest_release(), silent))
            except maj.UpdateError as e:
                self.q.put(("maj_info", e, silent))
        threading.Thread(target=worker, daemon=True).start()

    def _on_update_msg(self, kind, args):
        if kind == "maj_info":
            rel, silent = args
            if isinstance(rel, Exception):
                if not silent:
                    messagebox.showwarning(APP_TITLE, f"Impossible de vérifier les mises à jour.\n\n{rel}")
                return
            if maj.is_newer(rel["version"], core.VERSION):
                self.update_release = rel
                self.btn_update.configure(text=f"⬆ Installer la version {rel['version']}")
                self.btn_update.pack(side="right", padx=(0, 8))
                if not self.busy:   # au démarrage aussi : on propose tout de suite de l'installer
                    self.install_update()
            elif not silent:
                messagebox.showinfo(APP_TITLE, f"Vous avez la dernière version ({core.VERSION}).")
        elif kind == "maj_progress":
            if args[0] is not None:
                self.progress["value"] = args[0] * 1000
        elif kind == "maj_ready":
            try:
                maj.install_and_restart(*args)
            except Exception as e:
                self.busy = False
                self._update_buttons()
                messagebox.showerror(APP_TITLE, f"La mise à jour n'a pas pu être installée.\n\n{e}")
                return
            self.destroy()
        elif kind == "maj_error":
            self.busy = False
            self._update_buttons()
            self._set_activity("error")
            self.lbl_status.configure(text="Mise à jour impossible.")
            messagebox.showerror(APP_TITLE, "La mise à jour a échoué. Le programme actuel reste "
                                 f"utilisable.\n\n{args[0]}")

    def install_update(self):
        rel = self.update_release
        if not rel:
            return
        if self.busy:
            messagebox.showinfo(APP_TITLE, "Une opération est en cours. Installez la mise à jour quand elle "
                                "sera terminée (ou après l'avoir mise en pause).")
            return
        ok, why = maj.can_self_update()
        notes = rel["notes"].strip()
        notes = ("\n\nNouveautés :\n" + notes[:1200]) if notes else ""
        if not ok:
            if messagebox.askyesno(APP_TITLE, f"La version {rel['version']} est disponible (vous avez la "
                                   f"{core.VERSION}).{notes}\n\nInstallation automatique impossible : {why}.\n\n"
                                   "Ouvrir la page de téléchargement ?"):
                webbrowser.open(rel["page"])
            return
        if not messagebox.askyesno(APP_TITLE, f"Installer la version {rel['version']} ? (vous avez la "
                                   f"{core.VERSION}){notes}\n\nLe programme va se fermer, se mettre à jour "
                                   "puis se rouvrir tout seul. L'archive et les réglages ne sont pas touchés."):
            return
        self.busy = True
        self._update_buttons()
        self._set_activity("busy")
        self.lbl_status.configure(text=f"Téléchargement de la version {rel['version']}…")
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0

        def worker():
            try:
                stage, new_dir = maj.download(rel, lambda f: self.q.put(("maj_progress", f)))
                self.q.put(("maj_ready", stage, new_dir))
            except Exception as e:
                self.q.put(("maj_error", e))
        threading.Thread(target=worker, daemon=True).start()

    def show_help(self):
        P = theme.px
        w = tk.Toplevel(self)
        w.title("Mode d'emploi")
        w.configure(background=theme.BG)
        w.geometry(f"{P(860)}x{P(720)}")
        card = ttk.Frame(w, style="Card.TFrame", padding=P(6))
        card.pack(fill="both", expand=True, padx=P(16), pady=P(16))
        t = tk.Text(card, wrap="word", font="AFBody", padx=P(22), pady=P(16), relief="flat", borderwidth=0,
                    highlightthickness=0, background=theme.CARD, foreground=theme.TEXT, spacing1=P(2), spacing3=P(2))
        sb = ttk.Scrollbar(card, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        t.tag_configure("h", font="AFSubtitle", foreground=theme.ACCENT, spacing1=P(14), spacing3=P(4))
        t.tag_configure("step", font="AFStrong")
        for line in HELP_TEXT.splitlines(keepends=True):
            plain = line.strip()
            if plain and plain == plain.upper() and any(c.isalpha() for c in plain):
                t.insert("end", plain.capitalize() + "\n", "h")   # titres en capitales : plus doux à lire
            elif re.match(r"^\d\. ", plain):
                t.insert("end", line, "step")
            else:
                t.insert("end", line)
        t.configure(state="disabled")


def main():
    if core.IS_WINDOWS:
        try:
            core.ctypes.windll.shcore.SetProcessDpiAwareness(1)   # texte net sur écrans haute résolution
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

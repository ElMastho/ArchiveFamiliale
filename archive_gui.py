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
import os
import queue
import re
import sqlite3
import string
import sys
import threading
import traceback
import unicodedata
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import archive as core
import classement
import maj

APP_TITLE = "Archive Familiale"
ARCHIVE_FOLDER = core.ARCHIVE_FOLDER
RECOMMENDED_BACKUPS = 2
LOW_SPACE = 50 * 1024 ** 3     # en dessous : conseiller d'ajouter un disque

COLOR_DONE = "#1a7f37"
COLOR_WARN = "#b35900"
COLOR_TODO = "#777777"

HELP_TEXT = """\
À QUOI SERT CE PROGRAMME ?
Rassembler les photos, vidéos et documents éparpillés sur de nombreux disques durs,
en ne gardant qu'UN exemplaire de chaque fichier, puis en faire des copies de sauvegarde.
Les anciens disques ne sont JAMAIS modifiés : le programme ne fait que les lire.

L'archive peut occuper PLUSIEURS disques (ARCHIVE-1, ARCHIVE-2, …) : quand l'un est plein,
le programme continue sur le suivant. Collez une étiquette avec son nom sur chaque disque.
ARCHIVE-1 est le disque principal : il contient le catalogue et doit être branché à chaque fois.

LA PROCÉDURE, ÉTAPE PAR ÉTAPE

1. Disques de l'archive
   Branchez un disque NEUF (vide) et cliquez sur « Créer l'archive… » : il devient ARCHIVE-1.
   S'il n'est pas assez grand, branchez un autre disque neuf et cliquez sur
   « Ajouter un disque à l'archive… » : il devient ARCHIVE-2, et ainsi de suite.
   Le plus simple : laisser tous les disques de l'archive branchés pendant les imports
   (un hub USB alimenté aide beaucoup).

2. Importer les anciens disques — un par un
   • Branchez UN ancien disque.
   • Cliquez sur « Importer un disque… », choisissez-le dans la liste, donnez-lui une
     description (ex. : « disque noir du bureau »), puis « OK ».
   • Attendez la fin (cela peut durer plusieurs heures pour un gros disque).
     Vous pouvez cliquer sur « Arrêter » : la prochaine fois, ça reprendra où ça en était.
   • Si le programme dit que les disques de l'archive sont pleins : ajoutez un disque
     (étape 1) puis relancez l'import, il reprendra où il en était.
   • Éjectez le disque proprement (icône USB en bas à droite de Windows), débranchez-le,
     puis passez au suivant.

3. Vérifier l'archive
   Quand tous les disques sont importés, branchez tous les disques ARCHIVE-… et cliquez
   sur « Vérifier maintenant ». Le programme relit tout et s'assure que rien n'est abîmé.

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

DISQUES INTERNES D'UN PC (TOUR)
• Les disques internes apparaissent dans la liste comme les disques USB : on peut les importer.
• Sur un disque qui contient Windows (C:, ou l'ancien disque d'un autre PC), seuls les fichiers des
  utilisateurs sont analysés : Windows, les programmes et les dossiers AppData sont ignorés.
• Les fichiers OneDrive « en ligne uniquement » sont ignorés (ils ne sont pas sur le disque).
• Si un disque interne porte aussi l'archive (dossier ArchiveFamiliale), ce dossier est ignoré
  lors de l'analyse. Ne formatez alors jamais ce disque.

CONSEILS
• Ordinateur portable : laissez-le branché sur secteur. Le programme empêche la mise en veille.
• Ne débranchez jamais un disque pendant une opération (cliquez d'abord sur « Arrêter »).
• Un disque qui fait des bruits de cliquetis ou qui est très lent est peut-être en train de
  mourir : importez-le en priorité, sans l'allumer inutilement.
• Une fois par an : branchez tout et lancez les vérifications (archive et sauvegardes).
• Le programme est copié sur chaque disque (dossier _catalogue\\outil) : on peut
  toujours le relancer depuis là, même sur un autre ordinateur.
• Branchez les disques sur des ports USB 3 (bleus, ou marqués « SS ») : en USB 2, tout est
  trois fois plus lent. Au début de chaque gros import, le programme mesure la vitesse des
  disques, annonce une durée estimée et prévient si un disque semble branché en USB 2.

MISES À JOUR DU PROGRAMME
• Au démarrage, le programme vérifie s'il existe une nouvelle version. Si oui, un bouton
  « Installer la version … » apparaît en haut : un clic suffit, le programme se ferme, se met
  à jour et se rouvre. L'archive et les réglages ne sont pas touchés.
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


def short_date(iso) -> str:
    return (iso or "")[:16].replace("T", " ")


# --------------------------------------------------------------------------- #
# Fenêtres de dialogue
# --------------------------------------------------------------------------- #

class DriveDialog(tk.Toplevel):
    """mode : 'create' | 'addvol' | 'backup' | 'source' | 'scan' | 'check'"""

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
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=intro, wraplength=760, justify="left").pack(anchor="w")

        cols = ("lecteur", "nom", "taille", "libre", "type", "remarque")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=7, selectmode="browse")
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
        self.chosen = ttk.Label(frm, text="Aucun disque sélectionné.", foreground="#555")
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
                      foreground="#666").grid(row=0, column=2, sticky="w")
            ttk.Label(g, text="Description :").grid(row=1, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=self.var_note, width=60).grid(row=1, column=1, columnspan=2,
                                                                   sticky="w", padx=8)
            ttk.Label(g, text="ex. : disque noir du bureau, étiquette « photos 2005 »",
                      foreground="#666").grid(row=2, column=1, columnspan=2, sticky="w", padx=8)
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


class ChoiceDialog(tk.Toplevel):
    def __init__(self, app, title, text, options):
        super().__init__(app)
        self.result = None
        self.title(title)
        self.transient(app)
        frm = ttk.Frame(self, padding=16)
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
        frm = ttk.Frame(self, padding=16)
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
            ttk.Label(box, text=classement.MODEL_EXAMPLES[key], font=("Consolas", 9), foreground="#444",
                      justify="left").pack(anchor="w", padx=(28, 0))
        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(16, 0))
        ttk.Button(b, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Voir l'aperçu (rien n'est déplacé)", style="Accent.TButton",
                   command=lambda: (setattr(self, "result", self.var.get()), self.destroy())).pack(side="right", padx=8)
        self.wait_visibility()
        self.grab_set()


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
        self.q: queue.Queue = queue.Queue()
        self.action_buttons: list[ttk.Button] = []
        core.Progress.hook = lambda frac, text: self.q.put(("progress", frac, text))

        self._styles()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self.set_master(find_master(self.cfg), save=False)
        self._fit_to_screen()
        self.update_release = None
        if self.cfg.get("verifier_maj", True):
            self.after(2000, lambda: self.check_update(silent=True))

    def _fit_to_screen(self):
        """Taille de fenêtre adaptée à l'écran et à sa mise à l'échelle."""
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        k = float(self.tk.call("tk", "scaling")) / (96 / 72)   # 1.0 à 100 %, 2.0 à 200 %
        w, h = int(1100 * k), max(self.winfo_reqheight(), int(900 * k))
        if w > sw * 0.95 or h > sh * 0.90:
            try:
                self.state("zoomed")   # plein écran sur les petits écrans
                return
            except tk.TclError:
                w, h = int(sw * 0.95), int(sh * 0.88)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max((sh - h) // 3, 0)}")
        self.minsize(min(w, int(900 * k)), min(h, int(700 * k)))

    # ---------- construction ----------
    def _styles(self):
        s = ttk.Style(self)
        base = ("Segoe UI", 10)
        s.configure(".", font=base)
        s.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        s.configure("StepTitle.TLabel", font=("Segoe UI", 12, "bold"))
        s.configure("Glyph.TLabel", font=("Segoe UI Symbol", 22))
        s.configure("Next.TLabel", font=("Segoe UI", 11, "bold"), foreground=COLOR_WARN)
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        s.configure("Treeview", rowheight=24)
        s.configure("StepTitle.TRadiobutton", font=("Segoe UI", 11, "bold"))

    def _tree(self, parent, cols, height):
        t = ttk.Treeview(parent, columns=[c for c, _, _ in cols], show="headings", height=height)
        for c, label, w in cols:
            t.heading(c, text=label)
            t.column(c, width=w, anchor="w")
        t.grid(row=2, column=1, sticky="ew", pady=(4, 2), padx=(0, 8))
        return t

    def _build(self):
        top = ttk.Frame(self, padding=(16, 12, 16, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Archive Familiale", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"version {core.VERSION}", foreground=COLOR_TODO).pack(side="left", padx=(10, 0), pady=(8, 0))
        ttk.Button(top, text="? Aide / mode d'emploi", command=self.show_help).pack(side="right")
        ttk.Button(top, text="Mises à jour…", command=self.check_update).pack(side="right", padx=(0, 8))
        self.btn_update = ttk.Button(top, text="", style="Accent.TButton", command=self.install_update)
        self.lbl_next = ttk.Label(self, text="", style="Next.TLabel", padding=(16, 0, 16, 6))
        self.lbl_next.pack(fill="x")

        body = ttk.Frame(self, padding=(16, 0, 16, 0))
        body.pack(fill="both", expand=True)

        self.steps = {}
        s1 = self._step(body, 1, "Disques de l'archive",
                        [("Créer l'archive…", self.create_archive, True, True),
                         ("Ajouter un disque à l'archive…", self.add_main_disk, True, False),
                         ("Ouvrir une archive existante…", self.open_archive, False, True)])
        self.tree_vol = self._tree(s1, [("disque", "Disque", 130), ("branche", "Branché ?", 170),
                                        ("fichiers", "Fichiers", 90), ("donnees", "Données", 100),
                                        ("libre", "Libre", 100), ("verif", "Vérification (étape 3)", 230)], 3)

        s2 = self._step(body, 2, "Importer les anciens disques, un par un",
                        [("Importer un disque…", lambda: self.add_source(copy=True), True, False),
                         ("Estimer sans copier…", lambda: self.add_source(copy=False), False, False)])
        self.tree_src = self._tree(s2, [("nom", "Nom", 160), ("desc", "Description", 210),
                                        ("fichiers", "Fichiers", 80), ("taille", "Taille", 85),
                                        ("copies", "Nouveaux copiés", 120), ("etat", "Import", 150),
                                        ("controle", "Contrôle (étape 5)", 150)], 4)

        self._step(body, 3, "Vérifier l'archive",
                   [("Vérifier maintenant", self.verify_master, True, False)])

        s4 = self._step(body, 4, f"Jeux de sauvegarde (au moins {RECOMMENDED_BACKUPS}, dont un hors de la maison)",
                        [("Créer un jeu de sauvegarde…", self.create_set, True, False),
                         ("Ajouter un disque à un jeu…", self.add_set_disk, False, False),
                         ("Mettre à jour les sauvegardes", self.update_backups, True, False),
                         ("Vérifier une sauvegarde…", self.verify_backups, False, False),
                         ("Je ne veux pas de sauvegarde…", self.toggle_backups, False, False)])
        self.btn_toggle_backups = self.action_buttons[-1]
        self.tree_set = self._tree(s4, [("jeu", "Jeu", 120), ("disques", "Disques (✓ = branché)", 360),
                                        ("etat", "État", 170), ("maj", "Dernière mise à jour", 140),
                                        ("verif", "Dernière vérification", 150)], 2)

        self._step(body, 5, "Contrôler un ancien disque avant de le ranger",
                   [("Contrôler un ancien disque…", self.check_source, True, False)])
        self._step(body, 6, "Classer l'archive par type et par date (facultatif)",
                   [("Classer l'archive…", self.classify, True, False),
                    ("Annuler le dernier classement", self.undo_classify, False, False)])

        act = ttk.LabelFrame(self, text=" Activité ", padding=10)
        act.pack(fill="both", expand=False, padx=16, pady=(6, 4))
        row = ttk.Frame(act)
        row.pack(fill="x")
        self.progress = ttk.Progressbar(row, mode="determinate", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.btn_stop = ttk.Button(row, text="■ Arrêter", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        self.lbl_status = ttk.Label(act, text="Prêt.", foreground="#333")
        self.lbl_status.pack(anchor="w", pady=(4, 4))
        logf = ttk.Frame(act)
        logf.pack(fill="both", expand=True)
        self.txt = tk.Text(logf, height=7, wrap="word", font=("Consolas", 9), state="disabled",
                           background="#fafafa")
        sb = ttk.Scrollbar(logf, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bottom = ttk.Frame(self, padding=(16, 2, 16, 10))
        bottom.pack(fill="x")
        for text, cmd in (("Rapport détaillé", self.show_report),
                          ("Exporter les listes (Excel)", self.export_csv),
                          ("Ouvrir le dossier de l'archive", self.open_folder),
                          ("Ouvrir le journal", self.open_log)):
            b = ttk.Button(bottom, text=text, command=cmd)
            b.pack(side="left", padx=(0, 8))
            b._needs_master = True
            b._only_without_master = False
            self.action_buttons.append(b)

    def _step(self, parent, n, title, buttons):
        """buttons : (texte, action, principal, sans_archive) ; sans_archive = utilisable sans archive."""
        f = ttk.Frame(parent, padding=(8, 6), relief="groove", borderwidth=1)
        f.pack(fill="x", pady=4)
        f.columnconfigure(1, weight=1)
        glyph = ttk.Label(f, text="○", style="Glyph.TLabel", width=2, anchor="center")
        glyph.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))
        ttk.Label(f, text=f"{n}. {title}", style="StepTitle.TLabel").grid(row=0, column=1, sticky="w")
        status = ttk.Label(f, text="", justify="left")
        status.grid(row=1, column=1, sticky="ew")
        # le texte se replie selon la largeur réellement disponible (écrans 100 % à 200 %)
        status.bind("<Configure>", lambda e, lb=status: lb.configure(wraplength=max(e.width - 4, 200)))
        bf = ttk.Frame(f)
        bf.grid(row=0, column=2, rowspan=3, sticky="ne")
        for text, cmd, primary, without in buttons:
            b = ttk.Button(bf, text=text, command=cmd, style="Accent.TButton" if primary else "TButton")
            b.pack(side="top", fill="x", pady=1)
            b._needs_master = not without
            b._only_without_master = (cmd == self.create_archive)
            self.action_buttons.append(b)
        self.steps[n] = {"frame": f, "glyph": glyph, "status": status}
        return f

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

    def _set_step(self, n, kind, text):
        glyph, color = {"done": ("✔", COLOR_DONE), "warn": ("●", COLOR_WARN),
                        "todo": ("○", COLOR_TODO), "off": ("—", COLOR_TODO)}[kind]
        s = self.steps[n]
        s["glyph"].configure(text=glyph, foreground=color)
        s["status"].configure(text=text)

    def _update_steps(self):
        st = self.st
        for t in (self.tree_vol, self.tree_src, self.tree_set):
            t.delete(*t.get_children())
        if not st:
            self._set_step(1, "warn", "Aucune archive ouverte. Branchez un disque neuf puis cliquez sur « Créer "
                                      "l'archive… » (ou « Ouvrir… » si elle existe déjà).")
            for n in (2, 3, 4, 5):
                self._set_step(n, "todo", "Disponible une fois l'archive créée (étape 1).")
            self.lbl_next.configure(text="➜ À faire maintenant : étape 1, créer ou ouvrir l'archive.")
            self.title(APP_TITLE)
            return
        self.title(f"{APP_TITLE} — {self.master_path}")
        last_change = st["last_change"] or ""

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
            self.tree_vol.insert("", "end", values=(
                v["name"], where, core.fmt_int(v["files"]), core.fmt_size(v["bytes"]),
                core.fmt_size(v["free"]) if plugged else "?", ver))
        unplugged = [v["name"] for v in st["main_vols"] if not v["path"]]
        txt = (f"{len(st['main_vols'])} disque(s) — {core.fmt_int(st['stored_n'])} fichiers, "
               f"{core.fmt_size(st['stored_b'])} — place libre sur les disques branchés : {core.fmt_size(free_plugged)}")
        if unplugged:
            txt += f". Non branché(s) : {', '.join(unplugged)}."
        low = free_plugged < LOW_SPACE
        if low:
            txt += "  ⚠ Peu de place : ajoutez un disque à l'archive avant le prochain import."
        self._set_step(1, "warn" if low else "done", txt)

        # Étape 2 : sources
        srcs = st["sources"]
        pending = [s for s in srcs if not s["completed"]]
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
            self.tree_src.insert("", "end", values=(
                s["label"], s["note"] or "", core.fmt_int(s["n"]), core.fmt_size(s["sz"]),
                f"{core.fmt_int(s['nc'])} ({core.fmt_size(s['szc'])})", etat, ctrl))
        if not srcs:
            self._set_step(2, "todo", "Aucun disque importé pour l'instant. Branchez un ancien disque puis "
                                      "cliquez sur « Importer un disque… ».")
        elif pending:
            self._set_step(2, "warn", f"{len(srcs)} disque(s) connu(s), dont {len(pending)} à importer ou à "
                                      f"reprendre (rebranchez-le et relancez « Importer un disque… »).")
        else:
            self._set_step(2, "done", f"{len(srcs)} disque(s) importé(s). Branchez le suivant, ou passez à "
                                      f"l'étape 3 quand TOUS les anciens disques sont faits.")

        # Étape 3 : vérification, disque par disque
        to_verify = [v for v in st["main_vols"] if v["files"] and not (
            v["last_verify"] and v["last_verify_status"] == "ok" and v["last_verify"] >= (v["last_added"] or ""))]
        if not st["stored_n"]:
            self._set_step(3, "todo", "Rien à vérifier pour l'instant.")
        elif not to_verify:
            self._set_step(3, "done", "Tous les disques de l'archive ont été vérifiés : tout est intact.")
        else:
            names = ", ".join(v["name"] + ("" if v["path"] else " (non branché)") for v in to_verify)
            self._set_step(3, "warn" if any(v["last_verify"] for v in st["main_vols"]) else "todo",
                           f"À vérifier : {names}. Branchez ces disques puis « Vérifier maintenant » "
                           f"(relit tout : compter plusieurs heures).")

        # Étape 4 : jeux de sauvegarde
        n_ok = 0
        for s in st["sets"]:
            up = s["backlog_n"] == 0 and st["stored_n"] > 0
            n_ok += up
            disks = "  ".join(("✓ " if v["path"] else "✗ ") + v["name"] for v in s["vols"]) or "(aucun disque)"
            etat = "✔ À jour" if up else f"● {core.fmt_int(s['backlog_n'])} fichiers à copier ({core.fmt_size(s['backlog_b'])})"
            ver = short_date(s["last_verify"]) + (f" ({s['last_verify_status']})" if s["last_verify_status"] else "") \
                if s["last_verify"] else "jamais"
            self.tree_set.insert("", "end", values=(s["name"], disks, etat, short_date(s["last_sync"]) or "jamais", ver))
        no_backup = st["meta"].get("backup_policy") == "aucune" and not st["sets"]
        self.btn_toggle_backups.configure(text="Réactiver les sauvegardes" if no_backup
                                          else "Je ne veux pas de sauvegarde…")
        if no_backup:
            self._set_step(4, "off", "Pas de sauvegarde : c'est votre choix. ⚠ L'archive est alors la SEULE copie : "
                                     "si un de ses disques tombe en panne, son contenu est perdu. Vous pouvez "
                                     "changer d'avis à tout moment (« Créer un jeu de sauvegarde… »).")
        elif n_ok >= RECOMMENDED_BACKUPS:
            self._set_step(4, "done", f"{n_ok} jeux de sauvegarde à jour. Rangez-en un hors de la maison.")
        elif st["sets"]:
            self._set_step(4, "warn", f"{n_ok} jeu(x) à jour sur {RECOMMENDED_BACKUPS} recommandés. Branchez les disques "
                                      f"d'un jeu et cliquez « Mettre à jour les sauvegardes », ou créez un autre jeu.")
        else:
            self._set_step(4, "todo", "Aucune sauvegarde. Branchez un disque neuf et cliquez « Créer un jeu de "
                                      f"sauvegarde… » ({RECOMMENDED_BACKUPS} jeux conseillés).")

        # Étape 5 : contrôle des anciens disques
        checked = [s for s in srcs if s["last_check_status"] and s["last_check_status"].startswith("ok")
                   and s["last_check"] >= (s["last_seen"] or "")]
        if srcs and len(checked) == len(srcs):
            self._set_step(5, "done", f"Les {len(srcs)} anciens disques ont été contrôlés : leur contenu est "
                                      f"dans l'archive.")
        elif srcs:
            self._set_step(5, "warn" if checked else "todo",
                           f"{len(checked)}/{len(srcs)} anciens disques contrôlés. Ne vous séparez d'un ancien "
                           + ("disque qu'après contrôle. Sans sauvegarde, garder les anciens disques reste votre "
                              "seule copie de secours." if no_backup else
                              "disque qu'après contrôle ET sauvegardes à jour."))
        else:
            self._set_step(5, "todo", "Rien à contrôler pour l'instant.")

        # Étape 6 : classement
        cm = st["meta"].get("classification_model")
        if not st["stored_n"]:
            self._set_step(6, "todo", "Disponible une fois des fichiers importés.")
        elif not cm:
            self._set_step(6, "off", "Non classée : les fichiers sont rangés par ancien disque. Quand tous les disques "
                                     "sont importés, vous pouvez tout classer par type et par date (aperçu avant de "
                                     "valider, annulable).")
        elif st["unclassified"]:
            self._set_step(6, "warn", f"Classée selon le modèle {cm} ({classement.MODELS.get(cm, '')}) le "
                                      f"{short_date(st['meta'].get('classification_at'))}. "
                                      f"{core.fmt_int(st['unclassified'])} fichiers importés depuis sont à classer : "
                                      f"relancez « Classer l'archive… ».")
        else:
            self._set_step(6, "done", f"Classée selon le modèle {cm} ({classement.MODELS.get(cm, '')}) le "
                                      f"{short_date(st['meta'].get('classification_at'))}.")

        # Prochaine étape conseillée
        if low:
            nxt = "étape 1, ajouter un disque à l'archive (il reste peu de place)."
        elif not srcs or pending:
            nxt = "étape 2, importer les anciens disques."
        elif to_verify:
            nxt = "étape 3, vérifier l'archive (si tous les anciens disques sont importés)."
        elif n_ok < RECOMMENDED_BACKUPS and not no_backup:
            nxt = "étape 4, créer / mettre à jour les jeux de sauvegarde (ou choisir « pas de sauvegarde »)."
        elif len(checked) < len(srcs):
            nxt = "étape 5, contrôler les anciens disques."
        else:
            nxt = None
        self.lbl_next.configure(text=f"➜ À faire maintenant : {nxt}" if nxt else
                                ("✔ Tout est en ordre (sans sauvegarde, par choix). Pensez à vérifier l'archive "
                                 "une fois par an." if no_backup else
                                 "✔ Tout est en ordre. Pensez à vérifier l'archive et les sauvegardes une fois par an.")
                                + ("  Facultatif : étape 6, classer l'archive." if not nxt and not cm else ""))

    def _update_buttons(self):
        for b in self.action_buttons:
            enabled = not self.busy and (self.master_path or not b._needs_master)
            if b._only_without_master and self.master_path:
                enabled = False
            b.configure(state="normal" if enabled else "disabled")
        self.btn_stop.configure(state="normal" if self.busy else "disabled")

    # ---------- exécution des tâches en arrière-plan ----------
    def log(self, text):
        self.txt.configure(state="normal")
        self.txt.insert("end", text)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def run_jobs(self, jobs, on_all_done=None):
        """jobs : liste de (titre, argv). Exécutées l'une après l'autre dans un thread."""
        if self.busy:
            return
        self.busy = True
        self.usb2_warned = False
        core.CANCEL.clear()
        self._update_buttons()

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
            self.q.put(("done", results, on_all_done))

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
                    _, frac, text = msg
                    if frac is None:
                        if str(self.progress["mode"]) != "indeterminate":
                            self.progress.configure(mode="indeterminate")
                            self.progress.start(15)
                    else:
                        if str(self.progress["mode"]) != "determinate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate")
                        self.progress["value"] = frac * 1000
                    self.lbl_status.configure(text=text)
                elif kind == "start":
                    self.log(f"\n━━━ {msg[1]} ━━━\n")
                    self.lbl_status.configure(text=msg[1] + "…")
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress["value"] = 0
                elif kind == "done":
                    self._job_done(msg[1], msg[2])
                elif kind.startswith("maj_"):
                    self._on_update_msg(kind, msg[1:])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _job_done(self, results, on_all_done):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if self.closing:
            self.destroy()
            return
        self.refresh()
        worst = max((rc for _, rc, _ in results), default=0)
        last_title = results[-1][0] if results else ""
        if worst == 0:
            self.progress["value"] = 1000
            self.lbl_status.configure(text="Terminé ✔")
            if on_all_done:
                on_all_done(results)
        elif worst == 130:
            self.lbl_status.configure(text="Arrêté.")
            messagebox.showinfo(APP_TITLE, "Opération arrêtée.\n\nRien n'est perdu : relancez la même "
                                "action plus tard, elle reprendra là où elle s'était arrêtée.")
        elif worst == 1:
            self.lbl_status.configure(text="Terminé avec des problèmes — voir le détail ci-dessous.")
            messagebox.showwarning(APP_TITLE, f"« {last_title} » s'est terminé, mais avec des problèmes.\n\n"
                                   "Le détail est affiché dans la zone « Activité ». Relancer l'opération "
                                   "règle souvent le souci ; sinon, le disque est peut-être abîmé.")
        elif worst == 3:
            self.lbl_status.configure(text="Arrêté : plus de place.")
            messagebox.showwarning(APP_TITLE, "Les disques de l'archive branchés sont PLEINS.\n\n"
                                   "• Branchez un disque de l'archive qui a encore de la place, ou\n"
                                   "• ajoutez un nouveau disque (étape 1 → « Ajouter un disque à l'archive… »).\n\n"
                                   "Puis relancez l'import : il reprendra là où il s'est arrêté.")
        else:
            err = next((e for _, rc, e in results if e), None)
            self.lbl_status.configure(text="Erreur.")
            messagebox.showerror(APP_TITLE, (err or "Une erreur est survenue. Voir la zone « Activité ».")[:1500])

    def stop(self):
        if self.busy and messagebox.askyesno(APP_TITLE, "Arrêter l'opération en cours ?\n\n"
                                             "Vous pourrez la reprendre plus tard sans rien perdre."):
            core.CANCEL.set()
            self.lbl_status.configure(text="Arrêt en cours…")

    def _on_close(self):
        if not self.busy:
            self.destroy()
            return
        if messagebox.askyesno(APP_TITLE, "Une opération est en cours. L'arrêter et quitter ?\n\n"
                               "Elle pourra être reprise plus tard."):
            self.closing = True
            core.CANCEL.set()

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
                                                     "Étape suivante : branchez un ancien disque et cliquez "
                                                     "sur « Importer un disque… ».")))

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
        self.run_jobs([("Ajout d'un disque à l'archive", ["ajouter-disque", path, *self._m(), *extra])],
                      lambda _: messagebox.showinfo(APP_TITLE, f"Disque ajouté : il s'appelle « ARCHIVE-{n} ».\n\n"
                                                    f"Collez-lui une étiquette « ARCHIVE-{n} »."))

    # ---------- actions : sources ----------
    def add_source(self, copy: bool):
        intro = ("Branchez UN ancien disque, attendez qu'il apparaisse, puis sélectionnez-le "
                 "(cliquez sur « Actualiser la liste » s'il n'apparaît pas).\n"
                 "Le disque sera seulement LU : rien n'y est modifié ni effacé.")
        if copy:
            unplugged = [v["name"] for v in self.st["main_vols"] if not v["path"]]
            if unplugged:
                intro += (f"\n\nRemarque : {', '.join(unplugged)} n'est pas branché. Ce n'est pas grave tant que "
                          "les disques branchés ont de la place.")
        else:
            intro += ("\n\nMode estimation : le programme calcule ce que contient le disque et ce qui serait "
                      "nouveau, sans rien copier. Utile pour savoir combien de disques prévoir.")
        dlg = DriveDialog(self, "source" if copy else "scan",
                          "Importer un disque" if copy else "Estimer un disque", intro)
        self.wait_window(dlg)
        r = dlg.result
        if not r:
            return
        argv = ["importer" if copy else "scanner", r["path"], *self._m(), "-l", r["label"]]
        if r["note"]:
            argv += ["--note", r["note"]]

        def done(_):
            msg = (f"Le disque « {r['label']} » a été entièrement importé.\n\n"
                   "Vous pouvez l'éjecter (icône USB de Windows) et brancher le suivant.") if copy else \
                  (f"Estimation de « {r['label']} » terminée. Voir « Rapport détaillé » pour le total.")
            messagebox.showinfo(APP_TITLE, msg)

        self.run_jobs([(f"{'Import' if copy else 'Estimation'} de « {r['label']} »", argv)], done)

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
                if not silent:
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
            self.lbl_status.configure(text="Mise à jour impossible.")
            messagebox.showerror(APP_TITLE, "La mise à jour a échoué. Le programme actuel reste "
                                 f"utilisable.\n\n{args[0]}")

    def install_update(self):
        rel = self.update_release
        if not rel:
            return
        if self.busy:
            messagebox.showinfo(APP_TITLE, "Une opération est en cours. Installez la mise à jour quand elle "
                                "sera terminée (ou après l'avoir arrêtée).")
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
        w = tk.Toplevel(self)
        w.title("Mode d'emploi")
        w.geometry("860x720")
        t = tk.Text(w, wrap="word", font=("Segoe UI", 10), padx=16, pady=12)
        sb = ttk.Scrollbar(w, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        t.insert("1.0", HELP_TEXT)
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

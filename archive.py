#!/usr/bin/env python3
"""
archive.py - Consolidation et déduplication d'archives familiales, sur plusieurs disques.

Principe
--------
On branche les disques sources un par un. Pour chaque fichier, on calcule une
empreinte (hash BLAKE2b-256) de son contenu. Un catalogue SQLite garde la mémoire
de tout ce qui a déjà été vu :

  * contenu jamais vu  -> copié sur un disque de l'archive, sous <label>/<chemin d'origine>
  * contenu déjà connu -> rien n'est copié, on note seulement l'emplacement d'origine

L'archive peut s'étendre sur plusieurs disques (ARCHIVE-1, ARCHIVE-2, …) remplis dans
l'ordre. ARCHIVE-1 contient le catalogue ; chaque disque est un dossier normal, lisible
seul, identifié par un fichier _catalogue/volume.json (la lettre de lecteur peut changer).

Les sauvegardes sont des « jeux » de disques (ex. Sauvegarde-A-1, Sauvegarde-A-2) avec
leur propre répartition ; le catalogue sait où se trouve chaque copie.

Les disques sources ne sont JAMAIS modifiés (lecture seule).
Bibliothèque standard de Python uniquement (3.10+). Voir README.md.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import ctypes
import datetime as dt
import fnmatch
import hashlib
import json
import logging
import os
import queue
import re
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

VERSION = "2.5.1"

ARCHIVE_FOLDER = "ArchiveFamiliale"          # nom de dossier conseillé sur chaque disque
CATALOG_DIR = "_catalogue"
DB_NAME = "catalogue.sqlite"                 # catalogue de référence (sur ARCHIVE-1)
CATALOG_COPY_NAME = "catalogue-copie.sqlite"  # copie de secours (sur les autres disques)
MARKER_NAME = "volume.json"                  # identité du disque
MAIN_SET = "main"                            # identifiant de l'ensemble des disques d'archive
HASH_ALGO = "blake2b-256"
CHUNK = 4 * 1024 * 1024                      # taille des blocs de lecture
SMALL_FILE = 64 * 1024 * 1024                # lu en une fois en mémoire (évite une seconde lecture)
SLOW_DISK = 45 * 1024 ** 2                  # en dessous : sans doute branché en USB 2
REVERIFY_DAYS = 365                          # une copie relue sans défaut n'est relue qu'un an plus tard
SPEED_TEST_MIN = 1024 ** 3                   # mesure de vitesse seulement pour les imports d'au moins 1 Go
WRITE_QUEUE_CHUNKS = 32                      # au plus 128 Mo en attente d'écriture (< marge d'espace libre)
FREE_SPACE_MARGIN = 2 * 1024 ** 3            # toujours 2 Go libres sur chaque disque
PRIMARY_EXTRA_MARGIN = 8 * 1024 ** 3         # + 8 Go sur ARCHIVE-1 pour le catalogue
COMMIT_EVERY_FILES = 500
COMMIT_EVERY_SECONDS = 5.0
SNAPSHOTS_KEPT = 5
IS_WINDOWS = os.name == "nt"

# Dossiers système ignorés (comparaison en minuscules)
EXCLUDED_DIRS = {
    "system volume information", ".spotlight-v100", ".fseventsd", ".temporaryitems",
    ".documentrevisions-v100", ".mobilebackups", "$windows.~bt", "$windows.~ws",
    "$sysreset", "config.msi", "msocache",
}
# Corbeilles : ignorées par défaut, incluses avec --inclure-corbeille
TRASH_DIRS = {"$recycle.bin", "recycler", "recycled", ".trashes", ".trash"}
# Fichiers parasites ignorés
EXCLUDED_FILES = {
    "thumbs.db", "ehthumbs.db", "ehthumbs_vista.db", "desktop.ini", ".ds_store",
    "pagefile.sys", "hiberfil.sys", "swapfile.sys", "iconcache.db", ".localized",
}
EXCLUDED_FILE_PATTERNS = ["._*", "~$*", "ntuser.*", "usrclass.dat*"]   # AppleDouble, verrous Office, profils
# Disque contenant une installation Windows (disque système, ou ancien disque de PC) :
# on ignore le système et les programmes, on garde les fichiers des utilisateurs.
WIN_SYSTEM_TOP = {
    "windows", "program files", "program files (x86)", "programdata", "recovery", "perflogs",
    "$winreagent", "$getcurrent", "$windows.~bt", "$windows.~ws", "$sysreset", "onedrivetemp",
    "intel", "amd", "nvidia", "drivers", "system.sav", "esd", "swsetup", "boot",
}
# Sur un disque Windows, seuls les profils (Users\…) sont lus : les autres dossiers de la racine sont
# presque toujours des programmes ou des jeux. Ils sont listés à l'utilisateur, qui peut les ajouter.
SKIP_OUTSIDE_USERS = "hors des dossiers des utilisateurs (disque Windows)"
WIN_SKIP_PROFILES = {"default", "default user", "all users", "defaultapppool"}
WIN_USER_SKIP = {"appdata", "application data", "local settings", "cookies", "nethood", "printhood",
                 "recent", "sendto", "start menu", "templates", "intelgraphicsprofiles", ".cache"}
# Disque macOS (lu avec un pilote HFS+/APFS)
MAC_SYSTEM_TOP = {"system", "library", "applications", "private", "usr", "bin", "sbin", "cores", "opt",
                  "var", "etc", "tmp", "dev", "volumes", "network", ".vol"}
MAC_USER_SKIP = {"library", ".trash", ".cache"}
# Attributs Windows des fichiers « en ligne uniquement » (les lire déclencherait un téléchargement)
CLOUD_ATTRS = 0x00001000 | 0x00040000 | 0x00400000   # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS
# Dossiers-paquets conservés ENTIERS (pas de déduplication à l'intérieur) :
# bibliothèques Photos/iPhoto/Aperture/Lightroom/iMovie, structures DVD/caméscope.
KEEP_WHOLE_PATTERNS = [
    "*.photoslibrary", "*.photolibrary", "*.migratedphotolibrary", "*.aplibrary",
    "*.lrdata", "*.lrlibrary", "*.imovielibrary", "*.fcpbundle", "*.theater",
    "*.dvdmedia", "video_ts", "audio_ts", "bdmv", "avchd", "private",
]

LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,59}$")
WIN_INVALID_CHARS = set('<>:"|?*\\/')
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sources(
    label         TEXT PRIMARY KEY,
    note          TEXT,
    root          TEXT,
    volume_name   TEXT,
    volume_serial TEXT,
    filesystem    TEXT,
    first_seen    TEXT,
    last_seen     TEXT,
    last_mode     TEXT,
    completed     INTEGER NOT NULL DEFAULT 0,
    last_check        TEXT,
    last_check_status TEXT
);
-- Disques de l'archive (set_id = 'main') et des jeux de sauvegarde (set_id = id du jeu)
CREATE TABLE IF NOT EXISTS volumes(
    id                 TEXT PRIMARY KEY,
    set_id             TEXT NOT NULL,
    number             INTEGER NOT NULL,
    name               TEXT NOT NULL UNIQUE COLLATE NOCASE,
    root               TEXT,      -- dernier emplacement connu (la lettre peut changer)
    subpath            TEXT,      -- emplacement sans la lettre de lecteur
    volume_serial      TEXT,
    volume_name        TEXT,
    capacity           INTEGER,
    added_at           TEXT,
    last_seen          TEXT,
    last_verify        TEXT,
    last_verify_status TEXT
);
CREATE TABLE IF NOT EXISTS backup_sets(
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at         TEXT,
    last_sync          TEXT,
    last_sync_status   TEXT,
    last_verify        TEXT,
    last_verify_status TEXT
);
-- Fichiers présents dans l'archive (chemin relatif unique, séparateur /) et leur disque
CREATE TABLE IF NOT EXISTS stored(
    path          TEXT PRIMARY KEY COLLATE NOCASE,
    hash          TEXT NOT NULL,
    size          INTEGER NOT NULL,
    origin_label  TEXT,
    added_at      TEXT,
    verified_at   TEXT,
    verify_status TEXT
);
CREATE INDEX IF NOT EXISTS stored_hash ON stored(hash);
CREATE INDEX IF NOT EXISTS stored_size ON stored(size);
-- Copies des fichiers dans chaque jeu de sauvegarde (même chemin relatif)
CREATE TABLE IF NOT EXISTS backup_copies(
    set_id        TEXT NOT NULL,
    path          TEXT NOT NULL COLLATE NOCASE,
    volume        TEXT NOT NULL,
    size          INTEGER,
    copied_at     TEXT,
    verified_at   TEXT,
    verify_status TEXT,
    PRIMARY KEY(set_id, path)
);
CREATE INDEX IF NOT EXISTS bc_volume ON backup_copies(volume);
-- Chaque fichier vu sur chaque disque source
CREATE TABLE IF NOT EXISTS occurrences(
    label       TEXT NOT NULL,
    relpath     TEXT NOT NULL,
    size        INTEGER NOT NULL,
    mtime_ns    INTEGER,
    ctime_ns    INTEGER,
    hash        TEXT,
    status      TEXT NOT NULL,      -- scanned | copied | duplicate | error
    stored_path TEXT,
    keep_whole  INTEGER NOT NULL DEFAULT 0,
    seen_at     TEXT,
    error       TEXT,
    PRIMARY KEY(label, relpath)
);
CREATE INDEX IF NOT EXISTS occ_hash ON occurrences(hash);
-- Classement : dates lues dans le contenu des fichiers (cache par empreinte)
CREATE TABLE IF NOT EXISTS media_dates(
    hash         TEXT PRIMARY KEY,
    y            INTEGER,
    m            INTEGER,
    d            INTEGER,
    source       TEXT,
    extracted_at TEXT
);
-- Classement : chaque classement (ou annulation) et ses déplacements, pour pouvoir annuler
CREATE TABLE IF NOT EXISTS classifications(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model       TEXT,
    kind        TEXT,      -- classement | annulation
    created_at  TEXT,
    finished_at TEXT,
    status      TEXT,
    moved       INTEGER,
    undo_of     INTEGER,
    undone_at   TEXT
);
CREATE TABLE IF NOT EXISTS moves(
    batch    INTEGER NOT NULL,
    seq      INTEGER NOT NULL,
    volume   TEXT,
    old_path TEXT,
    new_path TEXT,
    status   TEXT,         -- pending | done | skipped
    PRIMARY KEY(batch, seq)
);
-- Éléments ignorés ou illisibles lors du dernier parcours d'une source
CREATE TABLE IF NOT EXISTS skipped(
    label   TEXT NOT NULL,
    relpath TEXT NOT NULL,
    reason  TEXT NOT NULL,
    PRIMARY KEY(label, relpath)
);
"""

log = logging.getLogger("archive")

# Demande d'arrêt (bouton « Arrêter » de l'interface graphique). Testée régulièrement
# pendant les longues opérations, qui s'arrêtent alors proprement comme sur un Ctrl+C.
CANCEL = threading.Event()


def check_cancel():
    if CANCEL.is_set():
        raise KeyboardInterrupt


def _isatty(stream) -> bool:
    try:
        return stream is not None and stream.isatty()
    except (AttributeError, ValueError):
        return False


class UserError(Exception):
    """Erreur à afficher telle quelle à l'utilisateur (sans trace Python)."""


class FatalCopyError(Exception):
    """Erreur qui doit arrêter tout le traitement (ex : plus de place sur les disques)."""


# --------------------------------------------------------------------------- #
# Utilitaires d'affichage
# --------------------------------------------------------------------------- #

def fmt_int(n) -> str:
    return f"{int(n or 0):,}".replace(",", "\u202f")


def fmt_size(n) -> str:
    n = float(n or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.2f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n:.2f} Po".replace(".", ",")


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def ns_to_iso(ns) -> str:
    if ns is None:
        return ""
    try:
        return dt.datetime.fromtimestamp(ns / 1e9).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return ""


class Progress:
    """Ligne de progression : pourcentage, débit, temps restant estimé."""

    # Si défini (interface graphique) : hook(fraction 0..1 ou None, texte) remplace la console.
    hook = None

    def __init__(self, total_files: int, total_bytes: int):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.files = 0
        self.done_bytes = 0
        self.cur = 0
        self.read_bytes = 0
        self.t0 = time.monotonic()
        self.last = 0.0
        self.tty = _isatty(sys.stderr)
        self.interval = 0.2 if Progress.hook else (0.5 if self.tty else 30.0)

    def add(self, n: int):
        check_cancel()
        self.read_bytes += n
        self.cur += n
        self._tick()

    def file_done(self, size: int):
        check_cancel()
        self.files += 1
        self.done_bytes += size
        self.cur = 0
        self._tick()

    def _tick(self, force=False):
        now = time.monotonic()
        if not force and now - self.last < self.interval:
            return
        self.last = now
        elapsed = max(now - self.t0, 1e-6)
        done = min(self.done_bytes + self.cur, self.total_bytes)
        pct = 100.0 * done / self.total_bytes if self.total_bytes else 100.0
        eta = (self.total_bytes - done) * elapsed / done if done > 0 else None
        line = (f"  {pct:5.1f} %  {fmt_int(self.files)}/{fmt_int(self.total_files)} fichiers"
                f"  {fmt_size(done)}/{fmt_size(self.total_bytes)}"
                f"  lecture {fmt_size(self.read_bytes / elapsed)}/s  reste ~{fmt_duration(eta)}")
        if Progress.hook:
            Progress.hook(pct / 100.0, line.strip())
            return
        if self.tty:
            sys.stderr.write("\r" + line.ljust(110)[:150])
        elif sys.stderr is not None:
            sys.stderr.write(line + "\n")
        if sys.stderr is not None:
            sys.stderr.flush()

    def finish(self):
        self._tick(force=True)
        if self.tty and not Progress.hook:
            sys.stderr.write("\n")
        return time.monotonic() - self.t0


# --------------------------------------------------------------------------- #
# Chemins, disques et système de fichiers
# --------------------------------------------------------------------------- #

def lp(path: str) -> str:
    """Chemin « long » Windows (\\\\?\\) pour dépasser la limite des 260 caractères."""
    if not IS_WINDOWS:
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def normalize_dir(p: str) -> str:
    p = os.path.expanduser(p.strip().strip('"'))
    if IS_WINDOWS and len(p) == 2 and p[1] == ":":
        p += "\\"
    return os.path.abspath(p)


def to_os(rel: str) -> str:
    return rel.replace("/", os.sep)


def is_inside(child: str, parent: str) -> bool:
    c = os.path.normcase(os.path.abspath(child))
    p = os.path.normcase(os.path.abspath(parent))
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def same_path(a: str, b: str) -> bool:
    return bool(a) and bool(b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def sanitize_component(name: str, max_len: int = 200) -> str:
    """Rend un nom de fichier/dossier valide sous Windows (NTFS/exFAT)."""
    out = "".join("_" if (c in WIN_INVALID_CHARS or ord(c) < 32) else c for c in name)
    out = out.rstrip(" .") or "_"
    if out.split(".")[0].upper() in WIN_RESERVED:
        out = "_" + out
    if len(out) > max_len:
        stem, ext = os.path.splitext(out)
        ext = ext[:20]
        out = stem[: max_len - len(ext)] + ext
    return out


def matches_keep_whole(dirname: str) -> bool:
    low = dirname.lower()
    return any(fnmatch.fnmatchcase(low, pat) for pat in KEEP_WHOLE_PATTERNS)


def is_excluded_file(name: str) -> bool:
    low = name.lower()
    return low in EXCLUDED_FILES or any(fnmatch.fnmatchcase(low, p) for p in EXCLUDED_FILE_PATTERNS)


def volume_info(path: str):
    """(nom du volume, numéro de série, système de fichiers) sous Windows, sinon (None,)*3."""
    if not IS_WINDOWS:
        return None, None, None
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive or drive.startswith("\\\\"):
        return None, None, None
    name = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_ulong(0)
    try:
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            drive + "\\", name, 261, ctypes.byref(serial), None, None, fs, 261)
    except Exception:
        return None, None, None
    if not ok:
        return None, None, None
    return name.value, f"{serial.value:08X}", fs.value


def volume_free(root: str) -> int:
    """Espace libre (fonction séparée pour pouvoir la simuler dans les tests)."""
    return shutil.disk_usage(root).free


def volume_total(root: str) -> int:
    return shutil.disk_usage(root).total


@dataclass
class Drive:
    root: str            # ex. "E:\\"
    kind: str            # "amovible", "interne", "réseau"
    name: str
    serial: str
    filesystem: str
    total: int
    used: int
    free: int

    def describe(self) -> str:
        name = f"« {self.name} »" if self.name else "(sans nom)"
        return (f"{self.root}  {name}  —  {fmt_size(self.total)} "
                f"({fmt_size(self.used)} utilisés)  —  disque {self.kind}")


def list_drives() -> list[Drive]:
    """Lecteurs actuellement branchés (Windows)."""
    if not IS_WINDOWS:
        return []
    k32 = ctypes.windll.kernel32
    k32.SetErrorMode(1)   # pas de fenêtre « insérez un disque » sur un lecteur de carte vide
    kinds = {2: "amovible", 3: "interne", 4: "réseau"}
    mask = k32.GetLogicalDrives()
    drives = []
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = f"{chr(65 + i)}:\\"
        kind = kinds.get(k32.GetDriveTypeW(root))
        if not kind:
            continue
        name, serial, fs = volume_info(root)
        if serial is None:
            continue
        try:
            u = shutil.disk_usage(root)
        except OSError:
            continue
        drives.append(Drive(root, kind, name or "", serial, fs or "", u.total, u.used, u.free))
    return drives


def drive_root_of(path: str) -> str:
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive + "\\" if drive and not drive.startswith("\\\\") else ""


def subpath_of(path: str):
    """Chemin sans la lettre de lecteur : 'G:\\ArchiveFamiliale' -> '\\ArchiveFamiliale'."""
    drive = drive_root_of(path)
    return path[len(drive) - 1:] if drive else None


def read_marker(root: str):
    try:
        with open(os.path.join(root, CATALOG_DIR, MARKER_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None


def write_marker(root: str, archive_id: str, vol, set_name: str | None = None):
    d = os.path.join(root, CATALOG_DIR)
    os.makedirs(d, exist_ok=True)
    data = {
        "info": "Ce disque fait partie d'une Archive Familiale. Ne pas modifier ni supprimer ce fichier.",
        "archive_id": archive_id,
        "volume_id": vol["id"],
        "set_id": vol["set_id"],
        "set_name": set_name,
        "name": vol["name"],
        "number": vol["number"],
    }
    tmp = os.path.join(d, MARKER_NAME + ".partial")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, MARKER_NAME))


def locate_volume(vol, drives: list[Drive] | None = None):
    """Retrouve le dossier d'un disque de l'archive, même si sa lettre a changé."""
    cands = []
    if vol["root"]:
        cands.append(vol["root"])
    if vol["subpath"] and IS_WINDOWS:
        if drives is None:
            drives = list_drives()
        for d in sorted(drives, key=lambda d: d.serial != vol["volume_serial"]):
            cands.append(d.root[:2] + vol["subpath"])
    seen = set()
    for c in cands:
        key = os.path.normcase(c)
        if key in seen:
            continue
        seen.add(key)
        m = read_marker(c)
        if m and m.get("volume_id") == vol["id"]:
            return c
    return None


@contextlib.contextmanager
def keep_awake():
    """Empêche la mise en veille de Windows pendant une longue opération."""
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    if IS_WINDOWS:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception:
            pass
    try:
        yield
    finally:
        if IS_WINDOWS:
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass


def _set_creation_time_windows(path: str, ns: int):
    """Recopie la date de création (Windows uniquement ; os.utime ne la gère pas)."""
    try:
        import ctypes.wintypes as wt
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = wt.HANDLE
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                    wt.DWORD, wt.DWORD, wt.HANDLE]
        k32.SetFileTime.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wt.HANDLE]
        FILE_WRITE_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 0x100, 3, 0x02000000
        handle = k32.CreateFileW(lp(path), FILE_WRITE_ATTRIBUTES, 0x7, None, OPEN_EXISTING,
                                 FILE_FLAG_BACKUP_SEMANTICS, None)
        if not handle or handle == wt.HANDLE(-1).value:
            return
        try:
            ticks = ns // 100 + 116444736000000000
            ft = wt.FILETIME(ticks & 0xFFFFFFFF, ticks >> 32)
            k32.SetFileTime(handle, ctypes.byref(ft), None, None)
        finally:
            k32.CloseHandle(handle)
    except Exception:
        pass


class _StartingVcn(ctypes.Structure):
    _fields_ = [("vcn", ctypes.c_longlong)]


class _FirstExtent(ctypes.Structure):   # RETRIEVAL_POINTERS_BUFFER limité au premier fragment
    _fields_ = [("count", ctypes.c_ulong), ("start_vcn", ctypes.c_longlong),
                ("next_vcn", ctypes.c_longlong), ("lcn", ctypes.c_longlong)]


_k32_pos = None


def disk_position(path: str):
    """Position physique du début du fichier sur son disque (numéro de cluster), ou None
    (petit fichier rangé dans la table des fichiers, système de fichiers qui ne le dit pas…).
    Lit seulement les métadonnées : le fichier n'est pas ouvert en lecture."""
    global _k32_pos
    if not IS_WINDOWS:
        return None
    import ctypes.wintypes as wt
    if _k32_pos is None:
        k32 = ctypes.WinDLL("kernel32")
        k32.CreateFileW.restype = wt.HANDLE
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                    wt.DWORD, wt.DWORD, wt.HANDLE]
        k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                        ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wt.HANDLE]
        _k32_pos = k32
    FILE_READ_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 0x80, 3, 0x02000000
    FSCTL_GET_RETRIEVAL_POINTERS = 0x00090073
    handle = _k32_pos.CreateFileW(lp(path), FILE_READ_ATTRIBUTES, 0x7, None, OPEN_EXISTING,
                                  FILE_FLAG_BACKUP_SEMANTICS, None)
    if not handle or handle == wt.HANDLE(-1).value:
        return None
    try:
        inp, out, n = _StartingVcn(0), _FirstExtent(), wt.DWORD(0)
        # Échoue avec ERROR_MORE_DATA si le fichier a plusieurs fragments : le premier est rempli quand même.
        _k32_pos.DeviceIoControl(handle, FSCTL_GET_RETRIEVAL_POINTERS, ctypes.byref(inp), ctypes.sizeof(inp),
                                 ctypes.byref(out), ctypes.sizeof(out), ctypes.byref(n), None)
        return out.lcn if out.count >= 1 and out.lcn >= 0 else None
    finally:
        _k32_pos.CloseHandle(handle)


def order_by_disk_position(root: str, entries: list, skip: set) -> list:
    """Range les fichiers dans l'ordre où ils sont posés sur le disque : sur un disque dur
    mécanique, la tête de lecture avance alors d'un fichier au suivant au lieu de faire des allers-
    retours (gain important sur les photos et petits fichiers ; sans effet sur SSD ou carte SD).
    Les fichiers de skip (déjà traités) et ceux sans position connue passent en premier."""
    keys = []
    for i, e in enumerate(entries):
        if i % 1000 == 0:
            check_cancel()
        pos = None if e.rel in skip else disk_position(os.path.join(root, to_os(e.rel)))
        keys.append(-1 if pos is None else pos)
    order = sorted(range(len(entries)), key=keys.__getitem__)   # stable : sinon, ordre des dossiers
    return [entries[i] for i in order]


def copy_times(src: str, dst: str):
    st = os.stat(lp(src))
    os.utime(lp(dst), ns=(st.st_atime_ns, st.st_mtime_ns))
    if IS_WINDOWS:
        birth = getattr(st, "st_birthtime_ns", None) or st.st_ctime_ns
        _set_creation_time_windows(dst, birth)


def new_hasher():
    return hashlib.blake2b(digest_size=32)


def hash_file(path: str, progress: Progress | None = None) -> str:
    h = new_hasher()
    with open(lp(path), "rb", buffering=0) as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            if progress:
                progress.add(len(chunk))
    return h.hexdigest()


def copy_with_hash(src: str, dst: str, progress: Progress | None = None) -> str:
    """Copie src -> dst en calculant le hash au vol. Écrit d'abord dans un .partial,
    puis renomme : une copie interrompue ne laisse jamais de fichier tronqué."""
    os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
    tmp = dst + ".partial"
    h = new_hasher()
    try:
        with open(lp(src), "rb", buffering=0) as fi, open(lp(tmp), "wb") as fo:
            while True:
                chunk = fi.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                fo.write(chunk)
                if progress:
                    progress.add(len(chunk))
            fo.flush()
            os.fsync(fo.fileno())
        copy_times(src, tmp)
        os.replace(lp(tmp), lp(dst))
    except BaseException:
        try:
            os.remove(lp(tmp))
        except OSError:
            pass
        raise
    return h.hexdigest()


def read_file(path: str, progress: Progress | None = None):
    """Lit un fichier entier en mémoire : (liste de blocs, empreinte). Pour les petits fichiers
    dont il faut l'empreinte avant de savoir s'il faut les copier : une seule lecture du disque."""
    h = new_hasher()
    parts = []
    with open(lp(path), "rb", buffering=0) as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            parts.append(chunk)
            if progress:
                progress.add(len(chunk))
    return parts, h.hexdigest()


class _WriteJob:
    def __init__(self, src: str, dst: str, on_fail):
        self.src, self.dst, self.tmp = src, dst, dst + ".partial"
        self.on_fail = on_fail
        self.fo = None
        self.keep = None       # décidé par le thread principal à la fin de la lecture
        self.error = None


class Writer:
    """Écriture en tâche de fond, à la chaîne : pendant que le thread principal lit (et calcule
    l'empreinte d')un fichier sur un disque, un thread écrit le précédent sur l'autre, et un
    troisième le synchronise (fsync), lui remet ses dates et le renomme de .partial en nom final.
    flush() attend la fin de tout cela ; il est appelé avant chaque commit du catalogue
    (Archive.commit) : un fichier n'est donc jamais inscrit au catalogue avant d'être réellement
    sur le disque.
    Au plus WRITE_QUEUE_CHUNKS blocs attendent d'être écrits ; leur taille (pending) est déduite
    de l'espace libre par l'Allocator.
    Une écriture qui échoue est signalée au thread principal par job.on_fail(exception)."""

    def __init__(self):
        self.q = queue.Queue(maxsize=WRITE_QUEUE_CHUNKS)
        self.sq = queue.Queue()   # fichiers écrits, à synchroniser et renommer
        self.failed = []          # remis au thread principal par flush()
        self.pending = 0          # octets confiés, pas encore écrits dans un fichier
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="ecriture", daemon=True)
        self.sync_thread = threading.Thread(target=self._run_sync, name="synchro", daemon=True)
        self.thread.start()
        self.sync_thread.start()

    # -- thread principal --
    def start(self, src: str, dst: str, on_fail) -> _WriteJob:
        job = _WriteJob(src, dst, on_fail)
        self.q.put(("open", job, None))
        return job

    def write(self, job: _WriteJob, data: bytes):
        with self.lock:
            self.pending += len(data)
        self.q.put(("data", job, data))

    def end(self, job: _WriteJob, keep: bool = True):
        job.keep = keep
        self.q.put(("close", job, keep))

    def flush(self):
        """Attend que tout soit écrit, synchronisé et renommé, puis signale les échecs."""
        done = threading.Event()
        self.q.put(("flush", None, done))
        done.wait()
        with self.lock:
            failed, self.failed = self.failed, []
        for job in failed:
            if job.keep:
                job.on_fail(job.error)

    def stop(self):
        self.flush()
        self.q.put(("stop", None, None))
        self.thread.join()
        self.sync_thread.join()

    # -- thread d'écriture --
    def _run(self):
        while True:
            op, job, arg = self.q.get()
            if op in ("stop", "flush"):
                self.sq.put((op, arg))   # dans l'ordre, après les fichiers déjà écrits
                if op == "stop":
                    return
                continue
            try:
                if job.error is not None:
                    continue
                if op == "open":
                    os.makedirs(lp(os.path.dirname(job.dst)), exist_ok=True)
                    job.fo = open(lp(job.tmp), "wb")
                elif op == "data":
                    job.fo.write(arg)
                    job.fo.flush()   # la place est prise sur le disque avant de quitter pending
                elif op == "close":
                    if arg:
                        self.sq.put(("sync", job))   # le fichier reste ouvert pour le fsync
                    else:
                        job.fo.close()
                        job.fo = None
                        os.remove(lp(job.tmp))
            except Exception as exc:
                self._fail(job, exc)
            finally:
                if op == "data":
                    with self.lock:
                        self.pending -= len(arg)

    # -- thread de synchronisation --
    def _run_sync(self):
        while True:
            op, arg = self.sq.get()
            if op == "stop":
                return
            if op == "flush":
                arg.set()
                continue
            job = arg
            try:
                job.fo.flush()
                os.fsync(job.fo.fileno())
                job.fo.close()
                job.fo = None
                copy_times(job.src, job.tmp)
                os.replace(lp(job.tmp), lp(job.dst))
            except Exception as exc:
                self._fail(job, exc)

    def _fail(self, job: _WriteJob, exc: Exception):
        job.error = exc
        try:
            if job.fo:
                job.fo.close()
                job.fo = None
            os.remove(lp(job.tmp))
        except OSError:
            pass
        with self.lock:
            self.failed.append(job)


def copy_async(writer: Writer, src: str, dst: str, progress: Progress | None, on_fail,
               expect: str | None = None) -> str:
    """Comme copy_with_hash, mais l'écriture est confiée à writer. Si expect est donné et que le
    contenu lu ne lui correspond pas, la copie est abandonnée. Renvoie l'empreinte du contenu lu."""
    job = writer.start(src, dst, on_fail)
    h = new_hasher()
    try:
        with open(lp(src), "rb", buffering=0) as fi:
            while True:
                chunk = fi.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                writer.write(job, chunk)
                if progress:
                    progress.add(len(chunk))
    except BaseException:
        writer.end(job, keep=False)
        raise
    digest = h.hexdigest()
    writer.end(job, keep=expect is None or digest == expect)
    return digest


def measure_read_speed(path: str, limit: int = 256 * 1024 ** 2, seconds: float = 3.0):
    """Débit de lecture (octets/s) mesuré sur le début d'un gros fichier, ou None."""
    done, t0 = 0, time.monotonic()
    try:
        with open(lp(path), "rb", buffering=0) as f:
            while done < limit and time.monotonic() - t0 < seconds:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                done += len(chunk)
    except OSError:
        return None
    elapsed = time.monotonic() - t0
    return done / elapsed if done >= 16 * 1024 ** 2 and elapsed > 0 else None


def measure_write_speed(folder: str, size: int = 64 * 1024 ** 2):
    """Débit d'écriture (octets/s) : écrit puis efface un fichier de test, ou None."""
    path = os.path.join(folder, ".test-vitesse.partial")
    block = os.urandom(CHUNK)   # aléatoire : certains disques compressent les zéros
    try:
        t0 = time.monotonic()
        with open(lp(path), "wb", buffering=0) as f:
            for _ in range(size // CHUNK):
                f.write(block)
            os.fsync(f.fileno())
        elapsed = time.monotonic() - t0
    except OSError:
        return None
    finally:
        try:
            os.remove(lp(path))
        except OSError:
            pass
    return size / elapsed if elapsed > 0 else None


def report_speeds(label: str, root: str, entries: list, dest: tuple | None):
    """Mesure la vitesse de la source (et du disque d'archive qui va recevoir les fichiers),
    annonce une durée estimée et signale un disque branché en USB 2."""
    total = sum(e.size for e in entries)
    if total < SPEED_TEST_MIN:
        return
    print("Vitesse des disques…")
    big = max(entries, key=lambda e: e.size)
    speeds = []
    r = measure_read_speed(os.path.join(root, to_os(big.rel))) if big.size >= 64 * 1024 ** 2 else None
    if r:
        speeds.append((f"« {label} » (lecture)", r))
    if dest:
        name, folder = dest
        w = measure_write_speed(folder)
        if w:
            speeds.append((f"« {name} » (écriture)", w))
    if not speeds:
        return
    for what, v in speeds:
        print(f"  {what} : {fmt_size(v)}/s")
    slowest = min(v for _, v in speeds)
    print(f"  durée estimée : au moins {fmt_duration(total / slowest)} pour {fmt_size(total)}"
          f" (plus long s'il y a beaucoup de petits fichiers ou de doublons à relire)")
    log.info("Vitesses : %s", ", ".join(f"{w} {fmt_size(v)}/s" for w, v in speeds))
    for what, v in speeds:
        if v < SLOW_DISK:
            print(f"  ⚠ {what} est lent ({fmt_size(v)}/s) : il est sans doute branché en USB 2. "
                  f"Sur un port USB 3 (bleu, ou marqué « SS »), ce serait environ 3 fois plus rapide. "
                  f"Vous pouvez arrêter, changer de port, puis relancer : rien n'est perdu.")


def is_disk_full(exc: OSError) -> bool:
    return getattr(exc, "errno", None) == 28 or getattr(exc, "winerror", None) in (39, 112)


@dataclass(slots=True)
class Entry:
    rel: str          # chemin relatif à la racine, séparateur /
    size: int
    mtime_ns: int
    ctime_ns: int
    keep_whole: bool


def is_windows_root(path: str) -> bool:
    return os.path.isdir(lp(os.path.join(path, "Windows", "System32")))


def is_mac_root(path: str) -> bool:
    return os.path.isdir(lp(os.path.join(path, "System", "Library"))) and \
        os.path.isdir(lp(os.path.join(path, "Applications")))


def is_archive_volume(path: str) -> bool:
    return os.path.isfile(lp(os.path.join(path, CATALOG_DIR, MARKER_NAME)))


def _child_mode(parent_mode, name_low: str, child_abs: str):
    """Mode « système » d'un sous-dossier, ou 'skip' s'il faut l'ignorer.
    Sert à ne garder que les fichiers des utilisateurs sur un disque système Windows/macOS."""
    if parent_mode == "win_root":
        if name_low in WIN_SYSTEM_TOP:
            return "skip"
        if name_low == "users":
            return "win_users"
        if name_low == "windows.old" and is_windows_root(child_abs):
            return "win_root"
        return "outside"
    elif parent_mode == "win_users":
        return "skip" if name_low in WIN_SKIP_PROFILES else "win_user"
    elif parent_mode == "win_user":
        if name_low in WIN_USER_SKIP or name_low.startswith("."):   # .vscode, .nuget… : outils
            return "skip"
    elif parent_mode == "mac_root":
        if name_low in MAC_SYSTEM_TOP:
            return "skip"
        if name_low == "users":
            return "mac_users"
    elif parent_mode == "mac_users":
        return "skip" if name_low == "shared" else "mac_user"
    elif parent_mode == "mac_user":
        if name_low in MAC_USER_SKIP:
            return "skip"
    return None


def print_outside(outside: list[str]):
    """Signale les dossiers de la racine d'un disque Windows qui n'ont pas été lus."""
    dirs = sorted(r.rstrip("/") for r in outside if r.endswith("/"))
    if dirs:
        shown = ", ".join(dirs[:15]) + (f" et {len(dirs) - 15} autres" if len(dirs) > 15 else "")
        print(f"  Non lus (à la racine, hors des dossiers des utilisateurs) : {shown}.")
        print("  S'il s'y trouve des fichiers personnels, importez ce dossier à part "
              "(« Ajouter un dossier précis »).")


def walk_source(root: str, include_trash: bool, on_skip, skip_top: str | None = None,
                exclusions: bool = True, include_system: bool = False, skip_archives: bool = True):
    """Parcourt root sans suivre les liens. Renvoie la liste des fichiers (Entry).
    on_skip(relpath, raison) est appelé pour chaque élément ignoré ou illisible.
    - exclusions : ignorer fichiers parasites, dossiers système et corbeilles ;
    - include_system=False : sur un disque contenant Windows ou macOS, ignorer le système et
      les programmes pour ne garder que les fichiers des utilisateurs ;
    - skip_archives : ignorer les dossiers qui sont des disques d'une archive (ArchiveFamiliale)."""
    entries: list[Entry] = []
    root_mode = None
    if exclusions and not include_system:
        root_mode = "win_root" if is_windows_root(root) else ("mac_root" if is_mac_root(root) else None)
    stack: list[tuple[str, bool, str | None]] = [("", False, root_mode)]
    tty = _isatty(sys.stderr) and not Progress.hook
    last = time.monotonic()
    while stack:
        check_cancel()
        reldir, keep_whole, mode = stack.pop()
        absdir = os.path.join(root, to_os(reldir)) if reldir else root
        if reldir and skip_archives and is_archive_volume(absdir):
            on_skip(reldir + "/", "disque d'une archive (ignoré)")
            continue
        try:
            it = os.scandir(lp(absdir))
        except OSError as e:
            on_skip(reldir + "/" if reldir else "./", f"dossier illisible : {e}")
            continue
        with it:
            for de in it:
                name = de.name
                rel = f"{reldir}/{name}" if reldir else name
                try:
                    is_junction = getattr(de, "is_junction", lambda: False)()
                    if de.is_symlink() or is_junction:
                        on_skip(rel, "lien symbolique / jonction (non suivi)")
                        continue
                    if de.is_dir(follow_symlinks=False):
                        low = name.lower()
                        if skip_top and not reldir and low == skip_top.lower():
                            continue
                        if exclusions and low in EXCLUDED_DIRS:
                            on_skip(rel + "/", "dossier système ignoré")
                            continue
                        if exclusions and low in TRASH_DIRS and not include_trash:
                            on_skip(rel + "/", "corbeille ignorée (voir --inclure-corbeille)")
                            continue
                        cmode = _child_mode(mode, low, os.path.join(absdir, name)) if mode else None
                        if cmode == "skip":
                            on_skip(rel + "/", "système / programmes ignorés (voir --inclure-systeme)")
                            continue
                        if cmode == "outside":
                            on_skip(rel + "/", SKIP_OUTSIDE_USERS)
                            continue
                        stack.append((rel, keep_whole or matches_keep_whole(name), cmode))
                    elif de.is_file(follow_symlinks=False):
                        if exclusions and is_excluded_file(name):
                            on_skip(rel, "fichier système ignoré")
                            continue
                        if mode == "win_root" and not reldir:
                            on_skip(rel, SKIP_OUTSIDE_USERS)
                            continue
                        st = de.stat(follow_symlinks=False)
                        if CLOUD_ATTRS & getattr(st, "st_file_attributes", 0):
                            on_skip(rel, "fichier « en ligne uniquement » (OneDrive, iCloud…) : non téléchargé")
                            continue
                        ctime = getattr(st, "st_birthtime_ns", None) or st.st_ctime_ns
                        entries.append(Entry(rel, st.st_size, st.st_mtime_ns, ctime, keep_whole))
                    else:
                        on_skip(rel, "fichier spécial ignoré")
                except OSError as e:
                    on_skip(rel, f"illisible : {e}")
        if time.monotonic() - last > 0.3:
            last = time.monotonic()
            if Progress.hook:
                Progress.hook(None, f"Recherche des fichiers : {fmt_int(len(entries))} trouvés…")
            elif tty:
                sys.stderr.write(f"\r  {fmt_int(len(entries))} fichiers trouvés…")
                sys.stderr.flush()
    if tty:
        sys.stderr.write("\r" + " " * 60 + "\r")
    return entries


def dir_is_empty(path: str) -> bool:
    if not os.path.isdir(path):
        return True
    return not [n for n in os.listdir(path) if n.lower() not in EXCLUDED_DIRS and n.lower() not in TRASH_DIRS]


# --------------------------------------------------------------------------- #
# Archive et catalogue
# --------------------------------------------------------------------------- #

class Archive:
    """Archive ouverte depuis le dossier du disque ARCHIVE-1 (qui contient le catalogue)."""

    def __init__(self, root: str, create: bool = False):
        if not root:
            raise UserError("Indiquez le disque principal de l'archive avec -m (ou ARCHIVE_MAITRE).")
        self.root = normalize_dir(root)
        self.cat_dir = os.path.join(self.root, CATALOG_DIR)
        self.db_path = os.path.join(self.cat_dir, DB_NAME)
        if not create and not os.path.exists(self.db_path):
            m = read_marker(self.root)
            if m and m.get("number") != 1 or (m and m.get("set_id") != MAIN_SET):
                raise UserError(f"Ce dossier est le disque « {m.get('name')} » de l'archive, pas le disque "
                                f"principal. Indiquez le disque ARCHIVE-1 (celui qui contient le catalogue).")
            raise UserError(f"Aucune archive trouvée dans {self.root}\n"
                            f"Créez-la d'abord avec : python archive.py init \"{self.root}\"")
        os.makedirs(self.cat_dir, exist_ok=True)
        self._setup_logging()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self._ensure_columns("sources", {"last_check": "TEXT", "last_check_status": "TEXT"})
        self._ensure_columns("stored", {"volume": "TEXT", "orig_path": "TEXT", "class_batch": "INTEGER"})
        self._ensure_columns("backup_copies", {"phys_path": "TEXT"})   # emplacement réel si pas encore renommé
        self.db.execute("CREATE INDEX IF NOT EXISTS stored_volume ON stored(volume)")
        self.db.execute("CREATE INDEX IF NOT EXISTS occ_stored ON occurrences(stored_path)")
        self.db.execute("CREATE INDEX IF NOT EXISTS bc_path ON backup_copies(path)")
        algo = self.meta("hash_algo")
        if algo is None:
            self.set_meta("hash_algo", HASH_ALGO)
            self.set_meta("created_at", now_iso())
            self.set_meta("created_with", VERSION)
        elif algo != HASH_ALGO:
            raise UserError(f"Catalogue créé avec l'algorithme {algo}, incompatible avec {HASH_ALGO}.")
        if self.meta("archive_id") is None:
            self.set_meta("archive_id", uuid.uuid4().hex)
        self.archive_id = self.meta("archive_id")
        self._init_primary()
        self.db.commit()
        self._last_commit = time.monotonic()
        self._pending = 0
        self._writer = None

    def _ensure_columns(self, table, cols: dict):
        existing = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols.items():
            if name not in existing:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")

    def _init_primary(self):
        """Crée (ou met à jour l'emplacement de) ARCHIVE-1, le disque qui porte le catalogue."""
        vname, serial, _ = volume_info(self.root)
        prim = self.db.execute("SELECT * FROM volumes WHERE set_id=? AND number=1", (MAIN_SET,)).fetchone()
        if prim is None:
            vid = uuid.uuid4().hex[:12]
            self.db.execute(
                "INSERT INTO volumes(id,set_id,number,name,root,subpath,volume_serial,volume_name,"
                "capacity,added_at,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (vid, MAIN_SET, 1, "ARCHIVE-1", self.root, subpath_of(self.root), serial, vname,
                 volume_total(self.root), now_iso(), now_iso()))
            prim = self.db.execute("SELECT * FROM volumes WHERE id=?", (vid,)).fetchone()
        elif not same_path(prim["root"], self.root) or prim["volume_serial"] != serial:
            self.db.execute("UPDATE volumes SET root=?, subpath=?, volume_serial=COALESCE(?,volume_serial), "
                            "volume_name=COALESCE(?,volume_name), last_seen=? WHERE id=?",
                            (self.root, subpath_of(self.root), serial, vname, now_iso(), prim["id"]))
            prim = self.db.execute("SELECT * FROM volumes WHERE id=?", (prim["id"],)).fetchone()
        self.primary_id = prim["id"]
        m = read_marker(self.root)
        if not m or m.get("volume_id") != prim["id"]:
            write_marker(self.root, self.archive_id, prim)
        # Archives créées avec la version 1 (un seul disque) : tout est sur ARCHIVE-1
        self.db.execute("UPDATE stored SET volume=? WHERE volume IS NULL", (prim["id"],))

    def _setup_logging(self):
        log_path = os.path.join(self.cat_dir, "journal.log")
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)

    def close(self):
        try:
            if self._writer:
                self._writer.stop()
                self._writer = None
            self.db.commit()
            self.db.close()
        finally:
            for h in list(log.handlers):
                log.removeHandler(h)
                h.close()

    # -- meta --
    def meta(self, key):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def pending_write_bytes(self) -> int:
        return self._writer.pending if self._writer else 0

    def writer(self) -> Writer:
        if self._writer is None:
            self._writer = Writer()
        return self._writer

    def commit(self):
        """Commit du catalogue, après que les fichiers en cours d'écriture sont sur le disque."""
        if self._writer:
            self._writer.flush()
        self.db.commit()
        self._pending = 0
        self._last_commit = time.monotonic()

    def maybe_commit(self, force=False):
        self._pending += 1
        if force or self._pending >= COMMIT_EVERY_FILES or \
                time.monotonic() - self._last_commit > COMMIT_EVERY_SECONDS:
            self.commit()

    # -- disques --
    def volumes(self, set_id=MAIN_SET):
        return self.db.execute("SELECT * FROM volumes WHERE set_id=? ORDER BY number", (set_id,)).fetchall()

    def all_volumes(self):
        return self.db.execute("SELECT * FROM volumes ORDER BY set_id='main' DESC, set_id, number").fetchall()

    def volume(self, vid):
        return self.db.execute("SELECT * FROM volumes WHERE id=?", (vid,)).fetchone()

    def volume_by_name(self, name):
        v = self.db.execute("SELECT * FROM volumes WHERE name=?", (name,)).fetchone()
        if v is None:
            raise UserError(f"Disque « {name} » inconnu. Disques : "
                            + ", ".join(x["name"] for x in self.all_volumes()))
        return v

    def margin(self, vid) -> int:
        return FREE_SPACE_MARGIN + (PRIMARY_EXTRA_MARGIN if vid == self.primary_id else 0)

    def resolve_roots(self, set_id=MAIN_SET, drives=None) -> dict:
        """{id du disque: dossier si branché, sinon None}. Met à jour les emplacements connus."""
        roots = {}
        for v in self.volumes(set_id):
            if v["id"] == self.primary_id:
                roots[v["id"]] = self.root
                continue
            if drives is None and v["subpath"] and IS_WINDOWS and not (v["root"] and read_marker(v["root"])):
                drives = list_drives()
            r = locate_volume(v, drives if drives is not None else [])
            roots[v["id"]] = r
            if r:
                vname, serial, _ = volume_info(r)
                self.db.execute("UPDATE volumes SET root=?, subpath=?, volume_serial=COALESCE(?,volume_serial), "
                                "last_seen=? WHERE id=?", (r, subpath_of(r), serial, now_iso(), v["id"]))
        self.db.commit()
        return roots

    def backup_set(self, name):
        r = self.db.execute("SELECT * FROM backup_sets WHERE name=?", (name,)).fetchone()
        if r is None:
            names = [x["name"] for x in self.db.execute("SELECT name FROM backup_sets")]
            raise UserError(f"Jeu de sauvegarde « {name} » inconnu."
                            + (f" Jeux existants : {', '.join(names)}" if names else
                               " Créez-le avec : ajouter-disque <dossier> --jeu <nom>"))
        return r

    def set_name(self, set_id):
        if set_id == MAIN_SET:
            return None
        r = self.db.execute("SELECT name FROM backup_sets WHERE id=?", (set_id,)).fetchone()
        return r[0] if r else None

    def no_space_message(self, set_id, size, roots) -> str:
        what = "de l'archive" if set_id == MAIN_SET else f"du jeu « {self.set_name(set_id)} »"
        unplugged = [v["name"] for v in self.volumes(set_id) if not roots.get(v["id"])]
        msg = f"plus de place sur les disques {what} branchés (fichier de {fmt_size(size)} à copier). "
        if unplugged:
            msg += f"Disques non branchés : {', '.join(unplugged)} — branchez-les s'ils ont encore de la place, ou "
        msg += (f"ajoutez un nouveau disque {what} (commande ajouter-disque, ou bouton « Ajouter un disque » "
                f"de l'interface), puis relancez : l'opération reprendra là où elle s'est arrêtée.")
        return msg

    # -- requêtes --
    def size_known(self, size: int) -> bool:
        return self.db.execute("SELECT 1 FROM stored WHERE size=? LIMIT 1", (size,)).fetchone() is not None

    def stored_path_for_hash(self, h: str):
        r = self.db.execute("SELECT path FROM stored WHERE hash=? ORDER BY added_at LIMIT 1", (h,)).fetchone()
        return r[0] if r else None

    def stored_row(self, path: str):
        return self.db.execute("SELECT * FROM stored WHERE path=?", (path,)).fetchone()

    def occurrence(self, label: str, rel: str):
        return self.db.execute("SELECT * FROM occurrences WHERE label=? AND relpath=?",
                               (label, rel)).fetchone()

    def upsert_occurrence(self, label, e: Entry, h, status, stored_path=None, error=None):
        self.db.execute(
            """INSERT INTO occurrences(label,relpath,size,mtime_ns,ctime_ns,hash,status,
                                       stored_path,keep_whole,seen_at,error)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(label,relpath) DO UPDATE SET
                 size=excluded.size, mtime_ns=excluded.mtime_ns, ctime_ns=excluded.ctime_ns,
                 hash=excluded.hash, status=excluded.status, stored_path=excluded.stored_path,
                 keep_whole=excluded.keep_whole, seen_at=excluded.seen_at, error=excluded.error""",
            (label, e.rel, e.size, e.mtime_ns, e.ctime_ns, h, status, stored_path,
             int(e.keep_whole), now_iso(), error))

    def make_dest_rel(self, label: str, rel: str, vroot: str) -> str:
        """Chemin de destination : <label>/<chemin d'origine>, rendu valide et unique dans toute
        l'archive (suffixe « (2) », « (3) »… en cas de collision)."""
        parts = [sanitize_component(label)] + [sanitize_component(p) for p in rel.split("/")]
        cand = "/".join(parts)
        i = 2
        while self.stored_row(cand) is not None or os.path.lexists(lp(os.path.join(vroot, to_os(cand)))):
            stem, ext = os.path.splitext(parts[-1])
            cand = "/".join(parts[:-1] + [f"{stem} ({i}){ext}"])
            i += 1
        return cand

    # -- catalogue et outil --
    def snapshot_db(self, dest_path: str):
        """Copie cohérente du catalogue (API de sauvegarde SQLite)."""
        self.db.commit()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        tmp = dest_path + ".partial"
        if os.path.exists(tmp):
            os.remove(tmp)
        dst = sqlite3.connect(tmp)
        try:
            self.db.backup(dst)
        finally:
            dst.close()
        os.replace(tmp, dest_path)

    def rotate_snapshots(self):
        d = os.path.join(self.cat_dir, "sauvegardes")
        self.snapshot_db(os.path.join(d, f"catalogue_{dt.datetime.now():%Y%m%d_%H%M%S}.sqlite"))
        snaps = sorted(f for f in os.listdir(d) if f.startswith("catalogue_") and f.endswith(".sqlite"))
        for old in snaps[:-SNAPSHOTS_KEPT]:
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass

    def sync_catalog_copies(self, set_ids=None):
        """Copie de secours du catalogue + du programme sur chaque disque branché (sauf ARCHIVE-1)."""
        if set_ids is None:
            set_ids = [MAIN_SET] + [r[0] for r in self.db.execute("SELECT id FROM backup_sets")]
        n = 0
        for sid in set_ids:
            for vid, root in self.resolve_roots(sid).items():
                if root and vid != self.primary_id:
                    try:
                        self.snapshot_db(os.path.join(root, CATALOG_DIR, CATALOG_COPY_NAME))
                        self.install_tool_copy(os.path.join(root, CATALOG_DIR))
                        n += 1
                    except OSError as e:
                        log.warning("Copie du catalogue sur %s impossible : %s", root, e)
        return n

    def install_tool_copy(self, target_cat_dir: str | None = None):
        """Copie le programme (exe ou scripts) et le README dans l'archive pour qu'elle soit
        autonome : on pourra toujours la relire/vérifier même sans l'ordinateur d'origine."""
        d = os.path.join(target_cat_dir or self.cat_dir, "outil")
        os.makedirs(d, exist_ok=True)
        if getattr(sys, "frozen", False):   # exécutable PyInstaller (mode dossier)
            app_dir = os.path.dirname(sys.executable)
            dst_dir = os.path.join(d, os.path.basename(app_dir))
            if same_path(app_dir, dst_dir):
                return   # on tourne déjà depuis cette copie
            try:
                exe_dst = os.path.join(dst_dir, os.path.basename(sys.executable))
                s = os.stat(sys.executable)
                if not (os.path.exists(exe_dst) and os.stat(exe_dst).st_size == s.st_size
                        and int(os.stat(exe_dst).st_mtime) == int(s.st_mtime)):
                    shutil.copytree(app_dir, dst_dir, dirs_exist_ok=True)
            except OSError:
                pass
            return
        here = os.path.dirname(os.path.abspath(__file__))
        for src in [os.path.join(here, n) for n in ("archive.py", "archive_gui.py", "README.md")]:
            dst = os.path.join(d, os.path.basename(src))
            try:
                if os.path.exists(src) and not same_path(src, dst):
                    s = os.stat(src)
                    if os.path.exists(dst) and os.stat(dst).st_size == s.st_size \
                            and int(os.stat(dst).st_mtime) == int(s.st_mtime):
                        continue
                    shutil.copy2(src, dst)
            except OSError:
                pass

    def record_master_location(self):
        _, serial, _ = volume_info(self.root)
        if serial:
            self.set_meta("master_serial", serial)
        sub = subpath_of(self.root)
        if sub:
            self.set_meta("master_subpath", sub)
        self.db.commit()

    def last_change(self):
        """Date du dernier ajout de fichier dans l'archive."""
        return self.db.execute("SELECT MAX(added_at) FROM stored").fetchone()[0]

    def exclusive_content(self, label: str):
        """Contenu présent sur cette source et nulle part ailleurs."""
        return self.db.execute(
            """SELECT COUNT(*), COALESCE(SUM(size),0) FROM (
                 SELECT hash, MIN(size) AS size FROM occurrences o
                 WHERE o.label=? AND o.hash IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM occurrences o2 WHERE o2.hash=o.hash AND o2.label<>?)
                   AND NOT EXISTS (SELECT 1 FROM stored s WHERE s.hash=o.hash AND
                                   (s.origin_label IS NULL OR s.origin_label<>?))
                 GROUP BY hash)""", (label, label, label)).fetchone()


class Allocator:
    """Choisit le disque où écrire : on remplit les disques dans l'ordre, en gardant un même
    groupe (contenu d'un même ancien disque) sur le même disque tant qu'il y a de la place."""

    def __init__(self, ar: Archive, set_id: str, roots: dict):
        self.ar = ar
        self.roots = roots
        vols = ar.volumes(set_id)
        self.order = [v["id"] for v in vols]
        self.names = {v["id"]: v["name"] for v in vols}
        self.sticky: dict[str, str] = {}
        self.full: set[str] = set()

    def mark_full(self, vid):
        self.full.add(vid)

    def _free(self, vid):
        root = self.roots.get(vid)
        if not root or vid in self.full:
            return None
        try:
            return volume_free(root) - self.ar.margin(vid) - self.ar.pending_write_bytes()
        except OSError:
            return None

    def pick(self, group: str, size: int, prefer=(), group_size: int | None = None):
        cands = []
        for vid in (self.sticky.get(group), *prefer, *self.order):
            if vid and vid not in cands:
                cands.append(vid)
        # Nouveau groupe de taille connue : un disque qui peut le contenir en entier, si possible
        if group_size and group not in self.sticky:
            for vid in cands:
                free = self._free(vid)
                if free is not None and free >= group_size:
                    self.sticky[group] = vid
                    return vid, self.roots[vid]
        for vid in cands:
            root = self.roots.get(vid)
            if not root or vid in self.full:
                continue
            try:
                free = volume_free(root) - self.ar.pending_write_bytes()
            except OSError:
                continue
            if free >= size + self.ar.margin(vid):
                old = self.sticky.get(group)
                if old and old != vid:
                    print(f"\n  -> « {self.names[old]} » est plein : la suite va sur « {self.names[vid]} ».")
                    log.info("Disque %s plein pour %s, bascule sur %s", self.names[old], group, self.names[vid])
                self.sticky[group] = vid
                return vid, root
        return None, None


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #

def validate_label(label: str, what: str = "Label") -> str:
    label = (label or "").strip()
    if not LABEL_RE.match(label) or label.lower() == CATALOG_DIR:
        raise UserError(f"{what} invalide : 1 à 60 caractères parmi lettres (sans accents), chiffres, "
                        f"espace, _ . -\nExemple : \"Disque07-WD-bleu\"")
    return label


def cmd_init(args) -> int:
    root = normalize_dir(args.master)
    if os.path.exists(os.path.join(root, CATALOG_DIR, DB_NAME)):
        print(f"Une archive existe déjà dans {root} : rien à faire.")
        return 0
    if read_marker(root):
        raise UserError(f"{root} est déjà un disque d'une archive.")
    if not dir_is_empty(root) and not args.forcer:
        raise UserError(f"Le dossier {root} n'est pas vide. Utilisez un disque/dossier vide, "
                        f"ou ajoutez --forcer si vous savez ce que vous faites.")
    os.makedirs(root, exist_ok=True)
    ar = Archive(root, create=True)
    try:
        ar.install_tool_copy()
        ar.record_master_location()
        log.info("Archive créée dans %s (version %s)", root, VERSION)
        print(f"Archive créée dans {root}  (disque « ARCHIVE-1 », qui contient le catalogue)")
        print(f"  espace libre : {fmt_size(volume_free(root))}")
        print("  Collez une étiquette « ARCHIVE-1 » sur ce disque.")
    finally:
        ar.close()
    return 0


def _check_new_volume_location(ar: Archive, dst: str, allow_same_disk: bool, accept_source_disk: bool = False):
    for v in ar.all_volumes():
        r = locate_volume(v, [])
        for p in filter(None, (r, v["root"])):
            if is_inside(dst, p) or is_inside(p, dst):
                raise UserError(f"Ce dossier est (ou contient) le disque « {v['name']} » de l'archive.")
    m = read_marker(dst)
    if m:
        raise UserError(f"Ce dossier est déjà le disque « {m.get('name')} » d'une archive.")
    if not dir_is_empty(dst):
        raise UserError(f"Le dossier {dst} contient déjà des fichiers. Choisissez un dossier vide "
                        f"(ex. {os.path.join(drive_root_of(dst) or dst, ARCHIVE_FOLDER)}).")
    _, serial, _ = volume_info(dst)
    if serial and not allow_same_disk:
        for v in ar.all_volumes():
            if v["volume_serial"] == serial:
                raise UserError(f"Ce disque physique porte déjà « {v['name']} ». Un disque ne doit servir qu'une "
                                f"fois (sinon une seule panne ferait perdre deux copies).")
        for s in ar.db.execute("SELECT label, root FROM sources WHERE volume_serial=?", (serial,)):
            if s["root"] and drive_root_of(s["root"]) == s["root"] and not accept_source_disk:
                raise UserError(f"Ce disque est l'ancien disque source « {s['label']} ». Utilisez de préférence un "
                                f"disque dédié ; sinon ajoutez --accepter-disque-source (et n'effacez JAMAIS ce "
                                f"disque : il contiendra l'archive).")


def cmd_add_volume(args) -> int:
    ar = Archive(args.master)
    try:
        dst = normalize_dir(args.dossier)
        if args.jeu:
            ar.db.execute("DELETE FROM meta WHERE key='backup_policy'")   # créer un jeu réactive les sauvegardes
            set_name = validate_label(args.jeu, "Nom de jeu")
            row = ar.db.execute("SELECT * FROM backup_sets WHERE name=?", (set_name,)).fetchone()
            if row is None:
                sid = uuid.uuid4().hex[:12]
                ar.db.execute("INSERT INTO backup_sets(id,name,created_at) VALUES(?,?,?)", (sid, set_name, now_iso()))
                print(f"Nouveau jeu de sauvegarde « {set_name} ».")
            else:
                sid, set_name = row["id"], row["name"]
        else:
            sid, set_name = MAIN_SET, None
        _check_new_volume_location(ar, dst, args.meme_disque, args.accepter_disque_source)
        number = (ar.db.execute("SELECT MAX(number) FROM volumes WHERE set_id=?", (sid,)).fetchone()[0] or 0) + 1
        name = f"ARCHIVE-{number}" if sid == MAIN_SET else f"{set_name}-{number}"
        os.makedirs(dst, exist_ok=True)
        vname, serial, _ = volume_info(dst)
        vid = uuid.uuid4().hex[:12]
        ar.db.execute("INSERT INTO volumes(id,set_id,number,name,root,subpath,volume_serial,volume_name,capacity,"
                      "added_at,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (vid, sid, number, name, dst, subpath_of(dst), serial, vname, volume_total(dst),
                       now_iso(), now_iso()))
        write_marker(dst, ar.archive_id, ar.volume(vid), set_name)
        ar.db.commit()
        ar.snapshot_db(os.path.join(dst, CATALOG_DIR, CATALOG_COPY_NAME))
        ar.install_tool_copy(os.path.join(dst, CATALOG_DIR))
        log.info("Disque ajouté : %s -> %s", name, dst)
        print(f"Disque « {name} » ajouté {'à l' + chr(39) + 'archive' if sid == MAIN_SET else 'au jeu « ' + set_name + ' »'}"
              f" : {dst}  ({fmt_size(volume_free(dst))} libres)")
        print(f"  Collez une étiquette « {name} » sur ce disque.")
    finally:
        ar.close()
    return 0


@dataclass
class RunStats:
    files: int = 0
    bytes: int = 0
    copied: int = 0
    copied_bytes: int = 0
    duplicates: int = 0
    duplicate_bytes: int = 0
    already: int = 0
    scanned: int = 0
    errors: int = 0
    skipped: int = 0
    per_volume: Counter = field(default_factory=Counter)
    error_samples: list = field(default_factory=list)


def _register_source(ar: Archive, label: str, root: str, note: str | None, force: bool, mode: str):
    vname, vserial, vfs = volume_info(root)
    row = ar.db.execute("SELECT * FROM sources WHERE label=?", (label,)).fetchone()
    if row:
        if row["volume_serial"] and vserial and row["volume_serial"] != vserial and not force:
            raise UserError(
                f"Le label « {label} » a déjà été utilisé pour un AUTRE volume "
                f"(n° {row['volume_serial']} « {row['volume_name'] or ''} »), "
                f"alors que celui-ci est n° {vserial} « {vname or ''} ».\n"
                f"Choisissez un autre label, ou ajoutez --forcer si c'est bien le même disque.")
        ar.db.execute("""UPDATE sources SET root=?, volume_name=COALESCE(?,volume_name),
                         volume_serial=COALESCE(?,volume_serial), filesystem=COALESCE(?,filesystem),
                         note=COALESCE(?,note), last_seen=?, last_mode=?, completed=0 WHERE label=?""",
                      (root, vname, vserial, vfs, note, now_iso(), mode, label))
    else:
        ar.db.execute("""INSERT INTO sources(label,note,root,volume_name,volume_serial,filesystem,
                         first_seen,last_seen,last_mode,completed) VALUES(?,?,?,?,?,?,?,?,?,0)""",
                      (label, note, root, vname, vserial, vfs, now_iso(), now_iso(), mode))
    ar.db.commit()
    return vname, vserial, vfs


LAST_ESTIMATE: dict | None = None   # résultat de la dernière estimation (lu par l'interface)
LAST_RUN: dict = {}                  # bilan chiffré du dernier import (lu par l'interface)


def cmd_estimate(args) -> int:
    """Estimation RAPIDE : liste les fichiers sans les lire. Un fichier est compté comme « sans doute
    déjà présent » si un fichier de même nom et de même taille est déjà dans l'archive (ou plus haut
    dans la liste des disques estimés). Rien n'est écrit dans le catalogue."""
    global LAST_ESTIMATE
    import bilan
    ar = Archive(args.master)
    try:
        summary = bilan.Summary()   # ce que contiennent ces disques, doublons entre eux retirés
        inner = set()
        known = {hash((size, rel.rsplit("/", 1)[-1].lower()))
                 for size, rel in ar.db.execute("SELECT size, relpath FROM occurrences "
                                                "WHERE status IN ('copied','duplicate')")}
        roots = ar.resolve_roots(MAIN_SET)
        free = 0
        for vid, r in roots.items():
            if r:
                try:
                    free += volume_free(r) - ar.margin(vid)
                except OSError:
                    pass
        rows = []
        for src in args.sources:
            root = normalize_dir(src)
            if not os.path.isdir(root):
                print(f"\n{root} : introuvable, ignoré.")
                rows.append({"source": root, "error": "introuvable"})
                continue
            print(f"\nEstimation de {root}…")
            outside = []
            entries = walk_source(root, False, lambda rel, reason: reason == SKIP_OUTSIDE_USERS
                                  and outside.append(rel))
            print_outside(outside)
            total = dup = 0
            for e in entries:
                key = hash((e.size, e.rel.rsplit("/", 1)[-1].lower()))
                summary.seen_n += 1
                summary.seen_b += e.size
                if key not in inner or not e.size:
                    inner.add(key)
                    summary.add(e.rel, e.size, e.mtime_ns)
                total += e.size
                if e.size and key in known:
                    dup += e.size
                else:
                    known.add(key)
            rows.append({"source": root, "files": len(entries), "total": total, "dup": dup, "new": total - dup})
            print(f"  {fmt_int(len(entries))} fichiers, {fmt_size(total)} — sans doute déjà présents : "
                  f"{fmt_size(dup)} — nouveaux : environ {fmt_size(total - dup)}")
        new = sum(r.get("new", 0) for r in rows)
        LAST_ESTIMATE = {"rows": rows, "new": new, "free": max(free, 0), "summary": summary}
        print("\nCe que contiennent ces disques :")
        print(summary.text(fmt_int, fmt_size))
        print(f"\nAu total, environ {fmt_size(new)} de nouveau à copier ; place libre sur l'archive : "
              f"{fmt_size(max(free, 0))}.")
        if new > free:
            print(f"  Il faudra sans doute environ {fmt_size(new - free)} de plus : prévoyez un disque d'archive "
                  f"supplémentaire.")
        print("  (Estimation rapide, d'après le nom et la taille des fichiers : l'import, qui compare le "
              "contenu exact, trouvera parfois un peu plus de doublons.)")
        return 0
    finally:
        ar.close()


def cmd_summary(args) -> int:
    """Bilan de l'archive : combien de photos, de vidéos, de documents… et sur quelle période."""
    import bilan
    ar = Archive(args.master)
    try:
        s = bilan.from_catalog(ar.db)
        if not s.seen_n:
            print("Rien n'a encore été importé.")
            return 0
        print("Ce que contient l'archive :")
        print(s.text(fmt_int, fmt_size))
        return 0
    finally:
        ar.close()


def cmd_option(args) -> int:
    ar = Archive(args.master)
    try:
        if args.sauvegardes == "non":
            ar.set_meta("backup_policy", "aucune")
            print("Choix enregistré : PAS de jeu de sauvegarde.")
            print("  ATTENTION : l'archive est alors la seule copie. Si un de ses disques tombe en panne, son "
                  "contenu est perdu. Conservez au moins les anciens disques tant que possible.")
        elif args.sauvegardes == "oui":
            ar.db.execute("DELETE FROM meta WHERE key='backup_policy'")
            print("Choix enregistré : sauvegardes activées (au moins 2 jeux recommandés).")
        else:
            print(f"Sauvegardes : {'désactivées (choix)' if ar.meta('backup_policy') == 'aucune' else 'activées'}")
        ar.db.commit()
    finally:
        ar.close()
    return 0


def cmd_ingest(args, copy: bool) -> int:
    ar = Archive(args.master)
    try:
        with keep_awake():
            return _ingest(ar, args, copy)
    finally:
        ar.close()


def _ingest(ar: Archive, args, copy: bool) -> int:
    mode = "import" if copy else "scan"
    root = normalize_dir(args.source)
    label = validate_label(args.label)
    if not os.path.isdir(root):
        raise UserError(f"Source introuvable : {root}")
    # Une source peut CONTENIR un disque de l'archive (ex. disque interne d'un PC qui porte aussi le
    # dossier ArchiveFamiliale) : ce dossier est alors ignoré. Mais elle ne peut pas être DANS l'archive.
    for v in ar.all_volumes():
        r = v["root"]
        if r and is_inside(root, r):
            raise UserError(f"La source se trouve dans le disque « {v['name']} » de l'archive : "
                            f"il ne faut pas l'importer.")
    m = read_marker(root)
    if m:
        raise UserError(f"Ce dossier est le disque « {m.get('name')} » d'une archive : il ne faut pas l'importer.")
    inside = [v["name"] for v in ar.all_volumes() if v["root"] and is_inside(v["root"], root)]

    roots, alloc, prefer = {}, None, ()
    if copy:
        roots = ar.resolve_roots(MAIN_SET)
        alloc = Allocator(ar, MAIN_SET, roots)
        last_vol = ar.db.execute("SELECT volume FROM stored WHERE origin_label=? ORDER BY added_at DESC LIMIT 1",
                                 (label,)).fetchone()
        prefer = (last_vol[0],) if last_vol else ()

    vname, vserial, vfs = _register_source(ar, label, root, args.note, args.forcer, mode)
    log.info("=== %s de %s (label=%s, volume=%s/%s/%s)", mode, root, label, vname, vserial, vfs)
    print(f"{'Import' if copy else 'Scan (inventaire seul, aucune copie)'} de {root}  ->  label « {label} »")
    if vserial:
        print(f"  volume : « {vname} » n° {vserial} ({vfs})")
    if copy:
        print("  disques de l'archive :")
        for v in ar.volumes(MAIN_SET):
            r = roots.get(v["id"])
            print(f"    {v['name']:<12} " + (f"branché ({r}) — {fmt_size(volume_free(r))} libres" if r
                                             else "non branché"))

    # 1. Inventaire
    if inside:
        print(f"  (ce disque contient aussi {', '.join(inside)} : ce dossier est ignoré)")
    if not args.inclure_systeme:
        if is_windows_root(root):
            print("  Installation Windows détectée : seuls les dossiers des utilisateurs (Documents, Images, "
                  "Bureau…) sont lus ; Windows, les programmes et AppData sont ignorés "
                  "(--inclure-systeme pour tout prendre).")
        elif is_mac_root(root):
            print("  Installation macOS détectée : système, applications et Bibliothèques sont ignorés ; "
                  "seuls les fichiers des utilisateurs sont analysés (--inclure-systeme pour tout prendre).")
    print("Inventaire des fichiers…")
    ar.db.execute("DELETE FROM skipped WHERE label=?", (label,))
    st = RunStats()
    outside = []

    def on_skip(rel, reason):
        st.skipped += 1
        ar.db.execute("INSERT OR REPLACE INTO skipped(label,relpath,reason) VALUES(?,?,?)",
                      (label, rel, reason))
        if reason == SKIP_OUTSIDE_USERS:
            outside.append(rel)
        if reason.startswith(("dossier illisible", "illisible")):
            log.warning("[%s] %s : %s", label, rel, reason)

    try:
        entries = walk_source(root, args.inclure_corbeille, on_skip, include_system=args.inclure_systeme)
    except KeyboardInterrupt:
        ar.db.commit()
        print("\nInterrompu pendant la recherche des fichiers. Rien n'a été copié.")
        return 130
    ar.db.commit()
    total_bytes = sum(e.size for e in entries)
    print(f"  {fmt_int(len(entries))} fichiers, {fmt_size(total_bytes)}"
          f"  ({fmt_int(st.skipped)} éléments ignorés)")
    print_outside(outside)
    done_status = ("copied", "duplicate") if copy else ("scanned", "copied", "duplicate")
    done = {r[0] for r in ar.db.execute(   # déjà traités lors d'un passage précédent
        f"SELECT relpath FROM occurrences WHERE label=? AND status IN ({','.join('?' * len(done_status))})",
        (label, *done_status))}
    if IS_WINDOWS and not args.ordre_dossiers:
        print("Ordre de lecture selon l'emplacement sur le disque…")
        t0 = time.monotonic()
        try:
            entries = order_by_disk_position(root, entries, done)
        except KeyboardInterrupt:
            print("\nInterrompu pendant la recherche des fichiers. Rien n'a été copié.")
            return 130
        log.info("Ordre physique de %s fichiers calculé en %s", len(entries), fmt_duration(time.monotonic() - t0))
    dest = None
    if copy:
        vid, vroot = alloc.pick(label, max((e.size for e in entries), default=0), prefer)
        if vid:
            dest = (alloc.names[vid], os.path.join(vroot, CATALOG_DIR))
    try:
        report_speeds(label, root, [e for e in entries if e.rel not in done], dest)
    except KeyboardInterrupt:
        print("\nInterrompu avant la copie. Rien n'a été copié.")
        return 130

    # 2. Traitement fichier par fichier
    progress = Progress(len(entries), total_bytes)
    interrupted = False
    fatal = None
    try:
        for e in entries:
            try:
                _process_entry(ar, label, root, e, copy, st, progress, alloc, prefer)
            except FatalCopyError as exc:
                fatal = str(exc)
                break
            except OSError as exc:
                st.errors += 1
                msg = f"{type(exc).__name__}: {exc}"
                if len(st.error_samples) < 10:
                    st.error_samples.append(f"{e.rel} -> {msg}")
                log.error("[%s] %s : %s", label, e.rel, msg)
                ar.upsert_occurrence(label, e, None, "error", error=msg)
            st.files += 1
            st.bytes += e.size
            progress.file_done(e.size)
            ar.maybe_commit()
    except KeyboardInterrupt:
        interrupted = True
    elapsed = progress.finish()
    ar.commit()   # attend la fin des écritures : les erreurs d'écriture sont comptées avant le bilan

    completed =copy and not interrupted and not fatal and st.errors == 0
    now = now_iso()
    ar.db.execute("UPDATE sources SET completed=?, last_seen=? WHERE label=?", (int(completed), now, label))
    if completed:   # import complet sans erreur : il vaut contrôle rapide, inutile de rebrancher le disque
        ar.db.execute("UPDATE sources SET last_check=?, last_check_status='ok' WHERE label=?", (now, label))
    ar.db.commit()
    if copy:
        ar.rotate_snapshots()
        ar.sync_catalog_copies()

    # 3. Bilan
    excl_n, excl_b = ar.exclusive_content(label)
    print()
    print(f"Bilan pour « {label} » ({fmt_duration(elapsed)}) :")
    print(f"  fichiers traités              : {fmt_int(st.files)} / {fmt_int(len(entries))}  ({fmt_size(st.bytes)})")
    if copy:
        print(f"  nouveaux, copiés dans l'archive : {fmt_int(st.copied)}  ({fmt_size(st.copied_bytes)})")
        names = {v["id"]: v["name"] for v in ar.volumes(MAIN_SET)}
        for vid, b in st.per_volume.items():
            print(f"      dont sur {names.get(vid, vid)} : {fmt_size(b)}")
        print(f"  déjà présents (doublons)      : {fmt_int(st.duplicates)}  ({fmt_size(st.duplicate_bytes)})")
        print(f"  déjà traités (reprise)        : {fmt_int(st.already)}")
    else:
        print(f"  empreintes calculées / reprises : {fmt_int(st.scanned)}")
    print(f"  contenu présent UNIQUEMENT ici : {fmt_int(excl_n)} fichiers ({fmt_size(excl_b)})")
    print(f"  erreurs de lecture            : {fmt_int(st.errors)}")
    print(f"  éléments ignorés              : {fmt_int(st.skipped)}")
    for s in st.error_samples:
        print(f"    ! {s}")
    if st.errors > len(st.error_samples):
        print(f"    … liste complète : python archive.py exporter -m \"{ar.root}\"")
    log.info("Fin %s %s : copiés=%s doublons=%s erreurs=%s", mode, label, st.copied, st.duplicates, st.errors)
    LAST_RUN.clear()
    LAST_RUN.update(copied=st.copied, copied_bytes=st.copied_bytes, duplicates=st.duplicates,
                    duplicate_bytes=st.duplicate_bytes, errors=st.errors, elapsed=elapsed)

    if fatal:
        print(f"\nARRÊT : {fatal}")
        return 3
    if interrupted:
        print("\nInterrompu. Relancez exactement la même commande pour reprendre là où vous en étiez.")
        return 130
    if copy and completed:
        print(f"\nOK : tout le contenu de « {label} » est dans l'archive. "
              f"Pour le confirmer avant de vous séparer du disque : commande `controler`.")
    elif copy:
        print("\nAttention : des fichiers n'ont pas pu être lus. Relancez la commande (les fichiers "
              "déjà traités sont sautés) ; si les erreurs persistent, le disque est peut-être abîmé.")
    return 0 if st.errors == 0 else 1


def _process_entry(ar: Archive, label: str, root: str, e: Entry, copy: bool,
                   st: RunStats, progress: Progress, alloc: Allocator | None, prefer):
    row = ar.occurrence(label, e.rel)
    unchanged = (row is not None and row["hash"] and row["size"] == e.size
                 and row["mtime_ns"] == e.mtime_ns)
    if unchanged and row["status"] in ("copied", "duplicate") and row["stored_path"] \
            and ar.stored_row(row["stored_path"]) is not None:
        st.already += 1
        return
    known_hash = row["hash"] if unchanged else None
    src = os.path.join(root, to_os(e.rel))

    if not copy:   # scan : on calcule seulement l'empreinte
        h = known_hash or hash_file(src, progress)
        ar.upsert_occurrence(label, e, h, "scanned")
        st.scanned += 1
        return

    # Import. Si aucun fichier de même taille n'est stocké, le contenu est forcément nouveau :
    # on copie directement (une seule lecture). Sinon on calcule d'abord le hash ; un petit
    # fichier est alors gardé en mémoire pour ne pas le relire s'il faut le copier.
    parts = None
    if known_hash:
        h = known_hash
    elif e.keep_whole or not ar.size_known(e.size):
        h = None
    elif e.size <= SMALL_FILE:
        parts, h = read_file(src, progress)
    else:
        h = hash_file(src, progress)

    if h and not e.keep_whole:
        existing = ar.stored_path_for_hash(h)
        if existing:
            ar.upsert_occurrence(label, e, h, "duplicate", stored_path=existing)
            st.duplicates += 1
            st.duplicate_bytes += e.size
            return

    vid, vroot = alloc.pick(label, e.size, prefer)
    if not vid:
        raise FatalCopyError(ar.no_space_message(MAIN_SET, e.size, alloc.roots))
    dest_rel = ar.make_dest_rel(label, e.rel, vroot)
    dest = os.path.join(vroot, to_os(dest_rel))

    def on_fail(exc):   # écriture échouée, découverte plus tard : on retire le fichier du catalogue
        if is_disk_full(exc):
            alloc.mark_full(vid)
        msg = f"écriture sur l'archive impossible : {type(exc).__name__}: {exc}"
        ar.db.execute("DELETE FROM stored WHERE path=?", (dest_rel,))
        ar.upsert_occurrence(label, e, h2, "error", error=msg)
        st.copied -= 1
        st.copied_bytes -= e.size
        st.per_volume[vid] -= e.size
        st.errors += 1
        if len(st.error_samples) < 10:
            st.error_samples.append(f"{e.rel} -> {msg}")
        log.error("[%s] %s : %s", label, e.rel, msg)

    w = ar.writer()
    if parts is not None:
        job = w.start(src, dest, on_fail)
        for p in parts:
            w.write(job, p)
        w.end(job)
        h2 = h
    else:
        h2 = copy_async(w, src, dest, progress, on_fail, expect=h)
    if h and h2 != h:
        raise OSError("contenu différent entre deux lectures (disque instable ou fichier "
                      "modifié pendant la lecture)")
    ar.db.execute("INSERT INTO stored(path,volume,hash,size,origin_label,added_at) VALUES(?,?,?,?,?,?)",
                  (dest_rel, vid, h2, e.size, label, now_iso()))
    ar.upsert_occurrence(label, e, h2, "copied", stored_path=dest_rel)
    st.copied += 1
    st.copied_bytes += e.size
    st.per_volume[vid] += e.size


def _set_backlog(ar: Archive, set_id: str):
    """(nombre, taille) des fichiers de l'archive pas encore copiés dans ce jeu."""
    return ar.db.execute(
        "SELECT COUNT(*), COALESCE(SUM(size),0) FROM stored s WHERE NOT EXISTS "
        "(SELECT 1 FROM backup_copies b WHERE b.set_id=? AND b.path=s.path)", (set_id,)).fetchone()


def cmd_report(args) -> int:
    ar = Archive(args.master)
    try:
        db = ar.db
        print(f"Archive : {ar.root}")
        print(f"  créée le {ar.meta('created_at')}  —  empreintes {ar.meta('hash_algo')}")
        print()

        roots = ar.resolve_roots(MAIN_SET)
        vstats = {r[0]: (r[1], r[2], r[3]) for r in db.execute(
            "SELECT volume, COUNT(*), COALESCE(SUM(size),0), MAX(added_at) FROM stored GROUP BY volume")}
        vols = ar.volumes(MAIN_SET)
        print(f"DISQUES DE L'ARCHIVE ({len(vols)})")
        for v in vols:
            n, b, last = vstats.get(v["id"], (0, 0, None))
            r = roots.get(v["id"])
            where = f"branché ({r}) — {fmt_size(volume_free(r))} libres" if r else \
                f"NON BRANCHÉ (dernier emplacement : {v['root']})"
            role = "  [principal : contient le catalogue]" if v["id"] == ar.primary_id else ""
            print(f"• {v['name']}{role}")
            print(f"    {where}")
            ver = "jamais vérifié"
            if v["last_verify"]:
                ver = f"vérifié le {v['last_verify']} ({v['last_verify_status']})"
                if last and v["last_verify"] < last:
                    ver += " — fichiers ajoutés depuis"
            print(f"    {fmt_int(n)} fichiers, {fmt_size(b)}  |  {ver}")
        print()

        rows = db.execute(
            """SELECT s.*, COUNT(o.relpath) AS n, COALESCE(SUM(o.size),0) AS sz,
                      COALESCE(SUM(o.status='copied'),0) AS nc,
                      COALESCE(SUM(CASE WHEN o.status='copied' THEN o.size END),0) AS szc,
                      COALESCE(SUM(o.status='duplicate'),0) AS nd,
                      COALESCE(SUM(o.status='scanned'),0) AS ns,
                      COALESCE(SUM(o.status='error'),0) AS ne
               FROM sources s LEFT JOIN occurrences o ON o.label=s.label
               GROUP BY s.label ORDER BY s.first_seen""").fetchall()
        skipped = dict(db.execute("SELECT label, COUNT(*) FROM skipped GROUP BY label").fetchall())
        print(f"ANCIENS DISQUES (SOURCES) ({len(rows)})")
        if not rows:
            print("  Aucune source pour l'instant. Commencez par `scanner` ou `importer` un disque.")
        for r in rows:
            state = "terminé" if r["completed"] else ("scanné" if r["last_mode"] == "scan" else "incomplet")
            vol = f"  volume « {r['volume_name'] or ''} » n° {r['volume_serial']}" if r["volume_serial"] else ""
            note = f"  ({r['note']})" if r["note"] else ""
            print(f"• {r['label']}{note}{vol}")
            chk = f"  —  contrôle : {r['last_check_status']} le {r['last_check']}" if r["last_check"] else ""
            print(f"    dernier passage : {r['last_mode']} le {r['last_seen']}  [{state}]{chk}")
            print(f"    {fmt_int(r['n'])} fichiers, {fmt_size(r['sz'])}  |  copiés : {fmt_int(r['nc'])} "
                  f"({fmt_size(r['szc'])})  |  doublons : {fmt_int(r['nd'])}  |  scannés non importés : "
                  f"{fmt_int(r['ns'])}  |  erreurs : {fmt_int(r['ne'])}  |  ignorés : "
                  f"{fmt_int(skipped.get(r['label'], 0))}")
            en, eb = ar.exclusive_content(r["label"])
            print(f"    contenu présent UNIQUEMENT sur cette source : {fmt_int(en)} fichiers ({fmt_size(eb)})")
        print()

        occ_n, occ_b = db.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM occurrences").fetchone()
        uniq_n, uniq_b = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(size),0) FROM "
            "(SELECT hash, MIN(size) size FROM occurrences WHERE hash IS NOT NULL GROUP BY hash)").fetchone()
        sto_n, sto_b = db.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM stored").fetchone()
        todo_n, todo_b = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(size),0) FROM (SELECT hash, MIN(size) size FROM occurrences "
            "WHERE hash IS NOT NULL AND hash NOT IN (SELECT hash FROM stored) GROUP BY hash)").fetchone()
        err_n = db.execute("SELECT COUNT(*) FROM occurrences WHERE status='error'").fetchone()[0]
        print("GLOBAL")
        print(f"  vu sur l'ensemble des sources    : {fmt_int(occ_n)} fichiers, {fmt_size(occ_b)}")
        print(f"  contenu unique (après dédoublonnage) : {fmt_int(uniq_n)} fichiers, {fmt_size(uniq_b)}")
        if occ_b:
            print(f"  part de doublons                 : {100 * (1 - uniq_b / occ_b):.1f} %")
        print(f"  stocké dans l'archive            : {fmt_int(sto_n)} fichiers, {fmt_size(sto_b)}")
        print(f"  reste à importer (scanné, pas encore copié) : {fmt_int(todo_n)} fichiers, {fmt_size(todo_b)}")
        print(f"  fichiers en erreur               : {fmt_int(err_n)}")
        cm = ar.meta("classification_model")
        if cm:
            todo_c = db.execute("SELECT COUNT(*) FROM stored WHERE class_batch IS NULL").fetchone()[0]
            print(f"  classement                       : modèle {cm}, le {ar.meta('classification_at')}"
                  + (f" — {fmt_int(todo_c)} fichiers ajoutés depuis, à classer" if todo_c else ""))
        else:
            print("  classement                       : non classée (rangement par disque source)")
        print(f"  dernière vérification complète   : {ar.meta('last_verify') or 'jamais'}"
              f"  ({ar.meta('last_verify_status') or '-'})")
        print()

        sets = db.execute("SELECT * FROM backup_sets ORDER BY created_at").fetchall()
        if ar.meta("backup_policy") == "aucune" and not sets:
            print("JEUX DE SAUVEGARDE : aucun, par choix (option --sauvegardes non).")
            print("  ATTENTION : l'archive est la seule copie des données.")
        else:
            print(f"JEUX DE SAUVEGARDE ({len(sets)}, recommandé : au moins 2 dont 1 hors de la maison)")
        for s in sets:
            sroots = ar.resolve_roots(s["id"])
            n, b = _set_backlog(ar, s["id"])
            print(f"• {s['name']}  —  " + ("À JOUR" if n == 0 else f"{fmt_int(n)} fichiers ({fmt_size(b)}) à copier"))
            for v in ar.volumes(s["id"]):
                r = sroots.get(v["id"])
                cnt = db.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM backup_copies WHERE volume=?",
                                 (v["id"],)).fetchone()
                print(f"    {v['name']:<20} {fmt_int(cnt[0])} fichiers, {fmt_size(cnt[1])} — "
                      + (f"branché ({r}), {fmt_size(volume_free(r))} libres" if r else "non branché"))
            print(f"    dernière mise à jour : {s['last_sync'] or 'jamais'} ({s['last_sync_status'] or '-'})"
                  f"  —  dernière vérification : {s['last_verify'] or 'jamais'} ({s['last_verify_status'] or '-'})")
    finally:
        ar.close()
    return 0


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        n = 0
        for r in rows:
            w.writerow(r)
            n += 1
    return n


def cmd_export(args) -> int:
    ar = Archive(args.master)
    try:
        out = normalize_dir(args.dossier) if args.dossier else \
            os.path.join(ar.cat_dir, "exports", f"{dt.datetime.now():%Y%m%d_%H%M%S}")
        os.makedirs(out, exist_ok=True)
        db = ar.db
        n1 = _write_csv(os.path.join(out, "inventaire.csv"),
                        ["source", "chemin_origine", "taille_octets", "date_modification",
                         "statut", "empreinte", "emplacement_dans_archive", "disque_archive", "erreur"],
                        ((r[0], r[1], r[2], ns_to_iso(r[3]), r[4], r[5], r[6], r[7], r[8]) for r in db.execute(
                            "SELECT o.label, o.relpath, o.size, o.mtime_ns, o.status, o.hash, o.stored_path, "
                            "v.name, o.error FROM occurrences o LEFT JOIN stored s ON s.path=o.stored_path "
                            "LEFT JOIN volumes v ON v.id=s.volume ORDER BY o.label, o.relpath")))
        n2 = _write_csv(os.path.join(out, "stockage.csv"),
                        ["emplacement_dans_archive", "disque_archive", "taille_octets", "empreinte",
                         "source_d_origine", "ajouté_le", "vérifié_le", "état_vérification",
                         "emplacement_avant_classement"],
                        db.execute("SELECT s.path, v.name, s.size, s.hash, s.origin_label, s.added_at, "
                                   "s.verified_at, s.verify_status, COALESCE(s.orig_path, s.path) "
                                   "FROM stored s LEFT JOIN volumes v "
                                   "ON v.id=s.volume ORDER BY s.path"))
        n3 = _write_csv(os.path.join(out, "doublons.csv"),
                        ["empreinte", "taille_octets", "nombre_exemplaires", "place_perdue_octets",
                         "emplacements"],
                        db.execute("SELECT hash, MIN(size), COUNT(*), MIN(size)*(COUNT(*)-1), "
                                   "GROUP_CONCAT(label || ' : ' || relpath, ' | ') FROM occurrences "
                                   "WHERE hash IS NOT NULL GROUP BY hash HAVING COUNT(*) > 1 "
                                   "ORDER BY MIN(size)*(COUNT(*)-1) DESC"))
        n4 = _write_csv(os.path.join(out, "ignores_et_erreurs.csv"),
                        ["source", "chemin", "raison"],
                        db.execute("SELECT label, relpath, reason FROM skipped "
                                   "UNION ALL SELECT label, relpath, 'ERREUR : ' || COALESCE(error,'') "
                                   "FROM occurrences WHERE status='error' ORDER BY 1, 2"))
        n5 = _write_csv(os.path.join(out, "sauvegardes.csv"),
                        ["jeu", "emplacement", "disque_sauvegarde", "copié_le", "vérifié_le", "état_vérification"],
                        db.execute("SELECT j.name, b.path, v.name, b.copied_at, b.verified_at, b.verify_status "
                                   "FROM backup_copies b JOIN backup_sets j ON j.id=b.set_id "
                                   "LEFT JOIN volumes v ON v.id=b.volume ORDER BY j.name, b.path"))
        print(f"Exports écrits dans {out}")
        print(f"  inventaire.csv          : {fmt_int(n1)} lignes (tous les fichiers vus, par source)")
        print(f"  stockage.csv            : {fmt_int(n2)} lignes (ce qui est dans l'archive, et sur quel disque)")
        print(f"  doublons.csv            : {fmt_int(n3)} lignes (contenus présents en plusieurs exemplaires)")
        print(f"  ignores_et_erreurs.csv  : {fmt_int(n4)} lignes")
        print(f"  sauvegardes.csv         : {fmt_int(n5)} lignes (où se trouve chaque copie de sauvegarde)")
        print("  (séparateur « ; », s'ouvre directement dans Excel / LibreOffice)")
    finally:
        ar.close()
    return 0


def cmd_verify(args) -> int:
    with keep_awake():
        return _verify(args)


def _verify(args) -> int:
    ar = Archive(args.master)
    try:
        if args.jeu:
            bset = ar.backup_set(args.jeu)
            set_id, what = bset["id"], f"du jeu de sauvegarde « {bset['name']} »"
            rows = ar.db.execute("SELECT COALESCE(b.phys_path, b.path) AS path, b.path AS logical, b.volume, "
                                 "s.hash, s.size, b.verified_at, b.verify_status FROM backup_copies b "
                                 "JOIN stored s ON s.path=b.path WHERE b.set_id=? ORDER BY b.volume, b.path",
                                 (set_id,)).fetchall()
        else:
            set_id, what = MAIN_SET, "de l'archive"
            rows = ar.db.execute("SELECT path, volume, hash, size, verified_at, verify_status FROM stored "
                                 "ORDER BY volume, path").fetchall()
        # Relecture complète seulement de ce qui n'a jamais été relu, de ce qui était en défaut et de ce
        # qui a été relu il y a plus d'un an ; le reste est seulement contrôlé (présence et taille). Une
        # vérification interrompue reprend donc là où elle en était, et après un nouvel import seuls
        # les nouveaux fichiers sont relus.
        fresh = set()
        if not args.rapide and not args.tout:
            limit = (dt.datetime.now() - dt.timedelta(days=REVERIFY_DAYS)).isoformat(timespec="seconds")
            fresh = {r["path"] for r in rows if r["verify_status"] == "ok" and (r["verified_at"] or "") >= limit}
        roots = ar.resolve_roots(set_id)
        names = {v["id"]: v["name"] for v in ar.volumes(set_id)}
        to_check = [r for r in rows if roots.get(r["volume"])]
        unplugged = Counter(r["volume"] for r in rows if not roots.get(r["volume"]))
        total = sum(r["size"] for r in to_check if r["path"] not in fresh)
        mode = "rapide (présence + taille)" if args.rapide else "complète (relecture + empreinte)"
        print(f"Vérification {mode} {what}")
        print(f"  {fmt_int(len(to_check))} fichiers à vérifier sur les disques branchés, {fmt_size(total)}")
        if fresh:
            print(f"  dont {fmt_int(len(fresh))} déjà relus sans défaut depuis moins d'un an : seulement "
                  f"contrôlés (présence et taille) ; --tout pour tout relire")
        log.info("=== Vérification %s %s", mode, what)
        progress = Progress(len(to_check), total)
        problems = []
        bad_vols = Counter()
        interrupted = False
        try:
            for r in to_check:
                p = os.path.join(roots[r["volume"]], to_os(r["path"]))
                status = "ok"
                try:
                    stt = os.stat(lp(p))
                    if stt.st_size != r["size"]:
                        status = "taille différente"
                    elif not args.rapide and r["path"] not in fresh:
                        if hash_file(p, progress) != r["hash"]:
                            status = "corrompu"
                except FileNotFoundError:
                    status = "manquant"
                except OSError as exc:
                    status = f"illisible : {exc}"
                if status != "ok":
                    problems.append((names.get(r["volume"], "?"), r["path"], status))
                    bad_vols[r["volume"]] += 1
                    log.error("Vérif %s [%s] : %s", r["path"], names.get(r["volume"]), status)
                if not args.rapide and (r["path"] not in fresh or status != "ok"):
                    if set_id == MAIN_SET:
                        ar.db.execute("UPDATE stored SET verified_at=?, verify_status=? WHERE path=?",
                                      (now_iso(), status, r["path"]))
                    else:
                        ar.db.execute("UPDATE backup_copies SET verified_at=?, verify_status=? "
                                      "WHERE set_id=? AND path=?", (now_iso(), status, set_id, r["logical"]))
                    ar.maybe_commit()
                progress.file_done(0 if r["path"] in fresh else r["size"])
        except KeyboardInterrupt:
            interrupted = True
        progress.finish()
        ar.db.commit()

        # Fichiers présents sur les disques mais absents du catalogue
        orphans = []
        if not interrupted:
            known = defaultdict(set)
            for r in ar.db.execute("SELECT COALESCE(phys_path, path) AS path, volume FROM backup_copies "
                                   "WHERE set_id=?", (set_id,)) if args.jeu else \
                    ar.db.execute("SELECT path, volume FROM stored"):
                known[r["volume"]].add(r["path"].lower())
            try:
                for vid, root in roots.items():
                    if root:
                        for e in walk_source(root, True, lambda rel, reason: None, skip_top=CATALOG_DIR,
                                               include_system=True, skip_archives=False):
                            if e.rel.lower() not in known[vid]:
                                orphans.append((names[vid], e.rel))
            except KeyboardInterrupt:
                interrupted = True

        # Mémorise les résultats (rapport et interface graphique)
        outcome = ("interrompu" if interrupted else "problèmes" if problems else
                   "partiel" if unplugged else "ok")
        if not args.rapide:
            if not interrupted:
                for vid, root in roots.items():
                    if root:
                        ar.db.execute("UPDATE volumes SET last_verify=?, last_verify_status=? WHERE id=?",
                                      (now_iso(), "problèmes" if bad_vols[vid] else "ok", vid))
            if set_id == MAIN_SET:
                ar.set_meta("last_verify", now_iso())
                ar.set_meta("last_verify_status", outcome)
            else:
                ar.db.execute("UPDATE backup_sets SET last_verify=?, last_verify_status=? WHERE id=?",
                              (now_iso(), outcome, set_id))
            ar.db.commit()

        report_dir = os.path.join(ar.cat_dir, "verifications")
        os.makedirs(report_dir, exist_ok=True)
        report = os.path.join(report_dir, f"verif_{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
        _write_csv(report, ["disque", "chemin", "problème"],
                   problems + [(v, o, "présent sur le disque mais absent du catalogue") for v, o in orphans])
        print()
        print(f"  fichiers en défaut : {fmt_int(len(problems))}")
        for vname, path, status in problems[:20]:
            print(f"    ! [{vname}] {path} -> {status}")
        print(f"  fichiers non catalogués : {fmt_int(len(orphans))}"
              + ("  (souvent des .partial d'une copie interrompue : sans danger)" if orphans else ""))
        for vid, n in unplugged.items():
            print(f"  NON VÉRIFIÉ : {fmt_int(n)} fichiers sur « {names.get(vid, vid)} » (disque non branché)")
        print(f"  rapport : {report}")
        if interrupted:
            print("Interrompu : vérification partielle.")
            return 130
        if problems:
            print("\nATTENTION : des fichiers sont en défaut. Restaurez-les depuis une sauvegarde "
                  "(commande `restaurer`), ou réimportez la source d'origine.")
            return 1
        if unplugged:
            print("\nOK pour les disques branchés. Branchez les autres disques et relancez pour tout vérifier.")
            return 0
        print("\nOK : tous les fichiers sont présents" + (" et intacts." if not args.rapide else "."))
        return 0
    finally:
        ar.close()


def cmd_check(args) -> int:
    with keep_awake():
        try:
            return _check(args)
        except KeyboardInterrupt:
            print("\nContrôle interrompu.")
            return 130


def _check(args) -> int:
    ar = Archive(args.master)
    try:
        root = normalize_dir(args.source)
        label = validate_label(args.label)
        if not ar.db.execute("SELECT 1 FROM sources WHERE label=?", (label,)).fetchone():
            raise UserError(f"Source « {label} » inconnue du catalogue.")
        print(f"Contrôle de {root} (label « {label} »){' en profondeur' if args.profond else ''}")
        roots = ar.resolve_roots(MAIN_SET) if args.profond else {}
        walk_problems = []

        def on_skip(rel, reason):
            if reason.startswith(("dossier illisible", "illisible")):
                walk_problems.append((rel, reason))

        entries = walk_source(root, args.inclure_corbeille, on_skip, include_system=args.inclure_systeme)
        total = sum(e.size for e in entries)
        progress = Progress(len(entries), total)
        problems = list(walk_problems)
        not_reread = 0
        for e in entries:
            row = ar.occurrence(label, e.rel)
            if row is None:
                problems.append((e.rel, "jamais importé"))
            elif row["status"] not in ("copied", "duplicate"):
                problems.append((e.rel, f"statut « {row['status']} » {row['error'] or ''}".strip()))
            elif row["size"] != e.size or row["mtime_ns"] != e.mtime_ns:
                problems.append((e.rel, "modifié depuis l'import"))
            else:
                sto = ar.stored_row(row["stored_path"])
                if sto is None:
                    problems.append((e.rel, "absent du stockage"))
                elif sto["verify_status"] and sto["verify_status"] != "ok":
                    problems.append((e.rel, f"copie dans l'archive en défaut : {sto['verify_status']}"))
                elif args.profond:
                    try:
                        if hash_file(os.path.join(root, to_os(e.rel)), progress) != row["hash"]:
                            problems.append((e.rel, "contenu différent de l'import"))
                        elif roots.get(sto["volume"]):
                            p = os.path.join(roots[sto["volume"]], to_os(sto["path"]))
                            if os.stat(lp(p)).st_size != sto["size"]:
                                problems.append((e.rel, "copie dans l'archive de mauvaise taille"))
                        else:
                            not_reread += 1
                    except OSError as exc:
                        problems.append((e.rel, f"illisible : {exc}"))
            progress.file_done(e.size)
        progress.finish()
        print(f"  {fmt_int(len(entries))} fichiers examinés ({fmt_size(total)})")
        if not_reread:
            print(f"  ({fmt_int(not_reread)} copies se trouvent sur des disques de l'archive non branchés : "
                  f"présence attestée par le catalogue, non relues)")
        status = "problèmes" if problems else ("ok-profond" if args.profond else "ok")
        ar.db.execute("UPDATE sources SET last_check=?, last_check_status=? WHERE label=?",
                      (now_iso(), status, label))
        ar.db.commit()
        if problems:
            report_dir = os.path.join(ar.cat_dir, "verifications")
            os.makedirs(report_dir, exist_ok=True)
            report = os.path.join(report_dir, f"controle_{sanitize_component(label)}_"
                                              f"{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
            _write_csv(report, ["chemin", "problème"], problems)
            print(f"\nNON : {fmt_int(len(problems))} fichier(s) de cette source ne sont pas (ou plus) "
                  f"garantis dans l'archive :")
            for rel, why in problems[:20]:
                print(f"    ! {rel} -> {why}")
            print(f"  liste complète : {report}")
            print("  -> Relancez `importer` sur cette source, puis recontrôlez.")
            return 1
        print(f"\nOUI : tout le contenu de « {label} » est présent dans l'archive.")
        if not args.profond:
            print("  (contrôle rapide basé sur le catalogue ; --profond relit et recompare chaque fichier)")
        return 0
    finally:
        ar.close()


def cmd_backup(args) -> int:
    with keep_awake():
        return _backup(args)


def _backup(args) -> int:
    ar = Archive(args.master)
    try:
        bset = ar.backup_set(args.jeu)
        sid, sname = bset["id"], bset["name"]
        set_vols = ar.volumes(sid)
        if not set_vols:
            raise UserError(f"Le jeu « {sname} » n'a aucun disque. Ajoutez-en un (ajouter-disque … --jeu {sname}).")
        main_roots = ar.resolve_roots(MAIN_SET)
        set_roots = ar.resolve_roots(sid)
        if not any(set_roots.values()):
            raise UserError(f"Aucun disque du jeu « {sname} » n'est branché. Branchez : "
                            + ", ".join(v["name"] for v in set_vols))
        main_names = {v["id"]: v["name"] for v in ar.volumes(MAIN_SET)}
        set_names = {v["id"]: v["name"] for v in set_vols}
        print(f"Mise à jour du jeu de sauvegarde « {sname} »")
        import classement
        renamed, pending_ren = classement.apply_backup_renames(ar, sid)
        if renamed:
            print(f"  {fmt_int(renamed)} fichiers renommés selon le classement de l'archive (sans recopie)")
        for v in set_vols:
            r = set_roots.get(v["id"])
            print(f"    {v['name']:<20} " + (f"branché ({r}) — {fmt_size(volume_free(r))} libres" if r
                                             else "non branché"))

        rows = ar.db.execute(
            "SELECT s.path, s.volume AS src_vol, s.hash, s.size, b.volume AS bk_vol, b.phys_path FROM stored s "
            "LEFT JOIN backup_copies b ON b.set_id=? AND b.path=s.path ORDER BY s.path", (sid,)).fetchall()
        group_pref = {}
        for r in ar.db.execute("SELECT path, volume FROM backup_copies WHERE set_id=?", (sid,)):
            group_pref.setdefault(r["path"].split("/")[0], r["volume"])
        alloc = Allocator(ar, sid, set_roots)
        group_todo = Counter()   # taille restant à copier par groupe (= dossier de premier niveau)
        for r in rows:
            if not r["bk_vol"]:
                group_todo[r["path"].split("/")[0]] += r["size"]
        log.info("=== Sauvegarde vers le jeu %s", sname)

        progress = Progress(len(rows), sum(r["size"] for r in rows))
        copied = copied_b = ok_existing = 0
        bk_unplugged, src_unplugged = Counter(), Counter()
        no_space_n = no_space_b = 0
        problems = []
        interrupted = False
        try:
            for r in rows:
                group = r["path"].split("/")[0]
                prefer = ()
                if r["bk_vol"]:
                    broot = set_roots.get(r["bk_vol"])
                    if not broot or r["phys_path"]:   # disque absent, ou renommage en attente
                        bk_unplugged[r["bk_vol"]] += 1
                        progress.file_done(r["size"])
                        continue
                    dst = os.path.join(broot, to_os(r["path"]))
                    try:
                        good = os.stat(lp(dst)).st_size == r["size"]
                        if good and args.profond:
                            good = hash_file(dst, progress) == r["hash"]
                    except OSError:
                        good = False
                    if good:
                        ok_existing += 1
                        progress.file_done(r["size"])
                        continue
                    prefer = (r["bk_vol"],)       # copie absente ou abîmée : on la refait
                else:
                    gp = group_pref.get(group)
                    prefer = (gp,) if gp else ()
                sroot = main_roots.get(r["src_vol"])
                if not sroot:
                    src_unplugged[r["src_vol"]] += 1
                    progress.file_done(r["size"])
                    continue
                src = os.path.join(sroot, to_os(r["path"]))
                done = False
                for _attempt in range(1):   # un seul tour : « break » abandonne ce fichier
                    vid, vroot = alloc.pick(group, r["size"], prefer, group_todo.get(group))
                    if not vid:
                        break
                    dst = os.path.join(vroot, to_os(r["path"]))

                    def on_fail(exc, r=r, vid=vid):   # écriture échouée, découverte plus tard
                        nonlocal copied, copied_b
                        if is_disk_full(exc):
                            alloc.mark_full(vid)
                        ar.db.execute("DELETE FROM backup_copies WHERE set_id=? AND path=?", (sid, r["path"]))
                        copied -= 1
                        copied_b -= r["size"]
                        problems.append((r["path"], f"écriture impossible : {type(exc).__name__}: {exc}"))
                        log.error("Sauvegarde %s : %s", *problems[-1])

                    try:
                        h = copy_async(ar.writer(), src, dst, progress, on_fail, expect=r["hash"])
                    except OSError as exc:
                        problems.append((r["path"], f"{type(exc).__name__}: {exc}"))
                        break
                    if h != r["hash"]:
                        problems.append((r["path"], "le fichier de l'ARCHIVE ne correspond plus à son "
                                                    "empreinte (corrompu ?) — lancez une vérification"))
                        break
                    # Le fichier de l'archive vient d'être relu en entier et son empreinte est bonne :
                    # c'est une vérification, inutile de le relire à l'étape « Vérifier l'archive ».
                    ar.db.execute("UPDATE stored SET verified_at=?, verify_status='ok' WHERE path=?",
                                  (now_iso(), r["path"]))
                    ar.db.execute("INSERT INTO backup_copies(set_id,path,volume,size,copied_at) VALUES(?,?,?,?,?) "
                                  "ON CONFLICT(set_id,path) DO UPDATE SET volume=excluded.volume, "
                                  "size=excluded.size, copied_at=excluded.copied_at, verified_at=NULL, "
                                  "verify_status=NULL", (sid, r["path"], vid, r["size"], now_iso()))
                    group_pref[group] = vid
                    copied += 1
                    copied_b += r["size"]
                    done = True
                    break
                if not done and not (problems and problems[-1][0] == r["path"]):
                    no_space_n += 1
                    no_space_b += r["size"]
                if problems and problems[-1][0] == r["path"]:
                    log.error("Sauvegarde %s : %s", *problems[-1])
                progress.file_done(r["size"])
                ar.maybe_commit()
        except KeyboardInterrupt:
            interrupted = True
        progress.finish()
        ar.commit()   # attend la fin des écritures : leurs erreurs entrent dans le bilan

        n_copies = ar.sync_catalog_copies()
        outcome = ("interrompu" if interrupted else "problèmes" if problems else
                   "incomplet" if (src_unplugged or no_space_n) else "ok")
        ar.db.execute("UPDATE backup_sets SET last_sync=?, last_sync_status=? WHERE id=?",
                      (now_iso(), outcome, sid))
        ar.db.commit()
        backlog_n, backlog_b = _set_backlog(ar, sid)

        print()
        print(f"  copiés maintenant : {fmt_int(copied)} ({fmt_size(copied_b)})  |  "
              f"déjà à jour : {fmt_int(ok_existing)}  |  problèmes : {fmt_int(len(problems))}")
        for path, why in problems[:20]:
            print(f"    ! {path} -> {why}")
        for vid, n in bk_unplugged.items():
            print(f"  (copies sur « {set_names[vid]} », non branché : {fmt_int(n)} fichiers non contrôlés)")
        if src_unplugged:
            print("  À COPIER PLUS TARD — disques de l'archive non branchés :")
            for vid, n in src_unplugged.items():
                print(f"    {main_names.get(vid, vid)} : {fmt_int(n)} fichiers")
        if no_space_n:
            print(f"  PLUS DE PLACE : {fmt_int(no_space_n)} fichiers ({fmt_size(no_space_b)}) n'ont pas pu être copiés.")
            print(f"    -> {ar.no_space_message(sid, 0, set_roots)}")
        print(f"  copie de secours du catalogue mise à jour sur {n_copies} disque(s) branché(s)")
        if interrupted:
            print("Interrompu. Relancez la même commande pour terminer.")
            return 130
        if problems:
            return 1
        if backlog_n:
            print(f"\nINCOMPLET : il reste {fmt_int(backlog_n)} fichiers ({fmt_size(backlog_b)}) à sauvegarder.")
            return 0
        print(f"\nOK : le jeu « {sname} » contient une copie vérifiée de toute l'archive.")
        return 0
    finally:
        ar.close()


def cmd_restore(args) -> int:
    with keep_awake():
        return _restore(args)


def _restore(args) -> int:
    """Reconstruit un disque de l'archive (mort ou remplacé) à partir des jeux de sauvegarde."""
    ar = Archive(args.master)
    try:
        vol = ar.volume_by_name(args.disque)
        if vol["set_id"] != MAIN_SET:
            raise UserError("Seuls les disques de l'archive (ARCHIVE-n) se restaurent ; pour un disque de "
                            "sauvegarde perdu, ajoutez un nouveau disque au jeu puis lancez `sauvegarder`.")
        dst_root = normalize_dir(args.vers)
        m = read_marker(dst_root)
        if m and m.get("volume_id") != vol["id"]:
            raise UserError(f"{dst_root} est déjà le disque « {m.get('name')} ».")
        if not m and not dir_is_empty(dst_root):
            raise UserError(f"{dst_root} n'est pas vide.")
        if vol["id"] != ar.primary_id:
            os.makedirs(dst_root, exist_ok=True)
            vname, serial, _ = volume_info(dst_root)
            ar.db.execute("UPDATE volumes SET root=?, subpath=?, volume_serial=?, volume_name=?, last_seen=? "
                          "WHERE id=?", (dst_root, subpath_of(dst_root), serial, vname, now_iso(), vol["id"]))
            write_marker(dst_root, ar.archive_id, ar.volume(vol["id"]))
            ar.db.commit()
        elif not same_path(dst_root, ar.root):
            raise UserError("Pour ARCHIVE-1, utilisez d'abord `reparer-catalogue`, puis restaurez avec "
                            "--vers égal au dossier indiqué par -m.")
        sets = ar.db.execute("SELECT id, name FROM backup_sets").fetchall()
        if args.jeu:
            sets = [ar.backup_set(args.jeu)]
        set_roots = {s["id"]: ar.resolve_roots(s["id"]) for s in sets}
        vnames = {v["id"]: v["name"] for v in ar.all_volumes()}
        rows = ar.db.execute("SELECT path, hash, size FROM stored WHERE volume=? ORDER BY path",
                             (vol["id"],)).fetchall()
        print(f"Restauration de « {vol['name']} » vers {dst_root} : {fmt_int(len(rows))} fichiers")
        progress = Progress(len(rows), sum(r["size"] for r in rows))
        restored = present = 0
        missing = Counter()
        problems = []
        interrupted = False
        try:
            for r in rows:
                dst = os.path.join(dst_root, to_os(r["path"]))
                try:
                    if os.stat(lp(dst)).st_size == r["size"] and (not args.profond or hash_file(dst) == r["hash"]):
                        present += 1
                        progress.file_done(r["size"])
                        continue
                except OSError:
                    pass
                copies = ar.db.execute("SELECT set_id, volume, COALESCE(phys_path, path) AS bpath "
                                       "FROM backup_copies WHERE path=?", (r["path"],)).fetchall()
                ok = False
                for c in copies:
                    broot = set_roots.get(c["set_id"], {}).get(c["volume"])
                    if not broot:
                        continue
                    try:
                        h = copy_with_hash(os.path.join(broot, to_os(c["bpath"])), dst, progress)
                    except OSError as exc:
                        problems.append((r["path"], f"{vnames[c['volume']]} : {exc}"))
                        continue
                    if h == r["hash"]:
                        ok = True
                        break
                    os.remove(lp(dst))
                    problems.append((r["path"], f"copie abîmée sur {vnames[c['volume']]}"))
                if ok:
                    restored += 1
                    ar.db.execute("UPDATE stored SET verified_at=?, verify_status='ok' WHERE path=?",
                                  (now_iso(), r["path"]))
                else:
                    unplugged = [vnames[c["volume"]] for c in copies
                                 if not set_roots.get(c["set_id"], {}).get(c["volume"])]
                    missing[", ".join(unplugged) or "AUCUNE COPIE"] += 1
                progress.file_done(r["size"])
                ar.maybe_commit()
        except KeyboardInterrupt:
            interrupted = True
        progress.finish()
        ar.db.commit()
        ar.sync_catalog_copies()
        print(f"\n  restaurés : {fmt_int(restored)}  |  déjà présents : {fmt_int(present)}  |  "
              f"problèmes : {fmt_int(len(problems))}")
        for path, why in problems[:20]:
            print(f"    ! {path} -> {why}")
        if missing:
            print("  NON RESTAURÉS (copie sur un disque de sauvegarde non branché) :")
            for where, n in missing.items():
                print(f"    {fmt_int(n)} fichiers — à brancher : {where}")
        if interrupted:
            print("Interrompu. Relancez la même commande pour continuer.")
            return 130
        return 0 if not missing and not problems else 1
    finally:
        ar.close()


def cmd_repair_catalog(args) -> int:
    """ARCHIVE-1 perdu : recrée un disque principal à partir d'une copie de secours du catalogue."""
    copy_path = os.path.abspath(args.copie)
    if not os.path.isfile(copy_path):
        raise UserError(f"Copie introuvable : {copy_path}")
    dst = normalize_dir(args.vers)
    if os.path.exists(os.path.join(dst, CATALOG_DIR, DB_NAME)):
        raise UserError(f"{dst} contient déjà un catalogue.")
    if not dir_is_empty(dst):
        raise UserError(f"{dst} n'est pas vide.")
    os.makedirs(os.path.join(dst, CATALOG_DIR), exist_ok=True)
    shutil.copy2(copy_path, os.path.join(dst, CATALOG_DIR, DB_NAME))
    ar = Archive(dst)   # met à jour l'emplacement d'ARCHIVE-1 et écrit son fichier d'identité
    try:
        ar.record_master_location()
        ar.install_tool_copy()
        print(f"Catalogue réinstallé dans {dst} (copie du {dt.datetime.fromtimestamp(os.path.getmtime(copy_path)):%d/%m/%Y %H:%M}).")
        print("Étapes suivantes :")
        print(f"  1. python archive.py restaurer -m \"{dst}\" --disque ARCHIVE-1 --vers \"{dst}\"")
        print("  2. Les imports faits APRÈS la date de cette copie ne sont pas connus : relancez l'import "
              "des disques sources concernés.")
    finally:
        ar.close()
    return 0


# --------------------------------------------------------------------------- #
# Ligne de commande
# --------------------------------------------------------------------------- #

EPILOG = r"""
Exemples (Windows) :
  python archive.py init F:\ArchiveFamiliale
  python archive.py ajouter-disque G:\ArchiveFamiliale -m F:\ArchiveFamiliale
  python archive.py scanner   E:\ -m F:\ArchiveFamiliale -l "Disque01-WD-bleu" --note "bureau"
  python archive.py importer  E:\ -m F:\ArchiveFamiliale -l "Disque01-WD-bleu"
  python archive.py rapport       -m F:\ArchiveFamiliale
  python archive.py controler E:\ -m F:\ArchiveFamiliale -l "Disque01-WD-bleu"
  python archive.py verifier      -m F:\ArchiveFamiliale
  python archive.py ajouter-disque H:\ArchiveFamiliale -m F:\ArchiveFamiliale --jeu Sauvegarde-A
  python archive.py sauvegarder   -m F:\ArchiveFamiliale --jeu Sauvegarde-A
  python archive.py verifier      -m F:\ArchiveFamiliale --jeu Sauvegarde-A
  python archive.py exporter      -m F:\ArchiveFamiliale

Astuce : définissez ARCHIVE_MAITRE=F:\ArchiveFamiliale pour ne plus taper -m.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="archive.py",
        description="Consolidation et déduplication d'archives familiales (photos, vidéos, documents).",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMANDE")

    def master_opt(sp):
        sp.add_argument("-m", "--maitre", dest="master", default=os.environ.get("ARCHIVE_MAITRE"),
                        help="dossier du disque ARCHIVE-1 (défaut : variable ARCHIVE_MAITRE)")

    sp = sub.add_parser("init", help="créer une archive (son premier disque, ARCHIVE-1)")
    sp.add_argument("master", metavar="DOSSIER")
    sp.add_argument("--forcer", action="store_true", help="accepter un dossier non vide")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("ajouter-disque", help="ajouter un disque à l'archive, ou à un jeu de sauvegarde")
    sp.add_argument("dossier", metavar="DOSSIER", help="dossier vide sur le nouveau disque, ex. G:\\ArchiveFamiliale")
    master_opt(sp)
    sp.add_argument("--jeu", help="nom du jeu de sauvegarde (créé s'il n'existe pas) ; sinon disque d'archive")
    sp.add_argument("--meme-disque", action="store_true",
                    help="autoriser un disque physique déjà utilisé (tests uniquement)")
    sp.add_argument("--accepter-disque-source", action="store_true",
                    help="autoriser un disque qui est aussi un ancien disque source (ex. disque interne d'un PC)")
    sp.set_defaults(func=cmd_add_volume)

    for name, copy, hlp in (("scanner", False, "inventorier une source (empreintes, AUCUNE copie)"),
                            ("importer", True, "copier dans l'archive le contenu nouveau d'une source")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("source", metavar="SOURCE", help="racine du disque ou dossier source, ex. E:\\")
        master_opt(sp)
        sp.add_argument("-l", "--label", required=True,
                        help="nom unique et stable de la source, ex. \"Disque07-WD-bleu\"")
        sp.add_argument("--note", help="description libre (où était le disque, couleur…)")
        sp.add_argument("--inclure-corbeille", action="store_true",
                        help="inclure les corbeilles ($RECYCLE.BIN, .Trashes…)")
        sp.add_argument("--inclure-systeme", action="store_true",
                        help="sur un disque Windows/macOS, prendre aussi le système, les programmes, AppData")
        sp.add_argument("--forcer", action="store_true",
                        help="réutiliser un label déjà associé à un autre numéro de volume")
        sp.add_argument("--ordre-dossiers", action="store_true",
                        help="lire dossier par dossier au lieu de suivre l'emplacement des fichiers sur le disque")
        sp.set_defaults(func=lambda a, c=copy: cmd_ingest(a, c))

    sp = sub.add_parser("option", help="réglages de l'archive (ex. ne pas faire de sauvegarde)")
    master_opt(sp)
    sp.add_argument("--sauvegardes", choices=["oui", "non"],
                    help="« non » : pas de jeu de sauvegarde, l'archive est la seule copie (déconseillé)")
    sp.set_defaults(func=cmd_option)

    sp = sub.add_parser("estimer", help="estimation rapide de ce que des disques apporteraient (rien n'est lu "
                                        "ni enregistré : noms et tailles seulement)")
    sp.add_argument("sources", nargs="+", metavar="SOURCE", help="disques ou dossiers à estimer")
    master_opt(sp)
    sp.set_defaults(func=cmd_estimate)

    sp = sub.add_parser("bilan", help="ce que contient l'archive : photos, vidéos, documents… et leurs périodes")
    master_opt(sp)
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("rapport", help="état des disques, des sources et des sauvegardes")
    master_opt(sp)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("exporter", help="exporter inventaire, doublons, erreurs, sauvegardes en CSV")
    master_opt(sp)
    sp.add_argument("--dossier", help="dossier de sortie (défaut : _catalogue/exports/<date>)")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("verifier", help="relire l'archive (ou un jeu de sauvegarde) et vérifier chaque empreinte")
    master_opt(sp)
    sp.add_argument("--jeu", help="vérifier ce jeu de sauvegarde au lieu de l'archive")
    sp.add_argument("--rapide", action="store_true", help="présence et taille seulement (sans relecture)")
    sp.add_argument("--tout", action="store_true",
                    help="relire tous les fichiers, même ceux relus sans défaut depuis moins d'un an")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("controler", help="tout le contenu de cette source est-il dans l'archive ?")
    sp.add_argument("source", metavar="SOURCE")
    master_opt(sp)
    sp.add_argument("-l", "--label", required=True)
    sp.add_argument("--profond", action="store_true", help="relire et recomparer chaque fichier source")
    sp.add_argument("--inclure-corbeille", action="store_true")
    sp.add_argument("--inclure-systeme", action="store_true")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("sauvegarder", help="copier dans un jeu de sauvegarde ce qui lui manque")
    master_opt(sp)
    sp.add_argument("--jeu", required=True, help="nom du jeu de sauvegarde, ex. Sauvegarde-A")
    sp.add_argument("--profond", action="store_true", help="relire aussi les copies déjà présentes")
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("classer", help="classer l'archive par type / date / événement (simulation par défaut)")
    master_opt(sp)
    sp.add_argument("--modele", required=True, choices=["A", "B", "C", "a", "b", "c"],
                    help="A : type + date + événement ; B : tout chronologique ; C : type + date seule")
    sp.add_argument("--appliquer", action="store_true", help="déplacer réellement les fichiers")
    sp.set_defaults(func=lambda a: __import__("classement").cmd_classify(a))

    sp = sub.add_parser("annuler-classement", help="remettre les fichiers là où ils étaient avant le dernier classement")
    master_opt(sp)
    sp.set_defaults(func=lambda a: __import__("classement").cmd_undo(a))

    sp = sub.add_parser("restaurer", help="reconstruire un disque de l'archive à partir des sauvegardes")
    master_opt(sp)
    sp.add_argument("--disque", required=True, help="nom du disque à reconstruire, ex. ARCHIVE-2")
    sp.add_argument("--vers", required=True, help="dossier vide sur le disque de remplacement")
    sp.add_argument("--jeu", help="n'utiliser que ce jeu de sauvegarde")
    sp.add_argument("--profond", action="store_true", help="relire les fichiers déjà présents")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("reparer-catalogue", help="ARCHIVE-1 perdu : repartir d'une copie de secours du catalogue")
    sp.add_argument("--copie", required=True, help=f"fichier {CATALOG_DIR}\\{CATALOG_COPY_NAME} d'un autre disque")
    sp.add_argument("--vers", required=True, help="dossier vide sur le nouveau disque principal")
    sp.set_defaults(func=cmd_repair_catalog)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UserError as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

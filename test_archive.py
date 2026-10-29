"""Tests de bout en bout : python -m unittest -v test_archive"""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
import zipfile

import archive
import maj
import notif

KB = 1024


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = archive.main(list(argv))
    return rc, out.getvalue()


def tree_size(root):
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if archive.CATALOG_DIR in dirnames:
            dirnames.remove(archive.CATALOG_DIR)
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:   # .partial renommé entre-temps par le thread d'écriture
                total += os.path.getsize(os.path.join(dirpath, f.removesuffix(".partial")))
    return total


ORDER_BY_DISK_POSITION = archive.order_by_disk_position


class Base(unittest.TestCase):
    def setUp(self):
        # L'ordre physique sur le disque est imprévisible : les tests gardent l'ordre des dossiers,
        # pour savoir lequel de deux fichiers identiques est copié (l'autre devient un doublon).
        archive.order_by_disk_position = lambda root, entries, skip: entries
        self.tmp = tempfile.mkdtemp(prefix="archtest_")
        self.master = os.path.join(self.tmp, "maitre")
        self.src1 = os.path.join(self.tmp, "disque1")
        self.src2 = os.path.join(self.tmp, "disque2")
        # Disque 1 : photos + un doublon interne + fichiers système + bundle Photos
        write(os.path.join(self.src1, "Photos", "2009", "IMG_001.JPG"), b"photo-1" * 1000)
        write(os.path.join(self.src1, "Photos", "2009", "IMG_002.JPG"), b"photo-2" * 1000)
        write(os.path.join(self.src1, "Copie", "IMG_001.JPG"), b"photo-1" * 1000)   # doublon
        write(os.path.join(self.src1, "Photos", "Thumbs.db"), b"x")                   # ignoré
        write(os.path.join(self.src1, "$RECYCLE.BIN", "old.jpg"), b"corbeille")      # ignoré
        write(os.path.join(self.src1, "Bibli.photoslibrary", "originals", "a.jpg"), b"photo-2" * 1000)
        write(os.path.join(self.src1, "Docs", "vide.txt"), b"")
        # Disque 2 : backup partiel du disque 1 + un fichier nouveau
        write(os.path.join(self.src2, "Sauvegarde", "IMG_001.JPG"), b"photo-1" * 1000)
        write(os.path.join(self.src2, "Sauvegarde", "Vacances.mp4"), b"video" * 5000)
        self.assertEqual(run("init", self.master)[0], 0)

    def tearDown(self):
        archive.order_by_disk_position = ORDER_BY_DISK_POSITION
        shutil.rmtree(self.tmp, ignore_errors=True)

    def db(self):
        con = sqlite3.connect(os.path.join(self.master, "_catalogue", "catalogue.sqlite"))
        con.row_factory = sqlite3.Row
        return con

    def q(self, sql, *params):
        with contextlib.closing(self.db()) as con:
            return con.execute(sql, params).fetchall()

    def stored_paths(self):
        return sorted(r[0] for r in self.q("SELECT path FROM stored"))


class SingleDiskTest(Base):
    def test_import_dedup_and_resume(self):
        rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stored_paths(), sorted([
            "Disque1/Bibli.photoslibrary/originals/a.jpg",   # bundle : copié malgré le doublon
            "Disque1/Docs/vide.txt",
            "Disque1/Photos/2009/IMG_001.JPG",
            "Disque1/Photos/2009/IMG_002.JPG",
        ]))
        rc, out = run("importer", self.src2, "-m", self.master, "-l", "Disque2")
        self.assertEqual(rc, 0, out)
        self.assertIn("Disque2/Sauvegarde/Vacances.mp4", self.stored_paths())
        self.assertNotIn("Disque2/Sauvegarde/IMG_001.JPG", self.stored_paths())
        src = os.stat(os.path.join(self.src2, "Sauvegarde", "Vacances.mp4")).st_mtime_ns
        dst = os.stat(os.path.join(self.master, "Disque2", "Sauvegarde", "Vacances.mp4")).st_mtime_ns
        self.assertEqual(src, dst)   # dates conservées
        rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        self.assertEqual(rc, 0)
        self.assertIn("déjà traités (reprise)        : 5", out)
        skipped = {r[0] for r in self.q("SELECT relpath FROM skipped")}
        self.assertIn("Photos/Thumbs.db", skipped)
        self.assertIn("$RECYCLE.BIN/", skipped)

    def test_scan_then_import_reuses_hashes(self):
        self.assertEqual(run("scanner", self.src1, "-m", self.master, "-l", "Disque1")[0], 0)
        self.assertEqual(self.stored_paths(), [])
        calls = []
        orig = archive.hash_file
        archive.hash_file = lambda *a, **k: calls.append(a[0]) or orig(*a, **k)
        try:
            self.assertEqual(run("importer", self.src1, "-m", self.master, "-l", "Disque1")[0], 0)
        finally:
            archive.hash_file = orig
        self.assertEqual(calls, [])   # aucune relecture pour calculer un hash
        self.assertEqual(len(self.stored_paths()), 4)

    def test_same_size_new_file_read_once(self):
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        src3 = os.path.join(self.tmp, "disque3")
        write(os.path.join(src3, "IMG_009.JPG"), b"photo-9" * 1000)   # même taille qu'IMG_001
        calls = []
        orig = archive.hash_file
        archive.hash_file = lambda *a, **k: calls.append(a[0]) or orig(*a, **k)
        try:
            self.assertEqual(run("importer", src3, "-m", self.master, "-l", "Disque3")[0], 0)
        finally:
            archive.hash_file = orig
        self.assertEqual(calls, [])   # lu une seule fois, en mémoire
        with open(os.path.join(self.master, "Disque3", "IMG_009.JPG"), "rb") as f:
            self.assertEqual(f.read(), b"photo-9" * 1000)

    def test_disk_position_order(self):
        entries = archive.walk_source(self.src1, False, lambda *a: None)
        ordered = ORDER_BY_DISK_POSITION(self.src1, entries, set())
        self.assertEqual(sorted(e.rel for e in ordered), sorted(e.rel for e in entries))
        if archive.IS_WINDOWS:
            big = os.path.join(self.src2, "Sauvegarde", "Vacances.mp4")
            self.assertIsNotNone(archive.disk_position(big))
        rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1", "--ordre-dossiers")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Ordre de lecture", out)

    def test_speed_report(self):
        big = os.path.join(self.src2, "Sauvegarde", "Film.mp4")
        write(big, os.urandom(70 * 1024 * KB))
        self.assertGreater(archive.measure_read_speed(big), 0)
        self.assertGreater(archive.measure_write_speed(self.tmp), 0)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".test-vitesse.partial")))
        old = archive.SPEED_TEST_MIN, archive.SLOW_DISK
        archive.SPEED_TEST_MIN, archive.SLOW_DISK = 0, 10 ** 15   # tout disque paraît lent
        try:
            rc, out = run("importer", self.src2, "-m", self.master, "-l", "Disque2")
        finally:
            archive.SPEED_TEST_MIN, archive.SLOW_DISK = old
        self.assertEqual(rc, 0, out)
        self.assertIn("durée estimée", out)
        self.assertIn("USB 2", out)
        self.assertEqual(os.listdir(os.path.join(self.master, "_catalogue")).count(".test-vitesse.partial"), 0)

    def test_write_failure_not_cataloged(self):
        orig = archive.copy_times

        def failing(src, dst):
            if "IMG_002" in src:
                raise OSError(5, "erreur d'écriture simulée")
            orig(src, dst)

        archive.copy_times = failing
        try:
            rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        finally:
            archive.copy_times = orig
        self.assertEqual(rc, 1, out)
        self.assertNotIn("Disque1/Photos/2009/IMG_002.JPG", self.stored_paths())
        self.assertEqual(sorted(os.listdir(os.path.join(self.master, "Disque1", "Photos", "2009"))),
                         ["IMG_001.JPG"])   # ni copie ni .partial
        rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        self.assertEqual(rc, 0, out)
        stored = set(self.stored_paths())
        for r in self.q("SELECT relpath, status, stored_path FROM occurrences WHERE label='Disque1'"):
            self.assertIn(r["status"], ("copied", "duplicate"), r["relpath"])
            self.assertIn(r["stored_path"], stored, r["relpath"])
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)

    def test_report_export(self):
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        rc, out = run("rapport", "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertIn("Disque1", out)
        self.assertIn("ARCHIVE-1", out)
        exp = os.path.join(self.tmp, "exp")
        rc, out = run("exporter", "-m", self.master, "--dossier", exp)
        self.assertEqual(rc, 0, out)
        for f in ("inventaire.csv", "stockage.csv", "doublons.csv", "ignores_et_erreurs.csv", "sauvegardes.csv"):
            self.assertTrue(os.path.exists(os.path.join(exp, f)))

    def test_verify_detects_corruption_and_missing(self):
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)
        write(os.path.join(self.master, "Disque1", "Photos", "2009", "IMG_001.JPG"), b"PHOTO-1" * 1000)
        os.remove(os.path.join(self.master, "Disque1", "Photos", "2009", "IMG_002.JPG"))
        rc, out = run("verifier", "-m", self.master)   # déjà relus : présence et taille seulement
        self.assertEqual(rc, 1)
        self.assertIn("manquant", out)
        self.assertNotIn("corrompu", out)
        rc, out = run("verifier", "-m", self.master, "--tout")
        self.assertEqual(rc, 1)
        self.assertIn("corrompu", out)
        self.assertIn("manquant", out)

    def test_quick_estimate(self):
        """Estimation rapide : rien n'est enregistré, les doublons évidents sont repérés."""
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        before = self.q("SELECT COUNT(*) FROM occurrences")[0][0]
        rc, out = run("estimer", self.src2, self.src1, "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.q("SELECT COUNT(*) FROM occurrences")[0][0], before)
        self.assertEqual(self.q("SELECT COUNT(*) FROM sources")[0][0], 1)
        rows = archive.LAST_ESTIMATE["rows"]
        self.assertEqual(archive.LAST_ESTIMATE["summary"].count["video"], 1)
        self.assertIn("Ce que contiennent ces disques", out)
        self.assertEqual(rows[0]["new"], 5 * 5000)        # la vidéo ; IMG_001.JPG est déjà là
        self.assertEqual(rows[1]["new"], 0)               # disque déjà importé : rien de nouveau

    def test_summary(self):
        """Bilan : familles de fichiers, périodes, doublons retirés."""
        import bilan
        os.utime(os.path.join(self.src1, "Docs", "vide.txt"), (1.5e9, 1.5e9))   # 2017
        write(os.path.join(self.src2, "Scans", "IMG_20050704_1.jpg"), b"vacances" * 100)
        write(os.path.join(self.src2, "Bureau", "budget.xlsx"), b"chiffres" * 100)
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        run("importer", self.src2, "-m", self.master, "-l", "Disque2")
        with contextlib.closing(self.db()) as con:
            s = bilan.from_catalog(con)
        self.assertEqual(s.count["photo"], 3)            # IMG_001, IMG_002, IMG_20050704_1 (doublons retirés)
        self.assertEqual(s.count["video"], 1)
        self.assertEqual(s.count["Tableurs"], 1)
        self.assertEqual(s.count["Textes"], 1)
        self.assertEqual(s.years["photo"][2005], 1)      # date lue dans le nom du fichier
        self.assertEqual(s.period("Textes"), (2017, 2017))
        self.assertGreater(s.seen_n, s.unique_n)
        rc, out = run("bilan", "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertIn("3  photos", out)
        self.assertIn("doublons", out)

    def test_check_source(self):
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        rc, out = run("controler", self.src1, "-m", self.master, "-l", "Disque1", "--profond")
        self.assertEqual(rc, 0, out)
        write(os.path.join(self.src1, "Nouveau.jpg"), b"nouveau")
        rc, out = run("controler", self.src1, "-m", self.master, "-l", "Disque1")
        self.assertEqual(rc, 1)
        self.assertIn("jamais importé", out)

    def test_cancel(self):
        archive.CANCEL.set()
        try:
            rc, out = run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        finally:
            archive.CANCEL.clear()
        self.assertEqual(rc, 130)
        self.assertEqual(run("importer", self.src1, "-m", self.master, "-l", "Disque1")[0], 0)

    def test_sanitize_and_collisions(self):
        self.assertEqual(archive.sanitize_component('a:b?.jpg'), "a_b_.jpg")
        self.assertEqual(archive.sanitize_component("CON.txt"), "_CON.txt")
        self.assertEqual(archive.sanitize_component("dossier. "), "dossier")
        ar = archive.Archive(self.master)
        try:
            ar.db.execute("INSERT INTO stored(path,volume,hash,size) VALUES('L/x.jpg',?,'h',1)", (ar.primary_id,))
            self.assertEqual(ar.make_dest_rel("L", "X.JPG", self.master), "L/X (2).JPG")
        finally:
            ar.close()

    def test_bad_label_and_refusals(self):
        self.assertEqual(run("importer", self.src1, "-m", self.master, "-l", "../evil")[0], 2)
        # importer le disque d'archive lui-même est refusé
        self.assertEqual(run("importer", self.master, "-m", self.master, "-l", "X")[0], 2)
        # ajouter comme disque un dossier non vide est refusé
        self.assertEqual(run("ajouter-disque", self.src1, "-m", self.master, "--meme-disque")[0], 2)


class PcDisksTest(Base):
    """Disques internes d'un PC : disque système, ancien disque Mac, disque portant l'archive."""

    def test_windows_system_disk(self):
        c = os.path.join(self.tmp, "C")
        for rel in ("Windows/System32/kernel.dll", "Program Files/App/app.exe", "ProgramData/x.dat",
                    "Users/bob/AppData/Local/cache.bin", "Users/bob/NTUSER.DAT", "Users/Default/x.txt",
                    "Windows.old/Windows/System32/old.dll", "Windows.old/Program Files/a.exe",
                    "Riot Games/jeu.pak", "Photos scannées/1990.jpg", "Users/bob/.vscode/x.json", "notes.txt"):
            write(os.path.join(c, rel), rel.encode())
        keep = ["Users/bob/Pictures/vacances.jpg", "Users/bob/Documents/lettre.doc",
                "Windows.old/Users/bob/Documents/ancien.doc"]
        for rel in keep:
            write(os.path.join(c, rel), rel.encode() * 10)
        rc, out = run("importer", c, "-m", self.master, "-l", "PC-C")
        self.assertEqual(rc, 0, out)
        self.assertIn("Installation Windows détectée", out)
        self.assertIn("Non lus (à la racine, hors des dossiers des utilisateurs) : Photos scannées, Riot Games.",
                      out)
        self.assertEqual(self.stored_paths(), sorted("PC-C/" + k for k in keep))
        # contrôle cohérent avec les mêmes exclusions
        self.assertEqual(run("controler", c, "-m", self.master, "-l", "PC-C")[0], 0)
        # --inclure-systeme : tout est pris
        rc, out = run("importer", c, "-m", self.master, "-l", "PC-C-tout", "--inclure-systeme")
        self.assertEqual(rc, 0, out)
        self.assertIn("PC-C-tout/Windows/System32/kernel.dll", self.stored_paths())

    def test_mac_disk(self):
        m = os.path.join(self.tmp, "Mac")
        for rel in ("System/Library/core", "Applications/Safari.app/x", "Library/Caches/c",
                    "private/var/log", "Users/alice/Library/Mail/m.emlx"):
            write(os.path.join(m, rel), rel.encode())
        write(os.path.join(m, "Users", "alice", "Pictures", "noel.heic"), b"noel" * 100)
        rc, out = run("importer", m, "-m", self.master, "-l", "Mac")
        self.assertEqual(rc, 0, out)
        self.assertIn("Installation macOS détectée", out)
        self.assertEqual(self.stored_paths(), ["Mac/Users/alice/Pictures/noel.heic"])

    def test_source_disk_containing_archive_disk(self):
        d = os.path.join(self.tmp, "D")
        write(os.path.join(d, "Photos", "a.jpg"), b"a" * 500)
        write(os.path.join(d, "Photos", "b.jpg"), b"b" * 500)
        vol = os.path.join(d, "ArchiveFamiliale")
        self.assertEqual(run("ajouter-disque", vol, "-m", self.master, "--meme-disque")[0], 0)
        rc, out = run("importer", d, "-m", self.master, "-l", "PC-D")
        self.assertEqual(rc, 0, out)
        self.assertIn("ARCHIVE-2 : ce dossier est ignoré", out)
        self.assertEqual(self.stored_paths(), ["PC-D/Photos/a.jpg", "PC-D/Photos/b.jpg"])
        # même si des fichiers ont été rangés dans ce dossier, une relance ne les réimporte pas
        write(os.path.join(vol, "PC-D", "Photos", "c.jpg"), b"c" * 500)
        rc, out = run("importer", d, "-m", self.master, "-l", "PC-D")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.stored_paths()), 2)
        # mais une source située DANS l'archive reste refusée
        self.assertEqual(run("importer", os.path.join(vol, "PC-D"), "-m", self.master, "-l", "X")[0], 2)

    def test_option_no_backup(self):
        rc, out = run("option", "-m", self.master, "--sauvegardes", "non")
        self.assertEqual(rc, 0, out)
        self.assertIn("par choix", run("rapport", "-m", self.master)[1])
        self.assertEqual(self.q("SELECT value FROM meta WHERE key='backup_policy'")[0][0], "aucune")
        # créer un jeu de sauvegarde réactive les sauvegardes
        run("ajouter-disque", os.path.join(self.tmp, "bk"), "-m", self.master, "--jeu", "A", "--meme-disque")
        self.assertEqual(self.q("SELECT value FROM meta WHERE key='backup_policy'"), [])


def make_jpeg(date: str, payload: bytes = b"") -> bytes:
    """JPEG minimal avec un bloc EXIF contenant DateTimeOriginal (« AAAA:MM:JJ HH:MM:SS »)."""
    import struct
    s = date.encode() + b"\0"                                  # 20 octets
    tiff = b"II*\x00" + struct.pack("<I", 8)
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x8769, 4, 1, 26) + struct.pack("<I", 0)   # IFD0
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, 20, 44) + struct.pack("<I", 0)  # EXIF
    tiff += s
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xda" + payload + b"\xff\xd9"


def make_mp4(year, month, day, payload: bytes = b"") -> bytes:
    import datetime as _dt
    import struct
    ts = int(_dt.datetime(year, month, day, 12, 0).timestamp()) + 2082844800
    mvhd = struct.pack(">I4sB3sII", 20, b"mvhd", 0, b"\0\0\0", ts, ts)
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    mdat = struct.pack(">I4s", 8 + len(payload), b"mdat") + payload
    return ftyp + mdat + moov


def make_xlsx(modified_iso: str) -> bytes:
    import zipfile as _zf
    buf = io.BytesIO()
    with _zf.ZipFile(buf, "w") as z:
        z.writestr("docProps/core.xml", f'<cp:coreProperties><dcterms:modified xsi:type="dcterms:W3CDTF">'
                                        f'{modified_iso}</dcterms:modified></cp:coreProperties>')
        z.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


class ClassementTest(Base):
    def setUp(self):
        super().setUp()
        self.s = os.path.join(self.tmp, "S")
        write(os.path.join(self.s, "Vacances Bretagne 2009", "IMG_1.JPG"), make_jpeg("2009:08:12 10:00:00", b"1"))
        write(os.path.join(self.s, "Vacances Bretagne 2009", "IMG_2.JPG"), make_jpeg("2009:08:20 10:00:00", b"2"))
        write(os.path.join(self.s, "Vacances Bretagne 2009", "IMG_1.xmp"), b"<xmp/>")
        write(os.path.join(self.s, "DCIM", "100CANON", "IMG_20150302_1.jpg"), b"\xff\xd8sans exif")
        write(os.path.join(self.s, "Mes documents", "Impots", "declaration.xlsx"), make_xlsx("2012-04-10T08:00:00Z"))
        write(os.path.join(self.s, "Musique", "Album X", "song.mp3"), b"ID3song")
        write(os.path.join(self.s, "Programmes", "setup.exe"), b"MZexe")
        write(os.path.join(self.s, "Videos", "clip.mp4"), make_mp4(2018, 6, 1, b"video"))
        rc, out = run("importer", self.s, "-m", self.master, "-l", "S")
        self.assertEqual(rc, 0, out)
        self.before = self.stored_paths()

    def classer(self, model, apply=True):
        rc, out = run("classer", "-m", self.master, "--modele", model, *(["--appliquer"] if apply else []))
        self.assertEqual(rc, 0, out)
        return out

    def assert_files_present(self, root=None):
        for (p,) in self.q("SELECT path FROM stored"):
            self.assertTrue(os.path.exists(os.path.join(root or self.master, archive.to_os(p))), p)

    def test_content_dates(self):
        import classement
        f = os.path.join(self.s, "Vacances Bretagne 2009", "IMG_1.JPG")
        self.assertEqual(classement.content_date(f, f), (2009, 8, 12))
        f = os.path.join(self.s, "Videos", "clip.mp4")
        self.assertEqual(classement.content_date(f, f), (2018, 6, 1))
        f = os.path.join(self.s, "Mes documents", "Impots", "declaration.xlsx")
        self.assertEqual(classement.content_date(f, f), (2012, 4, 10))
        self.assertEqual(classement.date_from_name("WhatsApp Image 2015-03-02 at 10.jpg"), (2015, 3, 2))
        self.assertEqual(classement.date_from_name("DSC_2009.jpg"), None)   # compteur, pas une date
        self.assertEqual(classement.event_for(["S", "Users", "bob", "Pictures", "x.jpg"]), None)
        self.assertEqual(classement.event_for(["S", "2004-12-24 Noël chez mamie", "x.jpg"]), "Noël chez mamie")

    def test_model_A_simulation_apply_undo(self):
        out = self.classer("A", apply=False)
        self.assertIn("SIMULATION", out)
        self.assertEqual(self.stored_paths(), self.before)          # rien n'a bougé
        self.classer("A")
        self.assertEqual(self.stored_paths(), sorted([
            "Photos et vidéos/2009/2009-08 Vacances Bretagne/IMG_1.JPG",
            "Photos et vidéos/2009/2009-08 Vacances Bretagne/IMG_2.JPG",
            "Photos et vidéos/2009/2009-08 Vacances Bretagne/IMG_1.xmp",   # suit sa photo
            "Photos et vidéos/2015/2015-03/IMG_20150302_1.jpg",
            "Photos et vidéos/2018/2018-06/clip.mp4",
            "Documents/Tableurs/2012/Impots/declaration.xlsx",
            "Musique/Album X/song.mp3",
            "Autres fichiers/S/Programmes/setup.exe",
        ]))
        self.assert_files_present()
        self.assertFalse(os.path.exists(os.path.join(self.master, "S")))   # dossiers vides supprimés
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)
        self.assertEqual(run("controler", self.s, "-m", self.master, "-l", "S", "--profond")[0], 0)
        # Les doublons restent détectés après le classement
        write(os.path.join(self.tmp, "S2", "copie.jpg"), make_jpeg("2009:08:12 10:00:00", b"1"))
        rc, out = run("importer", os.path.join(self.tmp, "S2"), "-m", self.master, "-l", "S2")
        self.assertIn("déjà présents (doublons)      : 1", out)
        # Annulation
        rc, out = run("annuler-classement", "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.stored_paths(), self.before)
        self.assert_files_present()
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)

    def test_models_B_and_C_and_switch(self):
        self.classer("B")
        paths = self.stored_paths()
        self.assertIn("2009/2009-08 Vacances Bretagne/IMG_1.JPG", paths)
        self.assertIn("2012/2012-04 Impots/declaration.xlsx", paths)
        self.classer("C")                                  # changement de modèle direct
        paths = self.stored_paths()
        self.assertIn("Photos/2009/2009-08/IMG_1.JPG", paths)
        self.assertIn("Vidéos/2018/2018-06/clip.mp4", paths)
        self.assertIn("Documents/Tableurs/2012/declaration.xlsx", paths)
        self.assert_files_present()
        # un fichier importé après le classement est classé à la relance, les autres ne bougent pas
        write(os.path.join(self.s, "Vacances Bretagne 2009", "IMG_3.JPG"), make_jpeg("2009:08:14 10:00:00", b"3"))
        run("importer", self.s, "-m", self.master, "-l", "S")
        out = self.classer("C")
        self.assertIn("Fichiers à déplacer : 1 ", out)
        self.assertIn("Photos/2009/2009-08/IMG_3.JPG", self.stored_paths())

    def test_backups_follow_without_recopy(self):
        bk = os.path.join(self.tmp, "bk")
        run("ajouter-disque", bk, "-m", self.master, "--jeu", "A", "--meme-disque")
        self.assertEqual(run("sauvegarder", "-m", self.master, "--jeu", "A")[0], 0)
        out = self.classer("A")                            # disque de sauvegarde branché : renommé tout de suite
        self.assertIn("renommés sur les disques branchés", out)
        self.assertEqual(run("verifier", "-m", self.master, "--jeu", "A")[0], 0)
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "A")
        self.assertIn("copiés maintenant : 0", out)
        # disque de sauvegarde débranché pendant l'annulation : renommage différé
        os.rename(bk, bk + "_x")
        run("annuler-classement", "-m", self.master)
        os.rename(bk + "_x", bk)
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "A")
        self.assertIn("renommés selon le classement", out)
        self.assertIn("copiés maintenant : 0", out)
        rc, out = run("verifier", "-m", self.master, "--jeu", "A")
        self.assertEqual(rc, 0, out)
        self.assert_files_present(bk)


class MultiDiskTest(Base):
    """Disques simulés : la place libre est calculée à partir d'une capacité fictive."""

    def setUp(self):
        super().setUp()
        self.caps = {}
        self._orig = (archive.volume_free, archive.FREE_SPACE_MARGIN, archive.PRIMARY_EXTRA_MARGIN)
        archive.FREE_SPACE_MARGIN = 0
        archive.PRIMARY_EXTRA_MARGIN = 0

        def fake_free(root):
            cap = self.caps.get(os.path.normcase(os.path.abspath(root)))
            if cap is None:
                return 10 ** 12
            return cap - tree_size(root)

        archive.volume_free = fake_free
        # 3 sources de 4 fichiers de 10 Ko chacun (contenus tous différents)
        self.srcs = []
        for s in range(3):
            d = os.path.join(self.tmp, f"src{s}")
            for i in range(4):
                write(os.path.join(d, f"f{i}.bin"), bytes([s * 10 + i]) * (10 * KB))
            self.srcs.append(d)

    def tearDown(self):
        archive.volume_free, archive.FREE_SPACE_MARGIN, archive.PRIMARY_EXTRA_MARGIN = self._orig
        super().tearDown()

    def cap(self, path, size):
        self.caps[os.path.normcase(os.path.abspath(path))] = size

    def add_disk(self, name, cap=None, jeu=None):
        p = os.path.join(self.tmp, name)
        if cap is not None:
            self.cap(p, cap)
        argv = ["ajouter-disque", p, "-m", self.master, "--meme-disque"] + (["--jeu", jeu] if jeu else [])
        rc, out = run(*argv)
        self.assertEqual(rc, 0, out)
        return p

    def per_volume(self):
        return dict(self.q("SELECT v.name, COUNT(s.path) FROM volumes v LEFT JOIN stored s ON s.volume=v.id "
                           "WHERE v.set_id='main' GROUP BY v.name"))

    def test_fill_in_order_then_next_disk(self):
        self.cap(self.master, 45 * KB)            # ARCHIVE-1 : 4 fichiers de 10 Ko
        v2 = self.add_disk("vol2", 100 * KB)
        for i, s in enumerate(self.srcs[:2]):
            rc, out = run("importer", s, "-m", self.master, "-l", f"S{i}")
            self.assertEqual(rc, 0, out)
        self.assertEqual(self.per_volume(), {"ARCHIVE-1": 4, "ARCHIVE-2": 4})
        # Chaque fichier est bien sur le disque indiqué par le catalogue
        for path, vol in self.q("SELECT s.path, v.root FROM stored s JOIN volumes v ON v.id=s.volume"):
            self.assertTrue(os.path.exists(os.path.join(vol, archive.to_os(path))), path)
        self.assertTrue(os.path.exists(os.path.join(v2, "_catalogue", "catalogue-copie.sqlite")))
        self.assertTrue(os.path.exists(os.path.join(v2, "_catalogue", "volume.json")))
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)

    def test_switch_mid_source_and_full_then_resume(self):
        self.cap(self.master, 25 * KB)            # 2 fichiers
        self.add_disk("vol2", 25 * KB)            # 2 fichiers
        rc, out = run("importer", self.srcs[0], "-m", self.master, "-l", "S0")
        self.assertEqual(rc, 0, out)
        self.assertIn("est plein : la suite va sur « ARCHIVE-2 »", out)
        rc, out = run("importer", self.srcs[1], "-m", self.master, "-l", "S1")
        self.assertEqual(rc, 3, out)              # plus de place nulle part
        self.assertIn("ajoutez un nouveau disque", out)
        self.add_disk("vol3", 100 * KB)
        rc, out = run("importer", self.srcs[1], "-m", self.master, "-l", "S1")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.per_volume(), {"ARCHIVE-1": 2, "ARCHIVE-2": 2, "ARCHIVE-3": 4})

    def test_unplugged_disk(self):
        self.cap(self.master, 45 * KB)
        v2 = self.add_disk("vol2", 100 * KB)
        run("importer", self.srcs[0], "-m", self.master, "-l", "S0")
        run("importer", self.srcs[1], "-m", self.master, "-l", "S1")
        os.rename(v2, v2 + "_debranche")         # simule un disque débranché
        rc, out = run("verifier", "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertIn("NON VÉRIFIÉ : 4 fichiers sur « ARCHIVE-2 »", out)
        # import d'une source déjà connue : les doublons sont détectés sans le disque 2
        write(os.path.join(self.tmp, "src9", "copie.bin"), bytes([10]) * (10 * KB))   # = S1/f0
        rc, out = run("importer", os.path.join(self.tmp, "src9"), "-m", self.master, "-l", "S9")
        self.assertEqual(rc, 0, out)
        self.assertIn("déjà présents (doublons)      : 1", out)
        os.rename(v2 + "_debranche", v2)
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)

    def test_backup_set_on_two_disks_verify_restore(self):
        self.cap(self.master, 45 * KB)
        v2 = self.add_disk("vol2", 100 * KB)
        for i, s in enumerate(self.srcs):
            self.assertEqual(run("importer", s, "-m", self.master, "-l", f"S{i}")[0], 0)
        self.add_disk("bkA1", 65 * KB, jeu="Sauvegarde-A")    # 6 fichiers
        self.add_disk("bkA2", 100 * KB, jeu="Sauvegarde-A")
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "Sauvegarde-A")
        self.assertEqual(rc, 0, out)
        self.assertIn("toute l'archive", out)
        per = dict(self.q("SELECT v.name, COUNT(*) FROM backup_copies b JOIN volumes v ON v.id=b.volume GROUP BY v.name"))
        self.assertEqual(per, {"Sauvegarde-A-1": 4, "Sauvegarde-A-2": 8})   # groupes gardés ensemble
        self.assertEqual(run("verifier", "-m", self.master, "--jeu", "Sauvegarde-A")[0], 0)
        # Relance : rien à copier
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "Sauvegarde-A")
        self.assertIn("copiés maintenant : 0", out)
        # Mort de ARCHIVE-2 : on le reconstruit sur un nouveau disque depuis la sauvegarde
        shutil.rmtree(v2)
        self.assertEqual(run("verifier", "-m", self.master)[0], 0)   # débranché = non vérifié
        new2 = os.path.join(self.tmp, "vol2_neuf")
        rc, out = run("restaurer", "-m", self.master, "--disque", "ARCHIVE-2", "--vers", new2)
        self.assertEqual(rc, 0, out)
        rc, out = run("verifier", "-m", self.master)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("NON VÉRIFIÉ", out)

    def test_backup_incomplete_when_set_full(self):
        for i, s in enumerate(self.srcs[:2]):
            run("importer", s, "-m", self.master, "-l", f"S{i}")
        self.add_disk("bkB1", 45 * KB, jeu="B")
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "B")
        self.assertEqual(rc, 0, out)
        self.assertIn("PLUS DE PLACE : 4 fichiers", out)
        self.assertIn("INCOMPLET", out)
        self.add_disk("bkB2", 100 * KB, jeu="B")
        rc, out = run("sauvegarder", "-m", self.master, "--jeu", "B")
        self.assertIn("toute l'archive", out)

    def test_repair_catalog_after_primary_loss(self):
        self.cap(self.master, 45 * KB)
        v2 = self.add_disk("vol2", 100 * KB)
        for i, s in enumerate(self.srcs[:2]):
            run("importer", s, "-m", self.master, "-l", f"S{i}")
        self.add_disk("bkA1", 10 ** 6, jeu="A")
        self.assertEqual(run("sauvegarder", "-m", self.master, "--jeu", "A")[0], 0)
        shutil.rmtree(self.master)                # ARCHIVE-1 détruit
        new1 = os.path.join(self.tmp, "vol1_neuf")
        copie = os.path.join(v2, "_catalogue", "catalogue-copie.sqlite")
        rc, out = run("reparer-catalogue", "--copie", copie, "--vers", new1)
        self.assertEqual(rc, 0, out)
        rc, out = run("restaurer", "-m", new1, "--disque", "ARCHIVE-1", "--vers", new1)
        self.assertEqual(rc, 0, out)
        rc, out = run("verifier", "-m", new1)
        self.assertEqual(rc, 0, out)

    def test_refuse_secondary_disk_as_master(self):
        v2 = self.add_disk("vol2")
        rc, out = run("rapport", "-m", v2)
        self.assertEqual(rc, 2)
        self.assertIn("ARCHIVE-1", out)


class GuiTest(Base):
    """L'interface s'ouvre, sans archive puis sur une archive, et réagit sans bloquer."""

    def open_app(self, keep_config=False):
        import archive_gui
        os.environ["APPDATA"] = os.path.join(self.tmp, "appdata")
        if not keep_config:
            write(os.path.join(self.tmp, "appdata", "ArchiveFamiliale", "config.json"),
                  json.dumps({"master": self.master, "verifier_maj": False}).encode())
        low = archive_gui.LOW_SPACE   # la place libre réelle de la machine ne doit pas changer l'étape conseillée
        archive_gui.LOW_SPACE = 0
        self.addCleanup(setattr, archive_gui, "LOW_SPACE", low)
        try:
            app = archive_gui.App()
        except tk.TclError as e:   # pas d'écran (serveur sans bureau)
            self.skipTest(f"pas d'affichage : {e}")
        self.addCleanup(self.close_app, app)
        app.update_idletasks()
        return app

    @staticmethod
    def close_app(app):
        with contextlib.suppress(tk.TclError):   # déjà fermée par le test
            app.destroy()

    def setUp(self):
        super().setUp()
        self._appdata = os.environ.get("APPDATA")

    def tearDown(self):
        if self._appdata is not None:
            os.environ["APPDATA"] = self._appdata
        super().tearDown()

    def test_open_with_archive(self):
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        app = self.open_app()
        self.assertEqual(app.stat["files"][0].cget("text"), "4")
        self.assertEqual(app.steps[2]["kind"], "done")
        self.assertIn("Vérifier", app.hero_title.cget("text"))
        for n in range(1, 7):
            app.select_step(n)
        app.busy = True
        app._set_activity("busy")
        app.progress["value"] = 500
        app.busy = False
        app._set_activity("ok")
        app.toggle_log(True)
        app.update_idletasks()

    def run_queue(self, app, items, until):
        """Lance une file d'import et fait tourner l'interface jusqu'à until(app) (30 s maximum)."""
        app.start_queue([{"path": p, "label": lab, "note": "", "serial": None, "size": 1000} for p, lab in items],
                        copy=True)
        end = time.monotonic() + 30
        while not until(app):
            self.assertLess(time.monotonic(), end, "la file d'import ne se termine pas")
            app.update()
            time.sleep(0.02)

    def test_import_queue(self):
        """Plusieurs disques à la suite : un disque introuvable n'arrête pas les suivants."""
        from unittest import mock
        import archive_gui
        app = self.open_app()
        with mock.patch.object(archive_gui, "messagebox") as mb:
            self.run_queue(app, [(self.src1, "Disque1"), (os.path.join(self.tmp, "absent"), "Absent"),
                                 (self.src2, "Disque2")], lambda a: a.iq is None and not a.busy)
        self.assertEqual(len(self.stored_paths()), 5)
        msg = mb.showwarning.call_args[0][1]
        self.assertIn("✅  Disque1", msg)
        self.assertIn("❌  Absent", msg)
        self.assertIn("✅  Disque2", msg)

    def test_import_queue_pauses_when_full(self):
        """Archive pleine : la file se met en pause sur le disque en cours, puis reprend."""
        from unittest import mock
        import archive_gui
        app = self.open_app()
        free = archive.volume_free
        archive.volume_free = lambda p: 0
        self.addCleanup(setattr, archive, "volume_free", free)
        with mock.patch.object(archive_gui, "messagebox") as mb:
            self.run_queue(app, [(self.src1, "Disque1"), (self.src2, "Disque2")],
                           lambda a: a.iq and a.iq["paused"] and not a.busy)
            self.assertEqual(app.iq["paused"], "plein")
            self.assertEqual([it["label"] for it in app.iq["items"]], ["Disque1", "Disque2"])
            self.assertEqual(app.hero_title.cget("text"), "L'archive est pleine")
            mb.showwarning.assert_called_once()
            archive.volume_free = free   # un disque a été ajouté : l'import reprend
            app.resume_queue()
            end = time.monotonic() + 30
            while app.iq is not None or app.busy:
                self.assertLess(time.monotonic(), end)
                app.update()
        self.assertEqual(len(self.stored_paths()), 5)
        self.assertIn("Terminé, tout s'est bien passé", mb.showinfo.call_args[0][1])

    def test_import_queue_survives_restart(self):
        """Pause, fermeture du programme (ou redémarrage du PC) : au lancement suivant, la file reprend."""
        from unittest import mock
        import archive_gui
        app = self.open_app()
        free = archive.volume_free
        archive.volume_free = lambda p: 0
        self.addCleanup(setattr, archive, "volume_free", free)
        with mock.patch.object(archive_gui, "messagebox") as mb:
            self.run_queue(app, [(self.src1, "Disque1"), (self.src2, "Disque2")],
                           lambda a: a.iq and a.iq["paused"] and not a.busy)
            app.destroy()
            archive.volume_free = free
            app = self.open_app(keep_config=True)
            self.assertEqual(app.iq["paused"], "attente")
            self.assertEqual([it["label"] for it in app.iq["items"]], ["Disque1", "Disque2"])
            self.assertEqual(app.hero_btn.cget("text"), "Démarrer l'import")
            app.resume_queue()
            end = time.monotonic() + 30
            while app.iq is not None or app.busy:
                self.assertLess(time.monotonic(), end)
                app.update()
        self.assertEqual(len(self.stored_paths()), 5)
        self.assertIn("✅  Disque2", mb.showinfo.call_args[0][1])
        self.assertNotIn("file_import", archive_gui.load_config())

    def test_plan_then_start(self):
        """Choisir les disques les met en attente ; « Démarrer » reprend d'abord ceux déjà commencés."""
        from unittest import mock
        import archive_gui
        run("importer", self.src2, "-m", self.master, "-l", "Disque2")
        with contextlib.closing(self.db()) as con:   # import de Disque2 resté incomplet
            con.execute("UPDATE sources SET completed=0")
            con.commit()
        app = self.open_app()
        app.plan_disks([{"path": p, "label": lab, "note": "", "serial": None, "size": 1000}
                        for p, lab in ((self.src1, "Disque1"), (self.src2, "Disque2"))])
        self.assertFalse(app.busy)
        self.assertEqual(app.steps[2]["kind"], "warn")
        self.assertIn("1 déjà commencé(s), repris en premier", app.steps[2]["status"].cget("text"))
        self.assertEqual(app.tree_src.set("Disque1", "etat"), "⏳ En attente (pas commencé)")
        self.assertEqual(app.hero_btn.cget("text"), "Démarrer l'import")
        self.assertEqual(str(app.btn_start.cget("state")), "normal")
        with mock.patch.object(archive_gui, "messagebox") as mb:
            app.start_import()
            end = time.monotonic() + 30
            while app.iq is not None or app.busy:
                self.assertLess(time.monotonic(), end)
                app.update()
        msg = mb.showinfo.call_args[0][1]
        self.assertLess(msg.index("Disque2"), msg.index("Disque1"))
        self.assertEqual(len(self.stored_paths()), 5)

    def test_remove_planned_and_summary_step(self):
        """« Retirer de la liste » enlève le disque sélectionné ; l'étape 7 affiche le bilan."""
        run("importer", self.src1, "-m", self.master, "-l", "Disque1")
        app = self.open_app()
        app.plan_disks([{"path": self.src2, "label": "Disque2", "note": "", "serial": None, "size": 1}])
        app.tree_src.selection_set("Disque2")
        app.remove_planned()
        self.assertIsNone(app.iq)
        self.assertFalse(app.tree_src.exists("Disque2"))
        app.select_step(7)
        end = time.monotonic() + 30
        while app.summary is None:
            self.assertLess(time.monotonic(), end)
            app.update()
            time.sleep(0.02)
        app.update_idletasks()
        kinds = [app.tree_kind.item(i, "values")[0] for i in app.tree_kind.get_children()]
        self.assertIn("Photos", kinds)
        self.assertEqual(app.steps[7]["kind"], "done")
        self.assertIn("doublons", app.steps[7]["status"].cget("text"))

    def test_archive_disks_not_importable(self):
        """Dans le choix des disques à importer, les disques de l'archive sont grisés."""
        from unittest import mock
        import archive_gui
        app = self.open_app()
        serial = self.q("SELECT volume_serial FROM volumes")[0][0]
        fake = [archive.Drive(self.master, "amovible", "Archive", "0000AAAA", "NTFS", 10, 5, 5),   # marqueur
                archive.Drive(self.tmp, "amovible", "Archive", serial, "NTFS", 10, 5, 5),          # n° de série
                archive.Drive(self.src1, "amovible", "Ancien", "0000BBBB", "NTFS", 10, 5, 5)]
        with mock.patch.object(archive, "list_drives", lambda: fake), \
                mock.patch.object(tk.Toplevel, "grab_set", lambda self: None):
            dlg = archive_gui.SourcesDialog(app, True, "Importer", "")
            dlg._check_all(True)
            self.assertEqual([p for p, r in dlg.rows.items() if r["var"].get()], [self.src1])
            self.assertFalse(dlg._remark(fake[0])[1])
            self.assertFalse(dlg._remark(fake[1])[1])
            dlg.destroy()

    def test_open_without_archive(self):
        shutil.rmtree(self.master)
        app = self.open_app()
        self.assertIsNone(app.master_path)
        self.assertEqual(app.hero_title.cget("text"), "Créer votre archive")


class NotifTest(unittest.TestCase):
    def test_send_and_links(self):
        from unittest import mock
        cfg = {"ntfy_sujet": notif.new_topic(), "ntfy_actif": True}
        n = notif.Notifier(cfg)
        self.assertRegex(n.topic, r"^archive-[a-z2-9]{12}$")
        self.assertEqual(n.app_link(), f"ntfy://ntfy.sh/{n.topic}?display=Archive+Familiale")
        sent = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout):
            sent.append(json.loads(req.data))
            return Resp(b"{}")

        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertIsNone(n.send("Titre", "Disque « é » terminé", tags=("tada",), wait=True))
            cfg["ntfy_actif"] = False
            n.send("Rien", "désactivé", wait=True)
        self.assertEqual(sent, [{"topic": n.topic, "title": "Titre", "message": "Disque « é » terminé",
                                 "priority": 3, "tags": ["tada"]}])
        with mock.patch("urllib.request.urlopen", side_effect=OSError("pas de réseau")):
            self.assertIsInstance(n.send("x", "y", force=True, wait=True), OSError)


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="majtest_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def publish(self, name, data, sha=None):
        """Simule un fichier publié (URL file://) et son .sha256."""
        p = os.path.join(self.tmp, "pub", name)
        write(p, data)
        write(p + ".sha256", ((sha or hashlib.sha256(data).hexdigest()) + "  " + name).encode())
        return {name: pathlib.Path(p).as_uri(), name + ".sha256": pathlib.Path(p + ".sha256").as_uri()}

    def release(self, assets):
        return {"version": "9.9.9", "notes": "", "page": "", "assets": assets, "sizes": {}}

    def zip_of(self, files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return buf.getvalue()

    def test_versions(self):
        self.assertTrue(maj.is_newer("v2.10.0", "2.9.3"))
        self.assertTrue(maj.is_newer("2.1.0", "2.0.0"))
        self.assertFalse(maj.is_newer("2.1.0", "2.1.0"))
        self.assertFalse(maj.is_newer("2.0.9", "2.1.0"))

    def test_download_portable(self):
        data = self.zip_of({"ArchiveFamiliale/ArchiveFamiliale.exe": b"exe",
                            "ArchiveFamiliale/_internal/lib.dll": b"dll"})
        stage, target = maj.download(self.release(self.publish(maj.ZIP_ASSET, data)), installed=False)
        try:
            with open(os.path.join(target, maj.EXE_NAME), "rb") as f:
                self.assertEqual(f.read(), b"exe")
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def test_download_installer(self):
        rel = self.release(self.publish(maj.SETUP_ASSET, b"setup"))
        stage, target = maj.download(rel, installed=True)
        try:
            self.assertTrue(target.endswith(maj.SETUP_ASSET))
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def test_download_refuses_bad_hash_and_unsafe_zip(self):
        with self.assertRaises(maj.UpdateError):
            maj.download(self.release(self.publish(maj.SETUP_ASSET, b"setup", sha="0" * 64)), installed=True)
        evil = self.zip_of({"../../dehors.exe": b"x", "ArchiveFamiliale/ArchiveFamiliale.exe": b"exe"})
        with self.assertRaises(maj.UpdateError):
            maj.download(self.release(self.publish(maj.ZIP_ASSET, evil)), installed=False)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "dehors.exe")))


if __name__ == "__main__":
    unittest.main()

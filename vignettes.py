"""Vignettes des photos pour « Nos souvenirs » (bibliothèque Pillow, facultative).

Une vignette est une petite image JPEG (THUMB_SIZE pixels au plus) rangée par empreinte du contenu :
<_catalogue>/souvenirs/v/<2 premiers caractères>/<empreinte>.jpg. La page « Nos souvenirs » de
ARCHIVE-1 les lit directement là ; celles des autres disques en reçoivent une copie.

Pour aller vite :
- pendant l'import, la photo est déjà en mémoire : Background la réduit sur les cœurs libres du
  processeur, sans relire le disque, et sans jamais ralentir l'import (s'il est en retard, il
  laisse la photo de côté : elle sera faite plus tard) ;
- beaucoup d'appareils (téléphones surtout) rangent dans la photo un aperçu déjà réduit : s'il est
  assez grand, on le prend tel quel, en ne lisant que le début du fichier ;
- sinon, le JPEG est décodé directement en taille réduite (draft), plusieurs à la fois ;
- les photos RAW (NEF, CR2, ARW, DNG…) ne se décodent pas, mais l'appareil y a rangé un aperçu
  JPEG : on lit seulement celui-là (1 à 2 Mo, au lieu des 20 à 50 Mo du fichier).
"""
from __future__ import annotations

import io
import os
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

THUMB_SIZE = 360
EMBEDDED_MIN = 300          # aperçu intégré accepté s'il fait au moins cette largeur (ou hauteur)
HEAD_BYTES = 256 * 1024     # début du fichier lu pour y chercher l'aperçu intégré
RAW_EXTS = {"nef", "nrw", "cr2", "arw", "srf", "sr2", "dng", "orf", "pef", "rw2", "raf", "srw", "erf", "kdc",
            "3fr", "mef", "mos", "iiq"}
EXTS = {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "tif", "tiff", "webp"} | RAW_EXTS
JPEG_EXTS = {"jpg", "jpeg", "jpe", "jfif"}
CACHE_PARTS = ("souvenirs", "v")   # sous le dossier _catalogue


def available() -> bool:
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


def workers() -> int:
    """Cœurs à utiliser : tous sauf deux (lecture, écriture, interface), entre 1 et 6."""
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name.rsplit("/", 1)[-1] else ""


def wanted(name: str) -> bool:
    return ext_of(name) in EXTS


# --------------------------------------------------------------------------- #
# Aperçu intégré (EXIF, IFD1) : JPEG déjà réduit, et orientation de la photo
# --------------------------------------------------------------------------- #

def _exif_block(head: bytes):
    """Contenu du segment APP1 « Exif » d'un JPEG (en-tête TIFF), ou None."""
    if head[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(head):
        if head[i] != 0xFF:
            return None
        marker = head[i + 1]
        if marker in (0xD9, 0xDA):   # fin d'image, début des données : plus d'en-têtes
            return None
        length = struct.unpack(">H", head[i + 2:i + 4])[0]
        if marker == 0xE1 and head[i + 4:i + 10] == b"Exif\0\0":
            return head[i + 10:i + 2 + length]
        i += 2 + length
    return None


def embedded_preview(head: bytes):
    """(octets du JPEG d'aperçu, orientation EXIF) lus dans le début d'une photo, ou (None, 1)."""
    tiff = _exif_block(head)
    if not tiff or len(tiff) < 8:
        return None, 1
    bo = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if not bo:
        return None, 1

    def ifd(off):
        if off < 8 or off + 2 > len(tiff):
            return {}, 0
        n = struct.unpack(bo + "H", tiff[off:off + 2])[0]
        tags = {}
        for k in range(n):
            p = off + 2 + 12 * k
            if p + 12 > len(tiff):
                break
            tag, typ, _count = struct.unpack(bo + "HHI", tiff[p:p + 8])
            val = struct.unpack(bo + ("H" if typ == 3 else "I"), tiff[p + 8:p + (10 if typ == 3 else 12)])[0]
            tags[tag] = val
        p = off + 2 + 12 * n
        nxt = struct.unpack(bo + "I", tiff[p:p + 4])[0] if p + 4 <= len(tiff) else 0
        return tags, nxt

    try:
        ifd0, ifd1_off = ifd(struct.unpack(bo + "I", tiff[4:8])[0])
        orientation = ifd0.get(0x0112, 1)
        ifd1, _ = ifd(ifd1_off)
        off, length = ifd1.get(0x0201), ifd1.get(0x0202)
        if off and length and off + length <= len(tiff):
            data = tiff[off:off + length]
            if data[:2] == b"\xff\xd8":
                return data, orientation
        return None, orientation
    except struct.error:
        return None, 1


# --------------------------------------------------------------------------- #
# Photos RAW : l'aperçu JPEG que l'appareil a rangé dans le fichier
# --------------------------------------------------------------------------- #

RAW_PREVIEW_MAX = 16 * 1024 * 1024   # un « aperçu » plus gros est sans doute l'image brute elle-même


def _raw_previews(f):
    """([(position, longueur)] des JPEG rangés dans un fichier RAW, orientation EXIF). Suit la
    structure TIFF (IFD0 et suivants, sous-IFD) ; RAF (Fujifilm) a son propre en-tête."""
    f.seek(0)
    head = f.read(160)
    if head.startswith(b"FUJIFILM") and len(head) >= 92:
        off, length = struct.unpack(">II", head[84:92])
        f.seek(off)
        inner = f.read(min(length, HEAD_BYTES))
        tiff = _exif_block(inner)
        orientation = _tiff_orientation(tiff) if tiff else 1
        return [(off, length)], orientation
    bo = {b"II": "<", b"MM": ">"}.get(head[:2])
    if not bo or struct.unpack(bo + "H", head[2:4])[0] not in (42, 0x4F52, 0x5352, 0x55):   # TIFF, ORF, RW2
        return [], 1
    found, seen, todo, orientation = [], set(), [struct.unpack(bo + "I", head[4:8])[0]], 1
    size = f.seek(0, 2)
    while todo and len(seen) < 32:
        off = todo.pop(0)
        if not off or off in seen or (size and off >= size):
            continue
        seen.add(off)
        f.seek(off)
        raw = f.read(2)
        if len(raw) < 2:
            continue
        n = struct.unpack(bo + "H", raw)[0]
        if n > 500:
            continue
        body = f.read(12 * n + 4)
        tags = {}
        for k in range(min(n, len(body) // 12)):
            tag, typ, count = struct.unpack(bo + "HHI", body[12 * k:12 * k + 8])
            val = body[12 * k + 8:12 * k + 12]
            tags[tag] = (typ, count, val)

        def num(tag):
            typ, count, val = tags[tag]
            return struct.unpack(bo + ("H" if typ == 3 else "I"), val[:2] if typ == 3 else val)[0]
        if 0x0112 in tags and orientation == 1:
            orientation = num(0x0112)
        if 0x0201 in tags and 0x0202 in tags:
            found.append((num(0x0201), num(0x0202)))
        if 0x002E in tags and tags[0x002E][0] == 7:   # RW2 (Panasonic) : JPEG rangé dans une étiquette
            typ, count, val = tags[0x002E]
            found.append((struct.unpack(bo + "I", val)[0], count))
        if tags.get(0x0103, (0, 0, b""))[0] and num(0x0103) in (6, 7) and 0x0111 in tags and 0x0117 in tags \
                and tags[0x0111][1] == 1:   # une seule bande compressée en JPEG (CR2, DNG…)
            found.append((num(0x0111), num(0x0117)))
        if 0x014A in tags:   # sous-IFD (NEF, DNG, ARW…)
            typ, count, val = tags[0x014A]
            if count == 1:
                todo.append(struct.unpack(bo + "I", val)[0])
            elif count <= 8:
                f.seek(struct.unpack(bo + "I", val)[0])
                todo += list(struct.unpack(bo + "I" * count, f.read(4 * count)))
        if 0x8769 in tags:   # EXIF : orientation, parfois l'aperçu (Nikon)
            todo.append(num(0x8769))
        if len(body) >= 12 * n + 4:
            todo.append(struct.unpack(bo + "I", body[12 * n:12 * n + 4])[0])
    return [(o, n) for o, n in found if 0 < n <= RAW_PREVIEW_MAX], orientation


def _tiff_orientation(tiff: bytes) -> int:
    try:
        bo = {b"II": "<", b"MM": ">"}[tiff[:2]]
        off = struct.unpack(bo + "I", tiff[4:8])[0]
        n = struct.unpack(bo + "H", tiff[off:off + 2])[0]
        for k in range(n):
            p = off + 2 + 12 * k
            if struct.unpack(bo + "H", tiff[p:p + 2])[0] == 0x0112:
                return struct.unpack(bo + "H", tiff[p + 8:p + 10])[0]
    except (KeyError, struct.error):
        pass
    return 1


def _from_raw(f, dst: str) -> int:
    """Vignette d'une photo RAW depuis son aperçu JPEG : octets lus, ou 0 si aucun aperçu utilisable.
    Le plus petit aperçu assez grand est pris (moins à lire), le décodage est réduit (draft)."""
    from PIL import Image
    previews, orientation = _raw_previews(f)
    read = 0
    for off, length in sorted(set(previews), key=lambda x: x[1]):
        f.seek(off)
        data = f.read(length)
        read += len(data)
        if data[:2] != b"\xff\xd8":
            continue
        try:
            with Image.open(io.BytesIO(data)) as im:
                if max(im.size) < EMBEDDED_MIN:
                    continue
                im.draft("RGB", (THUMB_SIZE * 2, THUMB_SIZE * 2))
                im.load()
                tr = _TRANSPOSE.get(orientation)
                if tr:
                    im = im.transpose(getattr(Image.Transpose, tr))
                im.thumbnail((THUMB_SIZE, THUMB_SIZE))
                _save(im, dst)
            return max(read, 1)
        except Exception:   # JPEG sans perte (données brutes d'un DNG…) : Pillow ne le lit pas
            continue
    return 0


_TRANSPOSE = {2: "FLIP_LEFT_RIGHT", 3: "ROTATE_180", 4: "FLIP_TOP_BOTTOM", 5: "TRANSPOSE",
              6: "ROTATE_270", 7: "TRANSVERSE", 8: "ROTATE_90"}


# --------------------------------------------------------------------------- #
# Fabrication
# --------------------------------------------------------------------------- #

def _save(im, dst: str):
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".partial"
    im.save(tmp, "JPEG", quality=78, optimize=True)
    os.replace(tmp, dst)


def _from_preview(head: bytes, dst: str) -> bool:
    from PIL import Image
    data, orientation = embedded_preview(head)
    if not data:
        return False
    with Image.open(io.BytesIO(data)) as im:
        if max(im.size) < EMBEDDED_MIN:
            return False
        im.load()
        t = _TRANSPOSE.get(orientation)
        if t:
            im = im.transpose(getattr(Image.Transpose, t))
        im.thumbnail((THUMB_SIZE, THUMB_SIZE))
        _save(im, dst)
    return True


def _decode(fp, dst: str):
    from PIL import Image, ImageOps
    with Image.open(fp) as im:
        im.draft("RGB", (THUMB_SIZE * 2, THUMB_SIZE * 2))   # JPEG : décodage réduit, bien plus rapide
        im = ImageOps.exif_transpose(im)
        im.thumbnail((THUMB_SIZE, THUMB_SIZE))
        _save(im, dst)


def make_from_file(src: str, dst: str) -> bool:
    """Vignette d'une photo sur disque ; False si impossible (format, image abîmée, Pillow absent)."""
    return make_from_file_counted(src, dst)[0]


def make_from_file_counted(src: str, dst: str, size: int | None = None) -> tuple[bool, int]:
    """Comme make_from_file, et renvoie aussi le nombre d'octets lus (environ : une photo décodée
    compte pour sa taille entière), pour afficher un débit de lecture."""
    if size is None:
        try:
            size = os.path.getsize(src)
        except OSError:
            size = 0
    read = 0
    try:
        if ext_of(src) in RAW_EXTS:
            with open(src, "rb") as f:
                read = _from_raw(f, dst)
            return read > 0, read
        if ext_of(src) in JPEG_EXTS:
            with open(src, "rb") as f:
                head = f.read(HEAD_BYTES)
            read = len(head)
            if _from_preview(head, dst):
                return True, read
        read = size
        _decode(src, dst)
        return True, read
    except Exception:   # format non reconnu, image abîmée… : la page affichera une icône
        return False, read


def make_from_bytes(data: bytes, name: str, dst: str) -> bool:
    try:
        if ext_of(name) in RAW_EXTS:
            return _from_raw(io.BytesIO(data), dst) > 0
        if ext_of(name) in JPEG_EXTS and _from_preview(data[:HEAD_BYTES], dst):
            return True
        _decode(io.BytesIO(data), dst)
        return True
    except Exception:
        return False


class Background:
    """Fabrique les vignettes pendant l'import, sur les cœurs libres. submit() ne bloque jamais :
    si les vignettes prennent du retard, la photo est laissée pour plus tard."""

    def __init__(self, path_for_hash, n_workers: int | None = None):
        self.path_for_hash = path_for_hash
        n = n_workers or workers()
        self.pool = ThreadPoolExecutor(n, thread_name_prefix="vignette")
        self.slots = threading.Semaphore(n * 3)
        self.made = 0
        self.lock = threading.Lock()

    def submit(self, h: str, name: str, parts):
        if not wanted(name) or not h:
            return
        dst = self.path_for_hash(h)
        if os.path.exists(dst) or not self.slots.acquire(blocking=False):
            return
        data = parts[0] if len(parts) == 1 else b"".join(parts)

        def work():
            try:
                if make_from_bytes(data, name, dst):
                    with self.lock:
                        self.made += 1
            finally:
                self.slots.release()
        self.pool.submit(work)

    def close(self):
        self.pool.shutdown(wait=True)

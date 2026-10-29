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
- sinon, le JPEG est décodé directement en taille réduite (draft), plusieurs à la fois.
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
EXTS = {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "tif", "tiff", "webp"}
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
    try:
        if ext_of(src) in JPEG_EXTS:
            with open(src, "rb") as f:
                head = f.read(HEAD_BYTES)
            if _from_preview(head, dst):
                return True
        _decode(src, dst)
        return True
    except Exception:   # format non reconnu, image abîmée… : la page affichera une icône
        return False


def make_from_bytes(data: bytes, name: str, dst: str) -> bool:
    try:
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

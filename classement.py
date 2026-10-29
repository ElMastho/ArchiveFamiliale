"""
classement.py - Classement automatique de l'archive par type, date et événement.

Les fichiers sont DÉPLACÉS sur leur disque (renommage : instantané, aucune place en plus).
Le catalogue suit (doublons, vérifications, sauvegardes), chaque déplacement est journalisé
et le dernier classement peut être annulé.

Dates, par ordre de fiabilité :
  1. contenu du fichier : EXIF (JPEG, HEIC, RAW), métadonnées vidéo (MP4/MOV, AVI),
     propriétés Office / OpenDocument, PDF ;
  2. date dans le nom du fichier (IMG_20090812_…, WhatsApp, captures d'écran…) ;
  3. date ou année dans le nom d'un dossier (« Vacances 2009 ») ;
  4. date de modification du fichier (la plus ancienne connue parmi ses copies) : « incertaine ».

Modèles :
  A. Par type, puis date et événement : Photos et vidéos/2009/2009-08 Vacances Bretagne/
  B. Tout chronologique               : 2009/2009-08 Vacances Bretagne/
  C. Par type, puis date seule        : Photos/2009/2009-08/
"""
from __future__ import annotations

import datetime as dt
import os
import re
import struct
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass

import archive as core

MODELS = {
    "A": "Par type, puis date et événement",
    "B": "Tout chronologique",
    "C": "Par type, puis date seule",
}
MODEL_EXAMPLES = {
    "A": ("Photos et vidéos\\2009\\2009-08 Vacances Bretagne\\IMG_1234.JPG\n"
          "Photos et vidéos\\2009\\2009-12 Noël chez mamie\\…\n"
          "Documents\\Tableurs\\2012\\Impôts\\declaration.xlsx\n"
          "Documents\\PDF\\2015\\…\n"
          "Musique\\<album>\\…   Courriels\\…   Autres fichiers\\…"),
    "B": ("2009\\2009-08 Vacances Bretagne\\IMG_1234.JPG\n"
          "2009\\2009-08 Vacances Bretagne\\liste-affaires.docx\n"
          "2012\\2012-04 Impôts\\declaration.xlsx\n"
          "Musique\\…   Courriels\\…   Autres fichiers\\…"),
    "C": ("Photos\\2009\\2009-08\\IMG_1234.JPG\n"
          "Vidéos\\2009\\2009-08\\MVI_0042.MOV\n"
          "Documents\\Tableurs\\2012\\declaration.xlsx\n"
          "Musique\\…   Courriels\\…   Autres fichiers\\…"),
}

PHOTO_EXT = {"jpg", "jpeg", "jpe", "jfif", "heic", "heif", "avif", "png", "gif", "bmp", "tif", "tiff", "webp",
             "psd", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "dng", "orf", "rw2", "raf", "pef",
             "srw", "x3f", "3fr", "erf", "kdc", "mrw", "mos", "rwl", "iiq"}
VIDEO_EXT = {"mp4", "m4v", "mov", "qt", "avi", "mkv", "wmv", "mpg", "mpeg", "mpe", "mts", "m2ts", "m2t", "ts",
             "3gp", "3g2", "flv", "webm", "vob", "mod", "tod", "dv", "asf", "divx", "ogv"}
AUDIO_EXT = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "wma", "aiff", "aif", "opus", "amr", "mid",
             "midi", "ape", "alac", "m4b"}
DOC_TYPES = {
    "Textes": {"doc", "docx", "docm", "dot", "dotx", "odt", "ott", "rtf", "txt", "pages", "wpd", "wps", "md"},
    "Tableurs": {"xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "ods", "ots", "csv", "numbers"},
    "Présentations": {"ppt", "pptx", "pptm", "pps", "ppsx", "pot", "potx", "odp", "otp", "key"},
    "PDF": {"pdf"},
}
DOC_EXT = {e: t for t, exts in DOC_TYPES.items() for e in exts}
MAIL_EXT = {"eml", "msg", "pst", "ost", "mbox", "emlx", "dbx", "mbx"}
SIDECAR_EXT = {"xmp", "thm", "aae", "lrv", "pp3", "dop"}

GENERIC_NAMES = {
    "dcim", "photos", "photo", "images", "image", "pictures", "picture", "my pictures", "mes images", "camera",
    "camera roll", "appareil photo", "pellicule", "whatsapp images", "whatsapp video", "whatsapp", "sent",
    "envoyé", "envoyés", "download", "downloads", "téléchargements", "telechargements", "desktop", "bureau",
    "documents", "mes documents", "my documents", "nouveau dossier", "new folder", "divers", "misc", "tmp",
    "temp", "backup", "backups", "sauvegarde", "sauvegardes", "old", "vieux", "export", "exports", "import",
    "imports", "video", "videos", "vidéo", "vidéos", "films", "movies", "music", "musique", "ma musique",
    "my music", "scans", "scan", "onedrive", "dropbox", "google drive", "icloud photos", "icloud", "iphone",
    "android", "mes vidéos", "my videos", "public", "users", "utilisateurs", "data", "donnees", "données",
    "fichiers", "files", "media", "médias", "medias", "100apple", "screenshots", "captures d'écran",
    "captures", "copie", "copy", "autres", "other", "others", "a trier", "à trier", "nouveau", "new",
    "my documents", "pictures folder", "sd card", "carte sd", "telephone", "téléphone", "portable",
}
GENERIC_RE = re.compile(r"^(\d{3}[a-z_]{0,8}|img|dsc|dcim\d*|camera\d*|\d+|disque ?\d+|dossier ?\d*|folder ?\d*)$")
USER_ROOTS = {"users", "utilisateurs", "documents and settings", "home"}

FULL_DATE_RE = re.compile(r"(?<!\d)((?:19[5-9]|20[0-4])\d)[-_. ]?(0[1-9]|1[0-2])[-_. ]?(0[1-9]|[12]\d|3[01])(?!\d)")
YEAR_MONTH_RE = re.compile(r"(?<!\d)((?:19[5-9]|20[0-4])\d)[-_.](0[1-9]|1[0-2])(?![\d])")
YEAR_RE = re.compile(r"(?<![\d])((?:19[5-9]|20[0-4])\d)(?![\d])")

UNKNOWN_DATE = "Date inconnue"
RELIABLE = {"contenu", "nom"}
SOURCE_LABELS = {
    "contenu": "lue dans le fichier (EXIF, vidéo, document)",
    "nom": "nom du fichier",
    "dossier": "nom du dossier",
    "fichier": "date du fichier (incertaine)",
    None: "inconnue",
}


# --------------------------------------------------------------------------- #
# Types de fichiers
# --------------------------------------------------------------------------- #

def ext_of(name: str) -> str:
    return os.path.splitext(name)[1][1:].lower()


def category(name: str):
    """(catégorie, sous-type) : photo, video, audio, doc(+type), mail, sidecar, other."""
    e = ext_of(name)
    if e in PHOTO_EXT:
        return "photo", None
    if e in VIDEO_EXT:
        return "video", None
    if e in AUDIO_EXT:
        return "audio", None
    if e in DOC_EXT:
        return "doc", DOC_EXT[e]
    if e in MAIL_EXT:
        return "mail", None
    if e in SIDECAR_EXT:
        return "sidecar", None
    return "other", None


# --------------------------------------------------------------------------- #
# Lecture des dates dans le contenu des fichiers (bibliothèque standard uniquement)
# --------------------------------------------------------------------------- #

def _today():
    return dt.date.today()


def _plausible(y, m=None, d=None, min_year=1900):
    try:
        if not (min_year <= y <= _today().year):
            return False
        if m is not None:
            date = dt.date(y, m, d or 1)
            return date <= _today() + dt.timedelta(days=1)
        return True
    except ValueError:
        return False


def _ymd_from_text(s, min_year=1900):
    if not s:
        return None
    m = re.search(r"(\d{4})[:\-/.](\d{2})[:\-/.](\d{2})", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (y, mo, d) if _plausible(y, mo, d, min_year) else None


def _parse_tiff_date(buf: bytes):
    """Date de prise de vue dans un bloc TIFF/EXIF (en-tête II* ou MM*)."""
    if len(buf) < 8:
        return None
    if buf[:2] == b"II":
        e = "<"
    elif buf[:2] == b"MM":
        e = ">"
    else:
        return None
    try:
        def read_ifd(off):
            if off <= 0 or off + 2 > len(buf):
                return {}
            n = struct.unpack(e + "H", buf[off:off + 2])[0]
            if n > 1000:
                return {}
            tags = {}
            for i in range(n):
                p = off + 2 + 12 * i
                if p + 12 > len(buf):
                    break
                tag, typ, cnt = struct.unpack(e + "HHI", buf[p:p + 8])
                tags[tag] = (typ, cnt, buf[p + 8:p + 12])
            return tags

        def as_text(t):
            typ, cnt, val = t
            if typ != 2:
                return None
            if cnt <= 4:
                data = val[:cnt]
            else:
                o = struct.unpack(e + "I", val)[0]
                data = buf[o:o + cnt]
            return data.split(b"\0")[0].decode("ascii", "ignore")

        ifd0 = read_ifd(struct.unpack(e + "I", buf[4:8])[0])
        exif = {}
        if 0x8769 in ifd0:
            exif = read_ifd(struct.unpack(e + "I", ifd0[0x8769][2])[0])
        for tags, tag in ((exif, 0x9003), (ifd0, 0x9003), (exif, 0x9004), (ifd0, 0x9004), (ifd0, 0x0132)):
            if tag in tags:
                d = _ymd_from_text(as_text(tags[tag]))
                if d:
                    return d
    except (struct.error, IndexError):
        return None
    return None


def _find_tiff(data: bytes, limit=64):
    for sig in (b"MM\x00\x2a", b"II\x2a\x00"):
        i = data.find(sig, 0, limit)
        if i >= 0:
            return data[i:]
    return None


def _jpeg_date(data: bytes):
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
            return _parse_tiff_date(data[i + 10:i + 2 + seglen])
        if marker == 0xDA:
            return None
        i += 2 + seglen
    return None


def _bmff_boxes(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        hdr = f.read(16)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack(">I4s", hdr[:8])
        hl = 8
        if size == 1:
            if len(hdr) < 16:
                return
            size = struct.unpack(">Q", hdr[8:16])[0]
            hl = 16
        elif size == 0:
            size = end - pos
        if size < hl:
            return
        yield typ, pos + hl, pos + size
        pos += size


def _heic_date(f, file_size):
    """HEIC/HEIF/AVIF : bloc Exif repéré via les boîtes meta/iinf/iloc."""
    for typ, s, e in _bmff_boxes(f, 0, file_size):
        if typ != b"meta":
            continue
        exif_id, locs = None, {}
        for t2, s2, e2 in _bmff_boxes(f, s + 4, e):
            f.seek(s2)
            body = f.read(min(e2 - s2, 1 << 20))
            if t2 == b"iinf":
                ver = body[0]
                off = 4 + (2 if ver == 0 else 4)
                while off + 8 <= len(body):
                    size, btyp = struct.unpack(">I4s", body[off:off + 8])
                    if size < 8:
                        break
                    if btyp == b"infe":
                        iv = body[off + 8]
                        if iv >= 2:
                            p = off + 12
                            if iv == 2:
                                item_id = struct.unpack(">H", body[p:p + 2])[0]
                                p += 2
                            else:
                                item_id = struct.unpack(">I", body[p:p + 4])[0]
                                p += 4
                            p += 2   # protection index
                            if body[p:p + 4] == b"Exif":
                                exif_id = item_id
                    off += size
            elif t2 == b"iloc":
                ver = body[0]
                p = 4
                off_size, len_size = body[p] >> 4, body[p] & 15
                base_size, idx_size = body[p + 1] >> 4, (body[p + 1] & 15 if ver in (1, 2) else 0)
                p += 2
                if ver < 2:
                    count = struct.unpack(">H", body[p:p + 2])[0]
                    p += 2
                else:
                    count = struct.unpack(">I", body[p:p + 4])[0]
                    p += 4

                def rd(n):
                    nonlocal p
                    v = int.from_bytes(body[p:p + n], "big") if n else 0
                    p += n
                    return v

                for _ in range(count):
                    item_id = rd(2 if ver < 2 else 4)
                    if ver in (1, 2):
                        rd(2)
                    rd(2)
                    base = rd(base_size)
                    ext_count = rd(2)
                    first = None
                    for _ in range(ext_count):
                        if ver in (1, 2) and idx_size:
                            rd(idx_size)
                        eo, el = rd(off_size), rd(len_size)
                        if first is None:
                            first = (base + eo, el)
                    if first:
                        locs[item_id] = first
        if exif_id is not None and exif_id in locs:
            off, length = locs[exif_id]
            f.seek(off)
            data = f.read(min(length or 65536, 1 << 20))
            tiff = _find_tiff(data, 64)
            return _parse_tiff_date(tiff) if tiff else None
    return None


def _mp4_date(f, file_size):
    """MP4/MOV/3GP : date de création de la boîte moov/mvhd (secondes depuis 1904)."""
    for typ, s, e in _bmff_boxes(f, 0, file_size):
        if typ == b"moov":
            for t2, s2, e2 in _bmff_boxes(f, s, e):
                if t2 == b"mvhd":
                    f.seek(s2)
                    body = f.read(12)
                    ver = body[0]
                    secs = struct.unpack(">Q", body[4:12])[0] if ver == 1 else struct.unpack(">I", body[4:8])[0]
                    ts = secs - 2082844800
                    if ts <= 0:
                        return None
                    try:
                        d = dt.datetime.fromtimestamp(ts).date()
                    except (OverflowError, OSError, ValueError):
                        return None
                    return (d.year, d.month, d.day) if _plausible(d.year, d.month, d.day, 1990) else None
            return None
    return None


def _avi_date(data: bytes):
    i = data.find(b"IDIT")
    if i < 0:
        return None
    size = struct.unpack("<I", data[i + 4:i + 8])[0]
    s = data[i + 8:i + 8 + min(size, 64)].split(b"\0")[0].decode("ascii", "ignore").strip()
    for fmt in ("%a %b %d %H:%M:%S %Y", "%Y:%m:%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            return (d.year, d.month, d.day) if _plausible(d.year, d.month, d.day, 1990) else None
        except ValueError:
            continue
    return _ymd_from_text(s, 1990)


def _office_date(path):
    try:
        with zipfile.ZipFile(core.lp(path)) as z:
            names = set(z.namelist())
            if "docProps/core.xml" in names:
                xml = z.read("docProps/core.xml").decode("utf-8", "ignore")
                for tag in ("dcterms:modified", "dcterms:created"):
                    m = re.search(rf"<{tag}[^>]*>([^<]+)<", xml)
                    d = _ymd_from_text(m.group(1), 1985) if m else None
                    if d:
                        return d
            if "meta.xml" in names:
                xml = z.read("meta.xml").decode("utf-8", "ignore")
                for tag in ("dc:date", "meta:creation-date"):
                    m = re.search(rf"<{tag}>([^<]+)<", xml)
                    d = _ymd_from_text(m.group(1), 1985) if m else None
                    if d:
                        return d
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, RuntimeError):
        return None
    return None


def _pdf_date(path, size):
    try:
        with open(core.lp(path), "rb") as f:
            head = f.read(65536)
            tail = b""
            if size > 131072:
                f.seek(size - 65536)
                tail = f.read(65536)
    except OSError:
        return None
    for data in (tail, head):   # la dernière mise à jour du PDF est à la fin
        m = re.search(rb"/CreationDate\s*\(\s*D:(\d{4})(\d{2})(\d{2})", data)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if _plausible(y, mo, d, 1985):
                return (y, mo, d)
        m = re.search(rb"<xmp:CreateDate>(\d{4})-(\d{2})-(\d{2})", data)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if _plausible(y, mo, d, 1985):
                return (y, mo, d)
    return None


def content_date(path: str, name: str):
    """Date inscrite dans le fichier lui-même, ou None. Ne lit que l'en-tête (rapide)."""
    e = ext_of(name)
    try:
        size = os.path.getsize(core.lp(path))
        if e in DOC_EXT:
            if e == "pdf":
                return _pdf_date(path, size)
            if e in ("docx", "docm", "dotx", "xlsx", "xlsm", "xltx", "pptx", "pptm", "ppsx", "potx",
                     "odt", "ott", "ods", "ots", "odp", "otp"):
                return _office_date(path)
            return None
        with open(core.lp(path), "rb") as f:
            if e in ("heic", "heif", "avif", "cr3"):
                if e == "cr3":
                    data = f.read(1 << 20)
                    i = data.find(b"CMT2")
                    return _parse_tiff_date(data[i + 4:]) if i >= 0 else None
                return _heic_date(f, size)
            if e in ("mp4", "m4v", "mov", "qt", "3gp", "3g2"):
                return _mp4_date(f, size)
            if e == "raf":
                head = f.read(100)
                if head.startswith(b"FUJIFILM"):
                    off = struct.unpack(">I", head[84:88])[0]
                    f.seek(off)
                    return _jpeg_date(f.read(1 << 18))
                return None
            data = f.read(1 << 19)
            if e == "avi":
                return _avi_date(data)
            if data[:2] == b"\xff\xd8":
                return _jpeg_date(data)
            if data[:2] in (b"II", b"MM"):   # TIFF et la plupart des RAW (CR2, NEF, ARW, DNG, ORF, RW2…)
                return _parse_tiff_date(data)
    except (OSError, struct.error, ValueError, IndexError):
        return None
    return None


# --------------------------------------------------------------------------- #
# Dates et événements tirés des noms
# --------------------------------------------------------------------------- #

def date_from_name(name: str):
    stem = os.path.splitext(name)[0]
    m = FULL_DATE_RE.search(stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _plausible(y, mo, d, 1950):
            return (y, mo, d)
    m = YEAR_MONTH_RE.search(stem)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if _plausible(y, mo, 1, 1950):
            return (y, mo, None)
    return None


def date_from_dirs(dirs):
    """Date ou année trouvée dans les noms de dossiers (le plus proche du fichier d'abord)."""
    for name in reversed(dirs):
        d = date_from_name(name + ".x")
        if d:
            return d
        m = YEAR_RE.search(name)
        if m and _plausible(int(m.group(1)), min_year=1950):
            return (int(m.group(1)), None, None)
    return None


def clean_event(name: str) -> str:
    s = FULL_DATE_RE.sub(" ", name)
    s = YEAR_MONTH_RE.sub(" ", s)
    s = YEAR_RE.sub(" ", s)
    s = re.sub(r"[\s_]+", " ", s)
    s = re.sub(r"\s*[-.]\s*(?=[-.]|$)", "", s)
    return s.strip(" -_.,;()[]")


def event_for(parts):
    """Nom d'événement tiré des dossiers d'origine (ex. « Vacances Bretagne »), ou None.
    parts : [label, dossier…, fichier]."""
    dirs = parts[1:-1]
    for depth, i in enumerate(range(len(dirs) - 1, -1, -1)):
        if depth >= 3:
            break
        if i > 0 and dirs[i - 1].lower() in USER_ROOTS:
            continue   # dossier de profil Windows/macOS (nom d'utilisateur)
        c = clean_event(dirs[i])
        low = c.lower()
        if not c or low in GENERIC_NAMES or GENERIC_RE.match(low) or len(c) < 2:
            continue
        return c[:60]
    return None


def _stem_key(name: str):
    low = name.lower()
    stem, e = os.path.splitext(low)
    if e[1:] in SIDECAR_EXT:
        s2, e2 = os.path.splitext(stem)
        if e2[1:] in PHOTO_EXT or e2[1:] in VIDEO_EXT:
            stem = s2
    return stem


# --------------------------------------------------------------------------- #
# Calcul du plan de classement
# --------------------------------------------------------------------------- #

@dataclass
class Item:
    path: str
    volume: str
    orig: str
    cat: str
    sub: str | None
    date: tuple | None = None
    source: str | None = None
    event: str | None = None
    new_path: str | None = None


def _month_folder(date, event):
    y, m = date[0], date[1]
    base = f"{y}-{m:02d}" if m else f"{y}"
    return f"{base} {event}" if event else base


def _target_dir(model, it: Item, parts, bundle_idx, label):
    S = core.sanitize_component
    origin_dirs = [S(p) for p in parts[:-1]]               # label inclus
    if bundle_idx is not None:
        root = {"A": "Photos et vidéos", "B": "", "C": "Photos"}[model]
        segs = ([root] if root else []) + ["Bibliothèques et DVD", S(label)] + [S(p) for p in parts[bundle_idx:-1]]
        return "/".join(segs)
    if it.cat == "audio":
        album = parts[-2] if len(parts) > 2 else ""
        album = album if album and album.lower() not in GENERIC_NAMES and not GENERIC_RE.match(album.lower()) else "Divers"
        return "/".join(["Musique", S(album)])
    if it.cat == "mail":
        return "/".join(["Courriels"] + origin_dirs)
    if it.cat in ("other", "sidecar"):
        return "/".join(["Autres fichiers"] + origin_dirs)

    date, ev = it.date, it.event
    if model == "A":
        if it.cat in ("photo", "video"):
            if not date:
                return "/".join(["Photos et vidéos", UNKNOWN_DATE, S(ev or label)])
            return "/".join(["Photos et vidéos", str(date[0]), S(_month_folder(date, ev))])
        segs = ["Documents", it.sub, str(date[0]) if date else UNKNOWN_DATE]
        return "/".join(segs + ([S(ev)] if ev else []))
    if model == "B":
        if not date:
            return "/".join([UNKNOWN_DATE, S(ev or label)])
        return "/".join([str(date[0]), S(_month_folder(date, ev))])
    # modèle C
    if it.cat in ("photo", "video"):
        top = "Photos" if it.cat == "photo" else "Vidéos"
        if not date:
            return "/".join([top, UNKNOWN_DATE, S(label)])
        return "/".join([top, str(date[0]), f"{date[0]}-{date[1]:02d}" if date[1] else str(date[0])])
    return "/".join(["Documents", it.sub, str(date[0]) if date else UNKNOWN_DATE])


def compute_plan(ar: core.Archive, model: str, roots: dict, progress=None) -> list[Item]:
    """Calcule le nouvel emplacement de chaque fichier de l'archive (sans rien déplacer)."""
    rows = ar.db.execute(
        "SELECT s.path, s.volume, s.hash, s.size, COALESCE(s.orig_path, s.path) AS orig, "
        "(SELECT MIN(o.mtime_ns) FROM occurrences o WHERE o.hash=s.hash) AS mtime, "
        "m.y, m.m, m.d, m.source AS csrc FROM stored s LEFT JOIN media_dates m ON m.hash=s.hash").fetchall()

    # 1. Dates lues dans le contenu (mises en cache par empreinte : on ne relit jamais deux fois)
    to_read = [r for r in rows if r["csrc"] is None and category(r["path"])[0] in ("photo", "video", "doc")]
    if progress:
        progress.total_files, progress.total_bytes = len(to_read), len(to_read)
    cache = {}
    for r in to_read:
        root = roots.get(r["volume"])
        d = content_date(os.path.join(root, core.to_os(r["path"])), r["path"]) if root else None
        cache[r["hash"]] = d
        ar.db.execute("INSERT OR REPLACE INTO media_dates(hash,y,m,d,source,extracted_at) VALUES(?,?,?,?,?,?)",
                      (r["hash"], *(d if d else (None, None, None)), "contenu" if d else "aucune", core.now_iso()))
        if progress:
            progress.file_done(1)
        ar.maybe_commit()
    ar.db.commit()

    # 2. Date et événement de chaque fichier
    items, parts_of, bundle_of = [], {}, {}
    for r in rows:
        parts = r["orig"].split("/")
        cat, sub = category(parts[-1])
        it = Item(r["path"], r["volume"], r["orig"], cat, sub)
        bundle_idx = next((i for i in range(1, len(parts) - 1) if core.matches_keep_whole(parts[i])), None)
        parts_of[it.path], bundle_of[it.path] = parts, bundle_idx
        if cat in ("photo", "video", "doc") and bundle_idx is None:
            if r["hash"] in cache:
                cd = cache[r["hash"]]
            elif r["csrc"] == "contenu":
                cd = (r["y"], r["m"], r["d"])
            else:
                cd = None
            if cd:
                it.date, it.source = cd, "contenu"
            elif (nd := date_from_name(parts[-1])):
                it.date, it.source = nd, "nom"
            elif (fd := date_from_dirs(parts[1:-1])):
                it.date, it.source = fd, "dossier"
            elif r["mtime"]:
                try:
                    d = dt.datetime.fromtimestamp(r["mtime"] / 1e9).date()
                    if _plausible(d.year, d.month, d.day, 1985):
                        it.date, it.source = (d.year, d.month, d.day), "fichier"
                except (OverflowError, OSError, ValueError):
                    pass
            if model in ("A", "B"):
                it.event = event_for(parts)
        items.append(it)

    # 3. Un événement reste groupé sous le mois de sa première date fiable s'il dure moins d'un mois
    if model in ("A", "B"):
        groups = defaultdict(list)
        for it in items:
            if it.event and it.date and (it.cat in ("photo", "video") or model == "B"):
                groups["/".join(parts_of[it.path][:-1]).lower()].append(it)
        for members in groups.values():
            reliable = [dt.date(i.date[0], i.date[1] or 1, i.date[2] or 1) for i in members
                        if i.source in RELIABLE and i.date[1]]
            if reliable and (max(reliable) - min(reliable)).days <= 31:
                first = min(reliable)
                for i in members:
                    i.date = (first.year, first.month, first.day)

    # 4. Dossier cible ; les fichiers compagnons (.xmp, .thm, .aae…) suivent leur photo/vidéo
    target_dir = {}
    for it in items:
        if it.cat != "sidecar":
            parts = parts_of[it.path]
            target_dir[it.path] = _target_dir(model, it, parts, bundle_of[it.path], parts[0])
    primaries = {}
    for it in items:
        if it.cat in ("photo", "video"):
            parts = parts_of[it.path]
            primaries.setdefault(("/".join(parts[:-1]).lower(), _stem_key(parts[-1])), it.path)
    for it in items:
        if it.cat == "sidecar":
            parts = parts_of[it.path]
            prim = primaries.get(("/".join(parts[:-1]).lower(), _stem_key(parts[-1])))
            if prim:
                target_dir[it.path] = target_dir[prim]
            else:
                target_dir[it.path] = _target_dir(model, it, parts, bundle_of[it.path], parts[0])

    # 5. Nom final unique (on garde le nom d'origine ; « (2) » en cas de collision)
    taken = {it.path.lower() for it in items}
    for it in sorted(items, key=lambda i: i.orig.lower()):
        tdir = target_dir[it.path]
        if os.path.dirname(it.path.replace("/", os.sep)).replace(os.sep, "/").lower() == tdir.lower():
            it.new_path = it.path
            continue
        name = core.sanitize_component(parts_of[it.path][-1])
        stem, ext = os.path.splitext(name)
        cand, i = f"{tdir}/{name}", 2
        while cand.lower() in taken:
            cand = f"{tdir}/{stem} ({i}){ext}"
            i += 1
        taken.add(cand.lower())
        it.new_path = cand
    return items


# --------------------------------------------------------------------------- #
# Application, annulation, reprise
# --------------------------------------------------------------------------- #

def _db_after_move(ar, old, new):
    ar.db.execute("UPDATE stored SET path=?, orig_path=COALESCE(orig_path, ?) WHERE path=?", (new, old, old))
    ar.db.execute("UPDATE occurrences SET stored_path=? WHERE stored_path=?", (new, old))
    ar.db.execute("UPDATE backup_copies SET phys_path = CASE WHEN COALESCE(phys_path, path)=? THEN NULL "
                  "ELSE COALESCE(phys_path, path) END, path=? WHERE path=?", (new, new, old))


def _free_name(ar, root, new):
    """Si la destination est prise (catalogue ou disque), ajoute « (2) », « (3) »…"""
    stem, ext = os.path.splitext(new)
    cand, i = new, 2
    while ar.stored_row(cand) is not None or os.path.lexists(core.lp(os.path.join(root, core.to_os(cand)))):
        cand = f"{stem} ({i}){ext}"
        i += 1
    return cand


def remove_empty_dirs(root: str):
    """Supprime les dossiers devenus vides (jamais le dossier _catalogue)."""
    n = 0
    for dirpath, dirnames, filenames in os.walk(core.lp(root), topdown=False):
        rel = os.path.relpath(dirpath, core.lp(root))
        if rel == "." or rel.split(os.sep)[0].lower() == core.CATALOG_DIR:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
                n += 1
        except OSError:
            pass
    return n


def reconcile(ar: core.Archive, roots: dict):
    """Termine proprement les déplacements interrompus (coupure de courant, arrêt brutal)."""
    rows = ar.db.execute("SELECT * FROM moves WHERE status='pending'").fetchall()
    for r in rows:
        root = roots.get(r["volume"])
        if not root:
            continue
        old_abs = os.path.join(root, core.to_os(r["old_path"]))
        new_abs = os.path.join(root, core.to_os(r["new_path"]))
        if os.path.lexists(core.lp(new_abs)) and not os.path.lexists(core.lp(old_abs)):
            _db_after_move(ar, r["old_path"], r["new_path"])
            status = "done"
        else:
            status = "skipped"
        ar.db.execute("UPDATE moves SET status=? WHERE batch=? AND seq=?", (status, r["batch"], r["seq"]))
    ar.db.execute("UPDATE classifications SET status='interrompu' WHERE status='en cours'")
    ar.db.commit()


def apply_moves(ar: core.Archive, moves, roots: dict, model: str, kind: str, undo_of=None, progress=None):
    """moves : liste de (volume, ancien chemin, nouveau chemin). Renvoie (déplacés, erreurs)."""
    cur = ar.db.execute("INSERT INTO classifications(model,kind,created_at,status,undo_of) VALUES(?,?,?,?,?)",
                        (model, kind, core.now_iso(), "en cours", undo_of))
    batch = cur.lastrowid
    ar.db.executemany("INSERT INTO moves(batch,seq,volume,old_path,new_path,status) VALUES(?,?,?,?,?,'pending')",
                      [(batch, i, v, o, n) for i, (v, o, n) in enumerate(moves)])
    ar.db.commit()
    moved, errors = 0, []
    interrupted = False
    try:
        for i, (vol, old, new) in enumerate(moves):
            root = roots[vol]
            new = _free_name(ar, root, new)
            src = os.path.join(root, core.to_os(old))
            dst = os.path.join(root, core.to_os(new))
            try:
                os.makedirs(core.lp(os.path.dirname(dst)), exist_ok=True)
                ar.db.execute("UPDATE moves SET new_path=? WHERE batch=? AND seq=?", (new, batch, i))
                ar.db.commit()
                os.rename(core.lp(src), core.lp(dst))
            except OSError as exc:
                errors.append((old, f"{type(exc).__name__}: {exc}"))
                ar.db.execute("UPDATE moves SET status='skipped' WHERE batch=? AND seq=?", (batch, i))
                continue
            _db_after_move(ar, old, new)
            ar.db.execute("UPDATE moves SET status='done' WHERE batch=? AND seq=?", (batch, i))
            moved += 1
            if progress:
                progress.file_done(1)
            ar.maybe_commit()
    except KeyboardInterrupt:
        interrupted = True
    ar.db.execute("UPDATE moves SET status='skipped' WHERE batch=? AND status='pending'", (batch,))
    ar.db.execute("UPDATE classifications SET status=?, finished_at=?, moved=? WHERE id=?",
                  ("interrompu" if interrupted else "terminé", core.now_iso(), moved, batch))
    ar.db.commit()
    for root in {r for r in roots.values() if r}:
        remove_empty_dirs(root)
    return batch, moved, errors, interrupted


def apply_backup_renames(ar: core.Archive, set_id=None):
    """Répercute les déplacements sur les disques de sauvegarde branchés (sans recopie).
    Renvoie (renommés, en attente car disque non branché)."""
    sets = [set_id] if set_id else [r[0] for r in ar.db.execute("SELECT id FROM backup_sets")]
    renamed = pending = 0
    for sid in sets:
        roots = ar.resolve_roots(sid)
        rows = ar.db.execute("SELECT path, volume, phys_path, size FROM backup_copies "
                             "WHERE set_id=? AND phys_path IS NOT NULL", (sid,)).fetchall()
        touched = set()
        for r in rows:
            root = roots.get(r["volume"])
            if not root:
                pending += 1
                continue
            src = os.path.join(root, core.to_os(r["phys_path"]))
            dst = os.path.join(root, core.to_os(r["path"]))
            try:
                if os.path.lexists(core.lp(dst)):
                    pass   # déjà en place
                elif os.path.lexists(core.lp(src)):
                    os.makedirs(core.lp(os.path.dirname(dst)), exist_ok=True)
                    os.rename(core.lp(src), core.lp(dst))
                    renamed += 1
                else:
                    # copie introuvable : elle sera refaite par la prochaine sauvegarde
                    ar.db.execute("DELETE FROM backup_copies WHERE set_id=? AND path=?", (sid, r["path"]))
                    continue
            except OSError:
                continue
            ar.db.execute("UPDATE backup_copies SET phys_path=NULL WHERE set_id=? AND path=?", (sid, r["path"]))
            touched.add(root)
        ar.db.commit()
        for root in touched:
            remove_empty_dirs(root)
    return renamed, pending


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #

def _require_all_main_volumes(ar):
    roots = ar.resolve_roots(core.MAIN_SET)
    missing = [v["name"] for v in ar.volumes(core.MAIN_SET) if not roots.get(v["id"])]
    if missing:
        raise core.UserError(f"Branchez tous les disques de l'archive avant de classer. Manquant(s) : "
                             f"{', '.join(missing)}.")
    return roots


def _print_summary(items, moves):
    tops = Counter()
    seconds = Counter()
    for it in items:
        segs = it.new_path.split("/")
        tops[segs[0]] += 1
        if len(segs) > 2:
            seconds["/".join(segs[:2])] += 1
    print("\nArborescence proposée (nombre de fichiers) :")
    for top, n in sorted(tops.items()):
        print(f"  {top:<40} {core.fmt_int(n)}")
        subs = sorted(((k, v) for k, v in seconds.items() if k.startswith(top + "/")), key=lambda kv: kv[0])
        for k, v in subs[:12]:
            print(f"      {k.split('/', 1)[1]:<36} {core.fmt_int(v)}")
        if len(subs) > 12:
            print(f"      … et {len(subs) - 12} autres dossiers")
    dated = [it for it in items if it.cat in ("photo", "video", "doc")]
    if dated:
        src = Counter(it.source for it in dated)
        print("\nOrigine des dates (photos, vidéos, documents) :")
        for k in ("contenu", "nom", "dossier", "fichier", None):
            if src.get(k):
                print(f"  {SOURCE_LABELS[k]:<45} {core.fmt_int(src[k])}  ({100 * src[k] / len(dated):.0f} %)")
    print(f"\nFichiers à déplacer : {core.fmt_int(len(moves))} sur {core.fmt_int(len(items))}")
    shown = 0
    for it in items:
        if it.new_path != it.path and shown < 12:
            print(f"  {it.path}\n     -> {it.new_path}")
            shown += 1


def cmd_classify(args) -> int:
    with core.keep_awake():
        ar = core.Archive(args.master)
        try:
            model = args.modele.upper()
            roots = _require_all_main_volumes(ar)
            reconcile(ar, roots)
            print(f"Classement de l'archive — modèle {model} : {MODELS[model]}"
                  + ("" if args.appliquer else "  (SIMULATION : rien n'est déplacé)"))
            print("Lecture des dates dans les fichiers (les fichiers déjà lus sont sautés)…")
            progress = core.Progress(0, 0)
            try:
                items = compute_plan(ar, model, roots, progress)
            except KeyboardInterrupt:
                print("\nInterrompu (les dates déjà lues sont conservées pour la prochaine fois).")
                return 130
            progress.finish()
            moves = [(it.volume, it.path, it.new_path) for it in items if it.new_path != it.path]
            _print_summary(items, moves)

            out_dir = os.path.join(ar.cat_dir, "classement")
            os.makedirs(out_dir, exist_ok=True)
            plan_csv = os.path.join(out_dir, f"plan_{model}_{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
            names = {v["id"]: v["name"] for v in ar.volumes(core.MAIN_SET)}
            core._write_csv(plan_csv, ["emplacement_actuel", "nouvel_emplacement", "disque", "type", "date",
                                       "origine_de_la_date"],
                            ((it.path, it.new_path, names.get(it.volume), it.sub or it.cat,
                              "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(it.date) if x) if it.date else "",
                              SOURCE_LABELS[it.source]) for it in items))
            print(f"\nPlan complet : {plan_csv}")
            if not args.appliquer:
                print("\nRien n'a été déplacé. Pour appliquer : la même commande avec --appliquer.")
                return 0
            if not moves:
                print("Rien à déplacer : l'archive est déjà classée selon ce modèle.")
                ar.set_meta("classification_model", model)
                ar.set_meta("classification_at", core.now_iso())
                ar.db.commit()
                return 0
            print(f"\nDéplacement de {core.fmt_int(len(moves))} fichiers…")
            batch, moved, errors, interrupted = apply_moves(ar, moves, roots, model, "classement",
                                                            progress=core.Progress(len(moves), len(moves)))
            if moved:
                ar.set_meta("classification_model", model)
                ar.set_meta("classification_at", core.now_iso())
                ar.db.execute("UPDATE stored SET class_batch=? WHERE path IN (SELECT new_path FROM moves "
                              "WHERE batch=? AND status='done')", (batch, batch))
            ar.db.execute("UPDATE stored SET class_batch=? WHERE class_batch IS NULL", (batch,))
            ar.db.commit()
            renamed, pending = apply_backup_renames(ar)
            ar.sync_catalog_copies()
            print(f"\n  déplacés : {core.fmt_int(moved)}  |  erreurs : {core.fmt_int(len(errors))}")
            for old, why in errors[:15]:
                print(f"    ! {old} -> {why}")
            if renamed or pending:
                print(f"  sauvegardes : {core.fmt_int(renamed)} fichiers renommés sur les disques branchés"
                      + (f", {core.fmt_int(pending)} en attente (disques non branchés : ce sera fait à la "
                         f"prochaine mise à jour des sauvegardes)" if pending else ""))
            if interrupted:
                print("Interrompu : relancez la même commande pour terminer le classement.")
                return 130
            print("\nOK : classement appliqué. Pour revenir en arrière : annuler-classement.")
            return 1 if errors else 0
        finally:
            ar.close()


def cmd_undo(args) -> int:
    with core.keep_awake():
        ar = core.Archive(args.master)
        try:
            roots = _require_all_main_volumes(ar)
            reconcile(ar, roots)
            last = ar.db.execute("SELECT * FROM classifications WHERE status IN ('terminé','interrompu') "
                                 "AND undone_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
            if last is None or last["kind"] != "classement":
                print("Aucun classement à annuler.")
                return 0
            rows = ar.db.execute("SELECT volume, old_path, new_path FROM moves WHERE batch=? AND status='done' "
                                 "ORDER BY seq DESC", (last["id"],)).fetchall()
            moves = [(r["volume"], r["new_path"], r["old_path"]) for r in rows
                     if ar.stored_row(r["new_path"]) is not None]
            print(f"Annulation du classement n°{last['id']} (modèle {last['model']}, {last['created_at']}) : "
                  f"{core.fmt_int(len(moves))} fichiers remis à leur place.")
            batch, moved, errors, interrupted = apply_moves(ar, moves, roots, last["model"], "annulation",
                                                            undo_of=last["id"],
                                                            progress=core.Progress(len(moves), len(moves)))
            if interrupted:
                print("Interrompu : relancez la même commande pour terminer l'annulation.")
                return 130
            ar.db.execute("UPDATE classifications SET undone_at=? WHERE id=?", (core.now_iso(), last["id"]))
            ar.db.execute("UPDATE stored SET class_batch=NULL WHERE class_batch=?", (last["id"],))
            prev = ar.db.execute("SELECT model FROM classifications WHERE kind='classement' AND undone_at IS NULL "
                                 "AND status='terminé' AND id<? ORDER BY id DESC LIMIT 1", (last["id"],)).fetchone()
            if prev:
                ar.set_meta("classification_model", prev[0])
            else:
                ar.db.execute("DELETE FROM meta WHERE key IN ('classification_model','classification_at')")
            ar.db.commit()
            renamed, pending = apply_backup_renames(ar)
            ar.sync_catalog_copies()
            print(f"  remis en place : {core.fmt_int(moved)}  |  erreurs : {core.fmt_int(len(errors))}")
            for old, why in errors[:15]:
                print(f"    ! {old} -> {why}")
            return 1 if errors else 0
        finally:
            ar.close()

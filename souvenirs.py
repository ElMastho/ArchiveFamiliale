"""« Nos souvenirs » : une visionneuse de l'archive, posée sur chaque disque.

Sur chaque disque de l'archive (et de chaque jeu de sauvegarde) branché, le programme écrit :
- _catalogue/souvenirs/ : une petite page web (index.html, app.js, style.css), la liste des
  fichiers de CE disque (donnees.js) et des vignettes des photos (v/xx/<empreinte>.jpg) ;
- « ▶ Nos souvenirs.html » à la racine, qui ouvre cette page d'un double-clic.

La page fonctionne sans Internet ni installation, dans n'importe quel navigateur (Windows, Mac) :
elle lit les fichiers du disque par des liens relatifs. Elle ne modifie jamais rien.

Les vignettes demandent la bibliothèque Pillow (facultative) : sans elle, la page fonctionne, les
photos s'affichent simplement en taille réelle, plus lentement. Elles sont gardées en cache sur
ARCHIVE-1 (_catalogue/vignettes) pour ne pas relire deux fois les mêmes photos d'un disque à l'autre.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

import archive as core
import bilan
import classement

SITE_DIR = "souvenirs"
CACHE_DIR = "vignettes"
LAUNCHER = "▶ Nos souvenirs.html"
DEFAULT_TITLE = "Nos souvenirs"
THUMB_SIZE = 360
THUMB_EXT = {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "tif", "tiff", "webp"}
ASSETS = ("index.html", "app.js", "style.css")


def assets_dir() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "souvenirs_site")


def _dates(db):
    """Empreinte -> (année, mois) lus dans le contenu, et empreinte -> plus ancienne date de modification."""
    content = {h: (y, m) for h, y, m in db.execute("SELECT hash, y, m FROM media_dates WHERE y IS NOT NULL")}
    mtimes = dict(db.execute("SELECT hash, MIN(mtime_ns) FROM occurrences WHERE hash IS NOT NULL GROUP BY hash"))
    return content, mtimes


def _when(path, h, content, mtimes):
    """(année, mois) d'un fichier : contenu, puis nom, puis dossiers, puis date de modification."""
    parts = path.split("/")
    this_year = dt.date.today().year
    c = content.get(h)
    if c and bilan.MIN_YEAR <= c[0] <= this_year:
        return c[0], c[1] or 0
    d = classement.date_from_name(parts[-1]) or classement.date_from_dirs(parts[:-1])
    if d and bilan.MIN_YEAR <= d[0] <= this_year:
        return d[0], d[1] or 0
    ns = mtimes.get(h)
    if ns:
        try:
            t = dt.datetime.fromtimestamp(ns / 1e9)
            if bilan.MIN_YEAR <= t.year <= this_year:
                return t.year, t.month
        except (OverflowError, OSError, ValueError):
            pass
    return 0, 0


def _album(path):
    """Nom d'album : le dossier d'origine (« Vacances Bretagne »), sans les dates."""
    return classement.event_for(path.split("/")) or ""   # 1er élément : disque d'origine ou famille


def _thumb(src, cache_path):
    """Fabrique la vignette (JPEG) d'une photo ; False si impossible (format, fichier abîmé…)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return False
    try:
        with Image.open(core.lp(src)) as im:
            im.draft("RGB", (THUMB_SIZE * 2, THUMB_SIZE * 2))   # JPEG : décodage réduit, bien plus rapide
            im = ImageOps.exif_transpose(im)
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp = cache_path + ".partial"
            im.save(core.lp(tmp), "JPEG", quality=78, optimize=True)
            os.replace(core.lp(tmp), core.lp(cache_path))
            return True
    except Exception as e:   # format non reconnu, image abîmée… : la page affichera une icône
        core.log.info("Vignette impossible pour %s : %s", src, e)
        return False


def _targets(ar):
    """Disques branchés où écrire la page : [(nom, racine, [(chemin, empreinte, taille)])]."""
    out = []
    for vid, root in ar.resolve_roots(core.MAIN_SET).items():
        if root:
            rows = ar.db.execute("SELECT path, hash, size FROM stored WHERE volume=?", (vid,)).fetchall()
            out.append((vid, root, [tuple(r) for r in rows]))
    for (sid,) in ar.db.execute("SELECT id FROM backup_sets").fetchall():
        for vid, root in ar.resolve_roots(sid).items():
            if root:
                rows = ar.db.execute(
                    "SELECT b.path, s.hash, s.size FROM backup_copies b JOIN stored s ON s.path=b.path "
                    "WHERE b.set_id=? AND b.volume=? AND b.phys_path IS NULL", (sid, vid)).fetchall()
                out.append((vid, root, [tuple(r) for r in rows]))
    return out


def _launcher(target_rel):
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={target_rel}">
<title>Nos souvenirs</title>
<style>body{{font:20px system-ui,sans-serif;background:#f3f5f8;color:#18212f;display:grid;place-items:center;
height:100vh;margin:0}}a{{background:#005fb8;color:#fff;padding:18px 34px;border-radius:14px;text-decoration:none}}</style>
</head><body><a href="{target_rel}">Ouvrir nos souvenirs</a></body></html>
"""


def write_launchers(root):
    """« ▶ Nos souvenirs.html » dans le dossier de l'archive, et à la racine du disque quand l'archive
    y est seule (disque dédié, pas le disque de Windows)."""
    rel = f"{core.CATALOG_DIR}/{SITE_DIR}/index.html"
    written = []
    p = os.path.join(root, LAUNCHER)
    with open(core.lp(p), "w", encoding="utf-8") as f:
        f.write(_launcher(rel))
    written.append(p)
    drive = core.drive_root_of(root)
    parent = os.path.dirname(os.path.normpath(root))
    system = os.environ.get("SystemDrive", "C:").upper()
    if drive and core.same_path(parent, drive) and not drive.upper().startswith(system):
        p = os.path.join(drive, LAUNCHER)
        try:
            with open(core.lp(p), "w", encoding="utf-8") as f:
                f.write(_launcher(f"{os.path.basename(os.path.normpath(root))}/{rel}"))
            written.append(p)
        except OSError:
            pass
    return written


def generate(ar, title=None) -> dict:
    """Écrit (ou met à jour) la page sur chaque disque branché. Renvoie un petit bilan."""
    title = title or ar.meta("souvenirs_titre") or DEFAULT_TITLE
    content, mtimes = _dates(ar.db)
    names = {v["id"]: v["name"] for v in ar.all_volumes()}
    totals = {v["id"]: 0 for v in ar.all_volumes()}
    for vid, n in ar.db.execute("SELECT volume, COUNT(*) FROM stored GROUP BY volume"):
        totals[vid] = n
    targets = _targets(ar)
    cache = os.path.join(ar.cat_dir, CACHE_DIR)
    photos = [size for _, _, rows in targets for p, _, size in rows if classement.ext_of(p) in THUMB_EXT]
    progress = core.Progress(len(photos), sum(photos))
    made = 0
    summary = {"disks": [], "thumbs": 0}
    for vid, root, rows in targets:
        site = os.path.join(root, core.CATALOG_DIR, SITE_DIR)
        os.makedirs(core.lp(site), exist_ok=True)
        files = []
        for path, h, size in sorted(rows):
            fam = bilan.family(path)
            if fam == "other" and classement.category(path)[0] == "sidecar":
                continue   # fichiers techniques d'appareil photo : rien à regarder
            y, m = _when(path, h, content, mtimes)
            thumb = ""   # empreinte si la vignette existe (v/xx/<empreinte>.jpg)
            if classement.ext_of(path) in THUMB_EXT:
                core.check_cancel()
                rel = f"v/{h[:2]}/{h}.jpg"
                dst = os.path.join(site, rel.replace("/", os.sep))
                if os.path.exists(core.lp(dst)):
                    thumb = h
                else:
                    cached = os.path.join(cache, h[:2], h + ".jpg")
                    if not os.path.exists(core.lp(cached)):
                        made += _thumb(os.path.join(root, core.to_os(path)), cached)
                    if os.path.exists(core.lp(cached)):
                        os.makedirs(core.lp(os.path.dirname(dst)), exist_ok=True)
                        shutil.copyfile(core.lp(cached), core.lp(dst))
                        thumb = h
                progress.file_done(size)
            files.append([path, fam, y, m, _album(path), size, thumb])
        others = [{"name": names.get(o, o), "files": n} for o, n in totals.items()
                  if o != vid and n and o in {v["id"] for v in ar.volumes(core.MAIN_SET)}]
        data = {"title": title, "disk": names.get(vid, vid), "generated": core.now_iso(),
                "families": {k: label for k, label, _ in bilan.FAMILIES}, "others": others, "files": files}
        with open(core.lp(os.path.join(site, "donnees.js")), "w", encoding="utf-8") as f:
            f.write("window.SOUVENIRS = ")
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            f.write(";\n")
        for name in ASSETS:
            shutil.copyfile(os.path.join(assets_dir(), name), core.lp(os.path.join(site, name)))
        write_launchers(root)
        summary["disks"].append((names.get(vid, vid), len(files)))
    progress.finish()
    summary["thumbs"] = made
    return summary


def cmd_souvenirs(args) -> int:
    ar = core.Archive(args.master)
    try:
        if args.titre:
            ar.set_meta("souvenirs_titre", args.titre.strip())
            ar.db.commit()
        print("Création de « Nos souvenirs » sur les disques branchés…")
        try:
            s = generate(ar)
        except KeyboardInterrupt:
            print("\nInterrompu : relancez pour terminer (les vignettes déjà faites sont gardées).")
            return 130
        if not s["disks"]:
            print("Aucun disque de l'archive n'est branché.")
            return 2
        for name, n in s["disks"]:
            print(f"  {name} : {core.fmt_int(n)} fichiers consultables")
        print(f"  {core.fmt_int(s['thumbs'])} vignettes de photos fabriquées")
        print(f"\nSur chaque disque, double-cliquez sur « {LAUNCHER} » pour consulter l'archive.")
        return 0
    finally:
        ar.close()

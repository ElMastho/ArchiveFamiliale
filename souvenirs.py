"""« Nos souvenirs » : une visionneuse de l'archive, posée sur chaque disque.

Sur chaque disque de l'archive (et de chaque jeu de sauvegarde) branché, le programme écrit :
- _catalogue/souvenirs/ : une petite page web (index.html, app.js, style.css), la liste des
  fichiers de CE disque (donnees.js, avec les documents qui semblent importants : importants.py)
  et des vignettes des photos (v/xx/<empreinte>.jpg) ;
- « ▶ Nos souvenirs.html » à la racine, qui ouvre cette page d'un double-clic.

La page fonctionne sans Internet ni installation, dans n'importe quel navigateur (Windows, Mac) :
elle lit les fichiers du disque par des liens relatifs. Elle ne modifie jamais rien.

Les vignettes (vignettes.py) demandent la bibliothèque Pillow (facultative) : sans elle, la page
fonctionne, les photos s'affichent simplement en taille réelle, plus lentement. Celles d'ARCHIVE-1
servent de réserve : les autres disques en reçoivent une copie, sans relire les photos. La plupart
sont faites pendant l'import, à partir des photos déjà en mémoire.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import archive as core
import bilan
import classement
import importants
import vignettes

SITE_DIR = "souvenirs"
LAUNCHER = "▶ Nos souvenirs.html"
DEFAULT_TITLE = "Nos souvenirs"
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


def _cache(ar) -> str:
    """Dossier des vignettes sur ARCHIVE-1 : celui de sa page, pour ne pas les avoir en double.
    Celles de la version 2.6 (_catalogue/vignettes) y sont déplacées."""
    cache = os.path.join(ar.cat_dir, *vignettes.CACHE_PARTS)
    old = os.path.join(ar.cat_dir, "vignettes")
    if os.path.isdir(core.lp(old)):
        for d in os.scandir(core.lp(old)):
            if d.is_dir():
                os.makedirs(core.lp(os.path.join(cache, d.name)), exist_ok=True)
                for f in os.scandir(d.path):
                    try:
                        os.replace(f.path, core.lp(os.path.join(cache, d.name, f.name)))
                    except OSError:
                        pass
        shutil.rmtree(core.lp(old), ignore_errors=True)
    return cache


def _existing(folder) -> set:
    """Empreintes des vignettes présentes dans un dossier v/."""
    out = set()
    try:
        for d in os.scandir(core.lp(folder)):
            if d.is_dir():
                out.update(f.name[:-4] for f in os.scandir(d.path) if f.name.endswith(".jpg"))
    except OSError:
        pass
    return out


def _write_site(site, data, meta, have, primary, vcache):
    """Écrit la page d'un disque. Les vignettes disponibles (have) sont copiées sur ce disque s'il
    n'est pas ARCHIVE-1 (dont la page lit directement la réserve)."""
    os.makedirs(core.lp(site), exist_ok=True)
    present = have if primary else _existing(os.path.join(site, "v"))
    files = []
    for path, fam, y, m, album, size, h, imp in meta:
        thumb = ""
        if h in have and vignettes.wanted(path):
            if h not in present:
                core.check_cancel()
                dst = os.path.join(site, "v", h[:2], h + ".jpg")
                os.makedirs(core.lp(os.path.dirname(dst)), exist_ok=True)
                shutil.copyfile(core.lp(os.path.join(vcache, h[:2], h + ".jpg")), core.lp(dst))
                present.add(h)
            thumb = h
        files.append([path, fam, y, m, album, size, thumb, imp])
    tmp = os.path.join(site, "donnees.js.partial")
    with open(core.lp(tmp), "w", encoding="utf-8") as f:
        f.write("window.SOUVENIRS = ")
        json.dump(dict(data, files=files), f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(core.lp(tmp), core.lp(os.path.join(site, "donnees.js")))
    for name in ASSETS:
        shutil.copyfile(os.path.join(assets_dir(), name), core.lp(os.path.join(site, name)))


def _make_thumbs(todo: dict, vcache: str, have: set) -> int:
    """Fait les vignettes manquantes (empreinte -> (photo, taille)), plusieurs à la fois."""
    progress = core.Progress(len(todo), sum(size for _, size in todo.values()))
    n = vignettes.workers()
    items = iter(todo.items())
    pending = {}
    made = 0
    try:
        with ThreadPoolExecutor(n, thread_name_prefix="vignette") as ex:
            try:
                while True:
                    while len(pending) < n * 2:
                        nxt = next(items, None)
                        if nxt is None:
                            break
                        h, (src, size) = nxt
                        dst = core.lp(os.path.join(vcache, h[:2], h + ".jpg"))
                        pending[ex.submit(vignettes.make_from_file, core.lp(src), dst)] = (h, size)
                    if not pending:
                        break
                    done, _ = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for fut in done:
                        h, size = pending.pop(fut)
                        if fut.result():
                            have.add(h)
                            made += 1
                        progress.file_done(size)
                    core.check_cancel()
            except KeyboardInterrupt:
                for fut in pending:
                    fut.cancel()
                raise
    finally:
        progress.finish()
    return made


def generate(ar, title=None) -> dict:
    """Écrit (ou met à jour) la page sur chaque disque branché. Renvoie un petit bilan.

    1. La page est écrite tout de suite sur chaque disque, avec les vignettes déjà faites (pendant
       l'import, ou une fois précédente) : elle est utilisable immédiatement ;
    2. les vignettes manquantes sont faites, plusieurs à la fois (vignettes.py) ;
    3. la page est réécrite pour les montrer. Interrompre pendant 2 ne perd rien."""
    title = title or ar.meta("souvenirs_titre") or DEFAULT_TITLE
    content, mtimes = _dates(ar.db)
    names = {v["id"]: v["name"] for v in ar.all_volumes()}
    main_ids = {v["id"] for v in ar.volumes(core.MAIN_SET)}
    totals = {v["id"]: 0 for v in ar.all_volumes()}
    for vid, n in ar.db.execute("SELECT volume, COUNT(*) FROM stored GROUP BY volume"):
        totals[vid] = n
    vcache = _cache(ar)
    have = _existing(vcache)
    sites = []   # (dossier de la page, données communes, fichiers, est ARCHIVE-1, racine)
    for vid, root, rows in _targets(ar):
        meta = []
        for path, h, size in sorted(rows):
            fam = bilan.family(path)
            if fam == "other" and classement.category(path)[0] == "sidecar":
                continue   # fichiers techniques d'appareil photo : rien à regarder
            y, m = _when(path, h, content, mtimes)
            meta.append((path, fam, y, m, _album(path), size, h, importants.category(path, fam) or ""))
        others = [{"name": names.get(o, o), "files": n} for o, n in totals.items()
                  if o != vid and n and o in main_ids]
        data = {"title": title, "disk": names.get(vid, vid), "generated": core.now_iso(),
                "families": {k: label for k, label, _ in bilan.FAMILIES},
                "important": {k: [label, icon] for k, label, icon, _ in importants.CATEGORIES},
                "others": others}
        sites.append((os.path.join(root, core.CATALOG_DIR, SITE_DIR), data, meta,
                      core.same_path(root, ar.root), root))

    def write_all():
        for site, data, meta, primary, root in sites:
            _write_site(site, data, meta, have, primary, vcache)
            write_launchers(root)

    write_all()
    todo = {}   # chaque photo une seule fois, lue sur le premier disque qui l'a
    for _, _, meta, _, root in sites:
        for path, _, _, _, _, size, h, _ in meta:
            if h not in have and h not in todo and vignettes.wanted(path):
                todo[h] = (os.path.join(root, core.to_os(path)), size)
    made = 0
    if todo and vignettes.available():
        try:
            made = _make_thumbs(todo, vcache, have)
        except KeyboardInterrupt:   # mise en pause : ARCHIVE-1 montre déjà les vignettes faites
            for site, data, meta, primary, _ in sites:
                if primary:
                    _write_site(site, data, meta, have, primary, vcache)
            raise
        write_all()
    return {"disks": [(d["disk"], len(meta)) for _, d, meta, _, _ in sites], "thumbs": made}


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
            print("\nInterrompu : la page est déjà utilisable ; relancez pour finir les vignettes "
                  "(celles déjà faites sont gardées).")
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

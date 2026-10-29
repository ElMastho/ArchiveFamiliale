"""Bilan : « qu'y avait-il dans tous ces disques ? »

Compte les fichiers par grande famille (photos, vidéos, musique, textes, tableurs, présentations,
PDF, e-mails), donne la période couverte par chacune et la répartition par année, mesure ce que
les doublons ont fait gagner, et compte les documents qui semblent importants (importants.py :
papiers d'identité, fiches de paie, diplômes, impôts…).

Deux usages :
- sur l'archive (catalogue) : tout ce qui a été vu sur les anciens disques ;
- sur une estimation rapide : les mêmes chiffres pour des disques simplement branchés, sans rien
  copier (le moteur appelle Summary.add pour chaque fichier listé).

La date d'un fichier est, par ordre de préférence : celle lue dans son contenu lors d'un classement
(table media_dates), celle écrite dans son nom (IMG_20120805…), sinon sa date de modification.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter

import classement
import importants

# Familles affichées, dans l'ordre : (clé, libellé au pluriel, libellé au singulier)
FAMILIES = [
    ("photo", "photos", "photo"),
    ("video", "vidéos", "vidéo"),
    ("audio", "musiques et sons", "musique ou son"),
    ("Textes", "textes (Word…)", "texte"),
    ("Tableurs", "tableurs (Excel…)", "tableur"),
    ("Présentations", "présentations (PowerPoint…)", "présentation"),
    ("PDF", "PDF", "PDF"),
    ("mail", "e-mails", "e-mail"),
    ("other", "autres fichiers", "autre fichier"),
]
LABELS = {k: plural for k, plural, _ in FAMILIES}
MIN_YEAR = 1970


def family(name: str) -> str:
    cat, sub = classement.category(name)
    if cat == "doc":
        return sub
    return "other" if cat == "sidecar" else cat


def year_of(name: str, mtime_ns, content_year=None):
    """Année d'un fichier, ou None si elle n'est pas plausible."""
    this_year = dt.date.today().year
    if content_year and MIN_YEAR <= content_year <= this_year:
        return content_year
    d = classement.date_from_name(name.rsplit("/", 1)[-1])
    if d:
        return d[0]
    if mtime_ns:
        try:
            y = dt.datetime.fromtimestamp(mtime_ns / 1e9).year
        except (OverflowError, OSError, ValueError):
            return None
        if MIN_YEAR <= y <= this_year:
            return y
    return None


class Summary:
    """Compteurs par famille et par année. add() pour chaque fichier UNIQUE (après dédoublonnage)."""

    def __init__(self):
        self.count = Counter()
        self.bytes = Counter()
        self.years: dict[str, Counter] = {k: Counter() for k, _, _ in FAMILIES}
        self.seen_n = self.seen_b = 0   # tout ce qui a été vu, doublons compris
        self.imp_count = Counter()      # documents importants, par catégorie (importants.CATEGORIES)
        self.imp_bytes = Counter()
        self.imp_years = Counter()

    def add(self, name: str, size: int, mtime_ns=None, content_year=None):
        f = family(name)
        self.count[f] += 1
        self.bytes[f] += size
        y = year_of(name, mtime_ns, content_year)
        if y:
            self.years[f][y] += 1
        imp = importants.category(name, f)
        if imp:
            self.imp_count[imp] += 1
            self.imp_bytes[imp] += size
            if y:
                self.imp_years[y] += 1

    @property
    def unique_n(self):
        return sum(self.count.values())

    @property
    def unique_b(self):
        return sum(self.bytes.values())

    def period(self, f):
        ys = self.years[f]
        return (min(ys), max(ys)) if ys else None

    def memories_by_year(self) -> Counter:
        """Photos et vidéos par année : la « frise » des souvenirs."""
        return self.years["photo"] + self.years["video"]

    def rows(self):
        """[(clé, libellé, nombre, octets, période)] des familles présentes, dans l'ordre d'affichage."""
        return [(k, plural, self.count[k], self.bytes[k], self.period(k))
                for k, plural, _ in FAMILIES if self.count[k]]

    def important_rows(self):
        """[(clé, libellé, nombre, octets)] des documents importants, par catégorie."""
        return [(k, label, self.imp_count[k], self.imp_bytes[k])
                for k, label, _, _ in importants.CATEGORIES if self.imp_count[k]]

    def important_period(self):
        return (min(self.imp_years), max(self.imp_years)) if self.imp_years else None

    def highlights(self, fmt_int, fmt_size) -> list[str]:
        """Quelques phrases simples qui résument le tout."""
        out = []
        if self.seen_n:
            dup_b = max(self.seen_b - self.unique_b, 0)
            out.append(f"{fmt_int(self.seen_n)} fichiers trouvés ({fmt_size(self.seen_b)}) ; une fois les "
                       f"doublons retirés, il en reste {fmt_int(self.unique_n)} ({fmt_size(self.unique_b)})"
                       + (f" : les doublons occupaient {fmt_size(dup_b)}." if dup_b else "."))
        mem = self.memories_by_year()
        if mem:
            first, last = min(mem), max(mem)
            best, n = mem.most_common(1)[0]
            out.append(f"Les photos et vidéos couvrent {last - first + 1} années, de {first} à {last} ; "
                       f"l'année la plus riche est {best} ({fmt_int(n)} photos et vidéos).")
        docs = sum(self.count[k] for k in ("Textes", "Tableurs", "Présentations", "PDF"))
        if docs:
            ys = sum((self.years[k] for k in ("Textes", "Tableurs", "Présentations", "PDF")), Counter())
            out.append(f"{fmt_int(docs)} documents" + (f", de {min(ys)} à {max(ys)}." if ys else "."))
        imp = sum(self.imp_count.values())
        if imp:
            top = ", ".join(f"{fmt_int(n)} « {label.lower()} »"
                            for _, label, n, _ in sorted(self.important_rows(), key=lambda r: -r[2])[:3])
            out.append(f"{fmt_int(imp)} documents semblent importants (identité, fiches de paie, diplômes, "
                       f"impôts…) : {top}.")
        return out

    def text(self, fmt_int, fmt_size) -> str:
        lines = [*self.highlights(fmt_int, fmt_size), ""]
        for _, label, n, b, per in self.rows():
            when = f", {per[0]}–{per[1]}" if per and per[0] != per[1] else (f", {per[0]}" if per else "")
            lines.append(f"  {fmt_int(n):>10}  {label} ({fmt_size(b)}{when})")
        if self.imp_count:
            lines += ["", "Documents qui semblent importants :"]
            for _, label, n, b in self.important_rows():
                lines.append(f"  {fmt_int(n):>10}  {label} ({fmt_size(b)})")
        return "\n".join(lines)


def from_catalog(db) -> Summary:
    """Bilan de l'archive : tout ce qui a été vu sur les anciens disques importés."""
    s = Summary()
    s.seen_n, s.seen_b = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(size),0) FROM occurrences WHERE status IN ('copied','duplicate')").fetchone()
    # Un fichier unique = une empreinte ; son nom et sa date : la plus ancienne de ses copies
    for _h, size, rel, mtime, y in db.execute(
            "SELECT o.hash, MIN(o.size), MIN(o.relpath), MIN(o.mtime_ns), MAX(m.y) FROM occurrences o "
            "LEFT JOIN media_dates m ON m.hash=o.hash WHERE o.status IN ('copied','duplicate') "
            "AND o.hash IS NOT NULL GROUP BY o.hash"):
        s.add(rel, size, mtime, y)
    return s

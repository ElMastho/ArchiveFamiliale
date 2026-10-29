"""
theme.py - Apparence de l'interface : couleurs, polices, icônes et formes arrondies.

Base : thème Sun Valley (sv_ttk, style Windows 11) quand il est installé, sinon « clam ».
Les cartes, pastilles et lignes sélectionnées sont des images arrondies dessinées ici, lissées
(anticrénelage) et à la taille de l'écran (mise à l'échelle Windows 100 % à 200 %).
Aucune dépendance obligatoire : sans sv_ttk, l'interface reste complète, simplement moins arrondie.
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

try:
    import sv_ttk
except ImportError:   # lancé depuis les sources sans « pip install sv-ttk »
    sv_ttk = None

# Couleurs : bleu (confiance) pour les actions, vert pour ce qui est fait, ambre pour ce qui attend.
BG = "#F3F5F8"
CARD = "#FFFFFF"
BORDER = "#E1E6ED"
TEXT = "#18212F"
MUTED = "#5C6878"
FAINT = "#8A94A3"
ACCENT = "#005FB8"
ACCENT_BG = "#EAF2FB"
ACCENT_BORDER = "#C7DBF2"
HOVER_BG = "#F4F7FB"
OK = "#107C41"
OK_BG = "#E9F5EE"
OK_BORDER = "#BFE3CC"
WARN = "#9D5D00"
WARN_BG = "#FFF5E1"
WARN_BORDER = "#F2D7A2"
OFF = "#6B7280"
OFF_BG = "#F1F3F5"
OFF_BORDER = "#DDE1E6"
DANGER = "#C42B1C"
STRIPE = "#F8FAFC"

# États d'une étape : (icône, couleur, fond de pastille, bord de pastille, texte de pastille)
KINDS = {
    "done": ("", OK, OK_BG, OK_BORDER, "Terminé"),
    "warn": ("", WARN, WARN_BG, WARN_BORDER, "À faire"),
    "todo": ("", FAINT, OFF_BG, OFF_BORDER, "En attente"),
    "off": ("", OFF, OFF_BG, OFF_BORDER, "Facultatif"),
}

ICON = {
    "shield": "", "drive": "", "import": "", "verify": "", "backup": "",
    "check": "", "sort": "", "sync": "", "help": "", "stop": "",
    "report": "", "list": "", "folder": "", "clock": "", "chevron": "",
    "chevron_down": "", "info": "", "done": "", "warn": "", "files": "",
    "size": "", "speed": "", "lock": "",
}

ICON_FONT = None   # famille de police d'icônes disponible (fixée par apply)
SCALE = 1.0        # facteur d'échelle de l'écran (1.0 à 100 %, 2.0 à 200 %)

_images: list = []   # garde les images en vie (sinon Tk les efface)
CENTER = 64          # taille de la partie centrale (répétée) des images arrondies


def px(n: float) -> int:
    """Taille en pixels à l'échelle de l'écran."""
    return max(1, round(n * SCALE))


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def rounded_image(master, radius: int, fill: str, border: str | None = None, behind: str = BG,
                  width: int = 1) -> tk.PhotoImage:
    """Rectangle arrondi lissé, découpable en 9 morceaux (élément image ttk, -border = radius+1)."""
    border = border or fill
    size = 2 * radius + 3
    half = size / 2
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            # distance signée au bord d'un rectangle arrondi (négative à l'intérieur)
            qx = abs(x + 0.5 - half) - (half - radius)
            qy = abs(y + 0.5 - half) - (half - radius)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius
            outer = min(max(0.5 - d, 0), 1)
            inner = min(max(0.5 - (d + width), 0), 1)
            c = _mix(behind, border, outer)
            row.append(_mix(c, fill, inner))
        rows.append(row)
    # Centre élargi : ttk remplit une carte en répétant le centre de l'image ; un centre d'un seul
    # pixel serait répété des millions de fois (fenêtre figée plusieurs secondes à l'affichage).
    c = radius + 1
    rows = [r[:c] + [r[c]] * CENTER + r[c + 1:] for r in rows]
    rows = rows[:c] + [rows[c]] * CENTER + rows[c + 1:]
    img = tk.PhotoImage(master=master, width=size - 1 + CENTER, height=size - 1 + CENTER)
    img.put(" ".join("{" + " ".join(r) + "}" for r in rows))
    _images.append(img)
    return img


def _surface(style: ttk.Style, master, name: str, fill: str, border: str, behind: str = BG, radius: int = 10):
    """Crée l'élément « <name>.bg » et les styles <name>.TFrame / <name>.TLabel / variantes."""
    r = px(radius)
    img = rounded_image(master, r, fill, border, behind)
    style.element_create(f"{name}.bg", "image", img, border=r + 1, sticky="nsew",
                         width=2 * r + 2, height=2 * r + 2)
    style.layout(f"{name}.TFrame", [(f"{name}.bg", {"sticky": "nsew"})])
    style.configure(f"{name}.TFrame", background=fill)
    style.configure(f"{name}Flat.TFrame", background=fill)   # cadre intérieur, sans bord
    for suffix, opts in (("", {"foreground": TEXT}), ("Muted", {"foreground": MUTED}),
                         ("Faint", {"foreground": FAINT}), ("Strong", {"foreground": TEXT, "font": "AFStrong"}),
                         ("Title", {"foreground": TEXT, "font": "AFSubtitle"}),
                         ("Big", {"foreground": TEXT, "font": "AFBig"}),
                         ("Kicker", {"foreground": ACCENT, "font": "AFKicker"}),
                         ("Icon", {"foreground": ACCENT, "font": "AFIcon"}),
                         ("IconBig", {"foreground": ACCENT, "font": "AFIconBig"})):
        style.configure(f"{name}{suffix}.TLabel", background=fill, **opts)
    return img


def _pill(style: ttk.Style, master, name: str, fill: str, border: str, fg: str, behind: str = CARD):
    """Pastille arrondie : style <name>.TLabel (texte court, ex. « Terminé »)."""
    r = px(9)
    img = rounded_image(master, r, fill, border, behind)
    style.element_create(f"{name}.pill", "image", img, border=r + 1, sticky="nsew",
                         width=2 * r + 2, height=2 * r + 2)
    style.layout(f"{name}.TLabel", [(f"{name}.pill", {"sticky": "nsew", "children": [
        ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
    style.configure(f"{name}.TLabel", background=fill, foreground=fg, font="AFCaptionStrong",
                    padding=(px(9), px(2), px(9), px(3)))


def apply(root: tk.Tk):
    """Applique le thème à toute l'application (à appeler une fois, avant de créer les widgets)."""
    global ICON_FONT, SCALE
    SCALE = float(root.tk.call("tk", "scaling")) / (96 / 72)
    families = set(tkfont.families(root))
    ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    text_font = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in families), "TkDefaultFont")
    strong_font = next((f for f in ("Segoe UI Variable Text Semibold", "Segoe UI Semibold") if f in families), text_font)
    display_font = next((f for f in ("Segoe UI Variable Display Semibold", "Segoe UI Semibold") if f in families),
                        text_font)

    if sv_ttk:
        sv_ttk.set_theme("light", root)
        # Sun Valley réapplique sa palette (option « *foreground »…) à l'événement <<ThemeChanged>>,
        # traité plus tard : elle écraserait les couleurs de chaque texte. On l'applique une fois
        # tout de suite, on retire ce réflexe, puis on efface la palette pour garder nos couleurs.
        root.tk.call("bind", root.winfo_class(), "<<ThemeChanged>>", "")
        try:
            root.tk.call("configure_colors")
        except tk.TclError:
            pass
        root.option_clear()
        # Les polices de Sun Valley sont en pixels : on les remet en points (suivent la mise à l'échelle).
        for name, size in (("SunValleyCaptionFont", 9), ("SunValleyBodyFont", 10), ("SunValleyBodyStrongFont", 10),
                           ("SunValleyBodyLargeFont", 13), ("SunValleySubtitleFont", 15), ("SunValleyTitleFont", 21)):
            try:
                tkfont.nametofont(name, root).configure(size=size)
            except tk.TclError:
                pass
    else:
        ttk.Style(root).theme_use("clam")

    for name, family, size, weight in (("AFBody", text_font, 10, "normal"), ("AFStrong", strong_font, 10, "normal"),
                                       ("AFCaption", text_font, 9, "normal"),
                                       ("AFCaptionStrong", strong_font, 9, "normal"),
                                       ("AFKicker", strong_font, 8, "normal"),
                                       ("AFSubtitle", display_font, 15, "normal"),
                                       ("AFTitle", display_font, 21, "normal"),
                                       ("AFBig", display_font, 17, "normal"),
                                       ("AFIcon", ICON_FONT or text_font, 14, "normal"),
                                       ("AFIconBig", ICON_FONT or text_font, 22, "normal"),
                                       ("AFIconSmall", ICON_FONT or text_font, 11, "normal"),
                                       ("AFMono", "Consolas", 9, "normal")):
        try:   # gardée en mémoire : un objet Font oublié par Python efface la police de Tk
            _images.append(tkfont.Font(root, name=name, family=family, size=size, weight=weight))
        except tk.TclError:   # déjà créée (second appel)
            tkfont.nametofont(name, root).configure(family=family, size=size, weight=weight)

    root.configure(background=BG)
    s = ttk.Style(root)
    s.configure(".", background=BG, foreground=TEXT, font="AFBody")
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("Title.TLabel", background=BG, foreground=TEXT, font="AFTitle")
    s.configure("Strong.TLabel", background=BG, foreground=TEXT, font="AFStrong")
    s.configure("Warn.TLabel", background=BG, foreground=WARN)
    s.configure("TButton", font="AFBody", padding=(px(12), px(4), px(12), px(5)))
    s.configure("Accent.TButton", font="AFStrong", padding=(px(14), px(5), px(14), px(6)))
    s.configure("Big.Accent.TButton", font="AFStrong", padding=(px(20), px(8), px(20), px(9)))
    s.configure("Toolbutton", font="AFBody", padding=(px(10), px(4), px(10), px(5)))
    s.configure("TCheckbutton", background=BG)
    s.configure("TRadiobutton", background=BG)
    s.configure("StepTitle.TRadiobutton", font="AFStrong", background=BG)
    s.configure("TProgressbar", thickness=px(6))

    # Surfaces arrondies
    _surface(s, root, "Card", CARD, BORDER, radius=12)
    _surface(s, root, "Hero", ACCENT_BG, ACCENT_BORDER, radius=14)
    _surface(s, root, "HeroOk", OK_BG, OK_BORDER, radius=14)
    _surface(s, root, "HeroWarn", WARN_BG, WARN_BORDER, radius=14)
    _surface(s, root, "Row", CARD, CARD, behind=CARD, radius=8)
    _surface(s, root, "RowHover", HOVER_BG, HOVER_BG, behind=CARD, radius=8)
    _surface(s, root, "RowSel", ACCENT_BG, ACCENT_BORDER, behind=CARD, radius=8)
    _surface(s, root, "Busy", ACCENT_BG, ACCENT_BORDER, radius=12)
    for st in ("HeroOk", "HeroOkIcon", "HeroOkIconBig", "HeroOkKicker"):
        s.configure(f"{st}.TLabel", foreground=OK if "Icon" in st or "Kicker" in st else TEXT)
    for st in ("HeroWarnIcon", "HeroWarnIconBig", "HeroWarnKicker"):
        s.configure(f"{st}.TLabel", foreground=WARN)
    # Logo : bouclier blanc sur carré bleu arrondi
    r = px(10)
    s.element_create("Logo.bg", "image", rounded_image(root, r, ACCENT, ACCENT, BG), border=r + 1, sticky="nsew",
                         width=2 * r + 2, height=2 * r + 2)
    s.layout("Logo.TLabel", [("Logo.bg", {"sticky": "nsew", "children": [
        ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
    s.configure("Logo.TLabel", background=ACCENT, foreground="#FFFFFF", font="AFIconBig",
                padding=(px(9), px(7), px(9), px(7)), anchor="center")
    # Pastilles d'état
    for kind, (_, fg, bg, bd, _) in KINDS.items():
        _pill(s, root, f"Pill{kind}", bg, bd, fg)

    # Tableaux : fond blanc arrondi, lignes plus hautes, en-têtes discrets
    r = px(8)
    s.element_create("Data.field", "image", rounded_image(root, r, CARD, BORDER, CARD), border=r + 1, sticky="nsew",
                         width=2 * r + 2, height=2 * r + 2)
    s.layout("Data.Treeview", [("Data.field", {"sticky": "nsew", "border": px(1), "children": [
        ("Treeview.padding", {"sticky": "nsew", "children": [("Treeview.treearea", {"sticky": "nsew"})]})]})])
    s.configure("Data.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, font="AFBody",
                rowheight=px(28), padding=px(3))
    s.map("Data.Treeview", background=[("selected", ACCENT_BG)], foreground=[("selected", TEXT)])
    s.configure("Data.Treeview.Heading", font="AFCaptionStrong", foreground=MUTED, padding=(px(6), px(5)))


def icon(name: str, fallback: str = "") -> str:
    """Glyphe d'icône, ou texte de secours si la police d'icônes Windows est absente."""
    return ICON[name] if ICON_FONT else fallback


def kind_glyph(kind: str) -> str:
    if ICON_FONT:
        return KINDS[kind][0]
    return {"done": "✔", "warn": "●", "todo": "○", "off": "—"}[kind]

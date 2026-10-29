"""
maj.py - Mise à jour automatique d'Archive Familiale depuis les versions publiées sur GitHub.

1. latest_release() demande à GitHub la dernière version publiée.
2. download() télécharge le bon fichier et vérifie son empreinte SHA-256 (publiée à côté, dans
   <fichier>.sha256) :
   - programme installé avec l'installateur : ArchiveFamiliale-Setup.exe ;
   - version portable (dossier décompressé du zip) : ArchiveFamiliale.zip, décompressé.
3. install_and_restart() lance un petit script PowerShell qui attend la fermeture du programme, puis :
   - installé : relance l'installateur en mode silencieux (il rouvre le programme à la fin) ;
   - portable : remplace l'exe et _internal (l'ancienne version est gardée jusqu'à la fin, et remise
     en place si la copie échoue), puis relance le programme.

Seul le programme est remplacé : l'archive, le catalogue et les réglages ne sont jamais touchés.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO = "ElMastho/ArchiveFamiliale"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_URL = f"https://github.com/{REPO}/releases/latest"
ZIP_ASSET = "ArchiveFamiliale.zip"
SETUP_ASSET = "ArchiveFamiliale-Setup.exe"
EXE_NAME = "ArchiveFamiliale.exe"
UNINSTALLER = "unins000.exe"   # présent seulement si le programme a été installé par l'installateur


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple:
    """« v2.1.0 » -> (2, 1, 0) ; les morceaux non numériques sont ignorés."""
    parts = []
    for p in text.strip().lstrip("vV").split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def _get(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": "ArchiveFamiliale",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def latest_release(timeout: float = 10) -> dict:
    """Dernière version publiée : {version, notes, page, assets: {nom: url}, sizes: {nom: taille}}."""
    try:
        with _get(API_URL, timeout) as r:
            data = json.load(r)
    except Exception as e:
        raise UpdateError(f"Impossible de joindre GitHub ({e}).") from e
    assets = {a["name"]: a for a in data.get("assets", [])}
    for name in (ZIP_ASSET, SETUP_ASSET):
        if name not in assets or name + ".sha256" not in assets:
            raise UpdateError("La dernière version publiée est incomplète.")
    return {
        "version": data.get("tag_name", "").lstrip("vV"),
        "notes": data.get("body") or "",
        "page": data.get("html_url") or PAGE_URL,
        "assets": {n: a["browser_download_url"] for n, a in assets.items()},
        "sizes": {n: a.get("size", 0) for n, a in assets.items()},
    }


def app_dir() -> str | None:
    """Dossier du programme (exe + _internal), ou None si on tourne depuis les scripts Python."""
    if not getattr(sys, "frozen", False):
        return None
    return os.path.dirname(sys.executable)


def is_installed(d: str | None = None) -> bool:
    d = d or app_dir()
    return bool(d) and os.path.exists(os.path.join(d, UNINSTALLER))


def can_self_update() -> tuple[bool, str]:
    d = app_dir()
    if not d:
        return False, "lancé depuis les scripts Python (mettez à jour avec git pull)"
    try:
        probe = tempfile.NamedTemporaryFile(dir=d, prefix=".maj-", delete=True)
        probe.close()
    except OSError:
        return False, f"le dossier du programme n'est pas modifiable ({d})"
    return True, ""


def _fetch(release: dict, name: str, dest: str, on_progress=None):
    """Télécharge un fichier publié et vérifie son empreinte SHA-256."""
    with _get(release["assets"][name + ".sha256"], 30) as r:
        expected = r.read().decode("ascii", "replace").split()[0].lower()
    h = hashlib.sha256()
    with _get(release["assets"][name], 60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or release["sizes"].get(name) or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done / total if total else None)
    if h.hexdigest() != expected:
        raise UpdateError("Le fichier téléchargé est abîmé (empreinte différente). Réessayez plus tard.")


def _extract_app(zpath: str, out: str) -> str:
    with zipfile.ZipFile(zpath) as z:
        base = os.path.realpath(out)
        for name in z.namelist():   # refuse les chemins qui sortiraient du dossier
            target = os.path.realpath(os.path.join(out, name))
            if target != base and not target.startswith(base + os.sep):
                raise UpdateError("Archive de mise à jour invalide.")
        z.extractall(out)
    for root, _dirs, files in os.walk(out):
        if EXE_NAME in files and os.path.isdir(os.path.join(root, "_internal")):
            return root
    raise UpdateError("Le programme est introuvable dans la mise à jour.")


def download(release: dict, on_progress=None, installed: bool | None = None) -> tuple[str, str]:
    """Télécharge et vérifie la nouvelle version. Renvoie (dossier temporaire, cible) : la cible est
    l'installateur (programme installé) ou le dossier décompressé qui contient l'exe (portable)."""
    installed = is_installed() if installed is None else installed
    stage = tempfile.mkdtemp(prefix="ArchiveFamiliale-maj-")
    try:
        if installed:
            target = os.path.join(stage, SETUP_ASSET)
            _fetch(release, SETUP_ASSET, target, on_progress)
            return stage, target
        zpath = os.path.join(stage, ZIP_ASSET)
        _fetch(release, ZIP_ASSET, zpath, on_progress)
        return stage, _extract_app(zpath, os.path.join(stage, "nouveau"))
    except UpdateError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError(f"Téléchargement impossible ({e}).") from e


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


SETUP_SCRIPT = r"""
$setup = {target}; $stage = {stage}
Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
$p = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -PassThru
$p.WaitForExit()   # pas -Wait : il attendrait aussi le programme relancé par l'installateur
if ($p.ExitCode -ne 0) {{
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("La mise à jour a échoué (code $($p.ExitCode)). Vous pouvez la refaire depuis le programme.", 'Archive Familiale') | Out-Null
    Start-Process -FilePath {exe}
}}
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
"""

SWAP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$app = {app}; $new = {target}; $stage = {stage}
Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
$old = Join-Path $app '_ancienne_version'
try {{
    if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Recurse -Force }}
    New-Item -ItemType Directory -Path $old | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $new -Force) {{
        $dst = Join-Path $app $item.Name
        if (Test-Path -LiteralPath $dst) {{ Move-Item -LiteralPath $dst -Destination $old }}
    }}
    foreach ($item in Get-ChildItem -LiteralPath $new -Force) {{
        Copy-Item -LiteralPath $item.FullName -Destination $app -Recurse -Force
    }}
    Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
    $err = $_.Exception.Message
    foreach ($item in Get-ChildItem -LiteralPath $new -Force) {{
        $dst = Join-Path $app $item.Name
        if (Test-Path -LiteralPath $dst) {{ Remove-Item -LiteralPath $dst -Recurse -Force -ErrorAction SilentlyContinue }}
    }}
    if (Test-Path -LiteralPath $old) {{
        Get-ChildItem -LiteralPath $old -Force | Move-Item -Destination $app -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
    }}
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("La mise à jour a échoué, l'ancienne version est conservée.`n`n$err", 'Archive Familiale') | Out-Null
}}
Start-Process -FilePath {exe} -WorkingDirectory $app
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
"""


def install_and_restart(stage: str, target: str, pid: int | None = None, app: str | None = None):
    """Lance l'installation en arrière-plan, une fois le programme fermé. L'appelant doit quitter
    le programme juste après ; il est rouvert automatiquement à la fin."""
    app = app or app_dir()
    if not app:
        raise UpdateError("Mise à jour automatique impossible depuis les scripts Python.")
    template = SETUP_SCRIPT if target.lower().endswith(".exe") else SWAP_SCRIPT
    script = template.format(app=_ps_quote(app), target=_ps_quote(target), stage=_ps_quote(stage),
                             pid=pid or os.getpid(), exe=_ps_quote(os.path.join(app, EXE_NAME)))
    path = os.path.join(stage, "installer-maj.ps1")
    with open(path, "w", encoding="utf-8-sig") as f:   # BOM : accents corrects dans PowerShell 5
        f.write(script)
    # Le script est dans $stage, qu'il efface à la fin : PowerShell l'a déjà lu en entier.
    # Pas DETACHED_PROCESS : PowerShell ne démarre pas sans console. Le script survit quand même
    # à la fermeture du programme.
    flags = 0x00000200 | 0x08000000   # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    return subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-WindowStyle", "Hidden", "-File", path],
                            creationflags=flags, close_fds=True)

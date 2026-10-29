"""Notifications sur le téléphone, par ntfy (https://ntfy.sh).

L'utilisateur installe l'application gratuite « ntfy » et s'abonne à un « sujet » : un nom secret
tiré au hasard, propre à son archive. Le programme y publie les événements importants (disque
importé, archive pleine, fin de la file…) : pas de compte, pas de mot de passe.

Rien n'est envoyé sans l'accord explicite de l'utilisateur (case cochée dans la fenêtre
« Notifications », ou « Oui » à la question posée au démarrage d'un import) : réglage « ntfy_accord ».
Les messages ne contiennent que des noms de disques et des chiffres, jamais le contenu des fichiers.
Un envoi qui échoue (pas d'Internet…) est simplement abandonné : il ne bloque jamais l'archivage.
"""
from __future__ import annotations

import json
import logging
import secrets
import string
import threading
import urllib.parse
import urllib.request

DEFAULT_SERVER = "https://ntfy.sh"
DISPLAY_NAME = "Archive Familiale"
log = logging.getLogger("archive")


def new_topic() -> str:
    """Sujet secret : impossible à deviner, mais facile à recopier (minuscules et chiffres, sans
    caractères qui se confondent)."""
    alphabet = "".join(c for c in string.ascii_lowercase + string.digits if c not in "0o1lij")
    return "archive-" + "".join(secrets.choice(alphabet) for _ in range(12))


class Notifier:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("ntfy_accord") and self.topic)

    @property
    def topic(self) -> str:
        return self.cfg.get("ntfy_sujet") or ""

    @property
    def server(self) -> str:
        return (self.cfg.get("ntfy_serveur") or DEFAULT_SERVER).rstrip("/")

    def app_link(self) -> str:
        """Lien qui ouvre l'application ntfy (Android) et s'abonne au sujet."""
        host = urllib.parse.urlsplit(self.server).netloc
        return f"ntfy://{host}/{self.topic}?display={urllib.parse.quote_plus(DISPLAY_NAME)}"

    def web_link(self) -> str:
        return f"{self.server}/{self.topic}"

    def send(self, title: str, message: str, priority: int = 3, tags=(), force=False, wait=False):
        """Publie un message (en arrière-plan). priority : 1 (discret) à 5 (urgent).
        Renvoie l'erreur éventuelle si wait=True, sinon None."""
        if not (self.enabled or force) or not self.topic:
            return None
        body = json.dumps({"topic": self.topic, "title": title, "message": message,
                           "priority": priority, "tags": list(tags)}).encode()
        result = {}

        def post():
            try:
                req = urllib.request.Request(self.server, data=body, method="POST",
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    r.read()
            except Exception as e:   # pas d'Internet, serveur indisponible… : jamais bloquant
                result["error"] = e
                log.warning("Notification non envoyée : %s", e)

        if wait:
            post()
            return result.get("error")
        threading.Thread(target=post, daemon=True).start()
        return None


def qr_matrix(text: str):
    """Matrice du QR code (liste de lignes de booléens), ou None si la bibliothèque manque."""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    return q.get_matrix()

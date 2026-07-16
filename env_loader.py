"""Chargement optionnel d'un fichier .env pour les variables d'environnement locales.

Permet de définir HEURES_SMTP_* (et d'autres réglages futurs basés sur des
variables d'environnement) dans un fichier .env local, plutôt que de devoir
les redéfinir à chaque lancement du serveur. Le fichier .env n'est jamais
versionné (voir .gitignore) : c'est là que vont les identifiants réels.
"""

import os
from pathlib import Path


def charger_env(chemin: Path | str = Path(__file__).parent / ".env") -> None:
    chemin = Path(chemin)
    if not chemin.exists():
        return

    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        cle, valeur = cle.strip(), valeur.strip()
        if cle and cle not in os.environ:
            os.environ[cle] = valeur

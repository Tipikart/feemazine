"""Suivi des dates de dernier export et dernier partage du fichier de passages.

Séparé du fichier de passages lui-même : ce sont des métadonnées sur les
actions effectuées (export, partage), pas des données de fréquentation.
Stockées dans un petit fichier JSON à part, data/suivi.json.
"""

import json
from datetime import datetime
from pathlib import Path

FICHIER_SUIVI = Path(__file__).parent / "data" / "suivi.json"


def _lire() -> dict:
    if not FICHIER_SUIVI.exists():
        return {}
    return json.loads(FICHIER_SUIVI.read_text(encoding="utf-8"))


def _ecrire(donnees: dict) -> None:
    FICHIER_SUIVI.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_SUIVI.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def enregistrer_export() -> None:
    donnees = _lire()
    donnees["dernier_export"] = datetime.now().isoformat(timespec="seconds")
    _ecrire(donnees)


def enregistrer_partage(moyen: str) -> None:
    """moyen : par exemple 'email' ou 'Google Drive'."""
    donnees = _lire()
    donnees["dernier_partage"] = datetime.now().isoformat(timespec="seconds")
    donnees["dernier_partage_moyen"] = moyen
    _ecrire(donnees)


def dernier_export() -> datetime | None:
    valeur = _lire().get("dernier_export")
    return datetime.fromisoformat(valeur) if valeur else None


def dernier_partage() -> tuple[datetime, str] | tuple[None, None]:
    donnees = _lire()
    valeur = donnees.get("dernier_partage")
    if not valeur:
        return None, None
    return datetime.fromisoformat(valeur), donnees.get("dernier_partage_moyen")

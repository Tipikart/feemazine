"""Paramètres de partage (email, Google Drive), configurables depuis l'interface.

Stockés localement dans data/parametres.json (ignoré par git : ces valeurs
ne sont jamais versionnées). Les champs sensibles (mot de passe SMTP,
identifiants du compte de service Google) ne sont jamais renvoyés en clair
au navigateur : seuls des indicateurs "déjà renseigné" sont exposés, et une
valeur vide soumise depuis un formulaire de réglages conserve la valeur
existante plutôt que de l'effacer.
"""

import json
from pathlib import Path

FICHIER_PARAMETRES = Path(__file__).parent / "data" / "parametres.json"

VALEURS_PAR_DEFAUT = {
    "smtp_serveur": "",
    "smtp_port": 587,
    "smtp_utilisateur": "",
    "smtp_mot_de_passe": "",
    "email_destinataires": [],
    "google_drive_dossier_id": "",
    "google_drive_identifiants": "",
}


def lire_parametres() -> dict:
    if not FICHIER_PARAMETRES.exists():
        return dict(VALEURS_PAR_DEFAUT)
    donnees = json.loads(FICHIER_PARAMETRES.read_text(encoding="utf-8"))
    return {**VALEURS_PAR_DEFAUT, **donnees}


def _ecrire(donnees: dict) -> None:
    FICHIER_PARAMETRES.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_PARAMETRES.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def enregistrer_parametres_email(serveur: str, port: int, utilisateur: str, mot_de_passe: str, destinataires: list[str]) -> None:
    """mot_de_passe vide = conserver le mot de passe déjà enregistré."""
    donnees = lire_parametres()
    donnees["smtp_serveur"] = serveur
    donnees["smtp_port"] = port
    donnees["smtp_utilisateur"] = utilisateur
    if mot_de_passe:
        donnees["smtp_mot_de_passe"] = mot_de_passe
    donnees["email_destinataires"] = destinataires
    _ecrire(donnees)


def enregistrer_parametres_drive(dossier_id: str, identifiants_json: str) -> None:
    """identifiants_json vide = conserver les identifiants déjà enregistrés."""
    donnees = lire_parametres()
    donnees["google_drive_dossier_id"] = dossier_id
    if identifiants_json:
        donnees["google_drive_identifiants"] = identifiants_json
    _ecrire(donnees)


def email_configure() -> bool:
    p = lire_parametres()
    return bool(p["smtp_serveur"] and p["smtp_utilisateur"] and p["smtp_mot_de_passe"] and p["email_destinataires"])


def drive_configure() -> bool:
    p = lire_parametres()
    return bool(p["google_drive_dossier_id"] and p["google_drive_identifiants"])

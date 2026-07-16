"""Partage du fichier de passages avec l'équipe : email ou Google Drive.

Les identifiants sont lus depuis parametres.py (paramétrable depuis
l'interface, jamais codés en dur). Tant qu'ils ne sont pas renseignés, ces
fonctions lèvent PartageNonConfigure au lieu d'échouer silencieusement.
"""

import smtplib
from email.message import EmailMessage

import parametres
from excel_writer import chemin_fichier, fichier_existe


class PartageNonConfigure(Exception):
    """Les identifiants nécessaires à ce moyen de partage n'ont pas encore été renseignés."""


def envoyer_par_email() -> None:
    """Envoie le fichier de passages en pièce jointe aux destinataires configurés."""
    if not fichier_existe():
        raise FileNotFoundError("Aucun fichier de passages n'existe encore.")

    if not parametres.email_configure():
        raise PartageNonConfigure(
            "L'envoi par email n'est pas encore configuré. Renseignez le serveur SMTP, "
            "l'adresse d'envoi, le mot de passe et les destinataires."
        )

    p = parametres.lire_parametres()
    chemin = chemin_fichier()

    message = EmailMessage()
    message["Subject"] = "Fée Mazine — Fichier de passages"
    message["From"] = p["smtp_utilisateur"]
    message["To"] = ", ".join(p["email_destinataires"])
    message.set_content("Bonjour,\n\nVeuillez trouver ci-joint le fichier de passages à jour.\n")
    message.add_attachment(
        chemin.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=chemin.name,
    )

    with smtplib.SMTP(p["smtp_serveur"], p["smtp_port"]) as serveur:
        serveur.starttls()
        serveur.login(p["smtp_utilisateur"], p["smtp_mot_de_passe"])
        serveur.send_message(message)


def envoyer_vers_google_drive() -> None:
    """Dépose le fichier de passages dans le dossier Google Drive configuré.

    L'envoi effectif n'est pas encore implémenté (nécessite l'ajout d'une
    bibliothèque cliente Google) : les identifiants sont enregistrés en
    préparation de cette fonctionnalité.
    """
    if not fichier_existe():
        raise FileNotFoundError("Aucun fichier de passages n'existe encore.")

    if not parametres.drive_configure():
        raise PartageNonConfigure(
            "L'envoi vers Google Drive n'est pas encore configuré. Renseignez l'identifiant "
            "du dossier et les identifiants du compte de service."
        )

    raise PartageNonConfigure(
        "Les identifiants Google Drive sont enregistrés, mais l'envoi automatique n'est pas "
        "encore implémenté dans ce pilote."
    )

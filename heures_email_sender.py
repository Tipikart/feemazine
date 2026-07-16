"""Envoi d'email pour le module Heures — isolé et remplaçable.

Configuré par variables d'environnement (HEURES_SMTP_*), pour être branché
plus tard sur l'infrastructure mail existante de l'association sans
toucher au reste du module. Si ces variables ne sont pas définies, le lien
de connexion est simplement affiché dans la console du serveur (mode
développement), pour permettre de tester le module sans serveur SMTP réel.
"""

import os
import smtplib
from email.message import EmailMessage


def _smtp_configure() -> bool:
    return bool(os.environ.get("HEURES_SMTP_SERVEUR") and os.environ.get("HEURES_SMTP_UTILISATEUR"))


def envoyer_lien_connexion(destinataire: str, lien: str) -> None:
    if not _smtp_configure():
        print(f"[heures] SMTP non configuré — lien de connexion pour {destinataire} : {lien}")
        return

    message = EmailMessage()
    message["Subject"] = "Fée Mazine — Votre lien de connexion"
    message["From"] = os.environ.get("HEURES_EMAIL_EXPEDITEUR", os.environ["HEURES_SMTP_UTILISATEUR"])
    message["To"] = destinataire
    message.set_content(
        "Bonjour,\n\n"
        "Cliquez sur ce lien pour vous connecter à l'espace Heures (valable 15 minutes) :\n"
        f"{lien}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n"
    )

    serveur_smtp = os.environ["HEURES_SMTP_SERVEUR"]
    port_smtp = int(os.environ.get("HEURES_SMTP_PORT", "587"))
    utilisateur = os.environ["HEURES_SMTP_UTILISATEUR"]
    mot_de_passe = os.environ["HEURES_SMTP_MOT_DE_PASSE"]

    if port_smtp == 465:
        with smtplib.SMTP_SSL(serveur_smtp, port_smtp) as serveur:
            serveur.login(utilisateur, mot_de_passe)
            serveur.send_message(message)
    else:
        with smtplib.SMTP(serveur_smtp, port_smtp) as serveur:
            serveur.starttls()
            serveur.login(utilisateur, mot_de_passe)
            serveur.send_message(message)

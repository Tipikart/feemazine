"""Envoi d'email pour le module Heures — isolé et remplaçable.

Configuré par variables d'environnement (HEURES_SMTP_*), pour être branché
plus tard sur l'infrastructure mail existante de l'association sans
toucher au reste du module.
"""

import os
import smtplib
from email.message import EmailMessage


def _smtp_configure() -> bool:
    return bool(os.environ.get("HEURES_SMTP_SERVEUR") and os.environ.get("HEURES_SMTP_UTILISATEUR"))


def _envoyer(destinataire: str, sujet: str, corps: str) -> None:
    if not _smtp_configure():
        print(f"[heures] SMTP non configuré — email pour {destinataire} : {sujet}")
        return

    message = EmailMessage()
    message["Subject"] = f"Fée Mazine — {sujet}"
    message["From"] = os.environ.get("HEURES_EMAIL_EXPEDITEUR", os.environ["HEURES_SMTP_UTILISATEUR"])
    message["To"] = destinataire
    message.set_content(corps)

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


def envoyer_lien_connexion(destinataire: str, lien: str) -> None:
    """Envoie un lien de connexion magique (valable 15 minutes)."""
    corps = (
        "Bonjour,\n\n"
        "Cliquez sur ce lien pour vous connecter à l'espace Heures (valable 15 minutes) :\n"
        f"{lien}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n"
    )
    _envoyer(destinataire, "Votre lien de connexion", corps)


def envoyer_notification_demande(
    lien_recup: str,
    demandeur_nom: str,
    duree_heures: float,
    justification: str,
    destinataires: list[str],
) -> None:
    """Notifie les autres membres qu'une nouvelle demande de récupération a été créée."""
    print(f"[heures] Notification aux {len(destinataires)} destinataires : {demandeur_nom} demande {duree_heures}h")
    if not _smtp_configure():
        return

    sujet = f"Nouvelle demande de récupération — {demandeur_nom}"
    corps = (
        "Bonjour,\n\n"
        f"{demandeur_nom} a soumis une demande de récupération de {duree_heures}h.\n\n"
        f"Justification : {justification}\n\n"
        f"Pour voter : {lien_recup}\n\n"
        "---\n"
        "Message automatique — Fée Mazine (heures)\n"
    )

    for dest in destinataires:
        try:
            _envoyer(dest, sujet, corps)
        except Exception as e:
            print(f"[heures] Erreur envoi email à {dest} : {e}")


def envoyer_resultat_recup(
    destinataire: str,
    demandeur_nom: str,
    duree_heures: float,
    resultat: str,  # "validee" ou "refusee"
    lien_recup: str,
) -> None:
    """Notifie le demandeur du résultat du vote sur sa demande de récupération."""
    if not _smtp_configure():
        print(f"[heures] Résultat pour {destinataire} : {duree_heures}h {resultat}")
        return

    verdict = "approuvée ✓" if resultat == "validee" else "refusée ✗"
    sujet = f"Demande de récupération {verdict}"
    corps = (
        f"Bonjour {demandeur_nom},\n\n"
        f"Votre demande de récupération de {duree_heures}h a été **{verdict}**.\n\n"
        f"Détails : {lien_recup}\n\n"
        "---\n"
        "Message automatique — Fée Mazine (heures)\n"
    )

    try:
        _envoyer(destinataire, sujet, corps)
    except Exception as e:
        print(f"[heures] Erreur envoi résultat à {destinataire} : {e}")

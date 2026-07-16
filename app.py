"""Routes FastAPI de l'application de pointage Fée Mazine.

Ce fichier ne contient que la logique web (affichage des pages, validation
des données reçues, redirections). La lecture/écriture du fichier Excel est
entièrement déléguée à excel_writer.py, et le calcul des statistiques à
statistiques.py.
"""

from datetime import date, datetime
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from env_loader import charger_env

charger_env()  # Charge .env (HEURES_SMTP_*, ...) avant tout le reste, s'il existe.

import bilan_router
import cartes_router
import heures_router
import parametres
import suivi
from excel_writer import (
    FichierVerrouille,
    chemin_fichier,
    derniere_modification,
    enregistrer_passage,
    fichier_existe,
    ouvrir_fichier,
    remplacer_fichier,
)
from heures_models import obtenir_cle_secrete
from partage import PartageNonConfigure, envoyer_par_email, envoyer_vers_google_drive
from cartes import statistiques_cartes
from cartes_models import obtenir_session_carte
from statistiques import calculer_statistiques, resume_rapide

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Cookie de session signé, utilisé par le module Heures pour l'authentification par lien magique.
app.add_middleware(SessionMiddleware, secret_key=obtenir_cle_secrete())
bilan_router.configurer(app)
cartes_router.configurer(app)
heures_router.configurer(app)

VALEURS_NOUVELLE_FAMILLE = {"Oui", "Non", "Non renseigné"}


def _rediriger_avec_message(url: str, *, erreur: str | None = None, confirmation: str | None = None) -> RedirectResponse:
    """Redirige vers `url` en transmettant un message via la query string (motif flash message)."""
    elements_url = []
    if erreur:
        elements_url.append("erreur=" + quote(erreur))
    if confirmation:
        elements_url.append("confirmation=" + quote(confirmation))
    if elements_url:
        url += "?" + "&".join(elements_url)
    return RedirectResponse(url=url, status_code=303)


def _formater_date(valeur: datetime | None) -> str:
    return valeur.strftime("%d/%m/%Y à %H:%M") if valeur else "Jamais"


def _infos_fichier() -> dict:
    """Dates de dernière modification, dernier export et dernier partage, prêtes pour l'affichage."""
    date_partage, moyen_partage = suivi.dernier_partage()
    return {
        "derniere_modification": _formater_date(derniere_modification()),
        "dernier_export": _formater_date(suivi.dernier_export()),
        "dernier_partage": _formater_date(date_partage),
        "dernier_partage_moyen": moyen_partage,
    }


def _parametres_pour_gabarit() -> dict:
    """État des paramètres de partage, prêt pour l'affichage (sans jamais exposer les secrets)."""
    p = parametres.lire_parametres()
    return {
        "email_configure": parametres.email_configure(),
        "drive_configure": parametres.drive_configure(),
        "smtp_serveur": p["smtp_serveur"],
        "smtp_port": p["smtp_port"],
        "smtp_utilisateur": p["smtp_utilisateur"],
        "smtp_mot_de_passe_defini": bool(p["smtp_mot_de_passe"]),
        "email_destinataires": ", ".join(p["email_destinataires"]),
        "google_drive_dossier_id": p["google_drive_dossier_id"],
        "google_drive_identifiants_definis": bool(p["google_drive_identifiants"]),
    }


@app.get("/", response_class=HTMLResponse)
def afficher_formulaire(request: Request, erreur: str | None = None, confirmation: str | None = None):
    return templates.TemplateResponse(
        request,
        "formulaire.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "stats": resume_rapide(),
            "infos": _infos_fichier(),
            "parametres": _parametres_pour_gabarit(),
            "actif": "accueil",
        },
    )


@app.post("/", response_class=HTMLResponse)
def valider_passage(
    request: Request,
    adultes: int = Form(...),
    enfants: int = Form(...),
    nouvelle_famille: str = Form("Non renseigné"),
):
    if nouvelle_famille not in VALEURS_NOUVELLE_FAMILLE:
        nouvelle_famille = "Non renseigné"

    if adultes < 0 or enfants < 0:
        erreur = "Les nombres d'adultes et d'enfants ne peuvent pas être négatifs."
    elif adultes == 0 and enfants == 0:
        erreur = "Impossible d'enregistrer un passage vide : au moins un adulte ou un enfant présent est requis."
    else:
        erreur = None

    if erreur:
        return templates.TemplateResponse(
            request,
            "formulaire.html",
            {
                "erreur": erreur,
                "confirmation": None,
                "stats": resume_rapide(),
                "infos": _infos_fichier(),
                "parametres": _parametres_pour_gabarit(),
                "actif": "accueil",
            },
        )

    try:
        enregistrer_passage(adultes, enfants, nouvelle_famille)
    except FichierVerrouille as erreur_verrou:
        return templates.TemplateResponse(
            request,
            "formulaire.html",
            {
                "erreur": f"{erreur_verrou} Fermez-le puis réessayez.",
                "confirmation": None,
                "stats": resume_rapide(),
                "infos": _infos_fichier(),
                "parametres": _parametres_pour_gabarit(),
                "actif": "accueil",
            },
        )

    return templates.TemplateResponse(
        request,
        "formulaire.html",
        {
            "erreur": None,
            "confirmation": "Passage enregistré avec succès.",
            "stats": resume_rapide(),
            "infos": _infos_fichier(),
            "parametres": _parametres_pour_gabarit(),
            "actif": "accueil",
        },
    )


@app.get("/statistiques", response_class=HTMLResponse)
def afficher_statistiques(
    request: Request,
    debut: str | None = None,
    fin: str | None = None,
    erreur: str | None = None,
    confirmation: str | None = None,
):
    try:
        date_debut = datetime.strptime(debut, "%Y-%m-%d").date() if debut else None
        date_fin = datetime.strptime(fin, "%Y-%m-%d").date() if fin else None
    except ValueError:
        date_debut = date_fin = None
        erreur = erreur or "Dates de filtre invalides, filtre ignoré."

    stats = calculer_statistiques(date_debut, date_fin)

    sc = None
    if stats.get("passages_carte", 0) > 0 or stats.get("familles_carte", 0) > 0:
        session_carte = next(obtenir_session_carte())
        try:
            sc = statistiques_cartes(session_carte, date_debut, date_fin)
        finally:
            session_carte.close()

    return templates.TemplateResponse(
        request,
        "statistiques.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "stats": stats,
            "stats_cartes": sc,
            "debut": debut or "",
            "fin": fin or "",
            "actif": "statistiques",
        },
    )


@app.get("/export")
def exporter_fichier():
    if not fichier_existe():
        return _rediriger_avec_message("/", erreur="Aucun fichier de passages n'existe encore.")

    suivi.enregistrer_export()
    nom_fichier = f"passages_export_{date.today().isoformat()}.xlsx"
    return FileResponse(
        chemin_fichier(),
        filename=nom_fichier,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/partager/email")
def partager_par_email():
    try:
        envoyer_par_email()
    except (FileNotFoundError, PartageNonConfigure) as erreur:
        return _rediriger_avec_message("/", erreur=str(erreur))
    except Exception as erreur:
        return _rediriger_avec_message("/", erreur=f"Échec de l'envoi par email : {erreur}")

    suivi.enregistrer_partage("email")
    return _rediriger_avec_message("/", confirmation="Fichier envoyé par email à l'équipe.")


@app.post("/partager/drive")
def partager_vers_drive():
    try:
        envoyer_vers_google_drive()
    except (FileNotFoundError, PartageNonConfigure) as erreur:
        return _rediriger_avec_message("/", erreur=str(erreur))
    except Exception as erreur:
        return _rediriger_avec_message("/", erreur=f"Échec de l'envoi vers Google Drive : {erreur}")

    suivi.enregistrer_partage("Google Drive")
    return _rediriger_avec_message("/", confirmation="Fichier envoyé vers Google Drive.")


@app.post("/parametres/email")
def enregistrer_parametres_email(
    smtp_serveur: str = Form(...),
    smtp_port: int = Form(587),
    smtp_utilisateur: str = Form(...),
    smtp_mot_de_passe: str = Form(""),
    email_destinataires: str = Form(...),
):
    destinataires = [adresse.strip() for adresse in email_destinataires.split(",") if adresse.strip()]
    parametres.enregistrer_parametres_email(
        smtp_serveur.strip(), smtp_port, smtp_utilisateur.strip(), smtp_mot_de_passe, destinataires
    )

    try:
        envoyer_par_email()
    except PartageNonConfigure as erreur:
        return _rediriger_avec_message("/", erreur=str(erreur))
    except Exception as erreur:
        return _rediriger_avec_message("/", erreur=f"Paramètres enregistrés, mais l'envoi a échoué : {erreur}")

    suivi.enregistrer_partage("email")
    return _rediriger_avec_message("/", confirmation="Paramètres enregistrés et fichier envoyé par email à l'équipe.")


@app.post("/parametres/drive")
def enregistrer_parametres_drive(
    google_drive_dossier_id: str = Form(...),
    google_drive_identifiants: str = Form(""),
):
    parametres.enregistrer_parametres_drive(google_drive_dossier_id.strip(), google_drive_identifiants.strip())
    return _rediriger_avec_message(
        "/",
        confirmation="Paramètres Google Drive enregistrés. L'envoi automatique sera disponible dans une prochaine version.",
    )


@app.post("/ouvrir")
def ouvrir_fichier_excel():
    try:
        ouvrir_fichier()
    except FileNotFoundError as erreur:
        return _rediriger_avec_message("/", erreur=str(erreur))
    except OSError as erreur:
        return _rediriger_avec_message("/", erreur=f"Impossible d'ouvrir le fichier : {erreur}")

    return _rediriger_avec_message("/", confirmation="Ouverture du fichier Excel demandée.")


@app.get("/importer", response_class=HTMLResponse)
def afficher_page_import(request: Request, erreur: str | None = None, confirmation: str | None = None):
    return templates.TemplateResponse(
        request,
        "importer.html",
        {"erreur": erreur, "confirmation": confirmation, "actif": "importer"},
    )


@app.post("/importer", response_class=HTMLResponse)
async def importer_fichier(request: Request, fichier: UploadFile = File(...)):
    contenu = await fichier.read()

    try:
        remplacer_fichier(contenu)
    except (ValueError, FichierVerrouille) as erreur:
        return templates.TemplateResponse(
            request,
            "importer.html",
            {"erreur": str(erreur), "confirmation": None, "actif": "importer"},
        )

    return _rediriger_avec_message("/statistiques", confirmation="Fichier importé avec succès.")

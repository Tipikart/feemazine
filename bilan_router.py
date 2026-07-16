"""Routes FastAPI pour le bilan CAF annuel du LAEP.

Trois volets :
- Volet 1 : heures d'activite par type CAF et par mois
- Volet 2 : frequentation annuelle (derive des passages existants)
- Volet 3 : fiche d'identite de la structure

Plus une page de synthese combinant les trois volets avec selecteur d'annee.
"""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bilan import (
    NOMS_MOIS,
    ajouter_heure,
    annees_disponibles,
    enregistrer_fiche_identite,
    frequentation_annuelle,
    lister_heures,
    minutes_en_heures,
    obtenir_fiche_identite,
    supprimer_heure,
    synthese_heures,
)
from bilan_models import (
    Accueillant,
    HeureActivite,
    TYPES_HEURES,
    initialiser_bd,
    obtenir_session_bilan,
)

routeur = APIRouter(prefix="/bilan", tags=["bilan"])
templates = Jinja2Templates(directory="templates")


def _rediriger(
    url: str,
    *,
    erreur: str | None = None,
    confirmation: str | None = None,
) -> RedirectResponse:
    params = []
    if erreur:
        params.append("erreur=" + quote(erreur))
    if confirmation:
        params.append("confirmation=" + quote(confirmation))
    if params:
        sep = "&" if "?" in url else "?"
        url += sep + "&".join(params)
    return RedirectResponse(url=url, status_code=303)


def _session():
    return next(obtenir_session_bilan())


# --- Synthese (page principale) ---


@routeur.get("/", response_class=HTMLResponse)
def afficher_synthese(
    request: Request, annee: int | None = None,
    erreur: str | None = None, confirmation: str | None = None,
):
    session = _session()
    try:
        annees = annees_disponibles(session)
        annee = annee or date.today().year

        heures = synthese_heures(session, annee)
        freq = frequentation_annuelle(annee)
        fiche = obtenir_fiche_identite(session, annee)

        return templates.TemplateResponse(
            request,
            "bilan/synthese.html",
            {
                "annee": annee,
                "annees": annees,
                "heures": heures,
                "freq": freq,
                "fiche": fiche,
                "types_heures": TYPES_HEURES,
                "noms_mois": NOMS_MOIS,
                "fmt": minutes_en_heures,
                "actif": "bilan",
                "sousnav": "synthese",
                "erreur": erreur,
                "confirmation": confirmation,
            },
        )
    finally:
        session.close()


# --- Saisie des heures ---


@routeur.get("/heures", response_class=HTMLResponse)
def afficher_heures(
    request: Request,
    annee: int | None = None,
    mois: int | None = None,
    erreur: str | None = None,
    confirmation: str | None = None,
):
    session = _session()
    try:
        annee = annee or date.today().year
        mois = mois or date.today().month

        heures = lister_heures(session, annee, mois)
        accueillants = (
            session.query(Accueillant)
            .filter(Accueillant.actif.is_(True))
            .order_by(Accueillant.nom)
            .all()
        )

        return templates.TemplateResponse(
            request,
            "bilan/heures.html",
            {
                "heures": heures,
                "accueillants": accueillants,
                "annee": annee,
                "mois": mois,
                "types_heures": TYPES_HEURES,
                "noms_mois": NOMS_MOIS,
                "fmt": minutes_en_heures,
                "actif": "bilan",
                "sousnav": "heures",
                "erreur": erreur,
                "confirmation": confirmation,
            },
        )
    finally:
        session.close()


@routeur.post("/heures", response_class=HTMLResponse)
def enregistrer_heure(
    accueillant_id: int = Form(...),
    date_activite: str = Form(...),
    type_activite: str = Form(...),
    duree_h: int = Form(0),
    duree_m: int = Form(0),
):
    session = _session()
    try:
        try:
            d = date.fromisoformat(date_activite)
        except ValueError:
            return _rediriger("/bilan/heures", erreur="Date invalide.")

        if type_activite not in TYPES_HEURES:
            return _rediriger("/bilan/heures", erreur="Type d'activite invalide.")

        duree_minutes = duree_h * 60 + duree_m
        if duree_minutes <= 0:
            return _rediriger("/bilan/heures", erreur="La duree doit etre positive.")

        accueillant = session.get(Accueillant, accueillant_id)
        if not accueillant:
            return _rediriger("/bilan/heures", erreur="Accueillant introuvable.")

        ajouter_heure(session, accueillant_id, d, type_activite, duree_minutes)

        return _rediriger(
            f"/bilan/heures?annee={d.year}&mois={d.month}",
            confirmation="Heure enregistree.",
        )
    finally:
        session.close()


@routeur.post("/heures/supprimer/{heure_id}")
def supprimer_une_heure(heure_id: int):
    session = _session()
    try:
        heure = session.get(HeureActivite, heure_id)
        annee = heure.date.year if heure else date.today().year
        mois = heure.date.month if heure else date.today().month

        if supprimer_heure(session, heure_id):
            return _rediriger(
                f"/bilan/heures?annee={annee}&mois={mois}",
                confirmation="Heure supprimee.",
            )
        return _rediriger("/bilan/heures", erreur="Heure introuvable.")
    finally:
        session.close()


# --- Accueillants ---


@routeur.get("/membres", response_class=HTMLResponse)
def afficher_membres(
    request: Request,
    erreur: str | None = None,
    confirmation: str | None = None,
):
    session = _session()
    try:
        accueillants = (
            session.query(Accueillant)
            .order_by(Accueillant.actif.desc(), Accueillant.nom)
            .all()
        )

        return templates.TemplateResponse(
            request,
            "bilan/membres.html",
            {
                "accueillants": accueillants,
                "actif": "bilan",
                "sousnav": "membres",
                "erreur": erreur,
                "confirmation": confirmation,
            },
        )
    finally:
        session.close()


@routeur.post("/membres")
def ajouter_membre(nom: str = Form(...), role: str = Form("accueillant")):
    session = _session()
    try:
        nom = nom.strip()
        if not nom:
            return _rediriger("/bilan/membres", erreur="Le nom est obligatoire.")

        session.add(Accueillant(nom=nom, role=role, actif=True))
        session.commit()
        return _rediriger("/bilan/membres", confirmation=f"{nom} ajoute.")
    finally:
        session.close()


@routeur.post("/membres/basculer/{membre_id}")
def basculer_membre(membre_id: int):
    session = _session()
    try:
        membre = session.get(Accueillant, membre_id)
        if not membre:
            return _rediriger("/bilan/membres", erreur="Accueillant introuvable.")

        membre.actif = not membre.actif
        session.commit()
        etat = "reactive" if membre.actif else "desactive"
        return _rediriger("/bilan/membres", confirmation=f"{membre.nom} {etat}.")
    finally:
        session.close()


# --- Fiche d'identite ---


@routeur.get("/fiche", response_class=HTMLResponse)
def afficher_fiche(
    request: Request,
    annee: int | None = None,
    erreur: str | None = None,
    confirmation: str | None = None,
):
    session = _session()
    try:
        annee = annee or date.today().year
        fiche = obtenir_fiche_identite(session, annee)
        annees = annees_disponibles(session)

        return templates.TemplateResponse(
            request,
            "bilan/fiche.html",
            {
                "fiche": fiche,
                "annee": annee,
                "annees": annees,
                "actif": "bilan",
                "sousnav": "fiche",
                "erreur": erreur,
                "confirmation": confirmation,
            },
        )
    finally:
        session.close()


@routeur.post("/fiche")
def enregistrer_fiche(
    annee: int = Form(...),
    lieu_dedie: str = Form(""),
    charte_signee: str = Form(""),
    supervision: str = Form(""),
    partenariat: str = Form(""),
    reseau_laep: str = Form(""),
    comite_pilotage: str = Form(""),
    observations: str = Form(""),
):
    session = _session()
    try:
        enregistrer_fiche_identite(
            session,
            annee,
            lieu_dedie=bool(lieu_dedie),
            charte_signee=bool(charte_signee),
            supervision=bool(supervision),
            partenariat=bool(partenariat),
            reseau_laep=bool(reseau_laep),
            comite_pilotage=bool(comite_pilotage),
            observations=observations.strip(),
        )
        return _rediriger(
            f"/bilan/fiche?annee={annee}",
            confirmation="Fiche enregistree.",
        )
    finally:
        session.close()


def configurer(app):
    initialiser_bd()
    app.include_router(routeur)

"""Routes du systeme de cartes pseudonymes.

Monte comme router FastAPI sous le prefixe /cartes (voir configurer() en
bas). Le passage en mode carte est aussi accessible depuis la page
d'accueil via POST /passage-carte.
"""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from cartes import (
    chercher_carte,
    creer_carte,
    enregistrer_passage_carte,
    modifier_carte,
    purger_cartes_inactives,
)
from cartes_models import (
    Carte,
    ParametreCarte,
    initialiser_bd_cartes,
    obtenir_session_carte,
)

router = APIRouter(prefix="/cartes")
templates = Jinja2Templates(directory="templates")


def _msg(*, erreur: str | None = None, confirmation: str | None = None) -> str:
    elements = []
    if erreur:
        elements.append("erreur=" + quote(erreur))
    if confirmation:
        elements.append("confirmation=" + quote(confirmation))
    return "&".join(elements)


def _extraire_enfants(form_data) -> list[dict]:
    """Extrait les donnees enfants depuis les champs numerotes du formulaire."""
    enfants = []
    i = 0
    while True:
        date_key = f"enfant_date_{i}"
        tranche_key = f"enfant_tranche_{i}"
        if date_key not in form_data and tranche_key not in form_data:
            break

        date_naissance = None
        tranche_declaree = None
        date_val = form_data.get(date_key, "").strip() if form_data.get(date_key) else ""
        tranche_val = form_data.get(tranche_key, "").strip() if form_data.get(tranche_key) else ""

        if date_val:
            try:
                date_naissance = date.fromisoformat(date_val)
            except ValueError:
                pass

        if date_naissance is None and tranche_val in ("0-3", "4-6"):
            tranche_declaree = tranche_val

        if date_naissance is not None or tranche_declaree is not None:
            enfants.append(
                {"date_naissance": date_naissance, "tranche_declaree": tranche_declaree}
            )

        i += 1

    return enfants


# --- Page principale cartes ------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def afficher_gestion(
    request: Request,
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session_carte),
):
    parametres = session.query(ParametreCarte).filter(ParametreCarte.id == 1).first()
    nb_actives = session.query(Carte).filter(Carte.actif.is_(True)).count()
    nb_inactives = session.query(Carte).filter(Carte.actif.is_(False)).count()

    return templates.TemplateResponse(
        request,
        "cartes/gestion.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "actif": "cartes",
            "sousnav": "gestion",
            "nb_actives": nb_actives,
            "nb_inactives": nb_inactives,
            "duree_purge": parametres.duree_purge_cartes_mois,
        },
    )


# --- Attribution -----------------------------------------------------------

@router.get("/attribuer", response_class=HTMLResponse)
def afficher_attribution(request: Request, erreur: str | None = None):
    return templates.TemplateResponse(
        request,
        "cartes/attribuer.html",
        {"erreur": erreur, "confirmation": None, "actif": "cartes"},
    )


@router.post("/attribuer", response_class=HTMLResponse)
async def creer_nouvelle_carte(
    request: Request,
    nb_adultes: int = Form(...),
    session: Session = Depends(obtenir_session_carte),
):
    if nb_adultes < 1:
        return RedirectResponse(
            url="/cartes/attribuer?" + _msg(erreur="Au moins un adulte requis."),
            status_code=303,
        )

    form_data = await request.form()
    enfants_data = _extraire_enfants(form_data)

    carte = creer_carte(session, nb_adultes, enfants_data)
    return RedirectResponse(url=f"/cartes/resultat/{carte.id}", status_code=303)


@router.get("/resultat/{code}", response_class=HTMLResponse)
def afficher_resultat(
    request: Request,
    code: str,
    session: Session = Depends(obtenir_session_carte),
):
    carte = chercher_carte(session, code)
    if carte is None:
        return RedirectResponse(
            url="/cartes/?" + _msg(erreur="Carte introuvable."), status_code=303
        )

    return templates.TemplateResponse(
        request,
        "cartes/resultat.html",
        {
            "erreur": None,
            "confirmation": None,
            "actif": "cartes",
            "carte": carte,
        },
    )


# --- Modification ----------------------------------------------------------

@router.get("/modifier", response_class=HTMLResponse)
def afficher_recherche_carte(request: Request, erreur: str | None = None):
    return templates.TemplateResponse(
        request,
        "cartes/chercher.html",
        {"erreur": erreur, "confirmation": None, "actif": "cartes"},
    )


@router.post("/chercher", response_class=HTMLResponse)
def chercher_pour_modifier(
    code: str = Form(...),
    session: Session = Depends(obtenir_session_carte),
):
    carte = chercher_carte(session, code)
    if carte is None:
        return RedirectResponse(
            url="/cartes/modifier?" + _msg(erreur="Aucune carte trouvee avec ce code."),
            status_code=303,
        )
    if not carte.actif:
        return RedirectResponse(
            url="/cartes/modifier?" + _msg(erreur="Cette carte a ete desactivee (purge automatique)."),
            status_code=303,
        )
    return RedirectResponse(url=f"/cartes/modifier/{carte.id}", status_code=303)


@router.get("/modifier/{code}", response_class=HTMLResponse)
def afficher_modification(
    request: Request,
    code: str,
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session_carte),
):
    carte = chercher_carte(session, code)
    if carte is None:
        return RedirectResponse(
            url="/cartes/modifier?" + _msg(erreur="Carte introuvable."),
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "cartes/modifier.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "actif": "cartes",
            "carte": carte,
        },
    )


@router.post("/modifier/{code}", response_class=HTMLResponse)
async def enregistrer_modification(
    request: Request,
    code: str,
    nb_adultes: int = Form(...),
    session: Session = Depends(obtenir_session_carte),
):
    carte = chercher_carte(session, code)
    if carte is None:
        return RedirectResponse(
            url="/cartes/modifier?" + _msg(erreur="Carte introuvable."),
            status_code=303,
        )

    if nb_adultes < 1:
        return RedirectResponse(
            url=f"/cartes/modifier/{code}?" + _msg(erreur="Au moins un adulte requis."),
            status_code=303,
        )

    form_data = await request.form()
    enfants_data = _extraire_enfants(form_data)
    modifier_carte(session, carte, nb_adultes, enfants_data)

    return RedirectResponse(
        url=f"/cartes/modifier/{code}?" + _msg(confirmation="Fiche mise a jour."),
        status_code=303,
    )


# --- Parametres ------------------------------------------------------------

@router.post("/parametres")
def enregistrer_parametres(
    duree_purge: int = Form(...),
    session: Session = Depends(obtenir_session_carte),
):
    if duree_purge < 1:
        return RedirectResponse(
            url="/cartes/?" + _msg(erreur="La duree de purge doit etre au moins 1 mois."),
            status_code=303,
        )
    parametres = session.query(ParametreCarte).filter(ParametreCarte.id == 1).first()
    parametres.duree_purge_cartes_mois = duree_purge
    session.commit()
    return RedirectResponse(
        url="/cartes/?" + _msg(confirmation="Parametres mis a jour."),
        status_code=303,
    )


# --- Integration -----------------------------------------------------------

def configurer(app) -> None:
    """Monte le router cartes, initialise la BD, lance la purge au demarrage."""
    initialiser_bd_cartes()
    app.include_router(router)

    session = next(obtenir_session_carte())
    try:
        nb = purger_cartes_inactives(session)
        if nb > 0:
            print(f"[cartes] Purge au demarrage : {nb} carte(s) desactivee(s).")
    finally:
        session.close()

    from excel_writer import FichierVerrouille

    from datetime import date, datetime, time
    from bilan_models import Accueillant, HeureActivite, initialiser_bd, obtenir_session_bilan

    initialiser_bd()

    from excel_writer import lire_tous_les_passages

    @app.post("/passage-carte")
    def passage_avec_carte(code: str = Form(...)):
        session = next(obtenir_session_carte())
        try:
            carte = chercher_carte(session, code)
            if carte is None:
                return RedirectResponse(
                    url="/?" + _msg(erreur=f"Code inconnu : {code}. Verifiez la saisie ou attribuez une nouvelle carte."),
                    status_code=303,
                )
            if not carte.actif:
                return RedirectResponse(
                    url="/?" + _msg(erreur="Cette carte a ete desactivee. Contactez un accueillant."),
                    status_code=303,
                )

            # Verifier doublon : meme carte deja enregistree aujourd'hui
            from tz_helpers import aujourdhui
            aujd_str = aujourdhui().isoformat()
            passages = lire_tous_les_passages()
            deja_passe = any(
                p.get("date") == aujd_str and p.get("carte_id") == code.upper()
                for p in passages
            )
            if deja_passe:
                return RedirectResponse(
                    url="/?" + _msg(erreur=f"Cette carte ({code}) a deja ete enregistree aujourd'hui."),
                    status_code=303,
                )

            try:
                enregistrer_passage_carte(session, carte)
            except FichierVerrouille as e:
                return RedirectResponse(
                    url="/?" + _msg(erreur=f"{e} Fermez-le puis reessayez."),
                    status_code=303,
                )

            # Verifier si une plage ouverture existe pour aujourd'hui
            from bilan_models import HeureActivite, obtenir_session_bilan
            session_bilan2 = next(obtenir_session_bilan())
            try:
                plage_existe = session_bilan2.query(HeureActivite).filter(
                    HeureActivite.date == aujourdhui(),
                    HeureActivite.type == "ouverture_public",
                ).first() is not None
            finally:
                session_bilan2.close()

            dest = "/" if plage_existe else "/ouverture"
            return RedirectResponse(
                url=dest + "?" + _msg(confirmation=f"Passage enregistre (carte {code})."),
                status_code=303,
            )
        finally:
            session.close()

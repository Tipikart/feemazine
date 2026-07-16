"""Routes et logique métier du module Heures (suivi du temps de l'équipe).

Monté comme router FastAPI additionnel sur l'application principale (voir
configurer() en bas de fichier, appelée depuis app.py), sous le préfixe
/heures. Conçu pour rester autonome : si ce module est un jour extrait
dans son propre projet, seul l'appel à configurer(app) change.
"""

import calendar
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from heures_auth import (
    AccesRefuse,
    NonAuthentifie,
    consommer_jeton,
    generer_jeton,
    membre_admin,
    membre_connecte,
)
from heures_email_sender import envoyer_lien_connexion
from heures_models import (
    DELAI_MODIFICATION,
    Horaire,
    Membre,
    Parametre,
    Salaire,
    Validation,
    initialiser_bd,
    obtenir_session,
)

router = APIRouter(prefix="/heures")
templates = Jinja2Templates(directory="templates")


# --- Aides de calcul ---------------------------------------------------

def _plage_periode(periode: str, reference: date) -> tuple[date, date]:
    if periode == "jour":
        return reference, reference
    if periode == "semaine":
        debut = reference - timedelta(days=reference.weekday())
        return debut, debut + timedelta(days=6)
    if periode == "annee":
        return date(reference.year, 1, 1), date(reference.year, 12, 31)
    dernier_jour = calendar.monthrange(reference.year, reference.month)[1]
    return reference.replace(day=1), reference.replace(day=dernier_jour)


def _duree_heures(horaire: Horaire) -> float:
    delta = datetime.combine(date.min, horaire.heure_depart) - datetime.combine(date.min, horaire.heure_arrivee)
    return round(delta.total_seconds() / 3600, 2)


def _jours_ouverture(debut: date, fin: date) -> list[date]:
    """Jours d'ouverture = jours de semaine (lundi-vendredi) de la période."""
    jours = []
    jour = debut
    while jour <= fin:
        if jour.weekday() < 5:
            jours.append(jour)
        jour += timedelta(days=1)
    return jours


def _salaire_applicable(session: Session, membre_id: int, a_la_date: date) -> Salaire | None:
    return (
        session.query(Salaire)
        .filter(Salaire.membre_id == membre_id, Salaire.date_effet <= a_la_date)
        .order_by(Salaire.date_effet.desc())
        .first()
    )


def _taux_horaire_moyen_mois_courant(session: Session, membre_id: int) -> float | None:
    """Salaire brut mensuel applicable ce mois-ci, divisé par les heures validées ce mois-ci."""
    aujourdhui = date.today()
    dernier_jour = calendar.monthrange(aujourdhui.year, aujourdhui.month)[1]
    debut_mois = aujourdhui.replace(day=1)
    fin_mois = aujourdhui.replace(day=dernier_jour)

    salaire = _salaire_applicable(session, membre_id, fin_mois)
    if salaire is None:
        return None

    horaires_valides = (
        session.query(Horaire)
        .filter(
            Horaire.membre_id == membre_id,
            Horaire.statut == "validé",
            Horaire.date >= debut_mois,
            Horaire.date <= fin_mois,
        )
        .all()
    )
    total_heures = sum(_duree_heures(h) for h in horaires_valides)
    if total_heures <= 0:
        return None
    return round(salaire.salaire_brut_mensuel / total_heures, 2)


def _peut_modifier(horaire: Horaire) -> bool:
    return horaire.statut != "validé" and datetime.now() <= horaire.modifiable_jusqu_a


def _horaire_pour_affichage(horaire: Horaire, avec_membre: bool = False) -> dict:
    donnees = {
        "id": horaire.id,
        "date": horaire.date.isoformat(),
        "date_affichage": horaire.date.strftime("%d/%m/%Y"),
        "heure_arrivee": horaire.heure_arrivee.strftime("%H:%M"),
        "heure_depart": horaire.heure_depart.strftime("%H:%M"),
        "heures": _duree_heures(horaire),
        "statut": horaire.statut,
        "peut_modifier": _peut_modifier(horaire),
        "nb_validations": len(horaire.validations),
    }
    if avec_membre:
        donnees["membre_nom"] = horaire.membre.nom
    return donnees


def _horaires_a_valider(session: Session, membre: Membre) -> list[Horaire]:
    deja_valides = session.query(Validation.horaire_id).filter(Validation.validateur_id == membre.id).subquery()
    return (
        session.query(Horaire)
        .filter(
            Horaire.membre_id != membre.id,
            Horaire.statut == "déclaré",
            ~Horaire.id.in_(deja_valides),
        )
        .order_by(Horaire.date.desc())
        .all()
    )


def _graphique(periode: str, horaires: list[Horaire], debut: date, fin: date) -> list[dict]:
    """Données d'un graphique en barres : par jour, sauf pour l'année (par mois)."""
    heures_par_jour: dict[date, float] = {}
    for h in horaires:
        heures_par_jour[h.date] = heures_par_jour.get(h.date, 0) + _duree_heures(h)

    points = []
    if periode == "annee":
        heures_par_mois: dict[date, float] = {}
        for jour, heures in heures_par_jour.items():
            cle = jour.replace(day=1)
            heures_par_mois[cle] = heures_par_mois.get(cle, 0) + heures
        mois = debut.replace(day=1)
        while mois <= fin:
            points.append((mois.strftime("%m/%Y"), heures_par_mois.get(mois, 0)))
            mois = date(mois.year + 1, 1, 1) if mois.month == 12 else date(mois.year, mois.month + 1, 1)
    else:
        format_libelle = "%d" if periode == "mois" else "%d/%m"
        jour = debut
        while jour <= fin:
            points.append((jour.strftime(format_libelle), heures_par_jour.get(jour, 0)))
            jour += timedelta(days=1)

    max_heures = max((h for _, h in points), default=0) or 1
    return [
        {"libelle": libelle, "heures": round(heures, 2), "hauteur_pct": round((heures / max_heures) * 100, 1)}
        for libelle, heures in points
    ]


def _msg(*, erreur: str | None = None, confirmation: str | None = None) -> str:
    elements = []
    if erreur:
        elements.append("erreur=" + quote(erreur))
    if confirmation:
        elements.append("confirmation=" + quote(confirmation))
    return "&".join(elements)


# --- Connexion (lien magique) -------------------------------------------

def _rendre_connexion(request: Request, **kwargs):
    contexte = {
        "erreur": None, "confirmation": None, "actif": "heures",
        "email": "", "proposer_creation": False, "lien_envoye": False,
    }
    contexte.update(kwargs)
    return templates.TemplateResponse(request, "heures/connexion.html", contexte)


def _envoyer_lien(request: Request, session: Session, membre: Membre) -> None:
    jeton = generer_jeton(session, membre)
    lien = str(request.base_url).rstrip("/") + f"/heures/connexion/verifier?jeton={jeton}"
    envoyer_lien_connexion(membre.email, lien)


@router.get("/connexion", response_class=HTMLResponse)
def afficher_connexion(request: Request, erreur: str | None = None):
    return _rendre_connexion(request, erreur=erreur)


@router.post("/connexion", response_class=HTMLResponse)
def demander_lien(request: Request, email: str = Form(...), session: Session = Depends(obtenir_session)):
    email = email.strip().lower()
    membre = session.query(Membre).filter(Membre.email == email).first()

    if membre is None:
        return _rendre_connexion(request, email=email, proposer_creation=True)

    if not membre.actif:
        return _rendre_connexion(request, email=email, erreur="Ce compte est désactivé. Contactez un administrateur.")

    _envoyer_lien(request, session, membre)
    return _rendre_connexion(request, email=email, lien_envoye=True)


@router.post("/connexion/creer-profil", response_class=HTMLResponse)
def creer_profil(
    request: Request,
    nom: str = Form(...),
    email: str = Form(...),
    session: Session = Depends(obtenir_session),
):
    email = email.strip().lower()
    nom = nom.strip()

    if session.query(Membre).filter(Membre.email == email).first() is not None:
        return _rendre_connexion(request, email=email, erreur="Un profil existe déjà pour cet email.")

    # Le tout premier membre créé sur une base vide devient admin : sans cela,
    # personne ne pourrait jamais accéder à l'espace admin pour promouvoir qui que ce soit.
    premier_membre = session.query(Membre).count() == 0
    membre = Membre(nom=nom, email=email, role="admin" if premier_membre else "membre", actif=True)
    session.add(membre)
    session.commit()

    _envoyer_lien(request, session, membre)
    return _rendre_connexion(request, email=email, lien_envoye=True)


@router.get("/connexion/verifier")
def verifier_lien(request: Request, jeton: str, session: Session = Depends(obtenir_session)):
    membre = consommer_jeton(session, jeton)
    if membre is None:
        url = "/heures/connexion?" + _msg(erreur="Lien invalide ou expiré. Redemandez un lien de connexion.")
        return RedirectResponse(url=url, status_code=303)

    request.session["membre_id"] = membre.id
    return RedirectResponse(url="/heures/", status_code=303)


@router.get("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse(url="/heures/connexion", status_code=303)


# --- Espace personnel ----------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def espace_personnel(
    request: Request,
    periode: str = "mois",
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    aujourdhui = date.today()
    debut, fin = _plage_periode(periode, aujourdhui)

    horaires = (
        session.query(Horaire)
        .filter(Horaire.membre_id == membre.id, Horaire.date >= debut, Horaire.date <= fin)
        .order_by(Horaire.date.desc())
        .all()
    )

    return templates.TemplateResponse(
        request,
        "heures/espace_personnel.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "actif": "heures",
            "souspage": "personnel",
            "membre_courant": membre,
            "horaires": [_horaire_pour_affichage(h) for h in horaires],
            "total_heures": round(sum(_duree_heures(h) for h in horaires), 2),
            "periode": periode,
            "taux_horaire": _taux_horaire_moyen_mois_courant(session, membre.id),
            "graphique": _graphique(periode, horaires, debut, fin),
            "horaires_a_valider": [_horaire_pour_affichage(h, avec_membre=True) for h in _horaires_a_valider(session, membre)],
            "aujourdhui": aujourdhui.isoformat(),
            "delai_modification_heures": int(DELAI_MODIFICATION.total_seconds() // 3600),
            "seuil_validation": session.get(Parametre, 1).seuil_validation,
        },
    )


@router.post("/declarer")
def declarer_horaire(
    date_saisie: str = Form(...),
    heure_arrivee: str = Form(...),
    heure_depart: str = Form(...),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    try:
        jour = date.fromisoformat(date_saisie)
        arrivee = time.fromisoformat(heure_arrivee)
        depart = time.fromisoformat(heure_depart)
    except ValueError:
        return RedirectResponse(url="/heures/?" + _msg(erreur="Date ou heure invalide."), status_code=303)

    if depart <= arrivee:
        url = "/heures/?" + _msg(erreur="L'heure de départ doit être après l'heure d'arrivée.")
        return RedirectResponse(url=url, status_code=303)

    existant = session.query(Horaire).filter(Horaire.membre_id == membre.id, Horaire.date == jour).first()

    if existant is not None:
        if not _peut_modifier(existant):
            url = "/heures/?" + _msg(erreur="Ce jour n'est plus modifiable (délai dépassé ou horaire déjà validé).")
            return RedirectResponse(url=url, status_code=303)
        existant.heure_arrivee = arrivee
        existant.heure_depart = depart
        # Les validations déjà obtenues portaient sur les horaires précédents : elles ne
        # tiennent plus après une correction, il faut les valider à nouveau.
        for validation in list(existant.validations):
            session.delete(validation)
        existant.statut = "déclaré"
    else:
        maintenant = datetime.now()
        session.add(
            Horaire(
                membre_id=membre.id,
                date=jour,
                heure_arrivee=arrivee,
                heure_depart=depart,
                statut="déclaré",
                cree_le=maintenant,
                modifiable_jusqu_a=maintenant + DELAI_MODIFICATION,
            )
        )
    session.commit()

    return RedirectResponse(url="/heures/?" + _msg(confirmation="Horaire enregistré."), status_code=303)


@router.post("/valider/{horaire_id}")
def valider_horaire(
    horaire_id: int,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    horaire = session.get(Horaire, horaire_id)
    if horaire is None:
        return RedirectResponse(url="/heures/?" + _msg(erreur="Horaire introuvable."), status_code=303)

    if horaire.membre_id == membre.id:
        url = "/heures/?" + _msg(erreur="Vous ne pouvez pas valider vos propres horaires.")
        return RedirectResponse(url=url, status_code=303)

    if horaire.statut == "validé":
        return RedirectResponse(url="/heures/?" + _msg(erreur="Cet horaire est déjà validé."), status_code=303)

    if session.query(Validation).filter_by(horaire_id=horaire.id, validateur_id=membre.id).first() is not None:
        return RedirectResponse(url="/heures/?" + _msg(erreur="Vous avez déjà validé cet horaire."), status_code=303)

    try:
        session.add(Validation(horaire_id=horaire.id, validateur_id=membre.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        return RedirectResponse(url="/heures/?" + _msg(erreur="Vous avez déjà validé cet horaire."), status_code=303)

    seuil = session.get(Parametre, 1).seuil_validation
    nb_validations = session.query(Validation).filter_by(horaire_id=horaire.id).count()
    if nb_validations >= seuil:
        horaire.statut = "validé"
        session.commit()

    return RedirectResponse(url="/heures/?" + _msg(confirmation="Validation enregistrée."), status_code=303)


# --- Vue équipe ------------------------------------------------------------

@router.get("/equipe", response_class=HTMLResponse)
def vue_equipe(
    request: Request,
    periode: str = "mois",
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    aujourdhui = date.today()
    debut, fin = _plage_periode(periode, aujourdhui)
    jours_ouvres = len(_jours_ouverture(debut, fin))

    membres = session.query(Membre).filter(Membre.actif.is_(True)).order_by(Membre.nom).all()
    lignes = []
    for m in membres:
        horaires_m = (
            session.query(Horaire)
            .filter(Horaire.membre_id == m.id, Horaire.date >= debut, Horaire.date <= fin)
            .all()
        )
        jours_presents = len({h.date for h in horaires_m})
        lignes.append(
            {
                "id": m.id,
                "nom": m.nom,
                "total_heures": round(sum(_duree_heures(h) for h in horaires_m), 2),
                "taux_presence": round((jours_presents / jours_ouvres) * 100) if jours_ouvres else 0,
            }
        )

    lignes.sort(key=lambda ligne: ligne["total_heures"], reverse=True)
    meilleur = lignes[0] if lignes and lignes[0]["total_heures"] > 0 else None

    return templates.TemplateResponse(
        request,
        "heures/vue_equipe.html",
        {
            "erreur": None, "confirmation": None, "actif": "heures", "souspage": "equipe",
            "membre_courant": membre, "periode": periode, "lignes": lignes, "meilleur": meilleur,
        },
    )


@router.get("/equipe/{membre_id}", response_class=HTMLResponse)
def fiche_membre(
    membre_id: int,
    request: Request,
    periode: str = "mois",
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    membre_cible = session.get(Membre, membre_id)
    if membre_cible is None:
        return RedirectResponse(url="/heures/equipe", status_code=303)

    aujourdhui = date.today()
    debut, fin = _plage_periode(periode, aujourdhui)
    horaires = (
        session.query(Horaire)
        .filter(Horaire.membre_id == membre_id, Horaire.date >= debut, Horaire.date <= fin)
        .order_by(Horaire.date.desc())
        .all()
    )

    peut_voir_taux = membre.id == membre_cible.id or membre.role == "admin"

    return templates.TemplateResponse(
        request,
        "heures/membre_detail.html",
        {
            "erreur": None, "confirmation": None, "actif": "heures", "souspage": "equipe",
            "membre_courant": membre, "membre_cible": membre_cible,
            "horaires": [_horaire_pour_affichage(h) for h in horaires],
            "total_heures": round(sum(_duree_heures(h) for h in horaires), 2),
            "periode": periode,
            "taux_horaire": _taux_horaire_moyen_mois_courant(session, membre_id) if peut_voir_taux else None,
            "peut_voir_taux": peut_voir_taux,
            "graphique": _graphique(periode, horaires, debut, fin),
        },
    )


# --- Espace admin ----------------------------------------------------------

@router.get("/admin", response_class=HTMLResponse)
def afficher_admin(
    request: Request,
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    membres = session.query(Membre).order_by(Membre.actif.desc(), Membre.nom).all()
    aujourdhui = date.today()
    lignes = []
    for m in membres:
        salaire = _salaire_applicable(session, m.id, aujourdhui)
        lignes.append(
            {
                "id": m.id, "nom": m.nom, "email": m.email, "role": m.role, "actif": m.actif,
                "salaire_actuel": salaire.salaire_brut_mensuel if salaire else None,
                "taux_horaire": _taux_horaire_moyen_mois_courant(session, m.id),
            }
        )

    return templates.TemplateResponse(
        request,
        "heures/admin.html",
        {
            "erreur": erreur, "confirmation": confirmation, "actif": "heures", "souspage": "admin",
            "membre_courant": membre, "lignes": lignes,
            "seuil_validation": session.get(Parametre, 1).seuil_validation,
        },
    )


@router.post("/admin/membres")
def ajouter_membre(
    nom: str = Form(...),
    email: str = Form(...),
    role: str = Form("membre"),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    email = email.strip().lower()
    nom = nom.strip()
    if role not in {"membre", "admin"}:
        role = "membre"

    if session.query(Membre).filter(Membre.email == email).first() is not None:
        url = "/heures/admin?" + _msg(erreur="Un membre existe déjà avec cet email.")
        return RedirectResponse(url=url, status_code=303)

    session.add(Membre(nom=nom, email=email, role=role, actif=True))
    session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Membre ajouté."), status_code=303)


@router.post("/admin/membres/{membre_id}/desactiver")
def desactiver_membre(
    membre_id: int,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    if membre_id == membre.id:
        url = "/heures/admin?" + _msg(erreur="Vous ne pouvez pas désactiver votre propre compte.")
        return RedirectResponse(url=url, status_code=303)

    cible = session.get(Membre, membre_id)
    if cible is not None:
        cible.actif = False
        session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Membre désactivé."), status_code=303)


@router.post("/admin/membres/{membre_id}/reactiver")
def reactiver_membre(
    membre_id: int,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    cible = session.get(Membre, membre_id)
    if cible is not None:
        cible.actif = True
        session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Membre réactivé."), status_code=303)


@router.post("/admin/salaires")
def ajouter_salaire(
    membre_id: int = Form(...),
    salaire_brut_mensuel: float = Form(...),
    date_effet: str = Form(...),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    try:
        jour_effet = date.fromisoformat(date_effet)
    except ValueError:
        return RedirectResponse(url="/heures/admin?" + _msg(erreur="Date d'effet invalide."), status_code=303)

    if salaire_brut_mensuel <= 0:
        return RedirectResponse(url="/heures/admin?" + _msg(erreur="Le salaire doit être positif."), status_code=303)

    session.add(Salaire(membre_id=membre_id, salaire_brut_mensuel=salaire_brut_mensuel, date_effet=jour_effet))
    session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Nouveau salaire enregistré."), status_code=303)


@router.post("/admin/parametres")
def modifier_parametres(
    seuil_validation: int = Form(...),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    if seuil_validation < 1:
        return RedirectResponse(url="/heures/admin?" + _msg(erreur="Le seuil doit être au moins 1."), status_code=303)

    parametre = session.get(Parametre, 1)
    parametre.seuil_validation = seuil_validation
    session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Seuil de validation mis à jour."), status_code=303)


# --- Intégration -------------------------------------------------------

def configurer(app) -> None:
    """Monte le router Heures sur l'application FastAPI principale.

    Initialise la base SQLite du module et enregistre les gestionnaires
    d'erreurs qui transforment les échecs d'authentification/autorisation
    en redirections propres plutôt qu'en erreurs 500.
    """
    initialiser_bd()
    app.include_router(router)

    @app.exception_handler(NonAuthentifie)
    def _gerer_non_authentifie(request: Request, exc: NonAuthentifie):
        return RedirectResponse(url="/heures/connexion", status_code=303)

    @app.exception_handler(AccesRefuse)
    def _gerer_acces_refuse(request: Request, exc: AccesRefuse):
        return RedirectResponse(url="/heures/", status_code=303)

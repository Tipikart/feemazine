"""Routes et logique métier du module Heures (suivi des heures et récupération).

Monté comme router FastAPI additionnel sur l'application principale (voir
configurer() en bas de fichier, appelée depuis app.py), sous le préfixe
/heures. Conçu pour rester autonome.
"""

import calendar
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from heures_auth import (
    AccesRefuse,
    NonAuthentifie,
    consommer_jeton,
    generer_jeton,
    membre_admin,
    membre_connecte,
)
from heures_email_sender import envoyer_lien_connexion, envoyer_notification_demande, envoyer_resultat_recup
from heures_models import (
    DELAI_MODIFICATION,
    DemandeRecup,
    HeuresPrevues,
    Horaire,
    Membre,
    Parametre,
    ValidationRecup,
    calculer_seuil_majorite,
    calculer_solde,
    initialiser_bd,
    obtenir_session,
)

router = APIRouter(prefix="/heures")
templates = Jinja2Templates(directory="templates")


# ── Aides ───────────────────────────────────────────────────────────────


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


def _horaire_pour_affichage(horaire: Horaire, avec_membre: bool = False) -> dict:
    donnees = {
        "id": horaire.id,
        "date": horaire.date.isoformat(),
        "date_affichage": horaire.date.strftime("%d/%m/%Y"),
        "heure_arrivee": horaire.heure_arrivee.strftime("%H:%M"),
        "heure_depart": horaire.heure_depart.strftime("%H:%M"),
        "heures": _duree_heures(horaire),
    }
    if avec_membre:
        donnees["membre_nom"] = horaire.membre.nom
    return donnees


def _graphique(periode: str, horaires: list[Horaire], debut: date, fin: date) -> list[dict]:
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


# ── Connexion (lien magique) — inchangé ─────────────────────────────────


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


# ── Espace personnel (déclaration + solde) ──────────────────────────────


@router.get("/", response_class=HTMLResponse)
def espace_personnel(
    request: Request,
    periode: str = "mois",
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    from tz_helpers import aujourdhui as aujourdhui_reunion
    aujd = aujourdhui_reunion()
    debut, fin = _plage_periode(periode, aujd)
    date_min = (aujd - timedelta(days=2)).isoformat()

    horaires = (
        session.query(Horaire)
        .filter(Horaire.membre_id == membre.id, Horaire.date >= debut, Horaire.date <= fin)
        .order_by(Horaire.date.desc())
        .all()
    )

    solde = calculer_solde(session, membre.id)

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
            "graphique": _graphique(periode, horaires, debut, fin),
            "aujourdhui": aujd.isoformat(),
            "date_min": date_min,
            "date_max": aujd.isoformat(),
            "solde": solde,
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

    maintenant = datetime.now()
    existant = session.query(Horaire).filter(Horaire.membre_id == membre.id, Horaire.date == jour).first()

    if existant is not None:
        if maintenant > existant.modifiable_jusqu_a:
            url = "/heures/?" + _msg(erreur="Ce jour n'est plus modifiable (délai dépassé).")
            return RedirectResponse(url=url, status_code=303)
        existant.heure_arrivee = arrivee
        existant.heure_depart = depart
    else:
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


# ── Demande de récupération ─────────────────────────────────────────────


@router.post("/demander-recup")
def demander_recup(
    request: Request,
    date_recup: str = Form(...),
    duree_heures: float = Form(...),
    justification: str = Form(...),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    try:
        jour = date.fromisoformat(date_recup)
    except ValueError:
        return RedirectResponse(url="/heures/?" + _msg(erreur="Date de récupération invalide."), status_code=303)

    if duree_heures <= 0:
        return RedirectResponse(url="/heures/?" + _msg(erreur="La durée doit être positive."), status_code=303)

    justification = justification.strip()
    if not justification:
        return RedirectResponse(url="/heures/?" + _msg(erreur="La justification est obligatoire."), status_code=303)

    solde = calculer_solde(session, membre.id)
    avertissement = None
    if duree_heures > solde["solde_disponible"]:
        avertissement = (
            f"⚠ La durée demandée ({duree_heures}h) dépasse votre solde disponible "
            f"({solde['solde_disponible']}h). La demande sera soumise malgré tout."
        )

    demande = DemandeRecup(
        membre_id=membre.id,
        date_recup=jour,
        duree_heures=duree_heures,
        justification=justification,
        statut="en_attente",
    )
    session.add(demande)
    session.commit()

    # Notification par email à tous les autres membres actifs
    autres_membres = (
        session.query(Membre.email)
        .filter(Membre.actif.is_(True), Membre.id != membre.id)
        .all()
    )
    destinataires = [m.email for m in autres_membres]
    # URL complète avec le préfixe nginx (/feemazine/) que FastAPI ne voit pas
    lien = str(request.base_url) + "feemazine/heures/recuperation"
    envoyer_notification_demande(
        lien_recup=lien,
        demandeur_nom=membre.nom,
        duree_heures=demande.duree_heures,
        justification=demande.justification,
        destinataires=destinataires,
    )

    url = "/heures/recuperation?" + _msg(confirmation="Demande de récupération soumise.")
    if avertissement:
        url += "&" + quote(avertissement)
    return RedirectResponse(url=url, status_code=303)


# ── Vue partagée des demandes de récupération ───────────────────────────


@router.get("/recuperation", response_class=HTMLResponse, name="vue_recuperation")
def vue_recuperation(
    request: Request,
    erreur: str | None = None,
    confirmation: str | None = None,
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    demandes = (
        session.query(DemandeRecup)
        .order_by(DemandeRecup.cree_le.desc())
        .all()
    )

    solde = calculer_solde(session, membre.id)
    seuil_majorite = calculer_seuil_majorite(session)

    demandes_vue = []
    for d in demandes:
        votes_valide = [v for v in d.validations if v.decision == "valide"]
        votes_refuse = [v for v in d.validations if v.decision == "refuse"]
        mon_vote = next((v for v in d.validations if v.validateur_id == membre.id), None)
        peut_voter = (
            d.statut == "en_attente"
            and d.membre_id != membre.id
            and mon_vote is None
        )

        demandes_vue.append({
            "demande": d,
            "demandeur_nom": d.demandeur.nom,
            "date_recup_affichage": d.date_recup.strftime("%d/%m/%Y"),
            "cree_le_affichage": d.cree_le.strftime("%d/%m/%Y %H:%M"),
            "nb_valide": len(votes_valide),
            "nb_refuse": len(votes_refuse),
            "validations": [
                {
                    "validateur_nom": v.validateur.nom,
                    "decision": v.decision,
                    "commentaire": v.commentaire,
                    "date_vote": v.date_validation.strftime("%d/%m/%Y %H:%M"),
                }
                for v in d.validations
            ],
            "peut_voter": peut_voter,
            "est_mien": d.membre_id == membre.id,
        })

    return templates.TemplateResponse(
        request,
        "heures/recuperation.html",
        {
            "erreur": erreur,
            "confirmation": confirmation,
            "actif": "heures",
            "souspage": "recuperation",
            "membre_courant": membre,
            "demandes": demandes_vue,
            "solde": solde,
            "seuil_majorite": seuil_majorite,
        },
    )


@router.post("/recuperation/{demande_id}/voter")
def voter_recup(
    demande_id: int,
    request: Request,
    decision: str = Form(...),
    commentaire: str = Form(""),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    demande = session.get(DemandeRecup, demande_id)
    if demande is None:
        return RedirectResponse(url="/heures/recuperation?" + _msg(erreur="Demande introuvable."), status_code=303)

    if demande.statut != "en_attente":
        return RedirectResponse(url="/heures/recuperation?" + _msg(erreur="Cette demande est déjà traitée."), status_code=303)

    if demande.membre_id == membre.id:
        url = "/heures/recuperation?" + _msg(erreur="Vous ne pouvez pas voter sur votre propre demande.")
        return RedirectResponse(url=url, status_code=303)

    if decision not in ("valide", "refuse"):
        return RedirectResponse(url="/heures/recuperation?" + _msg(erreur="Décision invalide."), status_code=303)

    vote_existant = (
        session.query(ValidationRecup)
        .filter_by(demande_id=demande_id, validateur_id=membre.id)
        .first()
    )
    if vote_existant is not None:
        url = "/heures/recuperation?" + _msg(erreur="Vous avez déjà voté sur cette demande.")
        return RedirectResponse(url=url, status_code=303)

    session.add(ValidationRecup(
        demande_id=demande_id,
        validateur_id=membre.id,
        decision=decision,
        commentaire=commentaire.strip() or None,
    ))
    session.commit()

    # Vérifier les seuils (majorité simple dynamique)
    seuil = calculer_seuil_majorite(session)
    nb_valide = (
        session.query(func.count(ValidationRecup.id))
        .filter_by(demande_id=demande_id, decision="valide")
        .scalar()
    )
    nb_refuse = (
        session.query(func.count(ValidationRecup.id))
        .filter_by(demande_id=demande_id, decision="refuse")
        .scalar()
    )

    if nb_valide >= seuil:
        demande.statut = "validee"
        session.commit()
        envoyer_resultat_recup(
            destinataire=demande.demandeur.email,
            demandeur_nom=demande.demandeur.nom,
            duree_heures=demande.duree_heures,
            resultat="validee",
            lien_recup=str(request.base_url) + "feemazine/heures/recuperation",
        )
        return RedirectResponse(
            url="/heures/recuperation?" + _msg(confirmation=f"Demande approuvée (majorité {seuil}.{seuil})."),
            status_code=303,
        )
    elif nb_refuse >= seuil:
        demande.statut = "refusee"
        session.commit()
        envoyer_resultat_recup(
            destinataire=demande.demandeur.email,
            demandeur_nom=demande.demandeur.nom,
            duree_heures=demande.duree_heures,
            resultat="refusee",
            lien_recup=str(request.base_url) + "feemazine/heures/recuperation",
        )
        return RedirectResponse(
            url="/heures/recuperation?" + _msg(confirmation=f"Demande refusée (majorité {seuil}.{seuil})."),
            status_code=303,
        )

    return RedirectResponse(
        url="/heures/recuperation?" + _msg(confirmation=f"Vote enregistré ({nb_valide}/{seuil} valide, {nb_refuse}/{seuil} refus)."),
        status_code=303,
    )


# ── Vue équipe ──────────────────────────────────────────────────────────


@router.get("/equipe", response_class=HTMLResponse)
def vue_equipe(
    request: Request,
    periode: str = "mois",
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_connecte),
):
    aujourdhui = date.today()
    debut, fin = _plage_periode(periode, aujourdhui)

    membres = session.query(Membre).filter(Membre.actif.is_(True)).order_by(Membre.nom).all()
    lignes = []
    for m in membres:
        horaires_m = (
            session.query(Horaire)
            .filter(Horaire.membre_id == m.id, Horaire.date >= debut, Horaire.date <= fin)
            .all()
        )
        solde = calculer_solde(session, m.id)
        lignes.append({
            "id": m.id,
            "nom": m.nom,
            "total_heures": round(sum(_duree_heures(h) for h in horaires_m), 2),
            "solde": solde["solde_disponible"],
        })

    return templates.TemplateResponse(
        request,
        "heures/vue_equipe.html",
        {
            "erreur": None, "confirmation": None, "actif": "heures", "souspage": "equipe",
            "membre_courant": membre, "periode": periode, "lignes": lignes,
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
    solde = calculer_solde(session, membre_id)

    return templates.TemplateResponse(
        request,
        "heures/membre_detail.html",
        {
            "erreur": None, "confirmation": None, "actif": "heures", "souspage": "equipe",
            "membre_courant": membre, "membre_cible": membre_cible,
            "horaires": [_horaire_pour_affichage(h) for h in horaires],
            "total_heures": round(sum(_duree_heures(h) for h in horaires), 2),
            "periode": periode,
            "graphique": _graphique(periode, horaires, debut, fin),
            "solde": solde,
        },
    )


# ── Espace admin ────────────────────────────────────────────────────────


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
        solde = calculer_solde(session, m.id)
        hp = (
            session.query(HeuresPrevues)
            .filter(HeuresPrevues.membre_id == m.id)
            .order_by(HeuresPrevues.date_effet.desc())
            .first()
        )
        lignes.append({
            "id": m.id, "nom": m.nom, "email": m.email, "role": m.role, "actif": m.actif,
            "heures_prevues": hp.heures_par_semaine if hp else None,
            "derniere_date_effet": hp.date_effet.isoformat() if hp else None,
            "total_travaille": solde["total_travaille"],
            "solde": solde["solde_disponible"],
        })

    return templates.TemplateResponse(
        request,
        "heures/admin.html",
        {
            "erreur": erreur, "confirmation": confirmation, "actif": "heures", "souspage": "admin",
            "membre_courant": membre, "lignes": lignes,
            "seuil_majorite": calculer_seuil_majorite(session),
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


@router.post("/admin/heures-prevues")
def definir_heures_prevues(
    membre_id: int = Form(...),
    heures_par_semaine: float = Form(...),
    date_effet: str = Form(...),
    session: Session = Depends(obtenir_session),
    membre: Membre = Depends(membre_admin),
):
    try:
        jour_effet = date.fromisoformat(date_effet)
    except ValueError:
        return RedirectResponse(url="/heures/admin?" + _msg(erreur="Date d'effet invalide."), status_code=303)

    if heures_par_semaine < 0:
        return RedirectResponse(url="/heures/admin?" + _msg(erreur="Le nombre d'heures ne peut pas être négatif."), status_code=303)

    session.add(HeuresPrevues(membre_id=membre_id, heures_par_semaine=heures_par_semaine, date_effet=jour_effet))
    session.commit()
    return RedirectResponse(url="/heures/admin?" + _msg(confirmation="Heures prévues enregistrées."), status_code=303)





# ── Intégration ──────────────────────────────────────────────────────────


def configurer(app) -> None:
    """Monte le router Heures sur l'application FastAPI principale."""
    initialiser_bd()
    app.include_router(router)

    @app.exception_handler(NonAuthentifie)
    def _gerer_non_authentifie(request: Request, exc: NonAuthentifie):
        return RedirectResponse(url="/heures/connexion", status_code=303)

    @app.exception_handler(AccesRefuse)
    def _gerer_acces_refuse(request: Request, exc: AccesRefuse):
        return RedirectResponse(url="/heures/", status_code=303)

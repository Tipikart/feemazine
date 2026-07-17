"""Logique metier du bilan CAF annuel.

Calculs derives (heures d'organisation, heures de fonctionnement, nombre de
seances) : JAMAIS stockes, toujours calcules a l'affichage.

Pas de nouvelle approximation au-dela de celles documentees dans le module
cartes.
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import extract
from sqlalchemy.orm import Session

from bilan_models import (
    Accueillant,
    FicheIdentite,
    HeureActivite,
    TYPES_HEURES,
    TYPES_ORGANISATION,
)

NOMS_MOIS = {
    1: "Janvier",
    2: "Fevrier",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Aout",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Decembre",
}


def ajouter_heure(
    session: Session,
    accueillant_id: int,
    date_activite: date,
    type_activite: str,
    duree_minutes: int,
    heure_debut: str | None = None,
    heure_fin: str | None = None,
) -> HeureActivite:
    if type_activite not in TYPES_HEURES:
        raise ValueError(f"Type d'activite invalide : {type_activite}")
    if duree_minutes <= 0:
        raise ValueError("La duree doit etre positive.")

    heure = HeureActivite(
        accueillant_id=accueillant_id,
        date=date_activite,
        type=type_activite,
        duree_minutes=duree_minutes,
        heure_debut=heure_debut,
        heure_fin=heure_fin,
    )
    session.add(heure)
    session.commit()
    return heure


def supprimer_heure(session: Session, heure_id: int) -> bool:
    heure = session.get(HeureActivite, heure_id)
    if not heure:
        return False
    session.delete(heure)
    session.commit()
    return True


def lister_heures(
    session: Session, annee: int, mois: int | None = None
) -> list[HeureActivite]:
    q = (
        session.query(HeureActivite)
        .join(Accueillant)
        .filter(extract("year", HeureActivite.date) == annee)
    )
    if mois:
        q = q.filter(extract("month", HeureActivite.date) == mois)
    return q.order_by(HeureActivite.date.desc()).all()


def synthese_heures(session: Session, annee: int) -> dict:
    """Synthese des heures pour une annee : totaux par type et par mois.

    Heures d'organisation et de fonctionnement CALCULEES, jamais stockees.
    """
    heures = (
        session.query(HeureActivite)
        .filter(extract("year", HeureActivite.date) == annee)
        .all()
    )

    par_mois: dict[int, dict[str, int]] = defaultdict(
        lambda: {t: 0 for t in TYPES_HEURES}
    )
    totaux_type: dict[str, int] = {t: 0 for t in TYPES_HEURES}
    dates_ouverture: set[date] = set()

    for h in heures:
        mois = h.date.month
        par_mois[mois][h.type] += h.duree_minutes
        totaux_type[h.type] += h.duree_minutes
        if h.type == "ouverture_public":
            dates_ouverture.add(h.date)

    total_organisation = sum(totaux_type[t] for t in TYPES_ORGANISATION)
    total_ouverture = totaux_type["ouverture_public"]
    total_fonctionnement = total_ouverture + total_organisation

    par_mois_derive = {}
    for m in range(1, 13):
        donnees = par_mois[m]
        org = sum(donnees[t] for t in TYPES_ORGANISATION)
        par_mois_derive[m] = {
            **donnees,
            "organisation": org,
            "fonctionnement": donnees["ouverture_public"] + org,
            "total_mois": sum(donnees.values()),
        }

    return {
        "par_mois": par_mois_derive,
        "totaux_type": totaux_type,
        "total_organisation": total_organisation,
        "total_ouverture": total_ouverture,
        "total_fonctionnement": total_fonctionnement,
        "nb_seances": len(dates_ouverture),
    }


def frequentation_annuelle(annee: int) -> dict:
    """Frequentation pour une annee, derivee des passages existants."""
    from cartes import statistiques_cartes
    from cartes_models import obtenir_session_carte
    from statistiques import calculer_statistiques

    date_debut = date(annee, 1, 1)
    date_fin = date(annee, 12, 31)

    stats = calculer_statistiques(date_debut, date_fin)

    stats_c = None
    if stats.get("passages_carte", 0) > 0 or stats.get("familles_carte", 0) > 0:
        session_carte = next(obtenir_session_carte())
        try:
            stats_c = statistiques_cartes(session_carte, date_debut, date_fin)
        finally:
            session_carte.close()

    return {
        "total_passages": stats["total_passages"],
        "total_adultes": stats["total_adultes"],
        "total_enfants": stats["total_enfants"],
        "total_personnes": stats["total_personnes"],
        "passages_carte": stats.get("passages_carte", 0),
        "passages_anonyme": stats.get("passages_anonyme", 0),
        "familles_carte": stats.get("familles_carte", 0),
        "nouvelles_familles": stats.get("nouvelles_familles", {}),
        "stats_cartes": stats_c,
    }


def obtenir_fiche_identite(
    session: Session, annee: int
) -> FicheIdentite | None:
    return (
        session.query(FicheIdentite)
        .filter(FicheIdentite.annee == annee)
        .first()
    )


def enregistrer_fiche_identite(
    session: Session,
    annee: int,
    lieu_dedie: bool,
    charte_signee: bool,
    supervision: bool,
    partenariat: bool,
    reseau_laep: bool,
    comite_pilotage: bool,
    observations: str,
) -> FicheIdentite:
    fiche = obtenir_fiche_identite(session, annee)
    if fiche is None:
        fiche = FicheIdentite(annee=annee)
        session.add(fiche)

    fiche.lieu_dedie = lieu_dedie
    fiche.charte_signee = charte_signee
    fiche.supervision = supervision
    fiche.partenariat = partenariat
    fiche.reseau_laep = reseau_laep
    fiche.comite_pilotage = comite_pilotage
    fiche.observations = observations

    session.commit()
    return fiche


def annees_disponibles(session: Session) -> list[int]:
    """Annees pour lesquelles des heures ou une fiche existent."""
    annees: set[int] = set()

    for (a,) in (
        session.query(extract("year", HeureActivite.date).label("a"))
        .distinct()
        .all()
    ):
        annees.add(int(a))

    for (a,) in session.query(FicheIdentite.annee).distinct().all():
        annees.add(a)

    annees.add(date.today().year)
    return sorted(annees, reverse=True)


def minutes_en_heures(minutes: int) -> str:
    if minutes == 0:
        return "—"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h{m:02d}"

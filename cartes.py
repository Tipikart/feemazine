"""Logique metier du systeme de cartes pseudonymes.

Gestion des cartes (attribution, modification, purge) et enregistrement
de passages en mode carte. Les cartes sont un identifiant pseudonyme
persistant -- pas anonyme -- qui permet de relier plusieurs passages a la
meme famille pour un comptage certifie. Aucune donnee d'identite directe
n'est stockee.

Limites documentees (voir aussi README) :

- Le nombre de "parents differents" additionne le nb_adultes declare par
  carte active sur la periode, sans distinguer si c'est le meme parent ou
  l'autre qui se presente d'une visite a l'autre. C'est une approximation.

- Le nombre de "familles differentes" combine les cartes distinctes actives
  et les familles comptees en mode anonyme (approximation declarative).
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from cartes_models import (
    Carte,
    EnfantCarte,
    ParametreCarte,
    date_il_y_a_mois,
    generer_code_carte,
)
from excel_writer import lire_tous_les_passages


def creer_carte(
    session: Session, nb_adultes: int, enfants_data: list[dict]
) -> Carte:
    for _ in range(10):
        code = generer_code_carte()
        if session.get(Carte, code) is None:
            break
    else:
        raise RuntimeError("Impossible de generer un code unique.")

    carte = Carte(
        id=code,
        nb_adultes=nb_adultes,
        date_attribution=date.today(),
        actif=True,
        derniere_maj=datetime.now(),
    )
    session.add(carte)

    for enfant in enfants_data:
        session.add(
            EnfantCarte(
                carte_id=code,
                date_naissance=enfant.get("date_naissance"),
                tranche_declaree=enfant.get("tranche_declaree"),
            )
        )

    session.commit()
    return carte


def chercher_carte(session: Session, code: str) -> Carte | None:
    return session.get(Carte, code.upper().strip())


def modifier_carte(
    session: Session, carte: Carte, nb_adultes: int, enfants_data: list[dict]
) -> None:
    carte.nb_adultes = nb_adultes
    carte.derniere_maj = datetime.now()

    for enfant in list(carte.enfants):
        session.delete(enfant)

    for enfant in enfants_data:
        session.add(
            EnfantCarte(
                carte_id=carte.id,
                date_naissance=enfant.get("date_naissance"),
                tranche_declaree=enfant.get("tranche_declaree"),
            )
        )

    session.commit()


def enregistrer_passage_carte(session: Session, carte: Carte) -> None:
    """Enregistre un passage en mode carte.

    Duplique nb_adultes et le nombre d'enfants dans le passage Excel pour
    garder un historique fidele meme si la fiche est modifiee plus tard.
    nouvelle_famille est automatique : vrai si premier passage pour cette carte.
    """
    from excel_writer import enregistrer_passage

    nb_enfants = len(carte.enfants)
    est_nouveau = carte.premier_passage_le is None

    enregistrer_passage(
        adultes=carte.nb_adultes,
        enfants=nb_enfants,
        nouvelle_famille="Oui" if est_nouveau else "Non",
        mode="carte",
        carte_id=carte.id,
    )

    if est_nouveau:
        carte.premier_passage_le = datetime.now()
        session.commit()


def purger_cartes_inactives(session: Session) -> int:
    """Desactive les cartes sans passage recent, supprime leurs enfants.

    Les passages deja enregistres dans le fichier Excel ne sont pas
    supprimes : ils ne contiennent que des compteurs historiques, pas
    de lien exploitable vers une identite une fois la carte purgee.
    """
    parametres = session.get(ParametreCarte, 1)
    date_limite = date_il_y_a_mois(parametres.duree_purge_cartes_mois)

    passages = lire_tous_les_passages()
    dernier_passage_par_carte: dict[str, date] = {}
    for p in passages:
        carte_id = p.get("carte_id")
        if not carte_id:
            continue
        d = p["date"]
        if isinstance(d, datetime):
            d = d.date()
        elif isinstance(d, str):
            d = date.fromisoformat(d)
        if carte_id not in dernier_passage_par_carte or d > dernier_passage_par_carte[carte_id]:
            dernier_passage_par_carte[carte_id] = d

    cartes_actives = session.query(Carte).filter(Carte.actif.is_(True)).all()
    nb_purgees = 0

    for carte in cartes_actives:
        dernier = dernier_passage_par_carte.get(carte.id)
        reference = dernier if dernier else carte.date_attribution
        if reference < date_limite:
            carte.actif = False
            for enfant in list(carte.enfants):
                session.delete(enfant)
            nb_purgees += 1

    if nb_purgees > 0:
        session.commit()

    return nb_purgees


def statistiques_cartes(
    session: Session, date_debut: date | None = None, date_fin: date | None = None
) -> dict:
    """Statistiques complementaires liees aux cartes pour la periode.

    Le nombre de "parents differents" additionne le nb_adultes declare par
    carte active sur la periode, sans distinguer si c'est le meme parent ou
    l'autre qui se presente. C'est une approximation a documenter face a la CAF.
    """
    passages = lire_tous_les_passages()

    cartes_ids_periode: set[str] = set()
    passages_carte = 0
    passages_anonyme = 0
    nouvelles_anonyme_oui = 0

    for p in passages:
        d = p["date"]
        if isinstance(d, datetime):
            d = d.date()
        elif isinstance(d, str):
            d = date.fromisoformat(d)
        if date_debut and d < date_debut:
            continue
        if date_fin and d > date_fin:
            continue

        mode = p.get("mode", "anonyme")
        if mode == "carte" and p.get("carte_id"):
            cartes_ids_periode.add(p["carte_id"])
            passages_carte += 1
        else:
            passages_anonyme += 1
            if p.get("nouvelle_famille") == "Oui":
                nouvelles_anonyme_oui += 1

    parents_differents = 0
    tranches: dict[str, int] = {}
    for carte_id in cartes_ids_periode:
        carte = session.get(Carte, carte_id)
        if carte:
            parents_differents += carte.nb_adultes
            for enfant in carte.enfants:
                tranche = enfant.tranche_age()
                tranches[tranche] = tranches.get(tranche, 0) + 1

    return {
        "familles_carte": len(cartes_ids_periode),
        "familles_anonyme_declarees": nouvelles_anonyme_oui,
        "familles_total_approx": len(cartes_ids_periode) + nouvelles_anonyme_oui,
        "parents_differents_approx": parents_differents,
        "passages_carte": passages_carte,
        "passages_anonyme": passages_anonyme,
        "tranches_age": dict(sorted(tranches.items())),
        "cartes_actives_total": session.query(Carte).filter(Carte.actif.is_(True)).count(),
    }

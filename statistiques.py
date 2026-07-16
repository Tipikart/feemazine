"""Calcul des statistiques de frequentation a partir des passages enregistres.

Toutes les statistiques sont calculees a la volee depuis le fichier Excel.
Aucune donnee individuelle n'est manipulee : uniquement des comptages agreges.

Limites du comptage (voir aussi README) :

- "Familles differentes" combine les cartes distinctes (comptage exact) et
  les familles declarees en mode anonyme (approximation declarative). Ce
  chiffre ne garantit pas un decompte exact face a la CAF.

- "Parents differents" additionne le nb_adultes declare par carte, sans
  distinguer si c'est le meme parent ou l'autre qui se presente.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from excel_writer import lire_tous_les_passages

VALEURS_NOUVELLE_FAMILLE = ["Oui", "Non", "Non renseigne"]


def _vers_date(valeur) -> date:
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    return datetime.strptime(str(valeur), "%Y-%m-%d").date()


def calculer_statistiques(date_debut: date | None = None, date_fin: date | None = None) -> dict:
    passages = []
    for ligne in lire_tous_les_passages():
        jour = _vers_date(ligne["date"])
        if date_debut and jour < date_debut:
            continue
        if date_fin and jour > date_fin:
            continue
        passages.append({**ligne, "date_obj": jour})

    nouvelles_familles = {valeur: 0 for valeur in VALEURS_NOUVELLE_FAMILLE}
    par_jour = defaultdict(int)
    par_semaine = defaultdict(int)
    par_mois = defaultdict(int)
    par_annee = defaultdict(int)

    cartes_distinctes: set[str] = set()
    passages_carte = 0
    passages_anonyme = 0

    for ligne in passages:
        cle_famille = ligne["nouvelle_famille"] if ligne["nouvelle_famille"] in nouvelles_familles else "Non renseigne"
        nouvelles_familles[cle_famille] += 1

        jour = ligne["date_obj"]
        par_jour[jour.isoformat()] += 1
        annee, semaine, _ = jour.isocalendar()
        par_semaine[f"{annee}-S{semaine:02d}"] += 1
        par_mois[jour.strftime("%Y-%m")] += 1
        par_annee[jour.strftime("%Y")] += 1

        mode = ligne.get("mode", "anonyme")
        if mode == "carte" and ligne.get("carte_id"):
            cartes_distinctes.add(ligne["carte_id"])
            passages_carte += 1
        else:
            passages_anonyme += 1

    total_adultes = sum(ligne["adultes"] for ligne in passages)
    total_enfants = sum(ligne["enfants"] for ligne in passages)

    return {
        "total_passages": len(passages),
        "total_adultes": total_adultes,
        "total_enfants": total_enfants,
        "total_personnes": total_adultes + total_enfants,
        "nouvelles_familles": nouvelles_familles,
        "par_jour": dict(sorted(par_jour.items(), reverse=True)),
        "par_semaine": dict(sorted(par_semaine.items(), reverse=True)),
        "par_mois": dict(sorted(par_mois.items(), reverse=True)),
        "par_annee": dict(sorted(par_annee.items(), reverse=True)),
        "familles_carte": len(cartes_distinctes),
        "passages_carte": passages_carte,
        "passages_anonyme": passages_anonyme,
    }


def resume_rapide() -> dict:
    passages = lire_tous_les_passages()
    dates = [_vers_date(ligne["date"]) for ligne in passages]

    aujourdhui = date.today()
    debut_semaine = aujourdhui - timedelta(days=aujourdhui.weekday())
    debut_mois = aujourdhui.replace(day=1)
    debut_annee = aujourdhui.replace(month=1, day=1)

    return {
        "aujourdhui": sum(1 for jour in dates if jour == aujourdhui),
        "semaine": sum(1 for jour in dates if debut_semaine <= jour <= aujourdhui),
        "mois": sum(1 for jour in dates if debut_mois <= jour <= aujourdhui),
        "annee": sum(1 for jour in dates if debut_annee <= jour <= aujourdhui),
    }

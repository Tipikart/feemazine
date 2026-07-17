"""Authentification par lien magique (sans mot de passe) pour le module Heures.

Le jeton est un identifiant aléatoire à usage unique, stocké en base avec
une expiration courte (voir DUREE_VALIDITE_JETON), jamais réutilisable une
fois consommé. La session est gérée par le SessionMiddleware de Starlette
(cookie signé, voir app.py) : elle ne contient que l'identifiant du membre
connecté, jamais de mot de passe.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from heures_models import JetonConnexion, Membre, obtenir_session

DUREE_VALIDITE_JETON = timedelta(minutes=15)


class NonAuthentifie(Exception):
    """Aucune session valide : l'appelant doit être redirigé vers la connexion."""


class AccesRefuse(Exception):
    """Session valide mais droits insuffisants (ex. route réservée aux admins)."""


def generer_jeton(session: Session, membre: Membre) -> str:
    jeton = secrets.token_urlsafe(32)
    session.add(
        JetonConnexion(
            membre_id=membre.id,
            jeton=jeton,
            expire_le=datetime.now() + DUREE_VALIDITE_JETON,
        )
    )
    session.commit()
    return jeton


def consommer_jeton(session: Session, jeton: str) -> Membre | None:
    """Valide et marque comme utilisé un jeton. Retourne le membre associé, ou None si invalide."""
    entree = session.query(JetonConnexion).filter_by(jeton=jeton).first()
    if entree is None or entree.utilise_le is not None or entree.expire_le < datetime.now():
        return None
    entree.utilise_le = datetime.now()
    session.commit()
    return session.get(Membre, entree.membre_id)


def membre_connecte(request: Request, session: Session = Depends(obtenir_session)) -> Membre:
    """Dépendance FastAPI : membre actuellement connecté, ou lève NonAuthentifie."""
    membre_id = request.session.get("membre_id")
    membre = session.get(Membre, membre_id) if membre_id else None
    if membre is None or not membre.actif:
        raise NonAuthentifie()
    return membre


def membre_admin(membre: Membre = Depends(membre_connecte)) -> Membre:
    """Dépendance FastAPI : membre connecté ET administrateur, ou lève AccesRefuse."""
    if membre.role != "admin":
        raise AccesRefuse()
    return membre

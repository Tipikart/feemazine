"""Authentification globale par email + mot de passe pour Fée Mazine.

Chaque membre de la table membres (heures.db) peut se connecter avec
son email et un mot de passe haché par bcrypt. La session est gérée
par le SessionMiddleware de Starlette (déjà en place dans app.py).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from heures_models import Membre, SessionLocale, obtenir_session

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Chemins accessibles sans authentification
CHEMINS_PUBLICS = frozenset({"/login", "/logout"})
PREFIXES_PUBLICS = ("/static/", "/heures/connexion")


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str | None) -> bool:
    """Vérifie un mot de passe contre un hash bcrypt.

    Retourne False si le hash est absent (compte sans mot de passe).
    """
    if not hash_stocke:
        return False
    try:
        return pwd_context.verify(mot_de_passe, hash_stocke)
    except Exception:
        return False


def chemin_public(chemin: str) -> bool:
    """Retourne True si le chemin ne nécessite pas d'authentification."""
    if chemin in CHEMINS_PUBLICS:
        return True
    for prefixe in PREFIXES_PUBLICS:
        if chemin.startswith(prefixe):
            return True
    return False


@router.get("/login", response_class=HTMLResponse)
def afficher_login(request: Request, erreur: str | None = None):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"erreur": erreur},
    )


@router.post("/login", response_class=HTMLResponse)
def valider_login(
    request: Request,
    email: str = Form(...),
    mot_de_passe: str = Form(...),
    session: Session = Depends(obtenir_session),
):
    email = email.strip().lower()
    membre = session.query(Membre).filter(Membre.email == email).first()

    if membre is None or not verifier_mot_de_passe(mot_de_passe, membre.mot_de_passe_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erreur": "Email ou mot de passe incorrect."},
            status_code=403,
        )

    if not membre.actif:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erreur": "Ce compte est désactivé."},
            status_code=403,
        )

    request.session["membre_id"] = membre.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


def configurer(app) -> None:
    """Monte les routes d'authentification sur l'application et ajoute le middleware."""
    app.include_router(router)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if chemin_public(request.url.path):
            return await call_next(request)

        membre_id = request.session.get("membre_id")
        if not membre_id:
            return RedirectResponse(url="/login", status_code=303)

        # Injecte le rôle dans request.state pour les templates
        request.state.membre_id = membre_id
        session = SessionLocale()
        try:
            membre = session.query(Membre).filter(Membre.id == membre_id).first()
            request.state.est_admin = membre is not None and membre.role == "admin"
        finally:
            session.close()

        return await call_next(request)

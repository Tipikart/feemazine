#!/usr/bin/env python3
"""Crée ou met à jour un utilisateur avec mot de passe pour Fée Mazine.

Usage :
    python3 creer_utilisateur.py email mot_de_passe [nom]

Le mot de passe est haché avec bcrypt avant stockage. Si l'email existe
déjà dans la table membres, seul le mot de passe est mis à jour (le nom
peut aussi être modifié si fourni).
"""

import os
import sys
from pathlib import Path

# Ajoute le dossier du projet au chemin Python
sys.path.insert(0, str(Path(__file__).parent))

from env_loader import charger_env

charger_env()

from passlib.context import CryptContext
from heures_models import (
    Membre,
    SessionLocale,
    initialiser_bd,
    migrer_ajouter_mot_de_passe_hash,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def creer_utilisateur(email: str, mot_de_passe: str, nom: str | None = None) -> None:
    initialiser_bd()
    migrer_ajouter_mot_de_passe_hash()

    session = SessionLocale()
    try:
        hash_pwd = pwd_context.hash(mot_de_passe)
        membre = session.query(Membre).filter(Membre.email == email).first()

        if membre:
            membre.mot_de_passe_hash = hash_pwd
            if nom:
                membre.nom = nom
            print(f"✓ Mot de passe mis à jour pour {email}")
        else:
            membre = Membre(
                nom=nom or email.split("@")[0],
                email=email,
                mot_de_passe_hash=hash_pwd,
                actif=True,
            )
            session.add(membre)
            print(f"✓ Utilisateur créé : {email}")

        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage : python3 creer_utilisateur.py email mot_de_passe [nom] [--admin]", file=sys.stderr)
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    mot_de_passe = sys.argv[2]
    nom = None
    role = "membre"

    for arg in sys.argv[3:]:
        if arg == "--admin":
            role = "admin"
        elif nom is None:
            nom = arg

    creer_utilisateur(email, mot_de_passe, nom)

    # Met à jour le rôle si demandé
    from heures_models import SessionLocale
    s = SessionLocale()
    try:
        m = s.query(Membre).filter(Membre.email == email).first()
        if m and m.role != role:
            m.role = role
            s.commit()
            print(f"→ Rôle défini : {role}")
    finally:
        s.close()

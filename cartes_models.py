"""Modeles SQLAlchemy pour le systeme de cartes pseudonymes.

Les cartes permettent un comptage certifie de familles distinctes au LAEP
sans jamais collecter de donnee d'identite directe (nom, prenom). Un code
pseudonyme -- pas anonyme -- permet de relier plusieurs passages a la meme
carte pour un comptage fiable. Le mode carte reste strictement optionnel :
une famille qui refuse la carte continue d'etre comptee via le mode anonyme.
"""

import secrets
import string
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
FICHIER_BD = DATA_DIR / "cartes.db"

Base = declarative_base()

_ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "OI01L"
)


def generer_code_carte() -> str:
    """Code pseudonyme XXXX-XXXX-XXXX (secrets, jamais random)."""
    return "-".join(
        "".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3)
    )


def date_il_y_a_mois(mois: int) -> date:
    aujourdhui = date.today()
    annee = aujourdhui.year
    m = aujourdhui.month - mois
    while m <= 0:
        m += 12
        annee -= 1
    dernier_jour = monthrange(annee, m)[1]
    return date(annee, m, min(aujourdhui.day, dernier_jour))


class Carte(Base):
    __tablename__ = "cartes"

    id = Column(String, primary_key=True)
    date_attribution = Column(Date, nullable=False, default=date.today)
    nb_adultes = Column(Integer, nullable=False, default=1)
    actif = Column(Boolean, nullable=False, default=True)
    derniere_maj = Column(DateTime, nullable=False, default=datetime.now)
    premier_passage_le = Column(DateTime, nullable=True)

    enfants = relationship(
        "EnfantCarte", back_populates="carte", cascade="all, delete-orphan"
    )


class EnfantCarte(Base):
    __tablename__ = "enfants_carte"

    id = Column(Integer, primary_key=True)
    carte_id = Column(String, ForeignKey("cartes.id"), nullable=False)
    date_naissance = Column(Date, nullable=True)
    tranche_declaree = Column(String, nullable=True)

    carte = relationship("Carte", back_populates="enfants")

    def tranche_age(self, a_la_date: date | None = None) -> str:
        """Tranche d'age calculee dynamiquement si date de naissance disponible."""
        if self.date_naissance is not None:
            ref = a_la_date or date.today()
            age_ans = (ref - self.date_naissance).days / 365.25
            if age_ans < 4:
                return "0-3"
            if age_ans < 7:
                return "4-6"
            return "6+"
        return self.tranche_declaree or "inconnue"


class ParametreCarte(Base):
    __tablename__ = "parametres_cartes"

    id = Column(Integer, primary_key=True)
    duree_purge_cartes_mois = Column(Integer, nullable=False, default=12)


DATA_DIR.mkdir(parents=True, exist_ok=True)
_moteur = create_engine(
    f"sqlite:///{FICHIER_BD}", connect_args={"check_same_thread": False}
)
SessionCarte = sessionmaker(bind=_moteur, autoflush=False, autocommit=False)


def initialiser_bd_cartes() -> None:
    Base.metadata.create_all(_moteur)
    session = SessionCarte()
    try:
        if session.get(ParametreCarte, 1) is None:
            session.add(ParametreCarte(id=1, duree_purge_cartes_mois=12))
            session.commit()
    finally:
        session.close()


def obtenir_session_carte():
    session = SessionCarte()
    try:
        yield session
    finally:
        session.close()

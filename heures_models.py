"""Modèles SQLAlchemy et accès base de données pour le module Heures.

Suivi du temps de l'équipe (salariés/bénévoles de l'association) : ce
module gère des données nominatives (noms, emails, salaires), sans rapport
avec l'anonymat exigé pour les passages LAEP suivis par les autres modules
de l'application — ce sont deux domaines de données séparés, stockés dans
des bases distinctes (data/heures.db ici, data/passages.xlsx ailleurs).
"""

import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
FICHIER_BD = DATA_DIR / "heures.db"
FICHIER_CLE_SECRETE = DATA_DIR / "secret.key"

DELAI_MODIFICATION = timedelta(hours=48)
SEUIL_VALIDATION_PAR_DEFAUT = 2

Base = declarative_base()


class Membre(Base):
    __tablename__ = "membres"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    role = Column(String, nullable=False, default="membre")  # "membre" ou "admin"
    actif = Column(Boolean, nullable=False, default=True)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)

    salaires = relationship("Salaire", back_populates="membre", order_by="Salaire.date_effet")
    horaires = relationship("Horaire", back_populates="membre")


class Salaire(Base):
    __tablename__ = "salaires"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    salaire_brut_mensuel = Column(Float, nullable=False)
    date_effet = Column(Date, nullable=False)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)

    membre = relationship("Membre", back_populates="salaires")


class Horaire(Base):
    __tablename__ = "horaires"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    date = Column(Date, nullable=False)
    heure_arrivee = Column(Time, nullable=False)
    heure_depart = Column(Time, nullable=False)
    statut = Column(String, nullable=False, default="déclaré")  # "déclaré" ou "validé"
    cree_le = Column(DateTime, nullable=False, default=datetime.now)
    modifiable_jusqu_a = Column(DateTime, nullable=False)

    membre = relationship("Membre", back_populates="horaires")
    validations = relationship("Validation", back_populates="horaire", cascade="all, delete-orphan")


class Validation(Base):
    __tablename__ = "validations"
    __table_args__ = (UniqueConstraint("horaire_id", "validateur_id", name="uniq_validation_par_membre"),)

    id = Column(Integer, primary_key=True)
    horaire_id = Column(Integer, ForeignKey("horaires.id"), nullable=False)
    validateur_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    date_validation = Column(DateTime, nullable=False, default=datetime.now)

    horaire = relationship("Horaire", back_populates="validations")
    validateur = relationship("Membre")


class Parametre(Base):
    """Table à une seule ligne (id=1) contenant les réglages globaux du module."""

    __tablename__ = "parametres"

    id = Column(Integer, primary_key=True)
    seuil_validation = Column(Integer, nullable=False, default=SEUIL_VALIDATION_PAR_DEFAUT)


class JetonConnexion(Base):
    """Jeton à usage unique pour le lien de connexion envoyé par email."""

    __tablename__ = "jetons_connexion"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    jeton = Column(String, nullable=False, unique=True)
    expire_le = Column(DateTime, nullable=False)
    utilise_le = Column(DateTime, nullable=True)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)


DATA_DIR.mkdir(parents=True, exist_ok=True)
moteur = create_engine(f"sqlite:///{FICHIER_BD}", connect_args={"check_same_thread": False})
SessionLocale = sessionmaker(bind=moteur, autoflush=False, autocommit=False)


def initialiser_bd() -> None:
    """Crée les tables si nécessaire et amorce la ligne de paramètres par défaut."""
    Base.metadata.create_all(moteur)
    session = SessionLocale()
    try:
        if session.get(Parametre, 1) is None:
            session.add(Parametre(id=1, seuil_validation=SEUIL_VALIDATION_PAR_DEFAUT))
            session.commit()
    finally:
        session.close()


def obtenir_session():
    """Dépendance FastAPI : une session BD par requête, fermée à la fin."""
    session = SessionLocale()
    try:
        yield session
    finally:
        session.close()


def obtenir_cle_secrete() -> str:
    """Clé de signature des cookies de session, générée une fois puis persistée localement."""
    if FICHIER_CLE_SECRETE.exists():
        return FICHIER_CLE_SECRETE.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cle = secrets.token_hex(32)
    FICHIER_CLE_SECRETE.write_text(cle, encoding="utf-8")
    return cle

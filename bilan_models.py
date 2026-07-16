"""Modeles SQLAlchemy pour le bilan CAF annuel du LAEP.

Trois tables :
- accueillants : personnes intervenant au LAEP (nom + role, pas d'email)
- heures_activite : heures par accueillant, date et type CAF
- fiche_identite : fiche de structure annuelle (une ligne par annee)

Stockees dans data/bilan.db, distincte de heures.db et cartes.db.
"""

from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
FICHIER_BD = DATA_DIR / "bilan.db"

Base = declarative_base()

TYPES_HEURES = {
    "ouverture_public": "Ouverture au public",
    "preparation_rangement_debriefing": "Preparation, rangement, debriefing",
    "analyse_pratique_supervision": "Analyse des pratiques / Supervision",
    "reunion_equipe_reseau": "Reunion d'equipe / Reseau",
}

TYPES_ORGANISATION = [
    "preparation_rangement_debriefing",
    "analyse_pratique_supervision",
    "reunion_equipe_reseau",
]


class Accueillant(Base):
    __tablename__ = "accueillants"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    role = Column(String, nullable=False, default="accueillant")
    actif = Column(Boolean, nullable=False, default=True)

    heures = relationship("HeureActivite", back_populates="accueillant")


class HeureActivite(Base):
    __tablename__ = "heures_activite"

    id = Column(Integer, primary_key=True)
    accueillant_id = Column(Integer, ForeignKey("accueillants.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String, nullable=False)
    duree_minutes = Column(Integer, nullable=False)

    accueillant = relationship("Accueillant", back_populates="heures")


class FicheIdentite(Base):
    __tablename__ = "fiche_identite"

    id = Column(Integer, primary_key=True)
    annee = Column(Integer, nullable=False, unique=True)
    lieu_dedie = Column(Boolean, nullable=False, default=False)
    charte_signee = Column(Boolean, nullable=False, default=False)
    supervision = Column(Boolean, nullable=False, default=False)
    partenariat = Column(Boolean, nullable=False, default=False)
    reseau_laep = Column(Boolean, nullable=False, default=False)
    comite_pilotage = Column(Boolean, nullable=False, default=False)
    observations = Column(String, nullable=True, default="")


DATA_DIR.mkdir(parents=True, exist_ok=True)
moteur = create_engine(
    f"sqlite:///{FICHIER_BD}", connect_args={"check_same_thread": False}
)
SessionLocale = sessionmaker(bind=moteur, autoflush=False, autocommit=False)


def initialiser_bd() -> None:
    Base.metadata.create_all(moteur)


def obtenir_session_bilan():
    session = SessionLocale()
    try:
        yield session
    finally:
        session.close()

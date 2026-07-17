"""Modèles SQLAlchemy et accès base de données pour le module Heures.

Gestionnaire d'heures supplémentaires et de récupération pour l'équipe
de l'association (salariés/bénévoles). Ne gère plus aucun salaire ni
rémunération horaire.
"""

import os
import secrets
from datetime import date, datetime, timedelta
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
    select,
    func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
FICHIER_BD = DATA_DIR / "heures.db"
FICHIER_CLE_SECRETE = DATA_DIR / "secret.key"

DELAI_MODIFICATION = timedelta(hours=48)

Base = declarative_base()


# ── Tables conservées (inchangées) ──────────────────────────────────────


class Membre(Base):
    __tablename__ = "membres"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    mot_de_passe_hash = Column(String, nullable=True)
    role = Column(String, nullable=False, default="membre")  # "membre" ou "admin"
    actif = Column(Boolean, nullable=False, default=True)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)

    horaires = relationship("Horaire", back_populates="membre")
    heures_prevues = relationship("HeuresPrevues", back_populates="membre", order_by="HeuresPrevues.date_effet")
    demandes_recup = relationship("DemandeRecup", back_populates="demandeur", foreign_keys="DemandeRecup.membre_id")
    validations_recup = relationship(
        "ValidationRecup", back_populates="validateur", foreign_keys="ValidationRecup.validateur_id"
    )


class Horaire(Base):
    """Déclaration quotidienne des heures de travail (arrivée/départ).

    La colonne statut est conservée mais n'est plus utilisée par la
    logique métier (l'ancien système de validation par les pairs a été
    remplacé par le système de récupération).
    """

    __tablename__ = "horaires"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    date = Column(Date, nullable=False)
    heure_arrivee = Column(Time, nullable=False)
    heure_depart = Column(Time, nullable=False)
    statut = Column(String, nullable=False, default="déclaré")
    cree_le = Column(DateTime, nullable=False, default=datetime.now)
    modifiable_jusqu_a = Column(DateTime, nullable=False)

    membre = relationship("Membre", back_populates="horaires")


# ── Nouvelles tables ────────────────────────────────────────────────────


class HeuresPrevues(Base):
    """Heures par semaine prévues pour un membre, avec historique.

    La valeur active pour une semaine donnée est celle dont date_effet
    est la plus récente antérieure ou égale au premier jour de la semaine.
    """

    __tablename__ = "heures_prevues"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    heures_par_semaine = Column(Float, nullable=False)
    date_effet = Column(Date, nullable=False)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)

    membre = relationship("Membre", back_populates="heures_prevues")


class DemandeRecup(Base):
    """Demande de récupération d'heures par un membre.

    Le statut évolue par votes collectifs : "en_attente" → "validee" ou "refusee".
    """

    __tablename__ = "demandes_recup"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    date_recup = Column(Date, nullable=False, comment="Jour du calendrier concerné")
    duree_heures = Column(Float, nullable=False, comment="Nombre d'heures demandées")
    justification = Column(String, nullable=False)
    statut = Column(String, nullable=False, default="en_attente")  # en_attente | validee | refusee
    cree_le = Column(DateTime, nullable=False, default=datetime.now)

    demandeur = relationship("Membre", back_populates="demandes_recup", foreign_keys=[membre_id])
    validations = relationship(
        "ValidationRecup", back_populates="demande", cascade="all, delete-orphan"
    )


class ValidationRecup(Base):
    """Vote d'un membre sur une demande de récupération."""

    __tablename__ = "validations_recup"
    __table_args__ = (UniqueConstraint("demande_id", "validateur_id", name="uniq_vote_par_demande"),)

    id = Column(Integer, primary_key=True)
    demande_id = Column(Integer, ForeignKey("demandes_recup.id"), nullable=False)
    validateur_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    decision = Column(String, nullable=False)  # "valide" ou "refuse"
    commentaire = Column(String, nullable=True)
    date_validation = Column(DateTime, nullable=False, default=datetime.now)

    demande = relationship("DemandeRecup", back_populates="validations")
    validateur = relationship("Membre", back_populates="validations_recup", foreign_keys=[validateur_id])


class JetonConnexion(Base):
    """Jeton à usage unique pour le lien de connexion envoyé par email."""

    __tablename__ = "jetons_connexion"

    id = Column(Integer, primary_key=True)
    membre_id = Column(Integer, ForeignKey("membres.id"), nullable=False)
    jeton = Column(String, nullable=False, unique=True)
    expire_le = Column(DateTime, nullable=False)
    utilise_le = Column(DateTime, nullable=True)
    cree_le = Column(DateTime, nullable=False, default=datetime.now)


# ── Paramètres globaux (table à une ligne, id=1) ────────────────────────


class Parametre(Base):
    __tablename__ = "parametres"

    id = Column(Integer, primary_key=True)
    seuil_validation_recup = Column(Integer, nullable=False, default=2)
    seuil_refus_recup = Column(Integer, nullable=False, default=2)


# ── Base de données ─────────────────────────────────────────────────────


DATA_DIR.mkdir(parents=True, exist_ok=True)
moteur = create_engine(f"sqlite:///{FICHIER_BD}", connect_args={"check_same_thread": False})
SessionLocale = sessionmaker(bind=moteur, autoflush=False, autocommit=False)


def initialiser_bd() -> None:
    """Crée les tables si nécessaire et amorce la ligne de paramètres par défaut."""
    Base.metadata.create_all(moteur)
    session = SessionLocale()
    try:
        if session.get(Parametre, 1) is None:
            session.add(Parametre(id=1, seuil_validation_recup=2, seuil_refus_recup=2))
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


# ── Clé secrète pour les cookies de session ─────────────────────────────


def obtenir_cle_secrete() -> str:
    """Clé de signature des cookies de session.

    Priorité :
    1. Variable d'environnement SECRET_KEY (recommandé en production)
    2. Fichier data/secret.key (généré automatiquement)
    """
    env_cle = os.environ.get("SECRET_KEY")
    if env_cle:
        return env_cle

    if FICHIER_CLE_SECRETE.exists():
        return FICHIER_CLE_SECRETE.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cle = secrets.token_hex(32)
    FICHIER_CLE_SECRETE.write_text(cle, encoding="utf-8")
    return cle


# ── Migrations ──────────────────────────────────────────────────────────


def _colonne_existe(nom_table: str, nom_colonne: str) -> bool:
    """Vérifie si une colonne existe dans une table SQLite."""
    with moteur.connect() as conn:
        result = conn.exec_driver_sql(f"PRAGMA table_info({nom_table})").fetchall()
        return nom_colonne in {row[1] for row in result}


def migrer_ajouter_mot_de_passe_hash() -> None:
    """Ajoute la colonne mot_de_passe_hash à la table membres si elle n'existe pas."""
    if not _colonne_existe("membres", "mot_de_passe_hash"):
        with moteur.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE membres ADD COLUMN mot_de_passe_hash TEXT")
            conn.commit()
        print("[migration] colonne mot_de_passe_hash ajoutée à la table membres.")


def migrer_parametres_recup() -> None:
    """Ajoute les colonnes de récupération à la table parametres si elles n'existent pas."""
    with moteur.connect() as conn:
        if not _colonne_existe("parametres", "seuil_validation_recup"):
            conn.exec_driver_sql(
                "ALTER TABLE parametres ADD COLUMN seuil_validation_recup INTEGER NOT NULL DEFAULT 2"
            )
            conn.commit()
            print("[migration] colonne seuil_validation_recup ajoutée à parametres.")

        if not _colonne_existe("parametres", "seuil_refus_recup"):
            conn.exec_driver_sql(
                "ALTER TABLE parametres ADD COLUMN seuil_refus_recup INTEGER NOT NULL DEFAULT 2"
            )
            conn.commit()
            print("[migration] colonne seuil_refus_recup ajoutée à parametres.")

    # Si l'ancien seuil existait mais que les nouveaux n'ont pas été initialisés, on les amorce
    session = SessionLocale()
    try:
        p = session.get(Parametre, 1)
        if p and p.seuil_validation_recup is None:
            p.seuil_validation_recup = 2
        if p and p.seuil_refus_recup is None:
            p.seuil_refus_recup = 2
        session.commit()
    finally:
        session.close()


# ── Calcul du solde ─────────────────────────────────────────────────────


def heures_prevues_pour_semaine(session, membre_id: int, premier_jour_semaine: date) -> float:
    """Retourne les heures_par_semaine actives pour un membre à une date donnée."""
    prevu = (
        session.query(HeuresPrevues)
        .filter(
            HeuresPrevues.membre_id == membre_id,
            HeuresPrevues.date_effet <= premier_jour_semaine,
        )
        .order_by(HeuresPrevues.date_effet.desc())
        .first()
    )
    return prevu.heures_par_semaine if prevu else 0.0


def debut_fin_semaine(jour: date) -> tuple[date, date]:
    """Retourne (lundi, dimanche) de la semaine ISO contenant jour."""
    lundi = jour - timedelta(days=jour.weekday())
    dimanche = lundi + timedelta(days=6)
    return lundi, dimanche


def calculer_solde(session, membre_id: int) -> dict:
    """Calcule le solde de récupération d'un membre (dérivé, jamais stocké).

    Retourne :
        solde_disponible (float) — heures disponibles
        historique (list[dict]) — un dict par semaine : debut, fin, travaille, prevu, delta
        total_travaille (float)
        total_prevu (float)
        total_valide (float)
        premier_horaire (date ou None)
    """
    # Plage temporelle
    premier = session.query(func.min(Horaire.date)).filter(Horaire.membre_id == membre_id).scalar()
    aujourdhui = date.today()

    # Toutes les demandes validées
    total_valide = (
        session.query(func.sum(DemandeRecup.duree_heures))
        .filter(DemandeRecup.membre_id == membre_id, DemandeRecup.statut == "validee")
        .scalar()
    ) or 0.0

    if not premier:
        return {
            "solde_disponible": 0.0,
            "historique": [],
            "total_travaille": 0.0,
            "total_prevu": 0.0,
            "total_valide": total_valide,
            "premier_horaire": None,
        }

    # Parcours semaine par semaine
    lundi, _ = debut_fin_semaine(premier)
    historique = []
    total_travaille = 0.0
    total_prevu = 0.0

    while lundi <= aujourdhui:
        dimanche = lundi + timedelta(days=6)

        # Heures travaillées cette semaine
        horaires_semaine = (
            session.query(Horaire)
            .filter(
                Horaire.membre_id == membre_id,
                Horaire.date >= lundi,
                Horaire.date <= dimanche,
            )
            .all()
        )
        heures_travaillees = sum(
            _duree_heures(h) for h in horaires_semaine
        )

        # Heures prévues actives cette semaine
        heures_prevues = heures_prevues_pour_semaine(session, membre_id, lundi)

        delta = round(heures_travaillees - heures_prevues, 2)
        total_travaille += heures_travaillees
        total_prevu += heures_prevues

        historique.append({
            "debut": lundi.isoformat(),
            "fin": dimanche.isoformat(),
            "travaille": round(heures_travaillees, 2),
            "prevu": heures_prevues,
            "delta": delta,
        })

        lundi = dimanche + timedelta(days=1)

    # Seuls les écarts positifs (travail > prévu) accumulent du temps de récup
    somme_deltas_positifs = sum(
        max(0, h["delta"]) for h in historique
    )
    solde = round(somme_deltas_positifs - total_valide, 2)

    return {
        "solde_disponible": solde,
        "historique": historique,
        "total_travaille": round(total_travaille, 2),
        "total_prevu": round(total_prevu, 2),
        "total_valide": total_valide,
        "premier_horaire": premier.isoformat() if premier else None,
    }


def _duree_heures(horaire: Horaire) -> float:
    """Calcule la durée en heures entre arrivée et départ."""
    from datetime import datetime, date, time

    delta = datetime.combine(date.min, horaire.heure_depart) - datetime.combine(date.min, horaire.heure_arrivee)
    return round(delta.total_seconds() / 3600, 2)


def calculer_seuil_majorite(session) -> int:
    """Retourne le nombre de voix nécessaire pour une majorité simple.

    Seuil = ceil(nombre_membres_actifs / 2).
    Le demandeur ne peut pas voter, ce seuil garantit qu'une décision
    prise est une majorité des membres de l'asso.
    """
    n_actifs = session.query(func.count(Membre.id)).filter(Membre.actif.is_(True)).scalar() or 0
    return (n_actifs + 1) // 2  # ceil(n/2)

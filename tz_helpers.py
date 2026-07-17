"""Fuseau horaire La Reunion (UTC+4) — helpers pour toute l'app."""

from zoneinfo import ZoneInfo
from datetime import datetime, date, time, timedelta

TZ_REUNION = ZoneInfo("Indian/Reunion")


def maintenant() -> datetime:
    """Retourne datetime actuel en timezone La Reunion."""
    return datetime.now(TZ_REUNION)


def aujourdhui() -> date:
    """Retourne la date du jour en timezone La Reunion."""
    return maintenant().date()


def heure_actuelle() -> time:
    """Retourne l'heure courante en timezone La Reunion."""
    return maintenant().time()

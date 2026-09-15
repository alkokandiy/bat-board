"""Shared helpers moved verbatim out of main.py so services can use them
without importing the FastAPI app module (which would be circular)."""

import json

import models


# --- Tier Calculation Helper ---
def calculate_bat_level(points: int) -> str:
    if points < 2000:
        return "The Orphan"
    elif points < 5000:
        return "The Vigilante"
    elif points < 10000:
        return "The Detective"
    elif points < 20000:
        return "Son of Gotham"
    elif points < 35000:
        return "The Caped Crusader"
    elif points < 55000:
        return "Heir of the Demon"
    elif points < 80000:
        return "The Dark Knight"
    elif points < 120000:
        return "Faris al-Khorasan"
    elif points < 180000:
        return "Sword of the Ummah"
    else:
        return "Dark Knight of Khorasan"


# --- Auto Log Helper ---
def auto_log_event(db, owner_id: int, event_type: str, details_dict: dict):
    log_entry = models.BatLog(
        owner_id=owner_id,
        event_type=event_type,
        details=json.dumps(details_dict)
    )
    db.add(log_entry)
    db.flush()

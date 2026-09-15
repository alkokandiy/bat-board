"""Profile business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from sqlalchemy.orm import Session

import models
from services.common import calculate_bat_level


def get_profile(
    db: Session,
    current_user: models.BatAccount,
) -> models.BatAccount:
    """Return the user's account with a freshly recalculated bat_level."""
    current_user.bat_level = calculate_bat_level(current_user.points)
    return current_user

"""Logs business logic.

Plain importable functions — no FastAPI request/response objects.
Alfred's tool layer will call these directly later.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

import models


def list_recent_logs(
    db: Session,
    current_user: models.BatAccount,
    limit: int = 50,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[models.BatLog]:
    q = db.query(models.BatLog).filter(models.BatLog.owner_id == current_user.id)
    if start_date:
        q = q.filter(models.BatLog.timestamp >= start_date)
    if end_date:
        q = q.filter(models.BatLog.timestamp <= end_date)
    return q.order_by(models.BatLog.timestamp.desc()).limit(limit).all()

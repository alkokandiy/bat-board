"""Pydantic contracts for the Countdowns API (input/output shapes only)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CountdownCreate(BaseModel):
    title: str
    target_date: datetime


class CountdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    target_date: datetime
    created_at: datetime
    # Computed at read time, never stored.
    days_remaining: int

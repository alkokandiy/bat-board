"""Pydantic contracts for the Notes API (input/output shapes only)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NoteCreate(BaseModel):
    title: str = ""
    body: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: bool = False


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: Optional[bool] = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

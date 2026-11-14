"""Pydantic contracts for sections."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SectionCreate(BaseModel):
    list_id: int
    name: str = Field(..., min_length=1, max_length=60)


class SectionUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class SectionReorder(BaseModel):
    list_id: int
    ordered_ids: List[int]


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    name: str
    position: int
    created_at: datetime
    open_missions: int = 0

"""Pydantic contracts for lists."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    color: Optional[str] = Field(None, max_length=32)
    icon: Optional[str] = Field(None, max_length=40)


class ListUpdate(BaseModel):
    # Every field optional and read through `model_fields_set`, so sending
    # `{"color": null}` clears the colour while leaving it out keeps it.
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    color: Optional[str] = Field(None, max_length=32)
    icon: Optional[str] = Field(None, max_length=40)
    archived: Optional[bool] = None


class ListReorder(BaseModel):
    ordered_ids: List[int]


class ListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    position: int
    archived: bool
    created_at: datetime
    # Filled by the router from one grouped query, rather than a count per
    # list: the rail asks for every list at once.
    open_missions: int = 0

"""Pydantic contracts for the corporate/work API (input/output shapes only)."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

import models


class WorkTaskCreate(BaseModel):
    title: str
    detail: Optional[str] = None
    status: str = "todo"
    project: Optional[str] = None
    due_date: Optional[datetime] = None


class WorkTaskUpdate(BaseModel):
    title: Optional[str] = None
    detail: Optional[str] = None
    status: Optional[str] = None
    project: Optional[str] = None
    due_date: Optional[datetime] = None


class WorkTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    detail: Optional[str] = None
    status: str
    project: Optional[str] = None
    due_date: Optional[datetime] = None
    focus_minutes: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class WorkNoteCreate(BaseModel):
    content: str
    kind: str = "note"
    work_task_id: Optional[int] = None


class WorkNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    content: str
    work_task_id: Optional[int] = None
    created_at: datetime


class WorkProfileUpdate(BaseModel):
    """Every field optional — send only what changed (same contract Alfred uses)."""

    employer: Optional[str] = None
    role: Optional[str] = None
    work_days: Optional[str] = Field(
        default=None, description="CSV weekdays, e.g. '0,1,2,3,4' (Mon=0) or 'Mon,Tue'.")
    work_start: Optional[str] = None
    work_end: Optional[str] = None
    expected_weekly_hours: Optional[int] = None
    started_on: Optional[str] = None
    report_time: Optional[str] = None
    daily_report: Optional[bool] = None
    weekly_report_day: Optional[str] = Field(
        default=None, description="Weekday for the weekly review, or 'none' to turn it off.")
    monthly_report: Optional[bool] = None
    notes: Optional[str] = None


class WorkToggle(BaseModel):
    enabled: bool


class WorkStatusResponse(BaseModel):
    """Everything the UI needs to decide whether to show the work side at all."""

    enabled: bool
    chosen: bool            # did the user explicitly decide, or is this the default?
    has_data: bool
    configured: bool
    missing_essential: List[str] = []
    next_question: Optional[str] = None
    profile: Dict = {}
    statuses: List[str] = list(models.WORK_STATUSES)
    note_kinds: List[str] = list(models.WORK_NOTE_KINDS)

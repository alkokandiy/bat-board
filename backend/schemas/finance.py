"""Pydantic contracts for the finance API (input/output shapes only).

Amounts cross the wire as integer minor units under `*_minor` names, so there
is no point at which a float could round somebody's money. Formatting into
"UZS 1 018 500,00" is the browser's job, from the currency and its exponent.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    name: str
    group: str = "cash"
    currency: str
    opening_balance_minor: int = 0
    settlement_day: Optional[int] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    group: str
    currency: str
    opening_balance_minor: int
    settlement_day: Optional[int]
    archived: bool
    # Derived from the transactions every time, never stored.
    balance_minor: int


class CategoryCreate(BaseModel):
    name: str
    kind: str
    icon: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    icon: Optional[str]
    parent_id: Optional[int]


class TransactionCreate(BaseModel):
    kind: str
    amount_minor: int
    occurred_on: date
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    category_id: Optional[int] = None
    note: Optional[str] = None
    description: Optional[str] = None
    rate_to_main: Optional[float] = None
    fee_minor: Optional[int] = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    occurred_on: date
    amount_minor: int
    currency: str
    rate_to_main: float
    fee_minor: Optional[int]
    from_account_id: Optional[int]
    to_account_id: Optional[int]
    category_id: Optional[int]
    note: Optional[str]
    description: Optional[str]
    created_at: datetime
    # Resolved names, so the list does not need a second round trip to render.
    from_account_name: Optional[str] = None
    to_account_name: Optional[str] = None
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    parent_category_name: Optional[str] = None


class PeriodTotals(BaseModel):
    income_minor: int
    expense_minor: int
    net_minor: int


class LedgerResponse(BaseModel):
    """Everything the transactions screen needs for one window, in one call."""

    start: date
    end: date
    main_currency: Optional[str]
    totals: PeriodTotals
    transactions: List[TransactionResponse]


class FinanceSettings(BaseModel):
    finance_enabled: bool
    main_currency: Optional[str]
    period_start_day: int


class FinanceSettingsUpdate(BaseModel):
    finance_enabled: Optional[bool] = None
    main_currency: Optional[str] = None
    period_start_day: Optional[int] = None

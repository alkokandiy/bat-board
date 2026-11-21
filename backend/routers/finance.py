"""Finance REST endpoints. Thin handlers only — the ledger lives in services.

Every write goes through `finance_service`, which is also what Alfred's tools
will call. The web API and Alfred must never be two implementations of the same
rule, because the day they disagree is the day a balance stops being arguable.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

import models
from dependencies import get_current_active_user, get_db, limiter
from schemas.finance import (AccountCreate, AccountResponse, CategoryCreate,
                             CategoryResponse, FinanceSettings,
                             FinanceSettingsUpdate, LedgerResponse, PeriodTotals,
                             TransactionCreate, TransactionResponse)
from services import finance_service

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _account_response(db: Session, user: models.BatAccount,
                      account: models.FinanceAccount) -> AccountResponse:
    return AccountResponse(
        id=account.id, name=account.name, group=account.group,
        currency=account.currency,
        opening_balance_minor=account.opening_balance_minor,
        settlement_day=account.settlement_day, archived=account.archived,
        balance_minor=finance_service.account_balance_minor(db, user, account.id),
    )


def _txn_response(db: Session, user: models.BatAccount,
                  txn: models.FinanceTransaction) -> TransactionResponse:
    src = finance_service.get_account(db, user, txn.from_account_id) if txn.from_account_id else None
    dst = finance_service.get_account(db, user, txn.to_account_id) if txn.to_account_id else None
    cat = finance_service.get_category(db, user, txn.category_id) if txn.category_id else None
    parent = finance_service.get_category(db, user, cat.parent_id) if cat and cat.parent_id else None
    return TransactionResponse(
        id=txn.id, kind=txn.kind, occurred_on=txn.occurred_on,
        amount_minor=txn.amount_minor, currency=txn.currency,
        rate_to_main=txn.rate_to_main, fee_minor=txn.fee_minor,
        from_account_id=txn.from_account_id, to_account_id=txn.to_account_id,
        category_id=txn.category_id, note=txn.note, description=txn.description,
        created_at=txn.created_at,
        from_account_name=src.name if src else None,
        to_account_name=dst.name if dst else None,
        category_name=cat.name if cat else None,
        category_icon=(cat.icon if cat else None) or (parent.icon if parent else None),
        parent_category_name=parent.name if parent else None,
    )


# --- settings --------------------------------------------------------------

@router.get("/settings", response_model=FinanceSettings)
def get_settings(
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return FinanceSettings(
        finance_enabled=finance_service.is_enabled(db, current_user),
        main_currency=finance_service.main_currency(current_user),
        period_start_day=finance_service.period_start_day(current_user),
    )


@router.put("/settings", response_model=FinanceSettings)
@limiter.limit("30/minute")
def update_settings(
    request: Request,
    payload: FinanceSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if payload.finance_enabled is not None:
        current_user.finance_enabled = bool(payload.finance_enabled)
    if payload.main_currency is not None:
        code = payload.main_currency.strip().upper()
        if len(code) != 3:
            raise HTTPException(status_code=400, detail="A currency is a three-letter code")
        current_user.main_currency = code
    if payload.period_start_day is not None:
        if not (1 <= payload.period_start_day <= 28):
            raise HTTPException(status_code=400, detail="A start day is between 1 and 28")
        current_user.period_start_day = payload.period_start_day
    db.commit()
    db.refresh(current_user)
    return get_settings(db=db, current_user=current_user)


# --- accounts --------------------------------------------------------------

@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return [_account_response(db, current_user, a)
            for a in finance_service.list_accounts(db, current_user, include_archived)]


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_account(
    request: Request,
    payload: AccountCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        account = finance_service.create_account(
            db, current_user, payload.name, payload.group, payload.currency,
            payload.opening_balance_minor, payload.settlement_day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _account_response(db, current_user, account)


# --- categories ------------------------------------------------------------

@router.get("/categories", response_model=List[CategoryResponse])
def list_categories(
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    return finance_service.list_categories(db, current_user, kind)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_category(
    request: Request,
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        return finance_service.create_category(
            db, current_user, payload.name, payload.kind, payload.icon, payload.parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- transactions ----------------------------------------------------------

@router.get("/ledger", response_model=LedgerResponse)
def ledger(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    """One window's transactions and its three header figures, in one call."""
    if end < start:
        raise HTTPException(status_code=400, detail="The window ends before it starts")
    rows = finance_service.list_transactions(db, current_user, start, end, limit=2000)
    return LedgerResponse(
        start=start, end=end,
        main_currency=finance_service.main_currency(current_user),
        totals=PeriodTotals(**finance_service.period_totals(db, current_user, start, end)),
        transactions=[_txn_response(db, current_user, t) for t in rows],
    )


@router.post("/transactions", response_model=TransactionResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
def create_transaction(
    request: Request,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    try:
        txn = finance_service.create_transaction(
            db, current_user, payload.kind, payload.amount_minor, payload.occurred_on,
            payload.from_account_id, payload.to_account_id, payload.category_id,
            payload.note, payload.description, payload.rate_to_main, payload.fee_minor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _txn_response(db, current_user, txn)


@router.delete("/transactions/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
def delete_transaction(
    request: Request,
    txn_id: int,
    db: Session = Depends(get_db),
    current_user: models.BatAccount = Depends(get_current_active_user),
):
    if not finance_service.delete_transaction(db, current_user, txn_id):
        raise HTTPException(status_code=404, detail="No such transaction")
    return None

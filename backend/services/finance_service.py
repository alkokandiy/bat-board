"""The ledger.

Every record moves money between accounts. Income arrives into one, an expense
leaves one, a transfer does both — and there is no fourth shape. That single
rule is what keeps a credit-card payment from being counted as spending twice,
and it is enforced in exactly one place: `resolve_posting`.

Money is a BigInteger count of minor units throughout. Never a float: floating
point cannot represent 0.10, and a ledger that drifts by a few tiyin is one
nobody can reconcile and therefore one nobody trusts.
"""

from datetime import date
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models

KINDS = ("income", "expense", "transfer")
GROUPS = ("cash", "bank", "card", "savings", "investment", "loan", "insurance", "other")
# Groups whose balance is money you owe rather than money you have.
LIABILITY_GROUPS = ("card", "loan")

MAX_NAME = 60
MAX_NOTE = 200

# Minor units per major unit. Two is right almost everywhere; these are the
# currencies where it is not, and getting it wrong means every amount is off by
# a factor of a hundred.
_EXPONENTS = {"JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0, "BIF": 0,
              "DJF": 0, "GNF": 0, "KMF": 0, "PYG": 0, "RWF": 0, "UGX": 0,
              "VUV": 0, "XAF": 0, "XOF": 0, "XPF": 0,
              "BHD": 3, "IQD": 3, "JOD": 3, "KWD": 3, "LYD": 3, "OMR": 3, "TND": 3}


def exponent(currency: str) -> int:
    """How many minor digits this currency has. Two unless it is one of the few."""
    return _EXPONENTS.get((currency or "").upper(), 2)


# --- the switch ------------------------------------------------------------

def has_finance_data(db: Session, user: models.BatAccount) -> bool:
    return (db.query(models.FinanceAccount)
            .filter(models.FinanceAccount.owner_id == user.id).first() is not None)


def is_enabled(db: Session, user: models.BatAccount) -> bool:
    """Is the finance track active for this user?

    Same tri-state as the work track. An explicit choice wins; NULL resolves to
    "on if they already have finance data", so nobody who never asked for it
    gets a money module, and nobody using one loses it.
    """
    explicit = getattr(user, "finance_enabled", None)
    if explicit is not None:
        return bool(explicit)
    return has_finance_data(db, user)


def set_enabled(db: Session, user: models.BatAccount, enabled: bool) -> bool:
    """Record an explicit choice. Returns the new state. Destroys no data."""
    user.finance_enabled = bool(enabled)
    db.commit()
    db.refresh(user)
    return bool(user.finance_enabled)


def main_currency(user: models.BatAccount) -> Optional[str]:
    """The currency reports are converted into, or None if never chosen.

    Deliberately not defaulted: rule 1 says no currency is the house one, and
    guessing would silently mislabel every figure on the page.
    """
    value = (getattr(user, "main_currency", None) or "").strip().upper()
    return value or None


def period_start_day(user: models.BatAccount) -> int:
    """Which day of the month their budget month begins on. 1 unless set."""
    value = getattr(user, "period_start_day", None)
    if value is None:
        return 1
    return min(28, max(1, int(value)))


# --- ownership -------------------------------------------------------------

def get_account(db: Session, user: models.BatAccount, account_id: int) -> Optional[models.FinanceAccount]:
    return (db.query(models.FinanceAccount)
            .filter(models.FinanceAccount.id == account_id,
                    models.FinanceAccount.owner_id == user.id).first())


def get_category(db: Session, user: models.BatAccount, category_id: int) -> Optional[models.FinanceCategory]:
    return (db.query(models.FinanceCategory)
            .filter(models.FinanceCategory.id == category_id,
                    models.FinanceCategory.owner_id == user.id).first())


def resolve_account(db: Session, user: models.BatAccount, value) -> Optional[int]:
    """Turn whatever the caller sent into one of this user's own account ids.

    The only thing standing between a transaction and somebody else's wallet.
    """
    if value is None or value == "":
        return None
    try:
        account_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not an account")
    if get_account(db, user, account_id) is None:
        raise ValueError("No such account")
    return account_id


def resolve_category(db: Session, user: models.BatAccount, value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        category_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a category")
    if get_category(db, user, category_id) is None:
        raise ValueError("No such category")
    return category_id


# --- the invariant ---------------------------------------------------------

def resolve_posting(db: Session, user: models.BatAccount, kind: str,
                    from_account=None, to_account=None, category=None) -> dict:
    """The single home of "what shape is a valid record of this kind".

    Returns the resolved `{from_account_id, to_account_id, category_id}`, or
    raises ValueError saying what is wrong in words a person can act on.

    Every writer goes through here — the REST router, Alfred's tools, the
    importer. Spread these checks across the three and the three will disagree,
    and a ledger that disagrees with itself is worse than no ledger at all.
    """
    if kind not in KINDS:
        raise ValueError(f"A record is income, expense or transfer — not '{kind}'")

    src = resolve_account(db, user, from_account)
    dst = resolve_account(db, user, to_account)
    cat = resolve_category(db, user, category)

    if kind == "expense":
        if src is None:
            raise ValueError("An expense has to come out of an account")
        if dst is not None:
            raise ValueError("An expense does not go into an account — that is a transfer")
        if cat is not None and get_category(db, user, cat).kind != "expense":
            raise ValueError("That category is for income, not spending")

    elif kind == "income":
        if dst is None:
            raise ValueError("Income has to land in an account")
        if src is not None:
            raise ValueError("Income does not come out of an account — that is a transfer")
        if cat is not None and get_category(db, user, cat).kind != "income":
            raise ValueError("That category is for spending, not income")

    else:  # transfer
        if src is None or dst is None:
            raise ValueError("A transfer needs both an account to leave and one to arrive in")
        if src == dst:
            raise ValueError("A transfer has to go somewhere else")
        if cat is not None:
            # Moving your own money between your own pockets is not spending.
            # Categorising it would double-count it in every report.
            raise ValueError("A transfer has no category — it is not spending")

    return {"from_account_id": src, "to_account_id": dst, "category_id": cat}


# --- writing ---------------------------------------------------------------

def _clean_name(name: Optional[str], what: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError(f"A{'n' if what[0] in 'aeiou' else ''} {what} needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"A {what} name is at most {MAX_NAME} characters")
    return name


def create_account(db: Session, user: models.BatAccount, name: str, group: str,
                   currency: str, opening_balance_minor: int = 0,
                   settlement_day: Optional[int] = None) -> models.FinanceAccount:
    name = _clean_name(name, "account")
    if group not in GROUPS:
        raise ValueError(f"'{group}' is not an account group")
    currency = (currency or "").strip().upper()
    if len(currency) != 3:
        raise ValueError("A currency is a three-letter code, like UZS or USD")
    if settlement_day is not None and not (1 <= int(settlement_day) <= 28):
        raise ValueError("A settlement day is between 1 and 28")

    account = models.FinanceAccount(
        name=name, group=group, currency=currency,
        opening_balance_minor=int(opening_balance_minor or 0),
        settlement_day=int(settlement_day) if settlement_day is not None else None,
        owner_id=user.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def create_category(db: Session, user: models.BatAccount, name: str, kind: str,
                    icon: Optional[str] = None, parent_id=None) -> models.FinanceCategory:
    name = _clean_name(name, "category")
    if kind not in ("income", "expense"):
        raise ValueError("A category is for income or for expense")

    parent = None
    if parent_id not in (None, ""):
        parent = get_category(db, user, int(parent_id))
        if parent is None:
            raise ValueError("No such category")
        if parent.kind != kind:
            raise ValueError("A subcategory sits under a parent of the same kind")
        if parent.parent_id is not None:
            # One level deep. A deeper tree is a filing problem wearing the
            # clothes of a feature, and it makes every report ambiguous.
            raise ValueError("Categories go one level deep")

    category = models.FinanceCategory(
        name=name, kind=kind, icon=(icon or None),
        parent_id=parent.id if parent else None, owner_id=user.id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def create_transaction(db: Session, user: models.BatAccount, kind: str,
                       amount_minor: int, occurred_on: date,
                       from_account=None, to_account=None, category=None,
                       note: Optional[str] = None, description: Optional[str] = None,
                       rate_to_main: Optional[float] = None,
                       fee_minor: Optional[int] = None) -> models.FinanceTransaction:
    """Record one movement. The only way a transaction is ever created."""
    amount_minor = int(amount_minor)
    if amount_minor <= 0:
        # Sign is carried by the kind, never by the amount. A negative expense
        # is a bug that reads as income in every total that sums the column.
        raise ValueError("An amount has to be more than nothing")

    placement = resolve_posting(db, user, kind, from_account, to_account, category)

    if fee_minor is not None:
        fee_minor = int(fee_minor)
        if fee_minor < 0:
            raise ValueError("A fee cannot be negative")
        if kind != "transfer":
            raise ValueError("Only a transfer carries a fee")

    # The currency comes from the account the money actually moved in — never
    # from the caller, who could otherwise label a UZS row as USD.
    anchor_id = placement["from_account_id"] or placement["to_account_id"]
    anchor = get_account(db, user, anchor_id)

    if kind == "transfer":
        other = get_account(db, user, placement["to_account_id"])
        if other.currency != anchor.currency:
            # One row carries one amount, so a transfer across currencies has
            # no honest answer here: the sum that leaves is not the sum that
            # arrives. Refusing is the only option that does not quietly
            # invent money at the far end. It needs its own rate field and a
            # second amount, which is a change to the row, not to this check.
            raise ValueError(
                f"A transfer between {anchor.currency} and {other.currency} "
                "is not something this can record yet — the amount that leaves "
                "is not the amount that arrives.")

    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE:
        raise ValueError(f"A note is at most {MAX_NOTE} characters")

    txn = models.FinanceTransaction(
        kind=kind,
        occurred_on=occurred_on,
        amount_minor=amount_minor,
        currency=anchor.currency,
        rate_to_main=float(rate_to_main) if rate_to_main is not None else 1.0,
        fee_minor=fee_minor,
        note=note,
        description=(description or "").strip() or None,
        owner_id=user.id,
        **placement,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def delete_transaction(db: Session, user: models.BatAccount, txn_id: int) -> bool:
    txn = (db.query(models.FinanceTransaction)
           .filter(models.FinanceTransaction.id == txn_id,
                   models.FinanceTransaction.owner_id == user.id).first())
    if txn is None:
        return False
    db.delete(txn)
    db.commit()
    return True


# --- reading ---------------------------------------------------------------

def account_balance_minor(db: Session, user: models.BatAccount, account_id: int) -> int:
    """What is in this account, derived from the rows that put it there.

    Never stored. A stored balance is a second source of truth that drifts
    away from the transactions and cannot be argued with afterwards.
    """
    account = get_account(db, user, account_id)
    if account is None:
        raise ValueError("No such account")

    total = int(account.opening_balance_minor or 0)
    rows = (db.query(models.FinanceTransaction)
            .filter(models.FinanceTransaction.owner_id == user.id,
                    or_(models.FinanceTransaction.from_account_id == account_id,
                        models.FinanceTransaction.to_account_id == account_id)).all())
    for txn in rows:
        if txn.to_account_id == account_id:
            total += int(txn.amount_minor)
        if txn.from_account_id == account_id:
            total -= int(txn.amount_minor)
            # The fee leaves the sending side with the money, not the receiving
            # side — otherwise a transfer silently invents cash at the far end.
            total -= int(txn.fee_minor or 0)
    return total


def list_accounts(db: Session, user: models.BatAccount, include_archived: bool = False):
    q = (db.query(models.FinanceAccount)
         .filter(models.FinanceAccount.owner_id == user.id))
    if not include_archived:
        q = q.filter(models.FinanceAccount.archived.is_(False))
    return q.order_by(models.FinanceAccount.sort_order, models.FinanceAccount.id).all()


def list_categories(db: Session, user: models.BatAccount, kind: Optional[str] = None):
    q = (db.query(models.FinanceCategory)
         .filter(models.FinanceCategory.owner_id == user.id,
                 models.FinanceCategory.archived.is_(False)))
    if kind:
        q = q.filter(models.FinanceCategory.kind == kind)
    return q.order_by(models.FinanceCategory.sort_order, models.FinanceCategory.id).all()


def list_transactions(db: Session, user: models.BatAccount,
                      start: Optional[date] = None, end: Optional[date] = None,
                      limit: int = 200):
    q = (db.query(models.FinanceTransaction)
         .filter(models.FinanceTransaction.owner_id == user.id))
    if start is not None:
        q = q.filter(models.FinanceTransaction.occurred_on >= start)
    if end is not None:
        q = q.filter(models.FinanceTransaction.occurred_on <= end)
    return (q.order_by(models.FinanceTransaction.occurred_on.desc(),
                       models.FinanceTransaction.id.desc())
            .limit(limit).all())


def period_totals(db: Session, user: models.BatAccount,
                  start: date, end: date) -> dict:
    """Income, expense and the net for a window — the three figures in the header.

    Transfers are excluded from both sides deliberately. Moving your own money
    is not earning and not spending, and counting it would make a month in
    which you shuffled cash to a card look like a month of heavy spending.
    """
    income = expense = 0
    for txn in list_transactions(db, user, start, end, limit=100000):
        amount = int(round(int(txn.amount_minor) * float(txn.rate_to_main or 1.0)))
        if txn.kind == "income":
            income += amount
        elif txn.kind == "expense":
            expense += amount
    return {"income_minor": income, "expense_minor": expense,
            "net_minor": income - expense}

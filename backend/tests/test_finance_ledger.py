"""The ledger: the posting invariant, ownership, and balances that derive.

The bar for this module is that a wrong answer about money is never silent.
Every test here fails loudly on a shape that would corrupt a balance, rather
than on a cosmetic difference.
"""

from datetime import date

import pytest


def _setup(client, h, currency="UZS"):
    """A cash account, a card, an expense tree and an income category."""
    cash = client.post("/api/finance/accounts", headers=h, json={
        "name": "Cash", "group": "cash", "currency": currency}).json()
    card = client.post("/api/finance/accounts", headers=h, json={
        "name": "Card", "group": "card", "currency": currency}).json()
    food = client.post("/api/finance/categories", headers=h, json={
        "name": "Food", "kind": "expense", "icon": "🍜"}).json()
    salary = client.post("/api/finance/categories", headers=h, json={
        "name": "Salary", "kind": "income"}).json()
    return cash, card, food, salary


def _expense(client, h, account_id, category_id, amount, day="2026-11-18", **extra):
    body = {"kind": "expense", "amount_minor": amount, "occurred_on": day,
            "from_account_id": account_id, "category_id": category_id}
    body.update(extra)
    return client.post("/api/finance/transactions", headers=h, json=body)


# --- the invariant ---------------------------------------------------------

class TestThePostingInvariant:
    def test_an_expense_needs_an_account_to_come_out_of(self, client, auth_headers):
        h = auth_headers("fin_inv1")
        _, _, food, _ = _setup(client, h)
        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "expense", "amount_minor": 1000, "occurred_on": "2026-11-18",
            "category_id": food["id"]})
        assert r.status_code == 400
        assert "out of an account" in r.json()["detail"]

    def test_income_needs_an_account_to_land_in(self, client, auth_headers):
        h = auth_headers("fin_inv2")
        cash, _, _, salary = _setup(client, h)
        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "income", "amount_minor": 1000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "category_id": salary["id"]})
        assert r.status_code == 400

    def test_a_transfer_cannot_go_to_the_same_account(self, client, auth_headers):
        h = auth_headers("fin_inv3")
        cash, _, _, _ = _setup(client, h)
        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 1000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": cash["id"]})
        assert r.status_code == 400
        assert "somewhere else" in r.json()["detail"]

    def test_a_transfer_refuses_a_category(self, client, auth_headers):
        """Moving your own money is not spending. A category would double-count it."""
        h = auth_headers("fin_inv4")
        cash, card, food, _ = _setup(client, h)
        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 1000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": card["id"],
            "category_id": food["id"]})
        assert r.status_code == 400
        assert "not spending" in r.json()["detail"]

    def test_an_expense_refuses_an_income_category(self, client, auth_headers):
        h = auth_headers("fin_inv5")
        cash, _, _, salary = _setup(client, h)
        r = _expense(client, h, cash["id"], salary["id"], 1000)
        assert r.status_code == 400
        assert "for income" in r.json()["detail"]

    def test_a_fourth_kind_is_refused(self, client, auth_headers):
        h = auth_headers("fin_inv6")
        cash, _, _, _ = _setup(client, h)
        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "refund", "amount_minor": 1000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"]})
        assert r.status_code == 400

    def test_a_negative_amount_is_refused(self, client, auth_headers):
        """Sign is carried by the kind. A negative expense reads as income in
        every total that sums the column."""
        h = auth_headers("fin_inv7")
        cash, _, food, _ = _setup(client, h)
        assert _expense(client, h, cash["id"], food["id"], -5000).status_code == 400
        assert _expense(client, h, cash["id"], food["id"], 0).status_code == 400

    def test_a_row_is_stamped_with_the_currency_of_the_account_it_moved_in(self, client, auth_headers):
        """Never the caller's word for it, or a UZS row can be labelled USD and
        every total that trusts the label is wrong."""
        h = auth_headers("fin_inv9")
        usd = client.post("/api/finance/accounts", headers=h, json={
            "name": "Dollars", "group": "cash", "currency": "USD"}).json()
        som = client.post("/api/finance/accounts", headers=h, json={
            "name": "Som", "group": "cash", "currency": "UZS"}).json()
        food = client.post("/api/finance/categories", headers=h, json={
            "name": "Food", "kind": "expense"}).json()
        salary = client.post("/api/finance/categories", headers=h, json={
            "name": "Salary", "kind": "income"}).json()

        spent = _expense(client, h, usd["id"], food["id"], 1_000).json()
        assert spent["currency"] == "USD"

        earned = client.post("/api/finance/transactions", headers=h, json={
            "kind": "income", "amount_minor": 500_000, "occurred_on": "2026-11-18",
            "to_account_id": som["id"], "category_id": salary["id"]}).json()
        assert earned["currency"] == "UZS"

    def test_a_transfer_across_currencies_is_refused_rather_than_guessed(self, client, auth_headers):
        """The sum that leaves is not the sum that arrives. One amount cannot
        describe both, so booking it would invent money at the far end."""
        h = auth_headers("fin_inv10")
        usd = client.post("/api/finance/accounts", headers=h, json={
            "name": "Dollars", "group": "cash", "currency": "USD"}).json()
        som = client.post("/api/finance/accounts", headers=h, json={
            "name": "Som", "group": "cash", "currency": "UZS"}).json()

        r = client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 10_000, "occurred_on": "2026-11-18",
            "from_account_id": usd["id"], "to_account_id": som["id"]})
        assert r.status_code == 400
        assert "USD" in r.json()["detail"] and "UZS" in r.json()["detail"]

    def test_only_a_transfer_carries_a_fee(self, client, auth_headers):
        h = auth_headers("fin_inv8")
        cash, _, food, _ = _setup(client, h)
        r = _expense(client, h, cash["id"], food["id"], 1000, fee_minor=50)
        assert r.status_code == 400


# --- ownership -------------------------------------------------------------

class TestOwnership:
    def test_a_transaction_cannot_name_another_users_account(self, client, auth_headers):
        mine = auth_headers("fin_own_a")
        theirs = auth_headers("fin_own_b")
        _, _, food, _ = _setup(client, mine)
        their_cash = client.post("/api/finance/accounts", headers=theirs, json={
            "name": "Their cash", "group": "cash", "currency": "USD"}).json()

        r = _expense(client, mine, their_cash["id"], food["id"], 1000)
        assert r.status_code == 400
        assert "No such account" in r.json()["detail"]

    def test_a_transaction_cannot_name_another_users_category(self, client, auth_headers):
        mine = auth_headers("fin_own_c")
        theirs = auth_headers("fin_own_d")
        cash, _, _, _ = _setup(client, mine)
        their_cat = client.post("/api/finance/categories", headers=theirs, json={
            "name": "Theirs", "kind": "expense"}).json()

        r = _expense(client, mine, cash["id"], their_cat["id"], 1000)
        assert r.status_code == 400
        assert "No such category" in r.json()["detail"]

    def test_the_ledger_shows_only_your_own_rows(self, client, auth_headers):
        mine = auth_headers("fin_own_e")
        theirs = auth_headers("fin_own_f")
        cash, _, food, _ = _setup(client, mine)
        _expense(client, mine, cash["id"], food["id"], 6000)

        their_cash, _, their_food, _ = _setup(client, theirs, currency="USD")
        _expense(client, theirs, their_cash["id"], their_food["id"], 999999)

        r = client.get("/api/finance/ledger", headers=mine,
                       params={"start": "2026-11-01", "end": "2026-11-30"}).json()
        assert r["totals"]["expense_minor"] == 6000
        assert all(t["amount_minor"] != 999999 for t in r["transactions"])

    def test_another_users_transaction_cannot_be_deleted(self, client, auth_headers):
        mine = auth_headers("fin_own_g")
        theirs = auth_headers("fin_own_h")
        cash, _, food, _ = _setup(client, theirs)
        txn = _expense(client, theirs, cash["id"], food["id"], 1000).json()
        assert client.delete(f"/api/finance/transactions/{txn['id']}",
                             headers=mine).status_code == 404


# --- balances --------------------------------------------------------------

class TestBalances:
    def test_a_balance_is_opening_plus_in_minus_out(self, client, auth_headers):
        h = auth_headers("fin_bal1")
        cash = client.post("/api/finance/accounts", headers=h, json={
            "name": "Cash", "group": "cash", "currency": "UZS",
            "opening_balance_minor": 10_000_000}).json()
        food = client.post("/api/finance/categories", headers=h, json={
            "name": "Food", "kind": "expense"}).json()
        salary = client.post("/api/finance/categories", headers=h, json={
            "name": "Salary", "kind": "income"}).json()

        _expense(client, h, cash["id"], food["id"], 600_000)
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "income", "amount_minor": 17_350_000, "occurred_on": "2026-11-18",
            "to_account_id": cash["id"], "category_id": salary["id"]})

        after = next(a for a in client.get("/api/finance/accounts", headers=h).json()
                     if a["id"] == cash["id"])
        assert after["balance_minor"] == 10_000_000 + 17_350_000 - 600_000

    def test_a_transfer_moves_money_without_creating_or_destroying_any(self, client, auth_headers):
        h = auth_headers("fin_bal2")
        cash, card, _, _ = _setup(client, h)
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 31_000_000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": card["id"]})

        accounts = {a["id"]: a["balance_minor"]
                    for a in client.get("/api/finance/accounts", headers=h).json()}
        assert accounts[cash["id"]] == -31_000_000
        assert accounts[card["id"]] == 31_000_000
        assert accounts[cash["id"]] + accounts[card["id"]] == 0

    def test_a_transfer_fee_leaves_the_sending_side(self, client, auth_headers):
        """The far end receives the amount; the fee is a real cost to the sender.
        Charging it to the receiver would invent money that never arrived."""
        h = auth_headers("fin_bal3")
        cash, card, _, _ = _setup(client, h)
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 100_000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": card["id"],
            "fee_minor": 6_000})

        accounts = {a["id"]: a["balance_minor"]
                    for a in client.get("/api/finance/accounts", headers=h).json()}
        assert accounts[cash["id"]] == -106_000
        assert accounts[card["id"]] == 100_000

    def test_a_balance_survives_amounts_too_big_for_a_32_bit_column(self, client, auth_headers):
        """A car in a low-denomination currency. Integer would silently overflow."""
        h = auth_headers("fin_bal4")
        cash = client.post("/api/finance/accounts", headers=h, json={
            "name": "Cash", "group": "cash", "currency": "UZS"}).json()
        salary = client.post("/api/finance/categories", headers=h, json={
            "name": "Salary", "kind": "income"}).json()
        huge = 20_000_000_000  # 200 000 000,00 UZS
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "income", "amount_minor": huge, "occurred_on": "2026-11-18",
            "to_account_id": cash["id"], "category_id": salary["id"]})

        after = client.get("/api/finance/accounts", headers=h).json()[0]
        assert after["balance_minor"] == huge


# --- totals ----------------------------------------------------------------

class TestPeriodTotals:
    def test_transfers_count_as_neither_income_nor_spending(self, client, auth_headers):
        """A month where cash was shuffled to a card is not a month of spending."""
        h = auth_headers("fin_tot1")
        cash, card, food, _ = _setup(client, h)
        _expense(client, h, cash["id"], food["id"], 6_000)
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 31_000_000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": card["id"]})

        totals = client.get("/api/finance/ledger", headers=h, params={
            "start": "2026-11-01", "end": "2026-11-30"}).json()["totals"]
        assert totals["expense_minor"] == 6_000
        assert totals["income_minor"] == 0
        assert totals["net_minor"] == -6_000

    def test_the_window_excludes_days_outside_it(self, client, auth_headers):
        h = auth_headers("fin_tot2")
        cash, _, food, _ = _setup(client, h)
        _expense(client, h, cash["id"], food["id"], 1_000, day="2026-10-31")
        _expense(client, h, cash["id"], food["id"], 2_000, day="2026-11-01")
        _expense(client, h, cash["id"], food["id"], 4_000, day="2026-11-30")
        _expense(client, h, cash["id"], food["id"], 8_000, day="2026-12-01")

        totals = client.get("/api/finance/ledger", headers=h, params={
            "start": "2026-11-01", "end": "2026-11-30"}).json()["totals"]
        assert totals["expense_minor"] == 6_000

    def test_a_foreign_currency_row_is_converted_at_its_own_stored_rate(self, client, auth_headers):
        """The rate is the one from the day, not today's — otherwise last
        year's totals change every time the exchange rate moves."""
        h = auth_headers("fin_tot3")
        usd = client.post("/api/finance/accounts", headers=h, json={
            "name": "Dollars", "group": "cash", "currency": "USD"}).json()
        food = client.post("/api/finance/categories", headers=h, json={
            "name": "Food", "kind": "expense"}).json()
        # $10.00 at 12 000 som to the dollar = 120 000,00 UZS
        _expense(client, h, usd["id"], food["id"], 1_000, rate_to_main=12_000.0)

        totals = client.get("/api/finance/ledger", headers=h, params={
            "start": "2026-11-01", "end": "2026-11-30"}).json()["totals"]
        assert totals["expense_minor"] == 12_000_000


# --- categories ------------------------------------------------------------

class TestCategories:
    def test_a_subcategory_sits_under_a_parent_of_the_same_kind(self, client, auth_headers):
        h = auth_headers("fin_cat1")
        _, _, food, salary = _setup(client, h)
        assert client.post("/api/finance/categories", headers=h, json={
            "name": "Lunch", "kind": "expense", "parent_id": food["id"]}).status_code == 201
        assert client.post("/api/finance/categories", headers=h, json={
            "name": "Bonus", "kind": "income", "parent_id": food["id"]}).status_code == 400

    def test_categories_stop_at_one_level(self, client, auth_headers):
        h = auth_headers("fin_cat2")
        _, _, food, _ = _setup(client, h)
        lunch = client.post("/api/finance/categories", headers=h, json={
            "name": "Lunch", "kind": "expense", "parent_id": food["id"]}).json()
        r = client.post("/api/finance/categories", headers=h, json={
            "name": "Somsa", "kind": "expense", "parent_id": lunch["id"]})
        assert r.status_code == 400
        assert "one level" in r.json()["detail"]

    def test_a_subcategory_inherits_its_parents_icon_for_display(self, client, auth_headers):
        h = auth_headers("fin_cat3")
        cash, _, food, _ = _setup(client, h)
        lunch = client.post("/api/finance/categories", headers=h, json={
            "name": "Lunch", "kind": "expense", "parent_id": food["id"]}).json()
        txn = _expense(client, h, cash["id"], lunch["id"], 60_000).json()
        assert txn["category_name"] == "Lunch"
        assert txn["parent_category_name"] == "Food"
        assert txn["category_icon"] == "🍜"


# --- the switch and the settings -------------------------------------------

class TestTheSwitch:
    def test_finance_is_off_until_there_is_data_or_a_choice(self, client, auth_headers):
        h = auth_headers("fin_sw1")
        assert client.get("/api/finance/settings", headers=h).json()["finance_enabled"] is False

    def test_creating_an_account_turns_it_on_without_being_asked(self, client, auth_headers):
        h = auth_headers("fin_sw2")
        client.post("/api/finance/accounts", headers=h, json={
            "name": "Cash", "group": "cash", "currency": "UZS"})
        assert client.get("/api/finance/settings", headers=h).json()["finance_enabled"] is True

    def test_switching_it_off_destroys_nothing(self, client, auth_headers):
        h = auth_headers("fin_sw3")
        cash, _, food, _ = _setup(client, h)
        _expense(client, h, cash["id"], food["id"], 6_000)

        client.put("/api/finance/settings", headers=h, json={"finance_enabled": False})
        assert client.get("/api/finance/settings", headers=h).json()["finance_enabled"] is False

        client.put("/api/finance/settings", headers=h, json={"finance_enabled": True})
        rows = client.get("/api/finance/ledger", headers=h, params={
            "start": "2026-11-01", "end": "2026-11-30"}).json()["transactions"]
        assert len(rows) == 1

    def test_no_currency_is_assumed_for_a_new_user(self, client, auth_headers):
        """Rule 1: nothing in here may decide that somebody is Uzbek."""
        h = auth_headers("fin_sw4")
        assert client.get("/api/finance/settings", headers=h).json()["main_currency"] is None

    def test_the_month_can_start_on_payday(self, client, auth_headers):
        h = auth_headers("fin_sw5")
        assert client.get("/api/finance/settings", headers=h).json()["period_start_day"] == 1
        client.put("/api/finance/settings", headers=h, json={"period_start_day": 25})
        assert client.get("/api/finance/settings", headers=h).json()["period_start_day"] == 25
        assert client.put("/api/finance/settings", headers=h,
                          json={"period_start_day": 31}).status_code == 400


# --- the rule that must not break ------------------------------------------

class TestMoneyEarnsNoPoints:
    def test_logging_money_pays_no_bat_points(self, client, auth_headers):
        """The work-track boundary, for a sharper reason: paying for logging
        rewards logging over accuracy, and paying for spending gamifies money."""
        h = auth_headers("fin_points")
        before = client.get("/api/account", headers=h).json()
        cash, card, food, salary = _setup(client, h)

        _expense(client, h, cash["id"], food["id"], 120_000)
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "income", "amount_minor": 17_350_000, "occurred_on": "2026-11-18",
            "to_account_id": cash["id"], "category_id": salary["id"]})
        client.post("/api/finance/transactions", headers=h, json={
            "kind": "transfer", "amount_minor": 31_000_000, "occurred_on": "2026-11-18",
            "from_account_id": cash["id"], "to_account_id": card["id"]})

        after = client.get("/api/account", headers=h).json()
        assert after["points"] == before["points"]
        assert after["bat_level"] == before["bat_level"]


class TestCurrencyExponents:
    def test_the_minor_unit_is_two_digits_unless_the_currency_says_otherwise(self):
        from services import finance_service as fs
        assert fs.exponent("UZS") == 2
        assert fs.exponent("USD") == 2
        assert fs.exponent("JPY") == 0
        assert fs.exponent("KWD") == 3
        assert fs.exponent("uzs") == 2

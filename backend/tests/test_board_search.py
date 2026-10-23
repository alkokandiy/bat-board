"""Finding what the user called it, not what the board stored.

"Restart screen time challenge" was declared not to exist, while
"Restart the screen-time challenge" sat on the board. Telling somebody their
own item is missing, when it is right there, is worse than being slow: they
stop believing the board.

Also covers the fabrication that prompted this work — asked to list work
tasks on a retry with no work tool available, Alfred produced eight generic
office tasks rather than admitting he could not look.
"""

import models
from database import SessionLocal
from services import alfred_agent, alfred_tools, board_search

_n = [1020000]


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"bs{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne",
                              work_enabled=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _missions(db, uid, titles):
    for t in titles:
        db.add(models.BatMission(owner_id=uid, title=t, status="pending"))
    db.commit()


# --- the reported failure --------------------------------------------------

def test_a_paraphrased_title_is_found():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _missions(db, uid, ["Restart the screen-time challenge", "Mission Statement"])
        out = board_search.search(db, user, "Restart screen time challenge")
        assert out["matches"], "the item is on the board and must be found"
        assert out["matches"][0]["title"] == "Restart the screen-time challenge"
        assert out["matches"][0]["kind"] == "mission"
    finally:
        db.close()


def test_a_typo_in_either_direction_still_matches():
    """Their typing and the stored title are both imperfect."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _missions(db, uid, ["applying NUriddin pirces to Sardor prices"])
        assert board_search.search(db, user, "nuriddin prices")["matches"]
    finally:
        db.close()


def test_a_fragment_of_the_title_is_enough():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _missions(db, uid, ["Restart the screen-time challenge"])
        assert board_search.search(db, user, "screen time")["matches"]
    finally:
        db.close()


def test_something_genuinely_absent_returns_nothing_and_says_what_to_do():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _missions(db, uid, ["Mission Statement"])
        out = board_search.search(db, user, "buy a helicopter")
        assert out["matches"] == []
        # It must not encourage a flat denial.
        assert "before telling them it does not exist" in out["note"].lower()
    finally:
        db.close()


def test_it_searches_every_kind_and_can_be_narrowed():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatMission(owner_id=uid, title="Screen time", status="pending"))
        db.add(models.BatHabit(owner_id=uid, name="Screen time", frequency="daily"))
        db.add(models.BatNote(owner_id=uid, title="Screen time"))
        db.commit()
        kinds = {m["kind"] for m in board_search.search(db, user, "screen time")["matches"]}
        assert {"mission", "habit", "note"} <= kinds
        only = board_search.search(db, user, "screen time", kinds=["habit"])["matches"]
        assert {m["kind"] for m in only} == {"habit"}
    finally:
        db.close()


def test_results_are_scoped_to_their_owner():
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        _missions(db, theirs, ["Secret plan"])
        out = board_search.search(db, db.get(models.BatAccount, mine), "Secret plan")
        assert out["matches"] == []
    finally:
        db.close()


def test_the_best_match_comes_first():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _missions(db, uid, ["Weekly Sunday Checklist", "Checklist"])
        assert board_search.search(db, user, "Checklist")["matches"][0]["title"] == "Checklist"
    finally:
        db.close()


def test_scoring_refuses_to_match_unrelated_text():
    assert board_search.score("buy milk", "Restart the screen-time challenge") < board_search.MATCH_FLOOR


# --- never invent what you could not read ----------------------------------

def test_the_charter_forbids_naming_anything_not_just_read():
    """Eight invented office tasks, indistinguishable from real ones."""
    prompt = alfred_agent.IDENTITY_CORE.lower()
    assert "every item you name must have come from a tool result in this turn" in prompt
    assert "if you cannot look, say so" in prompt
    assert "search before you deny" in prompt


def test_find_on_board_is_registered_and_listed_as_a_capability():
    assert "find_on_board" in alfred_tools.TOOL_NAMES
    assert "find_on_board" in alfred_tools.capability_summary()
    assert "find_on_board" in alfred_tools.LEAN_TOOL_NAMES


def test_a_bare_ok_is_not_treated_as_consent_to_an_old_suggestion():
    """Told "ok" about a university-lesson reminder, he replied "shall I begin
    the focus session for the movie bot?" — an agenda from an hour earlier."""
    prompt = alfred_agent.IDENTITY_CORE.lower()
    assert "a short reply answers the last thing said" in prompt
    assert "not your agenda" in prompt

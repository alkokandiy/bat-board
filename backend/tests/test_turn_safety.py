"""The three faults behind the garbled 02:38-02:41 Telegram exchange.

1. Several deletions in one turn armed only the FIRST, while the reply named
   them all — so YES silently did less than it promised.
2. Two messages sent seconds apart ran as concurrent turns that could not see
   each other, so replies answered the wrong message.
3. A long turn gave no sign of life, which is why the message was sent twice
   in the first place.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import alfred_agent

_n = [800000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ts{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _missions(db, uid, titles):
    ids = []
    for t in titles:
        m = models.BatMission(owner_id=uid, title=t, status="pending")
        db.add(m)
        db.flush()
        ids.append(m.id)
    db.commit()
    return ids


# --- 1. the batch confirmation gate ----------------------------------------

def test_confirming_a_batch_deletes_every_item_it_named():
    """The regression that lost data: four were listed, one was armed."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ids = _missions(db, uid, ["Mani ideam", "Sizi startupiz",
                                  "Websute buyicha", "Kanallar buyicha"])
        calls = [("delete_mission", {"mission_id": i}) for i in ids]

        message = alfred_agent.gate_destructive_tools(db, user, calls)
        # Everything it is about to delete is named in the confirmation.
        for title in ("Mani ideam", "Sizi startupiz",
                      "Websute buyicha", "Kanallar buyicha"):
            assert title in message
        assert "YES" in message

        status, reply = alfred_agent.check_pending_action(db, user, "YES")
        assert status == "handled"
        remaining = db.query(models.BatMission).filter_by(owner_id=uid).count()
        assert remaining == 0, "YES must delete everything it listed"
        for title in ("Mani ideam", "Kanallar buyicha"):
            assert title in reply
    finally:
        db.close()


def test_a_single_deletion_still_uses_the_plain_wording():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        (mid,) = _missions(db, uid, ["Only one"])
        message = alfred_agent.gate_destructive_tools(
            db, user, [("delete_mission", {"mission_id": mid})])
        assert message == ("Delete the mission 'Only one'? This can't be undone. "
                           "Reply YES to confirm.")
        alfred_agent.check_pending_action(db, user, "YES")
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 0
    finally:
        db.close()


def test_targets_that_no_longer_exist_are_dropped_not_invented():
    """A stale id must not become a phantom line in the confirmation."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        (good,) = _missions(db, uid, ["Real one"])
        message = alfred_agent.gate_destructive_tools(db, user, [
            ("delete_mission", {"mission_id": good}),
            ("delete_mission", {"mission_id": 999999}),
        ])
        assert "Real one" in message
        row = db.query(models.BatPendingAlfredAction).filter_by(owner_id=uid).first()
        # One real target left, so it falls back to the single-item gate.
        assert row.action_type == "delete_mission"
    finally:
        db.close()


def test_nothing_is_armed_when_no_target_exists():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.gate_destructive_tools(
            db, user, [("delete_mission", {"mission_id": 999999})]) is None
        assert db.query(models.BatPendingAlfredAction).filter_by(owner_id=uid).first() is None
    finally:
        db.close()


def test_anything_other_than_yes_cancels_a_batch():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ids = _missions(db, uid, ["One", "Two"])
        alfred_agent.gate_destructive_tools(
            db, user, [("delete_mission", {"mission_id": i}) for i in ids])
        status, _ = alfred_agent.check_pending_action(db, user, "actually no")
        assert status == "fallthrough"
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 2
    finally:
        db.close()


# --- 2. the per-user turn lock ---------------------------------------------

def test_a_second_turn_cannot_start_while_the_first_holds_the_lock():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.try_acquire_turn_lock(db, user) is True
        assert alfred_agent.try_acquire_turn_lock(db, user) is False
        alfred_agent.release_turn_lock(db, user)
        assert alfred_agent.try_acquire_turn_lock(db, user) is True
    finally:
        alfred_agent.release_turn_lock(db, user)
        db.close()


def test_the_lock_is_released_even_when_the_turn_raises():
    """A turn that blows up must not wedge the user out of their own bot."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)

        async def boom():
            async with alfred_agent.turn_lock(db, user):
                raise RuntimeError("turn exploded")

        try:
            _run(boom())
        except RuntimeError:
            pass
        assert db.get(models.BatAlfredTurnLock, uid) is None
    finally:
        db.close()


def test_a_lock_left_by_a_dead_worker_is_reclaimed():
    """Without this a crashed process would silence Alfred for that user."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        stale = datetime.now(timezone.utc) - alfred_agent.TURN_LOCK_TTL - timedelta(minutes=1)
        db.add(models.BatAlfredTurnLock(owner_id=uid, claimed_at=stale.replace(tzinfo=None)))
        db.commit()
        assert alfred_agent.try_acquire_turn_lock(db, user) is True
    finally:
        alfred_agent.release_turn_lock(db, user)
        db.close()


def test_a_live_lock_is_not_stolen():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        db.add(models.BatAlfredTurnLock(
            owner_id=uid, claimed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()
        assert alfred_agent.try_acquire_turn_lock(db, user) is False
    finally:
        alfred_agent.release_turn_lock(db, user)
        db.close()


def test_waiting_for_the_lock_gives_up_rather_than_interleaving():
    """Proceeding anyway would reintroduce the bug the lock exists to stop."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.try_acquire_turn_lock(db, user) is True

        async def second():
            async with alfred_agent.turn_lock(db, user, wait_seconds=0.05):
                return "should not get here"

        try:
            _run(second())
            raise AssertionError("expected TurnBusyError")
        except alfred_agent.TurnBusyError:
            pass
    finally:
        alfred_agent.release_turn_lock(db, user)
        db.close()


def test_locks_are_per_user():
    """One busy user must never block anybody else."""
    a, b = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        ua, ub = db.get(models.BatAccount, a), db.get(models.BatAccount, b)
        assert alfred_agent.try_acquire_turn_lock(db, ua) is True
        assert alfred_agent.try_acquire_turn_lock(db, ub) is True
    finally:
        for uid in (a, b):
            alfred_agent.release_turn_lock(db, db.get(models.BatAccount, uid))
        db.close()


# --- the exact failure from the 02:41 screenshot ---------------------------

def test_a_turn_asking_to_remove_four_missions_arms_all_four(monkeypatch):
    """End-to-end through the tool loop, not just the gate helper.

    This is the reported bug: Alfred listed four missions, the loop armed the
    first and returned, and YES deleted one while the user believed four had
    gone.
    """
    from services import llm_provider

    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        ids = _missions(db, uid, ["Mani ideam", "Sizi startupiz",
                                  "Websute buyicha", "Kanallar buyicha"])

        class Adapter:
            """Emits four parallel delete_mission calls, as the real model did."""

            def __init__(self):
                self.calls = 0

            async def generate(self, messages, tools, system_instruction=None):
                self.calls += 1
                return llm_provider.LLMResponse(
                    text="I will remove those four.",
                    tool_calls=[
                        llm_provider.ToolCall(name="delete_mission",
                                              arguments={"mission_id": i})
                        for i in ids
                    ],
                )

        monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user",
                            lambda db, user: Adapter())
        reply = _run(alfred_agent.run_turn(
            db, user, "remove ideam, startupiz, webstie and kanallar"))
    finally:
        db.close()

    # One confirmation, naming every mission it will delete.
    for title in ("Mani ideam", "Sizi startupiz",
                  "Websute buyicha", "Kanallar buyicha"):
        assert title in reply, f"{title} missing from the confirmation"

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        status, _ = alfred_agent.check_pending_action(db, user, "YES")
        assert status == "handled"
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 0
    finally:
        db.close()


# --- "delete all my habits" ------------------------------------------------

def test_deleting_every_habit_is_one_confirmation_not_a_march(monkeypatch):
    """The reported misery: six habits meant twelve messages and three hours.

    Alfred told the user he could only delete them individually, then asked
    for his own confirmation before the system's — two YESes per habit.
    """
    from services import llm_provider

    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        names = ["Memorization (1 page)", "Math", "Reading (30 mins)",
                 "Exercise (30 mins)", "Write autobiography", "Rivojlanish Kundaligi"]
        hids = []
        for n in names:
            h = models.BatHabit(owner_id=uid, name=n, frequency="daily", streak=0)
            db.add(h)
            db.flush()
            hids.append(h.id)
        db.commit()

        class Adapter:
            async def generate(self, messages, tools, system_instruction=None):
                return llm_provider.LLMResponse(
                    text="",
                    tool_calls=[llm_provider.ToolCall(name="delete_habit",
                                                      arguments={"habit_id": i})
                                for i in hids],
                )

        monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user",
                            lambda db, user: Adapter())
        reply = _run(alfred_agent.run_turn(db, user, "remove all habits"))
    finally:
        db.close()

    for n in names:
        assert n in reply, f"{n} missing from the single confirmation"

    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        status, _ = alfred_agent.check_pending_action(db, user, "YES")
        assert status == "handled"
        assert db.query(models.BatHabit).filter_by(owner_id=uid).count() == 0, \
            "one YES must clear every habit it listed"
    finally:
        db.close()


def test_cancelling_a_gate_tells_the_model_nothing_was_deleted(monkeypatch):
    """Alfred announced 'Deleted Math' for a habit that was never deleted.

    He had armed it, the user replied with something other than YES, and he
    then narrated the deletion as done. The cancellation must reach him.
    """
    from services import llm_provider

    uid = _mk_user()
    seen = {}
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        h = models.BatHabit(owner_id=uid, name="Math", frequency="daily", streak=0)
        db.add(h)
        db.commit()
        alfred_agent.gate_destructive_tools(
            db, user, [("delete_habit", {"habit_id": h.id})])

        class Adapter:
            async def generate(self, messages, tools, system_instruction=None):
                seen["last_user"] = messages[-1]["content"]
                return llm_provider.LLMResponse(text="Understood.", tool_calls=[])

        monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user",
                            lambda db, user: Adapter())
        _run(alfred_agent.run_turn(db, user, "and?"))

        # The habit survived, and the model was told so in as many words.
        assert db.query(models.BatHabit).filter_by(owner_id=uid).count() == 1
        assert "CANCELLED" in seen["last_user"]
        assert "NOTHING was deleted" in seen["last_user"]
        assert "and?" in seen["last_user"]
    finally:
        db.close()


def test_the_charter_tells_him_he_can_batch_and_must_not_pre_announce():
    """He refused to batch-delete because nothing had told him he could."""
    prompt = alfred_agent.IDENTITY_CORE.lower()
    assert "delete several at once" in prompt
    assert "do not ask first" in prompt
    assert "nothing is deleted until the system says so" in prompt


# --- he has no hands -------------------------------------------------------

def test_the_charter_rules_out_the_physical_world():
    """He offered to make a pot of tea. He is software with a database."""
    from services import alfred_principles

    charter = alfred_principles.charter().lower()
    assert "you have no hands and no world" in charter
    for impossible in ("tea", "fetch", "cook", "drive", "door"):
        assert impossible in charter, impossible


def test_the_charter_stops_him_answering_with_an_inventory():
    """"Yes, attending" earned a list of five undated missions.

    Checked on the CHAT charter specifically: this is a conversational
    failure, so the rule has to survive the trimmed version that every model
    call carries, not just the full one used for unprompted messages.
    """
    from services import alfred_principles

    for charter in (alfred_principles.charter().lower(),
                    alfred_principles.charter(full=True).lower()):
        assert "say one thing" in charter
        assert "never volunteer a review of what is incomplete" in charter


def test_the_charter_reads_the_whole_board_before_offering_rest():
    from services import alfred_principles

    for charter in (alfred_principles.charter().lower(),
                    alfred_principles.charter(full=True).lower()):
        assert "clear calendar is not a clear life" in charter \
            or "clear calendar does not mean a clear life" in charter


def test_the_chat_charter_is_markedly_smaller_than_the_full_one():
    """It rides on every model call, including each step of a tool loop."""
    from services import alfred_principles

    chat = alfred_principles.charter()
    full = alfred_principles.charter(full=True)
    assert len(chat) < len(full) * 0.8
    # The rules that must never be trimmed away to save room.
    low = chat.lower()
    assert "you have no hands and no world" in low
    assert "describe, do not diagnose" in low
    assert "21 days" in low and "25 minutes" in low

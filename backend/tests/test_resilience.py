"""Surviving a provider that will not answer, and never deleting the wrong thing.

Two real incidents drive this file.

A provider returned 503 on a full-sized request ("can you merge them into one
task?") and the whole turn was lost to an apology. A full request carries the
charter plus 48 tool schemas — roughly 11,000 tokens — and a loaded model can
refuse or stall on that while answering something smaller perfectly well.

Separately, and far worse: Alfred armed the deletion of "Fix Calendar, better
view, start from Monday." during a conversation about two Quran missions. The
gate worked exactly as designed — it resolved the id it was handed. The id was
invented.
"""

import asyncio

import models
from database import SessionLocal
from services import alfred_agent, alfred_tools, llm_provider

_n = [950000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _mk_user():
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"rs{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _mission(db, uid, title, **kw):
    m = models.BatMission(owner_id=uid, title=title, status="pending", **kw)
    db.add(m)
    db.flush()
    db.commit()
    return m.id


class _Dead:
    async def generate(self, messages, tools, system_instruction=None):
        raise llm_provider.LLMServiceError("provider API unavailable")


# --- the lean retry --------------------------------------------------------

def test_a_failed_full_request_is_retried_smaller_and_succeeds(monkeypatch):
    uid = _mk_user()
    seen = []

    class Flaky:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, tools, system_instruction=None):
            self.calls += 1
            seen.append({"system": messages[0]["content"], "tools": len(tools),
                         "messages": len(messages)})
            if self.calls == 1:
                raise llm_provider.LLMServiceError("provider API unavailable")
            return llm_provider.LLMResponse(text="Merged them, sir.", tool_calls=[])

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: Flaky())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        reply = _run(alfred_agent.run_turn(db, user, "can you merge them into one task?"))
    finally:
        db.close()

    assert reply == "Merged them, sir."
    assert len(seen) == 2
    # The second attempt is genuinely smaller — that is the whole point.
    assert len(seen[1]["system"]) * 5 < len(seen[0]["system"])
    assert seen[1]["tools"] < seen[0]["tools"]


def test_the_retry_still_carries_what_the_user_asked_for(monkeypatch):
    uid = _mk_user()
    seen = {}

    class Flaky:
        def __init__(self):
            self.calls = 0

        async def generate(self, messages, tools, system_instruction=None):
            self.calls += 1
            if self.calls == 1:
                raise llm_provider.LLMServiceError("down")
            seen["last"] = messages[-1]["content"]
            return llm_provider.LLMResponse(text="Done.", tool_calls=[])

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: Flaky())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        _run(alfred_agent.run_turn(db, user, "merge them both, Qada is primary"))
    finally:
        db.close()
    assert "Qada is primary" in seen["last"]


def test_a_turn_that_works_first_time_is_never_retried(monkeypatch):
    uid = _mk_user()
    calls = []

    class Fine:
        async def generate(self, messages, tools, system_instruction=None):
            calls.append(1)
            return llm_provider.LLMResponse(text="Very good, sir.", tool_calls=[])

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: Fine())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        assert _run(alfred_agent.run_turn(db, user, "hello")) == "Very good, sir."
    finally:
        db.close()
    assert len(calls) == 1


def test_the_lean_retry_keeps_every_way_of_LOOKING_at_the_board():
    """The worst possible saving, and it really happened.

    With the work tools dropped from the lean set, "list all work tasks"
    reached a retry that had no way to look — and Alfred answered with eight
    invented office tasks instead of saying he could not. A read is what
    people ask for most and costs the least, so every read stays.
    """
    assert alfred_tools.LEAN_TOOL_NAMES <= alfred_tools.TOOL_NAMES
    assert alfred_tools.LEAN_TOOL_NAMES < alfred_tools.TOOL_NAMES   # still a subset
    reads = {t for t in alfred_tools.TOOL_NAMES
             if t.startswith(("list_", "get_"))
             or t in ("work_report", "review_loose_ends", "alfred_recall",
                      "suggest_focus_length")}
    assert reads <= alfred_tools.LEAN_TOOL_NAMES, reads - alfred_tools.LEAN_TOOL_NAMES
    for essential in ("list_work_tasks", "list_missions", "list_habits",
                      "list_notes", "complete_work_task", "delete_mission"):
        assert essential in alfred_tools.LEAN_TOOL_NAMES, essential


def test_the_lean_prompt_forbids_filling_a_gap_from_memory():
    """A missing tool must produce a blank, never a plausible invention."""
    lean = alfred_agent.LEAN_PROMPT.lower()
    assert "never invent anything on their board" in lean
    assert "cannot reach it" in lean


# --- still useful with no model at all -------------------------------------

def test_when_everything_fails_he_reports_the_board_instead_of_only_apologising(monkeypatch):
    uid = _mk_user()
    db = SessionLocal()
    try:
        for t in ("One", "Two", "Three"):
            _mission(db, uid, t)
        db.add(models.BatHabit(owner_id=uid, name="Memorization", frequency="daily"))
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: _Dead())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        reply = _run(alfred_agent.run_turn(db, user, "what do I have on?"))
    finally:
        db.close()

    assert "provider" in reply.lower()
    assert "/setkey" in reply
    assert "3 missions open" in reply
    assert "1 habit unticked" in reply      # singular, not "1 habits"


def test_the_degraded_reply_counts_one_thing_in_the_singular():
    uid = _mk_user()
    db = SessionLocal()
    try:
        _mission(db, uid, "Only one")
        user = db.get(models.BatAccount, uid)
        reply = alfred_agent.degraded_reply(db, user)
        assert "1 mission open" in reply and "1 missions" not in reply
    finally:
        db.close()


def test_the_degraded_reply_is_scoped_to_its_owner():
    mine, theirs = _mk_user(), _mk_user()
    db = SessionLocal()
    try:
        for t in ("Not mine", "Also not mine"):
            _mission(db, theirs, t)
        reply = alfred_agent.degraded_reply(db, db.get(models.BatAccount, mine))
        assert "missions open" not in reply
    finally:
        db.close()


def test_the_degraded_reply_survives_a_broken_database_read(monkeypatch):
    """A failing fallback must never replace the reply with a stack trace."""
    uid = _mk_user()
    monkeypatch.setattr(alfred_agent, "local_now",
                        lambda u: (_ for _ in ()).throw(RuntimeError("boom")))
    db = SessionLocal()
    try:
        reply = alfred_agent.degraded_reply(db, db.get(models.BatAccount, uid))
    finally:
        db.close()
    assert "provider" in reply.lower()


def test_a_rate_limit_is_not_retried_leaner(monkeypatch):
    """A second request would be rejected just as fast; say so and stop."""
    uid = _mk_user()
    calls = []

    class Limited:
        async def generate(self, messages, tools, system_instruction=None):
            calls.append(1)
            raise llm_provider.LLMLimitError("429")

    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: Limited())
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
        reply = _run(alfred_agent.run_turn(db, user, "hello"))
    finally:
        db.close()
    assert reply == alfred_agent.RATE_LIMIT_REPLY
    assert len(calls) == 1


# --- never delete the wrong thing ------------------------------------------

def test_a_guessed_id_is_refused_instead_of_armed(monkeypatch):
    """The reported incident, reproduced.

    The user is discussing two Quran missions; the model hands over the id of
    an unrelated calendar mission. Before this check the user was asked to
    confirm deleting THAT, and a distracted YES would have done it.
    """
    uid = _mk_user()
    db = SessionLocal()
    try:
        wrong_id = _mission(db, uid, "Fix Calendar, better view, start from Monday.")
        _mission(db, uid, "Set up new bot for Qada tracking")

        class Guessing:
            def __init__(self):
                self.calls = 0

            async def generate(self, messages, tools, system_instruction=None):
                self.calls += 1
                if self.calls == 1:
                    return llm_provider.LLMResponse(text="", tool_calls=[
                        llm_provider.ToolCall(
                            name="delete_mission",
                            arguments={"mission_id": wrong_id,
                                       "expected_title": "Set up new bot for Qada tracking"})])
                return llm_provider.LLMResponse(text="Let me check the list again.",
                                                tool_calls=[])

        monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, u: Guessing())
        user = db.get(models.BatAccount, uid)
        reply = _run(alfred_agent.run_turn(db, user, "merge them, Qada is primary"))

        # Nothing was armed, and the calendar mission is untouched.
        assert "Fix Calendar" not in reply
        assert db.query(models.BatPendingAlfredAction).filter_by(owner_id=uid).first() is None
        assert db.query(models.BatMission).filter_by(owner_id=uid).count() == 2
    finally:
        db.close()


def test_a_correct_target_passes_straight_through():
    uid = _mk_user()
    db = SessionLocal()
    try:
        mid = _mission(db, uid, "Set up new bot for Qada tracking")
        user = db.get(models.BatAccount, uid)
        assert alfred_agent.wrong_target(db, user, "delete_mission", {
            "mission_id": mid,
            "expected_title": "Set up new bot for Qada tracking"}) is None
    finally:
        db.close()


def test_small_differences_in_wording_are_forgiven():
    """Refusing every retyped title would make deletion impossible."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        mid = _mission(db, uid, "Review Quran tracker and resume Hifz routine")
        user = db.get(models.BatAccount, uid)
        for close_enough in ("review quran tracker and resume hifz routine",
                             "Review Quran tracker and resume Hifz routine.",
                             "Review Quran tracker  and resume Hifz  routine"):
            assert alfred_agent.wrong_target(db, user, "delete_mission", {
                "mission_id": mid, "expected_title": close_enough}) is None
    finally:
        db.close()


def test_a_wholly_different_title_is_caught():
    uid = _mk_user()
    db = SessionLocal()
    try:
        mid = _mission(db, uid, "Fix Calendar, better view, start from Monday.")
        user = db.get(models.BatAccount, uid)
        out = alfred_agent.wrong_target(db, user, "delete_mission", {
            "mission_id": mid, "expected_title": "Set up new bot for Qada tracking"})
        assert out is not None
        assert "WRONG TARGET" in out["error"]
        assert out["what_that_id_actually_is"].startswith("Fix Calendar")
    finally:
        db.close()


def test_every_delete_tool_demands_a_stated_target():
    """If one is missed, that tool keeps the old guess-and-arm behaviour."""
    for tool in alfred_tools.DESTRUCTIVE_TOOLS:
        schema = tool.get("parameters") or tool.get("input_schema") or {}
        assert "expected_title" in schema.get("properties", {}), tool["name"]
        assert "expected_title" in schema.get("required", []), tool["name"]

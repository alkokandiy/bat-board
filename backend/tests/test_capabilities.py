"""Alfred knowing what he can do, and working out how.

He kept refusing things he was perfectly able to do — "I cannot delete them
all at once", when deleting six items is six calls. The failure was never the
tools; it was that he had no model of them, and treated "no single tool for
this" as "impossible".

A hand-written list of abilities would drift from the registry within a
release, so the inventory is generated from the live tools and an assert at
import time refuses to let a tool go unlisted.
"""

import models
from database import SessionLocal
from services import alfred_agent, alfred_tools, work_service

_n = [1010000]


def _mk_user(**kw):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"cap{_n[0]}", hashed_password="x",
                              timezone="UTC", alfred_address="Master Wayne", **kw)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


# --- the inventory cannot drift -------------------------------------------

def test_every_tool_appears_in_the_inventory():
    """A tool he is never told about is a tool he will refuse to use."""
    grouped = {n for _, names in alfred_tools.CAPABILITY_GROUPS for n in names}
    assert grouped == alfred_tools.TOOL_NAMES, (
        f"ungrouped: {alfred_tools.TOOL_NAMES - grouped}, "
        f"unknown: {grouped - alfred_tools.TOOL_NAMES}")


def test_no_tool_is_listed_in_two_places():
    seen, dupes = set(), set()
    for _, names in alfred_tools.CAPABILITY_GROUPS:
        for n in names:
            (dupes if n in seen else seen).add(n)
    assert not dupes


def test_the_summary_names_the_tools_it_claims():
    summary = alfred_tools.capability_summary()
    for essential in ("delete_mission", "create_missions", "log_past_focus",
                      "check_in_habit", "review_loose_ends"):
        assert essential in summary


def test_the_summary_is_small_enough_to_send_every_turn():
    """It rides on every model call, including each step of a tool loop."""
    assert len(alfred_tools.capability_summary()) < 2500


def test_it_only_claims_what_this_user_actually_has():
    """Someone with the work track off must not be told he can do work things."""
    available = alfred_tools.TOOL_NAMES - alfred_tools.WORK_TOOL_NAMES
    summary = alfred_tools.capability_summary(available)
    assert "complete_work_task" not in summary
    assert "list_missions" in summary


# --- what reaches the prompt ----------------------------------------------

def test_the_prompt_lists_his_abilities_and_follows_the_work_switch():
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)

        work_service.set_enabled(db, user, True)
        on = alfred_agent._build_system_prompt(user, work_enabled=True, db=db)
        assert "complete_work_task" in on

        work_service.set_enabled(db, user, False)
        off = alfred_agent._build_system_prompt(user, work_enabled=False, db=db)
        assert "complete_work_task" not in off
        # The everyday board survives either way.
        assert "delete_mission" in on and "delete_mission" in off
    finally:
        db.close()


def test_the_prompt_teaches_composition_rather_than_listing_cases():
    """The general fix. Patching "you CAN batch-delete" does not generalise to
    merging, rescheduling, or whatever he is asked next."""
    prompt = alfred_agent.IDENTITY_CORE
    assert "NO SINGLE TOOL FOR IT DOES NOT MEAN YOU CANNOT DO IT" in prompt
    assert "NEVER ANNOUNCE A LIMIT YOU HAVE NOT CHECKED" in prompt
    assert "QUANTITY IS NEVER THE OBSTACLE" in prompt
    # And the short, honest list of what really is beyond him.
    assert "outside bat-board" in prompt


def test_a_partial_job_is_reported_rather_than_refused():
    """"Too many to do" must become "here is what I did", never "I cannot"."""
    prompt = alfred_agent.IDENTITY_CORE
    assert "say exactly which are done and which remain" in prompt


def test_building_the_prompt_without_a_session_still_works():
    """Callers that have no db (tests, tooling) must not crash on capabilities."""
    uid = _mk_user()
    db = SessionLocal()
    try:
        user = db.get(models.BatAccount, uid)
    finally:
        db.close()
    out = alfred_agent._build_system_prompt(user, work_enabled=True)
    assert "delete_mission" in out

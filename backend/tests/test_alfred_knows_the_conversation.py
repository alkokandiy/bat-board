"""Alfred can see what he said, and what the user replied to.

Three failures the owner reported from one screenshot:

  "it's just firing messages without knowing the context, what sent last
   time and what received."
  "if i reply to older message it doesn't know i am replying."
  "the shittest thing here is telling me to another mission."

The third is the one that matters. He replied to a message about his
medication reminder with "Change it's time" and was answered "I have found
the mission to learn dots, sir." None of the three were prompt failures:
proactive messages were never written to the message table, reply_to_message
was never read, and the board matcher scored any substring at 0.92.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import models
from database import SessionLocal
from services import alfred_agent, alfred_context, board_search, briefing_service

_n = [993000]


def _mk_user(**kw):
    _n[0] += 1
    db = SessionLocal()
    try:
        u = models.BatAccount(username=f"ac{_n[0]}", hashed_password="x",
                              timezone=kw.pop("timezone", "UTC"), **kw)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


class TestTheMatcherThatFoundLearnDots:
    """score("a", "Learn dots") used to be 0.92."""

    def test_a_single_letter_is_not_a_confident_match(self):
        assert board_search.score("a", "Learn dots") < board_search.MATCH_FLOOR

    def test_a_fragment_of_a_word_is_not_a_match(self):
        # "do" is inside "learn dots"; it is not what anyone meant by it.
        assert board_search.score("do", "Learn dots") < board_search.MATCH_FLOOR

    def test_a_near_miss_survives_but_is_not_confident(self):
        """"earn" is a plausible typo for "learn", so it still scores on
        character similarity — it just no longer scores 0.92."""
        sc = board_search.score("earn", "Learn dots")
        assert sc < board_search.CONFIDENT_MATCH

    def test_a_whole_word_still_matches(self):
        assert board_search.score("dots", "Learn dots") == 0.92
        assert board_search.score("learn dots", "Learn dots") == 1.0

    def test_the_full_title_inside_a_longer_query_still_matches(self):
        assert board_search.score("learn dots please", "Learn dots") == 0.92

    def test_a_weak_result_is_reported_as_not_confident(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            db.add(models.BatMission(owner_id=uid, title="Learn dots", status="pending"))
            db.commit()
            out = board_search.search(db, user, "change its time")
            assert out.get("confident") is not True
            if out["matches"]:
                assert "NO CONFIDENT MATCH" in out["note"]
        finally:
            db.close()

    def test_a_real_match_is_reported_as_confident(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            db.add(models.BatMission(owner_id=uid, title="Learn dots", status="pending"))
            db.commit()
            out = board_search.search(db, user, "learn dots")
            assert out["confident"] is True
            assert out["matches"][0]["title"] == "Learn dots"
        finally:
            db.close()


class TestHeCanSeeWhatHeSent:
    def test_a_proactive_message_lands_in_the_history(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            alfred_context.record_outbound(
                db, user, "Your medication reminder has been suspended.",
                origin="reminder", telegram_message_id=4242)
            session = alfred_agent.get_active_session(db, user)
            assert session is not None
            history = alfred_agent.get_history(db, user, session.id)
            # It opens on an assistant message, which is dropped for the
            # model; the row itself is what matters here.
            rows = db.query(models.BatAlfredMessage).filter_by(owner_id=uid).all()
            assert len(rows) == 1
            assert rows[0].role == "assistant"
            assert rows[0].origin == "reminder"
            assert rows[0].telegram_message_id == 4242
            assert history == []
        finally:
            db.close()

    def test_it_is_visible_to_the_model_once_the_user_says_something(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_agent.store_turn(db, user, s.id, "morning", "Good morning.")
            alfred_context.record_outbound(db, user, "Reminder: medication.",
                                           origin="reminder")
            history = alfred_agent.get_history(db, user, s.id)
            assert any("Reminder: medication." in m["content"] for m in history)
        finally:
            db.close()

    def test_a_proactive_message_creates_a_session_when_there_is_none(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            assert alfred_agent.get_active_session(db, user) is None
            alfred_context.record_outbound(db, user, "Morning brief.",
                                           origin="briefing")
            assert alfred_agent.get_active_session(db, user) is not None
        finally:
            db.close()

    def test_recording_never_breaks_delivery(self):
        """A bookkeeping failure must not stop a reminder going out."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            # content is NOT NULL; this is a write that cannot succeed.
            assert alfred_context.record_outbound(
                db, user, None, origin="reminder") is None
        finally:
            db.close()


class TestHistoryStaysSendable:
    """Two assistant messages in a row is an API error, not a style problem."""

    def test_consecutive_assistant_messages_are_merged(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_agent.store_turn(db, user, s.id, "hello", "Good evening.")
            alfred_context.record_outbound(db, user, "Reminder one.", origin="reminder")
            alfred_context.record_outbound(db, user, "Reminder two.", origin="reminder")
            history = alfred_agent.get_history(db, user, s.id)
            roles = [m["role"] for m in history]
            assert roles == ["user", "assistant"], roles
            assert "Reminder one." in history[-1]["content"]
            assert "Reminder two." in history[-1]["content"]
        finally:
            db.close()

    def test_history_never_opens_on_the_assistant(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_context.record_outbound(db, user, "Reminder.", origin="reminder")
            alfred_agent.store_turn(db, user, s.id, "ok", "Noted.")
            history = alfred_agent.get_history(db, user, s.id)
            assert history[0]["role"] == "user"
        finally:
            db.close()

    def test_roles_always_alternate(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            for i in range(3):
                alfred_agent.store_turn(db, user, s.id, f"q{i}", f"a{i}")
                alfred_context.record_outbound(db, user, f"ping{i}", origin="nudge")
            roles = [m["role"] for m in alfred_agent.get_history(db, user, s.id)]
            assert all(a != b for a, b in zip(roles, roles[1:])), roles
            assert roles[0] == "user"
        finally:
            db.close()


class TestHeKnowsWhatYouRepliedTo:
    def test_a_reply_to_a_known_message_resolves(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Take the medicine", recurrence="daily",
                send_time="21:00")
            alfred_context.record_outbound(
                db, user,
                "The daily reminder for your medication has been suspended.",
                origin="reminder", telegram_message_id=777,
                about=("reminder", r.id))

            quoted = alfred_context.resolve_reply(db, user, {"message_id": 777})
            assert quoted is not None
            assert quoted.recognised is True
            assert quoted.about == ("reminder", r.id)
            assert quoted.about_label == "Take the medicine"
            assert quoted.role == "assistant"
        finally:
            db.close()

    def test_the_annotation_names_the_target_and_forbids_searching(self):
        """This is the exact failure: "Change it's time" -> "learn dots"."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Take the medicine", recurrence="daily",
                send_time="21:00")
            alfred_context.record_outbound(
                db, user, "The daily reminder for your medication has been suspended.",
                origin="reminder", telegram_message_id=777,
                about=("reminder", r.id))
            quoted = alfred_context.resolve_reply(db, user, {"message_id": 777})
            annotated = alfred_context.annotate(user, "Change it's time", quoted)

            assert f"reminder id {r.id}" in annotated
            assert "Take the medicine" in annotated
            assert "do not call find_on_board" in annotated
            assert "medication has been suspended" in annotated
            # The user's own words survive intact.
            assert annotated.rstrip().endswith("Change it's time")
        finally:
            db.close()

    def test_an_unrecognised_message_still_quotes_its_text(self):
        """Anything sent before this existed must still be answerable."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            quoted = alfred_context.resolve_reply(db, user, {
                "message_id": 1, "text": "Something from last month",
                "from": {"is_bot": True}})
            assert quoted is not None
            assert quoted.recognised is False
            assert quoted.role == "assistant"
            annotated = alfred_context.annotate(user, "that one", quoted)
            assert "Something from last month" in annotated
            assert "no record of this message" in annotated
        finally:
            db.close()

    def test_a_reply_to_the_users_own_message_is_attributed_to_them(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            quoted = alfred_context.resolve_reply(db, user, {
                "message_id": 2, "text": "buy milk", "from": {"is_bot": False}})
            assert quoted.role == "user"
            assert "They said" in alfred_context.annotate(user, "do it", quoted)
        finally:
            db.close()

    def test_no_reply_means_no_annotation(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            assert alfred_context.resolve_reply(db, user, None) is None
            assert alfred_context.resolve_reply(db, user, {}) is None
            assert alfred_context.annotate(user, "hello", None) is None
        finally:
            db.close()

    def test_a_reply_to_someone_elses_message_does_not_resolve(self):
        """Message ids are per-chat; the lookup must still be owner-scoped."""
        mine, theirs = _mk_user(), _mk_user()
        db = SessionLocal()
        try:
            me = db.get(models.BatAccount, mine)
            them = db.get(models.BatAccount, theirs)
            alfred_context.record_outbound(db, me, "Mine", origin="reminder",
                                           telegram_message_id=555)
            quoted = alfred_context.resolve_reply(db, them, {"message_id": 555})
            assert quoted is None
        finally:
            db.close()

    def test_a_long_quote_is_truncated(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            alfred_context.record_outbound(db, user, "x" * 2000, origin="briefing",
                                           telegram_message_id=909)
            quoted = alfred_context.resolve_reply(db, user, {"message_id": 909})
            assert len(quoted.text) <= alfred_context.MAX_QUOTE_CHARS + 1
        finally:
            db.close()

    def test_the_timestamp_is_in_the_users_own_clock(self):
        uid = _mk_user(timezone="Asia/Tashkent")
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            alfred_context.record_outbound(db, user, "Evening brief.",
                                           origin="briefing", telegram_message_id=31)
            row = db.query(models.BatAlfredMessage).filter_by(
                owner_id=uid, telegram_message_id=31).one()
            row.created_at = datetime(2026, 11, 4, 4, 31, tzinfo=timezone.utc) \
                .replace(tzinfo=None)
            db.commit()
            quoted = alfred_context.resolve_reply(db, user, {"message_id": 31})
            # Tashkent is UTC+5: 04:31Z is 09:31 to them.
            assert "09:31" in alfred_context.annotate(user, "hm", quoted)
        finally:
            db.close()


class TestTheReplyIdIsRecorded:
    def test_alfreds_own_chat_reply_can_be_replied_to(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_agent.store_turn(db, user, s.id, "what's left?",
                                    "Two missions, sir.", user_message_id=10)
            alfred_context.attach_reply_id(db, user, "Two missions, sir.", 11)

            quoted = alfred_context.resolve_reply(db, user, {"message_id": 11})
            assert quoted.text == "Two missions, sir."
            assert quoted.role == "assistant"
            # And a reply to their own earlier message resolves too.
            mine = alfred_context.resolve_reply(db, user, {"message_id": 10})
            assert mine.role == "user" and mine.text == "what's left?"
        finally:
            db.close()

    def test_the_id_is_not_attached_to_an_older_message(self):
        """A short-circuit reply is never stored; the id must not drift."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_agent.store_turn(db, user, s.id, "hi", "Good evening.")
            alfred_context.attach_reply_id(db, user, "Something else entirely", 99)
            assert alfred_context.resolve_reply(db, user, {"message_id": 99}) is None
        finally:
            db.close()


class TestATapIsAnAnswer:
    def test_tapping_done_is_recorded_in_the_conversation(self):
        """The tap answered the reminder and then vanished without trace."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            r = briefing_service.create_reminder(
                db, user, message="Take the medicine", recurrence="daily",
                send_time="21:00")
            alfred_context.record_action(
                db, user, '[Marked done the reminder "Take the medicine"]',
                about=("reminder", r.id))
            row = db.query(models.BatAlfredMessage).filter_by(
                owner_id=uid, origin="button").one()
            assert row.role == "user"
            assert row.about_kind == "reminder" and row.about_id == r.id
        finally:
            db.close()

    def test_alfred_can_see_the_tap_on_his_next_turn(self):
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)
            alfred_context.record_outbound(db, user, "Reminder: medication.",
                                           origin="reminder")
            alfred_context.record_action(db, user, "[Marked done the reminder]")
            history = alfred_agent.get_history(db, user, s.id)
            assert history[-1]["role"] == "user"
            assert "Marked done" in history[-1]["content"]
        finally:
            db.close()


class TestTheGateStillSeesYes:
    def test_confirming_by_replying_still_confirms(self):
        """A near-miss in this change: the gate matches a bare "YES".

        Annotating the turn with reply context would have hidden the word
        inside a block, so confirming a deletion by REPLYING to the question
        would have cancelled it instead. Fail-safe, but wrong.
        """
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            note = models.BatNote(owner_id=uid, title="Shred me", body="x")
            db.add(note)
            db.commit()
            db.refresh(note)
            db.add(models.BatPendingAlfredAction(
                owner_id=uid, action_type="delete_note",
                action_args=f'{{"note_id": {note.id}}}',
                confirmation_message="Delete the note 'Shred me'?",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(minutes=5)))
            db.commit()

            s = alfred_agent.create_session(db, user, "t")
            alfred_agent.set_active_session(db, user, s.id)

            # Exactly what the router builds when YES arrives as a reply.
            quoted = alfred_context.Quoted(
                text="Delete the note 'Shred me'?", role="assistant")
            annotated = alfred_context.annotate(user, "YES", quoted)
            assert annotated != "YES"

            reply = asyncio.new_event_loop().run_until_complete(
                alfred_agent.run_turn(db, user, annotated, session_id=s.id,
                                      store_text="YES"))
            assert "Deleted" in reply, reply
            assert db.get(models.BatNote, note.id) is None
        finally:
            db.close()

    def test_the_annotated_form_alone_would_not_have_confirmed(self):
        """The control: this is what would have reached the gate unfixed."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            quoted = alfred_context.Quoted(text="Delete it?", role="assistant")
            annotated = alfred_context.annotate(user, "YES", quoted)
            assert annotated.strip().lower() not in alfred_agent.CONFIRM_WORDS
        finally:
            db.close()


class TestHisOwnVoiceIsNotAConversation:
    """Recording outbound messages must not quietly change the nudge budget."""

    def test_a_reminder_does_not_count_as_them_talking(self):
        from datetime import timedelta as _td

        from services import nudges

        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            alfred_context.record_outbound(db, user, "Reminder: medication.",
                                           origin="reminder")
            row = db.query(models.BatAlfredMessage).filter_by(owner_id=uid).one()
            now = datetime.now(timezone.utc)
            row.created_at = (now - _td(minutes=5)).replace(tzinfo=None)
            db.commit()
            # may_nudge's "mid-conversation" guard must not see this.
            last = (
                db.query(models.BatAlfredMessage)
                .filter(models.BatAlfredMessage.owner_id == uid,
                        models.BatAlfredMessage.role == "user")
                .first()
            )
            assert last is None
            assert nudges.RECENT_CHAT_QUIET > _td(minutes=5)
        finally:
            db.close()

    def test_but_a_button_tap_does(self):
        """Tapping Done IS them engaging, and should buy quiet."""
        uid = _mk_user()
        db = SessionLocal()
        try:
            user = db.get(models.BatAccount, uid)
            alfred_context.record_action(db, user, "[Marked done the reminder]")
            last = (
                db.query(models.BatAlfredMessage)
                .filter(models.BatAlfredMessage.owner_id == uid,
                        models.BatAlfredMessage.role == "user")
                .first()
            )
            assert last is not None
        finally:
            db.close()

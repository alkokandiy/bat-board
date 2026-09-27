"""Background memory review: a separate pass files what's durable after each exchange.

Runs AFTER the user's reply is already sent (scheduled via BackgroundTasks
by both the Telegram and web paths). Uses the user's own configured
adapter/key — reused via resolve_adapter_for_user, never a new config.

The reviewer sees exactly ONE tool (alfred_remember). Anything else the
model attempts is ignored by construction, not by prompt alone. Most
exchanges correctly produce no write at all.

Failures here never surface: logged, swallowed, conversation unaffected.
"""

import structlog
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from services import alfred_tools

logger = structlog.get_logger()

REVIEWER_SYSTEM = """You are Alfred's private memory clerk. After each conversation exchange you decide whether anything said is worth filing in Alfred's long-term memory notes. You act silently — the user never sees your output, only the notes you file.

File ONLY what the user explicitly stated. Never file a conclusion, guess, or inference drawn from tone or context — if he did not say it outright, it does not go in.

A single passing mention of a minor preference is NOT filed the first time — wait for it to recur or clearly matter. Durable facts ARE filed immediately, even on first mention: identity details, an ongoing project, a relationship, an explicit stated preference, a decision taken.

You are given the current topic index. Check it before writing. If the new information belongs under an existing topic, update that note via alfred_remember using its EXACT existing title (upsert) — never create a near-duplicate under a slightly different title.

One topic per note. Never create a catch-all note mixing unrelated facts.

It is normal and correct for most exchanges to produce NO write at all. Do not force a write just to produce output. An empty result is success, not underperformance.

Never fabricate placeholder or forward-looking content — only what was actually said in this exchange."""

REMEMBER_TOOL = next(t for t in alfred_tools.ALL_TOOLS if t["name"] == "alfred_remember")


async def review_and_remember(
    db: Session,
    user: models.BatAccount,
    user_message: str,
    assistant_reply: str,
) -> None:
    """One background review pass. Never raises — failures are logged only."""
    try:
        await _review(db, user, user_message, assistant_reply)
    except Exception as exc:
        logger.warning(
            "memory_review_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )


async def _review(
    db: Session,
    user: models.BatAccount,
    user_message: str,
    assistant_reply: str,
) -> None:
    from services.alfred_agent import NoProviderConfiguredError, resolve_adapter_for_user

    try:
        adapter = resolve_adapter_for_user(db, user)
    except NoProviderConfiguredError:
        return

    topics = alfred_tools.execute_tool(db, user, "alfred_list_memory_topics", {})
    index_lines = [
        f"- {t['title']}: {t.get('description', '')}"
        for t in topics.get("topics", [])
    ]
    index = "\n".join(index_lines) if index_lines else "(no topics yet)"

    messages = [{
        "role": "user",
        "content": (
            f"User said: {user_message}\n"
            f"Alfred replied: {assistant_reply}\n"
            f"\nKnown memory topics:\n{index}"
        ),
    }]
    response = await adapter.generate(messages, [REMEMBER_TOOL], REVIEWER_SYSTEM)

    for call in response.tool_calls or []:
        if call.name != "alfred_remember":
            logger.warning("memory_review_off_scope", tool=call.name)
            continue
        alfred_tools.execute_tool(db, user, "alfred_remember", call.arguments or {})


def schedule_memory_review(background_tasks, user_id: int, user_message: str, assistant_reply: str) -> None:
    """Append the review pass to run after the reply is sent. Returns instantly.

    Opens its own DB session inside the task — never shares the request's.
    """
    from database import SessionLocal

    async def _run() -> None:
        db = SessionLocal()
        try:
            user = db.query(models.BatAccount).filter_by(id=user_id).first()
            if user is None:
                return
            await review_and_remember(db, user, user_message, assistant_reply)
        finally:
            db.close()

    background_tasks.add_task(_run)

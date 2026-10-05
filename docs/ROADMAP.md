# Alfred / bat-board roadmap

Source: the owner's plan, recovered 2026-10-05. Phases are built in order.

| Phase | Scope | Status |
|---|---|---|
| 2A / 2B, Batches A–C | Telegram link + webhook, Alfred tool-calling, multi-provider, BYOK, self-managed memory | Done |
| Audit + multi-user (PRs #2, #3) | Security/points fixes, per-user timezone & form of address, chat list, Reset Alfred | Done |
| Phase 2 | Focus session `mode` column + "by mode" stats | Done (migration 013) |
| Phase 3 (Batch D) | Telegram voice messages | Planned |
| Phase 4 (Batch E) | Images: understanding (A), then generation (B) | Planned |
| Phase 5 (Batch F) | Daily morning / night briefings | Planned |

## Adjustments to the plan (as of 2026-10-05)

The plan predates the audit and multi-user work. Where it conflicts with the
current code, these apply:

- **Capability flags already exist** in `services/llm_providers/capabilities.py`:
  `supports_audio_input`, `supports_vision_input`, `supports_image_generation`
  (the plan calls them `audio` / `vision` / `image_generation`). Reuse them; the
  plan's "re-verify against current provider docs" still applies to each value.
- **Workers:** production runs 1 gunicorn worker (`WEB_CONCURRENCY`, default 1),
  not 4. The plan's multi-worker-safe designs (DB-backed counters, unique
  constraints, a cron endpoint instead of an in-process scheduler) stay
  required — they're correct at any worker count and allow scaling later.
- **Timezone (Phase 5):** each account already has an IANA `timezone`
  (`bat_account.timezone`, set in Profile). Briefings must use it instead of a
  separate per-briefing timezone defaulting to Asia/Tashkent.
- **Form of address:** briefings and voice/image replies address the user by
  `bat_account.alfred_address` (fallback: username), never a hard-coded name.
- **Migrations:** next free revision is `014` (`013` = focus `mode`).
- **Failed turns:** transcripts / image placeholders that fail to process are
  kept out of the model's context like other failed turns (`FAILED_TURN_REPLIES`
  in `alfred_agent.py`).

---

## PHASE 2: bat_focus session mode column

Focus timer has 4 visual modes: Normal, Flip Clock, Bat-Signal, Batmobile.
Sessions currently don't record which was used.

- Add nullable column `mode` (short string: "normal" | "flip" | "signal" |
  "batmobile") to the bat_focus table via a new migration. Nullable so
  existing rows stay valid.
- Backend: accept optional `mode` on session start (POST /api/focus/sessions),
  validate against the allowed set (reject unknown values with 422),
  return it in session responses.
- Frontend (BatFocusTimer.jsx): send the currently selected mode when
  starting a session. If the user switches mode mid-session, record the mode
  at start only (keep it simple) and note that in the report.
- Stats: add a "by mode" breakdown to the focus stats endpoint and a small
  section in StatsPanel Overview (minutes per mode, reuse the existing
  breakdown component/style). Old sessions with null mode show as "Unknown".
- Tests: migration applies, validation rejects bad mode, stats grouping
  handles nulls.

---

## PHASE 3 (Batch D): Voice messages via Telegram

Goal: user sends a Telegram voice note, Alfred understands it and answers as
if it were text.

Design constraints:
- Telegram voice messages arrive as OGG/Opus. Flow: webhook update contains
  message.voice (file_id, duration) → Bot API getFile → download from the
  file endpoint using the bot token → transcribe → feed the transcript into
  the normal Alfred text pipeline.
- Reuse the existing webhook rules: return 200 immediately, do the work in
  BackgroundTasks, dedupe via BatTelegramSeenUpdate.
- Transcription goes through the provider abstraction, not a hardcoded
  vendor. Add an `audio` capability flag to ProviderCapabilities (default
  False, all-False fallback for unknown pairs stays). Set True only for
  providers/models that genuinely support audio input; check current
  provider docs rather than assuming. For a user whose configured provider
  lacks audio, reply with a clear message saying their current provider
  doesn't support voice and what to do (e.g. /setkey with a supporting
  provider). Don't silently fail and don't silently switch providers.
- Guards: cap duration (e.g. 120s, configurable constant), cap file size,
  reject non-voice audio gracefully, handle download failure and empty
  transcript with a friendly message.
- Show the transcript back to the user first ("🎙 I heard: ...") so wrong
  transcriptions are visible, then process it as a normal message.
  Mention in the transcript echo only; don't store audio bytes anywhere.
  Store only the transcript text in the Alfred message history.
- Same destructive-action rules apply: a transcribed "delete everything"
  still goes through the existing 2-minute confirmation gate. Add a test
  proving voice input cannot bypass it.
- Tests: mock Telegram getFile/download and the provider; cover happy path,
  too-long voice, unsupported provider, download error, duplicate update id.

---

## PHASE 4 (Batch E): Image understanding, then generation

Part A, understanding (build first):
- Telegram photo messages (message.photo, take the largest size; also handle
  image documents) with optional caption. Download via getFile, pass to the
  provider as image input when capabilities.vision is True (already True for
  Gemini, Anthropic claude-sonnet-5, and OpenAI gpt-5.6 in the registry;
  re-verify in code). If vision is False, reply clearly instead of dropping
  the image.
- Size guards, MIME validation, no image bytes persisted: store only a text
  placeholder like "[image: <caption or 'no caption'>]" plus Alfred's reply
  in message history.
- Treat any text inside an image as untrusted data, not as instructions to
  Alfred. Add a short note to the system prompt for this and a test with an
  image-borne "ignore previous instructions" style payload at the prompt-
  construction level (mock provider, assert the content is passed as data).

Part B, generation (only after A is committed):
- Add an `image_generation` capability flag (default False). Implement
  only for a provider/model where it is genuinely supported; verify against
  current docs. Expose it to Alfred as a tool (generate_image(prompt)),
  send the result back via Telegram sendPhoto. Rate-limit per user (DB-
  backed counter, since there are 4 workers) because generation costs
  money on the user's own BYOK key. If no configured provider supports it,
  Alfred says so plainly.
- Report honestly if generation can't be verified without a live key.

---

## PHASE 5 (Batch F): Daily morning and night briefings

Goal: Alfred proactively messages the user on Telegram twice a day.

Design constraints:
- Opt-in per user. Commands: /briefing on, /briefing off,
  /briefing morning HH:MM, /briefing night HH:MM. Defaults: morning 06:00,
  night 21:30, user timezone default Asia/Tashkent, stored per user
  (new table or columns via migration, e.g. BatBriefingSettings: owner_id
  UNIQUE, enabled, morning_time, night_time, timezone).
- Scheduling with 4 workers: do NOT use an in-process scheduler that every
  worker would run. Use ONE of: (a) a protected endpoint
  POST /api/internal/briefings/tick guarded by a BRIEFING_CRON_SECRET header
  (compare with secrets.compare_digest), called every minute or every few
  minutes by a Railway cron service or external pinger; or (b) a single
  scheduler guarded by a Postgres advisory lock. Prefer (a).
- Exactly-once: new table BatBriefingLog (owner_id, kind
  'morning'|'night', local_date) with a UNIQUE constraint. The tick inserts
  first; if the insert conflicts, skip. This makes double-ticks and
  multi-worker overlap harmless. Window logic: fire if now >= scheduled time
  and today's log row doesn't exist, but not if it's more than ~3 hours late
  (don't send a stale morning brief at noon).
- Morning content: missions due today and overdue, habits for today with
  streak status, upcoming countdowns/calendar items within 48h, yesterday's
  focus minutes. Night content: what got completed today, what's still open,
  habits missed, total focus time, and 1-3 items carried to tomorrow.
  Generate the text through the user's configured provider using real DB
  data passed in as context, and instruct the model to use only the
  provided data and invent nothing. If the provider call fails, fall back to
  a plain templated summary built straight from the data so a briefing is
  never silently skipped.
- Needs a linked Telegram chat; users without a linked chat are skipped
  without error.
- Tests: fires once at the right time, never twice on repeated ticks,
  respects timezone, skips disabled users, skips too-late windows, falls back
  to the template on provider failure, rejects missing/wrong cron secret.
- Document the Railway cron setup in the README as exact steps for me to do
  by hand, and mark clearly that I need to perform them.

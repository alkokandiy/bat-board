# Making bat-board and Alfred actually work

Source: *The Engineering of Human Behavior: AI-Native Habit Formation* (owner's
research, Nov 2026), read against the running code on 2026-11-03.

Two problems the owner reported, both reproduced in the code:

1. **"I forget to log time and timers. I was just working."**
   Every minute on the board requires remembering to start a timer *before*
   the work, or remembering afterwards to tell Alfred. Both are acts of
   memory, and memory is the thing that failed. The board therefore reads
   zero for a month of real work.

2. **"All reminders were just noise. I skipped them all and Alfred kept
   sending them tirelessly."**
   `BatReminder` has **no outcome field of any kind**. `BatReminderLog`
   records `sent_at` and nothing else. `briefings.render_reminder` returns
   plain text with no buttons. `scheduler._fire_reminders` fires on schedule
   forever. The fatigue, cooldown and unanswered-run limits that exist in
   `services/nudges.py` are not used by reminders at all.
   There is no channel through which thirty ignored reminders can change
   anything.

The research explains why (2) got worse rather than better: a cue that fires
and is never followed by reward closure produces a **negative reward
prediction error**, and the striatum extinguishes the association. Firing the
same cue again, harder, is the one intervention guaranteed to accelerate that.

---

## What of the research applies here, and what does not

Being honest about this up front, because chasing the inapplicable parts would
cost months and deliver nothing.

**Does not apply to bat-board as it exists.** The blueprint describes a
different product: Flutter client, WatermelonDB, HealthKit/WearOS biometrics,
geofencing, ambient noise, OS-level app blocking, Kafka, Redis, LangGraph.
bat-board is a FastAPI + React web app with a Telegram bot. It has no device,
no sensors, no background process on the user's phone. **No HRV, no sleep
debt, no motion state, no location** — and no readiness score built on them.

**But "no biometrics" is not "no context", and reading it that way was lazy.**
The database already holds timestamped evidence of the person: every message
they send Alfred, every focus session, work note and habit check-in. That
gives an *observed active window* — when there is evidence of them, and how
much of it the board can account for (`services/activity.py`). It is the
paper's context-normalisation node built from what this product can honestly
see, and it is enough to notice a day someone clearly spent working with
nothing recorded.

The hard rule on it: absence of evidence is **not** evidence. A quiet stretch
means the app saw nothing, never that the person was resting, idle or
unwell. No mood, no energy, no readiness inferred from silence.

**Does apply, and is the valuable part.** The behavioural mechanisms do not
need sensors. The system already holds the only context that matters for this
user: their calendar, their work hours, their check-in history, their
adherence, and what they tell Alfred.

| Mechanism from the paper | Already here | Gap |
|---|---|---|
| Cue / craving / response / reward loop | `habit.cue` exists | nothing closes the reward |
| Task-bracketing (start + finish matter, middle does not) | — | the whole design assumes the middle |
| Reward prediction error, extinction | **done** (phases 0–1) | — |
| Friction tuning | **done** (phase 2) | — |
| Adaptive downscaling to a micro-habit | — | missing entirely |
| Motivational-Interviewing response to a miss | partly, in `alfred_principles` | never triggered by a miss |
| Habit stacking | `cue` is free text | not anchored to anything real |
| Consistency index over raw streak | **done** — `recent_adherence` | — |
| Grace periods | — | missing |
| Calendar-anchored execution | events exist | habits are not on the calendar |

---

## Phases

Ordered by how much of the owner's actual pain each removes, not by how
interesting it is to build.

### Phase 0 — Make a miss visible (the precondition for everything)

Nothing else is possible while the system cannot tell "done" from "ignored".

- `BatReminderLog` gains an outcome: `sent` → `done` | `skipped` | `snoozed` |
  (nothing = ignored). Additive, nullable, no migration risk.
- Reminders go out with **inline buttons**: *Done* · *Not today* · *Stop
  this*. One tap, from the notification, no app.
- `/api/internal/cron/tick` is unchanged; only the payload and the callback
  handler grow.
- Alfred gains `reminder_history` so he can see what was acted on.

Deliverable: the system can finally observe the difference between a working
reminder and a dead one.

### Phase 1 — Stop firing into the void

With outcomes recorded, apply what `nudges.py` already knows:

- **N consecutive ignores → stop and ask.** After 3 unanswered, the reminder
  suspends itself and Alfred opens a conversation instead: *"The 9pm medicine
  reminder has gone unanswered eleven times. That is the reminder failing,
  not you. Is the time wrong, or is a reminder the wrong tool here?"*
  Motivational Interviewing, as the paper specifies: data, not blame, then a
  collaborative revision.
- **Never two notifications in the same breath.** Reminders join the global
  cooldown that nudges already respect.
- A reminder that is consistently *done* keeps firing untouched. The
  adaptation is one-directional: noise shrinks, signal does not.

Deliverable: the medicine reminder either gets fixed or gets retired. It does
not keep ringing for a month.

### Phase 2 — Capture time without remembering to

The timer stops being the source of truth and becomes one optional input.

- **Day-end reconstruction.** The night brief asks one question: *"What did
  you actually work on today?"* Free text → Alfred lays out blocks across the
  day and shows them for one confirmation. Typing one sentence replaces
  twelve remembered timer starts.
- **Proposed blocks from the work profile.** For an account with work hours
  set, Alfred can propose the default working day and ask only what differed.
  Confirmation is far cheaper than recall.
- **One-tap duration on the thing itself.** A mission row gets `+15m`
  `+30m` `+1h`, writing a backfilled block without a modal or a timer.
- **Implicit start.** Telling Alfred "starting on the pricelist now" starts a
  session. He already has the tools; nothing instructs him to.

Deliverable: a day's work can be recorded in one sentence, after the fact.

### Phase 3 — Downscale instead of breaking

The paper's central insight for adherence: preserve the bracket, shrink the
load.

- Each habit gains a `minimum_viable` form — the two-minute version, named by
  the user ("put the shoes on", "one page").
- When recent adherence falls below a threshold, Alfred offers the micro
  version rather than the full one. The streak is kept by doing the small
  thing, because the striatal circuit does not care about the size.
- **Grace periods**, as in the paper's schema: a miss inside an allowance
  does not reset the run, and the allowance is visible and finite.

### Phase 4 — Anchor habits to real time

- A habit can be placed on the calendar as a block, not just a free-text cue.
- Conflicts are surfaced: six habits all cued "after work" is a plan that
  cannot physically happen, and saying so beats watching it fail.
- Habit stacking: the cue can reference a *completed* habit or event, so
  the anchor is something the system can actually observe.

### Phase 5 — Alfred reads the record

Everything above produces data Alfred currently cannot see. This phase is
about him using it: naming the pattern ("you have never once done this on a
Tuesday"), proposing the revision, and holding the contract.

---

## Rules carried into all of it

- Nothing here invents a context stream the product does not have. No
  biometrics, no location, no inferred mood.
- Nothing added without an off switch; reminders and nudges must be
  retirable in one tap.
- Adaptation only ever reduces noise. It never silently increases demands.
- `alfred_principles.py` stays the single source for how Alfred speaks, and
  `reports/Human behaviour science for Alfred.md` for what he believes. New
  numbers need a source.

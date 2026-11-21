# bat-board — the plan

**One document, one numbering.** Every phase this project has had lives
here, 0 to 36, with its status. The reasoning behind phases 0–7 is in
`BEHAVIOUR_PLAN.md`; the reasoning behind 8–25 is below.

Absorbed `ROADMAP.md` on 2026-11-15. That file carried a *second* phase
numbering for the Alfred work (its own "Phase 2–5"), which meant "Phase 4"
could mean image understanding or drag-to-reschedule depending on which
document you had open. Its content is at the end of this file under
*Before phase 0*.

## Status

| Phase | What | Status |
|---|---|---|
| — | Telegram, Alfred tool-calling, multi-provider, BYOK, memory, voice, images, briefings, reminders | done — see *Before phase 0* |
| 0 | Make a miss visible | done |
| 1 | Stop firing into the void | done |
| 2 | Capture time without remembering to | done |
| 3 | Downscale instead of breaking | done |
| 4 | Anchor habits to real time | done |
| 5 | Alfred reads the record | done |
| 6 | Alfred knows what he said | done |
| 7 | "X times per week", and rest as a state | done |
| 8 | Lists | done (2026-11-13) |
| 9 | Sections inside a list | done (2026-11-14) |
| 10–13 | Tags, saved filters, smart lists, calendar subscription | **dropped by the owner, 2026-11-15** |
| 13b | The seven calendar views | done (2026-11-13) |
| 14 | Drag to reschedule | done (2026-11-15) |
| 15 | Multiple reminders per mission | done (2026-11-16) |
| 16–18 | Completion rate headline, focus presets, habit archiving | **dropped by the owner, 2026-11-15** |
| 19 | Per-mission activity | **dropped by the owner, 2026-11-20** |
| 20 | Attachments, starting with receipts | open — unblocked 2026-11-20 |
| 21 | Themes | open |
| 22 | Overtime — the clock does not stop at zero | done (2026-11-13) |
| 23 | The focus timeline strip | done (2026-11-20) |
| 24 | Quantified habit goals | open |
| 25 | A habit detail panel | done (2026-11-20) |
| 26 | The ledger | done (2026-11-20) |
| 27 | Alfred can log it, and what he is allowed to say | open |
| 28 | Bringing the history in, and getting it out | open |
| 29 | Budgets, and the month that starts on payday | open |
| 30 | The predictable half, posted for you | open |
| 31 | Where the money went | open |
| 32 | What the next months look like | open |
| 33 | Things you are saving for | open |
| 34 | Cards, loans, and what you actually owe | open |
| 35 | Before you commit to it | open |
| 36 | Alfred's financial register | open |

**17 done, 13 open, 8 dropped.**

---

What to build after the behaviour work, in the order worth building it.

Written 2026-11-13, from the owner's TickTick screenshots plus
`reports/TickTick mechanics for bat-board.md` (the habits, focus, reminder
and gamification research done 2026-11-04). The screenshots show the half
that report did not cover: **structure and surface** — the sidebar, lists,
filters, settings, integrations.

---

## The honest starting point

Most of what the screenshots show, bat-board already has — and TickTick
charges for several of them.

| TickTick module | bat-board |
|---|---|
| Habit Tracker | yes, with schedules, rest days, micro-versions, adherence |
| Pomodoro | yes — Focus, with its own median rather than a stock 25 |
| Eisenhower Matrix | yes |
| Calendar | yes, now with a day view |
| Countdown | yes |
| AI | **Alfred** — and a conversational agent over Telegram is a different
  class of thing from a text-completion box |

What bat-board has that TickTick does not: a work track that earns no
points and switches off whole, an assistant that notices a reminder being
ignored, a habit reward that is not a streak, and a rest day.

So this is not a catch-up list. There is exactly **one structural hole**,
and it is wide.

---

## The hole: there is no way to group a mission

A mission has a title, a date, a priority, a free-text `tags` string — and
nothing else. No list, no project, no section. The board is **one flat pile
of 44**, and no amount of sorting or filtering fixes that, because sorting
reorders a pile and filtering hides part of it.

TickTick's entire left rail is the answer to this: **Lists → Sections →
Tags → Filters → Smart Lists.** Five mechanisms, and bat-board had a weak
version of one.

Two of the five were built — lists and sections — and that closed the
hole: the board is no longer one flat pile. The owner dropped the other
three on 2026-11-15, which is a reasonable place to stop. Grouping is what
a pile needed; a second and third way to slice the same missions is what
an app builds when it has run out of problems.

Everything in Part 1 below is that hole. It is also what the owner has been
reporting for days without naming it — "31 with no date", "this look is
none of it and it sucks", 44 rows of equal weight.

---

## Part 1 — Structure (the spine)

### Phase 8 · Lists — **done** (2026-11-13)
A mission belongs to a list: Khorasan, Cybersecurity, Health, Admin. The
sidebar shows them with counts; the missions screen filters to one.

Migration adds `bat_lists` (name, colour, icon, position, archived) and a
nullable `list_id` on `bat_missions`. Nullable because every existing
mission has no list and must keep working — they appear in an **Inbox**
that is "no list yet", not a list of its own.

Alfred gets `list` on create and update, and learns to ask which list a new
mission belongs to when it is obvious he should.

*Why first: nothing else in this document means much while the board is one
pile. A filter over a flat list is still a flat list.*

### Phase 9 · Sections inside a list — **done** (2026-11-14)
The `Getting Started / Feature Modules / Explore More` grouping in the
screenshot. Named by the user, not fixed — TickTick's habit sections are
hard-coded Morning/Afternoon/Evening and that is the wrong call.

`bat_sections` (list_id, name, position) and a nullable `section_id`.

### Phases 10–13 · Dropped by the owner (2026-11-15)

Tags promoted out of the comma-separated string, saved filters,
configurable smart lists, and subscribing to a real calendar. All four
were planned, none are wanted.

Recorded rather than deleted so they are not proposed again as if they
were an oversight. They were considered and declined; the board already
groups by list and section, which was the part that mattered.

---

## Part 2 — The calendar is half a product

### Phase 13b · The seven calendar views *(done, 2026-11-13)*

From the owner's second and third batches of screenshots. The useful
finding was that TickTick's seven views are **three shapes**, not seven
features:

| shape | views |
|---|---|
| hours × N days | Day, Multi-Day (3), Week |
| day cells | 2 weeks, 3 weeks, Month |
| a list of what exists | Agenda |
| twelve mini grids | Year |

So bat-board has one `TimelineView` taking a list of days, one grid whose
day list changes, `AgendaView`, and `YearView`. Writing seven components
would have been seven places for the same off-by-one.

Decisions worth keeping:

- **Navigation moves by the unit the view is made of** — a month in the
  grid, a fortnight in 2 weeks, a day in Day, a year in Year. Stepping a
  month while looking at three days is a different screen, not the next.
- **One anchor date** drives every view. Month owning `year`/`month` while
  the others each kept a date would be two sources of truth for "where am
  I looking".
- **The heading names what is on screen** — `9–15 Nov`, `Next 30 days`,
  `2026` — never always a month.
- **The year heatmap takes two numbers, not one.** `minutes` is effort and
  `done` is output (missions completed plus habits kept). A day of three
  hours with nothing finished is a real day and so is the reverse; one
  blended number hides both, and the tooltip reports them apart.
- **Four bands, not a gradient.** A continuous scale invites comparing two
  days that differ by four minutes.
- Agenda **leaves empty days out**. An agenda of empty days is the thing
  it exists not to be.

`GET /api/stats/year?year=` returns the heatmap sparsely — only days with
something in them — and is fetched only while the year is on screen.

### Phase 14 · Drag to reschedule — **done** (2026-11-15)
In the month grid and the day view. The day view already has the hour rows;
rescheduling a mission is currently a date picker, which is correct but
slow for the one operation a calendar exists to make fast.

Two rules live on the server, so a drag and Alfred cannot disagree about
what a move means. **An event keeps its length** — the end moves by the
same delta, because a drag means "later", not "shorter", and setting the
start alone would silently shorten a meeting or be refused for ending
before it begins. **A mission keeps its time of day** and only its date
text is replaced, with no timezone conversion: converting on the way in
and slicing on the way out is how a mission dropped on Friday lands on
Thursday.

The date picker and the edit dialog stay. Drag works with neither a
keyboard nor a touchscreen, so it can never be the only way to move
something.

---

## Part 3 — Things that are due

Carried from the TickTick report, still unbuilt, ordered by value:

### Phase 15 · Multiple reminders per mission — **done** (2026-11-16)
"1 day ahead, and again on the day."

The premise as written here was wrong, and worth correcting rather than
deleting: a reminder could already point at a mission — `mission_id` has
been on `bat_reminders` for ages. What it could not do was take its *date*
from that mission. It fired at a clock time the user typed, so the link was
decorative, and Phase 14 turned that into a defect you could cause with a
flick of the wrist: drag a mission to next week and its warning still went
off on the old day, about work that was no longer due.

So reminders gain the recurrence `relative`: `offset_days` of notice, at
the reminder's own `send_time`, with the date read off the mission on every
tick. Nothing about the date is stored, so there is nothing to go stale —
reschedule the mission and every warning on it moves, with no second write
to get wrong. "A day ahead and again on the day" is two rows, offset 1 and
offset 0, which is what `mission_id` always allowed and nothing used.

Days rather than minutes on purpose. Counting back from the due *moment*
sounds more precise and is worse where it matters: a mission due Friday
23:59 with a day's notice would ring on Thursday at 23:59. The cost is
that "30 minutes before this meeting" is not expressible — timed warnings
belong to calendar events, not missions.

Two things it deliberately does not do. A warning is never sent about a
mission that is completed, dismissed, or has no due date, because a
notification about finished work is how someone learns to ignore the rest
of them. And a *fixed-time* reminder pointing at a mission still does not
move: "08:00 daily" means 08:00, whatever the mission does.

Reminders have no web API — they are created through Alfred over Telegram
and nothing in `frontend/` mentions them. This phase therefore lands in
`services/scheduler.py`, `services/briefing_service.py` and Alfred's
tools, with no UI. A reminders panel in the web app would be a separate
piece of work, and a larger one than this was.

### Phases 16–18 · Dropped by the owner (2026-11-15)

Completion rate as the headline number, named focus presets, and habit
archiving with streaks derived from the log.

Recorded rather than deleted so they are not proposed again as if they
were an oversight.

One of the three is worth a note for whoever reads this next. Phase 18
carried a real correctness point inside a feature nobody asked for:
streaks are a stored counter, and a stored counter drifts across
backfills and devices. If a streak is ever seen to be wrong, that is the
cause, and deriving it from the check-in log is the fix — as a bug fix,
not as this phase.

---

## Part 4 — Surface, last

### Phase 19 · Per-mission activity
bat-board already writes `BatLog` for everything. Surface it on the mission:
created, rescheduled four times, 2h40m focused. "Postponed six times" is a
fact about a mission worth seeing.

### Phase 20 · Attachments
Alfred already handles images over Telegram; missions cannot hold one.

### Phase 21 · Themes
Cheap, last, and only once the tokens have settled. The palette was unified
on 2026-11-04; a theme is now a swap of `:root` values rather than a hunt.

---

## Part 5 — The focus window and the habit dialog

From the owner's fourth batch (2026-11-13): TickTick's Pomodoro screen,
its focus records, and the whole Create Habit dialog.

### The one that matters: the clock does not stop at zero

TickTick's timer **keeps counting past the bell**, upward, showing
`+09:49`, with "Click to add to focus duration". bat-board ends the
session the instant the countdown reaches zero:

```js
if (focusRunning && focusTimeLeft === 0) { setFocusRunning(false); endFocusSession(); }
```

So every minute worked after the ding is **lost entirely** — and those
are exactly the minutes of the owner's original problem (a), "I was just
working and forgot to log it". A timer that stops recording while the
work continues is the capture problem wearing a friendlier face.

**Phase 22 · Overtime — done (2026-11-13).** At zero the session stays open and the clock
counts up. Finishing credits the planned time; one tap credits planned +
overtime. Never silently: the extra time is offered, not assumed, because
a timer left running on a closed laptop would otherwise invent hours.

### Phase 23 · The focus timeline strip — **done** (2026-11-20)
The right-hand panel draws the day as blocks against a 24-hour scale, with
a line at now. This is recommendation 3 of the TickTick report and the
passive half of the capture fix: unlogged time shows as a visible hole,
which invites backfill without a nag.

`GET /api/focus/day` returns each block already placed on a 0–1440 scale.
The placement is the server's job, not the browser's: these columns are
naive UTC and the day is the user's own, so which date a 23:30 block
belongs to depends on who is looking.

Three decisions the tests pin down. A block crossing midnight appears on
**both** days as the part that happened on each, while `minutes` stays the
whole session, so the bar and the number never quietly disagree. An
unfinished session is drawn up to now but **no further than
`STALE_FOCUS_HOURS`** from its start — the scheduler already closes a
session left open that long as abandoned, and without the cap a tab closed
last week painted itself across every day since. And **work time is named**
rather than dropped into "unassigned": the work track earns no points and
nothing here touches points, but an unlabelled block is exactly the hole
this strip exists to make visible.

The strip sits full width below the timer rather than in the right-hand
column — twenty-four hours squeezed into a third of the page is unreadable.

### Phase 24 · Quantified habit goals

The Create Habit dialog's "Reach a certain amount": `5 Pages/Day`, a
unit, a step, and **When checking: Auto / Manual / Complete all**. The
habit detail panel then shows monthly completion in that unit and a
daily-goals chart.

Worth having, and the report already specified the model (`goal`, `step`,
`unit`, boolean or numeric). Note that bat-board's `minimum_viable` is
the better half of the same idea — shrinking the goal beats tracking
fractions of it — so quantities are an addition, not a replacement.

### Phase 25 · A habit detail panel — **done** (2026-11-20)
Monthly check-ins, total, check-in rate, current streak and a month
calendar. bat-board held all of this already and showed almost none of it:
a habit row had a number and a bar over a log going back to the day it
started.

`GET /api/habits/{id}/history?month=YYYY-MM` returns the month day by day
in **five** states, and the distinctions are the substance:

- `rested` is **not** `missed`. A planned rest leaves the denominator
  rather than entering it as a miss, so resting cannot lower the rate —
  there is a test that says exactly that. A calendar drawing the two the
  same would re-tell the person the one thing the rest day exists to stop
  saying.
- `not_due` is not a miss either. A weekly habit is not failing on the
  other six days.
- `upcoming` is not a miss. Opening November on the 20th must not paint
  the rest of the month red.
- `check_in_rate` is **null, never 0**, when nothing has been due yet. 0%
  is a verdict, and a habit that has not been asked for anything has not
  failed.

`HabitCompletionLog` has no owner of its own — it hangs off the habit — so
the habit is resolved against the owner first and every row read through
that. Check-ins are bucketed into the user's local day, the same way the
check-in was recorded.

### Smaller, worth taking

- **A focus note** on the session — "what do you have in mind?" — which
  is also the obvious place to ask what the unlogged time was.
- **Icon or emoji per habit**, and per list when lists arrive. Cheap,
  and a board of twenty identical rows is harder to scan than it needs
  to be.
- **Habit sections**, same mechanism as mission sections (Phase 9).
- **A start date** on a habit, so adherence does not count days before
  it existed.

### Refused, from this batch

- **"Goal Days: 21 days"** in the dropdown. AGENTS.md rule 4 bans the
  21-day habit myth outright, and shipping it as a preset would teach it.
  A horizon is fine — 7, 30, 100, custom — but not that number.
- **Pomo count as a headline.** "Today's Pomo: 1" counts bells, not work.
  bat-board already leads with minutes and should keep doing so; a count
  of completed timers rewards starting them, which is the behaviour that
  produced a 25-session total against 8 hours.
- **A badge for the goal-days streak.** Same objection as the 3/7/21
  ladder already refused.

---

## What not to copy, and why

- **Premium gating.** Half the screenshots are an upsell. There is one user
  per deployment and nothing to upsell.
- **Sharing, members, assignees.** bat-board is a personal life OS. Every
  query is scoped by `owner_id` and should stay that way.
- **Zapier / IFTTT / Slack.** Alfred over Telegram already is the
  integration surface, and a conversational one is better than a webhook.
- **Leaderboards and social comparison.** Already refused in the TickTick
  report, for reasons the evidence supports.
- **The 3/7/21 badge ladder.** Embeds the 21-day myth this codebase bans
  (AGENTS.md rule 4).
- **Constant Reminder / DND bypass.** Escalation is precisely what produced
  the ignored-medicine month.
- **A general AI chat box.** Alfred is not a chat box and should not be
  flattened into one.

## One worth stealing that is not in the screenshots' spirit

**An MCP server for bat-board.** TickTick ships one, and the owner works in
Claude Code every day. A small MCP over the existing services would let an
assistant read and write the board directly from the editor — the same
tools Alfred already has, exposed on a second surface. Cheap, because
`services/alfred_tools.py` is already the tool layer; it would need an auth
story of its own.

---

## How to build it

One phase at a time, each shippable on its own, in the order above unless
something urgent cuts in. Every phase: additive migration, tests that fail
before the change, mutation-check the ones that matter, merge to `main`
and watch it deploy.

Phases 8 and 9 are the spine and were built in that order, because
sections need lists to live in. 10–13 were the rest of that plan and the
owner dropped them; the spine stops at sections.

---

## 19 and 20, revisited 2026-11-20

**19 — Per-mission activity: dropped.** The owner read it back and did not
want it. He is right: a per-mission audit log is written constantly and read
almost never, and "what happened to this mission" is already answerable from
the mission itself, the logs feed and Alfred's memory. Not an oversight — a
decision, and not to be re-proposed.

**20 — Attachments: unblocked, and re-scoped to receipts first.**

The old note said Railway's filesystem is ephemeral, so there was nowhere to
put a file. That conflated two things: the container's own disk is ephemeral,
but a **mounted Railway volume is not**, and the project already runs one —
`postgres-volume`, attached to the database service. Volumes mount to any
service and survive deploys. Hobby allows 5 GB and ten volumes per project,
resizable live, at roughly $0.15/GB/month against $5 of included usage. At
~200 KB a photo that is tens of thousands of receipts, so storage is not the
constraint it was assumed to be.

Two constraints that are real, and belong in the phase rather than in a
footnote:

- **A volume pins its service to one replica.** Nothing today needs more, and
  the scheduler's multi-worker safety is unaffected — but scaling out later
  means moving to object storage, so the upload path should go through one
  service function rather than being scattered, to keep that a swap.
- **Backups are the open question.** Postgres gets Railway's backups; a file
  volume is a separate story and must be confirmed BEFORE it holds the only
  copy of anything. A receipt the user cannot get back is worse than no
  attachment feature.

**Receipts first, because finance gave this a reason to exist.** The app this
project is replacing puts a camera on its expense form. A photo of the receipt
attached to the transaction is the use with real pull; attachments on missions
and notes follow the same machinery once it works.

---

# The finance track — phases 26 to 36

Added 2026-11-20 on the owner's brief: log income and outgoings with mechanics
matching **Money Manager** (Realbyte), let Alfred see the picture, and let him do
the planning arithmetic — a car, a wedding, "what can we do with what we have".

The research is `reports/Personal finance mechanics for bat-board.md`, and it is
the source of truth the way the behaviour report is for habits. Read it before
starting any phase here. Four things in it are not negotiable later, because they
are baked into the stored rows: **money is an integer of minor units, never a
float**; **one resolver owns the posting invariant**; **the exchange rate lives
on the transaction**; **the period start day is a setting, not the 1st**.

Two new project rules come with this track, and belong in `AGENTS.md` when
phase 26 lands:

- **Money earns no Bat Points.** The same boundary as the work track, for a
  sharper reason — paying for logging rewards logging over accuracy, and paying
  for spending gamifies money. Points are written in exactly three services
  (mission, habit, focus). Finance must not become a fourth, and a test asserts
  it.
- **Finance is switchable off, and off means off.** `finance_enabled` copies
  `work_enabled` exactly: tri-state, NULL resolving to "on if they already have
  finance data", destroying nothing when switched off.

---

## 26 — The ledger ✅ done 2026-11-20

The foundation, and the only phase that is hard to change afterwards.

Shipped with one refusal worth recording: **a transfer between two different
currencies is rejected rather than booked.** One row carries one amount, so the
sum that leaves is not the sum that arrives, and guessing would invent money at
the far end. It needs a second amount and its own rate — a change to the row,
not a patch to the check. Everything else in this phase is as described below.

**Accounts** with a group (cash, bank, card, savings, investment, loan,
insurance, other), each with its own currency and an opening balance.
**Categories** in two separate trees, income and expense, with parent/child and
a shipped preset set that is fully editable. **Transactions** of exactly three
types — income, expense, transfer — each one *moving money between accounts*,
which is what makes a transfer not an expense and a credit-card payment not a
purchase.

Balances are derived by summing signed effects, never stored as a column that
can drift out of agreement with the rows that produced it.

`finance_service.resolve_posting` is the single home of the invariant, in the
spirit of `mission_service.resolve_placement`: expense wants a from-account and
an expense category; income wants a to-account and an income category; a
transfer wants two distinct accounts and no category. Every writer — router,
Alfred tool, importer — goes through it. Ownership goes through a resolver like
`list_service.resolve`, which is the only thing stopping a transaction being
filed against another user's account.

UI: an accounts screen with balances by group, an entry form, a transaction
list. Deliberately plain; the reports come later.

**Done when** a person can record their real month and the balances match their
real accounts, and a cross-user isolation test exists for every finance table.

## 27 — Alfred can log it, and what he is allowed to say

The phase that decides whether the ledger gets used. A finance tracker dies of
entry friction, and this project's advantage over Money Manager's three taps is
that "spent 45k on lunch" in Telegram is fewer.

Tools: log an expense, income and transfer; list recent transactions; report
balances. Deletes go through the existing confirmation gate. Everything gated by
`finance_service.is_enabled` through the existing `work_blocked` pattern.

Shipping with it, not after it, because the moment Alfred can see money the
boundary matters:

- **He sees aggregates by default, not rows.** Totals, category sums, balances,
  surplus — not every merchant and amount. Alfred's context reaches an LLM
  provider that may be a third party under the user's own key.
- **The advice boundary in the prompt.** He does arithmetic on the user's own
  numbers. He does not advise on products, markets, instruments, loans or
  currencies, and says plainly that this one deserves a person.

**Done when** the owner can log a day's spending in Telegram without opening the
app, and the prompt work is reviewed by hand rather than generated.

## 28 — Bringing the history in, and getting it out

Early on purpose. Every report, budget and projection downstream is only as
interesting as the history behind it, and the owner has years of it in Money
Manager. Importing turns phase 31 from a demo into something true on the day it
ships.

Money Manager's Excel export in, mapped onto accounts, categories and the three
record types, with a dry-run that reports what it would create and what it
cannot match before writing anything. CSV and Excel out, because export is a
first-class feature in a product holding somebody's ledger, not a courtesy.

**Done when** a real export file lands as rows whose totals match the source
file, and a second import of the same file creates nothing new.

## 29 — Budgets, and the month that starts on payday

A monthly budget per category, with weekly and annual periods, and spend against
it. The period start day is a per-user setting resolved through
`services/timezones.py` — salary dates are what make a budget match a life, and
naive "this month" is the same bug this project already hit with naive "today".

**Carry-over is the one deliberate step past the parity target**: Money Manager
does not have it and its users keep asking. Unspent budget rolling forward,
opt-in per budget, off by default.

**Done when** a budget whose month starts on the 25th reports the right window
in any timezone.

## 30 — The predictable half, posted for you

Salary, rent, subscriptions, loan instalments — recurring transactions and
automatic transfers on a configurable frequency. This removes the half of the
logging that is knowable in advance, which is the other half of the friction
problem.

Scheduling rides on `POST /api/internal/cron/tick` and the existing insert-first
exactly-once pattern on a log table with a UNIQUE constraint. A salary that
posts twice because two workers ticked together is a corrupted ledger whose
first symptom is a balance nobody can explain.

**Done when** a recurring record fires once under repeated ticks and concurrent
workers, proven by a test that ticks twice.

## 31 — Where the money went

The reporting surface, and with phase 28 behind it, immediately meaningful: by
category with drill-down into subcategories, by month, in and out as cash flow,
and a calendar of daily totals. The focus timeline strip from phase 23 is the
house precedent — the gaps and the spikes are the point.

**Done when** the figures reconcile against the transaction list, and work
spending is labelled rather than folded anonymously into a total.

## 32 — What the next months look like

Projection, and the first phase where the honesty rules bite. **Medians of
complete periods, never means** — one hospital bill or one bonus destroys a mean
and the person then disbelieves the whole report, correctly. A **range, not a
point**, and the number of periods it rests on stated on the figure. The house
precedent is `focus_service.suggested_focus_minutes`: the user's own median,
never a constant.

No return assumptions, no inflation guesses, no borrowed rules of thumb. Their
numbers or nothing.

**Done when** a projection from four logged months says so on its face.

## 33 — Things you are saving for

The car and the wedding. A goal with a target amount, currency, optional date,
and the accounts that count toward it. Then the arithmetic both ways: time to
target at the observed surplus, and the monthly amount a chosen date demands —
with the honest verdict against reality, "you have cleared that in one of the
last six months".

The research is clear that a goal's defensible promise is *clarity*, not that it
will make someone save. Build it for the arithmetic, claim nothing more.

**Done when** a goal in a different currency from the main one is right.

## 34 — Cards, loans, and what you actually owe

Credit cards with a settlement date, which is what produces payable versus
outstanding; card payment as a transfer, not an expense; loans and overdrafts as
negative-balance accounts so net worth is a real number rather than a cheerful
one.

**Done when** a card's payable figure matches a real statement.

## 35 — Before you commit to it

"What can we do with what we have." A what-if over the projection: add a
commitment, a one-off purchase or a change in income, and see the shape it makes
— including the month a balance goes negative. Saved scenarios, compared side by
side, and never written to the ledger.

**Done when** a scenario can be run, kept and discarded without touching a
single real row.

## 36 — Alfred's financial register

The principles work, last because it needs everything above to reason about.
`alfred_principles.py` gains the financial folklore block — the 50/30/20 rule,
the latte factor, six months of expenses as a universal number, snowball versus
avalanche as settled, any return assumption, any claim that spending reveals a
mental state — banned on the same footing as the habit myths, and for the same
reason. Plus the per-user setting for anyone who wants him to see rows rather
than aggregates, and finance nudges inside the existing nudge budget and quiet
hours, since the evidence says reminders work and then fade.

**Done when** the folklore block is enforced by a test, as the habit myths are.

---

### Order worth building it in

Numeric order is dependency order here. **26 and 27 alone already beat a
notebook**, and are the honest minimum: a correct ledger and a way to fill it
without friction. 28 next, so everything after it is true rather than
illustrative. The rest can be taken in any order the owner likes, except that 32
must precede 33 and 35, which are both arithmetic on the projection.

---

## Before phase 0 — the Alfred build (2026-10, absorbed from ROADMAP.md)

All done. Kept because the constraints below still bind, not for the
history.

| What | Status |
|---|---|
| Telegram link + webhook, Alfred tool-calling, multi-provider, BYOK, self-managed memory | done |
| Security/points audit, multi-user, per-user timezone and form of address | done |
| Focus session `mode` column and "by mode" stats | done (migration 013) |
| Telegram voice messages | done |
| Image understanding (Telegram photos) | done |
| Focus-week chart and daily-brief card images | done |
| Image *generation* | deferred — chart visuals cover the stated use cases; AI-generated images only via a BYOK key |
| Daily briefings and reminders | done (migration 014) |

### Constraints from that work that still apply

- **Capability flags live in `services/llm_providers/capabilities.py`**:
  `supports_audio_input`, `supports_vision_input`,
  `supports_image_generation`. Reuse them rather than inventing new names.
- **One worker in production** (`WEB_CONCURRENCY`, default 1) — but every
  periodic design must still be safe at any worker count: DB-backed
  counters, unique constraints, and a cron endpoint instead of an
  in-process scheduler. They are correct at one worker and allow scaling.
- **Timezones** come from `bat_account.timezone`, never a per-feature
  default, and never a hard-coded city.
- **Form of address** is `bat_account.alfred_address`, falling back to the
  username. Never a hard-coded name.
- **Failed turns** (a transcript or image that could not be processed) are
  kept out of the model's context, like any other failed turn —
  `FAILED_TURN_REPLIES` in `alfred_agent.py`.

### Scheduling, for the operator

`POST /api/internal/cron/tick` is pinged every minute by an external cron
and guarded by `X-Cron-Secret` (compared with `secrets.compare_digest`).
`services/scheduler.py` fires each due item **at most once per local day**,
inside a 3-hour window, in each user's own timezone; the two insert-first
logs (`bat_briefing_log`, `bat_reminder_log`) are what make it
exactly-once. The Railway cron setup steps are in the README.

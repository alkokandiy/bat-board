# bat-board, the next era

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
Tags → Filters → Smart Lists.** Five mechanisms, and bat-board has a weak
version of one.

Everything in Part 1 below is that hole. It is also what the owner has been
reporting for days without naming it — "31 with no date", "this look is
none of it and it sucks", 44 rows of equal weight.

---

## Part 1 — Structure (the spine)

### Phase 8 · Lists — **done** (backend + Alfred; front end in the same PR)
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

### Phase 9 · Sections inside a list
The `Getting Started / Feature Modules / Explore More` grouping in the
screenshot. Named by the user, not fixed — TickTick's habit sections are
hard-coded Morning/Afternoon/Evening and that is the wrong call.

`bat_sections` (list_id, name, position) and a nullable `section_id`.

### Phase 10 · Tags, promoted
`tags` is already a comma-separated string nobody can browse. Normalise it:
`bat_tags` + a join table, a tag rail in the sidebar, click to filter, and
`#tag` recognised while typing a title.

A tag crosses lists where a list cannot — "#deep" spans Khorasan and
Cybersecurity. That is the whole reason to have both.

### Phase 11 · Saved filters
A named, stored query: list + tag + priority + date window + status.
"Overdue in Khorasan", "#deep this week". The Eisenhower view and the date
chips are already saved filters with no name and no way to add one.

### Phase 12 · Smart lists you can configure
TickTick's `Show / Hide / Show if not empty` per smart list, and the
Features panel where whole modules switch off.

bat-board already does the hard half: `work_service.is_enabled` turns the
work track off everywhere. Generalise that to the rest — somebody who does
not use countdowns should not see Countdowns.

---

## Part 2 — The calendar is half a product

### Phase 13 · Subscribe to a real calendar
The owner's actual appointments are in Google Calendar. bat-board's
calendar shows only what was typed into bat-board, which is why it looks
empty next to a board with 44 missions on it.

Read-only ICS subscription first (`CalDAV`/`.ics` URL, polled by the cron
tick, cached, never written back). One-way is most of the value for a
fraction of the risk, and it does not need OAuth.

Two-way Google sync is a much bigger piece of work and should only follow
if one-way proves it is used.

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

### Phase 14 · Drag to reschedule
In the month grid and the day view. The day view already has the hour rows;
rescheduling a mission is currently a date picker, which is correct but
slow for the one operation a calendar exists to make fast.

---

## Part 3 — Things that are due

Carried from the TickTick report, still unbuilt, ordered by value:

### Phase 15 · Multiple reminders per mission
"1 day ahead, and again on the day." Reminders currently attach to a
reminder row, not to the mission, so a mission cannot carry its own.

### Phase 16 · Completion rate as the headline number
Completed ÷ *originally scheduled*, per week. A rate, not a volume:
uninflatable by creating easy work, and it penalises over-planning as well
as under-doing. The most honest metric in TickTick and bat-board does not
have it.

### Phase 17 · Named focus presets
`/focus reading` → a saved "Reading, stopwatch, linked to the Quran
mission". Starting a session and deciding what it is for become one action.

### Phase 18 · Habit archiving, and streaks derived from the log
`status` + `archived_at`, history preserved, `best_streak` untouched. And
move streak computation server-side off the check-in log, because a stored
counter drifts across backfills and devices.

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

**Phase 22 · Overtime.** At zero the session stays open and the clock
counts up. Finishing credits the planned time; one tap credits planned +
overtime. Never silently: the extra time is offered, not assumed, because
a timer left running on a closed laptop would otherwise invent hours.

### Phase 23 · The focus timeline strip

The right-hand panel draws the session as a block against an hour scale,
with a line at now. This is recommendation 3 of the TickTick report,
still unbuilt, and it is the passive half of the capture fix: unlogged
time shows as a visible hole, which invites backfill without a nag.
bat-board now has the day-view hour grid to draw it in.

### Phase 24 · Quantified habit goals

The Create Habit dialog's "Reach a certain amount": `5 Pages/Day`, a
unit, a step, and **When checking: Auto / Manual / Complete all**. The
habit detail panel then shows monthly completion in that unit and a
daily-goals chart.

Worth having, and the report already specified the model (`goal`, `step`,
`unit`, boolean or numeric). Note that bat-board's `minimum_viable` is
the better half of the same idea — shrinking the goal beats tracking
fractions of it — so quantities are an addition, not a replacement.

### Phase 25 · A habit detail panel

Monthly check-ins, total, check-in rate, current streak, a month calendar
of check-ins, and the goal chart. bat-board holds all of this already and
shows almost none of it: a habit row has a number and a bar.

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

Phases 8–12 are the spine and should not be reordered — sections need
lists, filters need tags, and configuring smart lists is meaningless until
there are lists to be smart about.

import React, { useEffect, useState } from 'react';
import { Check, Flag, Moon, Sunrise, Timer, Trash2 } from 'lucide-react';
import { api } from '../utils/api';
import { PageHeader, Panel, Button, EmptyState, Field, IconButton, Segmented, fieldClass } from './ui';

const FREQUENCY_LABEL = { daily: 'daily', weekly: 'weekly', monthly: 'monthly' };

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const PERIOD_WORD = { daily: 'today', weekly: 'this week', monthly: 'this month' };

function target(habit) {
  return habit.times_target || 1;
}

function keptThisPeriod(habit) {
  // "Three times a week" is not kept on the first of the three. The server
  // counts this properly; trust it when it is there, and fall back to the
  // date arithmetic for a payload that predates the field.
  if (habit.done_this_period !== undefined && habit.done_this_period !== null) {
    return habit.done_this_period >= target(habit);
  }
  if (!habit.last_completed) return false;
  const last = new Date(habit.last_completed);
  const now = new Date();
  if (habit.frequency === 'weekly') {
    return (now - last) / 86400000 < 7 && last <= now;
  }
  if (habit.frequency === 'monthly') {
    return last.getFullYear() === now.getFullYear() && last.getMonth() === now.getMonth();
  }
  return last.toDateString() === now.toDateString();
}

function dateKey(value) {
  return value ? String(value).slice(0, 10) : '';
}

/**
 * How it is actually going.
 *
 * The row used to lead with the consecutive streak and award an "ON FIRE"
 * badge above three — which is the chain framing this codebase bans outright,
 * and the reason a single blameless missed day reads as total failure. The
 * screen simply never showed it. Now the honest measure is the headline and
 * the run is a footnote. The points say nothing about how it is going — a
 * check-in is worth the same whatever kind of week it has been — so this is
 * the only thing on the row that does.
 */
function Adherence({ habit }) {
  const window = habit.adherence_window || 0;
  const done = habit.adherence_done || 0;
  if (!window) return null;
  const rate = done / window;
  const tone = rate >= 0.7 ? 'bg-signal-good' : rate >= 0.4 ? 'bg-signal-warn' : 'bg-bat-line-strong';

  return (
    <div className="flex items-center gap-2 mt-2">
      <div className="h-1 w-full max-w-[90px] shrink rounded-full bg-bat-surface overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-300 ease-soft ${tone}`}
             style={{ width: `${Math.round(rate * 100)}%` }} />
      </div>
      <span className="text-[10px] font-mono text-ink-muted tabular-nums whitespace-nowrap">
        {done} of your last {window}
      </span>
    </div>
  );
}

function HabitRow({ habit, kept, onCheckIn, onDelete, onSetTargetDate, onRest, onFocusOn }) {
  const want = target(habit);
  const resting = habit.resting_today === true;
  return (
    <div
      className={`group rounded-tile bg-bat-raised ring-1 p-3.5
        transition-all duration-200 ease-soft
        ${kept ? 'ring-bat-line opacity-55' : 'ring-bat-line hover:ring-bat-line-strong hover:shadow-lift'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center flex-wrap gap-1.5">
            <h3 className={`text-sm font-semibold tracking-wide ${kept ? 'text-ink-muted' : 'text-ink'}`}>
              {habit.name}
            </h3>
            <span className="text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-chip ring-1 ring-bat-line text-ink-faint">
              {habit.schedule_label || FREQUENCY_LABEL[habit.frequency] || habit.frequency}
            </span>
            {/* How far through the period they are. Without it, two of three
                reads as a missed week. */}
            {want > 1 && (
              <span className="text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-chip ring-1 ring-bat-line text-ink-muted tabular-nums">
                {habit.done_this_period || 0} of {want} {PERIOD_WORD[habit.frequency] || 'this period'}
              </span>
            )}
            {/* A rest they chose is not a day they failed, and the row has to
                say so — otherwise it reads as outstanding all day. */}
            {resting && (
              <span className="inline-flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-chip ring-1 ring-bat-line text-signal-work">
                <Moon size={9} /> Resting today
              </span>
            )}
          </div>

          {/* The cue is the strongest lever there is, so it reads as the
              instruction rather than as a grey afterthought. */}
          {habit.cue && (
            <p className="text-[11px] text-signal-work/80 mt-1">{habit.cue}</p>
          )}
          {/* The floor, not a lesser option: doing this still fires the cue
              and closes the reward, which is the loop being built. */}
          {habit.minimum_viable && (
            <p className="text-[11px] text-ink-faint mt-1">
              On a bad day: <span className="text-signal-good">{habit.minimum_viable}</span>
            </p>
          )}
          {habit.description && (
            <p className="text-xs text-ink-muted mt-1 leading-snug">{habit.description}</p>
          )}

          <Adherence habit={habit} />

          <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono text-ink-faint mt-1.5">
            {habit.streak > 0 && <span>{habit.streak} in a row</span>}
            {habit.best_streak > 0 && <span>best {habit.best_streak}</span>}
            {habit.focus_minutes > 0 && <span>{habit.focus_minutes}m focused</span>}
            {habit.last_completed && (
              <span>last {new Date(habit.last_completed).toLocaleDateString()}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {kept ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest text-signal-good">
              <Check size={12} strokeWidth={3} /> kept
            </span>
          ) : (
            // Still offered while resting, and deliberately so: somebody may
            // change their mind and do it anyway, and refusing the check-in
            // would make the rest a decision they could not take back.
            <Button
              tone={resting ? 'ghost' : 'self'}
              size="sm"
              onClick={() => onCheckIn(habit.id)}
            >
              Check in
            </Button>
          )}
          <div className="opacity-60 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200 flex items-center gap-1.5">
            {/* ADDED beside the others, never replacing one. The calendar
                chip was made to mean "focus" and stopped meaning anything
                else, which is exactly the mistake not to repeat. */}
            {onFocusOn && (
              <IconButton
                label={`Focus on "${habit.name}"`}
                icon={Timer}
                onClick={() => onFocusOn(habit.id)}
              />
            )}
            <IconButton
              label={resting ? `Back on "${habit.name}"` : `Take a rest day on "${habit.name}"`}
              icon={resting ? Sunrise : Moon}
              onClick={() => onRest(habit.id, habit.name, resting)}
            />
            <IconButton
              label={`Delete "${habit.name}"`}
              icon={Trash2}
              tone="danger"
              onClick={() => onDelete(habit.id, habit.name)}
            />
          </div>
        </div>
      </div>

      {/* An end date is a real thing to want — "do this until the exam" — but
          it was a bare date input labelled "Target end date:" on every single
          row, which made forty habits into forty date pickers. It opens only
          when there is one, or when you ask for one. */}
      <details className="mt-2">
        <summary className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer transition-colors duration-200 inline-flex items-center gap-1">
          <Flag size={10} />
          {habit.target_date
            ? `until ${new Date(habit.target_date).toLocaleDateString()}`
            : 'set an end date'}
        </summary>
        <input
          type="date"
          defaultValue={dateKey(habit.target_date)}
          onChange={(e) => onSetTargetDate(habit.id, e.target.value || null)}
          aria-label={`End date for "${habit.name}"`}
          className={`${fieldClass} font-mono mt-1.5 w-auto text-xs`}
        />
      </details>
    </div>
  );
}

export default function HabitsPanel({ habits = [], onRefreshHabits, onRefreshAccount, onFocusOn }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [frequency, setFrequency] = useState('daily');
  // The when-and-where. Naming a trigger that already happens is the
  // strongest lever there is for a habit actually sticking.
  const [cue, setCue] = useState('');
  const [minimumViable, setMinimumViable] = useState('');
  const [weekdays, setWeekdays] = useState([]);
  // Particular days, or a number of times — the two are different promises
  // and the server refuses both at once, so the form has to make you choose.
  const [weeklyMode, setWeeklyMode] = useState('days');
  const [timesPerWeek, setTimesPerWeek] = useState('3');
  const [dayOfMonth, setDayOfMonth] = useState('');
  const [intervalDays, setIntervalDays] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [flash, setFlash] = useState(null);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2600);
    return () => clearTimeout(t);
  }, [flash]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setError(null);
    try {
      await api.createHabit({
        name,
        description: description.trim() || null,
        frequency,
        cue: cue.trim() || null,
        minimum_viable: minimumViable.trim() || null,
        weekdays: frequency === 'weekly' && weeklyMode === 'days' && weekdays.length
          ? weekdays.sort((a, b) => a - b).join(',')
          : null,
        // Exactly one of the two ever leaves here. Sending both is a 400,
        // and rightly so: naming the days already says how many.
        times_per_period: frequency === 'weekly' && weeklyMode === 'times' && timesPerWeek
          ? Number(timesPerWeek)
          : null,
        day_of_month: frequency === 'monthly' && dayOfMonth ? Number(dayOfMonth) : null,
        interval_days: frequency === 'interval' && intervalDays ? Number(intervalDays) : null
      });
      setFlash(`Tracking "${name.trim()}"`);
      setName('');
      setDescription('');
      setCue('');
      setMinimumViable('');
      setWeekdays([]);
      setWeeklyMode('days');
      setTimesPerWeek('3');
      setDayOfMonth('');
      setIntervalDays('');
      setFrequency('daily');
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to create habit.");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckIn = async (habitId) => {
    try {
      setActionError(null);
      const updated = await api.checkInHabit(habitId);
      setFlash(updated?.name ? `Kept "${updated.name}"` : 'Kept');
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      setActionError(err.message || "Check-in failed");
    }
  };

  const handleDelete = async (id, habitName) => {
    if (!confirm(`Stop tracking "${habitName}"? Its history goes with it.`)) return;
    try {
      setActionError(null);
      await api.deleteHabit(id);
      setFlash(`Stopped tracking "${habitName}"`);
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      setActionError(err.message || "Delete failed");
    }
  };

  const handleRest = async (habitId, habitName, resting) => {
    try {
      setActionError(null);
      if (resting) {
        await api.unrestHabit(habitId);
        setFlash(`"${habitName}" counts again`);
      } else {
        await api.restHabit(habitId, {});
        setFlash(`Resting "${habitName}" today — it will not count against you`);
      }
      await onRefreshHabits();
    } catch (err) {
      setActionError(err.message || 'Could not change the rest day');
    }
  };

  const handleSetTargetDate = async (habitId, dateStr) => {
    try {
      await api.updateHabit(habitId, { target_date: dateStr || null });
      await onRefreshHabits();
    } catch (err) {
      console.error(err);
    }
  };

  // Due today AND not yet kept. Before, a weekly habit sat in "still to
  // keep" all seven days, because nothing recorded which day it was for.
  const dueToday = (h) => h.due_today !== false;
  const pending = habits.filter((h) => dueToday(h) && !keptThisPeriod(h));
  const kept = habits.filter(keptThisPeriod);
  const notDueToday = habits.filter((h) => !dueToday(h) && !keptThisPeriod(h));
  const bestStreak = habits.reduce((max, h) => Math.max(max, h.best_streak || h.streak || 0), 0);
  const withoutCue = habits.filter((h) => !(h.cue || '').trim()).length;
  const withoutFloor = habits.filter((h) => !(h.minimum_viable || '').trim()).length;

  const habitStats = habits.length === 0
    ? [{ label: 'none yet', value: '' }]
    : [
        { label: 'tracked', value: habits.length },
        ...(pending.length
          ? [{ label: 'still to keep', value: pending.length, tone: 'warn' }]
          : [{ label: 'all kept', value: '', tone: 'good' }]),
        ...(bestStreak ? [{ label: 'day best run', value: bestStreak }] : []),
        ...(withoutCue ? [{ label: 'without a trigger', value: withoutCue }] : []),
        ...(withoutFloor ? [{ label: 'with no bad-day version', value: withoutFloor }] : []),
      ];

  return (
    <div className="space-y-4">
      <PageHeader title="RECURRING RITUALS" stats={habitStats} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter items-start">
        <Panel title="New ritual" className="lg:sticky lg:top-4">
          {error && (
            <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late mb-3">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
            <Field label="What is it">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Fifty press-ups"
                className={fieldClass}
                required
              />
            </Field>

            <Field label="Trigger" hint="Tie it to something that already happens. It is the single biggest thing that makes a habit stick.">
              <input
                type="text"
                value={cue}
                onChange={(e) => setCue(e.target.value)}
                placeholder="After I put the kettle on"
                maxLength={200}
                className={fieldClass}
              />
            </Field>

            <Field label="On a bad day" hint="The two-minute version. Doing it still counts — a habit you can keep on the worst day survives the weeks the full one would not.">
              <input
                type="text"
                value={minimumViable}
                onChange={(e) => setMinimumViable(e.target.value)}
                placeholder="Five of them"
                maxLength={200}
                className={fieldClass}
              />
            </Field>

            <Field label="How often">
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)} className={fieldClass}>
                <option value="daily">Every day</option>
                <option value="weekly">On certain days</option>
                <option value="monthly">Once a month, on a date</option>
                <option value="interval">Every few days</option>
              </select>
            </Field>

            {/* "Every week" used to mean "some day, who knows". Saying which
                days is the whole point of choosing it. */}
            {/* A labelled group, not a Field: a <label> may wrap one form
                control, not seven buttons. Inside one, each button's
                accessible name is computed from the whole label rather than
                its own text, so a screen reader announces the same thing
                seven times. */}
            {/* Two different promises. Three named days is the stricter one
                and more than most people can keep; "three times, you pick"
                is the version that survives a bad Tuesday. The server
                refuses both at once, so the form makes you choose. */}
            {frequency === 'weekly' && (
              <div>
                <span className="mb-1.5 block text-[10px] font-mono uppercase tracking-[0.14em] text-ink-muted">
                  How you want to keep it
                </span>
                <Segmented
                  label="How you want to keep it"
                  value={weeklyMode}
                  onChange={setWeeklyMode}
                  options={[
                    { value: 'days', label: 'Certain days' },
                    { value: 'times', label: 'N times a week' },
                  ]}
                />
              </div>
            )}

            {frequency === 'weekly' && weeklyMode === 'times' && (
              <Field label="How many times a week" hint="Whichever days they land on. The week counts as kept once you reach the number.">
                <input
                  type="number"
                  min={1}
                  max={7}
                  value={timesPerWeek}
                  onChange={(e) => setTimesPerWeek(e.target.value)}
                  className={fieldClass}
                />
              </Field>
            )}

            {frequency === 'weekly' && weeklyMode === 'days' && (
              <div role="group" aria-label="Which days">
                <span className="mb-1.5 block text-[10px] font-mono uppercase tracking-[0.14em] text-ink-muted">
                  Which days
                </span>
                <div className="flex flex-wrap gap-1">
                  {WEEKDAYS.map((label, i) => {
                    const on = weekdays.includes(i);
                    return (
                      <button
                        key={label}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setWeekdays(on ? weekdays.filter((d) => d !== i) : [...weekdays, i])}
                        className={`px-2 py-1 rounded-chip text-[10px] font-mono uppercase tracking-wider
                          transition-all duration-200 ease-soft active:scale-[0.94]
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60 ${
                          on ? 'bg-signal-self text-bat-bg font-bold' : 'bg-bat-raised text-ink-faint ring-1 ring-bat-line hover:text-ink-muted'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <span className="mt-1.5 block text-[10px] leading-snug text-ink-faint">
                  Leave all unticked for "any day that week".
                </span>
              </div>
            )}

            {frequency === 'monthly' && (
              <Field label="Which date" hint="The 31st happens on the last day of shorter months.">
                <input type="number" min={1} max={31} value={dayOfMonth}
                  onChange={(e) => setDayOfMonth(e.target.value)}
                  placeholder="1" className={fieldClass} />
              </Field>
            )}

            {frequency === 'interval' && (
              <Field label="Every how many days" hint="Counted from today.">
                <input type="number" min={1} max={365} value={intervalDays}
                  onChange={(e) => setIntervalDays(e.target.value)}
                  placeholder="3" className={fieldClass} />
              </Field>
            )}

            <Field label="Notes">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Anything you'll want to remember."
                className={`${fieldClass} h-16 resize-none`}
              />
            </Field>

            <Button type="submit" tone="self" disabled={loading} className="w-full py-2.5">
              {loading ? 'Saving...' : 'Start tracking'}
            </Button>
          </form>
        </Panel>

        <div className="lg:col-span-2 space-y-gutter">
          {actionError && (
            <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late">
              {actionError}
            </div>
          )}

          <Panel title="Still to keep" meta={`${pending.length}`} bodyClassName="p-3 space-y-2">
            {habits.length === 0 ? (
              <EmptyState>Nothing tracked yet</EmptyState>
            ) : pending.length === 0 ? (
              <EmptyState compact>All kept — come back tomorrow</EmptyState>
            ) : (
              pending.map((habit) => (
                <HabitRow
                  key={habit.id}
                  habit={habit}
                  kept={false}
                  onCheckIn={handleCheckIn}
                  onDelete={handleDelete}
                  onSetTargetDate={handleSetTargetDate}
                  onRest={handleRest} onFocusOn={onFocusOn}
                />
              ))
            )}
          </Panel>

          {notDueToday.length > 0 && (
            <details>
              <summary className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer px-1 py-2 transition-colors duration-200">
                Not due today ({notDueToday.length})
              </summary>
              <div className="space-y-2 mt-2">
                {notDueToday.map((habit) => (
                  <HabitRow key={habit.id} habit={habit} kept
                    onCheckIn={handleCheckIn} onDelete={handleDelete}
                    onSetTargetDate={handleSetTargetDate} onRest={handleRest} onFocusOn={onFocusOn} />
                ))}
              </div>
            </details>
          )}

          {/* Kept habits used to vanish from the screen entirely, so you could
              not see what you had already done — only what you had not. */}
          {kept.length > 0 && (
            <details>
              <summary className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer px-1 py-2 transition-colors duration-200">
                Kept ({kept.length})
              </summary>
              <div className="space-y-2 mt-2">
                {kept.map((habit) => (
                  <HabitRow
                    key={habit.id}
                    habit={habit}
                    kept
                    onCheckIn={handleCheckIn}
                    onDelete={handleDelete}
                    onSetTargetDate={handleSetTargetDate}
                    onRest={handleRest} onFocusOn={onFocusOn}
                  />
                ))}
              </div>
            </details>
          )}
        </div>
      </div>

      {flash && (
        <div
          role="status"
          className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] animate-rise-in
            rounded-chip bg-bat-raised ring-1 ring-bat-line-strong shadow-lift
            px-4 py-2 text-[11px] text-ink-muted max-w-[90vw] truncate"
        >
          {flash}
        </div>
      )}
    </div>
  );
}

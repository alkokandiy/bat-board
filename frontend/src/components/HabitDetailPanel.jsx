import React, { useEffect, useState } from 'react';
import { api } from '../utils/api';
import { Panel, StatTile, Button, EmptyState } from './ui';

const WEEKDAY_HEADERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const STATE_STYLES = {
  done: 'bg-signal-self text-bat-bg ring-1 ring-signal-self',
  // A rest is a decision, not a gap. It has to look like the neutral thing
  // it is, or the calendar tells the person off for taking one.
  rested: 'bg-bat-raised text-ink-muted ring-1 ring-bat-line-strong',
  missed: 'bg-signal-late/20 text-signal-late ring-1 ring-signal-late/40',
  not_due: 'bg-transparent text-ink-faint/40',
  upcoming: 'bg-transparent text-ink-faint ring-1 ring-bat-line',
};

const STATE_LABELS = {
  done: 'Done',
  rested: 'Rested',
  missed: 'Missed',
  not_due: 'Not due',
  upcoming: 'Upcoming',
};

const LEGEND_SWATCHES = {
  done: 'bg-signal-self',
  rested: 'bg-bat-raised ring-1 ring-bat-line-strong',
  missed: 'bg-signal-late/30 ring-1 ring-signal-late/50',
  not_due: 'bg-bat-surface ring-1 ring-bat-line/50',
  upcoming: 'bg-transparent ring-1 ring-bat-line-strong',
};

const LEGEND_ORDER = ['done', 'rested', 'missed', 'not_due', 'upcoming'];

const toMonthString = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

const monthLabel = (month) => {
  const [year, m] = month.split('-').map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
};

// Monday-first, derived from the date itself. Indexing into the payload would
// be right only when the month happens to start on a Monday.
const weekdayIndex = (dateStr) => {
  const d = new Date(`${dateStr}T00:00:00`);
  return (d.getDay() + 6) % 7;
};

const dayNumber = (dateStr) => Number(dateStr.slice(8, 10));

export default function HabitDetailPanel({ habitId, habitName, onClose }) {
  const [month, setMonth] = useState(() => toMonthString(new Date()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    api.getHabitHistory(habitId, month)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load this habit.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [habitId, month]);

  const currentMonth = toMonthString(new Date());
  const canGoForward = month < currentMonth;

  const changeMonth = (offset) => {
    const [year, m] = month.split('-').map(Number);
    const next = new Date(year, m - 1 + offset, 1);
    const nextMonth = toMonthString(next);
    if (nextMonth > currentMonth) return;
    setMonth(nextMonth);
  };

  const leadingBlanks = data && data.days.length ? weekdayIndex(data.days[0].date) : 0;

  return (
    <Panel
      title={data?.name || habitName || 'HABIT'}
      action={(
        <Button tone="ghost" size="sm" onClick={onClose} aria-label="Close habit history">
          Close
        </Button>
      )}
      bodyClassName="p-4 space-y-4"
    >
      <div className="flex items-center justify-between gap-3">
        <Button
          tone="ghost"
          size="sm"
          onClick={() => changeMonth(-1)}
          aria-label="Previous month"
        >
          ←
        </Button>
        <span className="text-xs font-mono uppercase tracking-widest text-ink-muted">
          {monthLabel(month)}
        </span>
        <Button
          tone="ghost"
          size="sm"
          onClick={() => changeMonth(1)}
          disabled={!canGoForward}
          aria-label="Next month"
        >
          →
        </Button>
      </div>

      {error && (
        <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late">
          {error}
        </div>
      )}

      {!error && loading && !data && (
        <div className="py-10 text-center text-ink-faint font-mono text-xs">GATHERING THE RECORD...</div>
      )}

      {!error && data && data.days.length === 0 && (
        <EmptyState>Nothing recorded this month</EmptyState>
      )}

      {!error && data && data.days.length > 0 && (
        <>
          <div>
            <div className="grid grid-cols-7 gap-1 mb-1">
              {WEEKDAY_HEADERS.map((label, i) => (
                <div key={`${label}-${i}`} className="text-center text-[9px] font-mono uppercase tracking-widest text-ink-faint">
                  {label}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: leadingBlanks }, (_, i) => (
                <div key={`blank-${i}`} aria-hidden="true" />
              ))}
              {data.days.map((d) => (
                <div
                  key={d.date}
                  data-testid={`habit-day-${d.date}`}
                  data-state={d.state}
                  aria-label={`${d.date}: ${STATE_LABELS[d.state] || d.state}`}
                  title={`${d.date} · ${STATE_LABELS[d.state] || d.state}`}
                  className={`aspect-square rounded-chip flex items-center justify-center text-[11px] font-mono tabular-nums
                    ${STATE_STYLES[d.state] || STATE_STYLES.not_due}`}
                >
                  {dayNumber(d.date)}
                </div>
              ))}
            </div>
          </div>

          <div data-testid="habit-legend" className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {LEGEND_ORDER.map((state) => (
              <span key={state} className="inline-flex items-center gap-1.5 text-[10px] font-mono text-ink-faint">
                <span className={`w-2.5 h-2.5 rounded-[3px] ${LEGEND_SWATCHES[state]}`} aria-hidden="true" />
                {STATE_LABELS[state]}
              </span>
            ))}
          </div>

          <div data-testid="habit-figures" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatTile
              label="Check-in rate"
              value={data.check_in_rate == null ? '—' : `${data.check_in_rate}%`}
              hint={`${data.done_this_month} done · ${data.rested_this_month} rested`}
            />
            <StatTile label="Done this month" value={data.done_this_month} />
            <StatTile label="Current streak" value={data.streak} />
            <StatTile label="Best streak" value={data.best_streak} />
            <StatTile label="Total check-ins" value={data.total_check_ins} />
          </div>
        </>
      )}
    </Panel>
  );
}

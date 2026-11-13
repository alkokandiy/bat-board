import React, { useMemo } from 'react';
import { isToday } from '../utils/calendarDays';

/**
 * Twelve months at once, coloured by what was in each day.
 *
 * The point of a year is not to read it — no appointment is legible at
 * this size — it is to see shape: which months were worked and which went
 * quiet. So the cells carry a heatmap and almost nothing else.
 *
 * Two inputs, because they answer different questions. `minutes` is
 * effort, time actually spent; `done` is output, missions completed plus
 * habits kept. A day of three hours with nothing finished is a real day
 * and so is the reverse, so the intensity takes both and the tooltip
 * reports them separately rather than blending them into one number
 * nobody can take apart again.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const DAY_INITIALS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

// Four steps, not a gradient: the eye reads bands, and a continuous scale
// invites comparing two days that differ by four minutes.
const LEVELS = [
  'bg-bat-raised',
  'bg-signal-self/20',
  'bg-signal-self/45',
  'bg-signal-self/70',
  'bg-signal-self',
];

/** An hour of focus, or two things finished, is a full day's worth. */
export function intensity(cell) {
  if (!cell) return 0;
  const score = (cell.minutes || 0) / 60 + (cell.done || 0) / 2;
  if (score <= 0) return 0;
  if (score < 0.5) return 1;
  if (score < 1.5) return 2;
  if (score < 3) return 3;
  return 4;
}

function monthCells(year, month) {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() + 6) % 7;        // Monday-first
  const length = new Date(year, month + 1, 0).getDate();
  const cells = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= length; d += 1) cells.push(new Date(year, month, d));
  return cells;
}

export default function YearView({ year, activity = [], onOpenDay }) {
  const byDate = useMemo(() => {
    const map = {};
    activity.forEach((c) => { map[c.date] = c; });
    return map;
  }, [activity]);

  const key = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4">
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {MONTHS.map((name, month) => (
          <div key={name}>
            <h3 className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-muted">
              {name}
            </h3>
            <div className="grid grid-cols-7 gap-[3px]">
              {DAY_INITIALS.map((d, i) => (
                <span key={i} className="text-center text-[8px] font-mono text-ink-faint/70">
                  {d}
                </span>
              ))}
              {monthCells(year, month).map((d, i) => {
                if (!d) return <span key={`p${i}`} />;
                const cell = byDate[key(d)];
                const level = intensity(cell);
                const parts = [];
                if (cell?.minutes) parts.push(`${cell.minutes}m focused`);
                if (cell?.done) parts.push(`${cell.done} done`);
                return (
                  <button
                    key={key(d)}
                    type="button"
                    onClick={() => onOpenDay?.(d)}
                    title={`${d.toLocaleDateString()}${parts.length ? ` — ${parts.join(', ')}` : ''}`}
                    aria-label={`Open ${d.toLocaleDateString()}`}
                    data-level={level}
                    className={`aspect-square rounded-[2px] text-[8px] leading-none
                      transition-all duration-150 ease-soft hover:brightness-150
                      focus:outline-none focus-visible:ring-1 focus-visible:ring-signal-self/60
                      ${LEVELS[level]}
                      ${isToday(d) ? 'ring-1 ring-signal-self' : ''}`}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-center gap-2">
        <span className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">Quiet</span>
        {LEVELS.map((c, i) => (
          <span key={i} className={`h-2.5 w-2.5 rounded-[2px] ${c}`} aria-hidden="true" />
        ))}
        <span className="font-mono text-[9px] uppercase tracking-widest text-ink-faint">Full</span>
      </div>
    </div>
  );
}

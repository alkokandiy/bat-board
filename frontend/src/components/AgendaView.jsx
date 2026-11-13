import React from 'react';
import { Flag, Timer } from 'lucide-react';
import { IconButton } from './ui';
import { isToday, timeRange } from '../utils/calendarDays';

/**
 * Everything ahead, in the order it happens.
 *
 * The grid and the timeline both draw empty space: a week with two
 * meetings in it is mostly blank rows. Agenda draws only what exists, so
 * "what is actually coming up" is one screen rather than a scroll through
 * seven columns of nothing.
 *
 * Days with nothing in them are left out entirely — an agenda of empty
 * days is the thing it exists not to be.
 */

const DAYS_AHEAD = 30;

export default function AgendaView({
  from,
  eventsForDay,
  missionsForDay,
  onEditEvent,
  onFocusOn,
  onOpenDay,
}) {
  const start = new Date(from);
  start.setHours(0, 0, 0, 0);

  const days = [];
  for (let i = 0; i < DAYS_AHEAD; i += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    const events = eventsForDay(day);
    const missions = missionsForDay(day);
    if (events.length || missions.length) days.push({ day, events, missions });
  }

  if (days.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
          Nothing in the next {DAYS_AHEAD} days
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-bat-line/50">
      {days.map(({ day, events, missions }) => (
        <div key={day.toDateString()} className="flex gap-4 px-5 py-3">
          {/* The date column is the spine; it repeats once per day, not
              once per row, so a day with four things reads as one day. */}
          <button
            type="button"
            onClick={() => onOpenDay?.(day)}
            aria-label={`Open ${day.toLocaleDateString()}`}
            className="w-14 shrink-0 text-left group"
          >
            <span className={`block font-display text-2xl leading-none tabular-nums
              ${isToday(day) ? 'text-signal-self' : 'text-ink-muted group-hover:text-ink'}`}>
              {day.getDate()}
            </span>
            <span className="block text-[9px] font-mono uppercase tracking-widest text-ink-faint">
              {day.toLocaleDateString(undefined, { weekday: 'short' })}
              {day.getDate() === 1 || isToday(day)
                ? ` ${day.toLocaleDateString(undefined, { month: 'short' })}`
                : ''}
            </span>
          </button>

          <div className="flex-1 min-w-0 space-y-1.5">
            {missions.map((m) => (
              <div
                key={`m${m.id}`}
                className="flex items-center gap-2 rounded-tile bg-bat-raised ring-1 ring-bat-line px-3 py-2"
              >
                <Flag size={11} className="shrink-0 text-signal-late" />
                <span className="flex-1 min-w-0 truncate text-xs text-ink" title={m.title}>
                  {m.title}
                </span>
                <span className="shrink-0 text-[9px] font-mono uppercase tracking-widest text-ink-faint">
                  due
                </span>
                {onFocusOn && (
                  <IconButton
                    label={`Focus on "${m.title}"`}
                    icon={Timer}
                    onClick={() => onFocusOn(m.id)}
                  />
                )}
              </div>
            ))}

            {events.map((e) => {
              const colour = e.color || '#eab308';
              return (
                <button
                  key={`e${e.id}`}
                  type="button"
                  onClick={() => onEditEvent?.(e)}
                  aria-label={`Edit "${e.title}"`}
                  className="flex w-full items-center gap-3 rounded-tile border-l-2 px-3 py-2 text-left
                    hover:brightness-125 transition-all duration-200 ease-soft
                    focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/40"
                  style={{ backgroundColor: `${colour}14`, borderColor: colour }}
                >
                  <span className="w-[5.5rem] shrink-0 font-mono text-[10px] tabular-nums text-ink-muted">
                    {timeRange(e)}
                  </span>
                  <span className="flex-1 min-w-0 truncate text-xs text-ink">{e.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

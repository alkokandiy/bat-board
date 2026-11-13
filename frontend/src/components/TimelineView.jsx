import React, { useEffect, useRef } from 'react';
import { Flag } from 'lucide-react';
import { HOURS, byHour, isToday, timeRange } from '../utils/calendarDays';

/**
 * Any number of days against the clock.
 *
 * One component for Day, 3 Days and Week, because they are the same
 * drawing with a different column count — seven separate calendar views
 * would be seven places for the same off-by-one.
 *
 * The month grid answers "what is this month shaped like"; this answers
 * the question you ask on a Monday morning, whether Thursday afternoon is
 * free, which a grid with no times in it cannot.
 */

const DEFAULT_HOUR = 8;

export default function TimelineView({
  days,
  events = [],
  missionsForDay = () => [],
  eventsForDay = () => [],
  onEditEvent,
  onAddEvent,
  onOpenDay,
}) {
  const scrollRef = useRef(null);
  // One grid template for the whole view, so the header, the due strip and
  // every hour row stay in the same columns however many days there are.
  const columns = { gridTemplateColumns: `3.5rem repeat(${days.length}, minmax(0, 1fr))` };

  // Start where the week's earliest event is, or the working morning.
  useEffect(() => {
    const hours = days.flatMap((d) => Object.keys(byHour(eventsForDay(d), d)).map(Number));
    const target = hours.length ? Math.min(...hours) : DEFAULT_HOUR;
    const row = scrollRef.current?.querySelector(`[data-hour="${target}"]`);
    if (row?.scrollIntoView) row.scrollIntoView({ block: 'start' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days.length && days[0].toDateString(), events]);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* The day names stay put while the hours scroll under them. */}
      <div style={columns} className="shrink-0 grid border-b border-bat-line">
        <div />
        {days.map((d) => (
          <button
            key={d.toDateString()}
            type="button"
            onClick={() => onOpenDay?.(d)}
            aria-label={`Open ${d.toLocaleDateString()}`}
            className={`px-1 py-2 text-center transition-colors duration-150 ease-soft
              hover:bg-bat-raised/60 focus:outline-none
              focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-signal-self/60
              ${isToday(d) ? 'bg-signal-self/[0.07]' : ''}`}
          >
            <span className="block text-[9px] font-mono uppercase tracking-widest text-ink-faint">
              {d.toLocaleDateString(undefined, { weekday: 'short' })}
            </span>
            <span className={`block text-sm font-mono tabular-nums
              ${isToday(d) ? 'text-signal-self font-bold' : 'text-ink-muted'}`}>
              {d.getDate()}
            </span>
          </button>
        ))}
      </div>

      {/* Missions are due ON a day, not AT a time, so they sit above the
          clock rather than being given an hour they never had. */}
      {days.some((d) => missionsForDay(d).length > 0) && (
        <div style={columns} className="shrink-0 grid border-b border-bat-line">
          <div className="px-2 py-1.5 text-right">
            <span className="text-[9px] font-mono uppercase tracking-widest text-ink-faint">Due</span>
          </div>
          {days.map((d) => (
            <div key={d.toDateString()} className="px-1 py-1.5 space-y-[2px] border-l border-bat-line/50">
              {missionsForDay(d).map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onOpenDay?.(d)}
                  title={`Mission due: ${m.title}`}
                  className="flex w-full items-center gap-1 rounded-sm bg-signal-late/15 px-1 py-0.5
                    text-left text-[9px] leading-tight text-signal-late
                    hover:brightness-125 transition-all duration-200 ease-soft"
                >
                  <Flag size={8} className="shrink-0" />
                  <span className="truncate">{m.title}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto">
        {HOURS.map((h) => (
          <div
            key={h}
            data-hour={h}
            style={columns}
            className="grid border-b border-bat-line/40 last:border-0"
          >
            <div className="px-2 py-1 text-right">
              <span className="text-[10px] font-mono tabular-nums text-ink-faint">
                {String(h).padStart(2, '0')}:00
              </span>
            </div>
            {days.map((d) => {
              const here = byHour(eventsForDay(d), d)[h] || [];
              return (
                <div key={d.toDateString()} className="border-l border-bat-line/40 min-h-[2rem] p-[2px]">
                  {here.length === 0 ? (
                    <button
                      type="button"
                      onClick={() => onAddEvent?.(d, h)}
                      aria-label={`Add an event on ${d.toLocaleDateString()} at ${String(h).padStart(2, '0')}:00`}
                      className="block h-full w-full min-h-[1.75rem] rounded-sm
                        hover:bg-bat-raised/60 transition-colors duration-150 ease-soft
                        focus:outline-none focus-visible:ring-1 focus-visible:ring-signal-self/40"
                    />
                  ) : (
                    here.map((e) => {
                      const colour = e.color || '#eab308';
                      return (
                        <button
                          key={e.id}
                          type="button"
                          onClick={() => onEditEvent?.(e)}
                          title={`${e.title} · ${timeRange(e)}`}
                          aria-label={`Edit "${e.title}"`}
                          className="mb-[2px] block w-full rounded-sm border-l-2 px-1 py-0.5 text-left
                            last:mb-0 hover:brightness-125 transition-all duration-200 ease-soft
                            focus:outline-none focus-visible:ring-1 focus-visible:ring-signal-self/40"
                          style={{ backgroundColor: `${colour}1f`, borderColor: colour }}
                        >
                          <span className="block truncate text-[10px] leading-tight text-ink">{e.title}</span>
                          <span className="block truncate text-[9px] font-mono tabular-nums text-ink-muted">
                            {timeRange(e)}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

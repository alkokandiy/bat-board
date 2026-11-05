import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Clock, Flag, Plus, Timer, X } from 'lucide-react';
import { Button, IconButton } from './ui';

/**
 * One day, hour by hour.
 *
 * The month grid can show four chips in a cell and then "+2 more", so a busy
 * day was partly invisible and entirely unordered — two events and a mission
 * due sat in the same little stack with no times on them. And because a chip
 * could only carry one click, every chip had to mean exactly one thing:
 * tapping a mission started a focus session, which is right when that is what
 * you wanted and wrong every other time.
 *
 * A day needs room, not a cleverer chip. Everything that day is here, in
 * order, with its own actions: edit the event, start the clock on the
 * mission, move it to another day, or add something at a particular hour.
 */

const HOURS = Array.from({ length: 24 }, (_, i) => i);

// Where to scroll when nothing in the day says otherwise. Not midnight: the
// top of the list would be eight empty hours.
const DEFAULT_HOUR = 8;

function hhmm(date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export default function DayView({
  day,
  events = [],
  missions = [],
  onClose,
  onEditEvent,
  onAddEvent,
  onFocusOn,
  onRescheduleMission,
}) {
  const scrollRef = useRef(null);
  const [moving, setMoving] = useState(null);   // mission id being rescheduled

  // An event belongs to the hour it STARTS in. A block spanning the real
  // duration would be the honest drawing, but it collides with overlapping
  // events and needs a layout algorithm; showing the range on one row says
  // the same thing and can be read at a glance.
  const byHour = useMemo(() => {
    const map = {};
    events.forEach((e) => {
      const start = new Date(e.start_time);
      const h = sameDay(start, day) ? start.getHours() : 0;
      (map[h] = map[h] || []).push(e);
    });
    Object.values(map).forEach((list) =>
      list.sort((a, b) => new Date(a.start_time) - new Date(b.start_time)));
    return map;
  }, [events, day]);

  useEffect(() => {
    const hours = Object.keys(byHour).map(Number).sort((a, b) => a - b);
    const target = hours.length ? hours[0] : DEFAULT_HOUR;
    const row = scrollRef.current?.querySelector(`[data-hour="${target}"]`);
    if (row?.scrollIntoView) row.scrollIntoView({ block: 'start' });
  }, [byHour]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const heading = day.toLocaleDateString(undefined, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
  const isToday = sameDay(day, new Date());

  return (
    <div
      className="fixed inset-0 z-[900] bg-bat-bg/80 backdrop-blur-sm flex items-start justify-center p-4 sm:p-8 overflow-y-auto"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Day view, ${heading}`}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl rounded-card bg-bat-surface ring-1 ring-bat-line-strong shadow-lift overflow-hidden"
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-bat-line">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-ink truncate">{heading}</h2>
            <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">
              {isToday ? 'today' : ''}
              {isToday && (events.length || missions.length) ? ' · ' : ''}
              {events.length} {events.length === 1 ? 'event' : 'events'}
              {missions.length ? ` · ${missions.length} due` : ''}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Button size="sm" tone="self" onClick={() => onAddEvent?.(day, 9)}>
              <Plus size={12} /> Event
            </Button>
            <IconButton label="Close day view" icon={X} onClick={onClose} />
          </div>
        </div>

        {/* Missions are due ON a day, not AT a time, so they sit above the
            clock rather than being given an hour they never had. */}
        {missions.length > 0 && (
          <div className="border-b border-bat-line px-4 py-3 space-y-1.5">
            <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">
              Due this day
            </p>
            {missions.map((m) => (
              <div
                key={m.id}
                className="flex items-center gap-2 rounded-tile bg-bat-raised ring-1 ring-bat-line px-3 py-2"
              >
                <Flag size={11} className="shrink-0 text-signal-late" />
                <span className="flex-1 min-w-0 truncate text-xs text-ink" title={m.title}>
                  {m.title}
                </span>
                {moving === m.id ? (
                  <input
                    type="date"
                    autoFocus
                    aria-label={`New date for "${m.title}"`}
                    onChange={(e) => {
                      if (!e.target.value) return;
                      onRescheduleMission?.(m.id, e.target.value);
                      setMoving(null);
                    }}
                    onBlur={() => setMoving(null)}
                    className="bg-bat-surface ring-1 ring-bat-line rounded-chip px-2 py-1
                      text-[10px] font-mono text-ink focus:outline-none
                      focus-visible:ring-2 focus-visible:ring-signal-self/60"
                  />
                ) : (
                  <>
                    {onFocusOn && (
                      <IconButton
                        label={`Focus on "${m.title}"`}
                        icon={Timer}
                        onClick={() => onFocusOn(m.id)}
                      />
                    )}
                    {onRescheduleMission && (
                      <IconButton
                        label={`Move "${m.title}" to another day`}
                        icon={Clock}
                        onClick={() => setMoving(m.id)}
                      />
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        <div ref={scrollRef} className="max-h-[55vh] overflow-y-auto">
          {HOURS.map((h) => {
            const here = byHour[h] || [];
            return (
              <div key={h} data-hour={h} className="flex border-b border-bat-line/50 last:border-0">
                <div className="w-14 shrink-0 px-2 py-2 text-right">
                  <span className="text-[10px] font-mono tabular-nums text-ink-faint">
                    {String(h).padStart(2, '0')}:00
                  </span>
                </div>
                {here.length === 0 ? (
                  // An empty hour IS the "add something at this time"
                  // target, so a time can be chosen by pointing at it
                  // rather than typed into a field.
                  <button
                    type="button"
                    onClick={() => onAddEvent?.(day, h)}
                    aria-label={`Add an event at ${String(h).padStart(2, '0')}:00`}
                    className="flex-1 min-w-0 min-h-[2.25rem]
                      hover:bg-bat-raised/60 transition-colors duration-150 ease-soft
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/40"
                  />
                ) : (
                  <div className="flex-1 min-w-0 px-2 py-1.5 space-y-1">
                    {here.map((e) => {
                      const start = new Date(e.start_time);
                      const end = e.end_time ? new Date(e.end_time) : null;
                      const colour = e.color || '#eab308';
                      return (
                        <button
                          key={e.id}
                          type="button"
                          onClick={() => onEditEvent?.(e)}
                          title={`Edit "${e.title}"`}
                          aria-label={`Edit "${e.title}"`}
                          className="w-full text-left rounded-tile border-l-2 px-2 py-1.5
                            hover:brightness-125 transition-all duration-200 ease-soft
                            focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/40"
                          style={{ backgroundColor: `${colour}1f`, borderColor: colour }}
                        >
                          <span className="block text-xs text-ink truncate">{e.title}</span>
                          <span className="block text-[10px] font-mono tabular-nums text-ink-muted">
                            {hhmm(start)}{end ? `–${hhmm(end)}` : ''}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

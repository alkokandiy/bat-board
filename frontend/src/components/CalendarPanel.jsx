import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Plus, Trash2, X } from 'lucide-react';
import { api } from '../utils/api';
import { PageHeader, Panel, Button, EmptyState, Field, IconButton, fieldClass } from './ui';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

// How many chips fit in a day cell before the rest become a count.
const MAX_CHIPS_PER_DAY = 3;

function getMonthDays(year, month) {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const startDay = (first.getDay() + 6) % 7;
  const days = [];
  for (let i = 0; i < startDay; i++) days.push(null);
  for (let d = 1; d <= last.getDate(); d++) days.push(new Date(year, month, d));
  while (days.length % 7 !== 0) days.push(null);
  return days;
}

function toLocalDatetimeString(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d}T${h}:${min}`;
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

// Midnight-to-midnight, so a comparison is about the DAY and not the hour.
function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/**
 * Does this event touch this day?
 *
 * It used to ask only whether the event STARTED here, so a conference running
 * Monday to Wednesday appeared on Monday and then vanished — the two days you
 * were actually busy looked free.
 */
function coversDay(event, day) {
  const from = startOfDay(new Date(event.start_time));
  const to = event.end_time ? startOfDay(new Date(event.end_time)) : from;
  const d = startOfDay(day);
  return d >= from && d <= to;
}

export default function CalendarPanel() {
  const [events, setEvents] = useState([]);
  const [missions, setMissions] = useState([]);
  // Recomputed every render, not frozen at mount: left open overnight, the
  // board used to go on highlighting yesterday as today.
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [showForm, setShowForm] = useState(false);
  const [editEvent, setEditEvent] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', start_time: '', end_time: '', color: '#eab308' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [flash, setFlash] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.getCalendarEvents().then(data => { if (!cancelled) setEvents(data); }).catch(() => {});
    api.getMissions().then(data => { if (!cancelled) setMissions(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2600);
    return () => clearTimeout(t);
  }, [flash]);

  const closeForm = useCallback(() => {
    setShowForm(false);
    setEditEvent(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (!showForm) return;
    const onKey = (e) => { if (e.key === 'Escape') closeForm(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showForm, closeForm]);

  const refreshEvents = useCallback(() => api.getCalendarEvents().then(setEvents), []);

  const days = useMemo(() => getMonthDays(year, month), [year, month]);

  const missionDueMap = useMemo(() => {
    const map = {};
    missions.forEach(m => {
      if (m.due_date && m.status !== 'completed') {
        // Due dates are UTC-midnight calendar dates: key on the date part so
        // they land on the right day in every timezone.
        const [y, mo, d] = String(m.due_date).slice(0, 10).split('-').map(Number);
        const key = new Date(y, mo - 1, d).toDateString();
        if (!map[key]) map[key] = [];
        map[key].push(m);
      }
    });
    return map;
  }, [missions]);

  const sortedEvents = useMemo(
    () => [...events].sort((a, b) => new Date(a.start_time) - new Date(b.start_time)),
    [events]);

  // "Upcoming" was every event ever, sorted — which is how a dentist
  // appointment three weeks past showed up under that word. An event still
  // running counts as upcoming, so judge by its end where it has one.
  const upcomingEvents = useMemo(() => {
    const now = Date.now();
    return sortedEvents.filter(
      (e) => new Date(e.end_time || e.start_time).getTime() >= now);
  }, [sortedEvents]);

  const eventsThisMonth = useMemo(
    () => events.filter((e) => {
      const d = new Date(e.start_time);
      return d.getFullYear() === year && d.getMonth() === month;
    }).length,
    [events, year, month]);

  const headerStats = useMemo(() => {
    const out = [{ label: `in ${MONTHS[month]}`, value: eventsThisMonth }];
    const next = upcomingEvents[0];
    if (next) {
      const when = new Date(next.start_time);
      const days = Math.round((when - new Date()) / 86400000);
      out.push({
        label: days <= 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${days} days`,
        value: next.title.length > 28 ? next.title.slice(0, 27) + '…' : next.title,
        tone: days <= 1 ? 'warn' : undefined,
      });
    } else {
      out.push({ label: 'nothing scheduled ahead', value: '' });
    }
    return out;
  }, [eventsThisMonth, month, upcomingEvents]);

  const openAddForm = useCallback((date) => {
    setEditEvent(null);
    setError(null);
    // 09:00, not the midnight a clicked day literally is — nobody schedules
    // a thing for 00:00 by default.
    const at = new Date(date);
    at.setHours(9, 0, 0, 0);
    setForm({ title: '', description: '', start_time: toLocalDatetimeString(at), end_time: '', color: '#eab308' });
    setShowForm(true);
  }, []);

  const openEditForm = useCallback((event) => {
    setEditEvent(event);
    setError(null);
    setForm({
      title: event.title,
      description: event.description || '',
      start_time: toLocalDatetimeString(new Date(event.start_time)),
      end_time: event.end_time ? toLocalDatetimeString(new Date(event.end_time)) : '',
      color: event.color || '#eab308',
    });
    setShowForm(true);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    // Caught here as well as on the server, so the answer is immediate.
    if (form.end_time && new Date(form.end_time) < new Date(form.start_time)) {
      setError('An event cannot end before it starts.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = {
        title: form.title,
        description: form.description.trim() || null,
        start_time: new Date(form.start_time).toISOString(),
        end_time: form.end_time ? new Date(form.end_time).toISOString() : null,
        color: form.color,
      };
      const wasEdit = Boolean(editEvent);
      if (editEvent) {
        await api.updateCalendarEvent(editEvent.id, payload);
      } else {
        await api.createCalendarEvent(payload);
      }
      closeForm();
      setFlash(wasEdit ? `Updated "${payload.title}"` : `Added "${payload.title}"`);
      await refreshEvents();
    } catch (err) {
      setError(err.message || 'Could not save the event.');
    } finally {
      setLoading(false);
    }
  };

  // This function existed and was never called from anywhere, so the web app
  // had no way at all to delete a calendar event — only Alfred did.
  const handleDelete = async (event) => {
    if (!confirm(`Delete "${event.title}"?`)) return;
    try {
      await api.deleteCalendarEvent(event.id);
      closeForm();
      setFlash(`Deleted "${event.title}"`);
      await refreshEvents();
    } catch (err) {
      setError(err.message || 'Could not delete the event.');
    }
  };

  const isToday = (d) => d && sameDay(d, today);
  const isCurrentMonth = (d) => d && d.getMonth() === month;
  const getEventsForDay = (d) => sortedEvents.filter(e => coversDay(e, d));
  const getMissionsForDay = (d) => missionDueMap[d.toDateString()] || [];

  const goToToday = () => {
    setYear(today.getFullYear());
    setMonth(today.getMonth());
  };

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else { setMonth(m => m - 1); }
  };

  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else { setMonth(m => m + 1); }
  };

  const isCurrentMonthView = year === today.getFullYear() && month === today.getMonth();

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="shrink-0">
        <PageHeader
          title="CALENDAR"
          stats={headerStats}
          action={(
            <Button tone="self" onClick={() => openAddForm(new Date())}>
              <Plus size={13} /> New event
            </Button>
          )}
        />
      </div>

      <div className="flex-1 min-h-0 rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile flex flex-col overflow-hidden">
        <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-white/[0.04]">
          <IconButton label="Previous month" icon={ChevronLeft} onClick={prevMonth} />
          <div className="flex items-center gap-4">
            <h2 className="font-display text-xl tracking-wide text-ink">{MONTHS[month]} {year}</h2>
            {!isCurrentMonthView && (
              <Button size="sm" onClick={goToToday}>Today</Button>
            )}
          </div>
          <IconButton label="Next month" icon={ChevronRight} onClick={nextMonth} />
        </div>

        {/* Red chips and coloured chips sat side by side with nothing to say
            they were different kinds of thing. */}
        <div className="shrink-0 flex items-center gap-4 px-5 py-2 border-b border-white/[0.04] text-[10px] font-mono uppercase tracking-wider text-ink-faint">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm bg-signal-late/40 ring-1 ring-signal-late/60" aria-hidden="true" />
            Mission due
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm bg-signal-self/40 ring-1 ring-signal-self/60" aria-hidden="true" />
            Event
          </span>
        </div>

        <div className="shrink-0 grid grid-cols-7 text-center border-b border-white/[0.04]">
          {DAYS.map(d => <div key={d} className="text-[10px] font-mono uppercase tracking-wider text-ink-faint py-2">{d}</div>)}
        </div>

        <div className="flex-1 grid grid-cols-7 auto-rows-fr">
          {days.map((d, i) => {
            if (!d) return <div key={i} className="border-b border-r border-bat-line bg-bat-bg/60" />;

            const dayMissions = getMissionsForDay(d);
            const dayEvents = getEventsForDay(d);
            // Missions take the first slots, events what is left — and the
            // overflow is whatever genuinely did not fit. It used to show a
            // count only above eight, so four missions and nothing else hid
            // the rest in silence.
            const shownMissions = dayMissions.slice(0, MAX_CHIPS_PER_DAY);
            const shownEvents = dayEvents.slice(0, Math.max(0, MAX_CHIPS_PER_DAY - shownMissions.length));
            const hidden = (dayMissions.length - shownMissions.length)
              + (dayEvents.length - shownEvents.length);

            return (
              <div key={i}
                role="button"
                tabIndex={0}
                aria-label={`Add an event on ${d.toLocaleDateString()}`}
                onClick={() => openAddForm(d)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openAddForm(d); } }}
                className={`border-b border-r border-bat-line p-2 cursor-pointer
                  transition-colors duration-200 ease-soft hover:bg-bat-raised
                  focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-signal-self/60
                  ${isToday(d) ? 'bg-signal-self/[0.07] ring-1 ring-inset ring-signal-self/30' : ''}`}
              >
                <div className="h-full flex flex-col">
                  <div className={`text-xs font-mono mb-1.5 leading-none tabular-nums ${isToday(d) ? 'text-signal-self font-bold' : isCurrentMonth(d) ? 'text-ink-muted' : 'text-ink-faint/50'}`}>
                    {d.getDate()}
                  </div>
                  <div className="flex-1 space-y-[2px] overflow-hidden">
                    {shownMissions.map(m => (
                      <div key={m.id} title={`Mission due: ${m.title}`}
                        className="text-[10px] bg-signal-late/15 text-signal-late border-l-2 border-signal-late/70 px-1.5 py-0.5 rounded-sm truncate leading-tight">
                        {m.title}
                      </div>
                    ))}
                    {shownEvents.map(evt => (
                      <div key={evt.id} title={evt.title}
                        onClick={evtClick => { evtClick.stopPropagation(); openEditForm(evt); }}
                        className="text-[10px] px-1.5 py-0.5 rounded-sm truncate leading-tight cursor-pointer border-l-2 hover:brightness-125 transition-all duration-200 ease-soft"
                        style={{ backgroundColor: (evt.color || '#eab308') + '26', color: evt.color || '#eab308', borderColor: evt.color || '#eab308' }}>
                        {evt.title}
                      </div>
                    ))}
                    {hidden > 0 && (
                      <div className="text-[10px] font-mono text-ink-faint">+{hidden} more</div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <Panel title="Upcoming" meta={`${upcomingEvents.length}`} bodyClassName="p-3" className="shrink-0">
        {upcomingEvents.length === 0 ? (
          <EmptyState compact>
            {sortedEvents.length ? 'Everything on the calendar has passed' : 'Nothing scheduled'}
          </EmptyState>
        ) : (
          <div className="flex items-center gap-2 overflow-x-auto">
            {upcomingEvents.slice(0, 8).map(e => (
              <button
                key={e.id}
                type="button"
                onClick={() => openEditForm(e)}
                aria-label={`Edit "${e.title}"`}
                className="flex items-center gap-1.5 text-xs rounded-chip bg-bat-raised ring-1 ring-bat-line
                  px-2.5 py-1.5 shrink-0 hover:ring-bat-line-strong transition-all duration-200 ease-soft"
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: e.color || '#eab308' }} />
                <span className="text-ink-muted truncate max-w-[140px]">{e.title}</span>
                <span className="text-ink-faint font-mono text-[9px]">
                  {new Date(e.start_time).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                </span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md"
          onClick={() => { if (form.title.trim() && !confirm('Discard unsaved changes?')) return; closeForm(); }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={editEvent ? 'Edit event' : 'New event'}
            className="w-full max-w-md rounded-card bg-gradient-to-b from-bat-surface to-bat-bg
              ring-1 ring-bat-line-strong shadow-lift animate-rise-in"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-white/[0.04]">
              <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted">
                {editEvent ? 'Edit event' : 'New event'}
              </h2>
              <button type="button" onClick={closeForm} aria-label="Close"
                className="text-ink-faint hover:text-ink transition-colors duration-200">
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-5 space-y-3.5 text-xs">
              {error && (
                <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late">
                  {error}
                </div>
              )}

              <Field label="What is it">
                <input type="text" value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="Dentist" className={fieldClass} required autoFocus />
              </Field>

              <Field label="Description">
                <textarea value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Anything you'll want at the time."
                  className={`${fieldClass} h-16 resize-none`} />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Starts">
                  <input type="datetime-local" value={form.start_time}
                    onChange={e => setForm({ ...form, start_time: e.target.value })}
                    className={`${fieldClass} font-mono text-[11px]`} required />
                </Field>
                <Field label="Ends" hint="Leave empty for a moment rather than a block.">
                  <input type="datetime-local" value={form.end_time}
                    onChange={e => setForm({ ...form, end_time: e.target.value })}
                    className={`${fieldClass} font-mono text-[11px]`} />
                </Field>
              </div>

              <Field label="Colour">
                <input type="color" value={form.color}
                  onChange={e => setForm({ ...form, color: e.target.value })}
                  className="w-full h-8 rounded-chip bg-bat-raised ring-1 ring-bat-line cursor-pointer" />
              </Field>

              <div className="flex items-center gap-3 pt-1">
                <Button type="submit" tone="self" disabled={loading} className="flex-1 py-2.5">
                  {loading ? 'Saving...' : editEvent ? 'Save changes' : 'Add event'}
                </Button>
                {/* There was no delete anywhere in the UI. */}
                {editEvent && (
                  <IconButton
                    label={`Delete "${editEvent.title}"`}
                    icon={Trash2}
                    tone="danger"
                    onClick={() => handleDelete(editEvent)}
                  />
                )}
                <button type="button" onClick={closeForm}
                  className="text-[10px] font-mono uppercase tracking-widest text-ink-faint hover:text-ink-muted transition-colors duration-200 px-2">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {flash && (
        <div role="status"
          className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] animate-rise-in
            rounded-chip bg-bat-raised ring-1 ring-bat-line-strong shadow-lift
            px-4 py-2 text-[11px] text-ink-muted max-w-[90vw] truncate">
          {flash}
        </div>
      )}
    </div>
  );
}

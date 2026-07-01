import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { api } from '../utils/api';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

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

export default function CalendarPanel() {
  const [events, setEvents] = useState([]);
  const [missions, setMissions] = useState([]);
  const [today] = useState(() => new Date());
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [showForm, setShowForm] = useState(false);
  const [editEvent, setEditEvent] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', start_time: '', end_time: '', color: '#eab308' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getCalendarEvents().then(data => { if (!cancelled) setEvents(data); }).catch(() => {});
    api.getMissions().then(data => { if (!cancelled) setMissions(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const refreshEvents = useCallback(() => api.getCalendarEvents().then(setEvents), []);

  const days = useMemo(() => getMonthDays(year, month), [year, month]);

  const missionDueMap = useMemo(() => {
    const map = {};
    missions.forEach(m => {
      if (m.due_date && m.status !== 'completed') {
        const key = new Date(m.due_date).toDateString();
        if (!map[key]) map[key] = [];
        map[key].push(m);
      }
    });
    return map;
  }, [missions]);

  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [events]);

  const openAddForm = useCallback((date) => {
    setEditEvent(null);
    setSelectedDate(date);
    setForm({ title: '', description: '', start_time: toLocalDatetimeString(date), end_time: '', color: '#eab308' });
    setShowForm(true);
  }, []);

  const openEditForm = useCallback((event) => {
    setEditEvent(event);
    setSelectedDate(null);
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
    setLoading(true);
    try {
      const payload = {
        title: form.title,
        description: form.description.trim() || null,
        start_time: new Date(form.start_time).toISOString(),
        end_time: form.end_time ? new Date(form.end_time).toISOString() : null,
        color: form.color,
      };
      if (editEvent) {
        await api.updateCalendarEvent(editEvent.id, payload);
      } else {
        await api.createCalendarEvent(payload);
      }
      setShowForm(false);
      setEditEvent(null);
      await refreshEvents();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this event?')) return;
    try {
      await api.deleteCalendarEvent(id);
      await refreshEvents();
    } catch (err) { console.error(err); }
  };

  const isToday = (d) => d && d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth() && d.getDate() === today.getDate();
  const isCurrentMonth = (d) => d && d.getMonth() === month;
  const getEventsForDay = (d) => events.filter(e => new Date(e.start_time).toDateString() === d.toDateString());
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

  const now = new Date();
  const isCurrentMonthView = year === today.getFullYear() && month === today.getMonth();

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="shrink-0 flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-wider">CALENDAR</h1>
        <button onClick={() => { setEditEvent(null); setForm({ title: '', description: '', start_time: toLocalDatetimeString(now), end_time: '', color: '#eab308' }); setShowForm(true); }} className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono text-xs tracking-widest">
          + EVENT
        </button>
      </div>

      <div className="flex-1 min-h-0 bg-dark-slate rounded border border-slate-800 flex flex-col overflow-hidden">
        <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-slate-800">
          <button onClick={prevMonth} className="text-slate-400 hover:text-slate-200 text-sm font-mono px-2 py-1">&larr;</button>
          <div className="flex items-center gap-4">
            <h2 className="text-base font-bold tracking-wider text-slate-200">{MONTHS[month]} {year}</h2>
            {!isCurrentMonthView && (
              <button onClick={goToToday} className="text-xs font-mono text-electric-bat-yellow hover:text-yellow-400 underline underline-offset-2">Today</button>
            )}
          </div>
          <button onClick={nextMonth} className="text-slate-400 hover:text-slate-200 text-sm font-mono px-2 py-1">&rarr;</button>
        </div>

        <div className="shrink-0 grid grid-cols-7 text-center border-b border-slate-800">
          {DAYS.map(d => <div key={d} className="text-xs font-mono text-slate-500 py-2">{d}</div>)}
        </div>

        <div className="flex-1 grid grid-cols-7 auto-rows-fr">
          {days.map((d, i) => (
            <div key={i}
              className={`border-b border-r border-slate-800 p-2 ${d ? 'cursor-pointer hover:bg-slate-800/50 transition' : ''} ${isToday(d) ? 'bg-yellow-900/10' : ''} ${!d ? 'bg-slate-900/30' : ''}`}
              onClick={() => d && openAddForm(d)}
            >
              {d && (
                <div className="h-full flex flex-col">
                  <div className={`text-sm font-mono mb-1 leading-none ${isToday(d) ? 'text-electric-bat-yellow font-bold' : isCurrentMonth(d) ? 'text-slate-300' : 'text-slate-600'}`}>
                    {d.getDate()}
                  </div>
                  <div className="flex-1 space-y-[2px] overflow-hidden">
                    {getMissionsForDay(d).slice(0, 4).map(m => (
                      <div key={m.id} className="text-[10px] bg-red-950/40 text-red-400 px-1.5 py-0.5 rounded truncate leading-tight">{m.title}</div>
                    ))}
                    {getEventsForDay(d).slice(0, 4).map(evt => (
                      <div key={evt.id} onClick={evtClick => { evtClick.stopPropagation(); openEditForm(evt); }} className="text-[10px] px-1.5 py-0.5 rounded truncate leading-tight cursor-pointer hover:opacity-80"
                        style={{ backgroundColor: evt.color + '30', color: evt.color }}>
                        {evt.title}
                      </div>
                    ))}
                    {(getMissionsForDay(d).length + getEventsForDay(d).length) > 8 && (
                      <div className="text-[10px] text-slate-500">+{getMissionsForDay(d).length + getEventsForDay(d).length - 8} more</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="shrink-0 bg-dark-slate px-4 py-2.5 rounded border border-slate-800 flex items-center gap-4 overflow-x-auto">
        <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 shrink-0">Upcoming</span>
        {sortedEvents.length === 0 ? (
          <span className="text-xs text-slate-500 italic shrink-0">No scheduled events.</span>
        ) : (
          sortedEvents.slice(0, 6).map(e => (
            <div key={e.id} className="flex items-center gap-1.5 text-xs bg-matte-obsidian px-2 py-1 rounded border border-slate-700 shrink-0 hover:border-slate-600 transition cursor-pointer"
              onClick={() => openEditForm(e)}>
              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: e.color }} />
              <span className="text-slate-300 truncate max-w-[120px]">{e.title}</span>
              <span className="text-slate-500 font-mono text-[9px]">{new Date(e.start_time).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
            </div>
          ))
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => { if (form.title.trim() && !confirm('Discard unsaved changes?')) return; setShowForm(false); setEditEvent(null); }}>
          <div className="bg-dark-slate rounded border border-slate-700 p-5 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              {editEvent ? 'Edit Event' : 'New Event'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-mono text-[10px]">Title</label>
                <input type="text" value={form.title} onChange={e => setForm({...form, title: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-electric-bat-yellow" required />
              </div>
              <div>
                <label className="block text-slate-400 mb-1 font-mono text-[10px]">Description</label>
                <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-electric-bat-yellow h-16 resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1 font-mono text-[10px]">Start</label>
                  <input type="datetime-local" value={form.start_time} onChange={e => setForm({...form, start_time: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-electric-bat-yellow font-mono text-[10px]" required />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1 font-mono text-[10px]">End</label>
                  <input type="datetime-local" value={form.end_time} onChange={e => setForm({...form, end_time: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-electric-bat-yellow font-mono text-[10px]" />
                </div>
              </div>
              <div>
                <label className="block text-slate-400 mb-1 font-mono text-[10px]">Color</label>
                <input type="color" value={form.color} onChange={e => setForm({...form, color: e.target.value})} className="w-full h-8 bg-matte-obsidian border border-slate-800 rounded cursor-pointer" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={loading} className="flex-1 py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono tracking-widest disabled:opacity-50">
                  {loading ? 'SAVING...' : editEvent ? 'UPDATE' : 'CREATE'}
                </button>
                <button type="button" onClick={() => { setShowForm(false); setEditEvent(null); }} className="px-4 py-2.5 bg-slate-800 text-slate-300 rounded hover:bg-slate-700 transition font-mono text-[10px]">
                  CANCEL
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

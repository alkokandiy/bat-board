import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

function getMonthDays(year, month) {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const startDay = first.getDay();
  const days = [];
  for (let i = 0; i < startDay; i++) days.push(null);
  for (let d = 1; d <= last.getDate(); d++) days.push(new Date(year, month, d));
  while (days.length % 7 !== 0) days.push(null);
  return days;
}

export default function CalendarPanel() {
  const [events, setEvents] = useState([]);
  const [missions, setMissions] = useState([]);
  const [now] = useState(() => new Date());
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());
  const getToday = () => new Date();
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

  const refreshEvents = () => api.getCalendarEvents().then(setEvents);

  const days = getMonthDays(year, month);
  const missionDueMap = {};
  missions.forEach(m => {
    if (m.due_date && m.status !== 'completed') {
      const key = new Date(m.due_date).toDateString();
      if (!missionDueMap[key]) missionDueMap[key] = [];
      missionDueMap[key].push(m);
    }
  });

  const openAddForm = (date) => {
    setEditEvent(null);
    setSelectedDate(date);
    const local = new Date(date);
    local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
    const iso = local.toISOString().slice(0, 16);
    setForm({ title: '', description: '', start_time: iso, end_time: '', color: '#eab308' });
    setShowForm(true);
  };

  const openEditForm = (event) => {
    setEditEvent(event);
    setSelectedDate(null);
    const start = new Date(event.start_time);
    start.setMinutes(start.getMinutes() - start.getTimezoneOffset());
    const end = event.end_time ? new Date(event.end_time) : null;
    if (end) end.setMinutes(end.getMinutes() - end.getTimezoneOffset());
    setForm({
      title: event.title,
      description: event.description || '',
      start_time: start.toISOString().slice(0, 16),
      end_time: end ? end.toISOString().slice(0, 16) : '',
      color: event.color || '#eab308',
    });
    setShowForm(true);
  };

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

  const isToday = (d) => d && d.toDateString() === getToday().toDateString();
  const getEventsForDay = (d) => events.filter(e => new Date(e.start_time).toDateString() === d.toDateString());
  const getMissionsForDay = (d) => missionDueMap[d.toDateString()] || [];

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-wider">CALENDAR</h1>
          <p className="text-xs text-slate-400">Mission deadlines and scheduled events at a glance.</p>
        </div>
        <button onClick={() => { setEditEvent(null); setForm({ title: '', description: '', start_time: '', end_time: '', color: '#eab308' }); setShowForm(true); }} className="px-3 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono text-[10px] tracking-widest">
          + EVENT
        </button>
      </div>

      <div className="bg-dark-slate rounded border border-slate-800 overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-slate-800">
          <button onClick={() => { if (month === 0) { setYear(y => y - 1); setMonth(11); } else { setMonth(m => m - 1); } }} className="text-slate-400 hover:text-slate-200 text-xs font-mono px-2">&lt; Prev</button>
          <h2 className="text-sm font-bold tracking-wider text-slate-200">{MONTHS[month]} {year}</h2>
          <button onClick={() => { if (month === 11) { setYear(y => y + 1); setMonth(0); } else { setMonth(m => m + 1); } }} className="text-slate-400 hover:text-slate-200 text-xs font-mono px-2">Next &gt;</button>
        </div>

        <div className="grid grid-cols-7 text-center">
          {DAYS.map(d => <div key={d} className="text-[10px] font-mono text-slate-500 py-2 border-b border-slate-800">{d}</div>)}
          {days.map((d, i) => (
            <div key={i} className={`min-h-[80px] border-b border-r border-slate-800 p-1 ${d ? 'cursor-pointer hover:bg-slate-800/50 transition' : ''} ${isToday(d) ? 'bg-yellow-900/10' : ''}`}
              onClick={() => d && openAddForm(d)}
            >
              {d && (
                <>
                  <div className={`text-[10px] font-mono mb-1 ${isToday(d) ? 'text-electric-bat-yellow font-bold' : 'text-slate-400'}`}>
                    {d.getDate()}
                  </div>
                  {getMissionsForDay(d).slice(0, 2).map(m => (
                    <div key={m.id} className="text-[7px] bg-red-950/40 text-red-400 px-1 py-0.5 rounded truncate mb-0.5 leading-tight">{m.title}</div>
                  ))}
                  {getEventsForDay(d).slice(0, 2).map(evt => (
                    <div key={evt.id} onClick={evtClick => { evtClick.stopPropagation(); openEditForm(evt); }} className="text-[7px] px-1 py-0.5 rounded truncate mb-0.5 leading-tight cursor-pointer hover:opacity-80"
                      style={{ backgroundColor: evt.color + '30', color: evt.color }}>
                      {evt.title}
                    </div>
                  ))}
                  {(getMissionsForDay(d).length + getEventsForDay(d).length) > 3 && (
                    <div className="text-[7px] text-slate-500">+{getMissionsForDay(d).length + getEventsForDay(d).length - 3} more</div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-dark-slate p-4 rounded border border-slate-800 space-y-3">
        <h2 className="text-xs font-mono uppercase tracking-widest text-slate-300">Upcoming Events</h2>
        {events.length === 0 ? (
          <div className="text-xs text-slate-500 italic">No scheduled events.</div>
        ) : (
          <div className="space-y-2">
            {events.sort((a, b) => new Date(a.start_time) - new Date(b.start_time)).slice(0, 10).map(e => (
              <div key={e.id} className="flex items-center justify-between text-xs bg-matte-obsidian p-2 rounded border border-slate-800">
                <div className="flex items-center space-x-2 min-w-0">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: e.color }} />
                  <span className="text-slate-200 truncate">{e.title}</span>
                  <span className="text-slate-500 font-mono text-[10px]">{new Date(e.start_time).toLocaleDateString()} {new Date(e.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <button onClick={() => openEditForm(e)} className="text-slate-600 hover:text-slate-300 text-[10px]">✎</button>
                  <button onClick={() => handleDelete(e.id)} className="text-slate-600 hover:text-red-500 text-[10px]">✕</button>
                </div>
              </div>
            ))}
          </div>
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
              <div className="flex space-x-3 pt-2">
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

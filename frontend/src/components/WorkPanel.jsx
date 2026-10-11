import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Briefcase, Plus, Trash2, Check, BookOpen, FileText } from 'lucide-react';
import { api } from '../utils/api';

// The work side is deliberately steel-coloured, never bat-yellow: yellow is the
// points ledger, and work earns none. That is a design rule, not decoration.
const STATUS_META = {
  todo: { label: 'To do', tone: 'text-slate-300', box: 'border-slate-800' },
  doing: { label: 'In hand', tone: 'text-sky-300', box: 'border-sky-900/40' },
  blocked: { label: 'Blocked', tone: 'text-amber-300', box: 'border-amber-900/40' },
  done: { label: 'Done', tone: 'text-emerald-300', box: 'border-emerald-900/40' },
};
const OPEN_STATUSES = ['todo', 'doing', 'blocked'];
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const PERIODS = [
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'This week' },
  { id: 'month', label: 'This month' },
];
const NOTE_KINDS = [
  { id: 'note', label: 'Note' },
  { id: 'learning', label: 'Learned' },
  { id: 'reflection', label: 'Reflection' },
];

function fmtHm(mins) {
  const m = Math.max(0, Math.round(mins || 0));
  const h = Math.floor(m / 60);
  const rem = m % 60;
  if (h && rem) return `${h}h ${rem}m`;
  return h ? `${h}h` : `${rem}m`;
}

function fmtDate(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}

/* --- setup ---------------------------------------------------------------- */
// One screen, one Save. Days and hours are the only things the rest of the
// system actually needs, so nothing else is asked for up front.
function SetupCard({ status, onSaved }) {
  const profile = status.profile || {};
  const initialDays = useMemo(
    () => new Set(String(profile.work_days || '').split(',').filter(Boolean).map(Number)),
    [profile.work_days],
  );
  const [days, setDays] = useState(initialDays);
  const [start, setStart] = useState(profile.work_start || '09:00');
  const [end, setEnd] = useState(profile.work_end || '18:00');
  const [employer, setEmployer] = useState(profile.employer || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const toggleDay = (i) => {
    setDays((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const save = async () => {
    if (days.size === 0) { setError('Pick at least one working day.'); return; }
    setSaving(true);
    setError(null);
    try {
      await api.updateWorkProfile({
        work_days: [...days].sort((a, b) => a - b).join(','),
        work_start: start,
        work_end: end,
        employer: employer.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-dark-slate rounded border border-sky-900/40 p-5 space-y-4">
      <div>
        <h2 className="text-sm font-mono uppercase tracking-widest text-sky-300">Set up your work</h2>
        <p className="text-xs text-slate-400 mt-1">
          Your days and hours are all this needs. They let the reports say
          &ldquo;32h of about 40 expected&rdquo; instead of a bare number — and stop Alfred
          asking whether you&rsquo;re drifting at 3pm on a working Tuesday.
        </p>
      </div>

      <div className="space-y-2">
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Working days</div>
        <div className="flex flex-wrap gap-2">
          {WEEKDAYS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => toggleDay(i)}
              className={`px-3 py-1.5 rounded text-xs font-mono border transition ${
                days.has(i)
                  ? 'bg-sky-900/40 border-sky-700 text-sky-200'
                  : 'bg-matte-obsidian border-slate-800 text-slate-500 hover:border-slate-600'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">From</span>
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="mt-1 w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-600"
          />
        </label>
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">To</span>
          <input
            type="time"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="mt-1 w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-600"
          />
        </label>
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Employer (optional)</span>
          <input
            type="text"
            value={employer}
            onChange={(e) => setEmployer(e.target.value)}
            placeholder="Wayne Enterprises"
            className="mt-1 w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
          />
        </label>
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-sky-700 hover:bg-sky-600 text-slate-50 text-xs font-bold rounded font-mono tracking-wider disabled:opacity-50"
        >
          {saving ? 'SAVING...' : 'SAVE SCHEDULE'}
        </button>
        <span className="text-[10px] text-slate-500">
          Or just tell Alfred &mdash; &ldquo;set up work&rdquo; does the same thing.
        </span>
      </div>
    </div>
  );
}

/* --- task card ------------------------------------------------------------ */

function TaskCard({ task, onMove, onComplete, onDelete, busy }) {
  const meta = STATUS_META[task.status] || STATUS_META.todo;
  return (
    <div className={`bg-matte-obsidian rounded border ${meta.box} p-3 space-y-2`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className={`text-sm ${task.status === 'done' ? 'text-slate-500 line-through' : 'text-slate-200'}`}>
            {task.title}
          </div>
          {task.detail && <div className="text-[11px] text-slate-500 mt-0.5">{task.detail}</div>}
          <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[10px] font-mono text-slate-500">
            {task.project && (
              <span className="px-1.5 py-0.5 rounded bg-dark-slate border border-slate-800 text-slate-400">
                {task.project}
              </span>
            )}
            {task.due_date && <span>due {fmtDate(task.due_date)}</span>}
            {task.focus_minutes > 0 && <span>⏱ {fmtHm(task.focus_minutes)}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {task.status !== 'done' && (
            <button
              onClick={() => onComplete(task)}
              disabled={busy}
              title="Mark done (no Bat Points — this is the job)"
              className="p-1.5 rounded border border-slate-800 text-slate-500 hover:text-emerald-300 hover:border-emerald-900/60 transition disabled:opacity-40"
            >
              <Check size={13} />
            </button>
          )}
          <button
            onClick={() => onDelete(task)}
            disabled={busy}
            title="Delete"
            className="p-1.5 rounded border border-slate-800 text-slate-500 hover:text-red-400 hover:border-red-900/60 transition disabled:opacity-40"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
      <select
        value={task.status}
        onChange={(e) => onMove(task, e.target.value)}
        disabled={busy}
        className="w-full bg-dark-slate border border-slate-800 rounded px-2 py-1 text-[11px] font-mono text-slate-300 focus:outline-none focus:border-sky-600 disabled:opacity-40"
      >
        {Object.entries(STATUS_META).map(([id, m]) => (
          <option key={id} value={id}>{m.label}</option>
        ))}
      </select>
    </div>
  );
}

/* --- report --------------------------------------------------------------- */

function ReportCard({ onSavedReflection }) {
  const [period, setPeriod] = useState('today');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reflection, setReflection] = useState('');
  const [saved, setSaved] = useState(false);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      setReport(await api.getWorkReport(p));
    } catch (err) {
      setError(err.message);
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  const saveReflection = async () => {
    if (!reflection.trim()) return;
    try {
      await api.createWorkNote({ content: reflection.trim(), kind: 'reflection' });
      setReflection('');
      setSaved(true);
      onSavedReflection?.();
      load(period);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="bg-dark-slate rounded border border-slate-800 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-2">
        <h2 className="text-xs font-mono uppercase tracking-widest text-slate-300 flex items-center gap-2">
          <FileText size={13} /> Report
        </h2>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => { setPeriod(p.id); setSaved(false); }}
              className={`px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider border transition ${
                period === p.id
                  ? 'bg-sky-900/40 border-sky-700 text-sky-200'
                  : 'border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-xs text-slate-500">Reading the ledger...</div>}
      {error && <div className="text-xs text-red-400">{error}</div>}

      {report && !loading && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { label: 'Finished', value: report.completed.length },
              { label: 'Logged', value: fmtHm(report.minutes) },
              {
                label: 'Days worked',
                value: report.expected_days
                  ? `${report.work_days}/${report.expected_days}`
                  : report.work_days,
              },
              { label: 'Still open', value: report.open_total },
            ].map((s) => (
              <div key={s.label} className="bg-matte-obsidian rounded border border-slate-800 p-2.5">
                <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500">{s.label}</div>
                <div className="text-lg font-bold text-slate-200 mt-0.5">{s.value}</div>
              </div>
            ))}
          </div>

          {report.expected_minutes > 0 && (
            <div className="text-[11px] text-slate-400 font-mono">
              {fmtHm(report.minutes)} of about {fmtHm(report.expected_minutes)} expected.
            </div>
          )}

          <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-sans leading-relaxed bg-matte-obsidian rounded border border-slate-800 p-3">
            {report.text}
          </pre>

          {/* The report ends in a question on purpose; this is where it gets answered. */}
          <div className="space-y-2">
            <textarea
              value={reflection}
              onChange={(e) => { setReflection(e.target.value); setSaved(false); }}
              rows={2}
              placeholder="Your answer — kept in the work journal, and it shows up in the month's report."
              className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={saveReflection}
                disabled={!reflection.trim()}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-mono tracking-wider rounded disabled:opacity-40"
              >
                SAVE REFLECTION
              </button>
              {saved && <span className="text-[10px] text-emerald-400">Kept.</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* --- journal -------------------------------------------------------------- */

function JournalCard({ notes, onAdded }) {
  const [content, setContent] = useState('');
  const [kind, setKind] = useState('note');
  const [error, setError] = useState(null);

  const add = async (e) => {
    e.preventDefault();
    if (!content.trim()) return;
    try {
      await api.createWorkNote({ content: content.trim(), kind });
      setContent('');
      setError(null);
      onAdded();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="bg-dark-slate rounded border border-slate-800 p-4 space-y-3">
      <h2 className="text-xs font-mono uppercase tracking-widest text-slate-300 flex items-center gap-2 border-b border-slate-800 pb-2">
        <BookOpen size={13} /> Work journal
      </h2>
      <form onSubmit={add} className="space-y-2">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={2}
          placeholder="Something learned, something worth remembering about the job."
          className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
        />
        <div className="flex items-center gap-2">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-[11px] font-mono text-slate-300 focus:outline-none focus:border-sky-600"
          >
            {NOTE_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
          <button
            type="submit"
            aria-label="Add journal entry"
            disabled={!content.trim()}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-mono tracking-wider rounded disabled:opacity-40"
          >
            ADD
          </button>
        </div>
        {error && <div className="text-xs text-red-400">{error}</div>}
      </form>

      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
        {notes.length === 0 ? (
          <div className="text-[11px] text-slate-600 italic">Nothing in the journal yet.</div>
        ) : notes.map((n) => (
          <div key={n.id} className="bg-matte-obsidian rounded border border-slate-800 p-2.5">
            <div className="flex items-center justify-between gap-2 text-[9px] font-mono uppercase tracking-wider text-slate-500">
              <span className={n.kind === 'learning' ? 'text-sky-400' : n.kind === 'reflection' ? 'text-amber-400' : ''}>
                {n.kind}
              </span>
              <span>{fmtDate(n.created_at)}</span>
            </div>
            <div className="text-xs text-slate-300 mt-1 whitespace-pre-wrap">{n.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* --- the panel ------------------------------------------------------------ */

export default function WorkPanel({ onStatusChange }) {
  const [status, setStatus] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [showDone, setShowDone] = useState(false);
  const [title, setTitle] = useState('');
  const [project, setProject] = useState('');
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const st = await api.getWorkStatus();
      setStatus(st);
      onStatusChange?.(st);
      if (!st.enabled) { setTasks([]); setNotes([]); return; }
      const [t, n] = await Promise.all([api.getWorkTasks(true), api.getWorkNotes()]);
      setTasks(t);
      setNotes(n);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [onStatusChange]);

  useEffect(() => { load(); }, [load]);

  const addTask = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setAdding(true);
    try {
      const created = await api.createWorkTask({
        title: title.trim(),
        project: project.trim() || null,
      });
      setTasks((prev) => [...prev, created]);
      setTitle('');
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setAdding(false);
    }
  };

  // Each mutation replaces just its own row, so the board never flashes.
  const withTask = async (task, fn) => {
    setBusyId(task.id);
    try {
      const updated = await fn();
      setTasks((prev) => (updated
        ? prev.map((t) => (t.id === task.id ? updated : t))
        : prev.filter((t) => t.id !== task.id)));
      setError(null);
    } catch (err) {
      setError(err.message);
      load();
    } finally {
      setBusyId(null);
    }
  };

  const moveTask = (task, status_) => withTask(task, () => api.updateWorkTask(task.id, { status: status_ }));
  const completeTask = (task) => withTask(task, () => api.completeWorkTask(task.id));
  const deleteTask = (task) => {
    if (!window.confirm(`Delete work task "${task.title}"?`)) return;
    return withTask(task, async () => { await api.deleteWorkTask(task.id); return null; });
  };

  if (loading) {
    return <div className="text-xs text-slate-500 font-mono">LOADING WORK LEDGER...</div>;
  }

  // The panel is only reachable while the track is on; if it was switched off
  // in another tab, say so plainly rather than rendering an empty board.
  if (status && !status.enabled) {
    return (
      <div className="bg-dark-slate rounded border border-slate-800 p-6 text-center space-y-2">
        <div className="text-sm text-slate-300">The work track is switched off.</div>
        <div className="text-xs text-slate-500">
          Turn it back on in Profile &rarr; Work track. Nothing of yours was deleted.
        </div>
      </div>
    );
  }

  const columns = showDone ? [...OPEN_STATUSES, 'done'] : OPEN_STATUSES;
  const profile = status?.profile || {};
  const scheduleLine = [
    profile.employer,
    profile.role,
    profile.work_days_label && profile.work_start && profile.work_end
      ? `${profile.work_days_label} · ${profile.work_start}–${profile.work_end}`
      : null,
  ].filter(Boolean).join(' · ');

  return (
    <div className="h-full flex flex-col min-h-0 space-y-5">
      <div className="border-l-4 border-sky-700 pl-4 py-1 shrink-0">
        <h1 className="text-2xl font-bold tracking-wider flex items-center gap-2">
          <Briefcase size={20} className="text-sky-400" /> CORPORATE TRACK
        </h1>
        <p className="text-xs text-slate-400">
          {scheduleLine || 'The job, kept apart from your missions.'}
        </p>
        <p className="text-[10px] text-slate-600 font-mono mt-0.5">
          NO BAT POINTS — BY DESIGN. POINTS MEASURE YOU, NOT THE JOB.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs shrink-0">{error}</div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto space-y-5 pr-1">
        {status && !status.configured && <SetupCard status={status} onSaved={load} />}

        <form onSubmit={addTask} className="bg-dark-slate rounded border border-slate-800 p-4 flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What does the job need? (Enter to add)"
            className="flex-1 bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
          />
          <input
            type="text"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="Project (optional)"
            className="sm:w-44 bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
          />
          <button
            type="submit"
            aria-label="Add work task"
            disabled={adding || !title.trim()}
            className="px-4 py-2 bg-sky-700 hover:bg-sky-600 text-slate-50 text-xs font-bold rounded font-mono tracking-wider flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <Plus size={14} /> ADD
          </button>
        </form>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Board</div>
            <button
              onClick={() => setShowDone((v) => !v)}
              className="text-[10px] font-mono uppercase tracking-wider text-slate-500 hover:text-slate-300"
            >
              {showDone ? 'HIDE DONE' : 'SHOW DONE'}
            </button>
          </div>
          <div className={`grid grid-cols-1 gap-3 ${showDone ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}>
            {columns.map((s) => {
              const meta = STATUS_META[s];
              const items = tasks.filter((t) => t.status === s);
              return (
                <div key={s} className={`bg-dark-slate rounded border ${meta.box} p-3 space-y-2`}>
                  <div className={`text-[10px] font-mono uppercase tracking-widest ${meta.tone} border-b border-slate-800 pb-1`}>
                    {meta.label} <span className="text-slate-500">({items.length})</span>
                  </div>
                  {items.length === 0 ? (
                    <div className="text-[10px] text-slate-600 italic">Nothing here</div>
                  ) : items.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      busy={busyId === t.id}
                      onMove={moveTask}
                      onComplete={completeTask}
                      onDelete={deleteTask}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ReportCard onSavedReflection={load} />
          <JournalCard notes={notes} onAdded={load} />
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Briefcase, Plus, Trash2, Check, BookOpen, FileText, Clock } from 'lucide-react';
import { PageHeader, Panel, EmptyState, Button, Field, fieldClass } from './ui';
import { api } from '../utils/api';

// The work side is deliberately steel-coloured, never bat-yellow: yellow is the
// points ledger, and work earns none. That is a design rule, not decoration.
// Cyan is to the work track what bat-yellow is to the personal board: the one
// accent, used consistently, so the two sides are told apart at a glance
// rather than the work side merely looking unfinished. Work still earns no
// Bat Points — that is the reason it is never yellow.
const STATUS_META = {
  todo: {
    label: 'To do', tone: 'text-ink-muted', box: 'border-bat-line',
    rail: 'bg-bat-line-strong', head: 'text-ink-muted border-bat-line',
  },
  doing: {
    label: 'In hand', tone: 'text-signal-work', box: 'border-signal-work/30',
    rail: 'bg-signal-work', head: 'text-signal-work border-signal-work/30',
  },
  blocked: {
    label: 'Blocked', tone: 'text-signal-warn', box: 'border-signal-warn/30',
    rail: 'bg-signal-warn', head: 'text-signal-warn border-signal-warn/30',
  },
  done: {
    label: 'Done', tone: 'text-signal-good', box: 'border-signal-good/30',
    rail: 'bg-signal-good', head: 'text-signal-good border-signal-good/30',
  },
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
    <div className="bg-bat-surface rounded border border-signal-work/30 p-5 space-y-4">
      <div>
        <h2 className="text-sm font-mono uppercase tracking-widest text-signal-work">Set up your work</h2>
        <p className="text-xs text-ink-muted mt-1">
          Your days and hours are all this needs. They let the reports say
          &ldquo;32h of about 40 expected&rdquo; instead of a bare number — and stop Alfred
          asking whether you&rsquo;re drifting at 3pm on a working Tuesday.
        </p>
      </div>

      <div className="space-y-2">
        <div className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">Working days</div>
        <div className="flex flex-wrap gap-2">
          {WEEKDAYS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => toggleDay(i)}
              className={`px-3 py-1.5 rounded text-xs font-mono border transition ${
                days.has(i)
                  ? 'bg-signal-work/10 border-signal-work/40 text-signal-work'
                  : 'bg-bat-raised border-bat-line text-ink-faint hover:border-bat-line-strong'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">From</span>
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="mt-1 w-full bg-bat-raised border border-bat-line rounded px-3 py-2 text-sm text-ink focus:outline-none focus:border-signal-work"
          />
        </label>
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">To</span>
          <input
            type="time"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="mt-1 w-full bg-bat-raised border border-bat-line rounded px-3 py-2 text-sm text-ink focus:outline-none focus:border-signal-work"
          />
        </label>
        <label className="block">
          <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">Employer (optional)</span>
          <input
            type="text"
            value={employer}
            onChange={(e) => setEmployer(e.target.value)}
            placeholder="Wayne Enterprises"
            className="mt-1 w-full bg-bat-raised border border-bat-line rounded px-3 py-2 text-sm text-ink placeholder-ink-faint focus:outline-none focus:border-signal-work"
          />
        </label>
      </div>

      {error && <div className="text-xs text-signal-late">{error}</div>}

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-signal-work hover:brightness-110 text-bat-bg text-xs font-bold rounded font-mono tracking-wider disabled:opacity-50"
        >
          {saving ? 'SAVING...' : 'SAVE SCHEDULE'}
        </button>
        <span className="text-[10px] text-ink-faint">
          Or just tell Alfred &mdash; &ldquo;set up work&rdquo; does the same thing.
        </span>
      </div>
    </div>
  );
}

/* --- task card ------------------------------------------------------------ */

function TaskCard({ task, onMove, onComplete, onDelete, onLogHours, busy }) {
  const meta = STATUS_META[task.status] || STATUS_META.todo;
  const [logging, setLogging] = useState(false);
  const [hours, setHours] = useState('');

  // Hours could only be recorded by asking Alfred, and before the tool
  // existed that produced a work NOTE claiming time the report read as zero.
  const submitHours = (e) => {
    e.preventDefault();
    const h = parseFloat(hours);
    if (!h || h <= 0) return;
    onLogHours(task, Math.round(h * 60));
    setHours('');
    setLogging(false);
  };
  return (
    <div className={`relative bg-bat-raised rounded border ${meta.box} p-3 pl-4 space-y-2 overflow-hidden`}>
      {/* The status is readable from the edge of the card, before reading a word. */}
      <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${meta.rail}`} aria-hidden="true" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className={`text-sm ${task.status === 'done' ? 'text-ink-faint line-through' : 'text-ink'}`}>
            {task.title}
          </div>
          {task.detail && <div className="text-[11px] text-ink-faint mt-0.5">{task.detail}</div>}
          <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[10px] font-mono text-ink-faint">
            {task.project && (
              <span className="px-1.5 py-0.5 rounded bg-bat-surface border border-bat-line text-ink-muted">
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
              className="p-1.5 rounded border border-bat-line text-ink-faint hover:text-signal-good hover:border-signal-good/40 transition disabled:opacity-40"
            >
              <Check size={13} />
            </button>
          )}
          <button
            onClick={() => setLogging((v) => !v)}
            disabled={busy}
            title="Log hours already spent on this"
            aria-label={`Log hours for ${task.title}`}
            className="p-1.5 rounded border border-bat-line text-ink-faint hover:text-signal-work hover:border-signal-work/60 transition disabled:opacity-40"
          >
            <Clock size={13} />
          </button>
          <button
            onClick={() => onDelete(task)}
            disabled={busy}
            title="Delete"
            className="p-1.5 rounded border border-bat-line text-ink-faint hover:text-signal-late hover:border-signal-late/40 transition disabled:opacity-40"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
      {logging && (
        <form onSubmit={submitHours} className="flex items-center gap-2 pt-0.5">
          <input
            type="number" step="0.25" min="0.25" max="16" autoFocus
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            placeholder="hours"
            aria-label="Hours already spent"
            className="w-20 bg-bat-raised border border-bat-line rounded px-2 py-1 text-[11px] font-mono text-ink focus:outline-none focus:border-signal-work"
          />
          <button type="submit" disabled={busy}
            className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border border-signal-work/60 text-signal-work hover:bg-signal-work/10 transition disabled:opacity-40">
            Log
          </button>
          <span className="text-[10px] text-ink-faint">ending now</span>
        </form>
      )}

      {/* One tap to move a task, instead of opening a select on every card.
          The current column is marked rather than offered again. */}
      <div className="flex flex-wrap gap-1 pt-0.5">
        {OPEN_STATUSES.map((id) => {
          const m = STATUS_META[id];
          const active = task.status === id;
          return (
            <button
              key={id}
              onClick={() => !active && onMove(task, id)}
              disabled={busy || active}
              aria-current={active ? 'true' : undefined}
              className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border transition
                ${active
                  ? `${m.tone} ${m.box} bg-bat-surface cursor-default`
                  : 'text-ink-faint border-bat-line hover:text-ink-muted hover:border-bat-line-strong'}
                disabled:opacity-100`}
            >
              {m.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* --- report --------------------------------------------------------------- */

function ReportCard({ onSavedReflection, refreshKey = 0 }) {
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

  // refreshKey changes when hours are logged elsewhere on this screen,
  // so the figures do not sit stale at 0m behind a fresh entry.
  useEffect(() => { load(period); }, [load, period, refreshKey]);

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
    <div className="bg-bat-surface rounded border border-bat-line p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 border-b border-bat-line pb-2">
        <h2 className="text-xs font-mono uppercase tracking-widest text-ink-muted flex items-center gap-2">
          <FileText size={13} /> Report
        </h2>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => { setPeriod(p.id); setSaved(false); }}
              className={`px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider border transition ${
                period === p.id
                  ? 'bg-signal-work/10 border-signal-work/40 text-signal-work'
                  : 'border-bat-line text-ink-faint hover:text-ink-muted'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-xs text-ink-faint">Reading the ledger...</div>}
      {error && <div className="text-xs text-signal-late">{error}</div>}

      {report && !loading && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { label: 'Finished', value: report.completed.length },
              {
                label: 'Logged',
                value: fmtHm(report.minutes),
                hint: report.minutes === 0 ? 'no focus recorded yet' : null,
              },
              {
                label: 'Days worked',
                value: report.expected_days
                  ? `${report.work_days}/${report.expected_days}`
                  : report.work_days,
              },
              { label: 'Still open', value: report.open_total },
            ].map((s) => (
              <div
                key={s.label}
                className="relative bg-bat-raised rounded border border-bat-line p-3 overflow-hidden"
              >
                <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-signal-work/50" aria-hidden="true" />
                <div className="text-[9px] font-mono uppercase tracking-widest text-ink-muted">{s.label}</div>
                {/* Monospace and tabular so four tiles read as one instrument
                    panel rather than four differently-sized numbers. */}
                <div className="text-2xl font-mono font-bold text-signal-work tabular-nums mt-1 leading-none">
                  {s.value}
                </div>
                {s.hint && (
                  <div className="text-[9px] font-mono text-ink-faint mt-1">{s.hint}</div>
                )}
              </div>
            ))}
          </div>

          {report.expected_minutes > 0 && (
            <div className="text-[11px] text-ink-muted font-mono">
              {fmtHm(report.minutes)} of about {fmtHm(report.expected_minutes)} expected.
            </div>
          )}

          <pre className="text-[11px] text-ink-muted whitespace-pre-wrap font-sans leading-relaxed bg-bat-raised rounded border border-bat-line p-3">
            {report.text}
          </pre>

          {/* The report ends in a question on purpose; this is where it gets answered. */}
          <div className="space-y-2">
            <textarea
              value={reflection}
              onChange={(e) => { setReflection(e.target.value); setSaved(false); }}
              rows={2}
              placeholder="Your answer — kept in the work journal, and it shows up in the month's report."
              className="w-full bg-bat-raised border border-bat-line rounded px-3 py-2 text-xs text-ink placeholder-ink-faint focus:outline-none focus:border-signal-work"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={saveReflection}
                disabled={!reflection.trim()}
                className="px-3 py-1.5 bg-bat-raised hover:bg-bat-line-strong text-ink text-[11px] font-mono tracking-wider rounded disabled:opacity-40"
              >
                SAVE REFLECTION
              </button>
              {saved && <span className="text-[10px] text-signal-good">Kept.</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* --- journal -------------------------------------------------------------- */

function JournalCard({ notes, onAdded, onDeleted }) {
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

  const remove = async (note) => {
    if (!window.confirm('Remove this journal entry?')) return;
    try {
      await api.deleteWorkNote(note.id);
      setError(null);
      onDeleted();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Panel
      title={<span className="flex items-center gap-2"><BookOpen size={13} /> Work journal</span>}
      meta={notes.length ? String(notes.length) : null}
    >
      <form onSubmit={add} className="space-y-2">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={2}
          placeholder="Something learned, something worth remembering about the job."
          className={`${fieldClass} text-xs resize-none focus:ring-signal-work/50`}
        />
        <div className="flex items-center gap-2">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className={`${fieldClass} w-auto py-1.5 text-[11px] font-mono focus:ring-signal-work/50`}
          >
            {NOTE_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
          <Button type="submit" size="sm" tone="work"
            aria-label="Add journal entry" disabled={!content.trim()}>
            Add
          </Button>
        </div>
        {error && <div className="text-xs text-signal-late">{error}</div>}
      </form>

      <div className="mt-3 space-y-2 max-h-64 overflow-y-auto pr-1">
        {notes.length === 0 ? (
          <EmptyState compact>Nothing in the journal yet</EmptyState>
        ) : notes.map((n) => (
          <div key={n.id}
            className="group rounded-chip bg-bat-raised ring-1 ring-bat-line p-2.5 transition-colors duration-200 ease-soft hover:ring-bat-line-strong">
            <div className="flex items-center justify-between gap-2 text-[9px] font-mono uppercase tracking-wider text-ink-faint">
              <span className={n.kind === 'learning' ? 'text-signal-work' : n.kind === 'reflection' ? 'text-signal-warn' : ''}>
                {n.kind}
              </span>
              <span className="flex items-center gap-2">
                {fmtDate(n.created_at)}
                {/* The journal was write-only until now, which stranded four
                    entries claiming hours the report counted as zero. */}
                <button
                  onClick={() => remove(n)}
                  aria-label={`Remove journal entry: ${n.content.slice(0, 40)}`}
                  title="Remove this entry"
                  className="opacity-0 group-hover:opacity-100 focus:opacity-100 text-ink-faint hover:text-signal-late transition-opacity duration-200"
                >
                  <Trash2 size={11} />
                </button>
              </span>
            </div>
            <div className="text-xs text-ink-muted mt-1 whitespace-pre-wrap">{n.content}</div>
          </div>
        ))}
      </div>
    </Panel>
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
  // Only today's total, for the header. The full report stays in ReportCard,
  // which has its own period tabs.
  const [todayMinutes, setTodayMinutes] = useState(null);
  const [reportKey, setReportKey] = useState(0);
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

  const refreshTodayMinutes = useCallback(async () => {
    try {
      const r = await api.getWorkReport('today');
      setTodayMinutes(r?.minutes ?? null);
    } catch {
      setTodayMinutes(null);
    }
  }, []);

  useEffect(() => { refreshTodayMinutes(); }, [refreshTodayMinutes]);

  const moveTask = (task, status_) => withTask(task, () => api.updateWorkTask(task.id, { status: status_ }));
  const completeTask = (task) => withTask(task, () => api.completeWorkTask(task.id));
  // Logging hours is not a task update: it writes a focus session, then the
  // report has to be re-read or the tile keeps saying 0m.
  const logHours = async (task, minutes) => {
    setBusyId(task.id);
    setError(null);
    try {
      await api.logPastFocus({ minutes, work_task_id: task.id });
      setReportKey((k) => k + 1);
      await refreshTodayMinutes();
    } catch (err) {
      // The service refuses overlaps and anything running into the future,
      // and says why — show that rather than a generic failure.
      setError(err.message || 'Could not log those hours.');
    } finally {
      setBusyId(null);
    }
  };

  const deleteTask = (task) => {
    if (!window.confirm(`Delete work task "${task.title}"?`)) return;
    return withTask(task, async () => { await api.deleteWorkTask(task.id); return null; });
  };

  if (loading) {
    return <div className="text-xs text-ink-faint font-mono">LOADING WORK LEDGER...</div>;
  }

  // The panel is only reachable while the track is on; if it was switched off
  // in another tab, say so plainly rather than rendering an empty board.
  if (status && !status.enabled) {
    return (
      <div className="bg-bat-surface rounded border border-bat-line p-6 text-center space-y-2">
        <div className="text-sm text-ink-muted">The work track is switched off.</div>
        <div className="text-xs text-ink-faint">
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

  const openCount = tasks.filter((t) => OPEN_STATUSES.includes(t.status)).length;
  const blockedCount = tasks.filter((t) => t.status === 'blocked').length;

  return (
    <div className="h-full flex flex-col min-h-0 space-y-5">
      <div className="shrink-0">
        <PageHeader
          title="CORPORATE TRACK"
          accent="work"
          stats={[
            { label: 'open', value: openCount, tone: 'work' },
            ...(blockedCount ? [{ label: 'blocked', value: blockedCount, tone: 'late' }] : []),
            ...(todayMinutes !== null ? [{ label: 'logged today', value: fmtHm(todayMinutes) }] : []),
          ]}
        >
          {scheduleLine || 'The job, kept apart from your missions.'}
          <span className="block mt-0.5 font-mono text-[10px] text-ink-faint/70">
            No Bat Points — by design. Points measure you, not the job.
          </span>
        </PageHeader>
      </div>

      {error && (
        <div className="p-3 bg-signal-late/10 border border-signal-late/30 rounded text-signal-late text-xs shrink-0">{error}</div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto space-y-5 pr-1">
        {status && !status.configured && <SetupCard status={status} onSaved={load} />}

        <form onSubmit={addTask} className="bg-bat-surface rounded border border-bat-line p-4 flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What does the job need? (Enter to add)"
            className="flex-1 bg-bat-raised border border-bat-line rounded px-3 py-2 text-sm text-ink placeholder-ink-faint focus:outline-none focus:border-signal-work"
          />
          <input
            type="text"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="Project (optional)"
            className="sm:w-44 bg-bat-raised border border-bat-line rounded px-3 py-2 text-sm text-ink placeholder-ink-faint focus:outline-none focus:border-signal-work"
          />
          <button
            type="submit"
            aria-label="Add work task"
            disabled={adding || !title.trim()}
            className="px-4 py-2 bg-signal-work hover:brightness-110 text-bat-bg text-xs font-bold rounded font-mono tracking-wider flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <Plus size={14} /> ADD
          </button>
        </form>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-mono uppercase tracking-widest text-ink-muted">Board</div>
            <button
              onClick={() => setShowDone((v) => !v)}
              className="text-[10px] font-mono uppercase tracking-wider text-ink-faint hover:text-ink-muted"
            >
              {showDone ? 'HIDE DONE' : 'SHOW DONE'}
            </button>
          </div>
          <div className={`grid grid-cols-1 gap-3 ${showDone ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}>
            {columns.map((s) => {
              const meta = STATUS_META[s];
              const items = tasks.filter((t) => t.status === s);
              return (
                <div key={s} className={`bg-bat-surface rounded border ${meta.box} p-3 space-y-2`}>
                  <div className={`flex items-baseline justify-between text-[10px] font-mono uppercase tracking-widest ${meta.head} border-b pb-1.5`}>
                    <span>{meta.label}</span>
                    <span className="tabular-nums">{String(items.length).padStart(2, '0')}</span>
                  </div>
                  {items.length === 0 ? (
                    /* A dashed well reads as "room for one", where flat grey
                       italic text read as something failing to load. */
                    <div className="rounded border border-dashed border-bat-line py-5 text-center text-[10px] font-mono uppercase tracking-wider text-ink-faint">
                      Empty
                    </div>
                  ) : items.map((t) => (
                    <TaskCard
                      key={t.id}
                      task={t}
                      busy={busyId === t.id}
                      onMove={moveTask}
                      onComplete={completeTask}
                      onDelete={deleteTask}
                      onLogHours={logHours}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ReportCard onSavedReflection={load} refreshKey={reportKey} />
          <JournalCard notes={notes} onAdded={load} onDeleted={load} />
        </div>
      </div>
    </div>
  );
}

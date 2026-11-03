import React, { useEffect, useState } from 'react';
import { Ban, Check, Copy, MapPin, Pencil, Pin, Plus, Target, Trash2, X } from 'lucide-react';
import { api } from '../utils/api';
import { PageHeader, Panel, Button, EmptyState, Field, IconButton, fieldClass } from './ui';

const priorityWeight = { critical: 4, high: 3, medium: 2, low: 1 };

// "135" -> "2h 15m", "40" -> "40m". Time invested matters more than the tick.
function fmtMins(mins) {
  const m = Math.max(0, Math.round(mins || 0));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

// Due dates are calendar dates stored as UTC midnight; read the date part
// directly so they never shift a day in timezones behind UTC.
function dueDateKey(due) {
  return due ? String(due).slice(0, 10) : '';
}

function formatDueDate(due) {
  const [y, m, d] = dueDateKey(due).split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString();
}

function localDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function parseSubtasks(val) {
  try { return val ? JSON.parse(val) : []; } catch { return []; }
}

// Full class names so Tailwind's build keeps them (interpolated names like
// `text-${tone}-400` are purged and rendered colourless).
const PRIORITY_CHIP = {
  low: 'text-ink-faint ring-bat-line',
  medium: 'text-signal-work ring-signal-work/30',
  high: 'text-signal-warn ring-signal-warn/30',
  critical: 'text-signal-late ring-signal-late/40',
};

/**
 * One control, four choices, no four separate bordered boxes.
 *
 * The filters were eight hand-rolled buttons on two rows, each drawing its own
 * border — so the screen opened with more chrome than content. A segmented
 * track reads as a single thing you are moving a selection along.
 */
function Segmented({ label, options, value, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-chip bg-bat-surface ring-1 ring-bat-line p-0.5">
      {options.map((opt) => {
        const on = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={on}
            className={`px-3 py-1 rounded-[6px] text-[10px] font-mono uppercase tracking-widest
              transition-all duration-200 ease-soft
              focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
              ${on ? 'bg-bat-raised text-ink shadow-tile' : 'text-ink-faint hover:text-ink-muted'}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Subtasks, edited as subtasks.
 *
 * This was a textarea labelled "Subtasks (JSON array of {title, done})" whose
 * placeholder was literal JSON. Asking someone to hand-write
 * [{"title":"...","done":false}] to add a checklist item is the single
 * clearest sign nobody had used this form. The stored value is still that
 * JSON string, so nothing on the backend changes — only what a person has to
 * type.
 */
function SubtaskEditor({ value, onChange }) {
  const items = parseSubtasks(value);
  const [draft, setDraft] = useState('');

  const write = (next) => onChange(next.length ? JSON.stringify(next) : '');

  const add = () => {
    const title = draft.trim();
    if (!title) return;
    write([...items, { title, done: false }]);
    setDraft('');
  };

  return (
    <div className="space-y-1.5">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2 rounded-chip bg-bat-raised ring-1 ring-bat-line px-2.5 py-1.5">
          <button
            type="button"
            onClick={() => write(items.map((it, j) => (j === i ? { ...it, done: !it.done } : it)))}
            aria-label={item.done ? `Mark "${item.title}" not done` : `Mark "${item.title}" done`}
            className={`w-3.5 h-3.5 shrink-0 rounded-[4px] ring-1 transition-colors duration-200 ease-soft
              ${item.done ? 'bg-signal-good ring-signal-good' : 'ring-bat-line-strong hover:ring-ink-muted'}`}
          />
          <span className={`flex-1 text-xs truncate ${item.done ? 'text-ink-faint line-through' : 'text-ink-muted'}`}>
            {item.title}
          </span>
          <button
            type="button"
            onClick={() => write(items.filter((_, j) => j !== i))}
            aria-label={`Remove subtask "${item.title}"`}
            className="text-ink-faint hover:text-signal-late transition-colors duration-200"
          >
            <X size={12} />
          </button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          // Enter must not submit the whole mission form while adding a step.
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="Add a step..."
          aria-label="New subtask"
          className={`${fieldClass} text-xs`}
        />
        <Button type="button" size="sm" onClick={add} disabled={!draft.trim()}>Add</Button>
      </div>
    </div>
  );
}

function MissionCard({ mission, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo }) {
  const isCompleted = mission.status === 'completed';
  const subtasks = parseSubtasks(mission.subtasks);
  const doneSubtasks = subtasks.filter(s => s.done).length;
  const tags = mission.tags ? mission.tags.split(',').map(t => t.trim()).filter(Boolean) : [];

  const overdue = !isCompleted && mission.due_date && dueDateKey(mission.due_date) < localDateKey(new Date());

  return (
    <div
      className={`group rounded-tile bg-bat-raised ring-1 p-3.5
        transition-all duration-200 ease-soft hover:shadow-lift
        ${isCompleted
          ? 'ring-bat-line opacity-50'
          : mission.is_pinned
            ? 'ring-signal-self/30'
            : overdue
              ? 'ring-signal-late/25'
              : 'ring-bat-line hover:ring-bat-line-strong'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <button
            type="button"
            onClick={() => onToggleStatus(mission)}
            aria-label={isCompleted ? `Reopen "${mission.title}"` : `Complete "${mission.title}"`}
            title={isCompleted ? 'Reopen' : 'Complete'}
            className={`w-5 h-5 mt-0.5 shrink-0 rounded-[6px] ring-1 inline-flex items-center justify-center
              transition-all duration-200 ease-soft active:scale-[0.9]
              focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
              ${isCompleted
                ? 'bg-signal-self ring-signal-self text-bat-bg'
                : 'ring-bat-line-strong text-transparent hover:ring-signal-self hover:text-signal-self/40'}`}
          >
            <Check size={12} strokeWidth={3} />
          </button>

          <div className="min-w-0">
            <div className="flex items-center flex-wrap gap-1.5">
              <h3 className={`text-sm font-semibold tracking-wide ${isCompleted ? 'line-through text-ink-faint' : 'text-ink'}`}>
                {mission.title}
              </h3>
              {mission.is_pinned && <Pin size={11} className="text-signal-self" aria-label="Pinned" />}
              <span className={`text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-chip ring-1 ${PRIORITY_CHIP[mission.priority] || PRIORITY_CHIP.low}`}>
                {mission.priority}
              </span>
              {tags.map((t, i) => (
                <span key={t + '-' + i} className="text-[9px] font-mono text-ink-muted px-1.5 py-0.5 rounded-chip bg-bat-surface ring-1 ring-bat-line">
                  {t}
                </span>
              ))}
            </div>

            {mission.description && (
              <p className={`text-xs mt-1 leading-snug ${isCompleted ? 'text-ink-faint' : 'text-ink-muted'}`}>
                {mission.description}
              </p>
            )}

            <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono text-ink-faint mt-1.5">
              {mission.due_date && (
                <span className={`inline-flex items-center gap-1 ${overdue ? 'text-signal-late' : ''}`}>
                  <Target size={10} /> {formatDueDate(mission.due_date)}{overdue ? ' · overdue' : ''}
                </span>
              )}
              {mission.location && (
                <span className="inline-flex items-center gap-1"><MapPin size={10} /> {mission.location}</span>
              )}
              {mission.focus_minutes > 0 && (
                <span className="text-signal-self">
                  {fmtMins(mission.focus_minutes)} focused
                  {mission.completed_focus_sessions > 0 && ` · ${mission.completed_focus_sessions} session${mission.completed_focus_sessions !== 1 ? 's' : ''}`}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Dim until the row is approached, then a legible set — rather than
            four controls permanently at the edge of visibility. */}
        <div className="flex items-center gap-0.5 shrink-0 opacity-60 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
          <IconButton label={`Edit "${mission.title}"`} onClick={() => onEdit(mission)} icon={Pencil} />
          <IconButton label={`Duplicate "${mission.title}"`} onClick={() => onDuplicate(mission)} icon={Copy} />
          {!mission.is_dismissed && (
            <IconButton label={`Won't do "${mission.title}"`} onClick={() => onWontDo(mission)} icon={Ban} tone="warn" />
          )}
          <IconButton label={`Delete "${mission.title}"`} onClick={() => onDelete(mission.id)} icon={Trash2} tone="danger" />
        </div>
      </div>

      {subtasks.length > 0 && (
        <div className="mt-3 ml-8 space-y-1.5">
          {/* How far along, before the list of steps — the count alone made
              you read every row to find out. */}
          <div className="flex items-center gap-2">
            {/* Capped, or a full-width track reads as a divider rule rather
                than as progress. */}
            <div className="h-1 w-full max-w-[160px] rounded-full bg-bat-surface overflow-hidden">
              <div
                className="h-full rounded-full bg-signal-good transition-all duration-300 ease-soft"
                style={{ width: `${Math.round((doneSubtasks / subtasks.length) * 100)}%` }}
              />
            </div>
            <span className="text-[10px] font-mono tabular-nums text-ink-faint shrink-0">
              {doneSubtasks}/{subtasks.length}
            </span>
          </div>
          {subtasks.map((s, i) => (
            <div key={s.title + '-' + i} className="flex items-center gap-2 text-xs">
              <span className={`w-2.5 h-2.5 shrink-0 rounded-[3px] ring-1 ${s.done ? 'bg-signal-good ring-signal-good' : 'ring-bat-line-strong'}`} aria-hidden="true" />
              <span className={s.done ? 'line-through text-ink-faint' : 'text-ink-muted'}>{s.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const QUADRANTS = [
  { key: 'do', label: 'Do', sub: 'urgent & important' },
  { key: 'decide', label: 'Decide', sub: 'urgent, not important' },
  { key: 'schedule', label: 'Schedule', sub: 'important, not urgent' },
  { key: 'delegate', label: 'Delegate', sub: 'neither' },
];

function EisenhowerQuadrant({ missions, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo }) {
  const classify = (m) => {
    const urgent = m.priority === 'critical' || m.priority === 'high';
    const important = m.priority !== 'low';
    if (urgent && important) return 'do';
    if (urgent && !important) return 'decide';
    if (!urgent && important) return 'schedule';
    return 'delegate';
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
      {QUADRANTS.map(({ key, label, sub }) => {
        const ms = missions.filter(m => classify(m) === key);
        return (
          <Panel key={key} title={label} meta={`${ms.length} · ${sub}`} bodyClassName="p-3 space-y-2">
            {ms.length === 0
              ? <EmptyState compact>Nothing here</EmptyState>
              : ms.map(m => (
                  <MissionCard key={m.id} mission={m} onEdit={onEdit} onDelete={onDelete} onToggleStatus={onToggleStatus} onDuplicate={onDuplicate} onWontDo={onWontDo} />
                ))}
          </Panel>
        );
      })}
    </div>
  );
}

export default function MissionsPanel({ missions, onRefreshMissions, onRefreshAccount }) {
  const [viewMode, setViewMode] = useState('list');
  const [showForm, setShowForm] = useState(false);
  const [editMission, setEditMission] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '', tags: '', location: '', notes: '', subtasks: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Saving used to produce no acknowledgement whatsoever: the modal vanished
  // and a row appeared somewhere in a list of forty.
  const [flash, setFlash] = useState(null);

  const [dateFilter, setDateFilter] = useState('all');

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2600);
    return () => clearTimeout(t);
  }, [flash]);

  // Escape closes the modal; every other dialog on the web does.
  useEffect(() => {
    if (!showForm) return;
    const onKey = (e) => { if (e.key === 'Escape') closeForm(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showForm]);

  const todayKey = localDateKey(new Date());
  const weekEndKey = localDateKey(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000));
  const inNext7Days = (d) => {
    if (!d) return false;
    const key = dueDateKey(d);
    return key >= todayKey && key <= weekEndKey;
  };

  const activeMissions = missions.filter(m => m.status !== 'completed' && !m.is_dismissed);
  const completedMissions = missions.filter(m => m.status === 'completed');
  const dismissedMissions = missions.filter(m => m.is_dismissed);

  const filterByDate = (list) => {
    if (dateFilter === 'today') return list.filter(m => dueDateKey(m.due_date) === todayKey);
    if (dateFilter === 'week') return list.filter(m => inNext7Days(m.due_date));
    return list;
  };

  const sortedMissions = [...filterByDate(activeMissions)].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0);
  });

  const resetForm = () => {
    setForm({ title: '', description: '', priority: 'medium', due_date: '', tags: '', location: '', notes: '', subtasks: '' });
    setError(null);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditMission(null);
    resetForm();
  };

  const openEdit = (mission) => {
    setEditMission(mission);
    setForm({
      title: mission.title,
      description: mission.description || '',
      priority: mission.priority,
      due_date: dueDateKey(mission.due_date),
      tags: mission.tags || '',
      location: mission.location || '',
      notes: mission.notes || '',
      subtasks: mission.subtasks || '',
    });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const payload = {
        title: form.title,
        description: form.description.trim() || null,
        priority: form.priority,
        due_date: form.due_date ? `${form.due_date}T00:00:00Z` : null,
        tags: form.tags.trim() || null,
        location: form.location.trim() || null,
        notes: form.notes.trim() || null,
        subtasks: form.subtasks.trim() || null,
      };
      // Status is only set on create: editing a completed mission used to
      // send status 'pending' and silently reopen it.
      if (!editMission) payload.status = 'pending';
      const wasEdit = Boolean(editMission);
      if (editMission) {
        await api.updateMission(editMission.id, payload);
      } else {
        await api.createMission(payload);
      }
      closeForm();
      setFlash(wasEdit ? `Updated "${payload.title}"` : `Added "${payload.title}"`);
      await onRefreshMissions();
      await onRefreshAccount();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (mission) => {
    const nextStatus = mission.status === 'completed' ? 'pending' : 'completed';
    try {
      await api.updateMission(mission.id, { status: nextStatus });
      setFlash(nextStatus === 'completed' ? `Done — "${mission.title}"` : `Reopened "${mission.title}"`);
      await onRefreshMissions();
      await onRefreshAccount();
    } catch (err) { console.error(err); }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to decommission this mission?')) return;
    try {
      await api.deleteMission(id);
      await onRefreshMissions();
      await onRefreshAccount();
    } catch (err) { console.error(err); }
  };

  const handleDuplicate = async (mission) => {
    try {
      await api.createMission({
        title: mission.title + ' (copy)',
        description: mission.description,
        priority: mission.priority,
        due_date: mission.due_date,
        tags: mission.tags,
        location: mission.location,
        notes: mission.notes,
        subtasks: mission.subtasks,
        is_pinned: false,
        status: 'pending',
      });
      setFlash(`Copied "${mission.title}"`);
      await onRefreshMissions();
    } catch (err) { console.error(err); }
  };

  const handleWontDo = async (mission) => {
    try {
      await api.updateMission(mission.id, { is_dismissed: true, status: 'dismissed' });
      setFlash(`Set aside "${mission.title}"`);
      await onRefreshMissions();
    } catch (err) { console.error(err); }
  };

  const renderForm = () => (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md"
      onClick={() => { if (form.title.trim() && !confirm('Discard unsaved changes?')) return; closeForm(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={editMission ? 'Edit mission' : 'New mission'}
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-card
          bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line-strong shadow-lift
          animate-rise-in"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-white/[0.04]">
          <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted">
            {editMission ? 'Edit mission' : 'New mission'}
          </h2>
          <button
            type="button"
            onClick={closeForm}
            aria-label="Close"
            className="text-ink-faint hover:text-ink transition-colors duration-200"
          >
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
            <input
              type="text"
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder="Finish the quarterly report"
              className={fieldClass}
              required
              autoFocus
            />
          </Field>

          <Field label="Description">
            <textarea
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Anything you'll want to remember when you pick it up."
              className={`${fieldClass} h-16 resize-none`}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Priority">
              <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className={fieldClass}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </Field>
            <Field label="Due" hint="A mission with a date is one you can plan around.">
              <input
                type="date"
                value={form.due_date}
                onChange={e => setForm({ ...form, due_date: e.target.value })}
                className={`${fieldClass} font-mono`}
              />
            </Field>
          </div>

          <Field label="Tags" hint="Comma-separated.">
            <input
              type="text"
              value={form.tags}
              onChange={e => setForm({ ...form, tags: e.target.value })}
              placeholder="work, admin"
              className={fieldClass}
            />
          </Field>

          <Field label="Where">
            <input
              type="text"
              value={form.location}
              onChange={e => setForm({ ...form, location: e.target.value })}
              placeholder="Office, home, the gym..."
              className={fieldClass}
            />
          </Field>

          <Field label="Notes">
            <textarea
              value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Links, numbers, context."
              className={`${fieldClass} h-16 resize-none`}
            />
          </Field>

          <Field label="Steps">
            <SubtaskEditor value={form.subtasks} onChange={(v) => setForm({ ...form, subtasks: v })} />
          </Field>

          {/* The primary action carries the weight; cancel is a quiet way out,
              not — as before — the louder of the two. */}
          <div className="flex items-center gap-3 pt-1">
            <Button type="submit" tone="self" disabled={loading} className="flex-1 py-2.5">
              {loading ? 'Saving...' : editMission ? 'Save changes' : 'Add mission'}
            </Button>
            <button
              type="button"
              onClick={closeForm}
              className="text-[10px] font-mono uppercase tracking-widest text-ink-faint hover:text-ink-muted transition-colors duration-200 px-2"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );

  // Overdue is the only thing on this screen that needs a decision today.
  const openForStats = missions.filter((m) => m.status === 'pending' && !m.is_dismissed);
  const overdueCount = openForStats.filter(
    (m) => m.due_date && dueDateKey(m.due_date) < todayKey).length;
  const dueTodayCount = openForStats.filter(
    (m) => dueDateKey(m.due_date) === todayKey).length;
  const undatedCount = openForStats.filter((m) => !m.due_date).length;

  const missionStats = [
    { label: 'open', value: openForStats.length },
    ...(overdueCount ? [{ label: 'overdue', value: overdueCount, tone: 'late' }] : []),
    ...(dueTodayCount ? [{ label: 'due today', value: dueTodayCount, tone: 'warn' }] : []),
    ...(undatedCount ? [{ label: 'with no date', value: undatedCount }] : []),
  ];

  const newMissionButton = (
    <Button tone="self" onClick={() => { setEditMission(null); resetForm(); setShowForm(true); }}>
      <Plus size={13} /> New mission
    </Button>
  );

  return (
    <div className="space-y-4">
      <PageHeader title="TACTICAL MISSIONS" stats={missionStats} action={newMissionButton} />

      <div className="flex items-center flex-wrap gap-2">
        <Segmented
          label="View"
          value={viewMode}
          onChange={setViewMode}
          options={[
            { value: 'list', label: 'List' },
            { value: 'eisenhower', label: 'Eisenhower' },
          ]}
        />
        {viewMode === 'list' && (
          <Segmented
            label="Due"
            value={dateFilter}
            onChange={setDateFilter}
            options={[
              { value: 'all', label: 'All' },
              { value: 'today', label: 'Today' },
              { value: 'week', label: 'This week' },
            ]}
          />
        )}
      </div>

      {viewMode === 'eisenhower' ? (
        <EisenhowerQuadrant missions={activeMissions} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} />
      ) : (
        <div className="space-y-gutter">
          <Panel title="Active" meta={`${sortedMissions.length}`} bodyClassName="p-3 space-y-2">
            {sortedMissions.length === 0 ? (
              <EmptyState>
                {dateFilter === 'all' ? 'Nothing on the board' : 'Nothing due in this window'}
              </EmptyState>
            ) : (
              sortedMissions.map(m => (
                <MissionCard key={m.id} mission={m} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} />
              ))
            )}
          </Panel>

          {dismissedMissions.length > 0 && (
            <details>
              <summary className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer px-1 py-2 transition-colors duration-200">
                Set aside ({dismissedMissions.length})
              </summary>
              <div className="space-y-2 mt-2">
                {dismissedMissions.map(m => (
                  <div key={m.id} className="flex items-center justify-between gap-3 rounded-tile bg-bat-raised ring-1 ring-bat-line px-3.5 py-2.5">
                    <span className="text-xs text-ink-faint line-through truncate">{m.title}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        size="sm"
                        onClick={async () => {
                          try {
                            await api.updateMission(m.id, { is_dismissed: false, status: 'pending' });
                            setFlash(`Back on the board — "${m.title}"`);
                            onRefreshMissions();
                          } catch (e) { console.error(e); }
                        }}
                      >
                        Restore
                      </Button>
                      <IconButton label={`Delete "${m.title}"`} onClick={() => handleDelete(m.id)} icon={Trash2} tone="danger" />
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}

          {completedMissions.length > 0 && (
            <details>
              <summary className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer px-1 py-2 transition-colors duration-200">
                Done ({completedMissions.length})
              </summary>
              <div className="space-y-2 mt-2">
                {completedMissions.map(m => (
                  <MissionCard key={m.id} mission={m} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {showForm && renderForm()}

      {flash && (
        <div
          role="status"
          className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] animate-rise-in
            rounded-chip bg-bat-raised ring-1 ring-bat-line-strong shadow-lift
            px-4 py-2 text-[11px] text-ink-muted max-w-[90vw] truncate"
        >
          {flash}
        </div>
      )}
    </div>
  );
}

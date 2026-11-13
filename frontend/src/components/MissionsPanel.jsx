import React, { useEffect, useMemo, useState } from 'react';
import { Ban, Check, ChevronDown, ChevronRight, Copy, MapPin, Pencil, Pin, Plus, Target, Timer, Trash2, X } from 'lucide-react';
import { api } from '../utils/api';
import { PageHeader, Panel, Button, EmptyState, Field, IconButton, Segmented, fieldClass } from './ui';

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

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * The Monday-to-Sunday week `now` falls in, and how to name it.
 *
 * Monday-first on purpose: it is what this codebase uses everywhere else
 * (habit weekdays are Mon=0) and what the owner means by a week. Sunday is
 * day 0 in JS, hence the shuffle.
 */
/**
 * The order of the list.
 *
 * It used to be pinned, then priority, then whatever order the rows came
 * back in — the due date was not in the sort at all. So a board of 44 open
 * missions with 13 overdue and 31 undated scattered the overdue ones
 * through the middle, and the thing most obviously needing attention could
 * sit eighteenth.
 *
 * Date beats priority, deliberately. A priority is a label chosen once,
 * usually when the mission was created and rarely revisited; nearly
 * everything ends up "medium". A due date is a commitment to a moment, and
 * a moment that has passed outranks any label. So a "medium" that was due
 * last week comes before a "high" with no date — which is the right answer,
 * because the first is late and the second is only an intention.
 *
 *   1. pinned        — an explicit "keep this in front of me"
 *   2. dated first   — a date is a commitment, no date is a someday
 *   3. soonest first — overdue, then today, then the rest in order
 *   4. priority      — the tiebreaker within a single day
 *   5. newest first  — stable, and the last thing added is the freshest
 */
/**
 * What a new mission starts as.
 *
 * Due defaults to today, like priority defaults to medium: a field left
 * empty by default is a field usually left empty, and 31 of 44 open
 * missions on this board had no date at all — which is a third of the
 * list that no filter can sort and no sort can order.
 *
 * Today rather than tomorrow or nothing, because the date can be changed
 * in one tap and a wrong date is visible where a missing one is not. Clear
 * it and the mission is undated, exactly as before.
 *
 * `listId` is where it is filed: the list currently selected in the rail,
 * or null (Inbox) when the rail is on All. Inbox means "not filed yet" —
 * null is what the API stores, 'inbox' is only what the rail calls it.
 */
export function blankMission(today = new Date(), listId = null) {
  return {
    title: '',
    description: '',
    priority: 'medium',
    due_date: localDateKey(today),
    tags: '',
    location: '',
    notes: '',
    subtasks: '',
    list_id: listId ?? null,
    // In the list, but not in a section. Only ever a section of list_id —
    // the form clears it whenever the list changes, because a section
    // belongs to exactly one list.
    section_id: null,
  };
}

export function byWhatIsDueFirst(a, b) {
  if (!!a.is_pinned !== !!b.is_pinned) return a.is_pinned ? -1 : 1;

  const aDue = dueDateKey(a.due_date);
  const bDue = dueDateKey(b.due_date);
  if (!!aDue !== !!bDue) return aDue ? -1 : 1;
  if (aDue && bDue && aDue !== bDue) return aDue < bDue ? -1 : 1;

  const byPriority = (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0);
  if (byPriority) return byPriority;

  return (b.id || 0) - (a.id || 0);
}

export function currentWeek(now = new Date()) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const end = new Date(start);
  end.setDate(start.getDate() + 6);

  // Bare days when the week sits in one month ("9–15"); both months named
  // when it straddles two ("30 Nov–6 Dec"), where the days alone would read
  // as going backwards.
  const range = start.getMonth() === end.getMonth()
    ? `${start.getDate()}–${end.getDate()}`
    : `${start.getDate()} ${MONTH_SHORT[start.getMonth()]}–${end.getDate()} ${MONTH_SHORT[end.getMonth()]}`;

  return {
    start,
    end,
    startKey: localDateKey(start),
    endKey: localDateKey(end),
    range,
    // The word AND the dates: the word says what the filter is for, the
    // dates say exactly where it stops. Recomputed on every render from
    // the current date — nothing here is fixed to a particular week.
    label: `This week · ${range}`,
  };
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

function MissionCard({ mission, list, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo, onLogTime, onFocusOn }) {
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
              {/* Which list it is filed under, only when it has one — the
                  Inbox is "no list yet", so it gets no chip. */}
              {list && (
                <span className="inline-flex items-center gap-1 text-[9px] font-mono text-ink-muted px-1.5 py-0.5 rounded-chip bg-bat-surface ring-1 ring-bat-line">
                  {list.color && (
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: list.color }}
                      aria-hidden="true"
                    />
                  )}
                  {list.name}
                </span>
              )}
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
          {/* Deciding what to work on and starting to work on it were two
              screens apart. The gap is where the intention went. */}
          {!isCompleted && onFocusOn && (
            <IconButton
              label={`Focus on "${mission.title}"`}
              onClick={() => onFocusOn(mission.id)}
              icon={Timer}
            />
          )}
          <IconButton label={`Edit "${mission.title}"`} onClick={() => onEdit(mission)} icon={Pencil} />
          <IconButton label={`Duplicate "${mission.title}"`} onClick={() => onDuplicate(mission)} icon={Copy} />
          {!mission.is_dismissed && (
            <IconButton label={`Won't do "${mission.title}"`} onClick={() => onWontDo(mission)} icon={Ban} tone="warn" />
          )}
          <IconButton label={`Delete "${mission.title}"`} onClick={() => onDelete(mission.id)} icon={Trash2} tone="danger" />
        </div>
      </div>

      {/* Recording time used to mean remembering to start a clock BEFORE the
          work. That is a record which is empty precisely on the busiest
          days. An hour is still an hour if nothing was running. */}
      {!isCompleted && onLogTime && (
        <div className="mt-2 ml-8 flex items-center gap-1.5">
          <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">
            Did some
          </span>
          {[15, 30, 60].map((mins) => (
            <button
              key={mins}
              type="button"
              onClick={() => onLogTime(mission, mins)}
              aria-label={`Log ${mins} minutes on "${mission.title}"`}
              className="px-2 py-0.5 rounded-chip text-[10px] font-mono text-ink-faint
                ring-1 ring-bat-line hover:text-ink hover:ring-bat-line-strong
                transition-all duration-200 ease-soft active:scale-[0.94]
                focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60"
            >
              +{mins < 60 ? `${mins}m` : '1h'}
            </button>
          ))}
        </div>
      )}

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

/**
 * Manage the sections of ONE list, in place: add, rename inline, delete.
 * Deleting never destroys missions — they stay in the list, ungrouped — so
 * the confirmation says exactly that, and both the sections and the
 * missions are re-read afterwards.
 */
function SectionManager({ listId, sections, onRefreshSections, onRefreshMissions }) {
  const [adding, setAdding] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [renamingId, setRenamingId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [confirmingId, setConfirmingId] = useState(null);
  const [error, setError] = useState(null);

  const run = async (fn) => {
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      // The server's message is meant to be read: a duplicate or empty
      // name comes back as a 400 with the reason in it.
      setError(err.message);
      return false;
    }
  };

  const submitCreate = async () => {
    const name = draftName.trim();
    if (!name) return;
    const ok = await run(async () => {
      await api.createSection({ list_id: listId, name });
      await onRefreshSections();
    });
    if (ok) { setDraftName(''); setAdding(false); }
  };

  const submitRename = async (id) => {
    const name = renameDraft.trim();
    if (!name) return;
    const ok = await run(async () => {
      await api.renameSection(id, name);
      await onRefreshSections();
    });
    if (ok) setRenamingId(null);
  };

  const submitDelete = async (id) => {
    setConfirmingId(null);
    await run(async () => {
      await api.deleteSection(id);
      // Its missions are now ungrouped, so the missions list is stale too.
      await Promise.all([onRefreshSections(), onRefreshMissions()]);
    });
  };

  return (
    <Panel
      title="Sections"
      meta={sections.length ? `${sections.length}` : null}
      bodyClassName="p-2.5 space-y-0.5"
    >
      {sections.map((s) => (
        <div key={s.id}>
          {renamingId === s.id ? (
            <div className="flex items-center gap-1 px-1 py-0.5">
              <input
                type="text"
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); submitRename(s.id); }
                  if (e.key === 'Escape') setRenamingId(null);
                }}
                autoFocus
                aria-label={`Rename section ${s.name}`}
                className={`${fieldClass} text-xs py-1`}
              />
              <IconButton label={`Save name for "${s.name}"`} onClick={() => submitRename(s.id)} icon={Check} />
              <IconButton label={`Cancel renaming "${s.name}"`} onClick={() => setRenamingId(null)} icon={X} />
            </div>
          ) : confirmingId === s.id ? (
            <div className="rounded-chip bg-bat-raised ring-1 ring-signal-late/30 px-2.5 py-2 space-y-2">
              <p className="text-[11px] leading-snug text-ink-muted">
                Delete <span className="text-ink">{s.name}</span>?
                {' '}Its missions stay in the list, ungrouped — nothing is deleted.
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => submitDelete(s.id)}
                  className="rounded-chip px-2 py-1 text-[10px] font-mono uppercase tracking-widest
                    text-signal-late ring-1 ring-signal-late/40 hover:bg-signal-late/10
                    transition-colors duration-200"
                >
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingId(null)}
                  className="px-2 py-1 text-[10px] font-mono uppercase tracking-widest text-ink-faint hover:text-ink-muted transition-colors duration-200"
                >
                  Keep
                </button>
              </div>
            </div>
          ) : (
            <div className="group flex items-center gap-1">
              <span className="flex-1 min-w-0 truncate px-2.5 py-1.5 font-mono text-xs text-ink-muted">
                {s.name}
              </span>
              {s.open_missions > 0 && (
                <span className="shrink-0 text-[10px] tabular-nums px-1.5 py-0.5 rounded-chip bg-bat-surface text-ink-faint ring-1 ring-bat-line">
                  {s.open_missions}
                </span>
              )}
              {/* Row actions stay out of the way until the row is approached. */}
              <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
                <IconButton
                  label={`Rename "${s.name}"`}
                  onClick={() => { setRenamingId(s.id); setRenameDraft(s.name); }}
                  icon={Pencil}
                />
                <IconButton
                  label={`Delete "${s.name}"`}
                  onClick={() => setConfirmingId(s.id)}
                  icon={Trash2}
                  tone="danger"
                />
              </div>
            </div>
          )}
        </div>
      ))}

      {adding ? (
        <div className="flex items-center gap-1 px-1 py-0.5">
          <input
            type="text"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); submitCreate(); }
              if (e.key === 'Escape') { setAdding(false); setDraftName(''); }
            }}
            autoFocus
            placeholder="New section"
            aria-label="New section name"
            className={`${fieldClass} text-xs py-1`}
          />
          <IconButton label="Save section" onClick={submitCreate} icon={Check} />
          <IconButton label="Cancel new section" onClick={() => { setAdding(false); setDraftName(''); }} icon={X} />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="w-full flex items-center gap-1.5 rounded-chip px-2.5 py-1.5
            font-mono text-xs text-ink-faint hover:text-ink hover:bg-bat-raised
            transition-all duration-200 ease-soft
            focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60"
        >
          <Plus size={12} /> Add section
        </button>
      )}

      {error && (
        <p role="alert" className="px-2.5 pt-1 text-[10px] text-signal-late">{error}</p>
      )}
    </Panel>
  );
}

/**
 * A collapsible heading over one section's missions. The count is what is
 * actually visible under it, so it never argues with the list below.
 */
function SectionGroupHeading({ name, count, collapsed, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      className="w-full flex items-center gap-1.5 rounded-chip px-1.5 py-1 text-left
        font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint
        hover:text-ink-muted transition-colors duration-200
        focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60"
    >
      {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
      <span className="truncate">{name}</span>
      {count > 0 && (
        <span className="shrink-0 text-[9px] tabular-nums px-1.5 py-0.5 rounded-chip bg-bat-surface text-ink-faint ring-1 ring-bat-line">
          {count}
        </span>
      )}
    </button>
  );
}

function EisenhowerQuadrant({ missions, listsById, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo, onLogTime, onFocusOn }) {
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
                  <MissionCard key={m.id} mission={m} list={listsById[m.list_id]} onEdit={onEdit} onDelete={onDelete} onToggleStatus={onToggleStatus} onDuplicate={onDuplicate} onWontDo={onWontDo} onLogTime={onLogTime} onFocusOn={onFocusOn} />
                ))}
          </Panel>
        );
      })}
    </div>
  );
}

export default function MissionsPanel({
  missions,
  onRefreshMissions,
  onRefreshAccount,
  onFocusOn,
  lists = [],
  selectedList = null,
  sections = [],
  onRefreshSections = () => {},
}) {
  const [viewMode, setViewMode] = useState('list');
  const [showForm, setShowForm] = useState(false);
  const [editMission, setEditMission] = useState(null);
  const [form, setForm] = useState(() => blankMission());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Saving used to produce no acknowledgement whatsoever: the modal vanished
  // and a row appeared somewhere in a list of forty.
  const [flash, setFlash] = useState(null);

  const [dateFilter, setDateFilter] = useState('all');

  const listsById = useMemo(
    () => Object.fromEntries(lists.map((l) => [l.id, l])),
    [lists]);

  // A new mission files itself wherever the rail is standing: the selected
  // list, or the Inbox when the rail is on All ('inbox' and null both mean
  // no list yet, so both become null).
  const defaultListId = selectedList === 'inbox' ? null : selectedList;

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
  const { startKey: weekStartKey, endKey: weekEndKey, label: weekLabel } = currentWeek();

  // Every filter means EXACTLY its dates. "Today" briefly meant "today or
  // anything already late", which put a mission from the 15th of October
  // under a button marked Today — reasonable as a to-do list, wrong as a
  // label, and the label is what people read. Overdue has its own button
  // instead, so nothing is hidden and nothing is mislabelled.
  const isOverdue = (d) => !!d && dueDateKey(d) < todayKey;

  // The week is the CALENDAR week, Monday to Sunday, and the button says
  // which dates those are. A rolling "next seven days" was neither what the
  // label claimed nor what anyone pictures when they say "this week", and a
  // filter you have to guess the boundaries of is a filter you cannot trust.
  // Days earlier in this week are inside it, so a mission that slipped on
  // Monday still appears on Friday.
  const inThisWeek = (d) => {
    if (!d) return false;
    const key = dueDateKey(d);
    return key >= weekStartKey && key <= weekEndKey;
  };

  // The list filter is a SECOND, independent filter: it narrows by where a
  // mission is filed, and the date filter below still applies on top of it.
  // null (the rail's All) and undefined (no rail wired) both mean everything.
  const matchesList = (m) => selectedList == null
    || (selectedList === 'inbox' ? !m.list_id : m.list_id === selectedList);

  const activeMissions = missions.filter(m => m.status !== 'completed' && !m.is_dismissed && matchesList(m));
  const completedMissions = missions.filter(m => m.status === 'completed' && matchesList(m));
  const dismissedMissions = missions.filter(m => m.is_dismissed && matchesList(m));

  const filterByDate = (list) => {
    if (dateFilter === 'overdue') return list.filter(m => isOverdue(m.due_date));
    if (dateFilter === 'today') return list.filter(m => dueDateKey(m.due_date) === todayKey);
    if (dateFilter === 'week') return list.filter(m => inThisWeek(m.due_date));
    return list;
  };

  const sortedMissions = [...filterByDate(activeMissions)].sort(byWhatIsDueFirst);

  // Sections (Phase 9). Grouping exists only when ONE list is selected:
  // All and Inbox have no single list to take sections from, so they stay
  // the flat list they have always been.
  const groupedView = typeof selectedList === 'number';

  const listSections = useMemo(
    () => sections.filter((s) => s.list_id === selectedList),
    [sections, selectedList]);

  // ...and even then only when the list actually has some: an Ungrouped
  // heading over a list with no sections would be furniture, not function.
  const useGroups = groupedView && listSections.length > 0;

  const [collapsedGroups, setCollapsedGroups] = useState({});
  // Collapsed state is keyed by section id; a stale key from another list
  // must not keep this one folded.
  useEffect(() => setCollapsedGroups({}), [selectedList]);

  // Grouping happens AFTER filtering and sorting: what the date filter
  // hid stays hidden, and within each section the order is the same
  // soonest-first order as the flat list.
  const groups = useMemo(() => {
    if (!useGroups) return null;
    const buckets = [...listSections]
      .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
      .map((s) => ({ id: `s${s.id}`, section: s, missions: [] }));
    const byId = new Map(buckets.map((b) => [b.section.id, b]));
    const ungrouped = { id: 'ungrouped', section: null, missions: [] };
    for (const m of sortedMissions) {
      // A section always belongs to the mission's own list — the server
      // enforces it. A stale id (a section just deleted) lands in the
      // ungrouped bucket rather than making the mission vanish.
      const bucket = (m.section_id != null ? byId.get(m.section_id) : null) || ungrouped;
      bucket.missions.push(m);
    }
    // A section with no missions was made on purpose: its heading stays.
    // Ungrouped is the leftover bucket, so it only speaks when it holds
    // something.
    return [...buckets, ...(ungrouped.missions.length ? [ungrouped] : [])];
  }, [useGroups, listSections, sortedMissions]);

  const resetForm = () => {
    setForm(blankMission(undefined, defaultListId));
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
      list_id: mission.list_id ?? null,
      section_id: mission.section_id ?? null,
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
        list_id: form.list_id ?? null,
        section_id: form.section_id ?? null,
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

  // Backfilled, ending now: "I have just done half an hour on this" is the
  // shape the time actually arrives in.
  const handleLogTime = async (mission, minutes) => {
    try {
      await api.logPastFocus({ minutes, mission_id: mission.id });
      setFlash(`Logged ${minutes < 60 ? `${minutes}m` : '1h'} on "${mission.title}"`);
      await onRefreshMissions();
    } catch (err) {
      setFlash(err.message || 'Could not log that.');
    }
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
        list_id: mission.list_id ?? null,
        section_id: mission.section_id ?? null,
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

          <Field label="List" hint="Inbox means not filed yet.">
            <select
              value={form.list_id ?? ''}
              onChange={e => setForm({ ...form, list_id: e.target.value ? Number(e.target.value) : null, section_id: null })}
              className={fieldClass}
            >
              <option value="">Inbox</option>
              {lists.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>

          {/* A section belongs to exactly ONE list, so the control exists
              only while a list is chosen, and only offers that list's
              sections — changing the list cleared it above. */}
          {form.list_id != null && (
            <Field label="Section" hint="A subdivision of the list. Optional.">
              <select
                value={form.section_id ?? ''}
                onChange={e => setForm({ ...form, section_id: e.target.value ? Number(e.target.value) : null })}
                className={fieldClass}
              >
                <option value="">None — just in the list</option>
                {sections.filter(s => s.list_id === form.list_id).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </Field>
          )}

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
              // Overdue earns its own button rather than being folded into
              // Today. It is the thing most worth seeing and the thing
              // least like "today".
              ...(overdueCount ? [{ value: 'overdue', label: `Overdue · ${overdueCount}` }] : []),
              { value: 'today', label: 'Today' },
              // Named by its actual dates — "9–15 Nov" — so the window is
              // visible rather than something you work out.
              { value: 'week', label: weekLabel },
            ]}
          />
        )}
      </div>

      {groupedView && (
        <SectionManager
          // Remount per list, so draft/rename/confirm state from one list
          // is never pointed at another.
          key={selectedList}
          listId={selectedList}
          sections={listSections}
          onRefreshSections={onRefreshSections}
          onRefreshMissions={onRefreshMissions}
        />
      )}

      {viewMode === 'eisenhower' ? (
        <EisenhowerQuadrant missions={activeMissions} listsById={listsById} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} onLogTime={handleLogTime} onFocusOn={onFocusOn} />
      ) : (
        <div className="space-y-gutter">
          {/* The order is stated, because a list you cannot explain the
              order of is one you end up re-reading top to bottom. */}
          <Panel
            title="Active"
            meta={`${sortedMissions.length} · soonest first`}
            bodyClassName="p-3 space-y-2"
          >
            {sortedMissions.length === 0 && !useGroups ? (
              <EmptyState>
                {selectedList != null ? 'Nothing in this list'
                  : dateFilter === 'all' ? 'Nothing on the board'
                  : dateFilter === 'today' ? 'Nothing due today'
                  : dateFilter === 'overdue' ? 'Nothing overdue'
                  : 'Nothing due in this window'}
              </EmptyState>
            ) : useGroups ? (
              groups.map(group => (
                <div key={group.id} className="space-y-2">
                  <SectionGroupHeading
                    name={group.section ? group.section.name : 'Ungrouped'}
                    count={group.missions.length}
                    collapsed={!!collapsedGroups[group.id]}
                    onToggle={() => setCollapsedGroups(prev => ({ ...prev, [group.id]: !prev[group.id] }))}
                  />
                  {!collapsedGroups[group.id] && (
                    <div className="space-y-2">
                      {group.missions.map(m => (
                        <MissionCard key={m.id} mission={m} list={listsById[m.list_id]} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} onLogTime={handleLogTime} onFocusOn={onFocusOn} />
                      ))}
                    </div>
                  )}
                </div>
              ))
            ) : (
              sortedMissions.map(m => (
                <MissionCard key={m.id} mission={m} list={listsById[m.list_id]} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} onLogTime={handleLogTime} onFocusOn={onFocusOn} />
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
                  <MissionCard key={m.id} mission={m} list={listsById[m.list_id]} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} onLogTime={handleLogTime} onFocusOn={onFocusOn} />
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

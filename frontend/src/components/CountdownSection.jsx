import React, { useState, useEffect, useMemo } from 'react';
import { Trash2 } from 'lucide-react';
import { api } from '../utils/api.js';
import { migrateOnce } from '../utils/migrateLocalStorage.js';
import { PageHeader, Panel, Button, EmptyState, Field, IconButton, fieldClass } from './ui';

const LEGACY_KEY = 'bat_countdown_goals';
const MIGRATED_FLAG = 'bat_countdown_migrated';

// Written out, because Tailwind reads the source for whole class names.
// These were built as `text-${color}`, so `text-blue-400` and
// `text-amber-400` appeared nowhere it could see them and were stripped from
// the stylesheet entirely — two of the three default labels have been
// rendering with no colour at all.
const TONES = {
  self: 'text-signal-self',
  work: 'text-signal-work',
  warn: 'text-signal-warn',
  late: 'text-signal-late',
};

function calcDiff(target, from) {
  const diff = target.getTime() - from;
  if (diff <= 0) return { days: 0, hours: 0, minutes: 0, seconds: 0, expired: true };
  const totalSeconds = Math.floor(diff / 1000);
  return {
    days: Math.floor(totalSeconds / 86400),
    hours: Math.floor((totalSeconds % 86400) / 3600),
    minutes: Math.floor((totalSeconds % 3600) / 60),
    seconds: totalSeconds % 60,
    expired: false,
  };
}

/**
 * One clock for the whole screen.
 *
 * Every tile used to run its own `setInterval`, so a page with the three
 * defaults and ten goals ticked thirteen separate timers a second, each
 * re-rendering on its own schedule.
 */
function useSecondTick() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function Unit({ value, suffix }) {
  return (
    <div className="flex items-baseline">
      <span className="text-2xl font-bold font-mono tabular-nums text-ink leading-none">{value}</span>
      <span className="text-[9px] font-mono text-ink-faint ml-1">{suffix}</span>
    </div>
  );
}

function CountdownTile({ label, target, tone = 'self', now, onDelete, onDismiss }) {
  const diff = calcDiff(new Date(target), now);

  return (
    <div className="group relative rounded-tile bg-bat-raised ring-1 ring-bat-line p-4
      transition-all duration-200 ease-soft hover:ring-bat-line-strong">
      {onDelete && !diff.expired && (
        <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
          <IconButton label={`Delete "${label}"`} icon={Trash2} tone="danger" size={12} onClick={onDelete} />
        </div>
      )}

      <div className={`text-[10px] font-mono uppercase tracking-[0.14em] mb-2 truncate pr-6 ${TONES[tone] || TONES.self}`}>
        {label}
      </div>

      {diff.expired ? (
        <div className="space-y-2">
          <div className="text-signal-good text-sm font-bold">Done</div>
          {onDismiss && <Button size="sm" onClick={onDismiss}>Clear it</Button>}
        </div>
      ) : (
        <div className="flex items-center gap-3">
          {diff.days > 0 && <Unit value={diff.days} suffix="d" />}
          <Unit value={String(diff.hours).padStart(2, '0')} suffix="h" />
          <Unit value={String(diff.minutes).padStart(2, '0')} suffix="m" />
          <Unit value={String(diff.seconds).padStart(2, '0')} suffix="s" />
        </div>
      )}
    </div>
  );
}

function fromServer(c) {
  return { id: c.id, label: c.title, target: c.target_date };
}

// Sunday 23:59, to match the Monday-first week the calendar draws. The old
// arithmetic was `date + (7 - getDay())`, which on a Sunday pointed at NEXT
// Sunday — "end of week" read as seven days away on the day it was due.
export function endOfWeek(from) {
  const d = new Date(from);
  d.setDate(d.getDate() + ((7 - d.getDay()) % 7));
  d.setHours(23, 59, 59, 999);
  return d;
}

export default function CountdownSection() {
  const [goals, setGoals] = useState([]);
  const [newLabel, setNewLabel] = useState('');
  const [newTarget, setNewTarget] = useState('');
  const [error, setError] = useState(null);
  const now = useSecondTick();

  // One-time legacy migration, then load from the API.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await migrateOnce({
          legacyKey: LEGACY_KEY,
          flagKey: MIGRATED_FLAG,
          toPayload: (g) => ({ title: g.label, target_date: g.target }),
          upload: (payload) => api.createCountdown(payload),
        });
      } catch {
        // Migration failed partway: flag not set, retries next load.
      }
      try {
        const data = await api.getCountdowns();
        if (!cancelled) setGoals((data || []).map(fromServer));
      } catch {
        // Offline/backend down: keep empty list rather than crashing.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const addGoal = async () => {
    if (!newLabel.trim() || !newTarget) return;
    setError(null);
    try {
      const created = await api.createCountdown({
        title: newLabel.trim(),
        // datetime-local has no timezone; interpret as local time.
        target_date: new Date(newTarget).toISOString(),
      });
      setGoals(prev => [...prev, fromServer(created)]);
      setNewLabel('');
      setNewTarget('');
    } catch (err) {
      // It used to fail in complete silence — you typed a goal, pressed Add,
      // and nothing happened or appeared.
      setError(err.message || 'Could not save that goal.');
    }
  };

  const deleteGoal = async (id) => {
    setGoals(prev => prev.filter(g => g.id !== id));
    try {
      await api.deleteCountdown(id);
    } catch {
      // Optimistic removal stands; next load re-syncs from the server.
    }
  };

  const defaults = useMemo(() => {
    const d = new Date(now);
    return [
      { label: 'End of week', target: endOfWeek(d).toISOString(), tone: 'work' },
      { label: 'End of month', target: new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999).toISOString(), tone: 'warn' },
      { label: 'End of year', target: new Date(d.getFullYear(), 11, 31, 23, 59, 59, 999).toISOString(), tone: 'late' },
    ];
    // Recomputed only when the day changes, not every second.
  }, [new Date(now).toDateString()]);

  const live = goals.filter((g) => new Date(g.target).getTime() > now);
  const passed = goals.filter((g) => new Date(g.target).getTime() <= now);
  const soonest = [...live].sort((a, b) => new Date(a.target) - new Date(b.target))[0];

  const stats = [
    { label: 'goals', value: goals.length },
    ...(soonest
      ? [{
          label: `until ${soonest.label.length > 22 ? soonest.label.slice(0, 21) + '…' : soonest.label}`,
          value: `${calcDiff(new Date(soonest.target), now).days}d`,
          tone: 'self',
        }]
      : []),
    ...(passed.length ? [{ label: 'passed', value: passed.length, tone: 'good' }] : []),
  ];

  return (
    <div className="space-y-gutter">
      {/* "Real-time countdown tracking for critical deadlines and personal
          goals" described the feature to someone already using it. */}
      <PageHeader title="COUNTDOWNS" stats={stats} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
        {defaults.map(d => (
          <CountdownTile key={d.label} label={d.label} target={d.target} tone={d.tone} now={now} />
        ))}
      </div>

      <Panel title="Your own">
        {error && (
          <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late mb-3">
            {error}
          </div>
        )}
        <div className="flex items-end gap-3">
          <Field label="What for" className="flex-1">
            <input type="text" value={newLabel} onChange={e => setNewLabel(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addGoal(); } }}
              placeholder="Thesis hand-in" className={`${fieldClass} text-xs`} />
          </Field>
          <Field label="When" className="flex-1">
            <input type="datetime-local" value={newTarget} onChange={e => setNewTarget(e.target.value)}
              className={`${fieldClass} text-xs font-mono`} />
          </Field>
          <Button tone="self" onClick={addGoal} disabled={!newLabel.trim() || !newTarget} className="mb-0.5">
            Add
          </Button>
        </div>
      </Panel>

      {goals.length === 0 ? (
        <EmptyState>Nothing of your own counting down</EmptyState>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-gutter">
          {[...live, ...passed].map(g => (
            <CountdownTile key={g.id} label={g.label} target={g.target} now={now}
              onDelete={() => deleteGoal(g.id)} onDismiss={() => deleteGoal(g.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

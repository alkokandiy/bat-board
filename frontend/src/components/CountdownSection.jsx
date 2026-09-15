import React, { useState, useEffect } from 'react';
import { api } from '../utils/api.js';
import { migrateOnce } from '../utils/migrateLocalStorage.js';

const LEGACY_KEY = 'bat_countdown_goals';
const MIGRATED_FLAG = 'bat_countdown_migrated';

function calcDiff(target) {
  const now = new Date();
  const diff = target.getTime() - now.getTime();
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

function CountdownTile({ label, target, color = 'electric-bat-yellow', onDelete, onDismiss }) {
  const [diff, setDiff] = useState(() => calcDiff(new Date(target)));

  useEffect(() => {
    const id = setInterval(() => setDiff(calcDiff(new Date(target))), 1000);
    return () => clearInterval(id);
  }, [target]);

  return (
    <div className={`bg-dark-slate p-4 rounded border border-slate-800 relative`}>
      {onDelete && !diff.expired && (
        <button onClick={onDelete} className="absolute top-2 right-2 text-slate-600 hover:text-red-500 text-[10px]">✕</button>
      )}
      <div className={`text-[10px] font-mono uppercase tracking-widest text-${color} mb-2 truncate pr-4`}>{label}</div>
      {diff.expired ? (
        <div className="space-y-2">
          <div className="text-green-400 text-sm font-bold">COMPLETE ✓</div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-[10px] font-mono tracking-widest text-slate-500 hover:text-electric-bat-yellow border border-slate-800 hover:border-electric-bat-yellow/50 rounded px-2 py-1 transition"
            >
              VERIFIED — DISMISS
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3 font-mono">
          {diff.days > 0 && <div><span className="text-2xl font-bold text-slate-100">{diff.days}</span><span className="text-[9px] text-slate-500 ml-1">d</span></div>}
          <div><span className="text-2xl font-bold text-slate-100">{String(diff.hours).padStart(2, '0')}</span><span className="text-[9px] text-slate-500 ml-1">h</span></div>
          <div><span className="text-2xl font-bold text-slate-100">{String(diff.minutes).padStart(2, '0')}</span><span className="text-[9px] text-slate-500 ml-1">m</span></div>
          <div><span className="text-2xl font-bold text-slate-100">{String(diff.seconds).padStart(2, '0')}</span><span className="text-[9px] text-slate-500 ml-1">s</span></div>
        </div>
      )}
    </div>
  );
}

function fromServer(c) {
  return { id: c.id, label: c.title, target: c.target_date };
}

export default function CountdownSection() {
  const [goals, setGoals] = useState([]);
  const [newLabel, setNewLabel] = useState('');
  const [newTarget, setNewTarget] = useState('');

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
    try {
      const created = await api.createCountdown({
        title: newLabel.trim(),
        // datetime-local has no timezone; interpret as local time.
        target_date: new Date(newTarget).toISOString(),
      });
      setGoals(prev => [...prev, fromServer(created)]);
      setNewLabel('');
      setNewTarget('');
    } catch {
      // Backend unreachable: don't pretend it was saved.
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

  const now = new Date();
  const endOfWeek = new Date(now);
  endOfWeek.setDate(now.getDate() + (7 - now.getDay()));
  endOfWeek.setHours(23, 59, 59, 999);
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);
  const endOfYear = new Date(now.getFullYear(), 11, 31, 23, 59, 59, 999);

  const defaults = [
    { label: 'End of Week', target: endOfWeek.toISOString(), color: 'blue-400' },
    { label: 'End of Month', target: endOfMonth.toISOString(), color: 'amber-400' },
    { label: 'End of Year', target: endOfYear.toISOString(), color: 'red-400' },
  ];

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">COUNTDOWN TIMER</h1>
        <p className="text-xs text-slate-400">Real-time countdown tracking for critical deadlines and personal goals.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {defaults.map(d => (
          <CountdownTile key={d.label} label={d.label} target={d.target} color={d.color} />
        ))}
      </div>

      <div className="bg-dark-slate p-4 rounded border border-slate-800 space-y-3">
        <h2 className="text-xs font-mono uppercase tracking-widest text-slate-300">Personal Goals</h2>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-[10px] text-slate-400 font-mono mb-1">Goal Name</label>
            <input type="text" value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Mission deadline..." className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow text-xs" />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] text-slate-400 font-mono mb-1">Target Date</label>
            <input type="datetime-local" value={newTarget} onChange={e => setNewTarget(e.target.value)} className="w-full bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-electric-bat-yellow text-xs font-mono" />
          </div>
          <button onClick={addGoal} disabled={!newLabel.trim() || !newTarget} className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono text-[10px] tracking-widest disabled:opacity-50 whitespace-nowrap">
            ADD
          </button>
        </div>
      </div>

      {goals.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {goals.map(g => (
            <CountdownTile key={g.id} label={g.label} target={g.target} onDelete={() => deleteGoal(g.id)} onDismiss={() => deleteGoal(g.id)} />
          ))}
        </div>
      )}

      {goals.length === 0 && (
        <div className="bg-dark-slate p-8 text-center rounded border border-slate-800 text-slate-500 font-mono text-xs">
          NO PERSONAL GOALS CONFIGURED. ADD ONE ABOVE.
        </div>
      )}
    </div>
  );
}

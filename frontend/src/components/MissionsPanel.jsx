import React, { useState } from 'react';
import { api } from '../utils/api';

const priorityWeight = { critical: 4, high: 3, medium: 2, low: 1 };

function parseSubtasks(val) {
  try { return val ? JSON.parse(val) : []; } catch { return []; }
}

function EisenhowerQuadrant({ missions, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo }) {
  const classify = (m) => {
    const urgent = m.priority === 'critical' || m.priority === 'high';
    const important = m.priority !== 'low';
    if (urgent && important) return 1;
    if (urgent && !important) return 2;
    if (!urgent && important) return 3;
    return 4;
  };
  const q1 = missions.filter(m => classify(m) === 1);
  const q2 = missions.filter(m => classify(m) === 2);
  const q3 = missions.filter(m => classify(m) === 3);
  const q4 = missions.filter(m => classify(m) === 4);

  const labels = [
    { label: '1. DO (Urgent & Important)', color: 'red', missions: q1 },
    { label: '2. DECIDE (Urgent & Not Important)', color: 'amber', missions: q2 },
    { label: '3. SCHEDULE (Not Urgent & Important)', color: 'blue', missions: q3 },
    { label: '4. DELEGATE (Not Urgent & Not Important)', color: 'slate', missions: q4 },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {labels.map(({ label, color, missions: ms }) => (
        <div key={color} className={`bg-dark-slate rounded border border-${color}-900/30 p-3 space-y-2`}>
          <div className={`text-[10px] font-mono uppercase tracking-widest text-${color}-400 border-b border-${color}-900/20 pb-1`}>
            {label} <span className="text-slate-500">({ms.length})</span>
          </div>
          {ms.length === 0 ? (
            <div className="text-[10px] text-slate-600 italic">No missions</div>
          ) : (
            ms.map(m => <MissionCard key={m.id} mission={m} onEdit={onEdit} onDelete={onDelete} onToggleStatus={onToggleStatus} onDuplicate={onDuplicate} onWontDo={onWontDo} />)
          )}
        </div>
      ))}
    </div>
  );
}

function MissionCard({ mission, onEdit, onDelete, onToggleStatus, onDuplicate, onWontDo }) {
  const isCompleted = mission.status === 'completed';
  const subtasks = parseSubtasks(mission.subtasks);
  const doneSubtasks = subtasks.filter(s => s.done).length;
  const tags = mission.tags ? mission.tags.split(',').map(t => t.trim()).filter(Boolean) : [];

  const priorityStyles = {
    low: 'bg-slate-800/60 text-slate-400 border-slate-800',
    medium: 'bg-blue-950/20 text-blue-400 border-blue-900/30',
    high: 'bg-amber-950/20 text-amber-400 border-amber-900/30',
    critical: 'bg-red-950/30 text-red-500 border-red-900/40 font-bold'
  };

  return (
    <div className={`bg-dark-slate p-4 rounded border transition-all duration-200 ${isCompleted ? 'border-slate-900 opacity-60' : mission.is_pinned ? 'border-yellow-700/50' : 'border-slate-800 hover:border-slate-700'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start space-x-3 min-w-0">
          <button onClick={() => onToggleStatus(mission)}
            className={`w-5 h-5 rounded border mt-0.5 flex items-center justify-center shrink-0 transition ${isCompleted ? 'bg-electric-bat-yellow border-electric-bat-yellow text-matte-obsidian' : 'border-slate-700 hover:border-electric-bat-yellow'}`}>
            {isCompleted && <span className="text-xs font-bold">✓</span>}
          </button>
          <div className="min-w-0">
            <div className="flex items-center flex-wrap gap-1.5">
              <h3 className={`text-sm font-semibold tracking-wide ${isCompleted ? 'line-through text-slate-500' : 'text-slate-200'}`}>
                {mission.title}
              </h3>
              {mission.is_pinned && <span className="text-[10px] text-yellow-500">📌</span>}
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${priorityStyles[mission.priority] || ''}`}>
                {mission.priority}
              </span>
              {tags.map((t, i) => (
                <span key={t + '-' + i} className="text-[10px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-slate-700">
                  {t}
                </span>
              ))}
            </div>
            {mission.description && (
              <p className={`text-xs mt-0.5 ${isCompleted ? 'text-slate-600' : 'text-slate-400'}`}>
                {mission.description}
              </p>
            )}
            <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono mt-1">
              {mission.due_date && <span>🎯 {new Date(mission.due_date).toLocaleDateString()}</span>}
              {mission.location && <span>📍 {mission.location}</span>}
              {subtasks.length > 0 && <span>✓ {doneSubtasks}/{subtasks.length}</span>}
              {mission.focus_minutes > 0 && <span>⏱ {mission.focus_minutes}m</span>}
            </div>
            {mission.completed_focus_sessions > 0 && (
              <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                {mission.completed_focus_sessions} focus session{mission.completed_focus_sessions !== 1 ? 's' : ''}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-1 shrink-0">
          <button onClick={() => onEdit(mission)} className="w-7 h-7 flex items-center justify-center rounded text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition text-xs" title="Edit">✎</button>
          <button onClick={() => onDuplicate(mission)} className="w-7 h-7 flex items-center justify-center rounded text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition text-xs" title="Duplicate">⧉</button>
          {!mission.is_dismissed && (
            <button onClick={() => onWontDo(mission)} className="w-7 h-7 flex items-center justify-center rounded text-slate-600 hover:text-amber-400 hover:bg-slate-800 transition text-xs" title="Won't Do">⊘</button>
          )}
          <button onClick={() => onDelete(mission.id)} className="w-7 h-7 flex items-center justify-center rounded text-slate-600 hover:text-red-500 hover:bg-slate-800 transition text-xs" title="Delete">✕</button>
        </div>
      </div>
      {subtasks.length > 0 && (
        <div className="mt-2 ml-7 space-y-0.5">
          {subtasks.map((s, i) => (
            <div key={s.title + '-' + i} className="flex items-center space-x-1.5 text-xs">
              <span className={s.done ? 'text-green-500' : 'text-slate-600'}>{s.done ? '☑' : '☐'}</span>
              <span className={s.done ? 'line-through text-slate-500' : 'text-slate-400'}>{s.title}</span>
            </div>
          ))}
        </div>
      )}
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

  const [dateFilter, setDateFilter] = useState('all');

  const todayStr = new Date().toDateString();
  const inNext7Days = (d) => {
    if (!d) return false;
    const ms = new Date(d).getTime() - new Date().getTime();
    return ms >= 0 && ms <= 7 * 24 * 60 * 60 * 1000;
  };

  const activeMissions = missions.filter(m => m.status !== 'completed' && !m.is_dismissed);
  const completedMissions = missions.filter(m => m.status === 'completed');
  const dismissedMissions = missions.filter(m => m.is_dismissed);

  const filterByDate = (list) => {
    if (dateFilter === 'today') return list.filter(m => m.due_date && new Date(m.due_date).toDateString() === todayStr);
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

  const openEdit = (mission) => {
    setEditMission(mission);
    setForm({
      title: mission.title,
      description: mission.description || '',
      priority: mission.priority,
      due_date: mission.due_date ? mission.due_date.slice(0, 10) : '',
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
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        tags: form.tags.trim() || null,
        location: form.location.trim() || null,
        notes: form.notes.trim() || null,
        subtasks: form.subtasks.trim() || null,
        status: 'pending',
      };
      if (editMission) {
        await api.updateMission(editMission.id, payload);
      } else {
        await api.createMission(payload);
      }
      setShowForm(false);
      setEditMission(null);
      resetForm();
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
      await onRefreshMissions();
    } catch (err) { console.error(err); }
  };

  const handleWontDo = async (mission) => {
    try {
      await api.updateMission(mission.id, { is_dismissed: true, status: 'dismissed' });
      await onRefreshMissions();
    } catch (err) { console.error(err); }
  };

  const renderForm = () => (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => { if (form.title.trim() && !confirm('Discard unsaved changes?')) return; setShowForm(false); setEditMission(null); resetForm(); }}>
      <div className="bg-dark-slate rounded border border-slate-700 p-5 w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
          {editMission ? 'Edit Mission' : 'Queue New Mission'}
        </h2>
        {error && <div className="p-2 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs mb-3">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Objective Name</label>
            <input type="text" value={form.title} onChange={e => setForm({...form, title: e.target.value})} placeholder="Secure Arkham perimeter..." className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow" required />
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Description</label>
            <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Tactical details..." className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow h-16 resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 mb-1 font-mono text-[10px]">Threat Level</label>
              <select value={form.priority} onChange={e => setForm({...form, priority: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-2.5 py-2 text-slate-200 focus:outline-none focus:border-electric-bat-yellow">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 mb-1 font-mono text-[10px]">Target Date</label>
              <input type="date" value={form.due_date} onChange={e => setForm({...form, due_date: e.target.value})} className="w-full bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-electric-bat-yellow font-mono" />
            </div>
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Tags (comma-separated)</label>
            <input type="text" value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} placeholder="gotham, arkham, stealth" className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow" />
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Location</label>
            <input type="text" value={form.location} onChange={e => setForm({...form, location: e.target.value})} placeholder="Gotham City - East Side" className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow" />
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Notes</label>
            <textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} placeholder="Classified intel..." className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow h-16 resize-none" />
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono text-[10px]">Subtasks (JSON array of {`{title, done}`})</label>
            <textarea value={form.subtasks} onChange={e => setForm({...form, subtasks: e.target.value})} placeholder='[{&quot;title&quot;:&quot;Scout perimeter&quot;,&quot;done&quot;:false}]' className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow h-12 resize-none font-mono text-[10px]" />
          </div>
          <div className="flex space-x-3 pt-2">
            <button type="submit" disabled={loading} className="flex-1 py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono tracking-widest disabled:opacity-50">
              {loading ? 'SAVING...' : editMission ? 'UPDATE MISSION' : 'LAUNCH PROTOCOL'}
            </button>
            <button type="button" onClick={() => { setShowForm(false); setEditMission(null); resetForm(); }} className="px-4 py-2.5 bg-slate-800 text-slate-300 rounded hover:bg-slate-700 transition font-mono text-[10px]">
              CANCEL
            </button>
          </div>
        </form>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
          <h1 className="text-2xl font-bold tracking-wider">TACTICAL MISSIONS</h1>
          <p className="text-xs text-slate-400">One-time operational objectives. Completing high-priority targets yields maximum resources.</p>
        </div>
        <button onClick={() => { setEditMission(null); resetForm(); setShowForm(true); }} className="px-3 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono text-[10px] tracking-widest">
          + NEW MISSION
        </button>
      </div>

      <div className="flex items-center space-x-2 text-[10px] font-mono">
        <button onClick={() => setViewMode('list')} className={`px-3 py-1.5 rounded border transition ${viewMode === 'list' ? 'bg-dark-slate border-electric-bat-yellow text-electric-bat-yellow' : 'border-slate-800 text-slate-400 hover:border-slate-600'}`}>List</button>
        <button onClick={() => setViewMode('eisenhower')} className={`px-3 py-1.5 rounded border transition ${viewMode === 'eisenhower' ? 'bg-dark-slate border-electric-bat-yellow text-electric-bat-yellow' : 'border-slate-800 text-slate-400 hover:border-slate-600'}`}>Eisenhower</button>
      </div>

      <div className="flex items-center space-x-2 text-[10px] font-mono">
        <button onClick={() => setDateFilter('all')} className={`px-3 py-1.5 rounded border transition ${dateFilter === 'all' ? 'bg-dark-slate border-electric-bat-yellow text-electric-bat-yellow' : 'border-slate-800 text-slate-400 hover:border-slate-600'}`}>All</button>
        <button onClick={() => setDateFilter('today')} className={`px-3 py-1.5 rounded border transition ${dateFilter === 'today' ? 'bg-dark-slate border-electric-bat-yellow text-electric-bat-yellow' : 'border-slate-800 text-slate-400 hover:border-slate-600'}`}>Today</button>
        <button onClick={() => setDateFilter('week')} className={`px-3 py-1.5 rounded border transition ${dateFilter === 'week' ? 'bg-dark-slate border-electric-bat-yellow text-electric-bat-yellow' : 'border-slate-800 text-slate-400 hover:border-slate-600'}`}>This Week</button>
      </div>

      {viewMode === 'eisenhower' ? (
        <EisenhowerQuadrant missions={activeMissions} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} />
      ) : (
        <div className="space-y-3">
          <div className="flex justify-between items-center text-xs font-mono text-slate-500 uppercase tracking-wider px-1">
            <span>Active Missions ({sortedMissions.length})</span>
          </div>
          {sortedMissions.length === 0 ? (
            <div className="bg-dark-slate p-8 text-center rounded border border-slate-800 text-slate-500 font-mono text-xs">ALL SECTORS SECURED. NO ACTIVE OBJECTIVES PLOTTED.</div>
          ) : (
            <div className="space-y-2">
              {sortedMissions.map(m => (
                <MissionCard key={m.id} mission={m} onEdit={openEdit} onDelete={handleDelete} onToggleStatus={handleToggleStatus} onDuplicate={handleDuplicate} onWontDo={handleWontDo} />
              ))}
            </div>
          )}

          {dismissedMissions.length > 0 && (
            <details className="group">
              <summary className="text-[10px] font-mono text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-300 px-1 py-2">
                Won't Do ({dismissedMissions.length})
              </summary>
              <div className="space-y-2 mt-2">
                {dismissedMissions.map(m => (
                  <div key={m.id} className="bg-dark-slate p-3 rounded border border-slate-800 opacity-50 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="text-slate-500 line-through text-xs">{m.title}</span>
                      <button onClick={async () => { try { await api.updateMission(m.id, { is_dismissed: false, status: 'pending' }); onRefreshMissions(); } catch (e) { console.error(e); } }} className="text-[9px] text-slate-600 hover:text-slate-300">(restore)</button>
                    </div>
                    <button onClick={() => handleDelete(m.id)} className="text-slate-600 hover:text-red-500 text-[10px]">✕</button>
                  </div>
                ))}
              </div>
            </details>
          )}

          {completedMissions.length > 0 && (
            <details className="group">
              <summary className="text-[10px] font-mono text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-300 px-1 py-2">
                Completed ({completedMissions.length})
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
    </div>
  );
}

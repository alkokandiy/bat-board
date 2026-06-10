import React, { useState } from 'react';
import { api } from '../utils/api';

export default function MissionsPanel({ missions, onRefreshMissions, onRefreshAccount }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('medium');
  const [dueDate, setDueDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;

    setLoading(true);
    setError(null);
    try {
      await api.createMission({
        title,
        description: description.trim() || null,
        priority,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
        status: 'pending'
      });
      setTitle('');
      setDescription('');
      setPriority('medium');
      setDueDate('');
      await onRefreshMissions();
      await onRefreshAccount();
    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to create mission.");
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
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Are you sure you want to decommission this mission?")) return;
    try {
      await api.deleteMission(id);
      await onRefreshMissions();
      await onRefreshAccount();
    } catch (err) {
      console.error(err);
    }
  };

  // Sort: pending first, then by priority (critical > high > medium > low)
  const priorityWeight = { critical: 4, high: 3, medium: 2, low: 1 };
  const sortedMissions = [...missions].sort((a, b) => {
    if (a.status === 'completed' && b.status !== 'completed') return 1;
    if (a.status !== 'completed' && b.status === 'completed') return -1;
    return (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0);
  });

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">TACTICAL MISSIONS</h1>
        <p className="text-xs text-slate-400">One-time operational objectives. Completing high-priority targets yields maximum resources.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Creation Form */}
        <div className="bg-dark-slate p-5 rounded border border-slate-800 h-fit space-y-4">
          <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
            Queue New Mission
          </h2>
          
          {error && (
            <div className="p-3 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Objective Name</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Secure Arkham perimeter..."
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow"
                required
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Description (Optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Analyze intelligence logs for suspicious active nodes."
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow h-20 resize-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Threat Level</label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  className="w-full bg-matte-obsidian border border-slate-800 rounded px-2.5 py-2 text-slate-200 focus:outline-none focus:border-electric-bat-yellow"
                >
                  <option value="low">Low Threat</option>
                  <option value="medium">Medium Threat</option>
                  <option value="high">High Threat</option>
                  <option value="critical">Critical (Boss)</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Target Date</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-200 focus:outline-none focus:border-electric-bat-yellow font-mono"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono tracking-widest disabled:opacity-50"
            >
              {loading ? "INITIALIZING..." : "LAUNCH PROTOCOL"}
            </button>
          </form>
        </div>

        {/* Missions Directory */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex justify-between items-center text-xs font-mono text-slate-500 uppercase tracking-wider px-1">
            <span>Missions Queue</span>
            <span>{missions.filter(m => m.status === 'pending').length} ACTIVE</span>
          </div>

          <div className="space-y-2.5">
            {sortedMissions.length === 0 ? (
              <div className="bg-dark-slate p-8 text-center rounded border border-slate-800 text-slate-500 font-mono text-xs">
                ALL SECTORS SECURED. NO ACTIVE OBJECTIVES PLOTTED.
              </div>
            ) : (
              sortedMissions.map((mission) => {
                const isCompleted = mission.status === 'completed';
                
                const priorityStyles = {
                  low: 'bg-slate-800/60 text-slate-400 border-slate-800',
                  medium: 'bg-blue-950/20 text-blue-400 border-blue-900/30',
                  high: 'bg-amber-950/20 text-amber-400 border-amber-900/30',
                  critical: 'bg-red-950/30 text-red-500 border-red-900/40 font-bold animate-pulse'
                };

                return (
                  <div
                    key={mission.id}
                    className={`bg-dark-slate p-4 rounded border transition-all duration-200 flex items-start justify-between gap-4 ${
                      isCompleted ? 'border-slate-900 opacity-60' : 'border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start space-x-3.5">
                      <button
                        onClick={() => handleToggleStatus(mission)}
                        className={`w-5 h-5 rounded border mt-0.5 flex items-center justify-center shrink-0 transition ${
                          isCompleted
                            ? 'bg-electric-bat-yellow border-electric-bat-yellow text-matte-obsidian'
                            : 'border-slate-700 hover:border-electric-bat-yellow'
                        }`}
                      >
                        {isCompleted && <span className="text-xs font-bold">✓</span>}
                      </button>

                      <div>
                        <div className="flex items-center space-x-2.5">
                          <h3 className={`text-sm font-semibold tracking-wide ${isCompleted ? 'line-through text-slate-500' : 'text-slate-200'}`}>
                            {mission.title}
                          </h3>
                          <span className={`text-[9px] uppercase tracking-wider px-2 py-0.5 rounded border ${priorityStyles[mission.priority] || ''}`}>
                            {mission.priority}
                          </span>
                        </div>
                        {mission.description && (
                          <p className={`text-xs mt-1 ${isCompleted ? 'text-slate-600' : 'text-slate-400'}`}>
                            {mission.description}
                          </p>
                        )}
                        {mission.due_date && (
                          <div className="text-[10px] text-slate-500 font-mono mt-1.5 flex items-center space-x-1">
                            <span>🎯 Target:</span>
                            <span>{new Date(mission.due_date).toLocaleDateString()}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <button
                      onClick={() => handleDelete(mission.id)}
                      className="text-slate-600 hover:text-red-500 transition text-xs font-mono tracking-widest"
                      title="Decommission mission"
                    >
                      ✕
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

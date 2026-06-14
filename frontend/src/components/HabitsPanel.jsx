import React, { useState } from 'react';
import { api } from '../utils/api';

export default function HabitsPanel({ habits = [], onRefreshHabits, onRefreshAccount }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [frequency, setFrequency] = useState('daily');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setError(null);
    try {
      await api.createHabit({
        name,
        description: description.trim() || null,
        frequency
      });
      setName('');
      setDescription('');
      setFrequency('daily');
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to create habit.");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckIn = async (habitId) => {
    try {
      setActionError(null);
      await api.checkInHabit(habitId);
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      setActionError(err.message || "Check-in failed");
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Are you sure you want to delete this recurring ritual?")) return;
    try {
      setActionError(null);
      await api.deleteHabit(id);
      await onRefreshHabits();
      await onRefreshAccount();
    } catch (err) {
      setActionError(err.message || "Delete failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">RECURRING RITUALS</h1>
        <p className="text-xs text-slate-400">Regular training loops keeping the body and mind razor sharp. Maintain active streaks to amplify resource yields.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Creation Form */}
        <div className="bg-dark-slate p-5 rounded border border-slate-800 h-fit space-y-4">
          <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
            Establish Ritual
          </h2>
          
          {error && (
            <div className="p-3 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Ritual Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Strength conditioning (50 reps)..."
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow"
                required
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Description (Optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Power workout or visual surveillance analysis check."
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow h-20 resize-none"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Frequency</label>
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-2.5 py-2 text-slate-200 focus:outline-none focus:border-electric-bat-yellow"
              >
                <option value="daily">Daily Loop</option>
                <option value="weekly">Weekly Loop</option>
                <option value="monthly">Monthly Loop</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono tracking-widest disabled:opacity-50"
            >
              {loading ? "COMMITTING..." : "LOG PROTOCOL"}
            </button>
          </form>
        </div>

        {/* Habits List */}
        <div className="lg:col-span-2 space-y-3">
          {actionError && (
            <div className="p-3 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs">
              {actionError}
            </div>
          )}
          <div className="flex justify-between items-center text-xs font-mono text-slate-500 uppercase tracking-wider px-1">
            <span>Active Rituals</span>
            <span>{habits.length} LOGGED</span>
          </div>

          <div className="space-y-2.5">
            {habits.length === 0 ? (
              <div className="bg-dark-slate p-8 text-center rounded border border-slate-800 text-slate-500 font-mono text-xs">
                NO RITUAL LOOPS ENGAGED. CONFIGURE A NEW ROUTINE TO BEGIN TRAINING.
              </div>
            ) : (
              habits.map((habit) => {
                const now = new Date();
                const todayUTC = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
                const lastCompletedUTC = habit.last_completed 
                  ? Date.UTC(
                      new Date(habit.last_completed).getFullYear(),
                      new Date(habit.last_completed).getMonth(),
                      new Date(habit.last_completed).getDate()
                    )
                  : null;
                const checkedToday = lastCompletedUTC === todayUTC;

                return (
                  <div
                    key={habit.id}
                    className="bg-dark-slate p-4 rounded border border-slate-800 hover:border-slate-700 transition flex items-center justify-between gap-4"
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center space-x-3">
                        <h3 className="text-sm font-semibold tracking-wide text-slate-200">
                          {habit.name}
                        </h3>
                        <span className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-800 font-mono">
                          {habit.frequency}
                        </span>
                      </div>
                      
                      {habit.description && (
                        <p className="text-xs text-slate-400">
                          {habit.description}
                        </p>
                      )}

                      <div className="flex items-center space-x-4 pt-1 text-[10px] font-mono">
                        <div className="flex items-center space-x-1">
                          <span className="text-slate-500">🔥 Streak:</span>
                          <span className={`${habit.streak > 0 ? 'text-orange-500 font-bold' : 'text-slate-400'}`}>
                            {habit.streak} {habit.streak === 1 ? 'day' : 'days'}
                          </span>
                        </div>
                        
                        {habit.streak > 2 && (
                          <span className="text-[9px] bg-orange-950/20 text-orange-400 border border-orange-950 px-1.5 py-0.5 rounded uppercase tracking-wider">
                            ON FIRE ⚡
                          </span>
                        )}

                        {habit.last_completed && (
                          <div className="text-slate-500">
                            Last checked: {new Date(habit.last_completed).toLocaleDateString()}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      <button
                        onClick={() => handleCheckIn(habit.id)}
                        disabled={checkedToday}
                        className={`px-4 py-2 rounded text-xs font-bold font-mono tracking-wider border transition duration-200 ${
                          checkedToday
                            ? 'bg-emerald-950/20 text-emerald-400 border-emerald-900/30 cursor-not-allowed'
                            : 'bg-electric-bat-yellow text-matte-obsidian border-electric-bat-yellow hover:bg-yellow-400'
                        }`}
                      >
                        {checkedToday ? 'COMPLETED' : 'CHECK IN'}
                      </button>

                      <button
                        onClick={() => handleDelete(habit.id)}
                        className="text-slate-600 hover:text-red-500 transition text-xs font-mono px-1.5 py-1"
                        title="Delete ritual"
                      >
                        ✕
                      </button>
                    </div>
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

import React from 'react';
import { trackPresets } from './AudioPlayer';
import BatFocusTimer from './BatFocusTimer';

export default function FocusPanel({
  activeTrack,
  isPlaying,
  onTrackChange,
  missions,
  habits,
  onRefreshMissions,
  onRefreshHabits,
  onRefreshAccount,
  onFocusModeChange,
  focusMode,
  focusTimeLeft,
  focusTotalTime,
  focusRunning,
  focusSessionLength,
  focusSelectedMissionId,
  focusSelectedHabitId,
  onFocusMissionChange,
  onFocusHabitChange,
  onFocusToggle,
  onFocusAdjustTime,
  onFocusSessionChange,
  onFocusReset,
  onFocusExit,
}) {
  const selectedMission = missions.find(m => String(m.id) === focusSelectedMissionId);
  const missionName = selectedMission ? selectedMission.title : '';

  if (focusMode) {
    return (
      <BatFocusTimer
        timeLeft={focusTimeLeft}
        totalTime={focusTotalTime}
        running={focusRunning}
        onToggleRunning={onFocusToggle}
        onAdjustTime={onFocusAdjustTime}
        onClose={onFocusExit}
        missionName={missionName}
        activeTrack={activeTrack}
        isPlaying={isPlaying}
        onTrackChange={onTrackChange}
        onFocusModeChange={onFocusModeChange}
        initialFocusActive={true}
      />
    );
  }

  const handleSessionChange = (e) => {
    const value = Math.max(1, Math.min(180, parseInt(e.target.value) || 1));
    onFocusSessionChange(value);
  };

  const handleTrackSelect = (track) => {
    if (activeTrack?.id === track.id && isPlaying) {
      onTrackChange(null);
    } else {
      onTrackChange(track);
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">FOCUS HOURGLASS</h1>
        <p className="text-xs text-slate-400">Lock yourself into cognitive isolation. Power through deep work with zero external interruptions.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <BatFocusTimer
            timeLeft={focusTimeLeft}
            totalTime={focusTotalTime}
            running={focusRunning}
            onToggleRunning={onFocusToggle}
            onAdjustTime={onFocusAdjustTime}
            missionName={missionName}
            activeTrack={activeTrack}
            isPlaying={isPlaying}
            onTrackChange={onTrackChange}
            onFocusModeChange={onFocusModeChange}
          />
        </div>

        <div className="bg-dark-slate p-6 rounded border border-slate-800 space-y-6">
          <div className="space-y-4">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
              Parameters
            </h2>
            <div className="text-xs">
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Mission Target</label>
              <select
                value={focusSelectedMissionId}
                onChange={e => onFocusMissionChange(e.target.value)}
                disabled={focusRunning}
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow disabled:opacity-50"
              >
                <option value="">— No Mission —</option>
                {missions.filter(m => m.status !== 'completed' && !m.is_dismissed).map(m => (
                  <option key={m.id} value={m.id}>{m.title}</option>
                ))}
              </select>
            </div>
            <div className="text-xs">
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Habit Target</label>
              <select
                value={focusSelectedHabitId}
                onChange={e => onFocusHabitChange(e.target.value)}
                disabled={focusRunning}
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow disabled:opacity-50"
              >
                <option value="">— No Habit —</option>
                {habits.filter(h => h.streak >= 0).map(h => (
                  <option key={h.id} value={h.id}>{h.name}</option>
                ))}
              </select>
            </div>
            <div className="text-xs">
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Session Length (Minutes)</label>
              <input
                type="number"
                min="1"
                max="180"
                value={focusSessionLength}
                onChange={handleSessionChange}
                disabled={focusRunning}
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow disabled:opacity-50"
              />
            </div>
          </div>

          <div className="space-y-4">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
              Soundtrack
            </h2>
            <div className="text-xs space-y-2">
              {trackPresets.map((track) => {
                const isSelected = activeTrack?.id === track.id;
                return (
                  <button
                    key={track.id}
                    onClick={() => handleTrackSelect(track)}
                    className={`w-full text-left px-3.5 py-2.5 rounded border transition flex items-center justify-between ${
                      isSelected
                        ? 'bg-electric-bat-yellow/10 border-electric-bat-yellow text-electric-bat-yellow'
                        : 'bg-matte-obsidian border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <span className="font-semibold text-[11px] tracking-wide truncate">{track.title}</span>
                    <span className="text-[10px] font-mono">{isSelected && isPlaying ? 'PLAYING' : isSelected ? 'PAUSED' : 'OFFLINE'}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

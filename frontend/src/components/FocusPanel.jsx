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
  timerMode,
  onTimerModeChange,
  focusMode,
  focusTimeLeft,
  focusTotalTime,
  focusRunning,
  focusSessionLength,
  focusSelectedMissionId,
  focusSelectedHabitId,
  focusNotice,
  onFocusMissionChange,
  onFocusHabitChange,
  onFocusToggle,
  onFocusAdjustTime,
  onFocusSessionChange,
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
        missionName={missionName}
        activeTrack={activeTrack}
        isPlaying={isPlaying}
        onTrackChange={onTrackChange}
        onFocusModeChange={onFocusModeChange}
        mode={timerMode}
        onModeChange={onTimerModeChange}
        initialFocusActive={true}
      />
    );
  }

  const handleSessionChange = (e) => {
    const value = Math.max(5, Math.min(180, parseInt(e.target.value) || 5));
    onFocusSessionChange(value);
  };

  // One target only: a mission OR a habit, never both. Encode the choice as
  // "m:<id>" / "h:<id>" and clear the other side on change.
  const targetValue = focusSelectedMissionId
    ? `m:${focusSelectedMissionId}`
    : focusSelectedHabitId ? `h:${focusSelectedHabitId}` : '';
  const handleTargetChange = (e) => {
    const v = e.target.value;
    if (v.startsWith('m:')) { onFocusMissionChange(v.slice(2)); onFocusHabitChange(''); }
    else if (v.startsWith('h:')) { onFocusHabitChange(v.slice(2)); onFocusMissionChange(''); }
    else { onFocusMissionChange(''); onFocusHabitChange(''); }
  };
  const openMissions = missions.filter(m => m.status !== 'completed' && !m.is_dismissed);

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

      {focusNotice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs text-amber-300 font-mono">
          {focusNotice}
        </div>
      )}

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
            mode={timerMode}
            onModeChange={onTimerModeChange}
          />
        </div>

        <div className="bg-dark-slate p-6 rounded border border-slate-800 space-y-6">
          <div className="space-y-4">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
              Parameters
            </h2>
            <div className="text-xs">
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Focus Target</label>
              <select
                value={targetValue}
                onChange={handleTargetChange}
                disabled={focusRunning}
                className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow disabled:opacity-50"
              >
                <option value="">— No target (free focus) —</option>
                {openMissions.length > 0 && (
                  <optgroup label="Missions">
                    {openMissions.map(m => (
                      <option key={`m${m.id}`} value={`m:${m.id}`}>{m.title}</option>
                    ))}
                  </optgroup>
                )}
                {habits.length > 0 && (
                  <optgroup label="Habits">
                    {habits.map(h => (
                      <option key={`h${h.id}`} value={`h:${h.id}`}>{h.name}</option>
                    ))}
                  </optgroup>
                )}
              </select>
              <p className="mt-1 text-[10px] text-slate-500 font-mono">One target per session — a mission or a habit.</p>
            </div>
            <div className="text-xs">
              <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Session Length (Minutes)</label>
              <input
                type="number"
                min="5"
                max="180"
                step="5"
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

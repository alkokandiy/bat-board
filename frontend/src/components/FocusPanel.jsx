import React from 'react';
import { trackPresets } from './AudioPlayer';
import BatFocusTimer from './BatFocusTimer';
import { PageHeader, Panel, Picker } from './ui';

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
  focusSuggestion,
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
  const handleTargetChange = (v) => {
    if (v.startsWith('m:')) { onFocusMissionChange(v.slice(2)); onFocusHabitChange(''); }
    else if (v.startsWith('h:')) { onFocusHabitChange(v.slice(2)); onFocusMissionChange(''); }
    else { onFocusMissionChange(''); onFocusHabitChange(''); }
  };
  const openMissions = missions.filter(m => m.status !== 'completed' && !m.is_dismissed);
  // Built here rather than inside the Picker so the encoding ("m:<id>") stays
  // in the one place that also decodes it.
  const targetGroups = [
    ...(openMissions.length
      ? [{ label: 'Missions', options: openMissions.map(m => ({ value: `m:${m.id}`, label: m.title })) }]
      : []),
    ...(habits.length
      ? [{ label: 'Habits', options: habits.map(h => ({ value: `h:${h.id}`, label: h.name })) }]
      : []),
  ];

  const selectedHabit = habits.find(h => String(h.id) === focusSelectedHabitId);
  const targetLabel = selectedMission ? selectedMission.title
    : selectedHabit ? selectedHabit.name : '';

  // Where the default came from. A bare "25" is the folklore this replaced;
  // their own median is the only defensible recommendation, and saying which
  // it is keeps the honesty of it visible.
  const lengthHint = !focusSuggestion ? null
    : focusSuggestion.basis === 'history'
      ? `Your usual session is ${focusSuggestion.minutes} min, across ${focusSuggestion.sessions} logged.`
      : 'A starting point — this becomes your own median once you have a few sessions logged.';

  const handleTrackSelect = (track) => {
    if (activeTrack?.id === track.id && isPlaying) {
      onTrackChange(null);
    } else {
      onTrackChange(track);
    }
  };

  return (
    <div className="space-y-6">
      {/* The old line — "Lock yourself into cognitive isolation" — described
          nothing about this session. These are the settings you are about to
          start with. */}
      <PageHeader
        title="FOCUS HOURGLASS"
        stats={[
          { label: 'minutes', value: focusSessionLength },
          // PageHeader renders value-then-label, so the preposition belongs
          // in the value or it reads "Review the tracker on".
          targetLabel
            ? { label: '', value: `on ${targetLabel}`, tone: 'self' }
            : { label: '', value: 'free focus' },
        ]}
      />

      {focusNotice && (
        <div className="rounded-lg border border-signal-warn/40 bg-signal-warn/10 px-4 py-2 text-xs text-signal-warn font-mono">
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

          {/* Three tracks in a row, under the clock, rather than a stack in
              the side column. Three one-line buttons never needed a column
              of their own, and holding one there squeezed the focus target
              above it into a few rows. */}
          <Panel title="Soundtrack" className="mt-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              {trackPresets.map((track) => {
                const isSelected = activeTrack?.id === track.id;
                return (
                  <button
                    key={track.id}
                    onClick={() => handleTrackSelect(track)}
                    className={`text-left px-3.5 py-2.5 rounded-tile border transition-all duration-200 ease-soft ${
                      isSelected
                        ? 'bg-signal-self/10 border-signal-self text-signal-self'
                        : 'bg-bat-raised border-bat-line text-ink-muted hover:border-bat-line-strong hover:text-ink'
                    }`}
                  >
                    <span className="block font-semibold text-[11px] tracking-wide truncate">{track.title}</span>
                    <span className="mt-0.5 block text-[10px] font-mono text-ink-faint">
                      {isSelected && isPlaying ? 'PLAYING' : isSelected ? 'PAUSED' : 'OFFLINE'}
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Parameters">
            <div className="text-xs">
              {/* A labelled group, not a <label>: the control is a button,
                  and the browser-drawn <select> this replaced could not be
                  styled, searched, or stopped from running off the screen. */}
              <span className="block text-ink-muted mb-1 font-mono uppercase tracking-wider text-[10px]">Focus Target</span>
              <Picker
                label="Focus Target"
                value={targetValue}
                onChange={handleTargetChange}
                disabled={focusRunning}
                emptyOption={{ value: '', label: '— No target (free focus) —' }}
                groups={targetGroups}
              />
              <p className="mt-1 text-[10px] text-ink-faint font-mono">One target per session — a mission or a habit.</p>
            </div>
            <div className="text-xs">
              <label className="block text-ink-muted mb-1 font-mono uppercase tracking-wider text-[10px]">Session Length (Minutes)</label>
              <input
                type="number"
                min="5"
                max="180"
                step="5"
                value={focusSessionLength}
                onChange={handleSessionChange}
                disabled={focusRunning}
                className="w-full bg-bat-raised border border-bat-line rounded px-3 py-2 text-ink font-mono focus:outline-none focus:border-signal-self disabled:opacity-50"
              />
              {lengthHint && (
                <p className="mt-1 text-[10px] text-ink-faint leading-relaxed">{lengthHint}</p>
              )}
            </div>
          </Panel>

        </div>
      </div>
    </div>
  );
}

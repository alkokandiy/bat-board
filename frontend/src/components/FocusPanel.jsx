import React, { useState, useEffect, useRef } from 'react';
import { trackPresets } from './AudioPlayer';
import { api } from '../utils/api';
import BatFocusTimer from './BatFocusTimer';

export default function FocusPanel({ activeTrack, isPlaying, onTrackChange, missions, habits, onRefreshMissions, onRefreshHabits, onRefreshAccount, onFocusModeChange, focusMode }) {
  const [timeLeft, setTimeLeft] = useState(25 * 60);
  const [isActive, setIsActive] = useState(false);
  const [sessionLength, setSessionLength] = useState(25);
  const [selectedMissionId, setSelectedMissionId] = useState('');
  const [selectedHabitId, setSelectedHabitId] = useState('');

  const timerRef = useRef(null);
  const focusSessionIdRef = useRef(null);
  const sessionLengthRef = useRef(sessionLength);
  sessionLengthRef.current = sessionLength;
  const wakeLockRef = useRef(null);

  const releaseWakeLock = async () => {
    if (wakeLockRef.current) {
      try { await wakeLockRef.current.release(); } catch {}
      wakeLockRef.current = null;
    }
  };

  const requestWakeLock = async () => {
    try {
      wakeLockRef.current = await navigator.wakeLock.request('screen');
    } catch {}
  };

  const endSession = useRef(async () => {
    const sid = focusSessionIdRef.current;
    if (!sid) return;
    focusSessionIdRef.current = null;
    try {
      await api.endFocusSession(sid, { duration_minutes: sessionLengthRef.current });
      onRefreshMissions();
      onRefreshAccount();
    } catch (err) {
      console.error(err);
    }
  }).current;

  const exitFocusMode = async () => {
    await releaseWakeLock();
    onFocusModeChange(false);
    if (document.fullscreenElement) await document.exitFullscreen();
  };

  useEffect(() => {
    if (!isActive) return;
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          setIsActive(false);
          endSession();
          exitFocusMode();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [isActive, endSession]);

  const enterFocusMode = async () => {
    await requestWakeLock();
    onFocusModeChange(true);
    try { await document.documentElement.requestFullscreen(); } catch {}
  };

  const startSession = async () => {
    try {
      const data = {};
      if (selectedMissionId) data.mission_id = parseInt(selectedMissionId);
      if (selectedHabitId) data.habit_id = parseInt(selectedHabitId);
      const session = await api.startFocusSession(data);
      focusSessionIdRef.current = session.id;
    } catch (err) {
      console.error(err);
    }
  };

  const toggleTimer = () => {
    if (!isActive) {
      if (timeLeft === 0) {
        setTimeLeft(sessionLength * 60);
      }
      startSession();
      enterFocusMode();
    }
    setIsActive(!isActive);
  };

  const resetTimer = async () => {
    clearInterval(timerRef.current);
    if (isActive) {
      const sid = focusSessionIdRef.current;
      if (sid) {
        focusSessionIdRef.current = null;
        try {
          await api.endFocusSession(sid, { duration_minutes: sessionLength });
        } catch (err) {
          console.error(err);
        }
        onRefreshMissions();
        onRefreshAccount();
      }
    }
    await exitFocusMode();
    setIsActive(false);
    setTimeLeft(sessionLength * 60);
  };

  const handleSessionChange = (e) => {
    const value = Math.max(1, Math.min(180, parseInt(e.target.value) || 1));
    setSessionLength(value);
    if (!isActive) setTimeLeft(value * 60);
  };

  const handleTrackSelect = (track) => {
    if (activeTrack?.id === track.id && isPlaying) {
      onTrackChange(null);
    } else {
      onTrackChange(track);
    }
  };

  const selectedMission = missions.find(m => String(m.id) === selectedMissionId);
  const missionName = selectedMission ? selectedMission.title : '';

  if (focusMode) {
    return (
      <BatFocusTimer
        timeLeft={timeLeft}
        totalTime={sessionLength * 60}
        running={isActive}
        onToggleRunning={toggleTimer}
        onAdjustTime={(delta) => setTimeLeft(prev => Math.max(0, prev + delta))}
        onClose={exitFocusMode}
        missionName={missionName}
        activeTrack={activeTrack}
        isPlaying={isPlaying}
        onTrackChange={onTrackChange}
        onFocusModeChange={onFocusModeChange}
        initialFocusActive={true}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">FOCUS HOURGLASS</h1>
        <p className="text-xs text-slate-400">Lock yourself into cognitive isolation. Power through deep work with zero external interruptions.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <BatFocusTimer
            timeLeft={timeLeft}
            totalTime={sessionLength * 60}
            running={isActive}
            onToggleRunning={toggleTimer}
            onAdjustTime={(delta) => setTimeLeft(prev => Math.max(0, prev + delta))}
            missionName={missionName} // Pass mission name for compact view as well
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
                value={selectedMissionId}
                onChange={e => setSelectedMissionId(e.target.value)}
                disabled={isActive}
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
                value={selectedHabitId}
                onChange={e => setSelectedHabitId(e.target.value)}
                disabled={isActive}
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
                value={sessionLength}
                onChange={handleSessionChange}
                disabled={isActive}
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

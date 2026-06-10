import React, { useState, useEffect, useRef } from 'react';

const trackPresets = [
  { id: 1, title: "Batmusic #1", src: "/tracks/track1.mp3" },
  { id: 2, title: "Batmusic #2", src: "/tracks/track2.mp3" },
  { id: 3, title: "Batmusic #3", src: "/tracks/track3.mp3" },
];

export default function FocusPanel() {
  const [timeLeft, setTimeLeft] = useState(25 * 60);
  const [isActive, setIsActive] = useState(false);
  const [sessionLength, setSessionLength] = useState(25);
  const [activeTrack, setActiveTrack] = useState(null);
  const [trackError, setTrackError] = useState(false);

  const timerRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    if (isActive && timeLeft > 0) {
      timerRef.current = setInterval(() => {
        setTimeLeft((prev) => prev - 1);
      }, 1000);
    } else if (timeLeft === 0) {
      clearInterval(timerRef.current);
      setIsActive(false);
    }
    return () => clearInterval(timerRef.current);
  }, [isActive, timeLeft]);

  useEffect(() => {
    if (audioRef.current) {
      if (activeTrack) {
        setTrackError(false);
        audioRef.current.src = activeTrack.src;
        audioRef.current.loop = true;
        audioRef.current.play().catch(() => setTrackError(true));
      } else {
        audioRef.current.pause();
        audioRef.current.src = "";
        setTrackError(false);
      }
    }
  }, [activeTrack]);

  const toggleTimer = () => {
    if (!isActive && timeLeft === 0) {
      setTimeLeft(sessionLength * 60);
    }
    setIsActive(!isActive);
  };

  const resetTimer = () => {
    clearInterval(timerRef.current);
    setIsActive(false);
    setTimeLeft(sessionLength * 60);
  };

  const handleSessionChange = (e) => {
    const value = Math.max(1, Math.min(180, parseInt(e.target.value) || 1));
    setSessionLength(value);
    if (!isActive) setTimeLeft(value * 60);
  };

  const handleTrackSelect = (track) => {
    setActiveTrack((prev) => (prev?.id === track.id ? null : track));
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const progress = sessionLength > 0 ? (timeLeft / (sessionLength * 60)) * 100 : 0;

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">FOCUS HOURGLASS</h1>
        <p className="text-xs text-slate-400">Lock yourself into cognitive isolation. Power through deep work with zero external interruptions.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-dark-slate p-8 rounded border border-slate-800 flex flex-col items-center justify-center space-y-6">
          <div className="text-center">
            <span className="text-slate-500 text-[10px] font-mono uppercase tracking-widest">Cognitive State Isolation</span>
            <div className="text-7xl font-bold font-mono tracking-widest text-slate-100 mt-2 select-none">
              {formatTime(timeLeft)}
            </div>
            <div className="h-1.5 w-64 bg-matte-obsidian rounded-full overflow-hidden mt-4 mx-auto border border-slate-800">
              <div
                className="h-full bg-electric-bat-yellow transition-all duration-300"
                style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
              />
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={toggleTimer}
              className={`px-8 py-3 rounded text-xs font-bold font-mono tracking-widest transition duration-200 ${
                isActive
                  ? 'bg-amber-950/20 text-amber-500 border border-amber-900/30 hover:bg-amber-950/40'
                  : 'bg-electric-bat-yellow text-matte-obsidian hover:bg-yellow-400 font-extrabold'
              }`}
            >
              {isActive ? 'SUSPEND FLOW' : 'ENGAGE INTENSITY'}
            </button>
            <button
              onClick={resetTimer}
              className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-bold font-mono tracking-widest border border-slate-800 transition"
            >
              REBOOT
            </button>
          </div>
        </div>

        <div className="bg-dark-slate p-6 rounded border border-slate-800 space-y-6">
          <div className="space-y-4">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2">
              Parameters
            </h2>
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
                    <span className="text-[10px] font-mono">{isSelected ? 'ON AIR' : 'OFFLINE'}</span>
                  </button>
                );
              })}
            </div>
            {trackError && (
              <p className="text-[10px] text-amber-400 font-mono text-center">
                Audio file not found. Place .mp3 files in public/tracks/.
              </p>
            )}
          </div>
        </div>
      </div>

      <audio ref={audioRef} preload="auto" />
    </div>
  );
}
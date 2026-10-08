import React, { useState, useEffect, useRef, useLayoutEffect, useMemo, useCallback, Suspense, lazy } from 'react';
import { trackPresets } from './AudioPlayer';
import FlipDigit from './timer/FlipDigit';
import BatEmblem from './timer/BatEmblem';

// three.js is heavy: load the 3D Batmobile only when that mode is opened. If
// the chunk can't load, fall back to the 2D car instead of crashing the timer.
const Batmobile3D = lazy(() =>
  import('./timer/Batmobile3D').catch(() => ({
    default: function Batmobile3DLoadFailed({ onUnsupported }) {
      useEffect(() => { onUnsupported?.(); }, [onUnsupported]);
      return null;
    },
  })),
);

// Colon Separator Component
function ColonSeparator({ running }) {
  return (
    <div className="flex flex-col gap-[10px] mx-[16px] items-center justify-center">
      <div
        className="w-[6px] h-[16px] rounded-[3px]"
        style={{
          background: 'var(--yellow-core)',
          opacity: 0.9,
          animation: running ? 'colonBlink 800ms ease infinite' : 'none',
        }}
      />
      <div
        className="w-[6px] h-[16px] rounded-[3px]"
        style={{
          background: 'var(--yellow-core)',
          opacity: 0.9,
          animation: running ? 'colonBlink 800ms ease infinite' : 'none',
        }}
      />
    </div>
  );
}

// ==========================================
// MAIN BAT FOCUS TIMER COMPONENT
// ==========================================
export default function BatFocusTimer({
  timeLeft: propTimeLeft,
  totalTime: propTotalTime,
  running: propRunning,
  onToggleRunning,
  onAdjustTime,
  missionName = '',
  activeTrack,
  isPlaying,
  onTrackChange = () => {},
  onFocusModeChange,
  mode: propMode,
  onModeChange,
  initialFocusActive = false,
}) {
  const [internalTimeLeft, setInternalTimeLeft] = useState(25 * 60);
  const [internalTotalTime, setInternalTotalTime] = useState(25 * 60);
  const [internalRunning, setInternalRunning] = useState(false);
  // 'N' | 'F' | 'B' | 'M'. Controlled when the parent passes `mode`
  // (so the choice survives the focus-mode remount and reaches the session
  // start); otherwise the timer keeps its own state.
  const [internalMode, setInternalMode] = useState('N');
  const mode = propMode ?? internalMode;
  const setMode = (m) => {
    setInternalMode(m);
    onModeChange?.(m);
  };
  const [focusActive, setFocusActive] = useState(initialFocusActive);
  const [batmobile3dFailed, setBatmobile3dFailed] = useState(false);
  const handleBatmobile3dUnsupported = useCallback(() => setBatmobile3dFailed(true), []);

  // Car container width measurement for Mode [M]
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(600);

  useLayoutEffect(() => {
    if (!containerRef.current) return;
    const measure = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.getBoundingClientRect().width);
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [mode, focusActive]);

  // Track whether we're in real browser fullscreen vs the software overlay only
  const [isNativeFullscreen, setIsNativeFullscreen] = useState(false);

  // Keep focusActive synced when native fullscreen is entered/exited (Esc, F11).
  // Exiting native fullscreen must NOT exit focus mode — the overlay is a
  // software overlay that stays up until the explicit EXIT FOCUS button.
  useEffect(() => {
    const handler = () => {
      setIsNativeFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const enterFocus = async () => {
    try {
      await document.documentElement.requestFullscreen?.();
    } catch {
      // Fullscreen unavailable/blocked (e.g. iOS Safari) — proceed with the
      // software overlay only. It's a valid degraded mode; we just don't
      // pretend native fullscreen succeeded.
    }
    if (!running) {
      if (onToggleRunning) onToggleRunning();
      else setInternalRunning(true);
    }
    setFocusActive(true);
    onFocusModeChange?.(true);
  };

  const exitFocus = () => {
    setFocusActive(false);
    onFocusModeChange?.(false);
    // Live check guards the race where fullscreenchange hasn't fired yet
    // (isNativeFullscreen state may still be stale right after entering).
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    }
    // Does NOT stop timer!
  };

  const isControlled = propTimeLeft !== undefined;
  const timeLeft = isControlled ? propTimeLeft : internalTimeLeft;
  const totalTime = isControlled ? (propTotalTime || 25 * 60) : internalTotalTime;
  const running = isControlled ? propRunning : internalRunning;

  // Wake Lock: prevent screen sleep during focus mode.
  // Declared after `running` — the dep array must not reference a TDZ binding.
  const wakeLockRef = useRef(null);
  useEffect(() => {
    if (focusActive && running) {
      let cancelled = false;
      let lock = null;
      (async () => {
        try {
          lock = await navigator.wakeLock.request('screen');
          if (cancelled) {
            lock.release();
            lock = null;
          } else {
            wakeLockRef.current = lock;
          }
        } catch {
          // Wake Lock not supported or denied — silent fail
        }
      })();
      return () => {
        cancelled = true;
        if (lock) lock.release();
        wakeLockRef.current = null;
      };
    } else {
      wakeLockRef.current?.release();
      wakeLockRef.current = null;
    }
  }, [focusActive, running]);

  // Internal countdown timer if uncontrolled
  useEffect(() => {
    if (isControlled || !internalRunning) return;
    const interval = setInterval(() => {
      setInternalTimeLeft((prev) => {
        if (prev <= 1) {
          setInternalRunning(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isControlled, internalRunning]);

  const progress = Math.min(100, Math.max(0, Math.round((1 - timeLeft / totalTime) * 100)));

  const fmt = (s) => [Math.floor(s / 60), s % 60].map((n) => String(n).padStart(2, '0')).join(':');
  const formattedTime = fmt(timeLeft);

  // Digits for Flip Clock (displayed minutes capped at 99 so each digit card
  // always holds a single character; the countdown itself continues past that)
  const minutesShown = Math.min(99, Math.floor(timeLeft / 60));
  const minTens = String(Math.floor(minutesShown / 10));
  const minUnits = String(minutesShown % 10);
  const secTens = String(Math.floor((timeLeft % 60) / 10));
  const secUnits = String(timeLeft % 10);

  const handleAdjustTime = (delta) => {
    if (onAdjustTime) {
      onAdjustTime(delta);
    } else {
      setInternalTimeLeft((prev) => {
        const nextTime = Math.max(0, prev + delta);
        if (nextTime > internalTotalTime) setInternalTotalTime(nextTime);
        return nextTime;
      });
    }
  };

  const toggleRunning = () => {
    if (onToggleRunning) {
      onToggleRunning();
    } else {
      if (internalTimeLeft === 0) {
        setInternalTimeLeft(internalTotalTime > 0 ? internalTotalTime : 25 * 60);
      }
      setInternalRunning(!internalRunning);
    }
  };

  // Batmobile position calculation (Part 8)
  const CAR_WIDTH = 280;
  const maxTravel = Math.max(0, containerWidth - CAR_WIDTH);
  const carX = Math.round((progress / 100) * maxTravel);

  // Common Keyframe Styles
  const globalStyles = (
    <style>{`
      @keyframes colonBlink {
        0%, 100% { opacity: 0.9; }
        50%      { opacity: 0.15; }
      }
      @keyframes batFlicker {
        0%   { transform: scaleX(1) scaleY(1); opacity: 0.9; }
        50%  { transform: scaleX(1.2) scaleY(0.8); opacity: 0.6; }
        100% { transform: scaleX(1) scaleY(1); opacity: 0.9; }
      }
      @keyframes lineFlash {
        0%, 100% { opacity: 0.7; }
        50%      { opacity: 0.2; }
      }
    `}</style>
  );

  // The original 2D SVG Batmobile (fallback for the 3D one).
  const renderBatmobile2D = () => (
          <div className="w-full max-w-[800px] flex flex-col items-center justify-center px-4 select-none">
            {/* Track container */}
            <div
              ref={containerRef}
              style={{
                position: 'relative',
                width: '100%',
                height: '110px',
              }}
            >
              {/* Car Wrapper Div */}
              <div
                style={{
                  position: 'absolute',
                  left: `${carX}px`,
                  bottom: '12px',
                  width: `${CAR_WIDTH}px`,
                  transition: 'left 0.6s linear',
                  willChange: 'left',
                }}
              >
                {/* Speed lines to the LEFT of car */}
                {running && (
                  <div
                    style={{
                      position: 'absolute',
                      right: '100%',
                      top: '25px',
                      pointerEvents: 'none',
                    }}
                  >
                    {[
                      { y: 0, w: 28, delay: '0ms' },
                      { y: 8, w: 18, delay: '50ms' },
                      { y: 16, w: 24, delay: '100ms' },
                      { y: 22, w: 16, delay: '150ms' },
                    ].map((line, idx) => (
                      <div
                        key={idx}
                        style={{
                          height: '1px',
                          width: `${line.w}px`,
                          marginBottom: '6px',
                          background: 'linear-gradient(to left, #FFD700, transparent)',
                          opacity: 0.7,
                          animation: `lineFlash 200ms ease-out infinite alternate ${line.delay}`,
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* Headlight glow beam to the RIGHT of car */}
                <div
                  style={{
                    position: 'absolute',
                    left: '100%',
                    top: '35%',
                    width: '36px',
                    height: '24px',
                    background: 'radial-gradient(ellipse at left, rgba(255,215,0,0.5) 0%, transparent 100%)',
                    pointerEvents: 'none',
                  }}
                />

                {/* Batmobile SVG (Facing Right via scaleX(-1)) */}
                <svg width={CAR_WIDTH} height="auto" viewBox="0 0 300 100" className="overflow-visible">
                  <defs>
                    <radialGradient id="headlightGlow" cx="0%" cy="50%" r="100%">
                      <stop offset="0%" stopColor="#FFD700" stopOpacity="0.9" />
                      <stop offset="100%" stopColor="#FFD700" stopOpacity="0" />
                    </radialGradient>

                    <linearGradient id="exhaustGrad" x1="100%" y1="50%" x2="0%" y2="50%">
                      <stop offset="0%" stopColor="#FF4400" />
                      <stop offset="30%" stopColor="#FF8800" />
                      <stop offset="70%" stopColor="#FFCC00" />
                      <stop offset="100%" stopColor="#FFCC00" stopOpacity="0" />
                    </linearGradient>

                    <filter id="redGlow" x="-50%" y="-50%" width="200%" height="200%">
                      <feGaussianBlur stdDeviation="1.5" />
                    </filter>
                  </defs>

                  {/* Ground Shadow below car */}
                  <ellipse cx="150" cy="88" rx="130" ry="6" fill="rgba(0,0,0,0.6)" filter="blur(4px)" />

                  {/* Mirrored Group so Nose faces RIGHT */}
                  <g transform="scale(-1, 1) translate(-300, 0)">
                    {/* Exhaust flames when running */}
                    {running && (
                      <ellipse
                        cx="280"
                        cy="75"
                        rx="14"
                        ry="4"
                        fill="url(#exhaustGrad)"
                        style={{
                          animation: 'batFlicker 120ms ease-in-out infinite alternate',
                          transformOrigin: '275px 75px',
                        }}
                      />
                    )}

                    {/* Main lower hull */}
                    <path
                      d="M 10,75 Q 30,60 60,58 Q 90,56 120,55 Q 150,52 180,53 Q 210,54 240,58 Q 260,65 275,72 L 275,80 Q 240,82 200,82 Q 170,83 140,82 Q 100,83 60,82 Q 30,82 10,80 Z"
                      fill="#0a0f1e"
                      stroke="rgba(255,215,0,0.4)"
                      strokeWidth="0.5"
                    />

                    {/* Cockpit canopy */}
                    <path
                      d="M 140,55 Q 148,40 158,36 Q 168,33 178,36 Q 188,40 192,50 Q 185,54 165,55 Z"
                      fill="#0d1828"
                      stroke="rgba(255,215,0,0.3)"
                      strokeWidth="0.4"
                    />
                    <ellipse cx="165" cy="44" rx="12" ry="5" fill="rgba(255,255,255,0.05)" />

                    {/* Rear bat-wing fins */}
                    <path d="M 220,55 Q 225,30 235,18 Q 240,12 245,18 Q 248,28 246,45 Q 240,52 230,55 Z" fill="#080c18" stroke="rgba(255,215,0,0.4)" strokeWidth="0.5" />
                    <path d="M 238,55 Q 243,25 250,15 Q 255,8 260,15 Q 263,28 258,50 L 248,55 Z" fill="#080c18" stroke="rgba(255,215,0,0.4)" strokeWidth="0.5" />
                    <path d="M 250,52 Q 256,30 264,20 Q 268,14 272,20 Q 274,32 270,50 Q 265,55 255,55 Z" fill="#080c18" stroke="rgba(255,215,0,0.4)" strokeWidth="0.5" />

                    {/* Front nose extension */}
                    <path d="M 10,68 Q 5,70 2,72 L 2,76 Q 5,76 10,75 Z" fill="#0a0f1e" />

                    {/* Turbine */}
                    <ellipse cx="155" cy="72" rx="18" ry="7" fill="#131d30" stroke="rgba(255,215,0,0.3)" strokeWidth="0.4" />

                    {/* Bat emblem on hood */}
                    <path d="M 94,66 L 97,64 L 99,67 L 101,64 L 104,66 L 101,69 Z" fill="#FFD700" opacity="0.8" />

                    {/* Front Wheel */}
                    <g>
                      <circle cx="65" cy="80" r="14" fill="#050810" stroke="#131d30" strokeWidth="0.5" />
                      <circle cx="65" cy="80" r="9" fill="#131d30" stroke="rgba(255,215,0,0.4)" strokeWidth="0.4" />
                      <circle cx="65" cy="80" r="4" fill="#050810" />
                    </g>

                    {/* Rear Wheel */}
                    <g>
                      <circle cx="220" cy="80" r="18" fill="#050810" stroke="#131d30" strokeWidth="0.5" />
                      <circle cx="220" cy="80" r="12" fill="#131d30" stroke="rgba(255,215,0,0.4)" strokeWidth="0.4" />
                      <circle cx="220" cy="80" r="5" fill="#050810" />
                    </g>

                    {/* Red Tail lights */}
                    <g filter="url(#redGlow)">
                      <ellipse cx="268" cy="40" rx="2.5" ry="2.5" fill="#cc2200" />
                      <ellipse cx="265" cy="47" rx="2" ry="2" fill="#cc2200" />
                    </g>

                    {/* Headlight */}
                    <ellipse cx="2" cy="70" rx="8" ry="4" fill="url(#headlightGlow)" opacity="0.6" />
                    <ellipse cx="8" cy="70" rx="3" ry="2" fill="#FFD700" />
                  </g>
                </svg>
              </div>
            </div>

            {/* Track Ground Line & Progress Fill (Part 8) */}
            <div className="w-full relative mt-1">
              <div
                style={{
                  width: '100%',
                  height: '1px',
                  background: 'linear-gradient(to right, transparent, rgba(255,215,0,0.15) 20%, rgba(255,215,0,0.15) 80%, transparent)',
                }}
              />
              <div
                style={{
                  width: '100%',
                  height: '2px',
                  marginTop: '4px',
                  background: 'rgba(255,215,0,0.06)',
                  borderRadius: '1px',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${progress}%`,
                    height: '100%',
                    background: 'var(--yellow-core)',
                    boxShadow: '0 0 8px rgba(255,215,0,0.4)',
                    transition: 'width 0.6s linear',
                  }}
                />
              </div>

              <div
                style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  letterSpacing: '1.5px',
                  textAlign: 'center',
                  marginTop: '12px',
                  fontFamily: "'Inter', sans-serif",
                  textTransform: 'uppercase',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                }}
              >
                <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '14px', color: 'var(--yellow-core)' }}>
                  {formattedTime}
                </span>
                <span>{progress}% · GOTHAM TO WAYNE MANOR</span>
              </div>
            </div>
          </div>
        );

  // Render Display Content according to active Mode
  const renderModeDisplay = () => {
    switch (mode) {
      case 'N':
        return (
          <div className="flex flex-col items-center justify-center select-none text-center">
            <div
              style={{
                fontSize: 'clamp(80px, 12vw, 140px)',
                color: 'var(--yellow-core)',
                letterSpacing: '8px',
                fontFamily: "'Share Tech Mono', monospace",
                textShadow: '0 0 60px rgba(255,215,0,0.15), 0 0 120px rgba(255,215,0,0.06)',
                lineHeight: 1,
              }}
            >
              {formattedTime}
            </div>

            <div
              style={{
                width: '320px',
                height: '2px',
                background: 'var(--border-dim)',
                borderRadius: '1px',
                marginTop: '32px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${progress}%`,
                  height: '100%',
                  background: 'linear-gradient(to right, #FFD700, #FBBF24)',
                  transition: 'width 0.5s linear',
                  borderRadius: '1px',
                }}
              />
            </div>

            <div
              style={{
                fontSize: '11px',
                color: 'var(--text-muted)',
                letterSpacing: '2px',
                marginTop: '12px',
                fontFamily: "'Inter', sans-serif",
                textTransform: 'uppercase',
              }}
            >
              {progress}% · {formattedTime} REMAINING
            </div>
          </div>
        );

      case 'F':
        return (
          <div className="flex flex-col items-center justify-center select-none">
            <div className="flex items-center justify-center gap-[6px]">
              <FlipDigit digit={minTens} />
              <FlipDigit digit={minUnits} />
              <ColonSeparator running={running} />
              <FlipDigit digit={secTens} />
              <FlipDigit digit={secUnits} />
            </div>

            <div
              style={{
                fontSize: '10px',
                color: 'var(--text-muted)',
                letterSpacing: '3px',
                marginTop: '32px',
                fontFamily: "'Inter', sans-serif",
                textTransform: 'uppercase',
              }}
            >
              MISSION TIME REMAINING
            </div>
          </div>
        );

      case 'B':
        return (
          <div className="relative flex flex-col items-center justify-center select-none w-full max-w-[500px]">
            {/* Ambient Radial Glow */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: `radial-gradient(ellipse at 50% 60%, rgba(255,215,0, ${0.03 + progress * 0.002}) 0%, transparent 60%)`,
                pointerEvents: 'none',
              }}
            />

            {/* Bat emblem: fills with light from the bottom as time passes */}
            <div className="relative w-[420px] max-w-full flex items-center justify-center">
              <BatEmblem progress={progress} className="w-full h-auto" />
            </div>

            {/* Progress Text below Logo */}
            <div className="text-center mt-[16px]">
              <div className="flex items-center justify-center gap-4">
                <span
                  style={{
                    fontFamily: "'Share Tech Mono', monospace",
                    fontSize: '48px',
                    color: 'var(--yellow-core)',
                    lineHeight: 1,
                    display: 'block',
                  }}
                >
                  {formattedTime}
                </span>
                <span
                  style={{
                    fontFamily: "'Share Tech Mono', monospace",
                    fontSize: '24px',
                    color: 'rgba(255,215,0,0.5)',
                    lineHeight: 1,
                  }}
                >
                  {progress}%
                </span>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  letterSpacing: '2px',
                  textTransform: 'uppercase',
                  fontFamily: "'Inter', sans-serif",
                  marginTop: '4px',
                  display: 'block',
                }}
              >
                TIME REMAINING · {progress}% ELAPSED
              </span>
            </div>
          </div>
        );

      case 'M':
        // Real-time 3D Batmobile (lazy-loaded). The 2D car below is shown while
        // it loads and whenever WebGL isn't available.
        return batmobile3dFailed ? (
          renderBatmobile2D()
        ) : (
          <Suspense fallback={renderBatmobile2D()}>
            <Batmobile3D
              progress={progress}
              running={running}
              onUnsupported={handleBatmobile3dUnsupported}
            />
          </Suspense>
        );

      default:
        return null;
    }
  };

  // Mode Selector Buttons JSX helper
  const renderModeButtons = (size = 'small') => {
    const isSmall = size === 'small';
    return (
      <div className="flex items-center gap-1.5">
        {[
          { id: 'N', label: 'N', title: 'Normal' },
          { id: 'F', label: 'F', title: 'Flip Clock' },
          { id: 'B', label: 'B', title: 'Bat-Signal' },
          { id: 'M', label: 'M', title: 'Batmobile' },
        ].map((m) => {
          const isActive = mode === m.id;
          return (
            <button
              key={m.id}
              title={m.title}
              onClick={() => setMode(m.id)}
              style={{
                width: isSmall ? '24px' : '28px',
                height: isSmall ? '24px' : '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '11px',
                fontFamily: "'Share Tech Mono', monospace",
                fontWeight: isActive ? '700' : '400',
                borderRadius: '4px',
                cursor: 'pointer',
                background: isActive ? '#FFD700' : 'transparent',
                color: isActive ? '#050810' : '#94a3b8',
                border: isActive ? 'none' : '1px solid rgba(255,215,0,0.12)',
                transition: 'all 0.15s ease',
              }}
            >
              {m.label}
            </button>
          );
        })}
      </div>
    );
  };

  // ==========================================
  // 1. FULLSCREEN FOCUS VIEW (focusActive === true)
  // ==========================================
  if (focusActive) {
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          background: '#050810',
          display: 'flex',
          flexDirection: 'column',
          width: '100vw',
          height: '100vh',
          overflow: 'hidden',
          fontFamily: "'Inter', sans-serif",
        }}
      >
        {globalStyles}

        {/* PART 2: MISSION STRIP */}
        <header
          style={{
            height: '48px',
            borderBottom: '1px solid rgba(255,215,0,0.06)',
            background: 'rgba(255,255,255,0.02)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 32px',
            position: 'relative',
            shrink: 0,
          }}
        >
          {/* Left side: Yellow Bat Icon + Mission Title */}
          <div className="flex items-center gap-2 select-none">
            <svg width="16" height="10" viewBox="0 0 24 14" fill="#FFD700">
              <path d="M 12 0 C 10.5 2 7 2 4 0 C 2 2 0 6 0 9 C 3 9 6 7 8 5 C 9 8 11 12 12 14 C 13 12 15 8 16 5 C 18 7 21 9 24 9 C 24 6 22 2 20 0 C 17 2 13.5 2 12 0 Z" />
            </svg>
            <span
              style={{
                fontSize: '11px',
                letterSpacing: '2px',
                color: '#94a3b8',
                textTransform: 'uppercase',
                fontFamily: "'Inter', sans-serif",
              }}
            >
              DEEP WORK · {missionName ? missionName.toUpperCase() : 'COGNITIVE ISOLATION'}
            </span>
          </div>

          {/* Center: Mode selector buttons [N] [F] [B] [M] */}
          <div>{renderModeButtons('small')}</div>

          {/* Right side: Soundtrack controls */}
          <div className="flex items-center gap-3 select-none mr-24">
            <button
              onClick={() => onTrackChange(activeTrack)}
              title={activeTrack && isPlaying ? 'Pause music' : 'Play music'}
              style={{
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '12px',
                borderRadius: '4px',
                cursor: 'pointer',
                background: activeTrack && isPlaying ? '#FFD700' : 'transparent',
                color: activeTrack && isPlaying ? '#050810' : '#94a3b8',
                border: activeTrack && isPlaying ? 'none' : '1px solid rgba(255,215,0,0.12)',
                transition: 'all 0.15s ease',
              }}
            >
              {activeTrack && isPlaying ? '❚❚' : '▶'}
            </button>
            <div className="flex items-center gap-1.5">
              {trackPresets.map((track) => {
                const isActiveTrack = activeTrack?.id === track.id;
                return (
                  <button
                    key={track.id}
                    title={track.title}
                    onClick={() => {
                      if (isActiveTrack && isPlaying) {
                        onTrackChange(null);
                      } else {
                        onTrackChange(track);
                      }
                    }}
                    style={{
                      height: '24px',
                      padding: '0 8px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      background: isActiveTrack ? 'rgba(255,215,0,0.12)' : 'transparent',
                      color: isActiveTrack ? '#FFD700' : '#64748b',
                      border: isActiveTrack ? '1px solid rgba(255,215,0,0.3)' : '1px solid transparent',
                      fontSize: '9px',
                      fontFamily: "'Share Tech Mono', monospace",
                      letterSpacing: '1px',
                      textTransform: 'uppercase',
                      transition: 'all 0.15s ease',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {track.title}
                    {isActiveTrack && isPlaying && (
                      <span style={{ marginLeft: '4px', fontSize: '8px' }}>▶</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Corner EXIT FOCUS Button */}
          <button
            onClick={exitFocus}
            title={isNativeFullscreen ? 'Exit fullscreen focus' : 'Exit focus mode'}
            style={{
              position: 'absolute',
              top: '14px',
              right: '24px',
              fontSize: '11px',
              color: '#475569',
              letterSpacing: '1px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontFamily: "'Inter', sans-serif",
              textTransform: 'uppercase',
              transition: 'color 0.2s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = '#FFD700')}
            onMouseLeave={(e) => (e.currentTarget.style.color = '#475569')}
          >
            ✕ EXIT FOCUS
          </button>
        </header>

        {/* PART 3: MODE DISPLAY AREA (CENTER, FRAMELESS) */}
        <main
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
            padding: '48px 64px',
            overflow: 'hidden',
          }}
        >
          {renderModeDisplay()}
        </main>

        {/* PART 3: CONTROL BAR (BOTTOM) */}
        <footer
          style={{
            height: '64px',
            borderTop: '1px solid rgba(255,215,0,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '16px',
            shrink: 0,
          }}
        >
          <button
            onClick={() => handleAdjustTime(-30)}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-mid)',
              color: 'var(--text-muted)',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '11px',
              letterSpacing: '1px',
              padding: '10px 20px',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-glow)';
              e.currentTarget.style.color = 'var(--yellow-dim)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-mid)';
              e.currentTarget.style.color = 'var(--text-muted)';
            }}
          >
            -30s
          </button>

          <button
            onClick={toggleRunning}
            style={{
              background: 'var(--yellow-core)',
              color: '#050810',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '12px',
              fontWeight: 600,
              letterSpacing: '2px',
              padding: '10px 32px',
              borderRadius: '6px',
              boxShadow: '0 0 24px rgba(255,215,0,0.2)',
              cursor: 'pointer',
              transition: 'box-shadow 0.2s ease',
              textTransform: 'uppercase',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 0 32px rgba(255,215,0,0.35)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = '0 0 24px rgba(255,215,0,0.2)';
            }}
          >
            {running ? 'PAUSE' : 'RESUME'}
          </button>

          <button
            onClick={() => handleAdjustTime(30)}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-mid)',
              color: 'var(--text-muted)',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '11px',
              letterSpacing: '1px',
              padding: '10px 20px',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-glow)';
              e.currentTarget.style.color = 'var(--yellow-dim)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-mid)';
              e.currentTarget.style.color = 'var(--text-muted)';
            }}
          >
            +30s
          </button>

          {/* Ends the session and logs the time (5 min minimum). */}
          <button
            onClick={exitFocus}
            title="End this session and log the time"
            style={{
              background: 'transparent',
              border: '1px solid rgba(248,113,113,0.4)',
              color: '#f87171',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '11px',
              letterSpacing: '1px',
              padding: '10px 20px',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#f87171';
              e.currentTarget.style.background = 'rgba(248,113,113,0.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(248,113,113,0.4)';
              e.currentTarget.style.background = 'transparent';
            }}
          >
            ■ STOP &amp; LOG
          </button>
        </footer>
      </div>
    );
  }

  // ==========================================
  // 2. COMPACT PANEL VIEW (focusActive === false)
  // ==========================================
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        background: 'var(--bg-card)',
        borderRadius: '16px',
        padding: '32px',
        minHeight: '400px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'space-between',
        border: '1px solid var(--border-dim)',
        boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
      }}
    >
      {globalStyles}

      {/* Top Bar in Panel View: Mode Selector */}
      <div className="flex items-center justify-between w-full mb-4">
        <div className="flex items-center gap-2 select-none">
          <svg width="16" height="10" viewBox="0 0 24 14" fill="#FFD700">
            <path d="M 12 0 C 10.5 2 7 2 4 0 C 2 2 0 6 0 9 C 3 9 6 7 8 5 C 9 8 11 12 12 14 C 13 12 15 8 16 5 C 18 7 21 9 24 9 C 24 6 22 2 20 0 C 17 2 13.5 2 12 0 Z" />
          </svg>
          <span
            style={{
              fontSize: '11px',
              letterSpacing: '2px',
              color: 'var(--text-secondary)',
              textTransform: 'uppercase',
              fontFamily: "'Inter', sans-serif",
            }}
          >
            {missionName ? missionName.toUpperCase() : 'FOCUS HOURGLASS'}
          </span>
        </div>

        <div>{renderModeButtons('normal')}</div>
      </div>

      {/* Center Display Area in Panel View */}
      <div className="w-full flex-1 flex items-center justify-center my-6 min-h-[260px]">
        {renderModeDisplay()}
      </div>

      {/* Bottom Controls in Panel View */}
      <div className="flex items-center justify-center gap-4">
        <button
          onClick={() => handleAdjustTime(-30)}
          style={{
            background: 'transparent',
            border: '1px solid var(--border-mid)',
            color: 'var(--text-muted)',
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '11px',
            letterSpacing: '1px',
            padding: '10px 20px',
            borderRadius: '6px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-glow)';
            e.currentTarget.style.color = 'var(--yellow-dim)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-mid)';
            e.currentTarget.style.color = 'var(--text-muted)';
          }}
        >
          -30s
        </button>

        <button
          onClick={enterFocus}
          style={{
            background: 'var(--yellow-core)',
            color: '#050810',
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '12px',
            fontWeight: 600,
            letterSpacing: '2px',
            padding: '10px 32px',
            borderRadius: '6px',
            boxShadow: '0 0 24px rgba(255,215,0,0.2)',
            cursor: 'pointer',
            transition: 'box-shadow 0.2s ease',
            textTransform: 'uppercase',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = '0 0 32px rgba(255,215,0,0.35)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = '0 0 24px rgba(255,215,0,0.2)';
          }}
        >
          ENTER FOCUS
        </button>

        <button
          onClick={() => handleAdjustTime(30)}
          style={{
            background: 'transparent',
            border: '1px solid var(--border-mid)',
            color: 'var(--text-muted)',
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '11px',
            letterSpacing: '1px',
            padding: '10px 20px',
            borderRadius: '6px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-glow)';
            e.currentTarget.style.color = 'var(--yellow-dim)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border-mid)';
            e.currentTarget.style.color = 'var(--text-muted)';
          }}
        >
          +30s
        </button>
      </div>
    </div>
  );
}

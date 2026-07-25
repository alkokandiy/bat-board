import React, { useState, useEffect, useRef } from 'react';

function FlipDigit({ digit }) {
  const [currentDigit, setCurrentDigit] = useState(digit);
  const [oldDigit, setOldDigit] = useState(digit);
  const [isFlipping, setIsFlipping] = useState(false);
  const prevDigitRef = useRef(digit);

  useEffect(() => {
    if (digit !== prevDigitRef.current) {
      setOldDigit(prevDigitRef.current);
      setCurrentDigit(digit);
      setIsFlipping(true);
      prevDigitRef.current = digit;

      const timer = setTimeout(() => {
        setIsFlipping(false);
      }, 450);

      return () => clearTimeout(timer);
    }
  }, [digit]);

  return (
    <div className="relative w-[60px] h-[80px] bg-[#1e293b] rounded-[6px] border border-[#334155] select-none overflow-hidden" style={{ perspective: '400px' }}>
      {/* Top half static (shows current/new digit top half) */}
      <div className="absolute top-0 left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b]">
        <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[52px] text-[#FFD700] leading-none">
          {currentDigit}
        </div>
      </div>

      {/* Bottom half static (shows old digit while flipping, or current digit when static) */}
      <div className="absolute top-[40px] left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b]">
        <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[52px] text-[#FFD700] leading-none -mt-[40px]">
          {isFlipping ? oldDigit : currentDigit}
        </div>
      </div>

      {/* Animated Top Flap (shows old digit top half folding down) */}
      {isFlipping && (
        <div
          className="absolute top-0 left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b] z-10"
          style={{
            transformOrigin: 'bottom center',
            animation: 'flipTop 300ms ease-in forwards',
            backfaceVisibility: 'hidden'
          }}
        >
          <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[52px] text-[#FFD700] leading-none">
            {oldDigit}
          </div>
        </div>
      )}

      {/* Animated Bottom Flap (shows new digit bottom half unfolding down) */}
      {isFlipping && (
        <div
          className="absolute top-[40px] left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b] z-10"
          style={{
            transformOrigin: 'top center',
            animation: 'flipBottom 300ms ease-out 150ms forwards',
            backfaceVisibility: 'hidden'
          }}
        >
          <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[52px] text-[#FFD700] leading-none -mt-[40px]">
            {currentDigit}
          </div>
        </div>
      )}

      {/* Center divider line */}
      <div className="absolute top-[39px] left-0 right-0 h-[2px] bg-[#0a0e1a] z-20 pointer-events-none" />
    </div>
  );
}

export default function BatFocusTimer({
  timeLeft: propTimeLeft,
  totalTime: propTotalTime,
  running: propRunning,
  onToggleRunning,
  onAdjustTime,
}) {
  const [internalTimeLeft, setInternalTimeLeft] = useState(25 * 60);
  const [internalTotalTime, setInternalTotalTime] = useState(25 * 60);
  const [internalRunning, setInternalRunning] = useState(false);
  const [mode, setMode] = useState('N'); // 'N' | 'F' | 'B' | 'M'

  const carContainerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(360);

  const isControlled = propTimeLeft !== undefined;
  const timeLeft = isControlled ? propTimeLeft : internalTimeLeft;
  const totalTime = isControlled ? (propTotalTime || 25 * 60) : internalTotalTime;
  const running = isControlled ? propRunning : internalRunning;

  // Measure car container width for Mode 4
  useEffect(() => {
    if (mode === 'M' && carContainerRef.current) {
      const updateWidth = () => {
        if (carContainerRef.current) {
          setContainerWidth(carContainerRef.current.clientWidth);
        }
      };
      updateWidth();
      window.addEventListener('resize', updateWidth);
      return () => window.removeEventListener('resize', updateWidth);
    }
  }, [mode]);

  // Internal Timer countdown logic (only when not controlled)
  useEffect(() => {
    if (isControlled || !internalRunning) return;

    const interval = setInterval(() => {
      setInternalTimeLeft(prev => {
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

  const fmt = (s) => [Math.floor(s / 60), s % 60].map(n => String(n).padStart(2, '0')).join(':');

  const formattedTime = fmt(timeLeft);
  const [m1, m2, , s1, s2] = formattedTime;

  const handleAdjustTime = (delta) => {
    if (onAdjustTime) {
      onAdjustTime(delta);
    } else {
      setInternalTimeLeft(prev => {
        const nextTime = Math.max(0, prev + delta);
        if (nextTime > internalTotalTime) {
          setInternalTotalTime(nextTime);
        }
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

  // Batmobile car position
  const carWidth = 100;
  const maxTravel = Math.max(0, containerWidth - carWidth);
  const carX = (progress / 100) * maxTravel;

  return (
    <div className="w-full bg-[#0a0e1a] rounded-2xl p-8 min-h-[400px] flex flex-col items-center justify-between text-slate-100 font-sans border border-slate-800/80 shadow-2xl">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

        .font-share-tech {
          font-family: 'Share Tech Mono', monospace;
        }

        @keyframes flicker {
          0% { transform: scaleX(0.7) scaleY(0.8); opacity: 0.7; }
          50% { transform: scaleX(1.3) scaleY(1.1); opacity: 1; }
          100% { transform: scaleX(0.8) scaleY(0.9); opacity: 0.8; }
        }

        @keyframes speedLine {
          0% { transform: scaleX(1); opacity: 0.8; }
          100% { transform: scaleX(0.3); opacity: 0.1; }
        }

        @keyframes flipTop {
          0% { transform: rotateX(0deg); }
          100% { transform: rotateX(-90deg); }
        }

        @keyframes flipBottom {
          0% { transform: rotateX(90deg); }
          100% { transform: rotateX(0deg); }
        }
      `}</style>

      {/* Top: Mode selector row */}
      <div className="flex items-center gap-3">
        {[
          { id: 'N', label: 'N', title: 'Normal' },
          { id: 'F', label: 'F', title: 'Flip Clock' },
          { id: 'B', label: 'B', title: 'Bat-Signal' },
          { id: 'M', label: 'M', title: 'Batmobile' },
        ].map(m => {
          const isActive = mode === m.id;
          return (
            <button
              key={m.id}
              title={m.title}
              onClick={() => setMode(m.id)}
              className={`w-[28px] h-[28px] flex items-center justify-center text-xs font-mono font-bold rounded cursor-pointer select-none transition-none ${
                isActive
                  ? 'bg-[#FFD700] text-[#0a0e1a]'
                  : 'bg-transparent border border-[#334155] text-[#94a3b8] hover:border-[#FFD700] hover:text-[#FFD700]'
              }`}
            >
              {m.label}
            </button>
          );
        })}
      </div>

      {/* Center: Main Visualization Area */}
      <div className="w-full flex-1 flex flex-col items-center justify-center my-6 min-h-[220px]">
        {/* Mode 1: [N] Normal */}
        {mode === 'N' && (
          <div className="flex flex-col items-center justify-center select-none">
            <div
              className="font-share-tech text-[76px] font-bold text-[#FFD700] leading-none tracking-[6px]"
              style={{ textShadow: '0 0 24px rgba(255,215,0,0.35)' }}
            >
              {formattedTime}
            </div>
            <div className="text-[#64748b] text-[12px] font-mono tracking-[2px] mt-3 uppercase">
              {progress}% ELAPSED
            </div>
          </div>
        )}

        {/* Mode 2: [F] Flip Clock */}
        {mode === 'F' && (
          <div className="flex flex-col items-center justify-center">
            <div className="flex items-center justify-center gap-2">
              <FlipDigit digit={m1} />
              <FlipDigit digit={m2} />
              <span className="font-share-tech text-[52px] text-[#FFD700] pb-2 select-none">:</span>
              <FlipDigit digit={s1} />
              <FlipDigit digit={s2} />
            </div>
            <div className="text-[#64748b] text-[12px] font-mono tracking-[2px] mt-4 uppercase">
              {progress}% ELAPSED
            </div>
          </div>
        )}

        {/* Mode 3: [B] Bat-Signal */}
        {mode === 'B' && (
          <div className="flex flex-col items-center justify-center">
            <div className="relative flex items-center justify-center w-[220px] h-[180px]">
              <svg width="220" height="180" viewBox="0 0 220 180" className="overflow-visible">
                <defs>
                  {/* Linear gradient filling from bottom to top */}
                  <linearGradient id="batFill" x1="0" y1="1" x2="0" y2="0">
                    <stop offset={`${100 - progress}%`} stopColor="#1e293b" />
                    <stop offset={`${100 - progress}%`} stopColor="#FFD700" />
                  </linearGradient>

                  {/* Radial gradient for background glow */}
                  <radialGradient id="bgGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#FFD700" stopOpacity="1" />
                    <stop offset="100%" stopColor="#0a0e1a" stopOpacity="0" />
                  </radialGradient>

                  {/* Filter for radial background glow blur */}
                  <filter id="glowBlur" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="20" />
                  </filter>

                  {/* Filter for SVG path glow */}
                  <filter id="batGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  {/* Extra intense glow filter when 100% completed */}
                  <filter id="batGlow100" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="8" result="blur2" />
                    <feMerge>
                      <feMergeNode in="blur2" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                {/* Background glowing ellipse */}
                <ellipse
                  cx="110"
                  cy="90"
                  rx="90"
                  ry="60"
                  fill="url(#bgGlow)"
                  opacity={0.05 + progress * 0.003}
                  filter="url(#glowBlur)"
                />

                {/* Outer halo when progress is 100% */}
                {progress === 100 && (
                  <ellipse
                    cx="110"
                    cy="90"
                    rx="100"
                    ry="70"
                    fill="none"
                    stroke="#FFD700"
                    strokeWidth="2"
                    opacity="0.8"
                    filter="url(#batGlow100)"
                  />
                )}

                {/* Bat Silhouette Path */}
                <path
                  d="M110,148 C108,145 104,138 98,128 L88,115 C82,108 76,102 70,98 C62,103 52,110 43,107 C37,103 39,92 48,86 C33,79 13,80 8,68 C18,48 44,36 66,44 L60,18 L92,34 L96,14 L110,28 L124,14 L128,34 L160,18 L154,44 C176,36 202,48 212,68 C207,80 187,79 172,86 C181,92 183,103 177,107 C168,110 158,103 150,98 C144,102 138,108 132,115 L122,128 C116,138 112,145 110,148 Z"
                  fill="url(#batFill)"
                  stroke="#FFD700"
                  strokeWidth={progress === 100 ? "2" : "0.75"}
                  strokeOpacity="0.9"
                  filter={progress === 100 ? "url(#batGlow100)" : "url(#batGlow)"}
                />
              </svg>
            </div>
            <div className="text-center mt-2">
              <div className="text-[#FFD700] text-[16px] font-bold font-mono">{progress}%</div>
              <div className="text-[#64748b] text-[11px] font-mono tracking-wider">ELAPSED</div>
            </div>
          </div>
        )}

        {/* Mode 4: [M] Batmobile */}
        {mode === 'M' && (
          <div className="w-full flex flex-col items-center justify-center px-2">
            {/* Car travel area */}
            <div ref={carContainerRef} className="w-full relative h-[65px] overflow-visible mb-2">
              <div
                className="absolute bottom-[3px]"
                style={{
                  left: `${carX}px`,
                  transition: 'left 0.5s linear',
                  width: '100px',
                  height: '56px'
                }}
              >
                {/* Exhaust flames & speed lines (only when running === true) */}
                {running && (
                  <>
                    {/* Exhaust flames behind the car (left side, as car drives right) */}
                    <div
                      className="absolute left-[-16px] bottom-[14px] w-[20px] h-[10px] rounded-full pointer-events-none"
                      style={{
                        background: 'radial-gradient(circle, #FFD700 0%, #ff4500 70%, transparent 100%)',
                        animation: 'flicker 80ms infinite alternate',
                        transformOrigin: 'right center'
                      }}
                    />

                    {/* Speed lines behind car */}
                    <div className="absolute left-[-22px] top-[18px] w-[18px] h-[1px] bg-gradient-to-r from-transparent to-[#FFD700] opacity-70" style={{ animation: 'speedLine 150ms infinite alternate' }} />
                    <div className="absolute left-[-16px] top-[26px] w-[14px] h-[1px] bg-gradient-to-r from-transparent to-[#FFD700] opacity-60" style={{ animation: 'speedLine 150ms infinite alternate 40ms' }} />
                    <div className="absolute left-[-24px] top-[34px] w-[20px] h-[1px] bg-gradient-to-r from-transparent to-[#FFD700] opacity-80" style={{ animation: 'speedLine 150ms infinite alternate 80ms' }} />
                  </>
                )}

                {/* Batmobile SVG (viewBox="0 0 100 56") */}
                <svg width="100" height="56" viewBox="0 0 100 56" className="overflow-visible">
                  <defs>
                    <radialGradient id="headlightGlow" cx="0%" cy="50%" r="100%">
                      <stop offset="0%" stopColor="#FFD700" stopOpacity="0.9" />
                      <stop offset="100%" stopColor="#FFD700" stopOpacity="0" />
                    </radialGradient>
                  </defs>

                  {/* Headlight beam (extending to the right) */}
                  <polygon points="94,36 120,28 120,44" fill="url(#headlightGlow)" />

                  {/* Rear fins (triangular bat-wings at back, left side) */}
                  <path d="M12,32 L2,10 L28,26 Z" fill="#1e293b" stroke="#FFD700" strokeWidth="1.5" strokeLinejoin="round" />
                  <path d="M18,30 L10,14 L32,24 Z" fill="#152030" stroke="#FFD700" strokeWidth="1" strokeLinejoin="round" />

                  {/* Sleek Hull Body */}
                  <path
                    d="M10,38 C15,30 25,28 40,26 C55,24 75,28 88,34 C94,37 98,40 96,44 C92,46 80,48 50,48 C20,48 10,44 10,38 Z"
                    fill="#1e293b"
                    stroke="#FFD700"
                    strokeWidth="1.5"
                  />

                  {/* Cockpit Bubble */}
                  <ellipse cx="52" cy="28" rx="16" ry="8" fill="#263352" stroke="#FFD700" strokeWidth="1.2" opacity="0.9" />

                  {/* Hood Bat Emblem */}
                  <path d="M72,35 L76,33 L78,36 L80,33 L84,35 L80,38 Z" fill="#FFD700" />

                  {/* Front Grille detail */}
                  <line x1="88" y1="40" x2="94" y2="40" stroke="#FFD700" strokeWidth="1" />
                  <line x1="89" y1="42" x2="93" y2="42" stroke="#FFD700" strokeWidth="1" />

                  {/* Front Wheel */}
                  <circle cx="78" cy="46" r="8" fill="#0a0e1a" stroke="#FFD700" strokeWidth="1.5" />
                  <circle cx="78" cy="46" r="3" fill="#FFD700" />

                  {/* Rear Wheel */}
                  <circle cx="26" cy="46" r="9" fill="#0a0e1a" stroke="#FFD700" strokeWidth="1.5" />
                  <circle cx="26" cy="46" r="3.5" fill="#FFD700" />

                  {/* Headlight lamp */}
                  <ellipse cx="94" cy="36" rx="2" ry="3" fill="#FFD700" />
                </svg>
              </div>
            </div>

            {/* Progress bar track */}
            <div className="w-full relative">
              <div className="w-full h-[3px] bg-[#1e293b] rounded-[2px] overflow-hidden">
                <div
                  className="h-full bg-[#FFD700] transition-all duration-300"
                  style={{
                    width: `${progress}%`,
                    boxShadow: '0 0 8px rgba(255,215,0,0.5)'
                  }}
                />
              </div>
              <div className="text-right text-[11px] text-[#64748b] font-mono mt-1">
                {progress}%
              </div>
            </div>

            {/* Time display */}
            <div className="font-share-tech text-[48px] font-bold text-[#FFD700] mt-2 select-none leading-none">
              {formattedTime}
            </div>
          </div>
        )}
      </div>

      {/* Bottom controls: [-30s] [START/PAUSE] [+30s] */}
      <div className="flex items-center justify-center gap-4">
        <button
          onClick={() => handleAdjustTime(-30)}
          className="px-3 py-2.5 bg-[#1e293b] border border-[#334155] text-[#94a3b8] hover:border-[#FFD700] hover:text-[#FFD700] rounded font-mono text-xs transition-colors cursor-pointer select-none"
        >
          -30s
        </button>

        <button
          onClick={toggleRunning}
          className="px-8 py-2.5 bg-[#FFD700] hover:bg-yellow-400 text-[#0a0e1a] font-extrabold rounded font-mono text-xs tracking-wider transition-colors cursor-pointer select-none shadow-lg shadow-amber-500/10"
        >
          {running ? 'PAUSE' : 'START'}
        </button>

        <button
          onClick={() => handleAdjustTime(30)}
          className="px-3 py-2.5 bg-[#1e293b] border border-[#334155] text-[#94a3b8] hover:border-[#FFD700] hover:text-[#FFD700] rounded font-mono text-xs transition-colors cursor-pointer select-none"
        >
          +30s
        </button>
      </div>
    </div>
  );
}

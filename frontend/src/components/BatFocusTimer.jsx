import React, { useState, useEffect, useRef, useLayoutEffect, useMemo } from 'react';

// ==========================================
// FIX 2: ICONIC FLIP CLOCK DIGIT COMPONENT
// ==========================================
function FlipDigit({ digit }) {
  const [currentDigit, setCurrentDigit] = useState(digit);
  const [prevDigit, setPrevDigit] = useState(digit);
  const [phase, setPhase] = useState('idle'); // 'idle' | 'flipping'
  const animatingRef = useRef(false);

  useEffect(() => {
    if (digit === currentDigit || animatingRef.current) return;
    animatingRef.current = true;
    setPrevDigit(currentDigit);
    setPhase('flipping');

    const t1 = setTimeout(() => {
      setCurrentDigit(digit);
      const t2 = setTimeout(() => {
        setPhase('idle');
        animatingRef.current = false;
      }, 350);
      return () => clearTimeout(t2);
    }, 200);

    return () => clearTimeout(t1);
  }, [digit, currentDigit]);

  return (
    <div
      className="relative w-[64px] h-[88px] bg-[#1a1f2e] rounded-[8px] border border-[#2a3a5a] select-none"
      style={{
        boxShadow: '0 4px 12px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.03)',
        perspective: '200px',
      }}
    >
      {/* Top half static (shows top 50% of currentDigit) */}
      <div className="absolute top-0 left-0 w-[64px] h-[44px] overflow-hidden bg-[#1a1f2e] rounded-t-[8px]">
        <div className="absolute top-0 left-0 w-[64px] h-[88px] flex items-center justify-center font-share-tech text-[64px] text-[#FFD700] leading-[88px]">
          {currentDigit}
        </div>
      </div>

      {/* Bottom half static (shows bottom 50% of currentDigit) */}
      <div className="absolute top-[44px] left-0 w-[64px] h-[44px] overflow-hidden bg-[#1a1f2e] rounded-b-[8px]">
        <div className="absolute top-[-44px] left-0 w-[64px] h-[88px] flex items-center justify-center font-share-tech text-[64px] text-[#FFD700] leading-[88px]">
          {currentDigit}
        </div>
      </div>

      {/* Center divider line */}
      <div className="absolute top-[43px] left-0 w-full h-[2px] bg-[#0a0e1a] z-10 pointer-events-none" />

      {/* FLAP A — "top fold away": overlays top half, shows prevDigit */}
      {phase === 'flipping' && (
        <div
          className="absolute top-0 left-0 w-[64px] h-[44px] overflow-hidden bg-[#1a1f2e] rounded-t-[8px] z-20"
          style={{
            transformOrigin: 'center bottom',
            backfaceVisibility: 'hidden',
            animation: 'flapTopOut 280ms ease-in forwards',
          }}
        >
          <div className="absolute top-0 left-0 w-[64px] h-[88px] flex items-center justify-center font-share-tech text-[64px] text-[#FFD700] leading-[88px]">
            {prevDigit}
          </div>
        </div>
      )}

      {/* FLAP B — "bottom unfold": overlays bottom half, shows new currentDigit */}
      {phase === 'flipping' && (
        <div
          className="absolute bottom-0 left-0 w-[64px] h-[44px] overflow-hidden bg-[#1a1f2e] rounded-b-[8px] z-20"
          style={{
            transformOrigin: 'center top',
            backfaceVisibility: 'hidden',
            transform: 'rotateX(90deg)',
            animation: 'flapBottomIn 280ms ease-out 200ms forwards',
          }}
        >
          <div className="absolute top-[-44px] left-0 w-[64px] h-[88px] flex items-center justify-center font-share-tech text-[64px] text-[#FFD700] leading-[88px]">
            {currentDigit}
          </div>
        </div>
      )}
    </div>
  );
}

// Blinking colon separator for Flip Clock
function ColonSeparator({ running }) {
  return (
    <div className="flex flex-col gap-[12px] my-0 mx-[8px] items-center justify-center">
      <div
        className="w-[8px] h-[8px] rounded-full bg-[#FFD700]"
        style={{ animation: running ? 'colonBlink 1s step-end infinite' : 'none' }}
      />
      <div
        className="w-[8px] h-[8px] rounded-full bg-[#FFD700]"
        style={{ animation: running ? 'colonBlink 1s step-end infinite' : 'none' }}
      />
    </div>
  );
}

// ==========================================
// FIX 4: BATMAN LOGO PIXEL GRID GENERATOR
// ==========================================
function buildLogoGrid() {
  const grid = [];
  const COLS = 40;
  const ROWS = 28;

  // BAT_MAP (17 rows x 13 cols)
  const BAT_MAP = [
    [0,0,1,0,0,0,1,0,0,1,0,0,0], // Row 0
    [0,1,1,1,0,0,1,0,1,1,1,0,0], // Row 1
    [0,1,1,1,1,0,1,0,1,1,1,1,0], // Row 2
    [1,1,1,1,1,1,1,1,1,1,1,1,1], // Row 3
    [1,1,1,1,1,1,1,1,1,1,1,1,1], // Row 4
    [1,1,1,0,1,1,1,1,1,0,1,1,1], // Row 5
    [1,1,0,0,0,1,1,1,0,0,0,1,1], // Row 6
    [1,0,0,0,0,0,1,0,0,0,0,0,1], // Row 7
    [0,0,0,0,0,0,1,0,0,0,0,0,0], // Row 8
    [0,0,0,0,0,1,1,1,0,0,0,0,0], // Row 9
    [0,0,0,0,1,1,1,1,1,0,0,0,0], // Row 10
    [0,0,0,1,1,0,1,0,1,1,0,0,0], // Row 11
    [0,0,1,1,0,0,1,0,0,1,1,0,0], // Row 12
    [0,1,1,0,0,0,1,0,0,0,1,1,0], // Row 13
    [0,0,0,0,0,0,1,0,0,0,0,0,0], // Row 14
    [0,0,0,0,0,1,1,1,0,0,0,0,0], // Row 15
    [0,0,0,0,1,1,1,1,1,0,0,0,0], // Row 16
  ];

  const cx = 19.5;
  const cy = 13.5;
  const a = 19;
  const b = 12;

  for (let r = 0; r < ROWS; r++) {
    const row = [];
    for (let c = 0; c < COLS; c++) {
      // Step 1: Oval test
      const normC = (c - cx) / a;
      const normR = (r - cy) / b;
      const inOval = (normC * normC + normR * normR) <= 1.0;

      if (!inOval) {
        row.push(0); // 0 = outside oval
        continue;
      }

      // Step 2: Bat shape overlay at row_offset=5, col_offset=14
      const batR = r - 5;
      const batC = c - 14;
      let isBat = false;

      if (batR >= 0 && batR < 17 && batC >= 0 && batC < 13) {
        if (BAT_MAP[batR][batC] === 1) {
          isBat = true;
        }
      }

      row.push(isBat ? 2 : 1); // 2 = black bat, 1 = yellow oval
    }
    grid.push(row);
  }

  return grid;
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
  onClose,
}) {
  const [internalTimeLeft, setInternalTimeLeft] = useState(25 * 60);
  const [internalTotalTime, setInternalTotalTime] = useState(25 * 60);
  const [internalRunning, setInternalRunning] = useState(false);
  const [mode, setMode] = useState('N'); // 'N' | 'F' | 'B' | 'M'

  // FIX 3: Batmobile car track container measurement
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(600);

  useLayoutEffect(() => {
    if (!containerRef.current) return;
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    const ro = new ResizeObserver(updateWidth);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [mode]);

  // FIX 1: Escape key listener
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const isControlled = propTimeLeft !== undefined;
  const timeLeft = isControlled ? propTimeLeft : internalTimeLeft;
  const totalTime = isControlled ? (propTotalTime || 25 * 60) : internalTotalTime;
  const running = isControlled ? propRunning : internalRunning;

  // Internal timer countdown logic (when not controlled)
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

  // Digits for Flip Clock
  const minTens = String(Math.floor(timeLeft / 600));
  const minUnits = String(Math.floor((timeLeft / 60) % 10));
  const secTens = String(Math.floor((timeLeft % 60) / 10));
  const secUnits = String(timeLeft % 10);

  // FIX 4: Bat-Signal Pixel Logo Grid & Fill logic
  const logoGrid = useMemo(() => buildLogoGrid(), []);

  const sortedOvalCells = useMemo(() => {
    const cells = [];
    for (let r = 27; r >= 0; r--) {
      for (let c = 0; c < 40; c++) {
        if (logoGrid[r][c] === 1) {
          cells.push({ r, c });
        }
      }
    }
    return cells;
  }, [logoGrid]);

  const totalOvalPixels = sortedOvalCells.length;
  const filledCount = Math.floor((progress / 100) * totalOvalPixels);

  const filledSet = useMemo(() => {
    const set = new Set();
    for (let i = 0; i < filledCount; i++) {
      const { r, c } = sortedOvalCells[i];
      set.add(`${r},${c}`);
    }
    return set;
  }, [sortedOvalCells, filledCount]);

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

  // FIX 3: Batmobile car position calculation
  const CAR_WIDTH = 300;
  const maxTravel = Math.max(0, containerWidth - CAR_WIDTH);
  const carX = (progress / 100) * maxTravel;

  const timerCard = (
    <div className="relative w-full max-w-[680px] bg-[#0a0e1a] rounded-2xl p-8 min-h-[400px] flex flex-col items-center justify-between text-slate-100 font-sans border border-slate-800/80 shadow-2xl">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

        .font-share-tech {
          font-family: 'Share Tech Mono', monospace;
        }

        @keyframes flapTopOut {
          0%   { transform: rotateX(0deg);   }
          100% { transform: rotateX(-90deg); }
        }

        @keyframes flapBottomIn {
          0%   { transform: rotateX(90deg); }
          100% { transform: rotateX(0deg);  }
        }

        @keyframes colonBlink {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.2; }
        }

        @keyframes flicker {
          0%   { transform: scaleX(1)   scaleY(1);   opacity: 0.9; }
          25%  { transform: scaleX(1.3) scaleY(0.7); opacity: 0.7; }
          50%  { transform: scaleX(0.8) scaleY(1.2); opacity: 1.0; }
          75%  { transform: scaleX(1.2) scaleY(0.8); opacity: 0.6; }
          100% { transform: scaleX(1)   scaleY(1);   opacity: 0.9; }
        }

        @keyframes speedPulse {
          from { opacity: 0.7; transform: scaleX(1); }
          to   { opacity: 0; transform: scaleX(0.3); }
        }
      `}</style>

      {/* FIX 1: Top-Right ESC / Close Button */}
      {onClose && (
        <button
          onClick={onClose}
          title="Close (Esc)"
          className="absolute top-[12px] right-[12px] w-[24px] h-[24px] flex items-center justify-center border border-[#334155] bg-transparent text-[#64748b] text-[12px] rounded hover:border-[#FFD700] hover:text-[#FFD700] transition-colors duration-150 cursor-pointer select-none z-30"
        >
          ✕
        </button>
      )}

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
      <div className="w-full flex-1 flex flex-col items-center justify-center my-6 min-h-[280px]">
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
            <div className="flex items-center justify-center gap-[8px]">
              <FlipDigit digit={minTens} />
              <FlipDigit digit={minUnits} />
              <ColonSeparator running={running} />
              <FlipDigit digit={secTens} />
              <FlipDigit digit={secUnits} />
            </div>
            <div className="text-[#64748b] text-[11px] font-mono tracking-[2px] mt-[20px] uppercase">
              {progress}% ELAPSED
            </div>
          </div>
        )}

        {/* Mode 3: [B] Bat-Signal Pixel Logo Grid */}
        {mode === 'B' && (
          <div className="flex flex-col items-center justify-center">
            <div className="relative select-none">
              {/* Radial glow background */}
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  background: `radial-gradient(ellipse at center, rgba(255,215,0, ${0.02 + progress * 0.002}) 0%, transparent 65%)`,
                  pointerEvents: 'none',
                  zIndex: -1,
                }}
              />

              {/* 40x28 Pixel Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(40, 9px)',
                  gap: '1px',
                }}
              >
                {logoGrid.map((row, r) =>
                  row.map((val, c) => {
                    if (val === 0) {
                      return <div key={`${r},${c}`} className="w-[9px] h-[9px] bg-transparent" />;
                    }
                    if (val === 2) {
                      // Black Bat silhouette cell
                      return (
                        <div
                          key={`${r},${c}`}
                          className="w-[9px] h-[9px] rounded-[1.5px] bg-[#0a0e1a]"
                        />
                      );
                    }
                    // val === 1: Yellow Oval area
                    const isFilled = filledSet.has(`${r},${c}`);
                    return (
                      <div
                        key={`${r},${c}`}
                        className="w-[9px] h-[9px] rounded-[1.5px]"
                        style={{
                          backgroundColor: isFilled ? '#FFD700' : '#1e293b',
                          boxShadow: isFilled ? '0 0 4px rgba(255,215,0,0.5)' : 'none',
                          transition: isFilled
                            ? 'background-color 0.4s ease, box-shadow 0.4s ease'
                            : 'background-color 0.4s ease',
                        }}
                      />
                    );
                  })
                )}
              </div>
            </div>

            <div className="text-center mt-[12px]">
              <div className="text-[#FFD700] text-[18px] font-bold font-mono">{progress}%</div>
              <div className="text-[#64748b] text-[11px] font-mono tracking-[3px]">ELAPSED</div>
            </div>
          </div>
        )}

        {/* Mode 4: [M] Realistic 1989 Batmobile */}
        {mode === 'M' && (
          <div className="w-full flex flex-col items-center justify-center px-2">
            {/* Position relative track container */}
            <div
              ref={containerRef}
              style={{
                position: 'relative',
                width: '100%',
                height: 120,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: carX,
                  bottom: 20,
                  width: CAR_WIDTH,
                  transition: 'left 0.5s linear',
                }}
              >
                {/* 1989 Batmobile SVG */}
                <svg width={CAR_WIDTH} height="auto" viewBox="0 0 300 100" className="overflow-visible">
                  <defs>
                    <radialGradient id="headlightGlow" cx="0%" cy="50%" r="100%">
                      <stop offset="0%" stopColor="#FFD700" stopOpacity="0.9" />
                      <stop offset="100%" stopColor="#FFD700" stopOpacity="0" />
                    </radialGradient>

                    <linearGradient id="exhaustGrad" x1="0%" y1="50%" x2="100%" y2="50%">
                      <stop offset="0%" stopColor="#FF4400" />
                      <stop offset="30%" stopColor="#FF8800" />
                      <stop offset="70%" stopColor="#FFCC00" />
                      <stop offset="100%" stopColor="#FFCC00" stopOpacity="0" />
                    </linearGradient>

                    <filter id="redGlow" x="-50%" y="-50%" width="200%" height="200%">
                      <feGaussianBlur stdDeviation="1.5" />
                      <feMerge>
                        <feMergeNode />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>

                  {/* Motion details when running */}
                  {running && (
                    <g>
                      {/* Exhaust flame from rear */}
                      <ellipse
                        cx="280"
                        cy="75"
                        rx="12"
                        ry="4"
                        fill="url(#exhaustGrad)"
                        style={{
                          animation: 'flicker 120ms ease-in-out infinite alternate',
                          transformOrigin: '275px 75px',
                        }}
                      />

                      {/* Speed lines behind car */}
                      <line x1="-20" y1="62" x2="0" y2="62" stroke="#FFD700" strokeWidth="0.8" opacity="0.7" style={{ animation: 'speedPulse 200ms ease-out infinite alternate' }} />
                      <line x1="-14" y1="67" x2="0" y2="67" stroke="#FFD700" strokeWidth="0.8" opacity="0.4" style={{ animation: 'speedPulse 200ms ease-out infinite alternate 50ms' }} />
                      <line x1="-18" y1="71" x2="0" y2="71" stroke="#FFD700" strokeWidth="0.8" opacity="0.6" style={{ animation: 'speedPulse 200ms ease-out infinite alternate 100ms' }} />
                      <line x1="-10" y1="76" x2="0" y2="76" stroke="#FFD700" strokeWidth="0.8" opacity="0.3" style={{ animation: 'speedPulse 200ms ease-out infinite alternate 150ms' }} />
                    </g>
                  )}

                  {/* 1. Main lower hull */}
                  <path
                    d="M 10,75 Q 30,60 60,58 Q 90,56 120,55 Q 150,52 180,53 Q 210,54 240,58 Q 260,65 275,72 L 275,80 Q 240,82 200,82 Q 170,83 140,82 Q 100,83 60,82 Q 30,82 10,80 Z"
                    fill="#0d1117"
                    stroke="#FFD700"
                    strokeWidth="0.3"
                  />

                  {/* 2. Cockpit canopy */}
                  <path
                    d="M 140,55 Q 148,40 158,36 Q 168,33 178,36 Q 188,40 192,50 Q 185,54 165,55 Z"
                    fill="#1a2535"
                    stroke="#FFD700"
                    strokeWidth="0.2"
                  />
                  <ellipse cx="165" cy="44" rx="12" ry="5" fill="rgba(255,215,0,0.08)" />

                  {/* 3. Rear bat-wing fins */}
                  <path d="M 220,55 Q 225,30 235,18 Q 240,12 245,18 Q 248,28 246,45 Q 240,52 230,55 Z" fill="#111827" stroke="#FFD700" strokeWidth="0.3" />
                  <path d="M 238,55 Q 243,25 250,15 Q 255,8 260,15 Q 263,28 258,50 L 248,55 Z" fill="#111827" stroke="#FFD700" strokeWidth="0.3" />
                  <path d="M 250,52 Q 256,30 264,20 Q 268,14 272,20 Q 274,32 270,50 Q 265,55 255,55 Z" fill="#111827" stroke="#FFD700" strokeWidth="0.3" />

                  {/* 4. Front nose extension */}
                  <path d="M 10,68 Q 5,70 2,72 L 2,76 Q 5,76 10,75 Z" fill="#0d1117" />

                  {/* 5. Turbine/exhaust between wheels */}
                  <ellipse cx="155" cy="72" rx="18" ry="7" fill="#1a2535" stroke="#FFD700" strokeWidth="0.2" />
                  <line x1="140" y1="69" x2="170" y2="69" stroke="#2a3a4a" strokeWidth="0.5" />
                  <line x1="140" y1="71" x2="170" y2="71" stroke="#2a3a4a" strokeWidth="0.5" />
                  <line x1="140" y1="73" x2="170" y2="73" stroke="#2a3a4a" strokeWidth="0.5" />
                  <line x1="140" y1="75" x2="170" y2="75" stroke="#2a3a4a" strokeWidth="0.5" />

                  {/* 6. Body panel lines */}
                  <path d="M 60,62 Q 80,64 110,65" stroke="#1e293b" strokeWidth="0.4" fill="none" />
                  <path d="M 120,60 Q 150,62 180,60" stroke="#1e293b" strokeWidth="0.4" fill="none" />

                  {/* 7. Bat emblem on hood */}
                  <path d="M 94,66 L 97,64 L 99,67 L 101,64 L 104,66 L 101,69 Z" fill="#FFD700" opacity="0.7" />

                  {/* 8. Front Wheel */}
                  <g>
                    <circle cx="65" cy="80" r="14" fill="#0a0e1a" stroke="#1e293b" strokeWidth="0.5" />
                    <circle cx="65" cy="80" r="9" fill="#111827" stroke="#FFD700" strokeWidth="0.4" />
                    <circle cx="65" cy="80" r="4" fill="#1e293b" />
                    {[0, 1, 2, 3, 4].map(k => (
                      <line
                        key={`fw-spoke-${k}`}
                        x1="65"
                        y1="80"
                        x2={65 + 9 * Math.cos(k * Math.PI * 0.4)}
                        y2={80 + 9 * Math.sin(k * Math.PI * 0.4)}
                        stroke="#FFD700"
                        strokeWidth="0.4"
                      />
                    ))}
                  </g>

                  {/* 9. Rear Wheel */}
                  <g>
                    <circle cx="220" cy="80" r="18" fill="#0a0e1a" stroke="#1e293b" strokeWidth="0.5" />
                    <circle cx="220" cy="80" r="12" fill="#111827" stroke="#FFD700" strokeWidth="0.4" />
                    <circle cx="220" cy="80" r="5" fill="#1e293b" />
                    {[0, 1, 2, 3, 4].map(k => (
                      <line
                        key={`rw-spoke-${k}`}
                        x1="220"
                        y1="80"
                        x2={220 + 12 * Math.cos(k * Math.PI * 0.4)}
                        y2={80 + 12 * Math.sin(k * Math.PI * 0.4)}
                        stroke="#FFD700"
                        strokeWidth="0.4"
                      />
                    ))}
                  </g>

                  {/* 10. Red Tail lights on fins */}
                  <g filter="url(#redGlow)">
                    <ellipse cx="268" cy="40" rx="2.5" ry="2.5" fill="#cc2200" />
                    <ellipse cx="265" cy="47" rx="2" ry="2" fill="#cc2200" />
                    <ellipse cx="263" cy="53" rx="1.5" ry="1.5" fill="#cc2200" />
                  </g>

                  {/* 11. Headlight & Beam */}
                  <ellipse cx="2" cy="70" rx="8" ry="4" fill="url(#headlightGlow)" opacity="0.6" />
                  <ellipse cx="8" cy="70" rx="3" ry="2" fill="#FFD700" />
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
                    boxShadow: '0 0 8px rgba(255,215,0,0.5)',
                  }}
                />
              </div>
              <div className="text-right text-[11px] text-[#64748b] font-mono mt-1">
                {progress}%
              </div>
            </div>

            {/* Centered MM:SS in 48px monospace */}
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

  // FIX 1: Render as modal overlay if onClose is provided
  if (onClose) {
    return (
      <div
        className="fixed inset-0 bg-black/85 backdrop-blur-[4px] z-[9999] flex items-center justify-center p-4"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="w-[90vw] max-w-[680px]">
          {timerCard}
        </div>
      </div>
    );
  }

  return timerCard;
}

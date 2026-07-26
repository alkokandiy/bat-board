import React, { useState, useEffect, useRef, useMemo } from 'react';

// ==========================================
// FLIP DIGIT COMPONENT (BUG-FIXED ARCHITECTURE)
// ==========================================
function FlipDigit({ digit }) {
  const [displayDigit, setDisplayDigit] = useState(digit);
  const [prevDigit, setPrevDigit] = useState(digit);
  const [flipping, setFlipping] = useState(false);

  useEffect(() => {
    if (digit !== displayDigit && !flipping) {
      setFlipping(true);
      setPrevDigit(displayDigit);

      const t1 = setTimeout(() => {
        setDisplayDigit(digit);
      }, 300);

      const t2 = setTimeout(() => {
        setFlipping(false);
      }, 450);

      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [digit, displayDigit, flipping]);

  return (
    <div className="relative w-[60px] h-[80px] rounded-[6px] border border-[#334155] select-none" style={{ perspective: '200px' }}>
      {/* Static Top Half (shows displayDigit) */}
      <div className="absolute top-0 left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b] rounded-t-[5px]">
        <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[60px] text-[#FFD700] leading-[80px]">
          {displayDigit}
        </div>
      </div>

      {/* Static Bottom Half (shows displayDigit) */}
      <div className="absolute top-[40px] left-0 right-0 h-[40px] overflow-hidden bg-[#1a2535] rounded-b-[5px]">
        <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[60px] text-[#FFD700] leading-[80px] -mt-[40px]">
          {displayDigit}
        </div>
      </div>

      {/* Top Flap Phase 1 (0-300ms): shows prevDigit top half, folds away upward */}
      {flipping && (
        <div
          className="absolute top-0 left-0 right-0 h-[40px] overflow-hidden bg-[#1e293b] rounded-t-[5px] z-10"
          style={{
            transformOrigin: 'center bottom',
            animation: 'flipTop 300ms ease-in forwards',
            backfaceVisibility: 'hidden'
          }}
        >
          <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[60px] text-[#FFD700] leading-[80px]">
            {prevDigit}
          </div>
        </div>
      )}

      {/* Bottom Flap Phase 2 (150ms-450ms): shows new digit bottom half, unfolds downward */}
      {flipping && (
        <div
          className="absolute top-[40px] left-0 right-0 h-[40px] overflow-hidden bg-[#1a2535] rounded-b-[5px] z-10"
          style={{
            transformOrigin: 'center top',
            animation: 'flipBottom 300ms ease-out 150ms forwards',
            backfaceVisibility: 'hidden'
          }}
        >
          <div className="h-[80px] w-full flex items-center justify-center font-share-tech text-[60px] text-[#FFD700] leading-[80px] -mt-[40px]">
            {digit}
          </div>
        </div>
      )}

      {/* 1px dark divider line */}
      <div className="absolute top-[39.5px] left-0 right-0 h-[1px] bg-[#0a0e1a] z-20 pointer-events-none" />
    </div>
  );
}

// ==========================================
// BATMAN LOGO PIXEL GRID GENERATOR
// ==========================================
function buildLogoGrid() {
  const grid = [];

  // Left-half bat silhouette matrix (12 rows x 10 cols)
  // Mirroring across center creates a 20-col wide symmetrical bat shape
  const BAT_HALF = [
    [0,0,0,0,1,0,0,0,0,0], // r0: ear tip
    [0,0,0,1,1,1,0,0,0,0], // r1: ear base
    [0,0,1,1,1,1,1,0,0,0], // r2: head/shoulder
    [0,1,1,1,1,1,1,1,0,1], // r3: shoulders & head
    [1,1,1,1,1,1,1,1,1,1], // r4: wing spread upper
    [1,1,1,1,1,1,1,1,1,1], // r5: wing spread max
    [1,1,1,1,1,1,1,1,1,1], // r6: wing body
    [1,1,1,1,0,1,1,1,1,1], // r7: wing scallop 1
    [1,1,0,0,0,0,1,1,1,1], // r8: wing scallop 2
    [0,0,0,0,0,0,0,1,1,1], // r9: bottom body
    [0,0,0,0,0,0,0,0,1,1], // r10: tail upper
    [0,0,0,0,0,0,0,0,0,1], // r11: tail tip
  ];

  for (let r = 0; r < 28; r++) {
    const row = [];
    for (let c = 0; c < 40; c++) {
      // Outer yellow ellipse formula: ((col-20)/19)² + ((row-14)/13)² <= 1
      const normC = (c - 20) / 19;
      const normR = (r - 14) / 13;
      const inOval = (normC * normC + normR * normR) <= 1.0;

      if (!inOval) {
        row.push(0); // 0 = background outside logo (never fills)
        continue;
      }

      // Bat silhouette inside oval (rows 8..19, cols 10..29)
      const batR = r - 8;
      const batC = c - 10;
      let isBat = false;

      if (batR >= 0 && batR < 12 && batC >= 0 && batC < 20) {
        const halfC = batC < 10 ? batC : 19 - batC;
        if (BAT_HALF[batR][halfC] === 1) {
          isBat = true;
        }
      }

      row.push(isBat ? 2 : 1); // 2 = black bat (always dark), 1 = yellow oval area
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
}) {
  const [internalTimeLeft, setInternalTimeLeft] = useState(25 * 60);
  const [internalTotalTime, setInternalTotalTime] = useState(25 * 60);
  const [internalRunning, setInternalRunning] = useState(false);
  const [mode, setMode] = useState('N'); // 'N' | 'F' | 'B' | 'M'

  const carContainerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(600);

  const isControlled = propTimeLeft !== undefined;
  const timeLeft = isControlled ? propTimeLeft : internalTimeLeft;
  const totalTime = isControlled ? (propTotalTime || 25 * 60) : internalTotalTime;
  const running = isControlled ? propRunning : internalRunning;

  // Measure car container width for Mode 4
  useEffect(() => {
    if (mode === 'M' && carContainerRef.current) {
      const updateWidth = () => {
        if (carContainerRef.current) {
          setContainerWidth(carContainerRef.current.offsetWidth);
        }
      };
      updateWidth();
      window.addEventListener('resize', updateWidth);
      return () => window.removeEventListener('resize', updateWidth);
    }
  }, [mode]);

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

  // Mode 3 Pixel Logo data & fill order calculation
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
      set.add(`${r}-${c}`);
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

  // Batmobile car position
  const carWidth = 300;
  const maxTravel = Math.max(0, containerWidth - carWidth);
  const carX = (progress / 100) * maxTravel;

  return (
    <div className="w-full bg-[#0a0e1a] rounded-2xl p-8 min-h-[400px] flex flex-col items-center justify-between text-slate-100 font-sans border border-slate-800/80">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

        .font-share-tech {
          font-family: 'Share Tech Mono', monospace;
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
          { id: 'B', label: 'B', title: 'Batman Pixel Logo' },
          { id: 'M', label: 'M', title: '1989 Batmobile' },
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
            <div className="flex items-center justify-center gap-2">
              <FlipDigit digit={minTens} />
              <FlipDigit digit={minUnits} />
              <span className="font-share-tech text-[52px] text-[#FFD700] pb-2 select-none">:</span>
              <FlipDigit digit={secTens} />
              <FlipDigit digit={secUnits} />
            </div>
            <div className="text-[#64748b] text-[12px] font-mono tracking-[2px] mt-4 uppercase">
              {progress}% ELAPSED
            </div>
          </div>
        )}

        {/* Mode 3: [B] Batman Logo Pixel Fill */}
        {mode === 'B' && (
          <div className="flex flex-col items-center justify-center">
            {/* Pixel Grid Canvas (40 cols x 28 rows, 9x9px cells with 1px gap) */}
            <div
              className="grid gap-[1px] p-2 bg-[#0a0e1a] rounded-lg select-none"
              style={{
                gridTemplateColumns: 'repeat(40, 9px)',
                gridTemplateRows: 'repeat(28, 9px)'
              }}
            >
              {logoGrid.map((row, r) =>
                row.map((val, c) => {
                  if (val === 0) {
                    return <div key={`${r}-${c}`} className="w-[9px] h-[9px] bg-transparent" />;
                  }
                  if (val === 2) {
                    // Black Bat silhouette cell (always dark)
                    return <div key={`${r}-${c}`} className="w-[9px] h-[9px] rounded-[1px] bg-[#0a0e1a]" />;
                  }
                  // val === 1: Yellow Oval area
                  const isFilled = filledSet.has(`${r}-${c}`);
                  return (
                    <div
                      key={`${r}-${c}`}
                      className={`w-[9px] h-[9px] rounded-[1px] transition-colors duration-300 ${
                        isFilled
                          ? 'bg-[#FFD700] shadow-[0_0_3px_rgba(255,215,0,0.4)]'
                          : 'bg-[#1e293b]'
                      }`}
                    />
                  );
                })
              )}
            </div>
            <div className="text-[#64748b] text-[12px] font-mono tracking-[2px] mt-3 uppercase">
              {progress}% ELAPSED
            </div>
          </div>
        )}

        {/* Mode 4: [M] Realistic 1989 Batmobile */}
        {mode === 'M' && (
          <div className="w-full flex flex-col items-center justify-center px-2">
            {/* Position relative car container */}
            <div ref={carContainerRef} className="w-full relative h-[100px] overflow-visible mb-2">
              <div
                style={{
                  position: 'absolute',
                  bottom: '20px',
                  left: `${carX}px`,
                  transition: 'left 0.5s linear',
                  width: '300px',
                  height: '100px'
                }}
              >
                {/* 1989 Batmobile SVG */}
                <svg width="300" height="100" viewBox="0 0 300 100" className="overflow-visible">
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
                          transformOrigin: '275px 75px'
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
                    boxShadow: '0 0 8px rgba(255,215,0,0.5)'
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
}

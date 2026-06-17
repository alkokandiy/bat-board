import React from 'react';

export default function BatProgress({ progress, className = '' }) {
  const pct = Math.max(0, Math.min(100, progress));

  const batarangPath = 'M50 5 L65 35 L95 50 L65 65 L50 95 L35 65 L5 50 L35 35 Z';

  return (
    <div className={`flex flex-col items-center gap-4 ${className}`}>
      {/* Batarang fill animation */}
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-lg">
          <defs>
            <linearGradient id="batGrad" x1="0" y1="1" x2="0" y2="0">
              <stop offset={`${pct}%`} stopColor="#f5c842" />
              <stop offset={`${pct}%`} stopColor="#1a1a22" />
            </linearGradient>
            <filter id="batGlow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path d={batarangPath} fill="none" stroke="#333" strokeWidth="2" />
          <path d={batarangPath} fill="url(#batGrad)" stroke="#f5c842" strokeWidth="2" filter="url(#batGlow)" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[10px] font-mono text-slate-400 font-bold">{Math.round(pct)}%</span>
        </div>
      </div>

      {/* Batmobile driving track */}
      <div className="relative w-full max-w-xs h-10">
        {/* road */}
        <div className="absolute bottom-3 left-0 right-0 h-1 bg-slate-800 rounded-full overflow-hidden">
          <div className="h-full bg-electric-bat-yellow transition-all duration-300" style={{ width: `${pct}%` }} />
        </div>
        {/* road dashes */}
        <div className="absolute bottom-2 left-0 right-0 flex justify-around">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="w-2 h-[2px] bg-slate-700" />
          ))}
        </div>
        {/* batmobile */}
        <div
          className="absolute bottom-4 transition-all duration-500 ease-linear"
          style={{ left: `calc(${pct}% - 12px)` }}
        >
          <svg width="24" height="14" viewBox="0 0 24 14" className="drop-shadow-lg">
            <defs>
              <linearGradient id="carGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#333" />
                <stop offset="100%" stopColor="#111" />
              </linearGradient>
            </defs>
            {/* body */}
            <path d="M3 10 L5 4 L8 3 L12 2 L16 3 L19 4 L21 10 Z" fill="url(#carGrad)" stroke="#555" strokeWidth="0.5" />
            {/* windshield */}
            <path d="M7 3.5 L10 2.5 L12 2.5 L15 3.5 Z" fill="#1a1a2e" opacity="0.8" />
            {/* wheels */}
            <circle cx="7" cy="11" r="2.5" fill="#111" stroke="#333" strokeWidth="0.5" />
            <circle cx="17" cy="11" r="2.5" fill="#111" stroke="#333" strokeWidth="0.5" />
            {/* fins */}
            <path d="M3 8 L1 6 L3 7 Z" fill="#222" />
            <path d="M21 8 L23 6 L21 7 Z" fill="#222" />
            {/* light */}
            <circle cx="4" cy="6" r="0.8" fill={pct > 0 ? '#f5c842' : '#333'} />
            {/* exhaust */}
            {pct > 0 && pct < 100 && (
              <circle cx="2" cy="9" r="1" fill="#f5c842" opacity={0.3 + Math.random() * 0.3} />
            )}
          </svg>
        </div>
      </div>
    </div>
  );
}

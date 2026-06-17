import React from 'react';

export default function BatmobileProgress({ progress }) {
  const pct = Math.max(0, Math.min(100, progress));

  return (
    <div className="relative w-full h-32 mx-auto overflow-hidden">
      <div className="absolute inset-x-0 bottom-0 h-1 bg-slate-800 rounded-full">
        <div
          className="h-full bg-electric-bat-yellow rounded-full transition-all duration-500 ease-linear"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div
        className="absolute bottom-2 transition-all duration-500 ease-linear"
        style={{ left: `calc(${pct}% - 30px)` }}
      >
        <svg
          viewBox="0 0 120 50"
          className="w-[60px] h-[25px]"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Main body */}
          <path
            d="M 15 35 L 20 20 L 35 12 L 85 12 L 100 20 L 105 35 Z"
            fill="#1e293b"
            stroke="#FBBF24"
            strokeWidth="1"
          />
          {/* Bat-wing rear fins */}
          <path
            d="M 85 12 L 95 5 L 100 12 Z"
            fill="#FBBF24"
            opacity="0.8"
          />
          <path
            d="M 20 20 L 15 10 L 25 18 Z"
            fill="#FBBF24"
            opacity="0.8"
          />
          {/* Cockpit */}
          <path
            d="M 45 12 L 50 6 L 65 6 L 70 12 Z"
            fill="#0f172a"
            stroke="#FBBF24"
            strokeWidth="0.5"
          />
          {/* Windshield */}
          <path
            d="M 50 6 L 55 3 L 62 3 L 65 6 Z"
            fill="#FBBF24"
            opacity="0.4"
          />
          {/* Front grille */}
          <rect x="95" y="22" width="10" height="8" rx="1" fill="#0f172a" stroke="#FBBF24" strokeWidth="0.5" />
          {/* Rear exhaust */}
          <rect x="12" y="24" width="4" height="6" rx="1" fill="#FBBF24" opacity="0.6" />
          {/* Left wheel */}
          <circle cx="30" cy="37" r="6" fill="#0f172a" stroke="#FBBF24" strokeWidth="1.5" />
          <circle cx="30" cy="37" r="2.5" fill="#FBBF24" opacity="0.3" />
          {/* Right wheel */}
          <circle cx="85" cy="37" r="6" fill="#0f172a" stroke="#FBBF24" strokeWidth="1.5" />
          <circle cx="85" cy="37" r="2.5" fill="#FBBF24" opacity="0.3" />
          {/* Bat emblem on hood */}
          <path
            d="M 70 18 L 72 15 L 74 18 L 73 20 L 71 20 Z"
            fill="#FBBF24"
          />
          {/* Headlight glow */}
          <ellipse cx="105" cy="28" rx="4" ry="3" fill="#FBBF24" opacity={0.3 + pct / 200} />
          {/* Exhaust flames */}
          {pct > 0 && pct < 100 && (
            <path d="M 12 26 Q 6 24 4 26 Q 8 28 12 28 Z" fill="#F97316" opacity="0.7" />
          )}
          {pct > 20 && pct < 100 && (
            <path d="M 12 28 Q 5 27 3 29 Q 8 31 12 30 Z" fill="#EF4444" opacity="0.5" />
          )}
          {/* Speed lines when moving */}
          {pct > 5 && pct < 100 && (
            <>
              <line x1="0" y1="20" x2="8" y2="20" stroke="#FBBF24" strokeWidth="0.5" opacity="0.3" />
              <line x1="-2" y1="26" x2="6" y2="26" stroke="#FBBF24" strokeWidth="0.5" opacity="0.2" />
              <line x1="2" y1="32" x2="10" y2="32" stroke="#FBBF24" strokeWidth="0.5" opacity="0.25" />
            </>
          )}
        </svg>
      </div>

      <div className="absolute bottom-[-4px] right-0">
        <span className="text-[10px] font-mono text-slate-500">{Math.round(pct)}%</span>
      </div>
    </div>
  );
}

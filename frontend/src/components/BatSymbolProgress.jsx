import React from 'react';

export default function BatSymbolProgress({ progress }) {
  const pct = Math.max(0, Math.min(100, progress));

  return (
    <div className="relative w-48 h-56 mx-auto">
      <div
        className="absolute inset-0 rounded-full blur-3xl transition-opacity duration-700 pointer-events-none"
        style={{
          background: `radial-gradient(circle, rgba(255,215,0,${pct / 250}) 0%, transparent 70%)`,
        }}
      />

      <svg viewBox="0 0 200 200" className="w-full h-full relative z-10">
        <defs>
          <linearGradient id="batFill" x1="0" y1="1" x2="0" y2="0">
            <stop offset={`${pct}%`} stopColor="#FFD700" />
            <stop offset={`${pct}%`} stopColor="#1e293b" />
          </linearGradient>
          <filter id="batGlow">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g filter="url(#batGlow)">
          <path
            d="M 100 15
               C 95 28, 82 35, 70 37
               C 50 38, 28 42, 10 52
               C 20 56, 30 60, 36 65
               C 24 68, 14 76, 5 88
               C 18 82, 34 78, 44 80
               C 34 88, 22 102, 12 120
               C 28 108, 46 100, 58 100
               C 48 114, 40 130, 35 148
               C 48 136, 62 126, 74 120
               C 78 130, 82 140, 90 152
               C 95 158, 100 162, 100 162
               C 100 162, 105 158, 110 152
               C 118 140, 122 130, 126 120
               C 138 126, 152 136, 165 148
               C 160 130, 152 114, 142 100
               C 154 100, 172 108, 188 120
               C 178 102, 166 88, 156 80
               C 166 78, 182 82, 195 88
               C 186 76, 176 68, 164 65
               C 170 60, 180 56, 190 52
               C 172 42, 150 38, 130 37
               C 118 35, 105 28, 100 15
               Z"
            fill="url(#batFill)"
          />
        </g>
      </svg>

      <div className="text-center mt-3">
        <span className="text-electric-bat-yellow font-mono text-xs font-bold tracking-wider">
          {Math.round(pct)}%
        </span>
      </div>
    </div>
  );
}

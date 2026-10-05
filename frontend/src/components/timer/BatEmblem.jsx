import React, { useId } from 'react';

// Original Nolan-era-style bat emblem: sharp ears, swept wings, and a
// claw-pointed trailing edge. One continuous, perfectly symmetric outline
// (the right half was drawn by hand and mirrored; no seam). viewBox 480 × 150.
export const EMBLEM_W = 480;
export const EMBLEM_H = 150;

const BAT_PATH =
  'M 240,40 L 244.5,20 L 245.5,1.5 L 255,13 L 263,34 C 292,27 336,18 380,19 C 416,20 450,32 476,54 Q 452,56 442,100 Q 424,62 392,108 Q 376,68 340,110 Q 322,76 292,104 Q 280,84 262,96 C 254,108 247,124 240,148 C 233,124 226,108 218,96 Q 200,84 188,104 Q 158,76 140,110 Q 104,68 88,108 Q 56,62 38,100 Q 28,56 4,54 C 30,32 64,20 100,19 C 144,18 188,27 217,34 L 225,13 L 234.5,1.5 L 235.5,20 L 240,40 Z';

// `progress` is 0–100: the emblem fills with light from the bottom up.
export default function BatEmblem({ progress = 0, className = '' }) {
  const id = useId().replace(/:/g, '');
  const p = Math.max(0, Math.min(100, progress));
  // At 100% the clip opens fully so the glow isn't cut off at the ears.
  const fillTop = p >= 100 ? -60 : EMBLEM_H - (p / 100) * EMBLEM_H;

  return (
    <svg
      data-testid="bat-emblem"
      viewBox={`0 0 ${EMBLEM_W} ${EMBLEM_H}`}
      className={`overflow-visible ${className}`}
      role="img"
      aria-label={`Bat emblem, ${Math.round(p)}% elapsed`}
    >
      <defs>
        <path id={`${id}-bat`} d={BAT_PATH} />

        {/* Soft bloom for the lit part */}
        <filter id={`${id}-glow`} x="-15%" y="-30%" width="130%" height="170%">
          <feGaussianBlur stdDeviation="7" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Metallic body: brighter along the wing crest, deeper toward the tail */}
        <linearGradient id={`${id}-lit`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFF1A8" />
          <stop offset="35%" stopColor="#FFD700" />
          <stop offset="100%" stopColor="#E0A800" />
        </linearGradient>

        {/* Unlit body: dark steel with a faint top-light */}
        <linearGradient id={`${id}-dark`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#27324a" />
          <stop offset="100%" stopColor="#0f1627" />
        </linearGradient>

        <clipPath id={`${id}-reveal`}>
          <rect x="-40" y={fillTop} width={EMBLEM_W + 80} height={EMBLEM_H + 160} />
        </clipPath>
      </defs>

      {/* Unlit emblem: always visible */}
      <use href={`#${id}-bat`} fill={`url(#${id}-dark)`} stroke="#3a4766" strokeWidth="1.2" strokeLinejoin="round" />

      {/* Lit part, revealed from the bottom as time passes */}
      <g clipPath={`url(#${id}-reveal)`}>
        <use href={`#${id}-bat`} fill={`url(#${id}-lit)`} stroke="#FFE680" strokeWidth="0.8" strokeLinejoin="round" filter={`url(#${id}-glow)`} />
      </g>
    </svg>
  );
}
